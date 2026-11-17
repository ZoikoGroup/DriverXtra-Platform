"""Phase 3 Test Suite: Staff Administration Dashboard & Invitation Management.

Verifies:
1. Staff directory listing with search, role, status, and MFA filters.
2. Authorization controls: Platform Admin has access; non-admin users (buyers, non-admin staff) receive 403 Forbidden.
3. Staff member detail retrieval with granular permissions and profile data.
4. Staff member updates: role modification, department updates, and status toggling (ACTIVE / SUSPENDED).
5. Self-suspension protection: Administrators cannot suspend their own account.
6. Available staff roles endpoint returning active roles and their permission codes.
7. Staff dashboard overview metrics: total staff, active, suspended, pending invites, MFA adoption.
8. Staff invitation management: listing invitations with status filters (PENDING, EXPIRED, ACCEPTED).
9. Re-dispatching invitations: resending invitation generates fresh token, updates expiration, sends email, and logs audit.
10. Resend prevention for already activated staff accounts.
11. Revoking pending invitations: deletes token and cleans unactivated user records.
12. Revocation prevention for already activated accounts.
13. Immutable audit trail verification for all staff management lifecycle events.
"""

from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.utils import timezone
import pyotp
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.identity.models import (
    AccountStatusChoices,
    RoleChoices,
    StaffInviteToken,
    StaffProfile,
    StaffRole,
    User,
)
from platform_core.audit.models import AuditLog


@pytest.fixture
def make_staff():
    """Helper factory to create staff users with specific roles and optional TOTP."""
    def _create(email, role_code, first_name='Staff', last_name='Member', mfa_enabled=False, account_status=AccountStatusChoices.ACTIVE):
        user = User.objects.create_user(
            email=email,
            password='SecureStaffPassword123!',
            first_name=first_name,
            last_name=last_name,
            is_staff=True,
            is_email_verified=True,
            status=account_status,
        )
        user.add_role(RoleChoices.STAFF)
        role = StaffRole.objects.get(code=role_code)
        profile, _ = StaffProfile.objects.get_or_create(user=user)
        profile.staff_role = role
        profile.department = 'Trust & Safety'
        if mfa_enabled:
            profile.totp_enabled = True
            profile.set_totp_secret(pyotp.random_base32())
        profile.save()
        return user
    return _create


