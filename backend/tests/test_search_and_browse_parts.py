import uuid
from decimal import Decimal
import pytest
from rest_framework import status
from django.test.utils import CaptureQueriesContext
from django.db import connection

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
    PartConditionChoices,
)
from apps.garage.models import GarageVehicle
from apps.marketplace.fitment import (
    batch_evaluate_listings_fitment,
    FITMENT_STATUS_VERIFIED,
    FITMENT_STATUS_CONDITIONAL,
    FITMENT_STATUS_CONFLICT,
    FITMENT_STATUS_SELLER_CLAIMED,
    FITMENT_STATUS_UNKNOWN,
)


@pytest.fixture
def browse_env(db, seller_user):
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

    category_braking = PartCategory.objects.create(name='Braking', slug='braking')
    category_engine = PartCategory.objects.create(name='Engine', slug='engine')

    # Canonical parts
    cat_calipers = Part.objects.create(
        name='Brembo M Sport Caliper Set',
        brand='Brembo',
        mpn='CALIPER-BM-01',
        category=category_braking,
    )
    cat_universal = Part.objects.create(
        name='Universal Brake Bleeder Kit',
        brand='Generic',
        mpn='BLEEDER-UNI-01',
        category=category_braking,
        is_universal=True,
    )
    cat_universal_conflict = Part.objects.create(
        name='Universal Hose Kit',
        brand='Generic',
        mpn='HOSE-UNI-01',
        category=category_braking,
        is_universal=True,
    )

    # Compatibilities:
    # cat_calipers + m_sport -> CONFIRMED_FIT
    PartCompatibility.objects.create(
        part=cat_calipers,
        vehicle_variant=variant_bmw_m_sport,
        fitment_type=FitmentTypeChoices.CONFIRMED_FIT,
    )
    # cat_calipers + base -> CONDITIONAL_FIT
    PartCompatibility.objects.create(
        part=cat_calipers,
        vehicle_variant=variant_bmw_base,
        fitment_type=FitmentTypeChoices.CONDITIONAL_FIT,
    )
    # cat_universal_conflict + m_sport -> DOES_NOT_FIT
    PartCompatibility.objects.create(
        part=cat_universal_conflict,
        vehicle_variant=variant_bmw_m_sport,
        fitment_type=FitmentTypeChoices.DOES_NOT_FIT,
    )

    return {
        'bmw': bmw,
        'bmw_model': bmw_model,
        'bmw_m_sport': variant_bmw_m_sport,
        'bmw_base': variant_bmw_base,
        'category_braking': category_braking,
        'category_engine': category_engine,
        'cat_calipers': cat_calipers,
        'cat_universal': cat_universal,
        'cat_universal_conflict': cat_universal_conflict,
    }


@pytest.mark.django_db
class TestPartBrowseDefaultsAndPermissions:
    """Ensure baseline anonymous browse and default output shape remain preserved."""

    def test_default_browse_returns_approved_only_with_standard_shape(self, api_client, seller_user, browse_env):
        cat_braking = browse_env['category_braking']

        # Approved listing
        p1 = SparePartListing.objects.create(
            seller=seller_user,
            category=cat_braking,
            name='Brake Pad Front',
            brand='Bosch',
            mpn='BP-01',
            price=Decimal('50.00'),
            stock_quantity=5,
            status=ListingStatusChoices.APPROVED,
        )
        # Draft listing (must not appear)
        SparePartListing.objects.create(
            seller=seller_user,
            category=cat_braking,
            name='Draft Part',
            brand='Bosch',
            mpn='BP-02',
            price=Decimal('50.00'),
            status=ListingStatusChoices.DRAFT,
        )
        # Inactive listing (must not appear)
        SparePartListing.objects.create(
            seller=seller_user,
            category=cat_braking,
            name='Inactive Part',
            brand='Bosch',
            mpn='BP-03',
            price=Decimal('50.00'),
            is_active=False,
            status=ListingStatusChoices.APPROVED,
        )

        res = api_client.get('/api/v1/marketplace/browse/parts/')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert 'count' in data
        assert 'next' in data
        assert 'previous' in data
        assert 'results' in data
        assert data['count'] == 1
        assert len(data['results']) == 1
        assert data['results'][0]['id'] == str(p1.id)
        assert 'facets' not in data  # Facets absent by default


