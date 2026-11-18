"""Authorization regression tests for admin account/workshop status endpoints (S1, S2, S3).

S1  POST /api/v1/admin/buyers/<id>/status/     platform administrators only; target must be an
                                                ordinary BUYER account (never staff/admin/superuser/self).
S2  POST /api/v1/admin/sellers/<id>/status/    'seller.verify'; target must be an ordinary SELLER account.
S3  POST /api/v1/admin/workshops/<id>/status/  'seller.verify'; VERIFY grants the WORKSHOP role, so
                                                unauthorized callers must not reach it.

Every refusal is checked for both the HTTP status and the unchanged database state.
"""
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.identity.models import AccountStatusChoices, RoleChoices, StaffProfile, StaffRole, User
from apps.organisations.models import Organisation, OrganisationTypeChoices
from apps.workshops.models import WorkshopProfile

PASSWORD = 'SecurePassword123!'


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _staff(email, staff_role_code=None):
    user = User.objects.create_user(email=email, password=PASSWORD, is_staff=True, is_email_verified=True)
    user.add_role(RoleChoices.STAFF)
    if staff_role_code:
        profile, _ = StaffProfile.objects.get_or_create(user=user)
        profile.staff_role = StaffRole.objects.get(code=staff_role_code)
        profile.save()
    return user


def _platform_admin(email='status_admin@driverxtra.com'):
    """Platform administrator via the ADMIN role (not a superuser)."""
    user = User.objects.create_user(email=email, password=PASSWORD, is_email_verified=True)
    user.add_role(RoleChoices.ADMIN)
    return user


def _account(email, *roles):
    user = User.objects.create_user(email=email, password=PASSWORD, is_email_verified=True)
    for role in roles:
        user.add_role(role)
    return user


def _post_status(client, kind, pk, action):
    return client.post(f'/api/v1/admin/{kind}/{pk}/status/', {'action': action, 'reason': 'test'}, format='json')


def _state(user):
    user.refresh_from_db()
    return user.status, user.is_active, user.session_version


def _suspended(email, *roles):
    user = _account(email, *roles)
    User.objects.filter(pk=user.pk).update(status=AccountStatusChoices.SUSPENDED, is_active=False)
    user.refresh_from_db()
    return user


# ============================================================================ S1: buyer status

@pytest.mark.django_db
@pytest.mark.parametrize('make_admin', ['admin_role', 'superuser'])
def test_s1_platform_admin_can_suspend_and_reactivate_buyer(buyer_user, make_admin):
    admin = _platform_admin() if make_admin == 'admin_role' else User.objects.create_superuser(
        email='status_root@driverxtra.com', password=PASSWORD)
    client = _client(admin)
    version_before = _state(buyer_user)[2]

    res = _post_status(client, 'buyers', buyer_user.id, 'SUSPEND')
    assert res.status_code == status.HTTP_200_OK, res.content
    st, active, version = _state(buyer_user)
    assert (st, active) == (AccountStatusChoices.SUSPENDED, False)
    assert version == version_before + 1  # session-version trigger revoked existing tokens

    res = _post_status(client, 'buyers', buyer_user.id, 'REACTIVATE')
    assert res.status_code == status.HTTP_200_OK, res.content
    st, active, version_after = _state(buyer_user)
    assert (st, active) == (AccountStatusChoices.ACTIVE, True)
    assert version_after == version  # reactivation never restores old tokens


@pytest.mark.django_db
@pytest.mark.parametrize('staff_role_code', [None, 'SUPPORT_AGENT', 'VERIFICATION_OFFICER',
                                             'DISPUTE_MANAGER', 'FINANCE_OFFICER'])
def test_s1_staff_cannot_suspend_or_reactivate_buyer(buyer_user, staff_role_code):
    client = _client(_staff(f's1_{staff_role_code or "plain"}@driverxtra.com', staff_role_code))
    before = _state(buyer_user)
    assert _post_status(client, 'buyers', buyer_user.id, 'SUSPEND').status_code == status.HTTP_403_FORBIDDEN
    assert _state(buyer_user) == before

    suspended = _suspended(f's1_susp_{staff_role_code or "plain"}@driverxtra.com', RoleChoices.BUYER)
    before = _state(suspended)
    assert _post_status(client, 'buyers', suspended.id, 'REACTIVATE').status_code == status.HTTP_403_FORBIDDEN
    assert _state(suspended) == before


