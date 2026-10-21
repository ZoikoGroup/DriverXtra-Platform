import pytest
from datetime import timedelta
from django.core import mail
from django.utils import timezone
from rest_framework import status
from apps.identity.models import User, RoleChoices, EmailVerificationToken, PasswordResetToken
from apps.identity.services import create_and_send_email_verification, create_and_send_password_reset, hash_token


@pytest.mark.django_db
class TestEmailVerification:

    def test_registration_creates_verification_token_and_sends_email(self, api_client):
        mail.outbox.clear()
        payload = {
            'email': 'verifytest@example.co.uk',
            'password': 'StrongPassword2026!',
            'first_name': 'Verify',
            'last_name': 'Me',
        }
        resp = api_client.post('/api/v1/auth/register/', payload, format='json')
        assert resp.status_code == status.HTTP_201_CREATED

        user = User.objects.get(email='verifytest@example.co.uk')
        assert not user.is_email_verified

        token_record = EmailVerificationToken.objects.filter(user=user, consumed_at__isnull=True).first()
        assert token_record is not None
        assert len(mail.outbox) == 1
        assert 'verify' in mail.outbox[0].subject.lower()
        assert 'verify-email?token=' in mail.outbox[0].body

    def test_verify_email_success(self, api_client, buyer_user):
        buyer_user.is_email_verified = False
        buyer_user.email_verified_at = None
        buyer_user.save()

        raw_token = create_and_send_email_verification(buyer_user)

        resp = api_client.post('/api/v1/auth/verify-email/', {'token': raw_token}, format='json')
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data['status'] == 'success'

        buyer_user.refresh_from_db()
        assert buyer_user.is_email_verified is True
        assert buyer_user.email_verified_at is not None

        # Verify token is marked consumed
        token_record = EmailVerificationToken.objects.get(token_hash=hash_token(raw_token))
        assert token_record.consumed_at is not None

    def test_verify_email_consumed_token_rejected(self, api_client, buyer_user):
        buyer_user.is_email_verified = False
        buyer_user.save()
        raw_token = create_and_send_email_verification(buyer_user)

        # First use
        first_resp = api_client.post('/api/v1/auth/verify-email/', {'token': raw_token}, format='json')
        assert first_resp.status_code == status.HTTP_200_OK

        # Second use (must be rejected)
        second_resp = api_client.post('/api/v1/auth/verify-email/', {'token': raw_token}, format='json')
        assert second_resp.status_code == status.HTTP_400_BAD_REQUEST
        assert 'already been used' in str(second_resp.json()).lower()

    def test_verify_email_expired_token_rejected(self, api_client, buyer_user):
        raw_token = create_and_send_email_verification(buyer_user)
        token_record = EmailVerificationToken.objects.get(token_hash=hash_token(raw_token))
        token_record.expires_at = timezone.now() - timedelta(minutes=5)
        token_record.save(update_fields=['expires_at'])

        resp = api_client.post('/api/v1/auth/verify-email/', {'token': raw_token}, format='json')
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert 'expired' in str(resp.json()).lower()

    def test_verify_email_invalid_token_rejected(self, api_client):
        resp = api_client.post('/api/v1/auth/verify-email/', {'token': 'completely_bogus_token'}, format='json')
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert 'invalid or expired' in str(resp.json()).lower()

    def test_resend_verification_enumeration_safe(self, api_client, buyer_user):
        mail.outbox.clear()
        buyer_user.is_email_verified = False
        buyer_user.save()

        # Resend for existing unverified user
        resp = api_client.post('/api/v1/auth/resend-verification/', {'email': buyer_user.email}, format='json')
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data['status'] == 'success'
        assert len(mail.outbox) == 1

        # Resend for non-existent email returns identical generic response
        mail.outbox.clear()
        resp_nonexistent = api_client.post('/api/v1/auth/resend-verification/', {'email': 'nonexistent@example.com'}, format='json')
        assert resp_nonexistent.status_code == status.HTTP_200_OK
        assert resp_nonexistent.json()['message'] == data['message']
        assert len(mail.outbox) == 0

    def test_registration_and_verification_end_to_end_from_email_url(self, api_client):
        """Regression: Full flow from public registration to extracting token from email URL,

        verifying account, and verifying replay protection on the newly generated token.
        """
        import re
        from urllib.parse import urlparse, parse_qs

        mail.outbox.clear()
        reg_payload = {
            'email': 'e2e_verify@example.co.uk',
            'password': 'StrongPassword2026!',
            'first_name': 'E2E',
            'last_name': 'Tester',
        }
        reg_resp = api_client.post('/api/v1/auth/register/', reg_payload, format='json')
        assert reg_resp.status_code == status.HTTP_201_CREATED

        user = User.objects.get(email='e2e_verify@example.co.uk')
        assert user.is_email_verified is False
        assert user.email_verified_at is None
        assert len(mail.outbox) == 1

        # Extract token from the verification link in the dispatched email
        email_body = mail.outbox[0].body
        url_match = re.search(r'http[s]?://\S+', email_body)
        assert url_match is not None, "Email body must contain verification URL"
        verification_url = url_match.group(0)

        parsed_url = urlparse(verification_url)
        query_params = parse_qs(parsed_url.query)
        assert 'token' in query_params, "Verification URL must include token query parameter"
        extracted_token = query_params['token'][0]

        # 1. Successful verification using newly generated token extracted from email URL
        verify_resp = api_client.post('/api/v1/auth/verify-email/', {'token': extracted_token}, format='json')
        assert verify_resp.status_code == status.HTTP_200_OK
        assert verify_resp.json()['status'] == 'success'

        user.refresh_from_db()
        assert user.is_email_verified is True
        assert user.email_verified_at is not None

        # 2. Reused token rejected (replay protection)
        reused_resp = api_client.post('/api/v1/auth/verify-email/', {'token': extracted_token}, format='json')
        assert reused_resp.status_code == status.HTTP_400_BAD_REQUEST
        assert 'already been used' in str(reused_resp.json()).lower()

        # 3. Invalid token rejected
        invalid_resp = api_client.post('/api/v1/auth/verify-email/', {'token': 'invalid_token_xyz'}, format='json')
        assert invalid_resp.status_code == status.HTTP_400_BAD_REQUEST
        assert 'invalid or expired' in str(invalid_resp.json()).lower()

    def test_resend_verification_invalidates_old_token_and_new_token_succeeds(self, api_client):
        """Regression: Resend verification must invalidate prior unconsumed tokens,

        and the newly generated token must verify successfully.
        """
        import re
        from urllib.parse import urlparse, parse_qs

        mail.outbox.clear()
        reg_payload = {
            'email': 'resend_flow@example.co.uk',
            'password': 'StrongPassword2026!',
            'first_name': 'Resend',
            'last_name': 'Flow',
        }
        reg_resp = api_client.post('/api/v1/auth/register/', reg_payload, format='json')
        assert reg_resp.status_code == status.HTTP_201_CREATED
        assert len(mail.outbox) == 1

        # Extract token 1
        url_match_1 = re.search(r'http[s]?://\S+', mail.outbox[0].body)
        token_1 = parse_qs(urlparse(url_match_1.group(0)).query)['token'][0]

        # Request resend
        resend_resp = api_client.post('/api/v1/auth/resend-verification/', {'email': 'resend_flow@example.co.uk'}, format='json')
        assert resend_resp.status_code == status.HTTP_200_OK
        assert len(mail.outbox) == 2

        # Extract token 2
        url_match_2 = re.search(r'http[s]?://\S+', mail.outbox[1].body)
        token_2 = parse_qs(urlparse(url_match_2.group(0)).query)['token'][0]

        # Token 1 must now be invalidated as consumed
        verify_token_1 = api_client.post('/api/v1/auth/verify-email/', {'token': token_1}, format='json')
        assert verify_token_1.status_code == status.HTTP_400_BAD_REQUEST
        assert 'already been used' in str(verify_token_1.json()).lower()

        # Token 2 must succeed
        verify_token_2 = api_client.post('/api/v1/auth/verify-email/', {'token': token_2}, format='json')
        assert verify_token_2.status_code == status.HTTP_200_OK
        assert verify_token_2.json()['status'] == 'success'

        user = User.objects.get(email='resend_flow@example.co.uk')
        assert user.is_email_verified is True

    def test_verify_email_accepts_full_url_and_labeled_token(self, api_client, buyer_user):
        """Ensure backend serializer cleans tokens pasted with full URL, prefix, or surrounding quotes."""
        buyer_user.is_email_verified = False
        buyer_user.email_verified_at = None
        buyer_user.save()

        # Test 1: Full verification link pasted
        raw_token_1 = create_and_send_email_verification(buyer_user)
        full_url = f"http://localhost:3000/verify-email?token={raw_token_1}&email={buyer_user.email}"
        resp_1 = api_client.post('/api/v1/auth/verify-email/', {'token': full_url}, format='json')
        assert resp_1.status_code == status.HTTP_200_OK
        assert resp_1.json()['status'] == 'success'

        # Reset
        buyer_user.is_email_verified = False
        buyer_user.email_verified_at = None
        buyer_user.save()

        # Test 2: Token with 'Verification Token: ' prefix pasted
        raw_token_2 = create_and_send_email_verification(buyer_user)
        labeled = f"Verification Token: {raw_token_2}"
        resp_2 = api_client.post('/api/v1/auth/verify-email/', {'token': labeled}, format='json')
        assert resp_2.status_code == status.HTTP_200_OK

        # Reset
        buyer_user.is_email_verified = False
        buyer_user.email_verified_at = None
        buyer_user.save()

        # Test 4: Token with 'Token: ' or 'token: ' prefix pasted
        raw_token_4 = create_and_send_email_verification(buyer_user)
        resp_4 = api_client.post('/api/v1/auth/verify-email/', {'token': f"Token: {raw_token_4}"}, format='json')
        assert resp_4.status_code == status.HTTP_200_OK

        # Reset
        buyer_user.is_email_verified = False
        buyer_user.save()

        # Test 5: URL without protocol (e.g. copied from address bar)
        raw_token_5 = create_and_send_email_verification(buyer_user)
        no_proto = f"localhost:3000/verify-email?token={raw_token_5}&email={buyer_user.email}"
        resp_5 = api_client.post('/api/v1/auth/verify-email/', {'token': no_proto}, format='json')
        assert resp_5.status_code == status.HTTP_200_OK

        # Reset
        buyer_user.is_email_verified = False
        buyer_user.save()

        # Test 6: Token with trailing &email parameter copied
        raw_token_6 = create_and_send_email_verification(buyer_user)
        trailing_param = f"{raw_token_6}&email={buyer_user.email}"
        resp_6 = api_client.post('/api/v1/auth/verify-email/', {'token': trailing_param}, format='json')
        assert resp_6.status_code == status.HTTP_200_OK

        # Reset
        buyer_user.is_email_verified = False
        buyer_user.save()

        # Test 7: Standalone token= query string
        raw_token_7 = create_and_send_email_verification(buyer_user)
        resp_7 = api_client.post('/api/v1/auth/verify-email/', {'token': f"token={raw_token_7}&email={buyer_user.email}"}, format='json')
        assert resp_7.status_code == status.HTTP_200_OK



