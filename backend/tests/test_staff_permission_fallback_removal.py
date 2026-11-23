"""Security issue 2: staff without a sub-role no longer inherit VERIFICATION_OFFICER permissions.

- Unassigned staff hold no operational permissions (has_permission / get_effective_permissions).
- Migration identity.0012 gives existing unassigned staff an explicit VERIFICATION_OFFICER
  profile, so their effective permissions are preserved; explicit assignments are untouched.
- StaffProfile.staff_role is PROTECT: a sub-role with members cannot be deleted.
"""
import importlib

import pytest
from django.apps import apps as django_apps
from django.db.migrations.loader import MigrationLoader
from django.db.models import ProtectedError
from rest_framework import status
from rest_framework.test import APIClient

from apps.identity.models import Permission, RoleChoices, StaffProfile, StaffRole, User

MIGRATION_0012 = 'apps.identity.migrations.0012_assign_unassigned_staff_verification_officer'

SEEDED_ROLE_PERMISSIONS = {
    'SUPPORT_AGENT': {'support.ticket.manage'},
    'VERIFICATION_OFFICER': {'seller.verify', 'listing.review', 'review.moderate'},
    'DISPUTE_MANAGER': {'dispute.manage', 'order.refund'},
    'FINANCE_OFFICER': {'finance.payout', 'order.refund'},
}


def _user(email, *, is_staff=False, roles=(), superuser=False):
    if superuser:
        return User.objects.create_superuser(email=email, password='SecurePassword123!')
    user = User.objects.create_user(email=email, password='SecurePassword123!', is_staff=is_staff,
                                    is_email_verified=True)
    for role in roles:
        user.add_role(role)
    return user


def _fresh(user):
    """Reloads the user so cached staff_profile relations are not reused."""
    return User.objects.get(pk=user.pk)


def _run_migration_0012():
    importlib.import_module(MIGRATION_0012).assign_unassigned_staff(django_apps, None)


def _vo_permissions():
    return set(StaffRole.objects.get(code='VERIFICATION_OFFICER')
               .role_permissions.values_list('permission__code', flat=True))


# --- Unassigned staff -----------------------------------------------------------------------------

@pytest.mark.django_db
@pytest.mark.parametrize('kind', ['is_staff_flag', 'staff_role', 'both', 'profile_without_role'])
def test_unassigned_staff_have_no_permissions(kind):
    user = _user(f'unassigned_{kind}@driverxtra.com',
                 is_staff=kind in ('is_staff_flag', 'both', 'profile_without_role'),
                 roles=[RoleChoices.STAFF] if kind in ('staff_role', 'both', 'profile_without_role') else [])
    if kind == 'profile_without_role':
        StaffProfile.objects.create(user=user, staff_role=None, department='Operations')
    user = _fresh(user)

    all_codes = list(Permission.objects.values_list('code', flat=True))
    assert all_codes  # seeded permissions exist
    for code in all_codes:
        assert user.has_permission(code) is False, code
    assert user.get_effective_permissions() == []


@pytest.mark.django_db
def test_unassigned_staff_are_refused_by_permission_gated_endpoints(seller_user):
    staff = _user('unassigned_endpoint@driverxtra.com', is_staff=True, roles=[RoleChoices.STAFF])
    client = APIClient()
    client.force_authenticate(user=staff)
    status_before = seller_user.status

    # 'seller.verify' (former fallback grant), 'review.moderate', 'order.refund', 'dispute.manage'.
    res = client.post(f'/api/v1/admin/sellers/{seller_user.id}/status/', {'action': 'SUSPEND', 'reason': 'test'},
                      format='json')
    assert res.status_code == status.HTTP_403_FORBIDDEN
    assert client.get('/api/v1/marketplace/admin/reviews/').status_code == status.HTTP_403_FORBIDDEN
    assert client.get('/api/v1/marketplace/admin/refunds/').status_code == status.HTTP_403_FORBIDDEN
    assert client.get('/api/v1/marketplace/admin/disputes/').status_code == status.HTTP_403_FORBIDDEN

    seller_user.refresh_from_db()
    assert seller_user.status == status_before


@pytest.mark.django_db
@pytest.mark.parametrize('code,expected', sorted(SEEDED_ROLE_PERMISSIONS.items()))
def test_explicitly_assigned_roles_keep_exact_permissions(code, expected):
    user = _user(f'explicit_{code.lower()}@driverxtra.com', is_staff=True, roles=[RoleChoices.STAFF])
    StaffProfile.objects.create(user=user, staff_role=StaffRole.objects.get(code=code))
    user = _fresh(user)
    assert set(user.get_effective_permissions()) == expected
    for perm in Permission.objects.values_list('code', flat=True):
        assert user.has_permission(perm) is (perm in expected), (code, perm)


@pytest.mark.django_db
def test_platform_admins_unaffected():
    admin = _user('fallback_admin@driverxtra.com', roles=[RoleChoices.ADMIN])
    root = _user('fallback_root@driverxtra.com', superuser=True)
    all_codes = set(Permission.objects.values_list('code', flat=True))
    for user in (admin, root):
        assert set(user.get_effective_permissions()) == all_codes
        assert user.has_permission('seller.verify') is True


# --- Migration 0012 ----------------------------------------------------------------------------

