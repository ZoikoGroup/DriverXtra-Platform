"""Security issue 1: support attachment exposure and test media isolation.

- Test runs write uploads only into a per-process temporary directory, never into the real
  backend/media or backend/private_media directories.
- DEBUG defaults to False when the DEBUG environment variable is unset.
- With DEBUG=False the public /media/ route is not mounted, so legacy support attachments that
  still sit under MEDIA_ROOT are not reachable by URL.
- Legacy attachments remain downloadable through the authenticated, permission-checked endpoint.
"""
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pytest
from django.conf import settings as django_settings
from django.core.files.storage import default_storage
from rest_framework import status
from rest_framework.test import APIClient

from apps.identity.models import RoleChoices, User
from apps.marketplace.models import private_vehicle_document_storage
from apps.support.models import private_support_storage
from apps.support.services import TicketService

BASE_DIR = Path(django_settings.BASE_DIR)
REAL_MEDIA_DIRS = (BASE_DIR / 'media', BASE_DIR / 'private_media')
PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"


def _snapshot(dirs):
    files = set()
    for d in dirs:
        if d.exists():
            files.update(str(p) for p in d.rglob('*') if p.is_file())
    return files


def _is_within(path, parent) -> bool:
    try:
        Path(path).resolve().relative_to(Path(parent).resolve())
        return True
    except ValueError:
        return False


