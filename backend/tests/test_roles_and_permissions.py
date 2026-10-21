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
        pre_auth_token = login_data['pre_auth_token']

        # 4. Verify code and complete login
        verify_res = api_client.post('/api/v1/auth/mfa/verify/', {
            'pre_auth_token': pre_auth_token,
            'code': totp.now(),
        }, format='json')
        assert verify_res.status_code == status.HTTP_200_OK
        token_data = verify_res.json()
        assert 'tokens' in token_data

        # 5. Check 15-minute token lifetime for staff
        access_token = token_data['tokens']['access']
        payload = jwt.decode(access_token, settings.SECRET_KEY, algorithms=['HS256'])
        exp_diff = payload['exp'] - payload['iat']
        # 15 minutes = 900 seconds
        assert 890 <= exp_diff <= 910

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
