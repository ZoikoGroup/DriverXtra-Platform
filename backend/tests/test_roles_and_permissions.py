import pytest
from rest_framework import status
from apps.identity.models import User, RoleChoices


@pytest.mark.django_db
class TestRolesAndPermissions:

    def test_prevent_public_users_self_granting_admin_privileges(self, api_client):
        payload = {
            'email': 'eviladmin@example.com',
            'password': 'SecurePassword123!',
            'first_name': 'Hacker',
            'last_name': 'Man',
            'roles': ['ADMIN'],
        }
        response = api_client.post('/api/v1/auth/register/', payload, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert 'prohibited' in str(data).lower() or 'staff or admin' in str(data).lower()
        assert not User.objects.filter(email='eviladmin@example.com').exists()

    def test_prevent_public_users_self_granting_staff_privileges(self, api_client):
        payload = {
            'email': 'evilstaff@example.com',
            'password': 'SecurePassword123!',
            'first_name': 'Sneaky',
            'last_name': 'Staff',
            'roles': ['STAFF'],
        }
        response = api_client.post('/api/v1/auth/register/', payload, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert 'prohibited' in str(data).lower()
        assert not User.objects.filter(email='evilstaff@example.com').exists()

    def test_user_multiple_roles_support(self, buyer_user):
        assert buyer_user.has_role(RoleChoices.BUYER)
        assert not buyer_user.has_role(RoleChoices.SELLER)

        # Assign second role
        buyer_user.add_role(RoleChoices.SELLER)
        assert buyer_user.has_role(RoleChoices.BUYER)
        assert buyer_user.has_role(RoleChoices.SELLER)
        assert len(buyer_user.roles) == 2
        assert RoleChoices.BUYER in buyer_user.roles
        assert RoleChoices.SELLER in buyer_user.roles

        # Remove a role
        buyer_user.remove_role(RoleChoices.BUYER)
        assert not buyer_user.has_role(RoleChoices.BUYER)
        assert buyer_user.has_role(RoleChoices.SELLER)

    def test_role_normalization_and_aliases(self, buyer_user):
        # Verify prototype role aliases map cleanly to canonical roles
        assert RoleChoices.normalize_role('CONSUMER') == RoleChoices.BUYER
        assert RoleChoices.normalize_role('INVENTORY_MANAGER') == RoleChoices.SELLER
        assert RoleChoices.normalize_role('DEALER') == RoleChoices.SELLER
        assert RoleChoices.normalize_role('WORKSHOP_MANAGER') == RoleChoices.WORKSHOP
        assert RoleChoices.normalize_role('MARKETPLACE_ADMIN') == RoleChoices.ADMIN
        assert RoleChoices.normalize_role('OPERATIONS') == RoleChoices.STAFF

    def test_admin_and_staff_flags(self, admin_user, staff_user, buyer_user):
        assert admin_user.is_platform_admin is True
        assert admin_user.is_platform_staff is True

        assert staff_user.is_platform_staff is True
        assert staff_user.is_platform_admin is False

        assert buyer_user.is_platform_admin is False
        assert buyer_user.is_platform_staff is False

    # =========================================================================
    # Phase 5: Permissions, Staff Roles, Active Role, MFA & Maker-Checker
    # =========================================================================

    def test_permission_seeding_and_staff_roles(self):
        from apps.identity.models import Permission, StaffRole
        expected_perms = [
            'seller.verify',
            'listing.review',
            'order.refund',
            'dispute.manage',
            'finance.payout',
            'staff.manage',
        ]
        for p in expected_perms:
            assert Permission.objects.filter(code=p).exists()

        verif_role = StaffRole.objects.get(code='VERIFICATION_OFFICER')
        verif_perm_codes = list(verif_role.role_permissions.values_list('permission__code', flat=True))
        assert 'seller.verify' in verif_perm_codes
        assert 'listing.review' in verif_perm_codes

        support_role = StaffRole.objects.get(code='SUPPORT_AGENT')
        support_perm_codes = list(support_role.role_permissions.values_list('permission__code', flat=True))
        assert 'dispute.manage' in support_perm_codes
        assert 'seller.verify' not in support_perm_codes

    def test_has_permission_drf_class(self, admin_user, staff_user, buyer_user):
        from apps.identity.models import StaffRole, StaffProfile
        # Admin has all permissions
        assert admin_user.has_permission('seller.verify') is True
        assert admin_user.has_permission('listing.review') is True
        assert admin_user.has_permission('nonexistent.perm') is True

        # Staff user setup as SUPPORT_AGENT
        support_role = StaffRole.objects.get(code='SUPPORT_AGENT')
        profile, _ = StaffProfile.objects.get_or_create(user=staff_user)
        profile.staff_role = support_role
        profile.save()

        assert staff_user.has_permission('dispute.manage') is True
        assert staff_user.has_permission('seller.verify') is False
        assert staff_user.has_permission('listing.review') is False

        # Switch to VERIFICATION_OFFICER
        verif_role = StaffRole.objects.get(code='VERIFICATION_OFFICER')
        profile.staff_role = verif_role
        profile.save()

        assert staff_user.has_permission('seller.verify') is True
        assert staff_user.has_permission('listing.review') is True
        assert staff_user.has_permission('finance.payout') is False

        # Buyer has no permissions
        assert buyer_user.has_permission('seller.verify') is False

    def test_admin_staff_invite_and_set_password(self, admin_auth_client, seller_auth_client, api_client):
        from django.core import mail
        from apps.identity.models import StaffInviteToken

        # 1. Non-admin cannot invite staff (403)
        invite_payload = {
            'email': 'newsupport@driverxtra.com',
            'first_name': 'Alice',
            'last_name': 'Support',
            'staff_role': 'SUPPORT_AGENT',
            'department': 'Operations',
        }
        res_denied = seller_auth_client.post('/api/v1/admin/staff/invite/', invite_payload, format='json')
        assert res_denied.status_code == status.HTTP_403_FORBIDDEN

        # 2. Admin invites staff
        res_ok = admin_auth_client.post('/api/v1/admin/staff/invite/', invite_payload, format='json')
        assert res_ok.status_code == status.HTTP_201_CREATED
        assert len(mail.outbox) > 0
        email = mail.outbox[-1]
        assert 'DriverXtra Staff Invitation' in email.subject
        assert 'token=' in email.body

        # Extract token from email
        import re
        match = re.search(r'token=([a-zA-Z0-9_\-]+)', email.body)
        assert match is not None
        raw_token = match.group(1)

        # 3. Staff user sets password via token
        set_pw_payload = {
            'token': raw_token,
            'new_password': 'SecureStaffPass123!',
        }
        set_res = api_client.post('/api/v1/auth/staff/set-password/', set_pw_payload, format='json')
        assert set_res.status_code == status.HTTP_200_OK

        # 4. Token cannot be reused (single-use)
        reused_res = api_client.post('/api/v1/auth/staff/set-password/', set_pw_payload, format='json')
        assert reused_res.status_code == status.HTTP_400_BAD_REQUEST

        # 5. User can now log in
        login_res = api_client.post('/api/v1/auth/login/', {
            'email': 'newsupport@driverxtra.com',
            'password': 'SecureStaffPass123!',
        }, format='json')
        assert login_res.status_code == status.HTTP_200_OK
        assert login_res.json()['active_role'] == 'STAFF'

    def test_jwt_active_role_and_role_switching(self, api_client, buyer_user):
        import jwt
        from django.conf import settings

        # User holds both BUYER and SELLER
        buyer_user.add_role(RoleChoices.SELLER)

        # Login: default active_role is SELLER (priority SELLER > BUYER)
        login_res = api_client.post('/api/v1/auth/login/', {
            'email': buyer_user.email,
            'password': 'SecurePassword123!',
        }, format='json')
        assert login_res.status_code == status.HTTP_200_OK
        data = login_res.json()
        assert data['active_role'] == RoleChoices.SELLER

        access_token = data['tokens']['access']
        payload = jwt.decode(access_token, settings.SECRET_KEY, algorithms=['HS256'])
        assert payload['active_role'] == RoleChoices.SELLER

        # Switch role to BUYER
        api_client.force_authenticate(user=buyer_user)
        switch_res = api_client.post('/api/v1/auth/switch-role/', {'role': 'BUYER'}, format='json')
        assert switch_res.status_code == status.HTTP_200_OK
        new_data = switch_res.json()
        assert new_data['active_role'] == RoleChoices.BUYER

        new_payload = jwt.decode(new_data['tokens']['access'], settings.SECRET_KEY, algorithms=['HS256'])
        assert new_payload['active_role'] == RoleChoices.BUYER

        # Attempt to switch to role user does NOT hold
        bad_switch = api_client.post('/api/v1/auth/switch-role/', {'role': 'ADMIN'}, format='json')
        assert bad_switch.status_code == status.HTTP_400_BAD_REQUEST

    def test_staff_totp_mfa_flow_and_15_minute_tokens(self, api_client, staff_user):
        import pyotp
        import jwt
        from django.conf import settings
        from datetime import datetime

        api_client.force_authenticate(user=staff_user)

        # 1. Enrol in MFA
        enrol_res = api_client.post('/api/v1/auth/mfa/enrol/', format='json')
        assert enrol_res.status_code == status.HTTP_200_OK
        secret = enrol_res.json()['secret']
        assert secret

        # 2. Confirm enrolment with valid code
        totp = pyotp.TOTP(secret)
        code = totp.now()
        confirm_res = api_client.post('/api/v1/auth/mfa/verify/', {'code': code}, format='json')
        assert confirm_res.status_code == status.HTTP_200_OK

        staff_user.refresh_from_db()
        assert staff_user.has_mfa_enabled is True

        # 3. Next login triggers MFA challenge
        api_client.force_authenticate(user=None)
        login_res = api_client.post('/api/v1/auth/login/', {
            'email': staff_user.email,
            'password': 'SecurePassword123!',
        }, format='json')
        assert login_res.status_code == status.HTTP_200_OK
        login_data = login_res.json()
        assert login_data['status'] == 'mfa_required'
        assert login_data['mfa_required'] is True
        assert 'tokens' not in login_data
        pre_auth_token = login_data['pre_auth_token']
        assert pre_auth_token

        # 4. Verify code and complete login
        verify_res = api_client.post('/api/v1/auth/mfa/verify/', {
            'pre_auth_token': pre_auth_token,
            'code': totp.now(),
        }, format='json')
        assert verify_res.status_code == status.HTTP_200_OK
        token_data = verify_res.json()
        assert 'tokens' in token_data
        assert token_data['tokens']['access']
        assert token_data['tokens']['refresh']
        assert token_data['user']['email'] == staff_user.email

        # 5. Check 15-minute token lifetime for staff
        access_token = token_data['tokens']['access']
        payload = jwt.decode(access_token, settings.SECRET_KEY, algorithms=['HS256'])
        exp_diff = payload['exp'] - payload['iat']
        # 15 minutes = 900 seconds
        assert 890 <= exp_diff <= 910

    def test_mfa_login_challenge_rejects_invalid_code_and_tampered_token(self, api_client, staff_user):
        import pyotp

        api_client.force_authenticate(user=staff_user)
        secret = api_client.post('/api/v1/auth/mfa/enrol/', format='json').json()['secret']
        totp = pyotp.TOTP(secret)
        assert api_client.post('/api/v1/auth/mfa/verify/', {'code': totp.now()}, format='json').status_code == status.HTTP_200_OK
        api_client.force_authenticate(user=None)

        login_data = api_client.post('/api/v1/auth/login/', {
            'email': staff_user.email,
            'password': 'SecurePassword123!',
        }, format='json').json()
        assert login_data['mfa_required'] is True
        pre_auth_token = login_data['pre_auth_token']

        wrong_code = '000000' if totp.now() != '000000' else '111111'
        bad_code_res = api_client.post('/api/v1/auth/mfa/verify/', {
            'pre_auth_token': pre_auth_token,
            'code': wrong_code,
        }, format='json')
        assert bad_code_res.status_code == status.HTTP_400_BAD_REQUEST
        assert 'tokens' not in bad_code_res.json()

        tampered_res = api_client.post('/api/v1/auth/mfa/verify/', {
            'pre_auth_token': pre_auth_token + 'tampered',
            'code': totp.now(),
        }, format='json')
        assert tampered_res.status_code == status.HTTP_400_BAD_REQUEST
        assert 'tokens' not in tampered_res.json()

    def test_approval_request_maker_checker(self, buyer_user, seller_user):
        from apps.identity.models import ApprovalRequest, ApprovalStatusChoices

        # Create approval request by buyer_user
        req = ApprovalRequest.objects.create(
            requester=buyer_user,
            action_type='REFUND',
            target_type='Order',
            target_id='ORD-12345',
            payload={'amount': '150.00'},
        )
        assert req.status == ApprovalStatusChoices.PENDING

        # Requester cannot approve their own request (maker-checker violation)
        with pytest.raises(ValueError, match="Maker-checker violation"):
            req.approve(approver=buyer_user, notes='Self approval attempt')

        # Distinct approver can approve
        req.approve(approver=seller_user, notes='Approved by supervisor')
        req.refresh_from_db()
        assert req.status == ApprovalStatusChoices.APPROVED
        assert req.approver == seller_user
        assert req.reviewed_at is not None


def _bearer_client(token):
    from rest_framework.test import APIClient
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return client


def _login(api_client, email):
    res = api_client.post('/api/v1/auth/login/', {'email': email, 'password': 'SecurePassword123!'}, format='json')
    assert res.status_code == status.HTTP_200_OK, res.content
    return res.json()['tokens']


@pytest.mark.django_db
class TestActiveRoleAndSessionConsistency:
    """F6, F7, F9 and the MFA status re-check from F3."""

    def test_users_me_reports_switched_active_role(self, api_client, buyer_user):
        buyer_user.add_role(RoleChoices.SELLER)
        tokens = _login(api_client, buyer_user.email)
        assert _bearer_client(tokens['access']).get('/api/v1/users/me/').json()['active_role'] == RoleChoices.SELLER

        switch_res = _bearer_client(tokens['access']).post('/api/v1/auth/switch-role/', {'role': 'BUYER'}, format='json')
        assert switch_res.status_code == status.HTTP_200_OK
        new_access = switch_res.json()['tokens']['access']
        assert _bearer_client(new_access).get('/api/v1/users/me/').json()['active_role'] == RoleChoices.BUYER

    def test_users_me_ignores_active_role_claim_for_revoked_role(self, api_client, buyer_user):
        buyer_user.add_role(RoleChoices.SELLER)
        access = _login(api_client, buyer_user.email)['access']
        buyer_user.remove_role(RoleChoices.SELLER)
        assert _bearer_client(access).get('/api/v1/users/me/').json()['active_role'] == RoleChoices.BUYER

    def test_switch_role_blacklists_only_the_supplied_old_refresh_token(self, api_client, buyer_user):
        buyer_user.add_role(RoleChoices.SELLER)
        tokens = _login(api_client, buyer_user.email)

        switch_res = _bearer_client(tokens['access']).post(
            '/api/v1/auth/switch-role/', {'role': 'BUYER', 'refresh': tokens['refresh']}, format='json')
        assert switch_res.status_code == status.HTTP_200_OK
        new_tokens = switch_res.json()['tokens']

        old_refresh = api_client.post('/api/v1/auth/token/refresh/', {'refresh': tokens['refresh']}, format='json')
        assert old_refresh.status_code == status.HTTP_401_UNAUTHORIZED
        # The newly issued pair stays valid.
        assert _bearer_client(new_tokens['access']).get('/api/v1/users/me/').status_code == status.HTTP_200_OK
        new_refresh = api_client.post('/api/v1/auth/token/refresh/', {'refresh': new_tokens['refresh']}, format='json')
        assert new_refresh.status_code == status.HTTP_200_OK

    def test_switch_role_without_or_with_foreign_refresh_token_is_backward_compatible(self, api_client, buyer_user, seller_user):
        buyer_user.add_role(RoleChoices.SELLER)
        tokens = _login(api_client, buyer_user.email)
        other_tokens = _login(api_client, seller_user.email)

        no_refresh = _bearer_client(tokens['access']).post('/api/v1/auth/switch-role/', {'role': 'BUYER'}, format='json')
        assert no_refresh.status_code == status.HTTP_200_OK
        refreshed = api_client.post('/api/v1/auth/token/refresh/', {'refresh': tokens['refresh']}, format='json')
        assert refreshed.status_code == status.HTTP_200_OK

        foreign = _bearer_client(tokens['access']).post(
            '/api/v1/auth/switch-role/', {'role': 'SELLER', 'refresh': other_tokens['refresh']}, format='json')
        assert foreign.status_code == status.HTTP_200_OK
        # Another user's refresh token is never blacklisted by this user's switch.
        other_refreshed = api_client.post('/api/v1/auth/token/refresh/', {'refresh': other_tokens['refresh']}, format='json')
        assert other_refreshed.status_code == status.HTTP_200_OK

        garbage = _bearer_client(tokens['access']).post(
            '/api/v1/auth/switch-role/', {'role': 'BUYER', 'refresh': 'not-a-token'}, format='json')
        assert garbage.status_code == status.HTTP_200_OK

    def test_staff_refresh_keeps_15_minute_access_lifetime(self, api_client, staff_user):
        import jwt
        from django.conf import settings
        tokens = _login(api_client, staff_user.email)
        refresh_res = api_client.post('/api/v1/auth/token/refresh/', {'refresh': tokens['refresh']}, format='json')
        assert refresh_res.status_code == status.HTTP_200_OK
        payload = jwt.decode(refresh_res.json()['access'], settings.SECRET_KEY, algorithms=['HS256'])
        assert 890 <= payload['exp'] - payload['iat'] <= 910
        assert payload['active_role'] == RoleChoices.STAFF

    def test_users_me_permissions_match_enforced_permissions(self, api_client, staff_user, buyer_user, admin_user):
        from apps.identity.models import Permission
        # STAFF without a StaffProfile falls back to VERIFICATION_OFFICER for enforcement and reporting.
        api_client.force_authenticate(user=staff_user)
        reported = set(api_client.get('/api/v1/users/me/').json()['permissions'])
        for code in Permission.objects.values_list('code', flat=True):
            assert (code in reported) == staff_user.has_permission(code), code
        assert {'listing.review', 'seller.verify'} <= reported
        assert 'order.refund' not in reported

        api_client.force_authenticate(user=buyer_user)
        assert api_client.get('/api/v1/users/me/').json()['permissions'] == []

        api_client.force_authenticate(user=admin_user)
        assert set(api_client.get('/api/v1/users/me/').json()['permissions']) == set(
            Permission.objects.values_list('code', flat=True))

    def test_mfa_verify_rejected_after_account_suspended(self, api_client, staff_user):
        import pyotp
        from apps.identity.models import AccountStatusChoices

        api_client.force_authenticate(user=staff_user)
        secret = api_client.post('/api/v1/auth/mfa/enrol/', format='json').json()['secret']
        totp = pyotp.TOTP(secret)
        assert api_client.post('/api/v1/auth/mfa/verify/', {'code': totp.now()}, format='json').status_code == status.HTTP_200_OK
        api_client.force_authenticate(user=None)

        login_res = api_client.post('/api/v1/auth/login/', {
            'email': staff_user.email, 'password': 'SecurePassword123!',
        }, format='json')
        pre_auth_token = login_res.json()['pre_auth_token']

        staff_user.refresh_from_db()
        staff_user.status = AccountStatusChoices.SUSPENDED
        staff_user.save(update_fields=['status', 'updated_at'])

        res = api_client.post('/api/v1/auth/mfa/verify/', {
            'pre_auth_token': pre_auth_token, 'code': totp.now(),
        }, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert 'tokens' not in res.json()
        assert 'suspended' in str(res.json()).lower()


@pytest.mark.django_db
class TestReviewModeratePermissionSeed:
    """Phase 2: migration 0007 adds 'review.moderate' to VERIFICATION_OFFICER only (decision U2)."""

    def test_review_moderate_permission_seeded_for_verification_officer_only(self):
        from apps.identity.models import Permission, StaffRole
        assert Permission.objects.filter(code='review.moderate').exists()
        holders = set(
            StaffRole.objects.filter(role_permissions__permission__code='review.moderate').values_list('code', flat=True)
        )
        assert holders == {'VERIFICATION_OFFICER'}

    def test_existing_staff_role_permissions_unchanged(self):
        from apps.identity.models import StaffRole
        expected = {
            'SUPPORT_AGENT': {'dispute.manage'},
            'VERIFICATION_OFFICER': {'seller.verify', 'listing.review', 'review.moderate'},
            'DISPUTE_MANAGER': {'dispute.manage', 'order.refund'},
            'FINANCE_OFFICER': {'finance.payout', 'order.refund'},
        }
        for code, perms in expected.items():
            role = StaffRole.objects.get(code=code)
            assert set(role.role_permissions.values_list('permission__code', flat=True)) == perms, code

    def test_review_moderate_effective_holders(self, staff_user, admin_user, buyer_user):
        from apps.identity.models import StaffRole, StaffProfile
        # STAFF without a sub-role falls back to VERIFICATION_OFFICER.
        assert staff_user.has_permission('review.moderate') is True
        assert admin_user.has_permission('review.moderate') is True
        assert buyer_user.has_permission('review.moderate') is False
        profile, _ = StaffProfile.objects.get_or_create(user=staff_user)
        for code in ('SUPPORT_AGENT', 'DISPUTE_MANAGER', 'FINANCE_OFFICER'):
            profile.staff_role = StaffRole.objects.get(code=code)
            profile.save()
            assert staff_user.has_permission('review.moderate') is False, code
