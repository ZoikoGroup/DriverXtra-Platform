import pytest
from rest_framework import status
from apps.identity.models import User, RoleChoices


@pytest.mark.django_db
class TestUserRegistration:

    def test_successful_registration_default_role(self, api_client):
        payload = {
            'email': 'newbuyer@example.co.uk',
            'password': 'StrongPassword2026!',
            'first_name': 'New',
            'last_name': 'User',
            'phone_number': '+447111222333',
        }
        response = api_client.post('/api/v1/auth/register/', payload, format='json')
        assert response.status_code == status.HTTP_201_CREATED

        data = response.json()
        assert data['status'] == 'success'
        assert data['user']['email'] == 'newbuyer@example.co.uk'
        assert RoleChoices.BUYER in data['user']['roles']

        # Verify user in database and password hashing
        user = User.objects.get(email='newbuyer@example.co.uk')
        assert user.check_password('StrongPassword2026!')
        assert user.password != 'StrongPassword2026!'
        assert user.password.startswith('pbkdf2_') or user.password.startswith('argon2')
        assert user.has_role(RoleChoices.BUYER)
        assert user.is_email_verified is False
        assert user.email_verified_at is None
        assert data['user']['is_email_verified'] is False

    def test_registration_with_custom_public_roles(self, api_client):
        payload = {
            'email': 'mechanic@example.co.uk',
            'password': 'StrongPassword2026!',
            'first_name': 'David',
            'last_name': 'Fixer',
            'roles': ['WORKSHOP', 'SELLER'],
        }
        response = api_client.post('/api/v1/auth/register/', payload, format='json')
        assert response.status_code == status.HTTP_201_CREATED

        data = response.json()
        roles = data['user']['roles']
        assert RoleChoices.WORKSHOP in roles
        assert RoleChoices.SELLER in roles

    def test_registration_ignores_client_supplied_email_verified_bypass(self, api_client):
        """Ensure client cannot self-verify during registration by injecting email verification fields."""
        payload = {
            'email': 'hacker@example.co.uk',
            'password': 'StrongPassword2026!',
            'first_name': 'Sneaky',
            'last_name': 'User',
            'is_email_verified': True,
            'email_verified_at': '2026-10-16T12:00:00Z',
        }
        response = api_client.post('/api/v1/auth/register/', payload, format='json')
        assert response.status_code == status.HTTP_201_CREATED

        user = User.objects.get(email='hacker@example.co.uk')
        assert user.is_email_verified is False
        assert user.email_verified_at is None

    def test_unverified_registered_user_cannot_receive_login_tokens(self, api_client):
        """Ensure newly registered unverified user cannot log in and receive JWT tokens."""
        payload = {
            'email': 'pendingverify@example.co.uk',
            'password': 'StrongPassword2026!',
            'first_name': 'Pending',
            'last_name': 'Verify',
        }
        reg_resp = api_client.post('/api/v1/auth/register/', payload, format='json')
        assert reg_resp.status_code == status.HTTP_201_CREATED
        assert 'tokens' not in reg_resp.json()

        # Attempt to login immediately without email verification
        login_resp = api_client.post('/api/v1/auth/login/', {
            'email': 'pendingverify@example.co.uk',
            'password': 'StrongPassword2026!',
        }, format='json')
        assert login_resp.status_code == status.HTTP_400_BAD_REQUEST
        login_data = login_resp.json()
        assert 'not verified' in str(login_data).lower()
        assert 'tokens' not in login_data

    def test_duplicate_email_rejected(self, api_client, buyer_user):
        payload = {
            'email': buyer_user.email,
            'password': 'AnotherPassword123!',
            'first_name': 'Copy',
            'last_name': 'Cat',
        }
        response = api_client.post('/api/v1/auth/register/', payload, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert 'already exists' in str(data)

    def test_missing_required_fields(self, api_client):
        response = api_client.post('/api/v1/auth/register/', {}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert 'email' in str(data)
        assert 'password' in str(data)

    def test_weak_password_rejected(self, api_client):
        payload = {
            'email': 'weakpass@example.com',
            'password': '123',  # Too short
        }
        response = api_client.post('/api/v1/auth/register/', payload, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert 'password' in str(data)
