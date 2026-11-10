import pytest
from datetime import timedelta
import pyotp
import jwt
from unittest.mock import patch
from decimal import Decimal
from django.conf import settings
from django.test import override_settings
from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.test import APIClient

from apps.identity.models import (
    User,
    RoleChoices,
    StaffRole,
    StaffProfile,
    StaffInviteToken,
    AccountStatusChoices,
)
from apps.marketplace.models import (
    Order,
    OrderItem,
    Refund,
    RefundStatusChoices,
    Dispute,
    DisputeStatusChoices,
    DisputeCategoryChoices,
    PaymentStatusChoices,
)
from apps.marketplace.returns.service import RefundService, DisputeService


@pytest.fixture
def make_staff():
    """Helper factory to create a staff member with a specific StaffRole."""
    def _create(email, role_code, first_name='Staff', last_name='Member'):
        user = User.objects.create_user(
            email=email,
            password='SecureStaffPassword123!',
            first_name=first_name,
            last_name=last_name,
            is_staff=True,
            is_email_verified=True,
        )
        user.add_role(RoleChoices.STAFF)
        role = StaffRole.objects.get(code=role_code)
        profile, _ = StaffProfile.objects.get_or_create(user=user)
        profile.staff_role = role
        profile.totp_enabled = True
        profile.set_totp_secret(pyotp.random_base32())
        profile.save()
        return user
    return _create


@pytest.fixture
def verification_officer(make_staff):
    return make_staff('verif.officer@driverxtra.com', 'VERIFICATION_OFFICER', 'Verif', 'Officer')


@pytest.fixture
def dispute_manager(make_staff):
    return make_staff('dispute.mgr@driverxtra.com', 'DISPUTE_MANAGER', 'Dispute', 'Manager')


@pytest.fixture
def finance_officer(make_staff):
    return make_staff('finance.officer@driverxtra.com', 'FINANCE_OFFICER', 'Finance', 'Officer')


@pytest.fixture
def support_agent(make_staff):
    return make_staff('support.agent@driverxtra.com', 'SUPPORT_AGENT', 'Support', 'Agent')


@pytest.fixture
def sample_order(db, buyer_user, seller_user):
    import uuid
    order = Order.objects.create(
        buyer=buyer_user,
        order_number=f"ORD-TEST-{uuid.uuid4().hex[:6].upper()}",
        total_amount=Decimal('100.00'),
        subtotal_taxable_amount=Decimal('80.00'),
        total_tax_amount=Decimal('20.00'),
        currency='GBP',
        shipping_country='GB',
        payment_status=PaymentStatusChoices.PAID,
        payment_reference='pi_test_remediation_123',
    )
    OrderItem.objects.create(
        order=order,
        title='Brake Disc Set',
        unit_price=Decimal('80.00'),
        quantity=1,
        taxable_amount=Decimal('80.00'),
        tax_amount=Decimal('20.00'),
        total_amount=Decimal('100.00'),
    )
    return order


@pytest.fixture
def pending_refund(db, sample_order, admin_user):
    refund = Refund.objects.create(
        order=sample_order,
        amount=Decimal('50.00'),
        currency='GBP',
        status=RefundStatusChoices.PENDING,
        created_by=admin_user,
    )
    return refund


@pytest.fixture
def sample_dispute(db, sample_order, buyer_user, seller_user):
    import uuid
    return Dispute.objects.create(
        dispute_number=f"DISP-{uuid.uuid4().hex[:8].upper()}",
        order=sample_order,
        buyer=buyer_user,
        seller=seller_user,
        category=DisputeCategoryChoices.DAMAGED_OR_DEFECTIVE,
        status=DisputeStatusChoices.OPEN,
        description="Damaged brake disc received",
    )


# =============================================================================
# Task A & D Tests: Staff Permission Bypass Remediation
# =============================================================================

