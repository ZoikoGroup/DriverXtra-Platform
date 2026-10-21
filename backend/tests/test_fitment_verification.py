import uuid
import pytest
from decimal import Decimal
from rest_framework import status
from apps.identity.models import User, RoleChoices
from apps.organisations.models import Organisation, OrganisationMembership, OrganisationRoleChoices, OrganisationTypeChoices
from apps.catalogue.models import (
    VehicleMake,
    VehicleModel,
    VehicleVariant,
    PartCategory,
    Part,
    PartCompatibility,
    FitmentTypeChoices,
    FuelTypeChoices,
)
from apps.marketplace.models import (
    SparePartListing,
    ListingStatusChoices,
)
from apps.garage.models import GarageVehicle
from apps.marketplace.fitment import (
    evaluate_listing_fitment,
    batch_evaluate_listings_fitment,
    get_conflicting_variants,
    FITMENT_STATUS_VERIFIED,
    FITMENT_STATUS_CONDITIONAL,
    FITMENT_STATUS_CONFLICT,
    FITMENT_STATUS_SELLER_CLAIMED,
    FITMENT_STATUS_UNKNOWN,
    FITMENT_SOURCE_CATALOGUE,
    FITMENT_SOURCE_SELLER,
    FITMENT_SOURCE_NONE,
)
from platform_core.audit.models import AuditLog


@pytest.fixture
def fitment_env(db, seller_user):
    # Makes & Models
    bmw = VehicleMake.objects.create(name='BMW')
    bmw_model = VehicleModel.objects.create(make=bmw, name='3 Series', year_start=2019)

    variant_bmw_m_sport = VehicleVariant.objects.create(
        model=bmw_model,
        name='330i M Sport',
        year=2021,
        engine_code='B48B20',
        fuel_type=FuelTypeChoices.PETROL,
    )
    variant_bmw_base = VehicleVariant.objects.create(
        model=bmw_model,
        name='320i Base',
        year=2020,
        engine_code='B48B20',
        fuel_type=FuelTypeChoices.PETROL,
    )
    variant_bmw_diesel = VehicleVariant.objects.create(
        model=bmw_model,
        name='320d EfficientDynamics',
        year=2020,
        engine_code='B47D20',
        fuel_type=FuelTypeChoices.DIESEL,
    )
    variant_audi = VehicleVariant.objects.create(
        model=VehicleModel.objects.create(make=VehicleMake.objects.create(name='Audi'), name='A4', year_start=2016),
        name='2.0 TFSI S Line',
        year=2020,
        fuel_type=FuelTypeChoices.PETROL,
    )
    variant_mercedes = VehicleVariant.objects.create(
        model=VehicleModel.objects.create(make=VehicleMake.objects.create(name='Mercedes'), name='C Class', year_start=2018),
        name='C200 AMG Line',
        year=2021,
        fuel_type=FuelTypeChoices.PETROL,
    )

    category = PartCategory.objects.create(name='Braking', slug='braking')

    # Canonical Parts
    part_calipers = Part.objects.create(
        name='Brembo M Sport Caliper Set',
        brand='Brembo',
        mpn='CALIPER-BM-01',
        category=category,
    )
    part_universal = Part.objects.create(
        name='Universal Brake Bleeder Kit',
        brand='Generic',
        mpn='BLEEDER-UNI-01',
        category=category,
        is_universal=True,
    )

    # Compatibilities:
    # 1. CONFIRMED_FIT for 330i M Sport
    PartCompatibility.objects.create(
        part=part_calipers,
        vehicle_variant=variant_bmw_m_sport,
        fitment_type=FitmentTypeChoices.CONFIRMED_FIT,
        qualifications='OEM Direct fit for 330i M Sport models.',
    )
    # 2. CONDITIONAL_FIT for 320i Base
    PartCompatibility.objects.create(
        part=part_calipers,
        vehicle_variant=variant_bmw_base,
        fitment_type=FitmentTypeChoices.CONDITIONAL_FIT,
        qualifications='Requires 18-inch wheels or larger for caliper clearance.',
    )
    # 3. DOES_NOT_FIT for Mercedes C200
    PartCompatibility.objects.create(
        part=part_calipers,
        vehicle_variant=variant_mercedes,
        fitment_type=FitmentTypeChoices.DOES_NOT_FIT,
        qualifications='BMW bolt pattern incompatible with Mercedes carrier.',
    )
    # 4. UNKNOWN record for 320d Diesel
    PartCompatibility.objects.create(
        part=part_calipers,
        vehicle_variant=variant_bmw_diesel,
        fitment_type=FitmentTypeChoices.UNKNOWN,
        qualifications='Engineering verification pending on diesel carrier brackets.',
    )

    return {
        'bmw_m_sport': variant_bmw_m_sport,
        'bmw_base': variant_bmw_base,
        'bmw_diesel': variant_bmw_diesel,
        'audi': variant_audi,
        'mercedes': variant_mercedes,
        'category': category,
        'part_calipers': part_calipers,
        'part_universal': part_universal,
    }


