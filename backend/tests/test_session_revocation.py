"""Session-version revocation (migration 0008 trigger + 'sv' JWT claim).

Every suspension pathway (Model.save, QuerySet.update, bulk_update, raw SQL) must:
  - block old access and refresh tokens while suspended;
  - keep them blocked after reactivation;
  - allow an immediate fresh login;
and unrelated updates must not change the session version. Tests use real Bearer tokens.
These tests are vendor-neutral: run against PostgreSQL they validate the PostgreSQL trigger.
"""
import importlib

import jwt
import pytest
from django.conf import settings
from django.core import signing
from django.db import connection
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.identity.authentication import stamp_session_version
from apps.identity.models import AccountStatusChoices, RoleChoices, User

PATHWAYS = ['save', 'queryset_update', 'bulk_update', 'raw_sql']
PASSWORD = 'SecurePassword123!'


# --------------------------------------------------------------------------- helpers

def _login(email, password=PASSWORD):
    res = APIClient().post('/api/v1/auth/login/', {'email': email, 'password': password}, format='json')
    assert res.status_code == status.HTTP_200_OK, res.content
    return res.json()['tokens']


def _me(access):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
    return client.get('/api/v1/users/me/')


def _refresh(refresh_token):
    return APIClient().post('/api/v1/auth/token/refresh/', {'refresh': refresh_token}, format='json')


def _version(user):
    return User.objects.values_list('session_version', flat=True).get(pk=user.pk)


def _sv_claim(token):
    return jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256']).get('sv')


def _write(user, pathway, **fields):
    """Persist ``fields`` on the user row through the given update pathway."""
    if pathway == 'save':
        fresh = User.objects.get(pk=user.pk)
        for name, value in fields.items():
            setattr(fresh, name, value)
        fresh.save()
    elif pathway == 'queryset_update':
        User.objects.filter(pk=user.pk).update(**fields)
    elif pathway == 'bulk_update':
        fresh = User.objects.get(pk=user.pk)
        for name, value in fields.items():
            setattr(fresh, name, value)
        User.objects.bulk_update([fresh], list(fields))
    elif pathway == 'raw_sql':
        table = connection.ops.quote_name(User._meta.db_table)
        assignments = ', '.join(f'{connection.ops.quote_name(name)} = %s' for name in fields)
        pk_value = User._meta.pk.get_db_prep_value(user.pk, connection)
        with connection.cursor() as cursor:
            cursor.execute(f'UPDATE {table} SET {assignments} WHERE id = %s', [*fields.values(), pk_value])
    else:  # pragma: no cover
        raise AssertionError(pathway)


# --------------------------------------------------------------------------- every pathway

@pytest.mark.django_db
@pytest.mark.parametrize('pathway', PATHWAYS)
def test_suspension_revokes_tokens_across_reactivation(buyer_user, pathway):
    tokens = _login(buyer_user.email)
    start = _version(buyer_user)
    assert _sv_claim(tokens['access']) == start

    _write(buyer_user, pathway, status=AccountStatusChoices.SUSPENDED)
    assert _version(buyer_user) == start + 1
    assert _me(tokens['access']).status_code == status.HTTP_401_UNAUTHORIZED
    assert _refresh(tokens['refresh']).status_code == status.HTTP_401_UNAUTHORIZED

    _write(buyer_user, pathway, status=AccountStatusChoices.ACTIVE)
    assert _version(buyer_user) == start + 1  # reactivation does not change the version
    old_me = _me(tokens['access'])
    assert old_me.status_code == status.HTTP_401_UNAUTHORIZED
    assert 'revoked' in str(old_me.json()).lower()
    assert _refresh(tokens['refresh']).status_code == status.HTTP_401_UNAUTHORIZED

    # Immediate fresh login works (no clock margin involved).
    new_tokens = _login(buyer_user.email)
    assert _sv_claim(new_tokens['access']) == start + 1
    assert _me(new_tokens['access']).status_code == status.HTTP_200_OK
    refreshed = _refresh(new_tokens['refresh'])
    assert refreshed.status_code == status.HTTP_200_OK
    assert _sv_claim(refreshed.json()['access']) == start + 1


@pytest.mark.django_db
@pytest.mark.parametrize('pathway', PATHWAYS)
def test_unrelated_updates_do_not_change_version(buyer_user, pathway):
    tokens = _login(buyer_user.email)
    start = _version(buyer_user)
    _write(buyer_user, pathway, first_name='Renamed')
    _write(buyer_user, pathway, status=AccountStatusChoices.ACTIVE)  # usable -> usable
    _write(buyer_user, pathway, is_active=True)
    assert _version(buyer_user) == start
    assert _me(tokens['access']).status_code == status.HTTP_200_OK
    assert _refresh(tokens['refresh']).status_code == status.HTTP_200_OK


