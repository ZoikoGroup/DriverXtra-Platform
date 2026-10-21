import pytest
from rest_framework import status
from apps.identity.models import User, RoleChoices
from apps.organisations.models import (
    Organisation,
    OrganisationMembership,
    OrganisationRoleChoices,
    OrganisationTypeChoices,
)
from apps.catalogue.models import (
    VehicleMake,
    VehicleModel,
    VehicleVariant,
    PartCategory,
    FuelTypeChoices,
    TransmissionChoices,
)
from apps.marketplace.models import (
    VehicleListing,
    SparePartListing,
    ListingStatusChoices,
)


@pytest.fixture
def make_bmw(db):
    return VehicleMake.objects.create(name='BMW', country_of_origin='Germany')


@pytest.fixture
def model_3series(db, make_bmw):
    return VehicleModel.objects.create(make=make_bmw, name='3 Series', year_start=2019)


@pytest.fixture
def variant_330i(db, model_3series):
    return VehicleVariant.objects.create(
        model=model_3series,
        name='330i M Sport',
        year=2021,
        engine_code='B48B20',
        fuel_type=FuelTypeChoices.PETROL,
        transmission=TransmissionChoices.AUTOMATIC,
        power_bhp=258,
    )


@pytest.fixture
def brakes_category(db):
    return PartCategory.objects.create(name='Braking Systems', slug='braking-systems')