@pytest.mark.django_db
class TestPasswordReset:

    def test_password_reset_request_enumeration_safe(self, api_client, buyer_user):
        mail.outbox.clear()
        resp = api_client.post('/api/v1/auth/password-reset/request/', {'email': buyer_user.email}, format='json')
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data['status'] == 'success'
        assert len(mail.outbox) == 1
        assert 'reset' in mail.outbox[0].subject.lower()

        # Non-existent email returns exact same message
        mail.outbox.clear()
        resp_nonexistent = api_client.post('/api/v1/auth/password-reset/request/', {'email': 'ghost@example.com'}, format='json')
        assert resp_nonexistent.status_code == status.HTTP_200_OK
        assert resp_nonexistent.json()['message'] == data['message']
        assert len(mail.outbox) == 0

    def test_password_reset_confirm_success_and_blacklists_tokens(self, api_client, buyer_user):
        raw_token = create_and_send_password_reset(buyer_user)

        # Login to generate an active JWT session
        login_resp = api_client.post('/api/v1/auth/login/', {
            'email': buyer_user.email,
            'password': 'SecurePassword123!',
        }, format='json')
        refresh_token = login_resp.json()['tokens']['refresh']

        # Confirm password reset with new password
        reset_resp = api_client.post('/api/v1/auth/password-reset/confirm/', {
            'token': raw_token,
            'new_password': 'BrandNewPassword2026!',
        }, format='json')
        assert reset_resp.status_code == status.HTTP_200_OK
        assert reset_resp.json()['status'] == 'success'

        # Verify old password no longer works
        old_login = api_client.post('/api/v1/auth/login/', {
            'email': buyer_user.email,
            'password': 'SecurePassword123!',
        }, format='json')
        assert old_login.status_code == status.HTTP_400_BAD_REQUEST

        # Verify new password works
        new_login = api_client.post('/api/v1/auth/login/', {
            'email': buyer_user.email,
            'password': 'BrandNewPassword2026!',
        }, format='json')
        assert new_login.status_code == status.HTTP_200_OK

        # Verify outstanding refresh token before password reset was blacklisted
        refresh_resp = api_client.post('/api/v1/auth/token/refresh/', {
            'refresh': refresh_token,
        }, format='json')
        assert refresh_resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_password_reset_confirm_single_use(self, api_client, buyer_user):
        raw_token = create_and_send_password_reset(buyer_user)

        first_resp = api_client.post('/api/v1/auth/password-reset/confirm/', {
            'token': raw_token,
            'new_password': 'NewPassword123!',
        }, format='json')
        assert first_resp.status_code == status.HTTP_200_OK

        # Second attempt must be rejected
        second_resp = api_client.post('/api/v1/auth/password-reset/confirm/', {
            'token': raw_token,
            'new_password': 'AnotherPassword123!',
        }, format='json')
        assert second_resp.status_code == status.HTTP_400_BAD_REQUEST
        assert 'already been used' in str(second_resp.json()).lower()

    def test_password_reset_confirm_expired(self, api_client, buyer_user):
        raw_token = create_and_send_password_reset(buyer_user)
        token_record = PasswordResetToken.objects.get(token_hash=hash_token(raw_token))
        token_record.expires_at = timezone.now() - timedelta(minutes=1)
        token_record.save(update_fields=['expires_at'])

        resp = api_client.post('/api/v1/auth/password-reset/confirm/', {
            'token': raw_token,
            'new_password': 'NewPassword123!',
        }, format='json')
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert 'expired' in str(resp.json()).lower()

    def test_password_reset_confirm_invalid_token(self, api_client):
        resp = api_client.post('/api/v1/auth/password-reset/confirm/', {
            'token': 'bogus_token_12345',
            'new_password': 'NewPassword123!',
        }, format='json')
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert 'invalid or expired' in str(resp.json()).lower()

    def test_password_reset_confirm_weak_password_rejected(self, api_client, buyer_user):
        raw_token = create_and_send_password_reset(buyer_user)

        resp = api_client.post('/api/v1/auth/password-reset/confirm/', {
            'token': raw_token,
            'new_password': 'short',
        }, format='json')
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert 'new_password' in str(resp.json())
