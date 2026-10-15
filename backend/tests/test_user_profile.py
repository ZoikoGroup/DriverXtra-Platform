import pytest
from rest_framework import status


@pytest.mark.django_db
class TestUserProfile:

    def test_unauthenticated_profile_access_denied(self, api_client):
        response = api_client.get('/api/v1/users/me/')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_authenticated_profile_retrieval(self, buyer_auth_client, buyer_user):
        response = buyer_auth_client.get('/api/v1/users/me/')
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data['id'] == str(buyer_user.id)
        assert data['email'] == buyer_user.email
        assert data['first_name'] == 'John'
        assert data['last_name'] == 'Buyer'
        assert data['phone_number'] == '+447000000001'
        assert 'BUYER' in data['roles']
        assert 'organisations' in data

    def test_permitted_profile_update(self, buyer_auth_client, buyer_user):
        payload = {
            'first_name': 'Johnny',
            'last_name': 'Updated',
            'phone_number': '+447999888777',
        }
        response = buyer_auth_client.patch('/api/v1/users/me/', payload, format='json')
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data['first_name'] == 'Johnny'
        assert data['last_name'] == 'Updated'
        assert data['phone_number'] == '+447999888777'

        buyer_user.refresh_from_db()
        assert buyer_user.first_name == 'Johnny'
        assert buyer_user.last_name == 'Updated'
        assert buyer_user.phone_number == '+447999888777'

    def test_restricted_profile_fields_cannot_be_escalated(self, buyer_auth_client, buyer_user):
        payload = {
            'email': 'hacked@driverxtra.com',
            'is_staff': True,
            'is_superuser': True,
            'status': 'DEACTIVATED',
            'roles': ['ADMIN'],
        }
        response = buyer_auth_client.patch('/api/v1/users/me/', payload, format='json')
        assert response.status_code == status.HTTP_200_OK

        buyer_user.refresh_from_db()
        # Verify read-only fields were not altered
        assert buyer_user.email == 'buyer@driverxtra.com'
        assert buyer_user.is_staff is False
        assert buyer_user.is_superuser is False
        assert buyer_user.status == 'ACTIVE'
        assert 'ADMIN' not in buyer_user.roles
