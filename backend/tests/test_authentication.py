import pytest
from rest_framework import status
from apps.identity.models import AccountStatusChoices


@pytest.mark.django_db
class TestAuthentication:

    def test_successful_login(self, api_client, buyer_user):
        payload = {
            'email': 'buyer@driverxtra.com',
            'password': 'SecurePassword123!',
        }
        response = api_client.post('/api/v1/auth/login/', payload, format='json')
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data['status'] == 'success'
        assert data['mfa_required'] is False
        assert 'tokens' in data
        assert 'access' in data['tokens']
        assert 'refresh' in data['tokens']
        assert data['user']['email'] == buyer_user.email

    def test_login_invalid_password(self, api_client, buyer_user):
        payload = {
            'email': 'buyer@driverxtra.com',
            'password': 'WrongPassword999!',
        }
        response = api_client.post('/api/v1/auth/login/', payload, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert 'Invalid email or password' in str(data)

    def test_login_nonexistent_email(self, api_client):
        payload = {
            'email': 'nobody@driverxtra.com',
            'password': 'SomePassword123!',
        }
        response = api_client.post('/api/v1/auth/login/', payload, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert 'Invalid email or password' in str(data)

    def test_login_suspended_account(self, api_client, buyer_user):
        buyer_user.status = AccountStatusChoices.SUSPENDED
        buyer_user.save()

        payload = {
            'email': 'buyer@driverxtra.com',
            'password': 'SecurePassword123!',
        }
        response = api_client.post('/api/v1/auth/login/', payload, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert 'suspended' in str(data).lower()

    def test_token_refresh(self, api_client, buyer_user):
        login_resp = api_client.post('/api/v1/auth/login/', {
            'email': 'buyer@driverxtra.com',
            'password': 'SecurePassword123!',
        }, format='json')
        refresh_token = login_resp.json()['tokens']['refresh']

        refresh_resp = api_client.post('/api/v1/auth/token/refresh/', {
            'refresh': refresh_token,
        }, format='json')
        assert refresh_resp.status_code == status.HTTP_200_OK
        assert 'access' in refresh_resp.json()

    def test_logout_and_token_invalidation(self, api_client, buyer_user):
        # Authenticate and obtain tokens
        login_resp = api_client.post('/api/v1/auth/login/', {
            'email': 'buyer@driverxtra.com',
            'password': 'SecurePassword123!',
        }, format='json')
        tokens = login_resp.json()['tokens']
        access_token = tokens['access']
        refresh_token = tokens['refresh']

        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')

        # Call logout with refresh token
        logout_resp = api_client.post('/api/v1/auth/logout/', {
            'refresh': refresh_token,
        }, format='json')
        assert logout_resp.status_code == status.HTTP_200_OK
        assert 'invalidated' in logout_resp.json()['message']

        # Attempting to reuse blacklisted refresh token must fail
        refresh_attempt = api_client.post('/api/v1/auth/token/refresh/', {
            'refresh': refresh_token,
        }, format='json')
        assert refresh_attempt.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_unverified_email_denied(self, api_client, buyer_user):
        buyer_user.is_email_verified = False
        buyer_user.save()

        payload = {
            'email': buyer_user.email,
            'password': 'SecurePassword123!',
        }
        response = api_client.post('/api/v1/auth/login/', payload, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert 'not verified' in str(data).lower()
        assert 'tokens' not in data


def _login_tokens(api_client, email, password='SecurePassword123!'):
    res = api_client.post('/api/v1/auth/login/', {'email': email, 'password': password}, format='json')
    assert res.status_code == status.HTTP_200_OK, res.content
    return res.json()['tokens']


def _get_me(token):
    from rest_framework.test import APIClient
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return client.get('/api/v1/users/me/')


def _refresh(refresh_token):
    from rest_framework.test import APIClient
    return APIClient().post('/api/v1/auth/token/refresh/', {'refresh': refresh_token}, format='json')


@pytest.mark.django_db
class TestAccountStatusEnforcement:
    """F3: account status is enforced on every authenticated request and every token refresh,
    using real Bearer tokens (force_authenticate would bypass authentication classes)."""

    @pytest.mark.parametrize('blocked_status', [AccountStatusChoices.SUSPENDED, AccountStatusChoices.DEACTIVATED])
    def test_blocked_status_rejects_existing_access_and_refresh_tokens(self, api_client, buyer_user, blocked_status):
        tokens = _login_tokens(api_client, buyer_user.email)
        assert _get_me(tokens['access']).status_code == status.HTTP_200_OK

        buyer_user.status = blocked_status
        buyer_user.save()
        assert buyer_user.is_active is True  # only the status changed

        me_res = _get_me(tokens['access'])
        assert me_res.status_code == status.HTTP_401_UNAUTHORIZED
        assert blocked_status.lower() in str(me_res.json()).lower()
        assert _refresh(tokens['refresh']).status_code == status.HTTP_401_UNAUTHORIZED

    def test_is_active_false_rejects_existing_tokens(self, api_client, buyer_user):
        tokens = _login_tokens(api_client, buyer_user.email)
        buyer_user.is_active = False
        buyer_user.save()
        assert _get_me(tokens['access']).status_code == status.HTTP_401_UNAUTHORIZED
        assert _refresh(tokens['refresh']).status_code == status.HTTP_401_UNAUTHORIZED

    def test_suspension_blacklists_refresh_tokens_and_reactivation_requires_new_login(self, api_client, buyer_user):
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
        tokens = _login_tokens(api_client, buyer_user.email)

        buyer_user.status = AccountStatusChoices.SUSPENDED
        buyer_user.save(update_fields=['status', 'updated_at'])
        assert BlacklistedToken.objects.filter(token__user=buyer_user).count() >= 1

        # Reactivate: old sessions stay revoked, a fresh login works.
        buyer_user.status = AccountStatusChoices.ACTIVE
        buyer_user.save(update_fields=['status', 'updated_at'])
        assert _refresh(tokens['refresh']).status_code == status.HTTP_401_UNAUTHORIZED
        new_tokens = _login_tokens(api_client, buyer_user.email)
        assert _get_me(new_tokens['access']).status_code == status.HTTP_200_OK
        assert _refresh(new_tokens['refresh']).status_code == status.HTTP_200_OK

    def test_unrelated_update_fields_save_does_not_revoke_sessions(self, api_client, buyer_user):
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
        tokens = _login_tokens(api_client, buyer_user.email)
        buyer_user.first_name = 'Renamed'
        buyer_user.save(update_fields=['first_name', 'updated_at'])
        assert BlacklistedToken.objects.filter(token__user=buyer_user).count() == 0
        assert _refresh(tokens['refresh']).status_code == status.HTTP_200_OK

    def test_queryset_update_bypasses_signal_but_status_is_still_enforced(self, api_client, buyer_user):
        """Documents the known gap: QuerySet.update() skips signals, so tokens are not blacklisted,
        but per-request and per-refresh enforcement still blocks the suspended account."""
        from apps.identity.models import User
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
        tokens = _login_tokens(api_client, buyer_user.email)

        User.objects.filter(pk=buyer_user.pk).update(status=AccountStatusChoices.SUSPENDED)
        assert BlacklistedToken.objects.filter(token__user=buyer_user).count() == 0
        assert _get_me(tokens['access']).status_code == status.HTTP_401_UNAUTHORIZED
        assert _refresh(tokens['refresh']).status_code == status.HTTP_401_UNAUTHORIZED

    def test_pending_status_behaviour_unchanged(self, api_client, buyer_user):
        tokens = _login_tokens(api_client, buyer_user.email)
        buyer_user.status = AccountStatusChoices.PENDING
        buyer_user.save()
        assert _get_me(tokens['access']).status_code == status.HTTP_200_OK
        assert _refresh(tokens['refresh']).status_code == status.HTTP_200_OK

    def test_active_user_token_refresh_keeps_standard_lifetime(self, api_client, buyer_user):
        import jwt
        from django.conf import settings
        tokens = _login_tokens(api_client, buyer_user.email)
        refresh_res = _refresh(tokens['refresh'])
        assert refresh_res.status_code == status.HTTP_200_OK
        payload = jwt.decode(refresh_res.json()['access'], settings.SECRET_KEY, algorithms=['HS256'])
        assert 3590 <= payload['exp'] - payload['iat'] <= 3610