def test_migration_graph_order():
    loader = MigrationLoader(None, ignore_no_migrations=True)
    m12 = loader.disk_migrations[('identity', '0012_assign_unassigned_staff_verification_officer')]
    m13 = loader.disk_migrations[('identity', '0013_staffprofile_staff_role_protect')]
    m14 = loader.disk_migrations[('identity', '0014_add_advertising_permissions')]
    assert ('identity', '0011_user_session_version') in m12.dependencies
    assert ('identity', '0012_assign_unassigned_staff_verification_officer') in m13.dependencies
    assert ('identity', '0013_staffprofile_staff_role_protect') in m14.dependencies
    assert loader.graph.leaf_nodes('identity') == [('identity', '0014_add_advertising_permissions')]


@pytest.mark.django_db
def test_migration_assigns_explicit_verification_officer_and_preserves_permissions():
    vo = StaffRole.objects.get(code='VERIFICATION_OFFICER')
    support = StaffRole.objects.get(code='SUPPORT_AGENT')
    vo_perms = _vo_permissions()

    no_profile_flag = _user('m_flag@driverxtra.com', is_staff=True)
    no_profile_role = _user('m_role@driverxtra.com', roles=[RoleChoices.STAFF])
    null_role = _user('m_null@driverxtra.com', is_staff=True, roles=[RoleChoices.STAFF])
    StaffProfile.objects.create(user=null_role, staff_role=None, department='Fleet Ops', totp_enabled=True,
                                totp_secret='encrypted-secret-placeholder')
    explicit = _user('m_explicit@driverxtra.com', is_staff=True, roles=[RoleChoices.STAFF])
    StaffProfile.objects.create(user=explicit, staff_role=support, department='Support')
    admin = _user('m_admin@driverxtra.com', is_staff=True, roles=[RoleChoices.ADMIN, RoleChoices.STAFF])
    root = _user('m_root@driverxtra.com', superuser=True)
    buyer = _user('m_buyer@driverxtra.com', roles=[RoleChoices.BUYER])

    _run_migration_0012()

    for user in (no_profile_flag, no_profile_role, null_role):
        profile = StaffProfile.objects.get(user=user)
        assert profile.staff_role_id == vo.id
        # Exactly the permissions the removed fallback used to grant.
        assert set(_fresh(user).get_effective_permissions()) == vo_perms

    assert StaffProfile.objects.get(user=no_profile_flag).department == 'Operations'
    assert StaffProfile.objects.get(user=no_profile_flag).totp_enabled is False
    # An existing profile keeps its MFA enrollment, secret and department.
    kept = StaffProfile.objects.get(user=null_role)
    assert (kept.department, kept.totp_enabled, kept.totp_secret) == ('Fleet Ops', True, 'encrypted-secret-placeholder')
    # Explicit assignments are never changed.
    assert StaffProfile.objects.get(user=explicit).staff_role_id == support.id
    assert set(_fresh(explicit).get_effective_permissions()) == SEEDED_ROLE_PERMISSIONS['SUPPORT_AGENT']
    # Platform admins, superusers and non-staff users get no profile.
    for user in (admin, root, buyer):
        assert not StaffProfile.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_migration_is_idempotent():
    user = _user('m_idem@driverxtra.com', is_staff=True, roles=[RoleChoices.STAFF])
    _run_migration_0012()
    first = StaffProfile.objects.get(user=user)
    _run_migration_0012()
    assert StaffProfile.objects.filter(user=user).count() == 1
    assert StaffProfile.objects.get(user=user).staff_role_id == first.staff_role_id


@pytest.mark.django_db
def test_migration_assigns_nothing_when_verification_officer_role_is_absent():
    """If the role does not exist, the old fallback granted nothing either."""
    StaffRole.objects.filter(code='VERIFICATION_OFFICER').delete()  # no members yet, so allowed
    user = _user('m_norole@driverxtra.com', is_staff=True, roles=[RoleChoices.STAFF])
    _run_migration_0012()
    assert not StaffProfile.objects.filter(user=user).exists()
    assert _fresh(user).get_effective_permissions() == []


# --- PROTECT on StaffRole deletion -------------------------------------------------------------

def test_staff_role_foreign_key_is_protect():
    from django.db import models
    field = StaffProfile._meta.get_field('staff_role')
    assert field.remote_field.on_delete is models.PROTECT


@pytest.mark.django_db
def test_deleting_a_staff_role_with_members_is_refused_and_nothing_changes():
    role = StaffRole.objects.get(code='SUPPORT_AGENT')
    member = _user('protect_member@driverxtra.com', is_staff=True, roles=[RoleChoices.STAFF])
    StaffProfile.objects.create(user=member, staff_role=role)
    perms_before = set(role.role_permissions.values_list('permission__code', flat=True))

    with pytest.raises(ProtectedError):
        role.delete()

    assert StaffRole.objects.filter(pk=role.pk).exists()
    assert StaffProfile.objects.get(user=member).staff_role_id == role.pk
    assert set(_fresh(member).get_effective_permissions()) == perms_before == {'support.ticket.manage'}


@pytest.mark.django_db
def test_deleting_a_staff_role_without_members_is_allowed():
    role = StaffRole.objects.get(code='FINANCE_OFFICER')
    assert not StaffProfile.objects.filter(staff_role=role).exists()
    role.delete()
    assert not StaffRole.objects.filter(code='FINANCE_OFFICER').exists()