@pytest.mark.django_db
@pytest.mark.parametrize('pathway', PATHWAYS)
@pytest.mark.parametrize('fields', [
    {'status': AccountStatusChoices.DEACTIVATED},
    {'is_active': False},
], ids=['deactivated', 'is_active_false'])
def test_other_unusable_states_increment_version(buyer_user, pathway, fields):
    tokens = _login(buyer_user.email)
    start = _version(buyer_user)
    _write(buyer_user, pathway, **fields)
    assert _version(buyer_user) == start + 1
    _write(buyer_user, pathway, status=AccountStatusChoices.ACTIVE, is_active=True)
    assert _me(tokens['access']).status_code == status.HTTP_401_UNAUTHORIZED
    assert _refresh(tokens['refresh']).status_code == status.HTTP_401_UNAUTHORIZED
    assert _me(_login(buyer_user.email)['access']).status_code == status.HTTP_200_OK


# --------------------------------------------------------------------------- transitions & monotonicity

@pytest.mark.django_db
def test_repeated_transitions_increment_only_on_usable_to_unusable(buyer_user):
    S, D, A = AccountStatusChoices.SUSPENDED, AccountStatusChoices.DEACTIVATED, AccountStatusChoices.ACTIVE
    steps = [
        ({'status': S}, 1),                    # ACTIVE -> SUSPENDED
        ({'status': D}, 1),                    # SUSPENDED -> DEACTIVATED (already unusable)
        ({'is_active': False}, 1),             # still unusable
        ({'status': A, 'is_active': True}, 1),  # reactivation
        ({'status': A}, 1),                    # no-op
        ({'status': S}, 2),                    # suspend again
        ({'status': A}, 2),                    # reactivate
        ({'is_active': False}, 3),             # deactivate via flag
        ({'is_active': True}, 3),
    ]
    for fields, expected in steps:
        User.objects.filter(pk=buyer_user.pk).update(**fields)
        assert _version(buyer_user) == expected, fields


@pytest.mark.django_db
def test_stale_instance_cannot_lower_version(buyer_user):
    stale = User.objects.get(pk=buyer_user.pk)  # session_version 0 in memory
    User.objects.filter(pk=buyer_user.pk).update(status=AccountStatusChoices.SUSPENDED)
    User.objects.filter(pk=buyer_user.pk).update(status=AccountStatusChoices.ACTIVE)
    assert _version(buyer_user) == 1

    stale.first_name = 'Stale write'
    stale.save()  # full save writes session_version=0 from memory
    assert _version(buyer_user) == 1

    User.objects.bulk_update([stale], ['first_name', 'session_version'])
    assert _version(buyer_user) == 1
    User.objects.filter(pk=buyer_user.pk).update(session_version=0)
    assert _version(buyer_user) == 1
    table = connection.ops.quote_name(User._meta.db_table)
    with connection.cursor() as cursor:
        cursor.execute(f'UPDATE {table} SET session_version = 0 WHERE id = %s',
                       [User._meta.pk.get_db_prep_value(buyer_user.pk, connection)])
    assert _version(buyer_user) == 1


@pytest.mark.django_db
def test_login_suspension_race_token_is_rejected(buyer_user):
    """A token minted from a user object read before a suspension carries the old version."""
    stale = User.objects.get(pk=buyer_user.pk)
    User.objects.filter(pk=buyer_user.pk).update(status=AccountStatusChoices.SUSPENDED)
    User.objects.filter(pk=buyer_user.pk).update(status=AccountStatusChoices.ACTIVE)

    refresh = RefreshToken.for_user(stale)
    stamp_session_version(refresh, stale)  # sv=0, the version seen by the in-flight login
    assert _me(str(refresh.access_token)).status_code == status.HTTP_401_UNAUTHORIZED
    assert _refresh(str(refresh)).status_code == status.HTTP_401_UNAUTHORIZED


# --------------------------------------------------------------------------- compatibility

