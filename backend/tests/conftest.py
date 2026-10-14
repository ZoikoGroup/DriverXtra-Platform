import pytest
from rest_framework.test import APIClient
from apps.identity.models import User, RoleChoices, AccountStatusChoices
from apps.organisations.models import Organisation, OrganisationMembership, OrganisationRoleChoices, OrganisationTypeChoices


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def buyer_user(db):
    user = User.objects.create_user(
        email='buyer@driverxtra.com',
        password='SecurePassword123!',
        first_name='John',
        last_name='Buyer',
        phone_number='+447000000001',
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.fixture
def seller_user(db):
    user = User.objects.create_user(
        email='seller@driverxtra.com',
        password='SecurePassword123!',
        first_name='Sarah',
        last_name='Seller',
        phone_number='+447000000002',
    )
    user.add_role(RoleChoices.SELLER)
    return user


@pytest.fixture
def workshop_user(db):
    user = User.objects.create_user(
        email='workshop@driverxtra.com',
        password='SecurePassword123!',
        first_name='David',
        last_name='Workshop',
        phone_number='+447000000003',
    )
    user.add_role(RoleChoices.WORKSHOP)
    return user


@pytest.fixture
def staff_user(db):
    user = User.objects.create_user(
        email='staff@driverxtra.com',
        password='SecurePassword123!',
        first_name='Operations',
        last_name='Staff',
        is_staff=True,
    )
    user.add_role(RoleChoices.STAFF)
    return user


@pytest.fixture
def admin_user(db):
    user = User.objects.create_superuser(
        email='admin@driverxtra.com',
        password='SuperAdminPassword123!',
        first_name='Marketplace',
        last_name='Admin',
    )
    return user


@pytest.fixture
def buyer_auth_client(buyer_user):
    client = APIClient()
    client.force_authenticate(user=buyer_user)
    return client


@pytest.fixture
def seller_auth_client(seller_user):
    client = APIClient()
    client.force_authenticate(user=seller_user)
    return client


@pytest.fixture
def admin_auth_client(admin_user):
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


@pytest.fixture
def test_organisation(db, seller_user):
    org = Organisation.objects.create(
        name='Apex Motors Ltd',
        type=OrganisationTypeChoices.DEALER_GROUP,
        jurisdiction='GB-ENG',
        created_by=seller_user,
    )
    OrganisationMembership.objects.create(
        organisation=org,
        user=seller_user,
        role=OrganisationRoleChoices.OWNER,
        is_active=True,
    )
    return org
