import pytest
from rest_framework import status
from apps.identity.models import RoleChoices, User
from apps.onboarding.models import SellerApplication, SellerApplicationStatusChoices, BusinessTypeChoices
from apps.organisations.models import Organisation, OrganisationRoleChoices


@pytest.mark.django_db
class TestSellerOnboarding:

    def test_unauthenticated_access_denied(self, api_client):
        res = api_client.get('/api/v1/seller/application/')
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

        res = api_client.post('/api/v1/seller/application/', {})
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_application_when_none_exists(self, buyer_auth_client):
        res = buyer_auth_client.get('/api/v1/seller/application/')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data['status'] == 'none'
        assert data['application'] is None

    def test_create_draft_application(self, buyer_auth_client, buyer_user):
        payload = {
            'business_name': 'Premier Bavarian Motors',
            'business_type': BusinessTypeChoices.DEALER,
            'company_registration_number': '12345678',
            'tax_id': 'GB123456789',
            'contact_email': 'contact@premierbavarian.co.uk',
            'contact_phone': '+447111222333',
            'city': 'Manchester',
            'country': 'United Kingdom',
            'submit_now': False,
        }
        res = buyer_auth_client.post('/api/v1/seller/application/', payload, format='json')
        assert res.status_code == status.HTTP_201_CREATED
        data = res.json()
        assert data['status'] == 'success'
        assert data['application']['status'] == SellerApplicationStatusChoices.DRAFT
        assert data['application']['business_name'] == 'Premier Bavarian Motors'

    def test_update_draft_application(self, buyer_auth_client, buyer_user):
        app = SellerApplication.objects.create(
            user=buyer_user,
            business_name='Initial Name',
            business_type=BusinessTypeChoices.DEALER,
            contact_email='initial@example.com',
            contact_phone='+447000000001',
            status=SellerApplicationStatusChoices.DRAFT,
        )
        res = buyer_auth_client.patch(
            '/api/v1/seller/application/',
            {'business_name': 'Updated Automotive Group', 'city': 'Leeds'},
            format='json',
        )
        assert res.status_code == status.HTTP_200_OK
        app.refresh_from_db()
        assert app.business_name == 'Updated Automotive Group'
        assert app.city == 'Leeds'

    def test_submit_application_for_review(self, buyer_auth_client, buyer_user):
        app = SellerApplication.objects.create(
            user=buyer_user,
            business_name='Auto Trade Direct',
            business_type=BusinessTypeChoices.DEALER,
            contact_email='trade@autodirect.com',
            contact_phone='+447000000002',
            status=SellerApplicationStatusChoices.DRAFT,
        )
        res = buyer_auth_client.post('/api/v1/seller/application/submit/')
        assert res.status_code == status.HTTP_200_OK
        app.refresh_from_db()
        assert app.status == SellerApplicationStatusChoices.PENDING
        assert app.submitted_at is not None

    def test_prevent_duplicate_active_applications(self, buyer_auth_client, buyer_user):
        # Create an existing pending application
        SellerApplication.objects.create(
            user=buyer_user,
            business_name='Existing Pending Corp',
            business_type=BusinessTypeChoices.DEALER,
            contact_email='pending@corp.com',
            contact_phone='+447000000003',
            status=SellerApplicationStatusChoices.PENDING,
        )
        payload = {
            'business_name': 'Second Application Corp',
            'business_type': BusinessTypeChoices.DEALER,
            'contact_email': 'second@corp.com',
            'contact_phone': '+447000000004',
        }
        res = buyer_auth_client.post('/api/v1/seller/application/', payload, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert 'pending review' in str(res.json()).lower()

    def test_ordinary_user_cannot_access_admin_review_endpoints(self, buyer_auth_client):
        res = buyer_auth_client.get('/api/v1/admin/seller-applications/')
        assert res.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_list_and_filter_seller_applications(self, admin_auth_client, buyer_user):
        SellerApplication.objects.create(
            user=buyer_user,
            business_name='Pending Motors',
            contact_email='p@m.com',
            contact_phone='+4470001',
            status=SellerApplicationStatusChoices.PENDING,
        )
        res = admin_auth_client.get('/api/v1/admin/seller-applications/?status=PENDING')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data['count'] >= 1

    def test_admin_approve_seller_application_grants_seller_role(self, admin_auth_client, buyer_user, admin_user):
        assert not buyer_user.has_role(RoleChoices.SELLER)

        app = SellerApplication.objects.create(
            user=buyer_user,
            business_name='Approved Dealership Ltd',
            contact_email='info@approved.com',
            contact_phone='+4470002',
            status=SellerApplicationStatusChoices.PENDING,
        )
        res = admin_auth_client.post(
            f'/api/v1/admin/seller-applications/{app.id}/review/',
            {'action': 'APPROVE', 'admin_notes': 'KYB and FCA documents verified.'},
            format='json',
        )
        assert res.status_code == status.HTTP_200_OK
        app.refresh_from_db()
        assert app.status == SellerApplicationStatusChoices.APPROVED
        assert app.reviewed_by == admin_user
        assert app.reviewed_at is not None

        # Verify applicant now holds SELLER role
        buyer_user.refresh_from_db()
        assert buyer_user.has_role(RoleChoices.SELLER)

    def test_admin_approve_workshop_application_grants_both_seller_and_workshop_roles(self, admin_auth_client, buyer_user, admin_user):
        assert not buyer_user.has_role(RoleChoices.SELLER)
        assert not buyer_user.has_role(RoleChoices.WORKSHOP)

        app = SellerApplication.objects.create(
            user=buyer_user,
            business_name='Apex Performance Workshop Ltd',
            business_type=BusinessTypeChoices.WORKSHOP,
            contact_email='garage@apex.com',
            contact_phone='+44700029',
            status=SellerApplicationStatusChoices.PENDING,
        )
        res = admin_auth_client.post(
            f'/api/v1/admin/seller-applications/{app.id}/review/',
            {'action': 'APPROVE', 'admin_notes': 'Workshop facilities and certifications verified.'},
            format='json',
        )
        assert res.status_code == status.HTTP_200_OK
        app.refresh_from_db()
        assert app.status == SellerApplicationStatusChoices.APPROVED

        # Verify applicant now holds both SELLER and WORKSHOP roles
        buyer_user.refresh_from_db()
        assert buyer_user.has_role(RoleChoices.SELLER)
        assert buyer_user.has_role(RoleChoices.WORKSHOP)

    def test_admin_reject_requires_reason(self, admin_auth_client, buyer_user):
        app = SellerApplication.objects.create(
            user=buyer_user,
            business_name='Questionable Dealership',
            contact_email='bad@dealers.com',
            contact_phone='+4470003',
            status=SellerApplicationStatusChoices.PENDING,
        )
        # Attempt reject without reason
        res = admin_auth_client.post(
            f'/api/v1/admin/seller-applications/{app.id}/review/',
            {'action': 'REJECT', 'reason': ''},
            format='json',
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert 'reason' in str(res.json()).lower()

        # Reject with valid reason
        res = admin_auth_client.post(
            f'/api/v1/admin/seller-applications/{app.id}/review/',
            {'action': 'REJECT', 'reason': 'Company registration number invalid on Companies House.'},
            format='json',
        )
        assert res.status_code == status.HTTP_200_OK
        app.refresh_from_db()
        assert app.status == SellerApplicationStatusChoices.REJECTED
        assert 'Companies House' in app.rejection_reason

    def test_self_approval_protection(self, api_client):
        # Create a staff user who also applies as a seller
        staff_applicant = User.objects.create_user(
            email='staff_seller@driverxtra.com',
            password='SecurePassword123!',
            first_name='Staff',
            last_name='Applicant',
            is_staff=True,
        )
        staff_applicant.add_role(RoleChoices.STAFF)

        app = SellerApplication.objects.create(
            user=staff_applicant,
            business_name='Staff Self Dealership',
            contact_email='staff@dealers.com',
            contact_phone='+4470004',
            status=SellerApplicationStatusChoices.PENDING,
        )

        client = api_client
        client.force_authenticate(user=staff_applicant)

        res = client.post(
            f'/api/v1/admin/seller-applications/{app.id}/review/',
            {'action': 'APPROVE'},
            format='json',
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert 'cannot' in str(res.json()).lower() or 'self' in str(res.json()).lower()

    def test_resubmission_after_rejection(self, buyer_auth_client, buyer_user):
        app = SellerApplication.objects.create(
            user=buyer_user,
            business_name='Fixable Motors',
            contact_email='fixable@motors.com',
            contact_phone='+4470005',
            status=SellerApplicationStatusChoices.REJECTED,
            rejection_reason='Missing VAT certificate.',
        )
        # Update details and resubmit
        res = buyer_auth_client.patch(
            '/api/v1/seller/application/',
            {'tax_id': 'GB999888777'},
            format='json',
        )
        assert res.status_code == status.HTTP_200_OK

        res_submit = buyer_auth_client.post('/api/v1/seller/application/submit/')
        assert res_submit.status_code == status.HTTP_200_OK
        app.refresh_from_db()
        assert app.status == SellerApplicationStatusChoices.PENDING

    def test_bank_details_not_collected_or_returned(self, buyer_auth_client):
        # Attempt to submit sensitive banking information
        payload = {
            'business_name': 'Secure Automotive Ltd',
            'business_type': BusinessTypeChoices.DEALER,
            'contact_email': 'secure@dealers.com',
            'contact_phone': '+4470006',
            'city': 'London',
            'bank_account_name': 'Secret Seller Account',
            'bank_sort_code': '12-34-56',
            'bank_account_number': '98765432',
        }
        res = buyer_auth_client.post('/api/v1/seller/application/', payload, format='json')
        assert res.status_code == status.HTTP_201_CREATED
        data = res.json()
        assert data['status'] == 'success'
        app_data = data['application']

        # Verify banking fields are never returned in the API response
        assert 'bank_account_name' not in app_data
        assert 'bank_sort_code' not in app_data
        assert 'bank_account_number' not in app_data

        # Verify banking fields do not exist on the persisted model
        app_obj = SellerApplication.objects.get(id=app_data['id'])
        assert not hasattr(app_obj, 'bank_account_number')
        assert not hasattr(app_obj, 'bank_sort_code')

        # Verify GET /api/v1/seller/application/ also contains zero banking fields
        res_get = buyer_auth_client.get('/api/v1/seller/application/')
        assert res_get.status_code == status.HTTP_200_OK
        get_data = res_get.json()['application']
        assert 'bank_account_number' not in get_data
        assert 'bank_sort_code' not in get_data

    def test_organisation_membership_and_authorization(self, buyer_auth_client, buyer_user, seller_user):
        # Create an organisation owned by seller_user where buyer_user is NOT a member
        org_unauthorized = Organisation.objects.create(name='Bavarian Heritage Motors', created_by=seller_user)
        org_unauthorized.add_member(seller_user, role=OrganisationRoleChoices.OWNER)

        # Buyer attempts to attach unauthorized organisation to their application
        payload = {
            'business_name': 'Unauthorized Dealership App',
            'organisation': str(org_unauthorized.id),
            'contact_email': 'buyer@driverxtra.com',
            'contact_phone': '+4470007',
        }
        res = buyer_auth_client.post('/api/v1/seller/application/', payload, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert 'not an active member' in str(res.json()).lower()

        # Buyer is added to an organisation, but only as a regular MEMBER (not OWNER or ADMIN)
        org_member_only = Organisation.objects.create(name='Technicians Union Ltd', created_by=seller_user)
        org_member_only.add_member(buyer_user, role=OrganisationRoleChoices.MEMBER)

        payload['organisation'] = str(org_member_only.id)
        res = buyer_auth_client.post('/api/v1/seller/application/', payload, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert 'owner or admin' in str(res.json()).lower()

        # Buyer creates their own organisation and is granted OWNER role
        org_owner = Organisation.objects.create(name='Buyer Official Motors', created_by=buyer_user)
        org_owner.add_member(buyer_user, role=OrganisationRoleChoices.OWNER)

        payload['organisation'] = str(org_owner.id)
        res = buyer_auth_client.post('/api/v1/seller/application/', payload, format='json')
        assert res.status_code == status.HTTP_201_CREATED
        assert res.json()['application']['organisation'] == str(org_owner.id)

    def test_individual_seller_without_organisation_preserved(self, buyer_auth_client):
        # Individual trader applying with organisation=None
        payload = {
            'business_name': 'Solo Independent Trader',
            'business_type': BusinessTypeChoices.INDIVIDUAL_TRADER,
            'contact_email': 'solo@trader.com',
            'contact_phone': '+4470008',
            'city': 'Birmingham',
            'organisation': None,
        }
        res = buyer_auth_client.post('/api/v1/seller/application/', payload, format='json')
        assert res.status_code == status.HTTP_201_CREATED
        assert res.json()['application']['organisation'] is None

    def test_requested_roles_validation_rejects_invalid_roles(self, buyer_auth_client):
        # Attempt to request ADMIN, STAFF, or BUYER roles
        for invalid_role in ['ADMIN', 'STAFF', 'BUYER', 'SUPERUSER']:
            res = buyer_auth_client.post(
                '/api/v1/seller/application/',
                {'business_name': 'Hacker Motors', 'requested_roles': [invalid_role]},
                format='json',
            )
            assert res.status_code == status.HTTP_400_BAD_REQUEST, f"Expected 400 for role {invalid_role}"
            assert 'invalid requested role' in str(res.json()).lower()

    def test_requested_roles_validation_rejects_empty_list(self, buyer_auth_client):
        res = buyer_auth_client.post(
            '/api/v1/seller/application/',
            {'business_name': 'Empty Roles Motors', 'requested_roles': []},
            format='json',
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert 'at least one role' in str(res.json()).lower()

    def test_requested_roles_validation_rejects_duplicates(self, buyer_auth_client):
        res = buyer_auth_client.post(
            '/api/v1/seller/application/',
            {'business_name': 'Duplicate Roles Motors', 'requested_roles': ['SELLER', 'SELLER']},
            format='json',
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert 'duplicate' in str(res.json()).lower()

    def test_requested_roles_workshop_only_approval_grants_only_workshop(self, buyer_auth_client, admin_auth_client, buyer_user):
        # Create draft with WORKSHOP role only
        create_res = buyer_auth_client.post(
            '/api/v1/seller/application/',
            {
                'business_name': 'Precision Workshop Services',
                'business_type': BusinessTypeChoices.LTD,
                'requested_roles': ['WORKSHOP'],
                'contact_name': 'John Mechanic',
                'contact_email': 'mechanic@precision.com',
                'contact_phone': '+447000123',
                'business_address_line1': '10 Pit Lane',
                'business_city': 'Silverstone',
                'business_postal_code': 'NN12 8TN',
            },
            format='json',
        )
        assert create_res.status_code == status.HTTP_201_CREATED
        app_id = create_res.json()['application']['id']

        # Submit application
        sub_res = buyer_auth_client.post('/api/v1/seller/application/submit/')
        assert sub_res.status_code == status.HTTP_200_OK

        # Admin approves application
        apprv_res = admin_auth_client.post(
            f'/api/v1/admin/seller-applications/{app_id}/review/',
            {'action': 'APPROVE', 'admin_notes': 'Verified workshop capabilities.'},
            format='json',
        )
        assert apprv_res.status_code == status.HTTP_200_OK

        # Verify applicant holds WORKSHOP but NOT SELLER role
        buyer_user.refresh_from_db()
        assert buyer_user.has_role(RoleChoices.WORKSHOP) is True
        assert buyer_user.has_role(RoleChoices.SELLER) is False

    def test_requested_roles_both_roles_approval_grants_both(self, buyer_auth_client, admin_auth_client, buyer_user):
        # Create draft requesting both SELLER and WORKSHOP
        create_res = buyer_auth_client.post(
            '/api/v1/seller/application/',
            {
                'business_name': 'Full Service Dealership Ltd',
                'business_type': BusinessTypeChoices.LTD,
                'requested_roles': ['SELLER', 'WORKSHOP'],
                'contact_name': 'Alice Director',
                'contact_email': 'alice@fullservice.com',
                'contact_phone': '+447000999',
                'business_address_line1': '1 Motor Way',
                'business_city': 'Coventry',
                'business_postal_code': 'CV1 1AA',
            },
            format='json',
        )
        assert create_res.status_code == status.HTTP_201_CREATED
        app_id = create_res.json()['application']['id']

        # Submit & approve
        buyer_auth_client.post('/api/v1/seller/application/submit/')
        apprv_res = admin_auth_client.post(
            f'/api/v1/admin/seller-applications/{app_id}/review/',
            {'action': 'APPROVE', 'admin_notes': 'Both roles approved.'},
            format='json',
        )
        assert apprv_res.status_code == status.HTTP_200_OK

        buyer_user.refresh_from_db()
        assert buyer_user.has_role(RoleChoices.SELLER) is True
        assert buyer_user.has_role(RoleChoices.WORKSHOP) is True

    def test_legacy_application_approval_preserves_expected_roles(self, admin_auth_client):
        from apps.onboarding.models import SellerApplication, SellerApplicationStatusChoices
        # 1. Legacy pending application with business_type=WORKSHOP and empty requested_roles
        legacy_workshop_user = User.objects.create_user(
            email='legacy.wksh@driverxtra.com',
            password='Password123!',
            is_email_verified=True,
        )
        legacy_app_wksh = SellerApplication.objects.create(
            user=legacy_workshop_user,
            business_name='Legacy Workshop Garage',
            business_type=BusinessTypeChoices.WORKSHOP,
            requested_roles=[],
            contact_email='legacy.wksh@driverxtra.com',
            contact_phone='+447000111',
            status=SellerApplicationStatusChoices.PENDING,
        )
        res = admin_auth_client.post(
            f'/api/v1/admin/seller-applications/{legacy_app_wksh.id}/review/',
            {'action': 'APPROVE'},
            format='json',
        )
        assert res.status_code == status.HTTP_200_OK
        legacy_workshop_user.refresh_from_db()
        assert legacy_workshop_user.has_role(RoleChoices.SELLER) is True
        assert legacy_workshop_user.has_role(RoleChoices.WORKSHOP) is True

        # 2. Legacy pending application with business_type=LTD and empty requested_roles
        legacy_seller_user = User.objects.create_user(
            email='legacy.seller@driverxtra.com',
            password='Password123!',
            is_email_verified=True,
        )
        legacy_app_seller = SellerApplication.objects.create(
            user=legacy_seller_user,
            business_name='Legacy Car Sales Ltd',
            business_type=BusinessTypeChoices.LTD,
            requested_roles=[],
            contact_email='legacy.seller@driverxtra.com',
            contact_phone='+447000222',
            status=SellerApplicationStatusChoices.PENDING,
        )
        res = admin_auth_client.post(
            f'/api/v1/admin/seller-applications/{legacy_app_seller.id}/review/',
            {'action': 'APPROVE'},
            format='json',
        )
        assert res.status_code == status.HTTP_200_OK
        legacy_seller_user.refresh_from_db()
        assert legacy_seller_user.has_role(RoleChoices.SELLER) is True
        assert legacy_seller_user.has_role(RoleChoices.WORKSHOP) is False

    def test_approval_audit_event_contains_granted_roles(self, buyer_auth_client, admin_auth_client, buyer_user):
        from platform_core.audit.models import AuditLog
        create_res = buyer_auth_client.post(
            '/api/v1/seller/application/',
            {
                'business_name': 'Audited Workshop Hub',
                'business_type': BusinessTypeChoices.LTD,
                'requested_roles': ['WORKSHOP'],
                'contact_name': 'Audited Contact',
                'contact_email': 'audited@workshop.com',
                'contact_phone': '+447000333',
                'business_address_line1': '1 Audit Road',
                'business_city': 'London',
                'business_postal_code': 'EC1A 1BB',
            },
            format='json',
        )
        app_id = create_res.json()['application']['id']
        buyer_auth_client.post('/api/v1/seller/application/submit/')
        admin_auth_client.post(
            f'/api/v1/admin/seller-applications/{app_id}/review/',
            {'action': 'APPROVE'},
            format='json',
        )

        audit_event = AuditLog.objects.filter(
            event_type='seller.application.approved',
            resource_id=str(app_id),
        ).latest('created_at')
        assert audit_event is not None
        assert audit_event.metadata.get('granted_roles') == ['WORKSHOP']