@pytest.mark.django_db
class TestEvaluateListingFitmentService:
    """Test suite for evaluate_listing_fitment service logic."""

    def test_all_fitment_statuses_and_sources(self, fitment_env, seller_user):
        category = fitment_env['category']
        part_calipers = fitment_env['part_calipers']
        v_m_sport = fitment_env['bmw_m_sport']
        v_base = fitment_env['bmw_base']
        v_mercedes = fitment_env['mercedes']
        v_diesel = fitment_env['bmw_diesel']
        v_audi = fitment_env['audi']

        listing = SparePartListing.objects.create(
            seller=seller_user,
            category=category,
            catalogue_part=part_calipers,
            name='Brembo Big Brake Calipers',
            brand='Brembo',
            mpn='CALIPER-BM-01',
            price=Decimal('450.00'),
            compatibility_notes='Seller notes: tested on road track.',
        )
        # Seller claims all 5 variants
        listing.compatible_variants.set([v_m_sport, v_base, v_mercedes, v_diesel, v_audi])

        evaluations = evaluate_listing_fitment(listing, [v_m_sport, v_base, v_mercedes, v_diesel, v_audi])
        eval_map = {e['variant_id']: e for e in evaluations}

        # 1. CONFIRMED_FIT -> VERIFIED
        assert eval_map[str(v_m_sport.id)]['status'] == FITMENT_STATUS_VERIFIED
        assert eval_map[str(v_m_sport.id)]['source'] == FITMENT_SOURCE_CATALOGUE
        assert 'OEM Direct fit' in eval_map[str(v_m_sport.id)]['qualifications']

        # 2. CONDITIONAL_FIT -> CONDITIONAL
        assert eval_map[str(v_base.id)]['status'] == FITMENT_STATUS_CONDITIONAL
        assert eval_map[str(v_base.id)]['source'] == FITMENT_SOURCE_CATALOGUE
        assert '18-inch wheels' in eval_map[str(v_base.id)]['qualifications']

        # 3. DOES_NOT_FIT -> CONFLICT (Catalogue overrides seller claim!)
        assert eval_map[str(v_mercedes.id)]['status'] == FITMENT_STATUS_CONFLICT
        assert eval_map[str(v_mercedes.id)]['source'] == FITMENT_SOURCE_CATALOGUE
        assert 'incompatible' in eval_map[str(v_mercedes.id)]['qualifications']

        # 4. UNKNOWN catalogue record -> falls back to SELLER_CLAIMED if claimed by seller
        assert eval_map[str(v_diesel.id)]['status'] == FITMENT_STATUS_SELLER_CLAIMED
        assert eval_map[str(v_diesel.id)]['source'] == FITMENT_SOURCE_SELLER

        # 5. No catalogue record -> SELLER_CLAIMED because seller claimed it
        assert eval_map[str(v_audi.id)]['status'] == FITMENT_STATUS_SELLER_CLAIMED
        assert eval_map[str(v_audi.id)]['source'] == FITMENT_SOURCE_SELLER

    def test_unknown_status_when_neither_catalogue_nor_seller_claim(self, fitment_env, seller_user):
        category = fitment_env['category']
        part_calipers = fitment_env['part_calipers']
        v_audi = fitment_env['audi']

        listing = SparePartListing.objects.create(
            seller=seller_user,
            category=category,
            catalogue_part=part_calipers,
            name='Brembo Big Brake Calipers',
            brand='Brembo',
            mpn='CALIPER-BM-01',
            price=Decimal('450.00'),
        )
        # Listing does NOT claim Audi
        evaluations = evaluate_listing_fitment(listing, [v_audi])
        assert len(evaluations) == 1
        assert evaluations[0]['status'] == FITMENT_STATUS_UNKNOWN
        assert evaluations[0]['source'] == FITMENT_SOURCE_NONE

    def test_universal_catalogue_part_without_record_returns_conditional(self, fitment_env, seller_user):
        category = fitment_env['category']
        part_universal = fitment_env['part_universal']
        v_audi = fitment_env['audi']

        listing = SparePartListing.objects.create(
            seller=seller_user,
            category=category,
            catalogue_part=part_universal,
            name='Universal Bleeder Tool',
            brand='Generic',
            mpn='BLEEDER-UNI-01',
            price=Decimal('25.00'),
        )
        evaluations = evaluate_listing_fitment(listing, [v_audi])
        assert len(evaluations) == 1
        assert evaluations[0]['status'] == FITMENT_STATUS_CONDITIONAL
        assert evaluations[0]['source'] == FITMENT_SOURCE_CATALOGUE
        assert 'universal' in evaluations[0]['qualifications'].lower()