@pytest.mark.django_db
class TestStaffPermissionBypassRemediation:

    def test_verification_officer_cannot_approve_or_reject_refunds(self, verification_officer, pending_refund):
        client = APIClient()
        client.force_authenticate(user=verification_officer)

        # 1. API endpoint returns 403 Forbidden
        approve_res = client.post(f'/api/v1/marketplace/admin/refunds/{pending_refund.id}/approve/', {'notes': 'Test'})
        assert approve_res.status_code == status.HTTP_403_FORBIDDEN

        reject_res = client.post(f'/api/v1/marketplace/admin/refunds/{pending_refund.id}/reject/', {'reason': 'Invalid'})
        assert reject_res.status_code == status.HTTP_403_FORBIDDEN

        dispatch_res = client.post(f'/api/v1/marketplace/admin/refunds/{pending_refund.id}/dispatch/')
        assert dispatch_res.status_code == status.HTTP_403_FORBIDDEN

        # 2. Service layer rejects with ValidationError
        with pytest.raises(DjangoValidationError, match="Permission denied"):
            RefundService.approve_refund(pending_refund, actor=verification_officer)

        with pytest.raises(DjangoValidationError, match="Permission denied"):
            RefundService.reject_refund(pending_refund, actor=verification_officer, reason="No access")

        with pytest.raises(DjangoValidationError, match="Permission denied"):
            RefundService.dispatch_gateway_refund(pending_refund, actor=verification_officer)

    def test_support_agent_cannot_approve_refunds_or_modify_disputes(self, support_agent, pending_refund, sample_dispute):
        client = APIClient()
        client.force_authenticate(user=support_agent)

        # Refund endpoints return 403
        approve_res = client.post(f'/api/v1/marketplace/admin/refunds/{pending_refund.id}/approve/')
        assert approve_res.status_code == status.HTTP_403_FORBIDDEN

        reject_res = client.post(f'/api/v1/marketplace/admin/refunds/{pending_refund.id}/reject/', {'reason': 'Invalid'})
        assert reject_res.status_code == status.HTTP_403_FORBIDDEN

        dispatch_res = client.post(f'/api/v1/marketplace/admin/refunds/{pending_refund.id}/dispatch/')
        assert dispatch_res.status_code == status.HTTP_403_FORBIDDEN

        # Dispute status update endpoint returns 403 (dispute.manage removed in migration 0007)
        dispute_res = client.post(
            f'/api/v1/marketplace/admin/disputes/{sample_dispute.id}/status/',
            {'status': 'RESOLVED', 'resolution': 'REFUND_ISSUED', 'resolution_notes': 'Agent decision'},
        )
        assert dispute_res.status_code == status.HTTP_403_FORBIDDEN

        # Service layer checks
        with pytest.raises(DjangoValidationError, match="Permission denied"):
            RefundService.approve_refund(pending_refund, actor=support_agent)

        with pytest.raises(DjangoValidationError, match="Permission denied"):
            RefundService.dispatch_gateway_refund(pending_refund, actor=support_agent)

        with pytest.raises(DjangoValidationError, match="Permission denied"):
            DisputeService.update_dispute_status(sample_dispute, actor=support_agent, new_status='RESOLVED')

    def test_dispute_manager_can_update_dispute_and_approve_refund(self, dispute_manager, sample_dispute, pending_refund):
        client = APIClient()
        client.force_authenticate(user=dispute_manager)

        # 1. Dispute Manager has 'dispute.manage'
        res_dispute = client.post(
            f'/api/v1/marketplace/admin/disputes/{sample_dispute.id}/status/',
            {'status': 'UNDER_REVIEW', 'resolution_notes': 'Reviewing evidence'},
        )
        assert res_dispute.status_code == status.HTTP_200_OK
        sample_dispute.refresh_from_db()
        assert sample_dispute.status == DisputeStatusChoices.UNDER_REVIEW

        # 2. Dispute Manager has 'order.refund': can approve refund
        res_refund = client.post(
            f'/api/v1/marketplace/admin/refunds/{pending_refund.id}/approve/',
            {'notes': 'Legitimate return claim'},
        )
        assert res_refund.status_code == status.HTTP_200_OK
        pending_refund.refresh_from_db()
        assert pending_refund.status == RefundStatusChoices.PROCESSING

        # 3. Dispute Manager lacks 'finance.payout': blocked from gateway dispatch
        res_dispatch = client.post(f'/api/v1/marketplace/admin/refunds/{pending_refund.id}/dispatch/')
        assert res_dispatch.status_code == status.HTTP_403_FORBIDDEN

        with pytest.raises(DjangoValidationError, match="finance.payout"):
            RefundService.dispatch_gateway_refund(pending_refund, actor=dispute_manager)

    def test_finance_officer_can_approve_refund_and_is_blocked_from_disputes(self, finance_officer, pending_refund, sample_dispute):
        client = APIClient()
        client.force_authenticate(user=finance_officer)

        # Finance officer has 'order.refund' / 'finance.payout'
        res_refund = client.post(
            f'/api/v1/marketplace/admin/refunds/{pending_refund.id}/approve/',
            {'notes': 'Financial authorization granted'},
        )
        assert res_refund.status_code == status.HTTP_200_OK

        # Finance officer has 'finance.payout' and can dispatch gateway refunds
        with patch('apps.marketplace.returns.service.RefundService.dispatch_gateway_refund', return_value=pending_refund):
            res_dispatch = client.post(f'/api/v1/marketplace/admin/refunds/{pending_refund.id}/dispatch/')
            assert res_dispatch.status_code == status.HTTP_200_OK

        # Finance officer is blocked from dispute adjudication (lacks 'dispute.manage')
        res_dispute = client.post(
            f'/api/v1/marketplace/admin/disputes/{sample_dispute.id}/status/',
            {'status': 'RESOLVED'},
        )
        assert res_dispute.status_code == status.HTTP_403_FORBIDDEN

    def test_buyer_blocked_from_staff_operations(self, buyer_user, pending_refund, sample_dispute):
        client = APIClient()
        client.force_authenticate(user=buyer_user)

        res_refund = client.post(f'/api/v1/marketplace/admin/refunds/{pending_refund.id}/approve/')
        assert res_refund.status_code == status.HTTP_403_FORBIDDEN

        res_dispatch = client.post(f'/api/v1/marketplace/admin/refunds/{pending_refund.id}/dispatch/')
        assert res_dispatch.status_code == status.HTTP_403_FORBIDDEN

        res_dispute = client.post(
            f'/api/v1/marketplace/admin/disputes/{sample_dispute.id}/status/',
            {'status': 'RESOLVED'},
        )
        assert res_dispute.status_code == status.HTTP_403_FORBIDDEN

    def test_platform_admin_has_full_administrative_access(self, admin_user, pending_refund, sample_dispute):
        client = APIClient()
        client.force_authenticate(user=admin_user)

        res_dispute = client.post(
            f'/api/v1/marketplace/admin/disputes/{sample_dispute.id}/status/',
            {'status': 'UNDER_REVIEW'},
        )
        assert res_dispute.status_code == status.HTTP_200_OK

        with patch('apps.marketplace.returns.service.RefundService.dispatch_gateway_refund', return_value=pending_refund):
            res_refund = client.post(
                f'/api/v1/marketplace/admin/refunds/{pending_refund.id}/approve/',
                {'notes': 'Admin override'},
            )
            assert res_refund.status_code == status.HTTP_200_OK

            res_dispatch = client.post(f'/api/v1/marketplace/admin/refunds/{pending_refund.id}/dispatch/')
            assert res_dispatch.status_code == status.HTTP_200_OK