@pytest.mark.django_db
class TestPartBrowseSortingAndTieBreaker:
    """Verify newest, price_asc, price_desc, relevance, stable tie-breaker, and invalid sort."""

    def test_sorting_price_asc_and_desc(self, api_client, seller_user, browse_env):
        cat = browse_env['category_braking']
        p_mid = SparePartListing.objects.create(
            seller=seller_user, category=cat, name='Mid Price', brand='BrandA', mpn='M-01',
            price=Decimal('50.00'), status=ListingStatusChoices.APPROVED,
        )
        p_low = SparePartListing.objects.create(
            seller=seller_user, category=cat, name='Low Price', brand='BrandB', mpn='L-01',
            price=Decimal('20.00'), status=ListingStatusChoices.APPROVED,
        )
        p_high = SparePartListing.objects.create(
            seller=seller_user, category=cat, name='High Price', brand='BrandC', mpn='H-01',
            price=Decimal('100.00'), status=ListingStatusChoices.APPROVED,
        )

        # price_asc
        res_asc = api_client.get('/api/v1/marketplace/browse/parts/?sort=price_asc')
        assert res_asc.status_code == status.HTTP_200_OK
        ids_asc = [r['id'] for r in res_asc.json()['results']]
        assert ids_asc == [str(p_low.id), str(p_mid.id), str(p_high.id)]

        # price_desc
        res_desc = api_client.get('/api/v1/marketplace/browse/parts/?sort=price_desc')
        assert res_desc.status_code == status.HTTP_200_OK
        ids_desc = [r['id'] for r in res_desc.json()['results']]
        assert ids_desc == [str(p_high.id), str(p_mid.id), str(p_low.id)]

    def test_invalid_sort_returns_structured_400(self, api_client):
        res = api_client.get('/api/v1/marketplace/browse/parts/?sort=cheapest')
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        data = res.json()
        assert data['status'] == 'error'
        assert data['code'] == 400
        assert 'sort' in data['details']

    def test_relevance_weights_order(self, api_client, seller_user, browse_env):
        cat = browse_env['category_braking']
        query = "FERODO"

        # 1. Exact MPN match
        p_mpn_exact = SparePartListing.objects.create(
            seller=seller_user, category=cat, name='Brake Pad Set', brand='Other', mpn='FERODO',
            price=Decimal('50.00'), status=ListingStatusChoices.APPROVED,
        )
        # 2. Exact OEM cross-reference match
        p_oem_exact = SparePartListing.objects.create(
            seller=seller_user, category=cat, name='Brake Caliper', brand='Other', mpn='CAL-999',
            oem_numbers=['FERODO', '34116860911'], price=Decimal('50.00'), status=ListingStatusChoices.APPROVED,
        )
        # 3. MPN Prefix match
        p_mpn_prefix = SparePartListing.objects.create(
            seller=seller_user, category=cat, name='Rotor Kit', brand='Other', mpn='FERODO-MAX-01',
            price=Decimal('50.00'), status=ListingStatusChoices.APPROVED,
        )
        # 4. Brand exact match
        p_brand_exact = SparePartListing.objects.create(
            seller=seller_user, category=cat, name='Universal Sensor', brand='FERODO', mpn='SNS-001',
            price=Decimal('50.00'), status=ListingStatusChoices.APPROVED,
        )
        # 5. Name contains
        p_name_contains = SparePartListing.objects.create(
            seller=seller_user, category=cat, name='FERODO Performance Hose', brand='Other', mpn='HSE-001',
            price=Decimal('50.00'), status=ListingStatusChoices.APPROVED,
        )
        # 6. Description contains
        p_desc_contains = SparePartListing.objects.create(
            seller=seller_user, category=cat, name='Standard Fluid', brand='Other', mpn='FLD-001',
            description='Compatible with FERODO racing formulations', price=Decimal('50.00'),
            status=ListingStatusChoices.APPROVED,
        )

        res = api_client.get(f'/api/v1/marketplace/browse/parts/?search={query}&sort=relevance')
        assert res.status_code == status.HTTP_200_OK
        ids = [r['id'] for r in res.json()['results']]
        expected_order = [
            str(p_mpn_exact.id),      # Weight 100
            str(p_oem_exact.id),      # Weight 90
            str(p_mpn_prefix.id),     # Weight 60
            str(p_brand_exact.id),    # Weight 40
            str(p_name_contains.id),  # Weight 25
            str(p_desc_contains.id),  # Weight 5
        ]
        assert ids == expected_order

    def test_relevance_without_search_falls_back_to_newest(self, api_client, seller_user, browse_env):
        cat = browse_env['category_braking']
        p1 = SparePartListing.objects.create(
            seller=seller_user, category=cat, name='First Part', brand='BrandA', mpn='MPN-1',
            price=Decimal('10.00'), status=ListingStatusChoices.APPROVED,
        )
        p2 = SparePartListing.objects.create(
            seller=seller_user, category=cat, name='Second Part', brand='BrandB', mpn='MPN-2',
            price=Decimal('20.00'), status=ListingStatusChoices.APPROVED,
        )
        from django.utils import timezone
        from datetime import timedelta
        SparePartListing.objects.filter(id=p1.id).update(created_at=timezone.now() - timedelta(days=1))
        SparePartListing.objects.filter(id=p2.id).update(created_at=timezone.now())

        res = api_client.get('/api/v1/marketplace/browse/parts/?sort=relevance')
        assert res.status_code == status.HTTP_200_OK
        ids = [r['id'] for r in res.json()['results']]
        assert ids == [str(p2.id), str(p1.id)]  # Newest first