@pytest.mark.django_db
def test_s1_buyer_and_seller_cannot_use_buyer_status(buyer_user, seller_user):
    victim = _account('s1_victim@driverxtra.com', RoleChoices.BUYER)
    before = _state(victim)
    for actor in (buyer_user, seller_user):
        assert _post_status(_client(actor), 'buyers', victim.id, 'SUSPEND').status_code == status.HTTP_403_FORBIDDEN
    assert _state(victim) == before


@pytest.mark.django_db
@pytest.mark.parametrize('target_kind', ['admin_role', 'superuser', 'staff', 'staff_with_buyer_role'])
def test_s1_cannot_target_privileged_accounts(target_kind):
    admin = _platform_admin()
    if target_kind == 'admin_role':
        target = _account('s1_t_admin@driverxtra.com', RoleChoices.ADMIN, RoleChoices.BUYER)
    elif target_kind == 'superuser':
        target = User.objects.create_superuser(email='s1_t_root@driverxtra.com', password=PASSWORD)
        target.add_role(RoleChoices.BUYER)
    elif target_kind == 'staff':
        target = _staff('s1_t_staff@driverxtra.com', 'SUPPORT_AGENT')
    else:
        target = _staff('s1_t_staffbuyer@driverxtra.com')
        target.add_role(RoleChoices.BUYER)
    before = _state(target)
    res = _post_status(_client(admin), 'buyers', target.id, 'SUSPEND')
    assert res.status_code == status.HTTP_403_FORBIDDEN, res.content
    assert _state(target) == before


@pytest.mark.django_db
def test_s1_cannot_target_self():
    admin = _platform_admin()
    admin.add_role(RoleChoices.BUYER)
    before = _state(admin)
    assert _post_status(_client(admin), 'buyers', admin.id, 'SUSPEND').status_code == status.HTTP_403_FORBIDDEN
    assert _state(admin) == before


@pytest.mark.django_db
def test_s1_cannot_target_user_without_buyer_role(seller_user, workshop_user):
    admin = _platform_admin()
    for target in (seller_user, workshop_user):  # fixtures hold SELLER / WORKSHOP only
        before = _state(target)
        res = _post_status(_client(admin), 'buyers', target.id, 'SUSPEND')
        assert res.status_code == status.HTTP_404_NOT_FOUND, res.content
        assert _state(target) == before


# ============================================================================ S2: seller status

@pytest.mark.django_db
@pytest.mark.parametrize('actor_kind', ['VERIFICATION_OFFICER', 'admin_role'])
def test_s2_seller_verifier_can_suspend_and_reactivate_seller(seller_user, actor_kind):
    actor = _staff('s2_verifier@driverxtra.com', 'VERIFICATION_OFFICER') if actor_kind != 'admin_role' else _platform_admin()
    client = _client(actor)
    version_before = _state(seller_user)[2]

    assert _post_status(client, 'sellers', seller_user.id, 'SUSPEND').status_code == status.HTTP_200_OK
    st, active, version = _state(seller_user)
    assert (st, active) == (AccountStatusChoices.SUSPENDED, False)
    assert version == version_before + 1

    assert _post_status(client, 'sellers', seller_user.id, 'REACTIVATE').status_code == status.HTTP_200_OK
    assert _state(seller_user) == (AccountStatusChoices.ACTIVE, True, version)


@pytest.mark.django_db
@pytest.mark.parametrize('staff_role_code', [None, 'SUPPORT_AGENT', 'DISPUTE_MANAGER', 'FINANCE_OFFICER'])
def test_s2_staff_without_seller_verify_cannot_change_seller_status(seller_user, staff_role_code):
    client = _client(_staff(f's2_{staff_role_code}@driverxtra.com', staff_role_code))
    before = _state(seller_user)
    assert _post_status(client, 'sellers', seller_user.id, 'SUSPEND').status_code == status.HTTP_403_FORBIDDEN
    assert _state(seller_user) == before

    suspended = _suspended(f's2_susp_{staff_role_code}@driverxtra.com', RoleChoices.SELLER)
    before = _state(suspended)
    assert _post_status(client, 'sellers', suspended.id, 'REACTIVATE').status_code == status.HTTP_403_FORBIDDEN
    assert _state(suspended) == before