def _load_urlconf(module_name):
    """Executes config/urls.py into a fresh module under the CURRENT settings (e.g. DEBUG)."""
    spec = importlib.util.spec_from_file_location(module_name, BASE_DIR / 'config' / 'urls.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def urlconf_with_debug(settings):
    """Returns a function that mounts config/urls.py as built with the given DEBUG value."""
    loaded = []

    def mount(debug: bool):
        settings.DEBUG = debug
        name = f"tests._urlconf_debug_{str(debug).lower()}_{uuid.uuid4().hex}"
        _load_urlconf(name)
        loaded.append(name)
        settings.ROOT_URLCONF = name  # setting_changed clears the URL resolver caches
        return name

    yield mount
    for name in loaded:
        sys.modules.pop(name, None)


def _legacy_attachment(customer):
    """Creates an attachment whose file exists only under MEDIA_ROOT (pre-private-storage layout)."""
    ticket = TicketService.create_ticket(
        customer=customer,
        subject="Legacy media exposure check",
        description="Legacy attachment stored under MEDIA_ROOT.",
    )
    upload = io.BytesIO(PDF_BYTES)
    upload.name = "legacy_statement.pdf"
    attachment = TicketService.attach_file(ticket=ticket, uploader=customer, file_obj=upload)

    private_path = Path(attachment.file.storage.location) / attachment.file.name
    legacy_path = Path(django_settings.MEDIA_ROOT) / attachment.file.name
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_bytes(private_path.read_bytes())
    private_path.unlink()
    return attachment, legacy_path, private_path


def _other_buyer():
    user = User.objects.create_user(email='other_media_buyer@driverxtra.com', password='SecurePassword123!',
                                    is_email_verified=True)
    user.add_role(RoleChoices.BUYER)
    return user


# --- Test isolation -----------------------------------------------------------------------------

def test_test_run_storage_roots_are_temporary_and_outside_the_project():
    media_root = Path(django_settings.MEDIA_ROOT)
    private_root = Path(django_settings.PRIVATE_STORAGE_ROOT)
    for root in (media_root, private_root):
        assert not _is_within(root, BASE_DIR), root
        assert _is_within(root, tempfile.gettempdir()), root
    # Storages bound at import time resolve to the temporary roots as well.
    assert _is_within(private_support_storage.location, private_root)
    assert _is_within(private_vehicle_document_storage.location, private_root)
    assert Path(default_storage.location).resolve() == media_root.resolve()


@pytest.mark.django_db
def test_uploads_during_tests_never_touch_real_media_directories(buyer_user):
    before = _snapshot(REAL_MEDIA_DIRS)
    attachment, legacy_path, _ = _legacy_attachment(buyer_user)
    # Re-upload into private storage as well, covering both write paths.
    upload = io.BytesIO(PDF_BYTES)
    upload.name = "private_statement.pdf"
    second = TicketService.attach_file(ticket=attachment.ticket, uploader=buyer_user, file_obj=upload)

    assert legacy_path.exists() and _is_within(legacy_path, django_settings.MEDIA_ROOT)
    assert second.file.storage.exists(second.file.name)
    assert _is_within(second.file.path, django_settings.PRIVATE_STORAGE_ROOT)
    assert _snapshot(REAL_MEDIA_DIRS) == before


# --- DEBUG default ------------------------------------------------------------------------------

def test_debug_defaults_to_false_when_environment_variable_is_unset():
    """Imports config.settings in a clean interpreter with no DEBUG variable and no .env loading."""
    env = {k: v for k, v in os.environ.items() if k not in ('DEBUG', 'IS_TESTING')}
    env['SECRET_KEY'] = 'debug-default-check-secret-key-not-used-anywhere'
    code = (
        "import dotenv\n"
        "dotenv.load_dotenv = lambda *a, **k: False\n"  # ignore the developer's local .env
        "import config.settings as s\n"
        "print('DEBUG=%s' % s.DEBUG)\n"
    )
    result = subprocess.run([sys.executable, '-c', code], cwd=str(BASE_DIR), env=env,
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert 'DEBUG=False' in result.stdout


@pytest.mark.parametrize('raw,expected', [('True', True), ('true', True), ('1', True), ('yes', True),
                                          ('False', False), ('0', False), ('', False)])
def test_debug_is_enabled_only_by_an_explicit_truthy_value(raw, expected):
    env = {k: v for k, v in os.environ.items() if k != 'IS_TESTING'}
    env.update({'SECRET_KEY': 'debug-default-check-secret-key-not-used-anywhere', 'DEBUG': raw})
    code = (
        "import dotenv\n"
        "dotenv.load_dotenv = lambda *a, **k: False\n"
        "import config.settings as s\n"
        "print('DEBUG=%s' % s.DEBUG)\n"
    )
    result = subprocess.run([sys.executable, '-c', code], cwd=str(BASE_DIR), env=env,
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert f'DEBUG={expected}' in result.stdout


# --- Public media exposure ----------------------------------------------------------------------

@pytest.mark.django_db
def test_legacy_attachment_not_served_by_url_when_debug_false(buyer_user, urlconf_with_debug):
    attachment, legacy_path, _ = _legacy_attachment(buyer_user)
    urlconf_with_debug(False)
    url = f"{django_settings.MEDIA_URL}{attachment.file.name}"

    for client in (APIClient(), _authed(buyer_user)):
        res = client.get(url)
        assert res.status_code == status.HTTP_404_NOT_FOUND
        assert PDF_BYTES not in b''.join(getattr(res, 'streaming_content', [res.content]))
    assert legacy_path.exists()  # nothing was moved or deleted by the denied requests


@pytest.mark.django_db
def test_media_route_is_debug_only_control(buyer_user, urlconf_with_debug):
    """Control for the test above: with DEBUG=True the same URL is served, proving the 404 is
    caused by DEBUG=False and not by a wrong URL."""
    attachment, _, _ = _legacy_attachment(buyer_user)
    urlconf_with_debug(True)
    res = APIClient().get(f"{django_settings.MEDIA_URL}{attachment.file.name}")
    assert res.status_code == status.HTTP_200_OK


@pytest.mark.django_db
@pytest.mark.parametrize('debug', [False, True])
def test_private_storage_is_never_served_by_url(buyer_user, urlconf_with_debug, debug):
    ticket = TicketService.create_ticket(customer=buyer_user, subject="Private storage URL check",
                                         description="Private attachment must not be URL-addressable.")
    upload = io.BytesIO(PDF_BYTES)
    upload.name = "private_only.pdf"
    attachment = TicketService.attach_file(ticket=ticket, uploader=buyer_user, file_obj=upload)
    urlconf_with_debug(debug)
    client = APIClient()
    for url in (f"{django_settings.MEDIA_URL}{attachment.file.name}",
                f"/private_media/{attachment.file.name}"):
        assert client.get(url).status_code == status.HTTP_404_NOT_FOUND, url
    # Path traversal out of MEDIA_ROOT: 404 when the media route is not mounted (DEBUG=False);
    # rejected by Django's safe_join as a SuspiciousFileOperation (400) when it is (DEBUG=True).
    res = client.get(f"{django_settings.MEDIA_URL}../private_media/{attachment.file.name}")
    assert res.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND)
    assert PDF_BYTES not in b''.join(getattr(res, 'streaming_content', [res.content]))
    with pytest.raises(ValueError):
        attachment.file.url  # private storage exposes no public URL


# --- Authenticated legacy downloads are preserved -----------------------------------------------

def _authed(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_legacy_attachment_download_still_works_through_authenticated_endpoint_with_debug_false(
        buyer_user, urlconf_with_debug):
    attachment, legacy_path, private_path = _legacy_attachment(buyer_user)
    urlconf_with_debug(False)
    endpoint = f'/api/v1/support/attachments/{attachment.id}/'

    # Anonymous and unrelated users are refused, and nothing is copied for them.
    assert APIClient().get(endpoint).status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
    assert _authed(_other_buyer()).get(endpoint).status_code == status.HTTP_403_FORBIDDEN
    assert not private_path.exists()

    # The ticket owner downloads it; the file is copied into private storage on demand.
    res = _authed(buyer_user).get(endpoint)
    assert res.status_code == status.HTTP_200_OK
    assert res['Content-Type'] == 'application/pdf'
    assert b''.join(res.streaming_content) == PDF_BYTES
    assert private_path.exists()
    assert legacy_path.exists()  # the legacy original is not deleted