@pytest.mark.django_db
class TestPartBrowsePagination:
    """Verify page_size clamping, error handling, and stable pagination."""

    def test_page_size_clamped_at_50(self, api_client, seller_user, browse_env):
        cat = browse_env['category_braking']
        for i in range(55):
            SparePartListing.objects.create(
                seller=seller_user, category=cat, name=f'Part {i}', brand='BrandX', mpn=f'MPN-{i}',
                price=Decimal('10.00'), status=ListingStatusChoices.APPROVED,
            )

        res = api_client.get('/api/v1/marketplace/browse/parts/?page_size=100')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert len(data['results']) == 50
        assert data['count'] == 55
        assert data['next'] is not None

    def test_invalid_page_size_returns_structured_400(self, api_client):
        for bad_val in ['0', '-5', 'abc']:
            res = api_client.get(f'/api/v1/marketplace/browse/parts/?page_size={bad_val}')
            assert res.status_code == status.HTTP_400_BAD_REQUEST
            data = res.json()
            assert data['status'] == 'error'
            assert data['code'] == 400
            assert 'page_size' in data['details']

    def test_no_duplicate_listings_across_pages_with_compatible_variants(self, api_client, seller_user, browse_env):
        cat = browse_env['category_braking']
        v1 = browse_env['bmw_m_sport']
        v2 = browse_env['bmw_base']

        # Listing linked to multiple variants
        p1 = SparePartListing.objects.create(
            seller=seller_user, category=cat, name='Multi Variant Part', brand='BrandM', mpn='MVAR-01',
            price=Decimal('10.00'), status=ListingStatusChoices.APPROVED,
        )
        p1.compatible_variants.set([v1, v2])

        res = api_client.get('/api/v1/marketplace/browse/parts/?page_size=20')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        ids = [r['id'] for r in data['results']]
        assert ids.count(str(p1.id)) == 1