@pytest.mark.django_db
class TestMarketplaceWorkflow:

    # =========================================================================
    # 1. Seller Submission & Ownership Isolation
    # =========================================================================

    def test_seller_can_submit_vehicle_for_approval(self, seller_auth_client, seller_user, make_bmw, model_3series, variant_330i):
        payload = {
            'title': '2021 BMW 330i M Sport Saloon',
            'make': str(make_bmw.id),
            'model': str(model_3series.id),
            'variant': str(variant_330i.id),
            'year': 2021,
            'registration_number': 'EA21 XYZ',
            'vin': 'WBA5R1C51M8B12345',
            'mileage': 28500,
            'fuel_type': 'PETROL',
            'transmission': 'AUTOMATIC',
            'body_type': 'Saloon',
            'price': '24950.00',
            'currency': 'GBP',
            'condition': 'EXCELLENT',
            'description': 'One previous owner, full main dealer service history.',
            'location_city': 'Manchester',
            'location_postcode': 'M1 4BT',
        }
        response = seller_auth_client.post('/api/v1/marketplace/vehicles/', payload, format='json')
        assert response.status_code == status.HTTP_201_CREATED

        data = response.json()
        assert data['status'] == ListingStatusChoices.PENDING_APPROVAL
        assert data['title'] == '2021 BMW 330i M Sport Saloon'
        assert data['seller'] == str(seller_user.id)
        assert data['masked_vin'] == '***********B12345'
        assert data['masked_registration'] == 'EA** ***'

        # Verify database record
        listing = VehicleListing.objects.get(id=data['id'])
        assert listing.seller == seller_user
        assert listing.status == ListingStatusChoices.PENDING_APPROVAL
        assert listing.vin == 'WBA5R1C51M8B12345'

    def test_seller_can_submit_spare_part_for_approval(self, seller_auth_client, seller_user, brakes_category, variant_330i):
        payload = {
            'name': 'Brembo Front Brake Discs Pair (348mm)',
            'brand': 'Brembo',
            'mpn': '09.C398.13',
            'oem_numbers': ['34116860911', '34116860912'],
            'category': str(brakes_category.id),
            'description': 'High carbon, UV coated vented brake discs.',
            'price': '185.00',
            'currency': 'GBP',
            'stock_quantity': 4,
            'condition': 'NEW',
            'compatible_variants': [str(variant_330i.id)],
            'compatibility_notes': 'Only for models with standard 348mm M Sport brakes.',
        }
        response = seller_auth_client.post('/api/v1/marketplace/parts/', payload, format='json')
        assert response.status_code == status.HTTP_201_CREATED

        data = response.json()
        assert data['status'] == ListingStatusChoices.PENDING_APPROVAL
        assert data['brand'] == 'Brembo'
        assert data['mpn'] == '09.C398.13'
        assert data['seller'] == str(seller_user.id)

        part = SparePartListing.objects.get(id=data['id'])
        assert part.seller == seller_user
        assert part.compatible_variants.filter(id=variant_330i.id).exists()

    def test_submission_field_validation(self, seller_auth_client, make_bmw, model_3series):
        # Negative price
        bad_price = {
            'title': 'Test Vehicle',
            'make': str(make_bmw.id),
            'model': str(model_3series.id),
            'year': 2020,
            'price': '-500.00',
        }
        res = seller_auth_client.post('/api/v1/marketplace/vehicles/', bad_price, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert 'price' in str(res.json())

        # Invalid year
        bad_year = {
            'title': 'Test Vehicle',
            'make': str(make_bmw.id),
            'model': str(model_3series.id),
            'year': 1850,
            'price': '15000.00',
        }
        res = seller_auth_client.post('/api/v1/marketplace/vehicles/', bad_year, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert 'year' in str(res.json())

    def test_seller_cannot_link_unauthorized_organisation(self, seller_auth_client, make_bmw, model_3series):
        # Create an organisation where seller is NOT an owner or admin
        other_org = Organisation.objects.create(name='Foreign Dealership Ltd', type=OrganisationTypeChoices.DEALER_GROUP)

        payload = {
            'title': 'Unauthorized Listing',
            'organisation': str(other_org.id),
            'make': str(make_bmw.id),
            'model': str(model_3series.id),
            'year': 2021,
            'price': '20000.00',
        }
        res = seller_auth_client.post('/api/v1/marketplace/vehicles/', payload, format='json')
        assert res.status_code == status.HTTP_403_FORBIDDEN
        assert 'OWNER or ADMIN' in str(res.json())

    def test_seller_isolation_cannot_view_or_edit_other_sellers_submissions(
        self, seller_auth_client, buyer_auth_client, seller_user, make_bmw, model_3series
    ):
        # Create another verified seller
        other_seller = User.objects.create_user(
            email='other_seller@driverxtra.com',
            password='SecurePassword123!',
            is_email_verified=True,
        )
        other_seller.add_role(RoleChoices.SELLER)
        from rest_framework.test import APIClient
        other_client = APIClient()
        other_client.force_authenticate(user=other_seller)

        # Create a listing owned by seller_user
        listing = VehicleListing.objects.create(
            seller=seller_user,
            title='Sarah Private Car',
            make=make_bmw,
            model=model_3series,
            year=2020,
            price=18000,
            status=ListingStatusChoices.PENDING_APPROVAL,
        )

        # Another seller attempts to retrieve seller endpoint -> 404 NOT FOUND
        res = other_client.get(f'/api/v1/marketplace/vehicles/{listing.id}/')
        assert res.status_code == status.HTTP_404_NOT_FOUND

        # Another seller attempts to patch -> 404 NOT FOUND
        patch_res = other_client.patch(f'/api/v1/marketplace/vehicles/{listing.id}/', {'price': '10000.00'}, format='json')
        assert patch_res.status_code == status.HTTP_404_NOT_FOUND

        # Buyer without seller role is denied access -> 403 FORBIDDEN
        buyer_res = buyer_auth_client.get(f'/api/v1/marketplace/vehicles/{listing.id}/')
        assert buyer_res.status_code == status.HTTP_403_FORBIDDEN

    # =========================================================================
    # 2. Admin Review Queue & Moderation Actions
    # =========================================================================

    def test_ordinary_seller_cannot_access_admin_queues_or_approve_directly(self, seller_auth_client, seller_user, make_bmw, model_3series):
        listing = VehicleListing.objects.create(
            seller=seller_user,
            title='Pending Car',
            make=make_bmw,
            model=model_3series,
            year=2021,
            price=22000,
            status=ListingStatusChoices.PENDING_APPROVAL,
        )

        # Seller calls admin review queue
        res = seller_auth_client.get('/api/v1/marketplace/admin/vehicles/')
        assert res.status_code == status.HTTP_403_FORBIDDEN

        # Seller attempts to call review endpoint
        review_res = seller_auth_client.post(f'/api/v1/marketplace/admin/vehicles/{listing.id}/review/', {'action': 'APPROVE'}, format='json')
        assert review_res.status_code == status.HTTP_403_FORBIDDEN

        # Seller attempts to directly patch status
        patch_res = seller_auth_client.patch(f'/api/v1/marketplace/vehicles/{listing.id}/', {'status': 'APPROVED'}, format='json')
        listing.refresh_from_db()
        assert listing.status == ListingStatusChoices.PENDING_APPROVAL

    def test_admin_can_approve_vehicle_listing(self, admin_auth_client, admin_user, seller_user, make_bmw, model_3series):
        listing = VehicleListing.objects.create(
            seller=seller_user,
            title='Vehicle For Approval',
            make=make_bmw,
            model=model_3series,
            year=2022,
            price=29000,
            status=ListingStatusChoices.PENDING_APPROVAL,
        )

        review_payload = {
            'action': 'APPROVE',
            'admin_notes': 'Verified registration and provenance.',
        }
        res = admin_auth_client.post(f'/api/v1/marketplace/admin/vehicles/{listing.id}/review/', review_payload, format='json')
        assert res.status_code == status.HTTP_200_OK

        listing.refresh_from_db()
        assert listing.status == ListingStatusChoices.APPROVED
        assert listing.reviewed_by == admin_user
        assert listing.reviewed_at is not None

    def test_admin_reject_requires_reason(self, admin_auth_client, seller_user, make_bmw, model_3series):
        listing = VehicleListing.objects.create(
            seller=seller_user,
            title='Vehicle To Reject',
            make=make_bmw,
            model=model_3series,
            year=2022,
            price=29000,
            status=ListingStatusChoices.PENDING_APPROVAL,
        )

        # Reject without reason should fail
        res = admin_auth_client.post(f'/api/v1/marketplace/admin/vehicles/{listing.id}/review/', {'action': 'REJECT'}, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert 'rejection_reason' in str(res.json())

        # Reject with reason succeeds
        res_ok = admin_auth_client.post(f'/api/v1/marketplace/admin/vehicles/{listing.id}/review/', {
            'action': 'REJECT',
            'rejection_reason': 'Odometer image is blurry, please provide clearer photo.',
        }, format='json')
        assert res_ok.status_code == status.HTTP_200_OK

        listing.refresh_from_db()
        assert listing.status == ListingStatusChoices.REJECTED
        assert 'blurry' in listing.rejection_reason

    def test_seller_can_resubmit_rejected_listing(self, seller_auth_client, seller_user, make_bmw, model_3series):
        listing = VehicleListing.objects.create(
            seller=seller_user,
            title='Rejected Vehicle',
            make=make_bmw,
            model=model_3series,
            year=2021,
            price=25000,
            status=ListingStatusChoices.REJECTED,
            rejection_reason='Fix typo in registration plate.',
        )

        resubmit_res = seller_auth_client.post(f'/api/v1/marketplace/vehicles/{listing.id}/resubmit/', format='json')
        assert resubmit_res.status_code == status.HTTP_200_OK

        listing.refresh_from_db()
        assert listing.status == ListingStatusChoices.PENDING_APPROVAL
        assert listing.rejection_reason == ""

    # =========================================================================
    # 3. Buyer Browsing & Isolation of Unapproved Items
    # =========================================================================

    def test_buyer_browse_returns_only_approved_inventory(self, api_client, seller_user, make_bmw, model_3series, brakes_category):
        # 1 Approved vehicle
        veh_approved = VehicleListing.objects.create(
            seller=seller_user,
            title='Approved 2021 BMW 330i',
            make=make_bmw,
            model=model_3series,
            year=2021,
            price=24000,
            fuel_type='PETROL',
            transmission='AUTOMATIC',
            location_city='London',
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )

        # 1 Pending vehicle
        veh_pending = VehicleListing.objects.create(
            seller=seller_user,
            title='Pending 2022 BMW 330i',
            make=make_bmw,
            model=model_3series,
            year=2022,
            price=28000,
            status=ListingStatusChoices.PENDING_APPROVAL,
            is_active=True,
        )

        # 1 Rejected vehicle
        veh_rejected = VehicleListing.objects.create(
            seller=seller_user,
            title='Rejected BMW 330i',
            make=make_bmw,
            model=model_3series,
            year=2020,
            price=19000,
            status=ListingStatusChoices.REJECTED,
            is_active=True,
        )

        # Buyer lists vehicles
        res = api_client.get('/api/v1/marketplace/browse/vehicles/')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        ids = [item['id'] for item in (data if isinstance(data, list) else data['results'])]

        assert str(veh_approved.id) in ids
        assert str(veh_pending.id) not in ids
        assert str(veh_rejected.id) not in ids

        # Buyer attempts direct retrieve of unapproved vehicle
        res_pending_detail = api_client.get(f'/api/v1/marketplace/browse/vehicles/{veh_pending.id}/')
        assert res_pending_detail.status_code == status.HTTP_404_NOT_FOUND

    def test_buyer_spare_parts_search_and_filtering(self, api_client, seller_user, brakes_category, variant_330i):
        # Approved part 1: Brembo
        part_brembo = SparePartListing.objects.create(
            seller=seller_user,
            name='Brembo High Performance Pads',
            brand='Brembo',
            mpn='P 06 088',
            category=brakes_category,
            price=65.00,
            stock_quantity=10,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )
        part_brembo.compatible_variants.add(variant_330i)

        # Approved part 2: Bosch
        part_bosch = SparePartListing.objects.create(
            seller=seller_user,
            name='Bosch QuietCast Rotors',
            brand='Bosch',
            mpn='0986479C12',
            category=brakes_category,
            price=120.00,
            stock_quantity=5,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )

        # Search by brand
        res_brand = api_client.get('/api/v1/marketplace/browse/parts/?brand=Brembo')
        assert res_brand.status_code == status.HTTP_200_OK
        data_brand = res_brand.json()
        brand_ids = [p['id'] for p in (data_brand if isinstance(data_brand, list) else data_brand['results'])]
        assert str(part_brembo.id) in brand_ids
        assert str(part_bosch.id) not in brand_ids

        # Search by variant compatibility
        res_compat = api_client.get(f'/api/v1/marketplace/browse/parts/?variant_id={variant_330i.id}')
        assert res_compat.status_code == status.HTTP_200_OK
        data_compat = res_compat.json()
        compat_ids = [p['id'] for p in (data_compat if isinstance(data_compat, list) else data_compat.get('results', []))]
        assert str(part_brembo.id) in compat_ids
        assert str(part_bosch.id) not in compat_ids

        # Search by price filter
        res_price = api_client.get('/api/v1/marketplace/browse/parts/?price_max=80.00')
        assert res_price.status_code == status.HTTP_200_OK
        data_price = res_price.json()
        price_ids = [p['id'] for p in (data_price if isinstance(data_price, list) else data_price.get('results', []))]
        assert str(part_brembo.id) in price_ids
        assert str(part_bosch.id) not in price_ids

    # =========================================================================
    # 4. End-to-End Draft Lifecycle & Approval Verification
    # =========================================================================

    def test_vehicle_draft_lifecycle_and_approval_workflow(
        self, seller_auth_client, admin_auth_client, api_client, seller_user, admin_user, make_bmw, model_3series, variant_330i
    ):
        # 1. Seller saves vehicle as DRAFT
        draft_payload = {
            'title': '2021 BMW 330i Draft Listing',
            'make': str(make_bmw.id),
            'model': str(model_3series.id),
            'variant': str(variant_330i.id),
            'year': 2021,
            'price': '23500.00',
            'status': 'DRAFT',
        }
        create_res = seller_auth_client.post('/api/v1/marketplace/vehicles/', draft_payload, format='json')
        assert create_res.status_code == status.HTTP_201_CREATED
        listing_id = create_res.json()['id']
        assert create_res.json()['status'] == ListingStatusChoices.DRAFT

        # 2. Draft does NOT appear in public buyer browsing
        browse_res = api_client.get('/api/v1/marketplace/browse/vehicles/')
        browse_ids = [v['id'] for v in (browse_res.json() if isinstance(browse_res.json(), list) else browse_res.json()['results'])]
        assert listing_id not in browse_ids

        # 3. Draft does NOT appear in pending admin queue
        admin_queue = admin_auth_client.get('/api/v1/marketplace/admin/vehicles/?status=PENDING_APPROVAL')
        queue_ids = [v['id'] for v in (admin_queue.json() if isinstance(admin_queue.json(), list) else admin_queue.json()['results'])]
        assert listing_id not in queue_ids

        # 4. Seller submits the draft for approval
        submit_res = seller_auth_client.post(f'/api/v1/marketplace/vehicles/{listing_id}/submit/', format='json')
        assert submit_res.status_code == status.HTTP_200_OK
        assert submit_res.json()['listing']['status'] == ListingStatusChoices.PENDING_APPROVAL

        # 5. Admin now sees vehicle in review queue
        admin_queue_after = admin_auth_client.get('/api/v1/marketplace/admin/vehicles/?status=PENDING_APPROVAL')
        queue_after_ids = [v['id'] for v in (admin_queue_after.json() if isinstance(admin_queue_after.json(), list) else admin_queue_after.json()['results'])]
        assert listing_id in queue_after_ids

        # 6. Admin approves vehicle
        approve_res = admin_auth_client.post(f'/api/v1/marketplace/admin/vehicles/{listing_id}/review/', {'action': 'APPROVE'}, format='json')
        assert approve_res.status_code == status.HTTP_200_OK
        data = approve_res.json()['listing']
        assert data['status'] == ListingStatusChoices.APPROVED
        assert data['reviewed_by_name'] == admin_user.full_name
        assert data['reviewed_at'] is not None

        # 7. Approved vehicle now appears in public buyer browsing
        browse_approved = api_client.get('/api/v1/marketplace/browse/vehicles/')
        approved_ids = [v['id'] for v in (browse_approved.json() if isinstance(browse_approved.json(), list) else browse_approved.json()['results'])]
        assert listing_id in approved_ids

    def test_part_draft_lifecycle_and_approval_workflow(
        self, seller_auth_client, admin_auth_client, api_client, seller_user, admin_user, brakes_category
    ):
        # 1. Seller saves spare part as DRAFT
        draft_payload = {
            'name': 'Brembo Track Day Pads',
            'brand': 'Brembo',
            'mpn': 'P-06-088T',
            'category': str(brakes_category.id),
            'price': '110.00',
            'stock_quantity': 6,
            'status': 'DRAFT',
        }
        create_res = seller_auth_client.post('/api/v1/marketplace/parts/', draft_payload, format='json')
        assert create_res.status_code == status.HTTP_201_CREATED
        part_id = create_res.json()['id']
        assert create_res.json()['status'] == ListingStatusChoices.DRAFT

        # 2. Draft does NOT appear in public buyer parts browsing
        browse_res = api_client.get('/api/v1/marketplace/browse/parts/')
        browse_ids = [p['id'] for p in (browse_res.json() if isinstance(browse_res.json(), list) else browse_res.json().get('results', []))]
        assert part_id not in browse_ids

        # 3. Seller submits draft
        submit_res = seller_auth_client.post(f'/api/v1/marketplace/parts/{part_id}/submit/', format='json')
        assert submit_res.status_code == status.HTTP_200_OK
        assert submit_res.json()['listing']['status'] == ListingStatusChoices.PENDING_APPROVAL

        # 4. Admin approves part
        approve_res = admin_auth_client.post(f'/api/v1/marketplace/admin/parts/{part_id}/review/', {'action': 'APPROVE'}, format='json')
        assert approve_res.status_code == status.HTTP_200_OK
        assert approve_res.json()['listing']['status'] == ListingStatusChoices.APPROVED

        # 5. Part appears in public buyer browsing
        browse_after = api_client.get('/api/v1/marketplace/browse/parts/?mpn=P-06-088T')
        after_ids = [p['id'] for p in (browse_after.json() if isinstance(browse_after.json(), list) else browse_after.json().get('results', []))]
        assert part_id in after_ids

    def test_admin_part_reject_requires_reason(self, admin_auth_client, seller_user, brakes_category):
        part = SparePartListing.objects.create(
            seller=seller_user,
            name='Faulty Sensor',
            brand='Generic',
            mpn='GEN-001',
            category=brakes_category,
            price=15.00,
            status=ListingStatusChoices.PENDING_APPROVAL,
        )

        # Reject without reason fails
        bad_res = admin_auth_client.post(f'/api/v1/marketplace/admin/parts/{part.id}/review/', {'action': 'REJECT'}, format='json')
        assert bad_res.status_code == status.HTTP_400_BAD_REQUEST

        # Reject with reason succeeds
        ok_res = admin_auth_client.post(f'/api/v1/marketplace/admin/parts/{part.id}/review/', {
            'action': 'REJECT',
            'rejection_reason': 'Unverified OEM equivalence; please provide OEM cross-reference.',
        }, format='json')
        assert ok_res.status_code == status.HTTP_200_OK
        part.refresh_from_db()
        assert part.status == ListingStatusChoices.REJECTED
        assert 'Unverified OEM' in part.rejection_reason

    def test_self_approval_prevention(self, admin_auth_client, admin_user, make_bmw, model_3series):
        # Admin user is NOT a superuser
        admin_user.is_superuser = False
        admin_user.save()

        # Admin lists their own vehicle
        own_listing = VehicleListing.objects.create(
            seller=admin_user,
            title='Admin Personal Car',
            make=make_bmw,
            model=model_3series,
            year=2021,
            price=21000,
            status=ListingStatusChoices.PENDING_APPROVAL,
        )

        res = admin_auth_client.post(f'/api/v1/marketplace/admin/vehicles/{own_listing.id}/review/', {'action': 'APPROVE'}, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert 'Self-approval violation' in str(res.json())

    # =========================================================================
    # 5. Phase 4: Material Edits Demotion & Organisation Listing Rules
    # =========================================================================

    def test_editing_material_field_on_approved_vehicle_resets_to_pending_approval(
        self, seller_auth_client, seller_user, make_bmw, model_3series
    ):
        listing = VehicleListing.objects.create(
            seller=seller_user,
            title='2021 BMW 330i M Sport',
            make=make_bmw,
            model=model_3series,
            year=2021,
            price=25000,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )

        # Edit price (material field)
        patch_res = seller_auth_client.patch(
            f'/api/v1/marketplace/vehicles/{listing.id}/',
            {'price': '23995.00'},
            format='json',
        )
        assert patch_res.status_code == status.HTTP_200_OK
        data = patch_res.json()
        assert data['status'] == ListingStatusChoices.PENDING_APPROVAL

        listing.refresh_from_db()
        assert listing.status == ListingStatusChoices.PENDING_APPROVAL
        assert float(listing.price) == 23995.00

    def test_stock_only_change_on_approved_part_keeps_approved_status(
        self, seller_auth_client, seller_user, brakes_category
    ):
        part = SparePartListing.objects.create(
            seller=seller_user,
            name='Brembo Caliper Left',
            brand='Brembo',
            mpn='CAL-001',
            category=brakes_category,
            price=150.00,
            stock_quantity=5,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )

        # Stock adjustment via dedicated stock endpoint
        stock_res = seller_auth_client.post(
            f'/api/v1/marketplace/parts/{part.id}/stock/',
            {'delta': 7, 'reason': 'ADJUSTMENT', 'note': 'Restocked'},
            format='json',
        )
        assert stock_res.status_code == status.HTTP_200_OK
        data = stock_res.json()
        assert data['status'] == 'success'
        assert data['listing']['status'] == ListingStatusChoices.APPROVED
        assert data['listing']['stock_quantity'] == 12

        part.refresh_from_db()
        assert part.status == ListingStatusChoices.APPROVED
        assert part.stock_quantity == 12

    def test_patch_part_with_stock_quantity_returns_structured_400(
        self, seller_auth_client, seller_user, brakes_category
    ):
        part = SparePartListing.objects.create(
            seller=seller_user,
            name='Brembo Caliper Left',
            brand='Brembo',
            mpn='CAL-001',
            category=brakes_category,
            price=150.00,
            stock_quantity=5,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )

        patch_res = seller_auth_client.patch(
            f'/api/v1/marketplace/parts/{part.id}/',
            {'stock_quantity': 12},
            format='json',
        )
        assert patch_res.status_code == status.HTTP_400_BAD_REQUEST
        body = patch_res.json()
        assert body['status'] == 'error'
        assert body['code'] == 400
        assert 'stock_quantity' in str(body)


    def test_editing_material_field_on_approved_part_resets_to_pending_approval(
        self, seller_auth_client, seller_user, brakes_category
    ):
        part = SparePartListing.objects.create(
            seller=seller_user,
            name='Brembo Caliper Right',
            brand='Brembo',
            mpn='CAL-002',
            category=brakes_category,
            price=150.00,
            stock_quantity=5,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )

        # Update price (material field)
        patch_res = seller_auth_client.patch(
            f'/api/v1/marketplace/parts/{part.id}/',
            {'price': '165.00'},
            format='json',
        )
        assert patch_res.status_code == status.HTTP_200_OK
        data = patch_res.json()
        assert data['status'] == ListingStatusChoices.PENDING_APPROVAL

        part.refresh_from_db()
        assert part.status == ListingStatusChoices.PENDING_APPROVAL

    def test_non_owner_admin_org_member_cannot_create_org_listing(
        self, api_client, test_organisation, workshop_user, make_bmw, model_3series, variant_330i
    ):
        # Add workshop_user as regular MEMBER in test_organisation
        test_organisation.add_member(workshop_user, role=OrganisationRoleChoices.MEMBER)
        # Give workshop_user SELLER role so they have marketplace access
        workshop_user.add_role(RoleChoices.SELLER)
        api_client.force_authenticate(user=workshop_user)

        payload = {
            'organisation': str(test_organisation.id),
            'title': 'Org BMW 330i',
            'make': str(make_bmw.id),
            'model': str(model_3series.id),
            'variant': str(variant_330i.id),
            'year': 2021,
            'price': '22000.00',
        }
        res = api_client.post('/api/v1/marketplace/vehicles/', payload, format='json')
        assert res.status_code == status.HTTP_403_FORBIDDEN
        assert 'OWNER or ADMIN' in str(res.json())

    def test_non_owner_admin_org_member_cannot_edit_org_listing(
        self, api_client, seller_user, test_organisation, workshop_user, make_bmw, model_3series
    ):
        # Create listing under org by owner (seller_user)
        listing = VehicleListing.objects.create(
            seller=seller_user,
            organisation=test_organisation,
            title='Org Fleet Car',
            make=make_bmw,
            model=model_3series,
            year=2021,
            price=20000,
            status=ListingStatusChoices.PENDING_APPROVAL,
        )

        # Workshop user is MEMBER of test_organisation
        test_organisation.add_member(workshop_user, role=OrganisationRoleChoices.MEMBER)
        workshop_user.add_role(RoleChoices.SELLER)
        api_client.force_authenticate(user=workshop_user)

        # Attempt to edit listing
        res = api_client.patch(
            f'/api/v1/marketplace/vehicles/{listing.id}/',
            {'price': '19500.00'},
            format='json',
        )
        assert res.status_code == status.HTTP_403_FORBIDDEN

    def test_org_admin_can_edit_org_listing_even_if_not_creator(
        self, api_client, seller_user, test_organisation, workshop_user, make_bmw, model_3series
    ):
        listing = VehicleListing.objects.create(
            seller=seller_user,
            organisation=test_organisation,
            title='Org Fleet Car 2',
            make=make_bmw,
            model=model_3series,
            year=2021,
            price=20000,
            status=ListingStatusChoices.PENDING_APPROVAL,
        )

        # Workshop user is ADMIN of test_organisation
        test_organisation.add_member(workshop_user, role=OrganisationRoleChoices.ADMIN)
        workshop_user.add_role(RoleChoices.SELLER)
        api_client.force_authenticate(user=workshop_user)

        res = api_client.patch(
            f'/api/v1/marketplace/vehicles/{listing.id}/',
            {'price': '19000.00'},
            format='json',
        )
        assert res.status_code == status.HTTP_200_OK
        listing.refresh_from_db()
        assert float(listing.price) == 19000.00

    def test_resubmit_rules_for_organisation_listings(
        self, api_client, seller_user, test_organisation, workshop_user, make_bmw, model_3series
    ):
        listing = VehicleListing.objects.create(
            seller=seller_user,
            organisation=test_organisation,
            title='Org Rejected Car',
            make=make_bmw,
            model=model_3series,
            year=2021,
            price=20000,
            status=ListingStatusChoices.REJECTED,
            rejection_reason='Missing documentation',
        )

        test_organisation.add_member(workshop_user, role=OrganisationRoleChoices.MEMBER)
        workshop_user.add_role(RoleChoices.SELLER)
        api_client.force_authenticate(user=workshop_user)

        # Regular member cannot resubmit
        res_denied = api_client.post(f'/api/v1/marketplace/vehicles/{listing.id}/resubmit/', format='json')
        assert res_denied.status_code == status.HTTP_403_FORBIDDEN

        # Upgrade workshop_user to ADMIN
        membership = test_organisation.memberships.get(user=workshop_user)
        membership.role = OrganisationRoleChoices.ADMIN
        membership.save()

        # Org ADMIN can resubmit
        res_allowed = api_client.post(f'/api/v1/marketplace/vehicles/{listing.id}/resubmit/', format='json')
        assert res_allowed.status_code == status.HTTP_200_OK
        listing.refresh_from_db()
        assert listing.status == ListingStatusChoices.PENDING_APPROVAL