@pytest.mark.django_db
def test_tokens_without_sv_claim_are_version_zero(buyer_user, seller_user):
    legacy = RefreshToken.for_user(buyer_user)  # no 'sv' claim, as issued before migration 0008
    assert 'sv' not in legacy.payload
    assert _me(str(legacy.access_token)).status_code == status.HTTP_200_OK
    refreshed = _refresh(str(legacy))
    assert refreshed.status_code == status.HTTP_200_OK
    assert _me(refreshed.json()['access']).status_code == status.HTTP_200_OK

    User.objects.filter(pk=seller_user.pk).update(status=AccountStatusChoices.SUSPENDED)
    User.objects.filter(pk=seller_user.pk).update(status=AccountStatusChoices.ACTIVE)
    legacy_seller = RefreshToken.for_user(seller_user)
    assert _me(str(legacy_seller.access_token)).status_code == status.HTTP_401_UNAUTHORIZED
    assert _refresh(str(legacy_seller)).status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_malformed_sv_claim_is_rejected(buyer_user):
    refresh = RefreshToken.for_user(buyer_user)
    refresh['sv'] = 'not-a-number'
    assert _me(str(refresh.access_token)).status_code == status.HTTP_401_UNAUTHORIZED
    assert _refresh(str(refresh)).status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_switch_role_and_staff_refresh_carry_session_version(buyer_user, staff_user):
    User.objects.filter(pk=buyer_user.pk).update(status=AccountStatusChoices.SUSPENDED)
    User.objects.filter(pk=buyer_user.pk).update(status=AccountStatusChoices.ACTIVE)
    buyer_user.add_role(RoleChoices.SELLER)
    tokens = _login(buyer_user.email)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    switched = client.post('/api/v1/auth/switch-role/', {'role': 'BUYER', 'refresh': tokens['refresh']}, format='json')
    assert switched.status_code == status.HTTP_200_OK
    new = switched.json()['tokens']
    assert _sv_claim(new['access']) == 1 and _sv_claim(new['refresh']) == 1
    assert _me(new['access']).status_code == status.HTTP_200_OK
    assert _refresh(tokens['refresh']).status_code == status.HTTP_401_UNAUTHORIZED  # old one blacklisted

    staff_tokens = _login(staff_user.email)
    refreshed = _refresh(staff_tokens['refresh'])
    assert refreshed.status_code == status.HTTP_200_OK
    payload = jwt.decode(refreshed.json()['access'], settings.SECRET_KEY, algorithms=['HS256'])
    assert payload['sv'] == 0
    assert 890 <= payload['exp'] - payload['iat'] <= 910


# --------------------------------------------------------------------------- MFA pre-authentication

def _enable_mfa(user):
    import pyotp
    client = APIClient()
    client.force_authenticate(user=user)
    secret = client.post('/api/v1/auth/mfa/enrol/', format='json').json()['secret']
    totp = pyotp.TOTP(secret)
    assert client.post('/api/v1/auth/mfa/verify/', {'code': totp.now()}, format='json').status_code == status.HTTP_200_OK
    return totp


def _mfa_challenge(user):
    data = APIClient().post('/api/v1/auth/login/', {'email': user.email, 'password': PASSWORD}, format='json').json()
    assert data['mfa_required'] is True
    return data['pre_auth_token']


def _mfa_verify(pre_auth_token, code):
    return APIClient().post('/api/v1/auth/mfa/verify/', {'pre_auth_token': pre_auth_token, 'code': code}, format='json')


@pytest.mark.django_db
def test_mfa_challenge_revoked_by_suspension_even_after_reactivation(staff_user):
    totp = _enable_mfa(staff_user)
    pre_auth = _mfa_challenge(staff_user)
    assert signing.loads(pre_auth, salt='driverxtra.mfa', max_age=300)['sv'] == 0

    User.objects.filter(pk=staff_user.pk).update(status=AccountStatusChoices.SUSPENDED)
    User.objects.filter(pk=staff_user.pk).update(status=AccountStatusChoices.ACTIVE)
    res = _mfa_verify(pre_auth, totp.now())
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert 'tokens' not in res.json()
    assert 'mfa session' in str(res.json()).lower()

    fresh = _mfa_verify(_mfa_challenge(staff_user), totp.now())
    assert fresh.status_code == status.HTTP_200_OK
    assert _sv_claim(fresh.json()['tokens']['access']) == 1
    assert _me(fresh.json()['tokens']['access']).status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_mfa_payload_without_sv_is_version_zero(staff_user):
    totp = _enable_mfa(staff_user)
    legacy = signing.dumps({'user_id': str(staff_user.id), 'action': 'mfa_login'}, salt='driverxtra.mfa')
    assert _mfa_verify(legacy, totp.now()).status_code == status.HTTP_200_OK

    User.objects.filter(pk=staff_user.pk).update(status=AccountStatusChoices.SUSPENDED)
    User.objects.filter(pk=staff_user.pk).update(status=AccountStatusChoices.ACTIVE)
    legacy_after = signing.dumps({'user_id': str(staff_user.id), 'action': 'mfa_login'}, salt='driverxtra.mfa')
    assert _mfa_verify(legacy_after, totp.now()).status_code == status.HTTP_400_BAD_REQUEST