@pytest.mark.django_db
class TestPartBrowseFilters:
    """Verify condition (single, multiple, invalid), in_stock (true/false/invalid), and out-of-stock visibility."""

    def test_condition_filter_single_and_multiple(self, api_client, seller_user, browse_env):
        cat = browse_env['category_braking']
        p_new = SparePartListing.objects.create(
            seller=seller_user, category=cat, name='New Part', brand='Brand', mpn='NEW-01',
            condition=PartConditionChoices.NEW, price=Decimal('10.00'), status=ListingStatusChoices.APPROVED,
        )
        p_used = SparePartListing.objects.create(
            seller=seller_user, category=cat, name='Used Part', brand='Brand', mpn='USD-01',
            condition=PartConditionChoices.USED, price=Decimal('10.00'), status=ListingStatusChoices.APPROVED,
        )
        p_refurb = SparePartListing.objects.create(
            seller=seller_user, category=cat, name='Refurb Part', brand='Brand', mpn='REF-01',
            condition=PartConditionChoices.REFURBISHED, price=Decimal('10.00'), status=ListingStatusChoices.APPROVED,
        )

        # Single condition: NEW
        res_new = api_client.get('/api/v1/marketplace/browse/parts/?condition=NEW')
        assert res_new.status_code == status.HTTP_200_OK
        assert [r['id'] for r in res_new.json()['results']] == [str(p_new.id)]

        # Multiple condition: NEW,REFURBISHED
        res_multi = api_client.get('/api/v1/marketplace/browse/parts/?condition=NEW,REFURBISHED')
        assert res_multi.status_code == status.HTTP_200_OK
        ids_multi = set(r['id'] for r in res_multi.json()['results'])
        assert ids_multi == {str(p_new.id), str(p_refurb.id)}

    def test_invalid_condition_returns_structured_400(self, api_client):
        res = api_client.get('/api/v1/marketplace/browse/parts/?condition=BROKEN')
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        data = res.json()
        assert data['status'] == 'error'
        assert data['code'] == 400
        assert 'condition' in data['details']

    def test_in_stock_filter_true_false_and_default(self, api_client, seller_user, browse_env):
        cat = browse_env['category_braking']
        p_in_stock = SparePartListing.objects.create(
            seller=seller_user, category=cat, name='In Stock Part', brand='Brand', mpn='STK-01',
            stock_quantity=5, price=Decimal('10.00'), status=ListingStatusChoices.APPROVED,
        )
        p_out_of_stock = SparePartListing.objects.create(
            seller=seller_user, category=cat, name='Out of Stock Part', brand='Brand', mpn='OOS-01',
            stock_quantity=0, price=Decimal('10.00'), status=ListingStatusChoices.APPROVED,
        )

        # Default: both are visible
        res_def = api_client.get('/api/v1/marketplace/browse/parts/')
        assert res_def.status_code == status.HTTP_200_OK
        ids_def = set(r['id'] for r in res_def.json()['results'])
        assert ids_def == {str(p_in_stock.id), str(p_out_of_stock.id)}

        # in_stock=true: only stock_quantity > 0
        res_true = api_client.get('/api/v1/marketplace/browse/parts/?in_stock=true')
        assert res_true.status_code == status.HTTP_200_OK
        assert [r['id'] for r in res_true.json()['results']] == [str(p_in_stock.id)]

        # in_stock=false: both remain visible
        res_false = api_client.get('/api/v1/marketplace/browse/parts/?in_stock=false')
        assert res_false.status_code == status.HTTP_200_OK
        assert set(r['id'] for r in res_false.json()['results']) == {str(p_in_stock.id), str(p_out_of_stock.id)}

    def test_invalid_in_stock_returns_structured_400(self, api_client):
        res = api_client.get('/api/v1/marketplace/browse/parts/?in_stock=maybe')
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        data = res.json()
        assert data['status'] == 'error'
        assert data['code'] == 400
        assert 'in_stock' in data['details']