@pytest.mark.django_db
class TestStaffAdministrationDirectoryAndDetails:

    def test_admin_can_list_staff_directory_with_filters(self, admin_auth_client, make_staff):
        s1 = make_staff('officer1@driverxtra.com', 'VERIFICATION_OFFICER', 'Alice', 'Smith', mfa_enabled=True)
        s2 = make_staff('dispute1@driverxtra.com', 'DISPUTE_MANAGER', 'Bob', 'Jones', mfa_enabled=False)
        s3 = make_staff('suspended1@driverxtra.com', 'FINANCE_OFFICER', 'Charlie', 'Brown', account_status=AccountStatusChoices.SUSPENDED)

        # 1. Full list
        res = admin_auth_client.get('/api/v1/admin/staff/')
        assert res.status_code == status.HTTP_200_OK
        emails = [item['email'] for item in res.json()['results']]
        assert s1.email in emails
        assert s2.email in emails
        assert s3.email in emails

        # 2. Search filter
        res_search = admin_auth_client.get('/api/v1/admin/staff/?search=Alice')
        assert res_search.status_code == status.HTTP_200_OK
        assert len(res_search.json()['results']) == 1
        assert res_search.json()['results'][0]['email'] == s1.email

        # 3. Role filter
        res_role = admin_auth_client.get('/api/v1/admin/staff/?role=DISPUTE_MANAGER')
        assert res_role.status_code == status.HTTP_200_OK
        role_emails = [item['email'] for item in res_role.json()['results']]
        assert s2.email in role_emails
        assert s1.email not in role_emails

        # 4. Status filter
        res_status = admin_auth_client.get('/api/v1/admin/staff/?status=SUSPENDED')
        assert res_status.status_code == status.HTTP_200_OK
        suspended_emails = [item['email'] for item in res_status.json()['results']]
        assert s3.email in suspended_emails
        assert s1.email not in suspended_emails

        # 5. MFA filter
        res_mfa = admin_auth_client.get('/api/v1/admin/staff/?mfa=true')
        assert res_mfa.status_code == status.HTTP_200_OK
        mfa_emails = [item['email'] for item in res_mfa.json()['results']]
        assert s1.email in mfa_emails
        assert s2.email not in mfa_emails

    def test_non_admin_forbidden_from_staff_directory(self, buyer_user, make_staff):
        client = APIClient()
        client.force_authenticate(user=buyer_user)
        res_buyer = client.get('/api/v1/admin/staff/')
        assert res_buyer.status_code == status.HTTP_403_FORBIDDEN

        staff_user = make_staff('regular.staff@driverxtra.com', 'SUPPORT_AGENT')
        client.force_authenticate(user=staff_user)
        res_staff = client.get('/api/v1/admin/staff/')
        assert res_staff.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_retrieve_staff_detail(self, admin_auth_client, make_staff):
        officer = make_staff('detail.officer@driverxtra.com', 'VERIFICATION_OFFICER', 'Diana', 'Prince')
        res = admin_auth_client.get(f'/api/v1/admin/staff/{officer.id}/')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()['staff_member']
        assert data['email'] == officer.email
        assert data['staff_role']['code'] == 'VERIFICATION_OFFICER'
        assert 'seller.verify' in data['staff_role']['permissions']
        assert 'listing.review' in data['staff_role']['permissions']

    def test_admin_can_update_staff_role_and_department(self, admin_auth_client, make_staff):
        officer = make_staff('switch.officer@driverxtra.com', 'VERIFICATION_OFFICER')

        payload = {
            'staff_role': 'FINANCE_OFFICER',
            'department': 'Global Finance & Treasury',
        }
        res = admin_auth_client.patch(f'/api/v1/admin/staff/{officer.id}/', payload, format='json')
        assert res.status_code == status.HTTP_200_OK
        updated = res.json()['staff_member']
        assert updated['staff_role']['code'] == 'FINANCE_OFFICER'
        assert updated['department'] == 'Global Finance & Treasury'

        # Verify database
        officer.refresh_from_db()
        assert officer.staff_profile.staff_role.code == 'FINANCE_OFFICER'
        assert officer.staff_profile.department == 'Global Finance & Treasury'

        # Verify audit log
        assert AuditLog.objects.filter(
            action='staff:update',
            resource_id=str(officer.id),
        ).exists()

    def test_admin_can_suspend_and_reactivate_staff_member(self, admin_auth_client, make_staff):
        officer = make_staff('toggle.officer@driverxtra.com', 'SUPPORT_AGENT')

        # Suspend
        res_suspend = admin_auth_client.patch(
            f'/api/v1/admin/staff/{officer.id}/',
            {'status': AccountStatusChoices.SUSPENDED},
            format='json',
        )
        assert res_suspend.status_code == status.HTTP_200_OK
        assert res_suspend.json()['staff_member']['status'] == AccountStatusChoices.SUSPENDED
        officer.refresh_from_db()
        assert officer.status == AccountStatusChoices.SUSPENDED
        assert officer.is_active is False

        # Reactivate
        res_activate = admin_auth_client.patch(
            f'/api/v1/admin/staff/{officer.id}/',
            {'status': AccountStatusChoices.ACTIVE},
            format='json',
        )
        assert res_activate.status_code == status.HTTP_200_OK
        assert res_activate.json()['staff_member']['status'] == AccountStatusChoices.ACTIVE
        officer.refresh_from_db()
        assert officer.status == AccountStatusChoices.ACTIVE
        assert officer.is_active is True

    def test_admin_cannot_suspend_own_account(self, admin_auth_client, admin_user):
        res = admin_auth_client.patch(
            f'/api/v1/admin/staff/{admin_user.id}/',
            {'status': AccountStatusChoices.SUSPENDED},
            format='json',
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert 'cannot suspend your own' in str(res.json()).lower()


@pytest.mark.django_db
class TestStaffRolesAndMetrics:

    def test_list_active_staff_roles(self, admin_auth_client):
        res = admin_auth_client.get('/api/v1/admin/staff/roles/')
        assert res.status_code == status.HTTP_200_OK
        roles = res.json()['roles']
        role_codes = [r['code'] for r in roles]
        assert 'VERIFICATION_OFFICER' in role_codes
        assert 'DISPUTE_MANAGER' in role_codes
        assert 'FINANCE_OFFICER' in role_codes
        assert 'SUPPORT_AGENT' in role_codes

        verif = next(r for r in roles if r['code'] == 'VERIFICATION_OFFICER')
        assert 'seller.verify' in verif['permissions']
        assert 'listing.review' in verif['permissions']

    def test_staff_metrics_overview(self, admin_auth_client, make_staff):
        make_staff('mfa.staff@driverxtra.com', 'VERIFICATION_OFFICER', mfa_enabled=True)
        make_staff('nomfa.staff@driverxtra.com', 'SUPPORT_AGENT', mfa_enabled=False)

        res = admin_auth_client.get('/api/v1/admin/staff/metrics/')
        assert res.status_code == status.HTTP_200_OK
        metrics = res.json()['metrics']
        assert metrics['total_staff'] >= 2
        assert metrics['active_staff'] >= 2
        assert 'mfa_adoption_percentage' in metrics
        assert 'role_distribution' in metrics


@pytest.mark.django_db
class TestStaffInvitationManagement:

    def test_list_invitations_with_status_filtering(self, admin_auth_client):
        # 1. Create an active invitation
        res1 = admin_auth_client.post('/api/v1/admin/staff/invite/', {
            'email': 'pending.invite@driverxtra.com',
            'first_name': 'Pending',
            'last_name': 'User',
            'staff_role': 'SUPPORT_AGENT',
        }, format='json')
        assert res1.status_code == status.HTTP_201_CREATED

        # 2. Create an expired invitation
        res2 = admin_auth_client.post('/api/v1/admin/staff/invite/', {
            'email': 'expired.invite@driverxtra.com',
            'first_name': 'Expired',
            'last_name': 'User',
            'staff_role': 'FINANCE_OFFICER',
        }, format='json')
        assert res2.status_code == status.HTTP_201_CREATED
        # Manually backdate expiration
        StaffInviteToken.objects.filter(user__email='expired.invite@driverxtra.com').update(
            expires_at=timezone.now() - timedelta(hours=2)
        )

        # 3. List all
        res_all = admin_auth_client.get('/api/v1/admin/staff/invitations/')
        assert res_all.status_code == status.HTTP_200_OK
        all_emails = [i['email'] for i in res_all.json()['results']]
        assert 'pending.invite@driverxtra.com' in all_emails
        assert 'expired.invite@driverxtra.com' in all_emails

        # 4. Filter PENDING
        res_pending = admin_auth_client.get('/api/v1/admin/staff/invitations/?status=PENDING')
        assert res_pending.status_code == status.HTTP_200_OK
        pending_emails = [i['email'] for i in res_pending.json()['results']]
        assert 'pending.invite@driverxtra.com' in pending_emails
        assert 'expired.invite@driverxtra.com' not in pending_emails

        # 5. Filter EXPIRED
        res_expired = admin_auth_client.get('/api/v1/admin/staff/invitations/?status=EXPIRED')
        assert res_expired.status_code == status.HTTP_200_OK
        expired_emails = [i['email'] for i in res_expired.json()['results']]
        assert 'expired.invite@driverxtra.com' in expired_emails
        assert 'pending.invite@driverxtra.com' not in expired_emails

    def test_resend_invitation_dispatches_fresh_link_and_updates_expiry(self, admin_auth_client):
        mail.outbox.clear()
        # Create initial invite
        admin_auth_client.post('/api/v1/admin/staff/invite/', {
            'email': 'resend.test@driverxtra.com',
            'first_name': 'Resend',
            'last_name': 'Target',
            'staff_role': 'DISPUTE_MANAGER',
        }, format='json')

        invite = StaffInviteToken.objects.get(user__email='resend.test@driverxtra.com')
        old_hash = invite.token_hash
        # Backdate expiration
        invite.expires_at = timezone.now() - timedelta(hours=1)
        invite.save()

        # Resend invitation
        res = admin_auth_client.post(f'/api/v1/admin/staff/invitations/{invite.id}/resend/')
        assert res.status_code == status.HTTP_200_OK
        assert 'dispatched successfully' in res.json()['message'].lower()

        invite.refresh_from_db()
        assert invite.token_hash != old_hash
        assert invite.expires_at > timezone.now() + timedelta(hours=47)

        # Verify email dispatched
        assert len(mail.outbox) >= 2
        assert 'Resent' in mail.outbox[-1].subject

        # Verify audit log
        assert AuditLog.objects.filter(
            action='staff:invite_resend',
            resource_id=str(invite.user.id),
        ).exists()

    def test_cannot_resend_invitation_for_activated_account(self, admin_auth_client, api_client):
        admin_auth_client.post('/api/v1/admin/staff/invite/', {
            'email': 'activated@driverxtra.com',
            'staff_role': 'SUPPORT_AGENT',
        }, format='json')

        invite = StaffInviteToken.objects.get(user__email='activated@driverxtra.com')

        # Simulate password activation
        invite.consumed_at = timezone.now()
        invite.save()
        invite.user.status = AccountStatusChoices.ACTIVE
        invite.user.save()

        res = admin_auth_client.post(f'/api/v1/admin/staff/invitations/{invite.id}/resend/')
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert 'already been activated' in str(res.json()).lower()

    def test_revoke_invitation_removes_token_and_unactivated_user(self, admin_auth_client):
        admin_auth_client.post('/api/v1/admin/staff/invite/', {
            'email': 'revoke.me@driverxtra.com',
            'staff_role': 'VERIFICATION_OFFICER',
        }, format='json')

        invite = StaffInviteToken.objects.get(user__email='revoke.me@driverxtra.com')
        invite_id = str(invite.id)

        res = admin_auth_client.post(f'/api/v1/admin/staff/invitations/{invite_id}/revoke/')
        assert res.status_code == status.HTTP_200_OK
        assert 'revoked' in res.json()['message'].lower()

        # Token and pending user should be cleaned up
        assert not StaffInviteToken.objects.filter(id=invite_id).exists()
        assert not User.objects.filter(email='revoke.me@driverxtra.com').exists()

        # Audit log verified
        assert AuditLog.objects.filter(
            action='staff:invite_revoke',
            resource_id=invite_id,
        ).exists()

    def test_cannot_revoke_already_activated_invitation(self, admin_auth_client):
        admin_auth_client.post('/api/v1/admin/staff/invite/', {
            'email': 'active.stay@driverxtra.com',
            'staff_role': 'SUPPORT_AGENT',
        }, format='json')

        invite = StaffInviteToken.objects.get(user__email='active.stay@driverxtra.com')
        invite.consumed_at = timezone.now()
        invite.save()
        invite.user.status = AccountStatusChoices.ACTIVE
        invite.user.save()

        res = admin_auth_client.post(f'/api/v1/admin/staff/invitations/{invite.id}/revoke/')
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert 'already been accepted' in str(res.json()).lower()


@pytest.mark.django_db
class TestStaffSecuritySignoffVerification:

    def test_last_active_administrator_cannot_be_suspended_or_demoted(self, admin_user, make_staff):
        # Ensure admin_user is the ONLY active admin
        User.objects.filter(is_superuser=True).exclude(id=admin_user.id).delete()
        User.objects.filter(user_roles__role=RoleChoices.ADMIN).exclude(id=admin_user.id).delete()

        client = APIClient()
        client.force_authenticate(user=admin_user)

        # 1. Attempting to suspend the last admin is rejected
        res_suspend = client.patch(f'/api/v1/admin/staff/{admin_user.id}/', {'status': 'SUSPENDED'}, format='json')
        assert res_suspend.status_code == status.HTTP_400_BAD_REQUEST
        assert 'cannot suspend' in str(res_suspend.json()).lower()

        # 2. Attempting to demote the last admin to a staff sub-role is rejected
        res_demote = client.patch(f'/api/v1/admin/staff/{admin_user.id}/', {'staff_role': 'SUPPORT_AGENT'}, format='json')
        assert res_demote.status_code == status.HTTP_400_BAD_REQUEST
        assert 'cannot demote the last active platform administrator' in str(res_demote.json()).lower()

        # 3. Create a second active administrator
        admin2 = User.objects.create_user(
            email='admin2@driverxtra.com',
            password='SecurePassword123!',
            is_staff=True,
            is_email_verified=True,
            status=AccountStatusChoices.ACTIVE,
        )
        admin2.add_role(RoleChoices.ADMIN)

        # Now admin_user can demote admin2 (since admin_user remains active admin)
        res_demote_admin2 = client.patch(f'/api/v1/admin/staff/{admin2.id}/', {'staff_role': 'SUPPORT_AGENT'}, format='json')
        assert res_demote_admin2.status_code == status.HTTP_200_OK
        admin2.refresh_from_db()
        assert not admin2.has_role(RoleChoices.ADMIN)

        # Now that admin2 is demoted, admin_user is once again the last active administrator.
        # Demoting or suspending admin_user must be blocked again!
        res_block = client.patch(f'/api/v1/admin/staff/{admin_user.id}/', {'staff_role': 'SUPPORT_AGENT'}, format='json')
        assert res_block.status_code == status.HTTP_400_BAD_REQUEST
        assert 'cannot demote the last active platform administrator' in str(res_block.json()).lower()

    def test_invitation_only_permits_valid_staff_roles(self, admin_auth_client):
        # Cannot invite as ADMIN
        res_admin = admin_auth_client.post('/api/v1/admin/staff/invite/', {
            'email': 'badrole1@driverxtra.com',
            'staff_role': 'ADMIN',
        }, format='json')
        assert res_admin.status_code == status.HTTP_400_BAD_REQUEST
        assert 'invalid staff role' in str(res_admin.json()).lower()

        # Cannot invite with arbitrary invalid string
        res_arbitrary = admin_auth_client.post('/api/v1/admin/staff/invite/', {
            'email': 'badrole2@driverxtra.com',
            'staff_role': 'SUPER_HACKER',
        }, format='json')
        assert res_arbitrary.status_code == status.HTTP_400_BAD_REQUEST
        assert 'invalid staff role' in str(res_arbitrary.json()).lower()

    def test_invitation_acceptance_enforces_mandatory_mfa_before_access(self, admin_auth_client, api_client):
        from django.test import override_settings
        import re

        mail.outbox.clear()
        admin_auth_client.post('/api/v1/admin/staff/invite/', {
            'email': 'mfa.onboard@driverxtra.com',
            'first_name': 'MFA',
            'last_name': 'Tester',
            'staff_role': 'SUPPORT_AGENT',
        }, format='json')

        match = re.search(r'token=([a-zA-Z0-9_\-]+)', mail.outbox[-1].body)
        assert match is not None
        raw_token = match.group(1)

        # Set password
        set_res = api_client.post('/api/v1/auth/staff/set-password/', {
            'token': raw_token,
            'new_password': 'SuperPassword123!',
        }, format='json')
        assert set_res.status_code == status.HTTP_200_OK

        # Attempt to sign in under mandatory MFA
        with override_settings(MFA_MANDATORY_ENFORCED=True):
            login_res = api_client.post('/api/v1/auth/login/', {
                'email': 'mfa.onboard@driverxtra.com',
                'password': 'SuperPassword123!',
            }, format='json')

            # Must challenge with MFA enrollment required, tokens NOT released
            assert login_res.status_code == status.HTTP_200_OK
            body = login_res.json()
            assert body.get('mfa_required') is True
            assert body.get('mfa_enrollment_required') is True
            assert 'tokens' not in body
            assert 'pre_auth_token' in body

    def test_invalid_uuid_gracefully_returns_404(self, admin_auth_client):
        # Non-UUID string parameters on staff and invitation endpoints return 404 instead of 500
        res_staff = admin_auth_client.get('/api/v1/admin/staff/not-a-valid-uuid/')
        assert res_staff.status_code == status.HTTP_404_NOT_FOUND

        res_patch = admin_auth_client.patch('/api/v1/admin/staff/not-a-valid-uuid/', {'department': 'New'}, format='json')
        assert res_patch.status_code == status.HTTP_404_NOT_FOUND

        res_resend = admin_auth_client.post('/api/v1/admin/staff/invitations/not-a-valid-uuid/resend/')
        assert res_resend.status_code == status.HTTP_404_NOT_FOUND

        res_revoke = admin_auth_client.post('/api/v1/admin/staff/invitations/not-a-valid-uuid/revoke/')
        assert res_revoke.status_code == status.HTTP_404_NOT_FOUND

    def test_audit_logs_do_not_expose_passwords_tokens_or_secrets(self, admin_auth_client):
        import re

        mail.outbox.clear()
        admin_auth_client.post('/api/v1/admin/staff/invite/', {
            'email': 'audit.check@driverxtra.com',
            'first_name': 'Audit',
            'last_name': 'Safe',
            'staff_role': 'VERIFICATION_OFFICER',
        }, format='json')

        match = re.search(r'token=([a-zA-Z0-9_\-]+)', mail.outbox[-1].body)
        raw_token = match.group(1)

        # Retrieve audit logs for this target
        audit_entries = AuditLog.objects.filter(metadata__invited_email='audit.check@driverxtra.com')
        assert audit_entries.exists()
        for entry in audit_entries:
            meta_str = str(entry.metadata)
            assert raw_token not in meta_str
            assert 'password' not in meta_str.lower()