# --------------------------------------------------------------------------- migration & trigger

@pytest.mark.django_db
def test_backfill_targets_only_currently_unusable_accounts():
    from django.apps import apps as django_apps
    migration = importlib.import_module('apps.identity.migrations.0008_user_session_version')
    active = User.objects.create_user(email='bf_active@driverxtra.com', password=PASSWORD)
    suspended = User.objects.create_user(email='bf_susp@driverxtra.com', password=PASSWORD,
                                         status=AccountStatusChoices.SUSPENDED)
    deactivated = User.objects.create_user(email='bf_deact@driverxtra.com', password=PASSWORD,
                                           status=AccountStatusChoices.DEACTIVATED)
    inactive = User.objects.create_user(email='bf_inactive@driverxtra.com', password=PASSWORD, is_active=False)
    pending = User.objects.create_user(email='bf_pending@driverxtra.com', password=PASSWORD,
                                       status=AccountStatusChoices.PENDING)
    # Rows inserted unusable: no UPDATE happened, so the trigger has not touched them.
    assert {_version(u) for u in (active, suspended, deactivated, inactive, pending)} == {0}

    migration.backfill_unusable_accounts(django_apps, None)
    assert _version(active) == 0
    assert _version(pending) == 0
    assert _version(suspended) == 1
    assert _version(deactivated) == 1
    assert _version(inactive) == 1


@pytest.mark.django_db
def test_session_version_trigger_is_installed():
    """Fails loudly if a later migration rebuilds the user table on SQLite and drops the trigger."""
    with connection.cursor() as cursor:
        if connection.vendor == 'sqlite':
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger' AND name = %s",
                ['trg_identity_user_session_version'],
            )
        elif connection.vendor == 'postgresql':
            cursor.execute(
                "SELECT tgname FROM pg_trigger WHERE tgname = %s AND NOT tgisinternal",
                ['trg_identity_user_session_version'],
            )
        else:
            pytest.skip(f'No session-version trigger for vendor {connection.vendor}')
        assert cursor.fetchone() is not None


@pytest.mark.django_db
def test_postgresql_trigger_function_installed():
    if connection.vendor != 'postgresql':
        pytest.skip('PostgreSQL trigger function check (run the suite against PostgreSQL).')
    with connection.cursor() as cursor:
        cursor.execute("SELECT proname FROM pg_proc WHERE proname = %s", ['identity_user_session_version_guard'])
        assert cursor.fetchone() is not None


# --------------------------------------------------------------------------- reversibility

def _user_columns():
    with connection.cursor() as cursor:
        return {col.name for col in connection.introspection.get_table_description(cursor, User._meta.db_table)}


def _trigger_present():
    with connection.cursor() as cursor:
        if connection.vendor == 'sqlite':
            cursor.execute("SELECT 1 FROM sqlite_master WHERE type = 'trigger' AND name = %s",
                           ['trg_identity_user_session_version'])
        else:
            cursor.execute("SELECT 1 FROM pg_trigger WHERE tgname = %s AND NOT tgisinternal",
                           ['trg_identity_user_session_version'])
        return cursor.fetchone() is not None


@pytest.mark.django_db(transaction=True)
def test_migration_0008_is_reversible():
    """Runs only against the automated test database (never the development database)."""
    if connection.vendor not in ('sqlite', 'postgresql'):
        pytest.skip('Trigger only implemented for SQLite and PostgreSQL.')
    from django.db.migrations.executor import MigrationExecutor

    assert 'session_version' in _user_columns() and _trigger_present()

    executor = MigrationExecutor(connection)
    executor.migrate([('identity', '0007_add_review_moderate_permission')])
    assert 'session_version' not in _user_columns()
    assert not _trigger_present()

    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate([('identity', '0008_user_session_version')])
    assert 'session_version' in _user_columns()
    assert _trigger_present()

    # Behaviour restored after re-applying.
    user = User.objects.create_user(email='rev_check@driverxtra.com', password=PASSWORD)
    User.objects.filter(pk=user.pk).update(status=AccountStatusChoices.SUSPENDED)
    assert _version(user) == 1