@pytest.mark.django_db
class TestPartBrowseFitsOnlyAndDecisionTableParity:
    """Verify fits_only parameter validation, database pre-filtering, and full decision-table parity with Part C."""

    def test_fits_only_without_fits_vehicle_returns_400(self, buyer_auth_client):
        res = buyer_auth_client.get('/api/v1/marketplace/browse/parts/?fits_only=true')
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        data = res.json()
        assert data['status'] == 'error'
        assert data['code'] == 400
        assert 'fits_only' in data['details']

    def test_fits_only_unauthenticated_returns_401(self, api_client):
        res = api_client.get(f'/api/v1/marketplace/browse/parts/?fits_vehicle={uuid.uuid4()}&fits_only=true')
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

    def test_fits_only_invalid_uuid_returns_400(self, buyer_auth_client):
        res = buyer_auth_client.get('/api/v1/marketplace/browse/parts/?fits_vehicle=invalid-uuid&fits_only=true')
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert 'fits_vehicle' in res.json()['details']

    def test_fits_only_other_user_vehicle_returns_404(self, buyer_auth_client, seller_user, browse_env):
        other_vehicle = GarageVehicle.objects.create(
            user=seller_user,
            make='BMW', model='3 Series', year=2021,
            vehicle_variant=browse_env['bmw_m_sport'],
        )
        res = buyer_auth_client.get(f'/api/v1/marketplace/browse/parts/?fits_vehicle={other_vehicle.id}&fits_only=true')
        assert res.status_code == status.HTTP_404_NOT_FOUND

    def test_fits_only_unlinked_vehicle_returns_empty_results(self, buyer_auth_client, buyer_user, seller_user, browse_env):
        cat = browse_env['category_braking']
        SparePartListing.objects.create(
            seller=seller_user, category=cat, name='Any Part', brand='Brand', mpn='ANY-01',
            price=Decimal('10.00'), status=ListingStatusChoices.APPROVED,
        )
        unlinked_vehicle = GarageVehicle.objects.create(
            user=buyer_user,
            make='BMW', model='3 Series', year=2021,
            vehicle_variant=None,
        )
        res = buyer_auth_client.get(f'/api/v1/marketplace/browse/parts/?fits_vehicle={unlinked_vehicle.id}&fits_only=true')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data['count'] == 0
        assert data['results'] == []

    def test_fits_only_full_decision_table_parity(self, buyer_auth_client, buyer_user, seller_user, browse_env):
        """Build listings representing every branch of the Part C decision table and assert

        100% parity between the SQL fits_only filter and the Python batch_evaluate_listings_fitment.
        """
        cat = browse_env['category_braking']
        v_m_sport = browse_env['bmw_m_sport']
        v_base = browse_env['bmw_base']
        cat_calipers = browse_env['cat_calipers']
        cat_universal = browse_env['cat_universal']
        cat_universal_conflict = browse_env['cat_universal_conflict']

        # Buyer vehicle has v_m_sport
        buyer_vehicle = GarageVehicle.objects.create(
            user=buyer_user,
            make='BMW', model='3 Series', year=2021,
            vehicle_variant=v_m_sport,
        )

        # 1. VERIFIED: Linked to cat_calipers (CONFIRMED_FIT for v_m_sport)
        p_verified = SparePartListing.objects.create(
            seller=seller_user, category=cat, catalogue_part=cat_calipers, name='Verified Caliper',
            brand='Brembo', mpn='CAL-VER-1', price=Decimal('200.00'), status=ListingStatusChoices.APPROVED,
        )

        # 2. CONDITIONAL: Universal part with no PartCompatibility record
        p_conditional_uni = SparePartListing.objects.create(
            seller=seller_user, category=cat, catalogue_part=cat_universal, name='Conditional Universal',
            brand='Generic', mpn='UNI-COND-1', price=Decimal('30.00'), status=ListingStatusChoices.APPROVED,
        )

        # 3. CONFLICT: Universal part but explicit DOES_NOT_FIT record for v_m_sport
        p_conflict_uni = SparePartListing.objects.create(
            seller=seller_user, category=cat, catalogue_part=cat_universal_conflict, name='Conflict Universal',
            brand='Generic', mpn='UNI-CONF-1', price=Decimal('30.00'), status=ListingStatusChoices.APPROVED,
        )

        # 4. SELLER_CLAIMED: No catalogue_part, but seller declared compatible variant
        p_seller_claimed = SparePartListing.objects.create(
            seller=seller_user, category=cat, catalogue_part=None, name='Seller Claimed Part',
            brand='Custom', mpn='CUST-01', price=Decimal('40.00'), status=ListingStatusChoices.APPROVED,
        )
        p_seller_claimed.compatible_variants.set([v_m_sport])

        # 5. UNKNOWN: No catalogue_part, no declared variant
        p_unknown = SparePartListing.objects.create(
            seller=seller_user, category=cat, catalogue_part=None, name='Unknown Part',
            brand='Custom', mpn='CUST-02', price=Decimal('40.00'), status=ListingStatusChoices.APPROVED,
        )

        all_listings = [p_verified, p_conditional_uni, p_conflict_uni, p_seller_claimed, p_unknown]

        # Verify Part C evaluator statuses for all 5 listings
        evals = batch_evaluate_listings_fitment(all_listings, v_m_sport)
        assert evals[p_verified.id]['status'] == FITMENT_STATUS_VERIFIED
        assert evals[p_conditional_uni.id]['status'] == FITMENT_STATUS_CONDITIONAL
        assert evals[p_conflict_uni.id]['status'] == FITMENT_STATUS_CONFLICT
        assert evals[p_seller_claimed.id]['status'] == FITMENT_STATUS_SELLER_CLAIMED
        assert evals[p_unknown.id]['status'] == FITMENT_STATUS_UNKNOWN

        # Query marketplace browse with fits_only=true
        res = buyer_auth_client.get(f'/api/v1/marketplace/browse/parts/?fits_vehicle={buyer_vehicle.id}&fits_only=true')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data['count'] == 2
        returned_ids = {r['id'] for r in data['results']}
        assert returned_ids == {str(p_verified.id), str(p_conditional_uni.id)}

        # Ensure returned listings have fitment annotation
        for item in data['results']:
            assert item['fitment']['status'] in (FITMENT_STATUS_VERIFIED, FITMENT_STATUS_CONDITIONAL)


