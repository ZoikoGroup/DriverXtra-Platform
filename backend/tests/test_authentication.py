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