@pytest.mark.django_db
@pytest.mark.parametrize('target_kind', ['admin_role', 'superuser', 'staff', 'staff_with_seller_role'])
def test_s2_cannot_target_privileged_accounts(target_kind):
    verifier = _staff('s2_v@driverxtra.com', 'VERIFICATION_OFFICER')
    if target_kind == 'admin_role':
        target = _account('s2_t_admin@driverxtra.com', RoleChoices.ADMIN, RoleChoices.SELLER)
    elif target_kind == 'superuser':
        target = User.objects.create_superuser(email='s2_t_root@driverxtra.com', password=PASSWORD)
        target.add_role(RoleChoices.SELLER)
    elif target_kind == 'staff':
        target = _staff('s2_t_staff@driverxtra.com', 'FINANCE_OFFICER')
    else:
        target = _staff('s2_t_staffseller@driverxtra.com')
        target.add_role(RoleChoices.SELLER)
    before = _state(target)
    res = _post_status(_client(verifier), 'sellers', target.id, 'SUSPEND')
    assert res.status_code == status.HTTP_403_FORBIDDEN, res.content
    assert _state(target) == before


@pytest.mark.django_db
def test_s2_cannot_target_self():
    verifier = _staff('s2_self@driverxtra.com', 'VERIFICATION_OFFICER')
    before = _state(verifier)
    assert _post_status(_client(verifier), 'sellers', verifier.id, 'SUSPEND').status_code == status.HTTP_403_FORBIDDEN
    assert _state(verifier) == before


@pytest.mark.django_db
def test_s2_cannot_target_user_without_seller_role(buyer_user, workshop_user):
    verifier = _staff('s2_role@driverxtra.com', 'VERIFICATION_OFFICER')
    for target in (buyer_user, workshop_user):
        before = _state(target)
        res = _post_status(_client(verifier), 'sellers', target.id, 'SUSPEND')
        assert res.status_code == status.HTTP_404_NOT_FOUND, res.content
        assert _state(target) == before


# ============================================================================ S3: workshop verification

@pytest.fixture
def unverified_workshop(db):
    owner = _account('s3_owner@driverxtra.com', RoleChoices.BUYER)  # no WORKSHOP role yet
    org = Organisation.objects.create(name='S3 Garage', slug='s3-garage', type=OrganisationTypeChoices.WORKSHOP,
                                      created_by=owner)
    wp = WorkshopProfile.objects.create(organisation=org, business_name='S3 Garage Ltd', slug='s3-garage-ltd',
                                        contact_email='s3@driverxtra.com', city='Leeds', is_verified=False)
    return wp, owner


def _workshop_state(wp, owner):
    wp.refresh_from_db()
    return wp.is_verified, wp.is_accepting_bookings, owner.has_role(RoleChoices.WORKSHOP)


@pytest.mark.django_db
@pytest.mark.parametrize('actor_kind', ['VERIFICATION_OFFICER', 'admin_role'])
def test_s3_seller_verify_holder_can_verify_workshop_and_grant_role(unverified_workshop, actor_kind):
    wp, owner = unverified_workshop
    actor = _staff('s3_verifier@driverxtra.com', 'VERIFICATION_OFFICER') if actor_kind != 'admin_role' else _platform_admin()
    res = _post_status(_client(actor), 'workshops', wp.id, 'VERIFY')
    assert res.status_code == status.HTTP_200_OK, res.content
    assert _workshop_state(wp, owner)[0] is True
    assert owner.has_role(RoleChoices.WORKSHOP) is True  # existing role-assignment workflow preserved


@pytest.mark.django_db
@pytest.mark.parametrize('staff_role_code', [None, 'SUPPORT_AGENT', 'DISPUTE_MANAGER', 'FINANCE_OFFICER'])
@pytest.mark.parametrize('action', ['VERIFY', 'UNVERIFY', 'SUSPEND', 'REACTIVATE'])
def test_s3_staff_without_seller_verify_cannot_change_workshop(unverified_workshop, staff_role_code, action):
    wp, owner = unverified_workshop
    actor = _staff(f's3_{staff_role_code or "plain"}@driverxtra.com', staff_role_code)
    if staff_role_code is None:
        # Staff without an assigned sub-role hold no permissions (no implicit fallback).
        assert actor.has_permission('seller.verify') is False
    before = _workshop_state(wp, owner)
    res = _post_status(_client(actor), 'workshops', wp.id, action)
    assert res.status_code == status.HTTP_403_FORBIDDEN, res.content
    assert _workshop_state(wp, owner) == before
    assert owner.has_role(RoleChoices.WORKSHOP) is False  # no role granted by an unauthorized request


@pytest.mark.django_db
def test_s3_buyer_and_seller_cannot_verify_workshop(unverified_workshop, buyer_user, seller_user):
    wp, owner = unverified_workshop
    for actor in (buyer_user, seller_user, owner):
        assert _post_status(_client(actor), 'workshops', wp.id, 'VERIFY').status_code == status.HTTP_403_FORBIDDEN
    assert _workshop_state(wp, owner) == (False, True, False)