# =============================================================================
# Task B Tests: Mandatory Staff MFA
# =============================================================================

@pytest.mark.django_db
class TestMandatoryStaffMFA:

    @pytest.fixture(autouse=True)
    def enable_mfa(self, settings):
        settings.MFA_MANDATORY_ENFORCED = True

    def test_new_staff_without_mfa_receives_enrollment_required_challenge(self, api_client):
        # Create newly activated staff member without MFA
        staff = User.objects.create_user(
            email='newstaff@driverxtra.com',
            password='SecureStaffPassword123!',
            first_name='Alice',
            last_name='Newbie',
            is_staff=True,
            is_email_verified=True,
            status=AccountStatusChoices.ACTIVE,
        )
        staff.add_role(RoleChoices.STAFF)
        role = StaffRole.objects.get(code='VERIFICATION_OFFICER')
        StaffProfile.objects.create(user=staff, staff_role=role, totp_enabled=False)

        # 1. Login attempt
        res = api_client.post('/api/v1/auth/login/', {
            'email': 'newstaff@driverxtra.com',
            'password': 'SecureStaffPassword123!',
        }, format='json')

        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data['status'] == 'mfa_enrollment_required'
        assert data.get('mfa_required') is True
        assert data.get('mfa_enrollment_required') is True
        assert 'pre_auth_token' in data
        assert 'tokens' not in data  # Full JWT tokens NOT issued!

        pre_auth_token = data['pre_auth_token']

        # 2. Pre-auth token CANNOT be used to access protected business APIs
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {pre_auth_token}')
        protected_res = api_client.get('/api/v1/users/me/')
        assert protected_res.status_code == status.HTTP_401_UNAUTHORIZED

        # 3. Request TOTP enrollment setup with pre_auth_token
        api_client.credentials()  # clear auth header
        enrol_res = api_client.post('/api/v1/auth/mfa/enrol/', {
            'pre_auth_token': pre_auth_token,
        }, format='json')
        assert enrol_res.status_code == status.HTTP_200_OK
        enrol_data = enrol_res.json()
        assert 'secret' in enrol_data
        assert 'qr_code_uri' in enrol_data
        secret = enrol_data['secret']

        # 4. Verify invalid OTP returns 400
        verify_fail = api_client.post('/api/v1/auth/mfa/verify/', {
            'pre_auth_token': pre_auth_token,
            'code': '000000',
        }, format='json')
        assert verify_fail.status_code == status.HTTP_400_BAD_REQUEST

        # 5. Verify valid OTP activates MFA and issues full tokens
        totp = pyotp.TOTP(secret)
        verify_ok = api_client.post('/api/v1/auth/mfa/verify/', {
            'pre_auth_token': pre_auth_token,
            'code': totp.now(),
        }, format='json')
        assert verify_ok.status_code == status.HTTP_200_OK
        token_data = verify_ok.json()
        assert 'tokens' in token_data
        assert 'access' in token_data['tokens']
        assert 'refresh' in token_data['tokens']

        # 6. Verify profile now has totp_enabled = True
        staff.refresh_from_db()
        assert staff.has_mfa_enabled is True

        # 7. Next login now requires standard MFA challenge (action=mfa_login)
        res_next = api_client.post('/api/v1/auth/login/', {
            'email': 'newstaff@driverxtra.com',
            'password': 'SecureStaffPassword123!',
        }, format='json')
        assert res_next.status_code == status.HTTP_200_OK
        next_data = res_next.json()
        assert next_data['status'] == 'mfa_required'
        assert next_data.get('mfa_required') is True
        assert next_data.get('mfa_enrollment_required') is False

    def test_admin_account_mfa_enrollment_and_subsequent_login_flow(self, api_client):
        """Validates that an ADMIN account without MFA receives MFA_ENROLLMENT_REQUIRED,

        can enrol TOTP via pre_auth_token, verify code to obtain tokens, and subsequent
        logins trigger MFA_REQUIRED challenge.
        """
        admin = User.objects.create_superuser(
            email='admin.test@driverxtra.local',
            password='SuperAdminSecurePassword123!',
            first_name='Admin',
            last_name='User',
        )
        assert admin.has_mfa_enabled is False

        # 1. First login attempt: MFA enrollment required
        res_login = api_client.post('/api/v1/auth/login/', {
            'email': 'admin.test@driverxtra.local',
            'password': 'SuperAdminSecurePassword123!',
        }, format='json')

        assert res_login.status_code == status.HTTP_200_OK
        data = res_login.json()
        assert data['status'] == 'mfa_enrollment_required'
        assert data.get('code') == 'MFA_ENROLLMENT_REQUIRED'
        assert data.get('mfa_required') is True
        assert data.get('mfa_enrollment_required') is True
        assert data.get('active_role') == 'ADMIN'
        pre_auth_token = data['pre_auth_token']

        # 2. Call enrollment endpoint
        res_enrol = api_client.post('/api/v1/auth/mfa/enrol/', {
            'pre_auth_token': pre_auth_token,
        }, format='json')
        assert res_enrol.status_code == status.HTTP_200_OK
        enrol_data = res_enrol.json()
        assert 'secret' in enrol_data
        assert 'qr_code_uri' in enrol_data
        secret = enrol_data['secret']

        # 3. Verify TOTP code
        totp = pyotp.TOTP(secret)
        res_verify = api_client.post('/api/v1/auth/mfa/verify/', {
            'pre_auth_token': pre_auth_token,
            'code': totp.now(),
        }, format='json')
        assert res_verify.status_code == status.HTTP_200_OK
        verify_data = res_verify.json()
        assert 'tokens' in verify_data
        assert 'access' in verify_data['tokens']
        assert 'refresh' in verify_data['tokens']
        assert verify_data.get('active_role') == 'ADMIN'

        # 4. Verify admin account now has MFA enabled
        admin.refresh_from_db()
        assert admin.has_mfa_enabled is True

        # 5. Subsequent login: requires standard MFA challenge
        res_subsequent = api_client.post('/api/v1/auth/login/', {
            'email': 'admin.test@driverxtra.local',
            'password': 'SuperAdminSecurePassword123!',
        }, format='json')
        assert res_subsequent.status_code == status.HTTP_200_OK
        subsequent_data = res_subsequent.json()
        assert subsequent_data['status'] == 'mfa_required'
        assert subsequent_data.get('code') == 'MFA_REQUIRED'
        assert subsequent_data.get('mfa_required') is True
        assert subsequent_data.get('mfa_enrollment_required') is False
        assert subsequent_data.get('active_role') == 'ADMIN'
        subsequent_pre_auth = subsequent_data['pre_auth_token']

        # 6. Complete standard MFA verification
        res_verify_subsequent = api_client.post('/api/v1/auth/mfa/verify/', {
            'pre_auth_token': subsequent_pre_auth,
            'code': totp.now(),
        }, format='json')
        assert res_verify_subsequent.status_code == status.HTTP_200_OK
        assert 'tokens' in res_verify_subsequent.json()

        # 7. Direct login with TOTP code provided in initial payload
        res_direct = api_client.post('/api/v1/auth/login/', {
            'email': 'admin.test@driverxtra.local',
            'password': 'SuperAdminSecurePassword123!',
            'code': totp.now(),
        }, format='json')
        assert res_direct.status_code == status.HTTP_200_OK
        assert 'tokens' in res_direct.json()

    def test_buyer_login_unaffected_by_mfa(self, api_client, buyer_user):
        res = api_client.post('/api/v1/auth/login/', {
            'email': buyer_user.email,
            'password': 'SecurePassword123!',
        }, format='json')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data['status'] == 'success'
        assert 'tokens' in data
        assert 'access' in data['tokens']
        assert 'refresh' in data['tokens']

    def test_pre_auth_token_single_use_replay_prevention(self, api_client, verification_officer):
        totp = pyotp.TOTP(verification_officer.staff_profile.get_totp_secret())
        login_res = api_client.post('/api/v1/auth/login/', {
            'email': verification_officer.email,
            'password': 'SecureStaffPassword123!',
        }, format='json')
        pre_auth_token = login_res.json()['pre_auth_token']

        # First verification succeeds
        verify_1 = api_client.post('/api/v1/auth/mfa/verify/', {
            'pre_auth_token': pre_auth_token,
            'code': totp.now(),
        }, format='json')
        assert verify_1.status_code == status.HTTP_200_OK

        # Second verification with exact same pre_auth_token is rejected (single-use)
        verify_2 = api_client.post('/api/v1/auth/mfa/verify/', {
            'pre_auth_token': pre_auth_token,
            'code': totp.now(),
        }, format='json')
        assert verify_2.status_code == status.HTTP_400_BAD_REQUEST
        assert 'already been used' in verify_2.json()['message'].lower()

    def test_pre_auth_token_expired_fails(self, api_client, verification_officer):
        totp = pyotp.TOTP(verification_officer.staff_profile.get_totp_secret())
        # Craft a signed token that is expired (over 300s TTL)
        from django.core import signing
        import time
        token = signing.dumps(
            {'user_id': str(verification_officer.id), 'action': 'mfa_login'},
            salt='driverxtra.mfa',
        )
        current_t = time.time()
        # Advance time by 400 seconds so the 300s TTL has expired
        with patch('time.time', return_value=current_t + 400):
            verify_res = api_client.post('/api/v1/auth/mfa/verify/', {
                'pre_auth_token': token,
                'code': totp.now(),
            }, format='json')
        assert verify_res.status_code == status.HTTP_400_BAD_REQUEST
        assert 'expired' in verify_res.json()['message'].lower()

    def test_pre_auth_token_cannot_access_protected_apis(self, api_client, verification_officer):
        login_res = api_client.post('/api/v1/auth/login/', {
            'email': verification_officer.email,
            'password': 'SecureStaffPassword123!',
        }, format='json')
        pre_auth_token = login_res.json()['pre_auth_token']

        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {pre_auth_token}')
        res = api_client.get('/api/v1/users/me/')
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

    def test_enrolled_staff_cannot_re_enrol_via_pre_auth(self, api_client, verification_officer):
        from django.core import signing
        pre_auth_token = signing.dumps(
            {'user_id': str(verification_officer.id), 'action': 'mfa_enrollment'},
            salt='driverxtra.mfa',
        )
        res = api_client.post('/api/v1/auth/mfa/enrol/', {
            'pre_auth_token': pre_auth_token,
        }, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert 'already enrolled' in res.json()['message'].lower()


# =============================================================================
# Task B.2 Tests: MFA Disabled Login Flow (Email/Password Direct Authentication)
# =============================================================================

@pytest.mark.django_db
class TestMfaDisabledLoginFlow:
    """Verifies that when MFA_MANDATORY_ENFORCED is False (default), users across
    all roles (ADMIN, STAFF, BUYER, SELLER, WORKSHOP) authenticate directly via
    email and password, receiving SimpleJWT access and refresh tokens without any
    MFA enrollment or verification challenge.
    """

    def test_admin_login_without_mfa_issues_tokens_directly(self, api_client, admin_user):
        res = api_client.post('/api/v1/auth/login/', {
            'email': admin_user.email,
            'password': 'SuperAdminPassword123!',
        }, format='json')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data.get('status') == 'success'
        assert data.get('mfa_required') is False or 'mfa_required' not in data
        assert 'pre_auth_token' not in data
        assert 'tokens' in data
        assert 'access' in data['tokens']
        assert 'refresh' in data['tokens']
        assert data.get('active_role') == 'ADMIN'

        # Admin access token has 15-minute lifetime
        payload = jwt.decode(data['tokens']['access'], settings.SECRET_KEY, algorithms=['HS256'])
        exp_diff = payload['exp'] - payload['iat']
        assert 890 <= exp_diff <= 910
        assert payload.get('active_role') == 'ADMIN'

    def test_staff_login_without_mfa_issues_tokens_directly(self, api_client, verification_officer):
        res = api_client.post('/api/v1/auth/login/', {
            'email': verification_officer.email,
            'password': 'SecureStaffPassword123!',
        }, format='json')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data.get('status') == 'success'
        assert 'pre_auth_token' not in data
        assert 'tokens' in data
        assert 'access' in data['tokens']
        assert 'refresh' in data['tokens']
        assert data.get('active_role') == 'STAFF'

        # Staff access token has 15-minute lifetime
        payload = jwt.decode(data['tokens']['access'], settings.SECRET_KEY, algorithms=['HS256'])
        exp_diff = payload['exp'] - payload['iat']
        assert 890 <= exp_diff <= 910

    def test_buyer_login_without_mfa_issues_tokens_directly(self, api_client, buyer_user):
        res = api_client.post('/api/v1/auth/login/', {
            'email': buyer_user.email,
            'password': 'SecurePassword123!',
        }, format='json')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data.get('status') == 'success'
        assert 'tokens' in data
        assert 'access' in data['tokens']
        assert 'refresh' in data['tokens']
        assert data.get('active_role') == 'BUYER'

        # Non-staff standard lifetime (60 minutes)
        payload = jwt.decode(data['tokens']['access'], settings.SECRET_KEY, algorithms=['HS256'])
        exp_diff = payload['exp'] - payload['iat']
        assert 3550 <= exp_diff <= 3650

    def test_seller_login_without_mfa_issues_tokens_directly(self, api_client, seller_user):
        res = api_client.post('/api/v1/auth/login/', {
            'email': seller_user.email,
            'password': 'SecurePassword123!',
        }, format='json')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data.get('status') == 'success'
        assert 'tokens' in data
        assert 'access' in data['tokens']
        assert 'refresh' in data['tokens']
        assert data.get('active_role') == 'SELLER'

    def test_workshop_login_without_mfa_issues_tokens_directly(self, api_client, workshop_user):
        res = api_client.post('/api/v1/auth/login/', {
            'email': workshop_user.email,
            'password': 'SecurePassword123!',
        }, format='json')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data.get('status') == 'success'
        assert 'tokens' in data
        assert 'access' in data['tokens']
        assert 'refresh' in data['tokens']
        assert data.get('active_role') == 'WORKSHOP'

    def test_mfa_disabled_still_enforces_password_and_account_validations(self, api_client, buyer_user):
        # Invalid password
        bad_pw = api_client.post('/api/v1/auth/login/', {
            'email': buyer_user.email,
            'password': 'WrongPassword999!',
        }, format='json')
        assert bad_pw.status_code == status.HTTP_400_BAD_REQUEST

        # Unverified email
        buyer_user.is_email_verified = False
        buyer_user.save()
        unverified = api_client.post('/api/v1/auth/login/', {
            'email': buyer_user.email,
            'password': 'SecurePassword123!',
        }, format='json')
        assert unverified.status_code == status.HTTP_400_BAD_REQUEST

        # Suspended account
        buyer_user.is_email_verified = True
        buyer_user.status = AccountStatusChoices.SUSPENDED
        buyer_user.save()
        suspended = api_client.post('/api/v1/auth/login/', {
            'email': buyer_user.email,
            'password': 'SecurePassword123!',
        }, format='json')
        assert suspended.status_code == status.HTTP_400_BAD_REQUEST


# =============================================================================
# Task C Tests: Staff JWT Refresh Lifetime (15-Minute Clamping)
# =============================================================================

@pytest.mark.django_db
class TestStaffJWTRefreshLifetime:

    @pytest.fixture(autouse=True)
    def enable_mfa(self, settings):
        settings.MFA_MANDATORY_ENFORCED = True

    def test_staff_refresh_maintains_15_minute_lifetime(self, api_client, verification_officer):
        # Generate initial tokens via MFA
        totp = pyotp.TOTP(verification_officer.staff_profile.get_totp_secret())
        login_res = api_client.post('/api/v1/auth/login/', {
            'email': verification_officer.email,
            'password': 'SecureStaffPassword123!',
        }, format='json')
        pre_auth_token = login_res.json()['pre_auth_token']

        verify_res = api_client.post('/api/v1/auth/mfa/verify/', {
            'pre_auth_token': pre_auth_token,
            'code': totp.now(),
        }, format='json')
        initial_tokens = verify_res.json()['tokens']
        refresh_token = initial_tokens['refresh']

        # 1. First refresh
        refresh_res = api_client.post('/api/v1/auth/token/refresh/', {
            'refresh': refresh_token,
        }, format='json')
        assert refresh_res.status_code == status.HTTP_200_OK
        new_tokens = refresh_res.json()
        new_access = new_tokens['access']

        # Check access token lifetime is clamped to 15 minutes (900 seconds)
        payload = jwt.decode(new_access, settings.SECRET_KEY, algorithms=['HS256'])
        exp_diff = payload['exp'] - payload['iat']
        assert 890 <= exp_diff <= 910

        # 2. Second consecutive refresh using rotated refresh token
        rotated_refresh = new_tokens['refresh']
        second_refresh_res = api_client.post('/api/v1/auth/token/refresh/', {
            'refresh': rotated_refresh,
        }, format='json')
        assert second_refresh_res.status_code == status.HTTP_200_OK
        second_tokens = second_refresh_res.json()
        second_payload = jwt.decode(second_tokens['access'], settings.SECRET_KEY, algorithms=['HS256'])
        second_diff = second_payload['exp'] - second_payload['iat']
        assert 890 <= second_diff <= 910

        # 3. Old refresh token was blacklisted after rotation
        blacklisted_res = api_client.post('/api/v1/auth/token/refresh/', {
            'refresh': refresh_token,
        }, format='json')
        assert blacklisted_res.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED)

    def test_buyer_refresh_preserves_standard_60_minute_lifetime(self, api_client, buyer_user):
        login_res = api_client.post('/api/v1/auth/login/', {
            'email': buyer_user.email,
            'password': 'SecurePassword123!',
        }, format='json')
        refresh_token = login_res.json()['tokens']['refresh']

        refresh_res = api_client.post('/api/v1/auth/token/refresh/', {
            'refresh': refresh_token,
        }, format='json')
        assert refresh_res.status_code == status.HTTP_200_OK
        new_access = refresh_res.json()['access']

        payload = jwt.decode(new_access, settings.SECRET_KEY, algorithms=['HS256'])
        exp_diff = payload['exp'] - payload['iat']
        # Standard lifetime is 60 minutes = 3600 seconds
        assert 3550 <= exp_diff <= 3650

    def test_role_tampering_in_refresh_token_fails_to_bypass_staff_policy(self, api_client, verification_officer):
        """Even if client-side or token payload claims active_role='BUYER', server checks DB."""
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(verification_officer)
        # Attempt to forge claims
        refresh['active_role'] = 'BUYER'
        refresh['roles'] = ['BUYER']

        res = api_client.post('/api/v1/auth/token/refresh/', {
            'refresh': str(refresh),
        }, format='json')
        assert res.status_code == status.HTTP_200_OK
        access_token = res.json()['access']
        payload = jwt.decode(access_token, settings.SECRET_KEY, algorithms=['HS256'])
        exp_diff = payload['exp'] - payload['iat']
        # Authoritative DB lookup confirms user.is_staff=True -> 15 min lifetime enforced!
        assert 890 <= exp_diff <= 910

    def test_inactive_or_suspended_user_cannot_refresh(self, api_client, buyer_user):
        login_res = api_client.post('/api/v1/auth/login/', {
            'email': buyer_user.email,
            'password': 'SecurePassword123!',
        }, format='json')
        refresh_token = login_res.json()['tokens']['refresh']

        # Deactivate user
        buyer_user.is_active = False
        buyer_user.save()

        res = api_client.post('/api/v1/auth/token/refresh/', {
            'refresh': refresh_token,
        }, format='json')
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

    def test_missing_user_in_refresh_token_fails(self, api_client):
        import uuid
        from rest_framework_simplejwt.tokens import RefreshToken
        from rest_framework_simplejwt.settings import api_settings
        refresh = RefreshToken()
        refresh[api_settings.USER_ID_CLAIM] = str(uuid.uuid4())

        res = api_client.post('/api/v1/auth/token/refresh/', {
            'refresh': str(refresh),
        }, format='json')
        assert res.status_code == status.HTTP_401_UNAUTHORIZED