@pytest.mark.django_db
class TestPartBrowseFacets:
    """Verify facet calculation per brand, category, condition under active filters."""

    def test_facets_correct_counts_and_structure(self, api_client, seller_user, browse_env):
        cat_braking = browse_env['category_braking']
        cat_engine = browse_env['category_engine']

        # Create listings
        # 2 Bosch, 1 Brembo
        # 2 NEW, 1 USED
        # 2 Braking, 1 Engine
        SparePartListing.objects.create(
            seller=seller_user, category=cat_braking, name='Brake Pad 1', brand='Bosch', mpn='B-01',
            condition=PartConditionChoices.NEW, price=Decimal('50.00'), status=ListingStatusChoices.APPROVED,
        )
        SparePartListing.objects.create(
            seller=seller_user, category=cat_braking, name='Brake Pad 2', brand='Bosch', mpn='B-02',
            condition=PartConditionChoices.NEW, price=Decimal('60.00'), status=ListingStatusChoices.APPROVED,
        )
        SparePartListing.objects.create(
            seller=seller_user, category=cat_engine, name='Engine Valve', brand='Brembo', mpn='V-01',
            condition=PartConditionChoices.USED, price=Decimal('120.00'), status=ListingStatusChoices.APPROVED,
        )
        # 1 Draft listing (must not be counted in facets)
        SparePartListing.objects.create(
            seller=seller_user, category=cat_braking, name='Draft Part', brand='Bosch', mpn='D-01',
            condition=PartConditionChoices.NEW, price=Decimal('50.00'), status=ListingStatusChoices.DRAFT,
        )

        res = api_client.get('/api/v1/marketplace/browse/parts/?include_facets=true')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert 'facets' in data
        facets = data['facets']

        # Brands
        brands_map = {b['brand']: b['count'] for b in facets['brands']}
        assert brands_map['Bosch'] == 2
        assert brands_map['Brembo'] == 1

        # Conditions
        conditions_map = {c['condition']: c['count'] for c in facets['conditions']}
        assert conditions_map['NEW'] == 2
        assert conditions_map['USED'] == 1

        # Categories
        cat_map = {c['slug']: c['count'] for c in facets['categories']}
        assert cat_map['braking'] == 2
        assert cat_map['engine'] == 1
        assert 'id' in facets['categories'][0]
        assert 'name' in facets['categories'][0]

    def test_facets_respect_active_filters(self, api_client, seller_user, browse_env):
        cat_braking = browse_env['category_braking']
        cat_engine = browse_env['category_engine']

        SparePartListing.objects.create(
            seller=seller_user, category=cat_braking, name='Brake Pad 1', brand='Bosch', mpn='B-01',
            condition=PartConditionChoices.NEW, price=Decimal('50.00'), status=ListingStatusChoices.APPROVED,
        )
        SparePartListing.objects.create(
            seller=seller_user, category=cat_engine, name='Engine Valve', brand='Brembo', mpn='V-01',
            condition=PartConditionChoices.USED, price=Decimal('120.00'), status=ListingStatusChoices.APPROVED,
        )

        # Filter by category braking
        res = api_client.get(f'/api/v1/marketplace/browse/parts/?category_id={cat_braking.id}&include_facets=true')
        assert res.status_code == status.HTTP_200_OK
        facets = res.json()['facets']
        brands_map = {b['brand']: b['count'] for b in facets['brands']}
        assert brands_map.get('Bosch') == 1
        assert 'Brembo' not in brands_map


