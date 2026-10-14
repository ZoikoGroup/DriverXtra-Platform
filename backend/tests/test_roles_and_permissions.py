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