# =============================================================================
# Task E Tests: Safe Staff Invitation Lifecycle
# =============================================================================

@pytest.mark.django_db
class TestFailureSafeStaffInvitations:

    def test_invitation_creation_rolls_back_atomically_on_email_failure(self, admin_auth_client):
        payload = {
            'email': 'unreachable@driverxtra.com',
            'first_name': 'Test',
            'last_name': 'FailedEmail',
            'staff_role': 'SUPPORT_AGENT',
            'department': 'Support',
        }

        # Mock send_mail to simulate an SMTP network failure
        with patch('django.core.mail.send_mail', side_effect=OSError("SMTP server connection timeout")):
            res = admin_auth_client.post('/api/v1/admin/staff/invite/', payload, format='json')

        assert res.status_code == status.HTTP_400_BAD_REQUEST
        # Transaction rolled back: user must NOT exist in database
        assert not User.objects.filter(email='unreachable@driverxtra.com').exists()
        assert not StaffInviteToken.objects.filter(user__email='unreachable@driverxtra.com').exists()

        # Re-invite with working email succeeds immediately without "user already exists" error
        res_ok = admin_auth_client.post('/api/v1/admin/staff/invite/', payload, format='json')
        assert res_ok.status_code == status.HTTP_201_CREATED
        assert User.objects.filter(email='unreachable@driverxtra.com').exists()

    def test_active_user_cannot_be_invited_again(self, admin_auth_client, buyer_user):
        payload = {
            'email': buyer_user.email,
            'staff_role': 'SUPPORT_AGENT',
        }
        res = admin_auth_client.post('/api/v1/admin/staff/invite/', payload, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert 'already exists' in str(res.json()).lower()

    def test_invitation_single_use_and_expiration(self, admin_auth_client, api_client):
        from django.core import mail
        import re

        payload = {
            'email': 'singleuse@driverxtra.com',
            'staff_role': 'DISPUTE_MANAGER',
        }
        res = admin_auth_client.post('/api/v1/admin/staff/invite/', payload, format='json')
        assert res.status_code == status.HTTP_201_CREATED

        # Extract token
        email_body = mail.outbox[-1].body
        match = re.search(r'token=([a-zA-Z0-9_\-]+)', email_body)
        assert match is not None
        raw_token = match.group(1)

        # First redemption succeeds
        set_res = api_client.post('/api/v1/auth/staff/set-password/', {
            'token': raw_token,
            'new_password': 'SecurePassword123!',
        }, format='json')
        assert set_res.status_code == status.HTTP_200_OK

        # Second redemption fails (single-use)
        reused_res = api_client.post('/api/v1/auth/staff/set-password/', {
            'token': raw_token,
            'new_password': 'AnotherPassword123!',
        }, format='json')
        assert reused_res.status_code == status.HTTP_400_BAD_REQUEST
        assert 'already used' in str(reused_res.json()).lower()

    def test_invitation_error_does_not_leak_smtp_details(self, admin_auth_client):
        payload = {
            'email': 'leaktest@driverxtra.com',
            'first_name': 'Test',
            'last_name': 'LeakCheck',
            'staff_role': 'SUPPORT_AGENT',
            'department': 'Support',
        }
        with patch('django.core.mail.send_mail', side_effect=Exception("smtp.internal.driverxtra.com:587 auth failure with pass=SuperSecretPass!")):
            res = admin_auth_client.post('/api/v1/admin/staff/invite/', payload, format='json')

        assert res.status_code == status.HTTP_400_BAD_REQUEST
        err_msg = str(res.json())
        assert 'SuperSecretPass!' not in err_msg
        assert 'smtp.internal.driverxtra.com' not in err_msg
        assert 'safely rolled back' in err_msg.lower()