@pytest.mark.django_db
class TestPartBrowseQueryCountAndPerformance:
    """Ensure constant O(1) database queries when varying the number of matching listings (3 vs 30)

    and page_size across plain list, fits_only list, and include_facets=true list.
    """

    def test_query_count_constant_plain_list(self, api_client, seller_user, browse_env):
        cat = browse_env['category_braking']

        # Warm up connection / django tables
        api_client.get('/api/v1/marketplace/browse/parts/')

        # Create 3 listings
        listings_3 = [
            SparePartListing.objects.create(
                seller=seller_user, category=cat, name=f'Item {i}', brand='Brand', mpn=f'MPN-{i}',
                price=Decimal('10.00'), status=ListingStatusChoices.APPROVED,
            )
            for i in range(3)
        ]

        with CaptureQueriesContext(connection) as ctx_3:
            res_3 = api_client.get('/api/v1/marketplace/browse/parts/?page_size=20')
        assert res_3.status_code == status.HTTP_200_OK
        count_3 = len(ctx_3.captured_queries)

        # Add 27 more listings (total 30)
        for i in range(3, 30):
            SparePartListing.objects.create(
                seller=seller_user, category=cat, name=f'Item {i}', brand='Brand', mpn=f'MPN-{i}',
                price=Decimal('10.00'), status=ListingStatusChoices.APPROVED,
            )

        with CaptureQueriesContext(connection) as ctx_30:
            res_30 = api_client.get('/api/v1/marketplace/browse/parts/?page_size=20')
        assert res_30.status_code == status.HTTP_200_OK
        count_30 = len(ctx_30.captured_queries)

        assert count_3 == count_30, f"Query count changed when scaling 3 -> 30: {count_3} vs {count_30}"

    def test_query_count_constant_fits_only(self, buyer_auth_client, buyer_user, seller_user, browse_env):
        cat = browse_env['category_braking']
        v_m_sport = browse_env['bmw_m_sport']
        cat_calipers = browse_env['cat_calipers']

        buyer_vehicle = GarageVehicle.objects.create(
            user=buyer_user,
            make='BMW', model='3 Series', year=2021,
            vehicle_variant=v_m_sport,
        )

        # Warm up
        buyer_auth_client.get(f'/api/v1/marketplace/browse/parts/?fits_vehicle={buyer_vehicle.id}&fits_only=true')

        for i in range(3):
            SparePartListing.objects.create(
                seller=seller_user, category=cat, catalogue_part=cat_calipers, name=f'Fits Part {i}',
                brand='Brembo', mpn=f'FIT-{i}', price=Decimal('10.00'), status=ListingStatusChoices.APPROVED,
            )

        with CaptureQueriesContext(connection) as ctx_3:
            res_3 = buyer_auth_client.get(f'/api/v1/marketplace/browse/parts/?fits_vehicle={buyer_vehicle.id}&fits_only=true&page_size=20')
        assert res_3.status_code == status.HTTP_200_OK
        count_3 = len(ctx_3.captured_queries)

        for i in range(3, 30):
            SparePartListing.objects.create(
                seller=seller_user, category=cat, catalogue_part=cat_calipers, name=f'Fits Part {i}',
                brand='Brembo', mpn=f'FIT-{i}', price=Decimal('10.00'), status=ListingStatusChoices.APPROVED,
            )

        with CaptureQueriesContext(connection) as ctx_30:
            res_30 = buyer_auth_client.get(f'/api/v1/marketplace/browse/parts/?fits_vehicle={buyer_vehicle.id}&fits_only=true&page_size=20')
        assert res_30.status_code == status.HTTP_200_OK
        count_30 = len(ctx_30.captured_queries)

        assert count_3 == count_30, f"Query count changed when scaling fits_only 3 -> 30: {count_3} vs {count_30}"

    def test_query_count_constant_with_facets(self, api_client, seller_user, browse_env):
        cat = browse_env['category_braking']

        # Warm up
        api_client.get('/api/v1/marketplace/browse/parts/?include_facets=true')

        for i in range(3):
            SparePartListing.objects.create(
                seller=seller_user, category=cat, name=f'Facet Part {i}', brand='Brand', mpn=f'F-{i}',
                price=Decimal('10.00'), status=ListingStatusChoices.APPROVED,
            )

        with CaptureQueriesContext(connection) as ctx_3:
            res_3 = api_client.get('/api/v1/marketplace/browse/parts/?include_facets=true&page_size=20')
        assert res_3.status_code == status.HTTP_200_OK
        count_3 = len(ctx_3.captured_queries)

        for i in range(3, 30):
            SparePartListing.objects.create(
                seller=seller_user, category=cat, name=f'Facet Part {i}', brand='Brand', mpn=f'F-{i}',
                price=Decimal('10.00'), status=ListingStatusChoices.APPROVED,
            )

        with CaptureQueriesContext(connection) as ctx_30:
            res_30 = api_client.get('/api/v1/marketplace/browse/parts/?include_facets=true&page_size=20')
        assert res_30.status_code == status.HTTP_200_OK
        count_30 = len(ctx_30.captured_queries)

        assert count_3 == count_30, f"Query count changed with facets 3 -> 30: {count_3} vs {count_30}"
