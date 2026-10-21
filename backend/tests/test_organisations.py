import pytest
from rest_framework import status
from apps.organisations.models import Organisation, OrganisationMembership, OrganisationRoleChoices, OrganisationTypeChoices


@pytest.mark.django_db
class TestOrganisationsAndAccessControl:

    def test_unauthenticated_organisations_access_denied(self, api_client):
        response = api_client.get('/api/v1/organisations/')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_organisation_assigns_owner_role(self, seller_auth_client, seller_user):
        payload = {
            'name': 'Bavarian Performance Tuning',
            'type': 'WORKSHOP',
            'jurisdiction': 'GB-ENG',
        }
        response = seller_auth_client.post('/api/v1/organisations/', payload, format='json')
        assert response.status_code == status.HTTP_201_CREATED

        data = response.json()
        assert data['name'] == 'Bavarian Performance Tuning'
        assert data['user_role'] == 'OWNER'
        assert data['member_count'] == 1

        org_id = data['id']
        org = Organisation.objects.get(id=org_id)
        assert org.is_member(seller_user)
        assert org.get_member_role(seller_user) == OrganisationRoleChoices.OWNER

    def test_list_organisations_filtered_by_membership(self, buyer_auth_client, seller_auth_client, test_organisation):
        # Buyer has no organisations
        buyer_resp = buyer_auth_client.get('/api/v1/organisations/')
        assert buyer_resp.status_code == status.HTTP_200_OK
        assert len(buyer_resp.json()['results']) == 0

        # Seller is owner of test_organisation
        seller_resp = seller_auth_client.get('/api/v1/organisations/')
        assert seller_resp.status_code == status.HTTP_200_OK
        results = seller_resp.json()['results']
        assert len(results) == 1
        assert results[0]['id'] == str(test_organisation.id)

    def test_organisation_detail_access_control(self, buyer_auth_client, seller_auth_client, test_organisation):
        # Non-member (buyer) receives 403 Forbidden
        denied_resp = buyer_auth_client.get(f'/api/v1/organisations/{test_organisation.id}/')
        assert denied_resp.status_code == status.HTTP_403_FORBIDDEN

        # Member (seller) receives 200 OK
        allowed_resp = seller_auth_client.get(f'/api/v1/organisations/{test_organisation.id}/')
        assert allowed_resp.status_code == status.HTTP_200_OK
        assert allowed_resp.json()['name'] == test_organisation.name

    def test_owner_can_add_member(self, seller_auth_client, test_organisation, workshop_user):
        payload = {
            'email': workshop_user.email,
            'role': 'TECHNICIAN',
        }
        response = seller_auth_client.post(
            f'/api/v1/organisations/{test_organisation.id}/members/',
            payload,
            format='json',
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data['status'] == 'success'
        assert data['member']['email'] == workshop_user.email
        assert data['member']['role'] == 'TECHNICIAN'

        # Verify in DB
        assert test_organisation.is_member(workshop_user)
        assert test_organisation.get_member_role(workshop_user) == 'TECHNICIAN'

    def test_regular_member_cannot_add_members(self, api_client, test_organisation, workshop_user, buyer_user):
        # Add workshop_user as regular MEMBER
        test_organisation.add_member(workshop_user, role=OrganisationRoleChoices.MEMBER)

        # Authenticate as workshop_user (regular member, not owner/admin)
        api_client.force_authenticate(user=workshop_user)

        payload = {
            'email': buyer_user.email,
            'role': 'MEMBER',
        }
        response = api_client.post(
            f'/api/v1/organisations/{test_organisation.id}/members/',
            payload,
            format='json',
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        data = response.json()
        assert 'Only organisation OWNER or ADMIN' in str(data)

    def test_add_nonexistent_user_rejected(self, seller_auth_client, test_organisation):
        payload = {
            'email': 'nonexistent_person_12345@example.com',
            'role': 'MEMBER',
        }
        response = seller_auth_client.post(
            f'/api/v1/organisations/{test_organisation.id}/members/',
            payload,
            format='json',
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert 'does not exist' in str(data)

    def test_cannot_assign_owner_role_directly(self, seller_auth_client, test_organisation, workshop_user):
        payload = {
            'email': workshop_user.email,
            'role': 'OWNER',
        }
        response = seller_auth_client.post(
            f'/api/v1/organisations/{test_organisation.id}/members/',
            payload,
            format='json',
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert 'Cannot assign OWNER role directly' in str(data)

    def test_platform_admin_can_view_any_organisation(self, admin_auth_client, test_organisation):
        # Platform admin is not a direct member, but has cross-tenant admin oversight
        response = admin_auth_client.get(f'/api/v1/organisations/{test_organisation.id}/')
        assert response.status_code == status.HTTP_200_OK
        assert response.json()['name'] == test_organisation.name



    def test_platform_staff_can_list_organisations(
        self, api_client, staff_user, test_organisation
    ):
        api_client.force_authenticate(user=staff_user)
        response = api_client.get('/api/v1/organisations/')

        assert response.status_code == status.HTTP_200_OK
        assert any(
            item['id'] == str(test_organisation.id)
            for item in response.json()['results']
        )

    def test_platform_staff_cannot_view_non_member_organisation_details(
        self, api_client, staff_user, test_organisation
    ):
        api_client.force_authenticate(user=staff_user)
        response = api_client.get(
            f'/api/v1/organisations/{test_organisation.id}/'
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_platform_staff_cannot_view_non_member_organisation_members(
        self, api_client, staff_user, test_organisation
    ):
        api_client.force_authenticate(user=staff_user)
        response = api_client.get(
            f'/api/v1/organisations/{test_organisation.id}/members/'
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_non_member_workshop_cannot_view_organisation_details(
        self, api_client, workshop_user, test_organisation
    ):
        api_client.force_authenticate(user=workshop_user)
        response = api_client.get(
            f'/api/v1/organisations/{test_organisation.id}/'
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_non_admin_cannot_create_internal_ops_org(self, seller_auth_client):
        payload = {
            'name': 'Internal Operations Org',
            'type': OrganisationTypeChoices.INTERNAL_OPS,
            'jurisdiction': 'GB-ENG',
        }
        response = seller_auth_client.post('/api/v1/organisations/', payload, format='json')
        assert response.status_code == status.HTTP_403_FORBIDDEN
        data = response.json()
        assert 'Only platform administrators' in str(data)

    def test_platform_admin_can_create_internal_ops_org(self, admin_auth_client):
        payload = {
            'name': 'DriverXtra Operations Team',
            'type': OrganisationTypeChoices.INTERNAL_OPS,
            'jurisdiction': 'GB-ENG',
        }
        response = admin_auth_client.post('/api/v1/organisations/', payload, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data['type'] == OrganisationTypeChoices.INTERNAL_OPS
        assert data['name'] == 'DriverXtra Operations Team'