@pytest.mark.django_db
class TestSubmissionGate:
    """Test suite for fitment verification submission gates."""

    def test_create_non_draft_with_conflict_rejected(self, seller_auth_client, fitment_env):
        category = fitment_env['category']
        part_calipers = fitment_env['part_calipers']
        v_mercedes = fitment_env['mercedes']  # DOES_NOT_FIT

        payload = {
            'name': 'Brembo Calipers',
            'brand': 'Brembo',
            'mpn': 'CALIPER-BM-01',
            'category': str(category.id),
            'catalogue_part': str(part_calipers.id),
            'price': '450.00',
            'compatible_variants': [str(v_mercedes.id)],
            'status': 'PENDING_APPROVAL',
        }
        res = seller_auth_client.post('/api/v1/marketplace/parts/', payload, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        data = res.json()
        assert data['status'] == 'error'
        assert 'conflicts' in data['details']
        assert len(data['details']['conflicts']) == 1
        assert data['details']['conflicts'][0]['variant_id'] == str(v_mercedes.id)

        # Confirm listing was NOT created
        assert not SparePartListing.objects.filter(mpn='CALIPER-BM-01').exists()

        # Confirm denied audit entry was recorded
        audit = AuditLog.objects.filter(action='listing:submit', reason_code='FITMENT_CONFLICT').first()
        assert audit is not None
        assert str(v_mercedes.id) in audit.metadata['conflicting_variant_ids']

    def test_draft_with_conflict_can_be_saved_but_not_submitted(self, seller_auth_client, fitment_env, seller_user):
        category = fitment_env['category']
        part_calipers = fitment_env['part_calipers']
        v_mercedes = fitment_env['mercedes']

        # 1. Save draft with conflict -> allowed
        payload = {
            'name': 'Brembo Calipers Draft',
            'brand': 'Brembo',
            'mpn': 'CALIPER-BM-01-DRAFT',
            'category': str(category.id),
            'catalogue_part': str(part_calipers.id),
            'price': '450.00',
            'compatible_variants': [str(v_mercedes.id)],
            'status': 'DRAFT',
        }
        res = seller_auth_client.post('/api/v1/marketplace/parts/', payload, format='json')
        assert res.status_code == status.HTTP_201_CREATED
        listing_id = res.json()['id']
        listing = SparePartListing.objects.get(id=listing_id)
        assert listing.status == ListingStatusChoices.DRAFT

        # Verify fitment_verification & summary on draft
        assert res.json()['fitment_summary']['conflict'] == 1

        # 2. Try to submit draft -> blocked with 400
        submit_res = seller_auth_client.post(f'/api/v1/marketplace/parts/{listing_id}/submit/')
        assert submit_res.status_code == status.HTTP_400_BAD_REQUEST
        assert submit_res.json()['status'] == 'error'
        assert 'conflicts' in submit_res.json()['details']

        listing.refresh_from_db()
        assert listing.status == ListingStatusChoices.DRAFT

        # 3. Fix the claim by removing the conflicting variant
        v_m_sport = fitment_env['bmw_m_sport']
        patch_res = seller_auth_client.patch(
            f'/api/v1/marketplace/parts/{listing_id}/',
            {'compatible_variants': [str(v_m_sport.id)]},
            format='json',
        )
        assert patch_res.status_code == status.HTTP_200_OK

        # 4. Submit again -> successful!
        submit_res2 = seller_auth_client.post(f'/api/v1/marketplace/parts/{listing_id}/submit/')
        assert submit_res2.status_code == status.HTTP_200_OK
        listing.refresh_from_db()
        assert listing.status == ListingStatusChoices.PENDING_APPROVAL

    def test_resubmit_rejected_listing_with_conflict_blocked(self, seller_auth_client, fitment_env, seller_user):
        category = fitment_env['category']
        part_calipers = fitment_env['part_calipers']
        v_mercedes = fitment_env['mercedes']

        listing = SparePartListing.objects.create(
            seller=seller_user,
            category=category,
            catalogue_part=part_calipers,
            name='Brembo Rejected',
            brand='Brembo',
            mpn='CALIPER-BM-REJ',
            price=Decimal('450.00'),
            status=ListingStatusChoices.REJECTED,
        )
        listing.compatible_variants.set([v_mercedes])

        res = seller_auth_client.post(f'/api/v1/marketplace/parts/{listing.id}/resubmit/')
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        listing.refresh_from_db()
        assert listing.status == ListingStatusChoices.REJECTED

    def test_approved_listing_material_edit_introducing_conflict_rejected(self, seller_auth_client, fitment_env, seller_user):
        category = fitment_env['category']
        part_calipers = fitment_env['part_calipers']
        v_m_sport = fitment_env['bmw_m_sport']
        v_mercedes = fitment_env['mercedes']

        listing = SparePartListing.objects.create(
            seller=seller_user,
            category=category,
            catalogue_part=part_calipers,
            name='Brembo Approved',
            brand='Brembo',
            mpn='CALIPER-BM-APP',
            price=Decimal('450.00'),
            status=ListingStatusChoices.APPROVED,
        )
        listing.compatible_variants.set([v_m_sport])

        # Attempt to patch compatible_variants to add Mercedes (DOES_NOT_FIT)
        patch_res = seller_auth_client.patch(
            f'/api/v1/marketplace/parts/{listing.id}/',
            {'compatible_variants': [str(v_m_sport.id), str(v_mercedes.id)]},
            format='json',
        )
        assert patch_res.status_code == status.HTTP_400_BAD_REQUEST
        data = patch_res.json()
        assert data['status'] == 'error'

        # Listing remains UNCHANGED and still APPROVED
        listing.refresh_from_db()
        assert listing.status == ListingStatusChoices.APPROVED
        assert list(listing.compatible_variants.values_list('id', flat=True)) == [v_m_sport.id]


@pytest.mark.django_db
class TestAdminModerationFitmentVerification:
    """Test suite for Admin review with fitment conflicts."""

    def test_admin_approve_blocked_on_conflict(self, admin_auth_client, fitment_env, seller_user):
        category = fitment_env['category']
        part_calipers = fitment_env['part_calipers']
        v_mercedes = fitment_env['mercedes']

        listing = SparePartListing.objects.create(
            seller=seller_user,
            category=category,
            catalogue_part=part_calipers,
            name='Brembo Pending',
            brand='Brembo',
            mpn='CALIPER-BM-PEND',
            price=Decimal('450.00'),
            status=ListingStatusChoices.PENDING_APPROVAL,
        )
        listing.compatible_variants.set([v_mercedes])

        # Attempt to APPROVE
        res = admin_auth_client.post(
            f'/api/v1/marketplace/admin/parts/{listing.id}/review/',
            {'action': 'APPROVE'},
            format='json',
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        listing.refresh_from_db()
        assert listing.status == ListingStatusChoices.PENDING_APPROVAL

    def test_admin_reject_and_request_changes_allowed_with_conflict(self, admin_auth_client, fitment_env, seller_user):
        category = fitment_env['category']
        part_calipers = fitment_env['part_calipers']
        v_mercedes = fitment_env['mercedes']

        listing = SparePartListing.objects.create(
            seller=seller_user,
            category=category,
            catalogue_part=part_calipers,
            name='Brembo To Reject',
            brand='Brembo',
            mpn='CALIPER-BM-REJ2',
            price=Decimal('450.00'),
            status=ListingStatusChoices.PENDING_APPROVAL,
        )
        listing.compatible_variants.set([v_mercedes])

        # REQUEST_CHANGES
        res = admin_auth_client.post(
            f'/api/v1/marketplace/admin/parts/{listing.id}/review/',
            {'action': 'REQUEST_CHANGES', 'rejection_reason': 'Please remove Mercedes variant.'},
            format='json',
        )
        assert res.status_code == status.HTTP_200_OK
        listing.refresh_from_db()
        assert listing.status == ListingStatusChoices.CHANGES_REQUESTED


@pytest.mark.django_db
class TestBuyerFitsVehicleBrowse:
    """Test suite for buyer ?fits_vehicle=<id> parameter on public browse endpoints."""

    def test_fits_vehicle_unauthenticated_returns_401(self, api_client):
        random_id = uuid.uuid4()
        res = api_client.get(f'/api/v1/marketplace/browse/parts/?fits_vehicle={random_id}')
        assert res.status_code == status.HTTP_401_UNAUTHORIZED
        assert res.json()['status'] == 'error'

    def test_fits_vehicle_invalid_uuid_returns_400(self, buyer_auth_client):
        res = buyer_auth_client.get('/api/v1/marketplace/browse/parts/?fits_vehicle=invalid-uuid-format')
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert res.json()['status'] == 'error'

    def test_fits_vehicle_other_users_vehicle_returns_404(self, buyer_auth_client, seller_user, fitment_env):
        # Create garage vehicle owned by seller
        other_vehicle = GarageVehicle.objects.create(
            user=seller_user,
            make='BMW',
            model='3 Series',
            year=2021,
            vehicle_variant=fitment_env['bmw_m_sport'],
        )
        # Buyer attempts to query with seller's vehicle
        res = buyer_auth_client.get(f'/api/v1/marketplace/browse/parts/?fits_vehicle={other_vehicle.id}')
        assert res.status_code == status.HTTP_404_NOT_FOUND

    def test_fits_vehicle_archived_vehicle_returns_404(self, buyer_auth_client, buyer_user, fitment_env):
        archived_vehicle = GarageVehicle.objects.create(
            user=buyer_user,
            make='BMW',
            model='3 Series',
            year=2021,
            vehicle_variant=fitment_env['bmw_m_sport'],
            is_archived=True,
        )
        res = buyer_auth_client.get(f'/api/v1/marketplace/browse/parts/?fits_vehicle={archived_vehicle.id}')
        assert res.status_code == status.HTTP_404_NOT_FOUND

    def test_fits_vehicle_without_variant_returns_unknown_for_all(self, buyer_auth_client, buyer_user, seller_user, fitment_env):
        category = fitment_env['category']
        part_calipers = fitment_env['part_calipers']
        listing = SparePartListing.objects.create(
            seller=seller_user,
            category=category,
            catalogue_part=part_calipers,
            name='Brembo Calipers',
            brand='Brembo',
            mpn='CALIPER-BM-PUB',
            price=Decimal('450.00'),
            status=ListingStatusChoices.APPROVED,
        )

        unlinked_vehicle = GarageVehicle.objects.create(
            user=buyer_user,
            make='BMW',
            model='Custom Build',
            year=2022,
            vehicle_variant=None,  # No variant linked
        )

        res = buyer_auth_client.get(f'/api/v1/marketplace/browse/parts/?fits_vehicle={unlinked_vehicle.id}')
        assert res.status_code == status.HTTP_200_OK
        results = res.json()
        items = results.get('results', results)
        assert len(items) >= 1
        item = [i for i in items if i['id'] == str(listing.id)][0]
        assert item['fitment']['status'] == FITMENT_STATUS_UNKNOWN
        assert item['fitment']['qualifications'] == 'vehicle not linked to catalogue'
        assert item['fitment']['source'] == FITMENT_SOURCE_NONE

    def test_fits_vehicle_evaluates_correctly_and_does_not_filter(self, buyer_auth_client, buyer_user, seller_user, fitment_env):
        category = fitment_env['category']
        part_calipers = fitment_env['part_calipers']
        v_m_sport = fitment_env['bmw_m_sport']

        # Create approved listing
        listing = SparePartListing.objects.create(
            seller=seller_user,
            category=category,
            catalogue_part=part_calipers,
            name='Brembo Calipers',
            brand='Brembo',
            mpn='CALIPER-BM-VERIF',
            price=Decimal('450.00'),
            status=ListingStatusChoices.APPROVED,
        )
        listing.compatible_variants.set([v_m_sport])

        buyer_vehicle = GarageVehicle.objects.create(
            user=buyer_user,
            make='BMW',
            model='3 Series',
            year=2021,
            vehicle_variant=v_m_sport,
            registration_plate='AB21 CDE',
            vin='WBA330I1234567890',
        )

        # 1. List endpoint with fits_vehicle
        res = buyer_auth_client.get(f'/api/v1/marketplace/browse/parts/?fits_vehicle={buyer_vehicle.id}')
        assert res.status_code == status.HTTP_200_OK
        results = res.json()
        items = results.get('results', results)
        item = [i for i in items if i['id'] == str(listing.id)][0]

        assert item['fitment']['status'] == FITMENT_STATUS_VERIFIED
        assert item['fitment']['source'] == FITMENT_SOURCE_CATALOGUE
        assert 'OEM Direct fit' in item['fitment']['qualifications']

        # Confirm NO garage sensitive fields leaked (no plate, no VIN)
        assert 'vin' not in item
        assert 'registration_plate' not in item
        assert 'AB21 CDE' not in str(res.content)
        assert 'WBA330I1234567890' not in str(res.content)

        # 2. Detail endpoint with fits_vehicle
        detail_res = buyer_auth_client.get(f'/api/v1/marketplace/browse/parts/{listing.id}/?fits_vehicle={buyer_vehicle.id}')
        assert detail_res.status_code == status.HTTP_200_OK
        detail_data = detail_res.json()
        assert detail_data['fitment']['status'] == FITMENT_STATUS_VERIFIED
        assert detail_data['fitment']['source'] == FITMENT_SOURCE_CATALOGUE

    def test_anonymous_requests_without_fits_vehicle_unchanged(self, api_client, seller_user, fitment_env):
        category = fitment_env['category']
        part_calipers = fitment_env['part_calipers']
        listing = SparePartListing.objects.create(
            seller=seller_user,
            category=category,
            catalogue_part=part_calipers,
            name='Public Part',
            brand='Brembo',
            mpn='CALIPER-BM-PUB2',
            price=Decimal('100.00'),
            status=ListingStatusChoices.APPROVED,
        )

        # Anonymous list
        res = api_client.get('/api/v1/marketplace/browse/parts/')
        assert res.status_code == status.HTTP_200_OK
        items = res.json().get('results', res.json())
        item = [i for i in items if i['id'] == str(listing.id)][0]
        assert 'fitment' not in item

        # Anonymous detail
        detail_res = api_client.get(f'/api/v1/marketplace/browse/parts/{listing.id}/')
        assert detail_res.status_code == status.HTTP_200_OK
        assert 'fitment' not in detail_res.json()


@pytest.mark.django_db
class TestQueryCountAndPerformance:
    """Ensure constant fitment database queries when browsing parts with ?fits_vehicle=."""

    def test_fits_vehicle_batch_query_count(self, buyer_auth_client, buyer_user, seller_user, fitment_env, django_assert_num_queries):
        category = fitment_env['category']
        part_calipers = fitment_env['part_calipers']
        v_m_sport = fitment_env['bmw_m_sport']

        buyer_vehicle = GarageVehicle.objects.create(
            user=buyer_user,
            make='BMW',
            model='3 Series',
            year=2021,
            vehicle_variant=v_m_sport,
        )

        # Create 10 approved listings linked to the same or different catalogue parts
        for i in range(10):
            SparePartListing.objects.create(
                seller=seller_user,
                category=category,
                catalogue_part=part_calipers,
                name=f'Brembo Calipers {i}',
                brand='Brembo',
                mpn=f'CALIPER-BM-N{i}',
                price=Decimal('200.00') + Decimal(i),
                status=ListingStatusChoices.APPROVED,
            )

        # Measure query count for 10 items
        # Should be constant: User/Auth + GarageVehicle + Listings page + Count + Prefetch + PartCompatibility
        res = buyer_auth_client.get(f'/api/v1/marketplace/browse/parts/?fits_vehicle={buyer_vehicle.id}')
        assert res.status_code == status.HTTP_200_OK
        items = res.json().get('results', res.json())
        assert len(items) >= 10
        for item in items:
            assert 'fitment' in item
            assert item['fitment']['status'] == FITMENT_STATUS_VERIFIED


@pytest.mark.django_db
class TestPermissionsOnCompatibleVariants:
    """Ensure strict permission isolation on compatible_variants and catalogue_part modifications."""

    def test_other_seller_cannot_modify_compatible_variants(self, fitment_env, seller_user, api_client):
        # Create second seller
        other_seller = User.objects.create_user(
            email='other_seller@driverxtra.com',
            password='SecurePassword123!',
            first_name='Other',
            last_name='Seller',
            is_email_verified=True,
        )
        other_seller.add_role(RoleChoices.SELLER)

        category = fitment_env['category']
        part_calipers = fitment_env['part_calipers']
        v_m_sport = fitment_env['bmw_m_sport']
        v_base = fitment_env['bmw_base']

        listing = SparePartListing.objects.create(
            seller=seller_user,
            category=category,
            catalogue_part=part_calipers,
            name='Seller 1 Part',
            brand='Brembo',
            mpn='CALIPER-S1-01',
            price=Decimal('300.00'),
            status=ListingStatusChoices.DRAFT,
        )
        listing.compatible_variants.set([v_m_sport])

        # Other seller attempts to patch listing
        api_client.force_authenticate(user=other_seller)
        res = api_client.patch(
            f'/api/v1/marketplace/parts/{listing.id}/',
            {'compatible_variants': [str(v_base.id)]},
            format='json',
        )
        # Should be 404 or 403 (isolation hides it or denies it)
        assert res.status_code in (status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN)
        listing.refresh_from_db()
        assert list(listing.compatible_variants.values_list('id', flat=True)) == [v_m_sport.id]

    def test_readonly_org_member_cannot_modify_compatible_variants(self, fitment_env, seller_user, api_client):
        # Create organisation
        org = Organisation.objects.create(
            name='Fleet Parts Hub',
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

        # Create analyst member
        analyst = User.objects.create_user(
            email='analyst@driverxtra.com',
            password='SecurePassword123!',
            first_name='Analyst',
            last_name='User',
            is_email_verified=True,
        )
        analyst.add_role(RoleChoices.SELLER)
        OrganisationMembership.objects.create(
            organisation=org,
            user=analyst,
            role=OrganisationRoleChoices.ANALYST,
            is_active=True,
        )

        category = fitment_env['category']
        part_calipers = fitment_env['part_calipers']
        v_m_sport = fitment_env['bmw_m_sport']
        v_base = fitment_env['bmw_base']

        org_listing = SparePartListing.objects.create(
            seller=seller_user,
            organisation=org,
            category=category,
            catalogue_part=part_calipers,
            name='Org Part',
            brand='Brembo',
            mpn='CALIPER-ORG-01',
            price=Decimal('350.00'),
            status=ListingStatusChoices.PENDING_APPROVAL,
        )
        org_listing.compatible_variants.set([v_m_sport])

        # Analyst attempts to patch listing
        api_client.force_authenticate(user=analyst)
        res = api_client.patch(
            f'/api/v1/marketplace/parts/{org_listing.id}/',
            {'compatible_variants': [str(v_base.id)]},
            format='json',
        )
        assert res.status_code == status.HTTP_403_FORBIDDEN
        org_listing.refresh_from_db()
        assert list(org_listing.compatible_variants.values_list('id', flat=True)) == [v_m_sport.id]


@pytest.mark.django_db
class TestSellerCompatibilityUpdateAndPersistence:
    """Verify that seller inventory PATCH endpoint properly supports adding, updating,
    preserving, and clearing compatible_variants and compatibility_notes, and that
    fitment_verification and fitment_summary reflect the current saved compatibility.
    """

    def test_listing_without_variants_returns_empty_fitment_verification(self, fitment_env, seller_user, api_client):
        """Simulate an approved listing created without compatible variants (like the Bosch listing)."""
        category = fitment_env['category']
        part_calipers = fitment_env['part_calipers']
        api_client.force_authenticate(user=seller_user)

        listing = SparePartListing.objects.create(
            seller=seller_user,
            category=category,
            catalogue_part=part_calipers,
            name='front disc brake pad set',
            brand='Bosch',
            mpn='F 002 H23 683',
            price=Decimal('119.99'),
            status=ListingStatusChoices.APPROVED,
        )

        res = api_client.get(f'/api/v1/marketplace/parts/{listing.id}/')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data['compatible_variants'] == []
        assert data['compatibility_notes'] == ''
        assert data['fitment_verification'] == []
        assert data['fitment_summary'] == {
            'verified': 0,
            'conditional': 0,
            'seller_claimed': 0,
            'conflict': 0,
        }

    def test_patch_only_price_or_description_preserves_existing_compatibility(self, fitment_env, seller_user, api_client):
        """Updating price or description must not unintentionally clear compatibility."""
        category = fitment_env['category']
        part_calipers = fitment_env['part_calipers']
        v_m_sport = fitment_env['bmw_m_sport']
        api_client.force_authenticate(user=seller_user)

        listing = SparePartListing.objects.create(
            seller=seller_user,
            category=category,
            catalogue_part=part_calipers,
            name='front disc brake pad set',
            brand='Bosch',
            mpn='F 002 H23 683',
            price=Decimal('119.99'),
            compatibility_notes='M-Sport brakes only',
            status=ListingStatusChoices.APPROVED,
        )
        listing.compatible_variants.set([v_m_sport])

        # Patch only price
        res = api_client.patch(
            f'/api/v1/marketplace/parts/{listing.id}/',
            {'price': '129.99'},
            format='json',
        )
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert str(v_m_sport.id) in [str(vid) for vid in data['compatible_variants']]
        assert data['compatibility_notes'] == 'M-Sport brakes only'
        assert len(data['fitment_verification']) == 1
        assert data['fitment_verification'][0]['status'] == FITMENT_STATUS_VERIFIED
        assert data['fitment_summary']['verified'] == 1

        # Patch only description
        res2 = api_client.patch(
            f'/api/v1/marketplace/parts/{listing.id}/',
            {'description': 'Updated technical description'},
            format='json',
        )
        assert res2.status_code == status.HTTP_200_OK
        data2 = res2.json()
        assert str(v_m_sport.id) in [str(vid) for vid in data2['compatible_variants']]
        assert data2['compatibility_notes'] == 'M-Sport brakes only'
        assert data2['fitment_summary']['verified'] == 1

    def test_patch_adds_compatible_variant_and_updates_fitment_verification(self, fitment_env, seller_user, api_client):
        """Seller edits listing to declare compatible variant and notes, updating fitment verification."""
        category = fitment_env['category']
        part_calipers = fitment_env['part_calipers']
        v_m_sport = fitment_env['bmw_m_sport']
        api_client.force_authenticate(user=seller_user)

        listing = SparePartListing.objects.create(
            seller=seller_user,
            category=category,
            catalogue_part=part_calipers,
            name='front disc brake pad set',
            brand='Bosch',
            mpn='F 002 H23 683',
            price=Decimal('119.99'),
            status=ListingStatusChoices.APPROVED,
        )

        res = api_client.patch(
            f'/api/v1/marketplace/parts/{listing.id}/',
            {
                'compatible_variants': [str(v_m_sport.id)],
                'compatibility_notes': 'Fits 330i M Sport with blue calipers',
            },
            format='json',
        )
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert str(v_m_sport.id) in [str(vid) for vid in data['compatible_variants']]
        assert data['compatibility_notes'] == 'Fits 330i M Sport with blue calipers'
        assert len(data['fitment_verification']) == 1
        assert data['fitment_verification'][0]['variant_id'] == str(v_m_sport.id)
        assert data['fitment_verification'][0]['status'] == FITMENT_STATUS_VERIFIED
        assert data['fitment_summary']['verified'] == 1

    def test_patch_clears_compatible_variant_when_empty_list_sent(self, fitment_env, seller_user, api_client):
        """Seller explicitly selects Universal / Unlinked, clearing compatible_variants."""
        category = fitment_env['category']
        part_calipers = fitment_env['part_calipers']
        v_m_sport = fitment_env['bmw_m_sport']
        api_client.force_authenticate(user=seller_user)

        listing = SparePartListing.objects.create(
            seller=seller_user,
            category=category,
            catalogue_part=part_calipers,
            name='front disc brake pad set',
            brand='Bosch',
            mpn='F 002 H23 683',
            price=Decimal('119.99'),
            compatibility_notes='Some note',
            status=ListingStatusChoices.DRAFT,
        )
        listing.compatible_variants.set([v_m_sport])

        res = api_client.patch(
            f'/api/v1/marketplace/parts/{listing.id}/',
            {
                'compatible_variants': [],
                'compatibility_notes': '',
            },
            format='json',
        )
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data['compatible_variants'] == []
        assert data['compatibility_notes'] == ''
        assert data['fitment_verification'] == []
        assert data['fitment_summary']['verified'] == 0


