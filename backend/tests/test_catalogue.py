import pytest
from rest_framework import status
from apps.catalogue.models import (
    VehicleMake,
    VehicleModel,
    VehicleVariant,
    PartCategory,
    Part,
    PartCompatibility,
    FitmentTypeChoices,
    FuelTypeChoices,
    TransmissionChoices,
)
from apps.identity.models import User, RoleChoices, Permission, StaffRole, StaffRolePermission, StaffProfile


@pytest.fixture
def sample_catalogue(db):
    bmw = VehicleMake.objects.create(name='BMW', country_of_origin='Germany')
    audi = VehicleMake.objects.create(name='Audi', country_of_origin='Germany')

    bmw_3series = VehicleModel.objects.create(make=bmw, name='3 Series', year_start=2019)
    audi_a4 = VehicleModel.objects.create(make=audi, name='A4', year_start=2016)

    variant_330i = VehicleVariant.objects.create(
        model=bmw_3series,
        name='330i M Sport',
        year=2021,
        engine_code='B48B20',
        fuel_type=FuelTypeChoices.PETROL,
        transmission=TransmissionChoices.AUTOMATIC,
        power_bhp=258,
    )

    braking_category = PartCategory.objects.create(name='Braking Systems', slug='braking-systems')
    rotors_category = PartCategory.objects.create(
        name='Brake Rotors',
        slug='brake-rotors',
        parent=braking_category,
    )

    brembo_rotor = Part.objects.create(
        name='Brembo Prime Two-Piece Front Brake Disc Rotor Set (348mm)',
        brand='Brembo',
        mpn='09.C398.13',
        category=rotors_category,
        attributes={'diameter_mm': 348, 'thickness_mm': 30, 'bolt_holes': 5},
        oem_numbers=['BMW 34116860911', 'BMW 34116860912'],
    )

    universal_oil = Part.objects.create(
        name='Castrol Edge 5W-30 LL Engine Oil (5L)',
        brand='Castrol',
        mpn='CAS-5W30-5L',
        category=braking_category,
        is_universal=True,
    )

    return {
        'make_bmw': bmw,
        'make_audi': audi,
        'model_3series': bmw_3series,
        'variant_330i': variant_330i,
        'category_braking': braking_category,
        'category_rotors': rotors_category,
        'part_brembo': brembo_rotor,
        'part_universal': universal_oil,
    }


@pytest.mark.django_db
class TestCatalogue:

    def test_list_vehicle_makes(self, api_client, sample_catalogue):
        res = api_client.get('/api/v1/catalogue/makes/')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data['count'] >= 2
        make_names = [m['name'] for m in data['results']]
        assert 'BMW' in make_names
        assert 'Audi' in make_names

    def test_list_models_filtered_by_make(self, api_client, sample_catalogue):
        bmw_id = sample_catalogue['make_bmw'].id
        res = api_client.get(f'/api/v1/catalogue/models/?make_id={bmw_id}')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data['count'] == 1
        assert data['results'][0]['name'] == '3 Series'

    def test_list_variants_filtered_by_model(self, api_client, sample_catalogue):
        model_id = sample_catalogue['model_3series'].id
        res = api_client.get(f'/api/v1/catalogue/variants/?model_id={model_id}')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data['count'] == 1
        variant = data['results'][0]
        assert variant['name'] == '330i M Sport'
        assert variant['year'] == 2021
        assert variant['engine_code'] == 'B48B20'

    def test_list_part_categories_with_nesting(self, api_client, sample_catalogue):
        res = api_client.get('/api/v1/catalogue/categories/?root_only=true')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data['count'] >= 1
        braking = next(c for c in data['results'] if c['slug'] == 'braking-systems')
        assert len(braking['subcategories']) == 1
        assert braking['subcategories'][0]['slug'] == 'brake-rotors'

    def test_list_parts_and_filtering(self, api_client, sample_catalogue):
        # List all parts
        res = api_client.get('/api/v1/catalogue/parts/')
        assert res.status_code == status.HTTP_200_OK
        assert res.json()['count'] >= 2

        # Filter by brand
        res_brand = api_client.get('/api/v1/catalogue/parts/?brand=Brembo')
        assert res_brand.status_code == status.HTTP_200_OK
        assert res_brand.json()['count'] == 1
        assert res_brand.json()['results'][0]['mpn'] == '09.C398.13'

        # Filter by search MPN
        res_search = api_client.get('/api/v1/catalogue/parts/?search=09.C398')
        assert res_search.status_code == status.HTTP_200_OK
        assert res_search.json()['count'] == 1

    def test_unprivileged_user_cannot_create_catalogue_items(self, buyer_auth_client):
        # Attempt to create make as a regular buyer
        res = buyer_auth_client.post('/api/v1/catalogue/makes/', {'name': 'Porsche'}, format='json')
        assert res.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_create_catalogue_make_and_model(self, admin_auth_client):
        res_make = admin_auth_client.post('/api/v1/catalogue/makes/', {'name': 'Porsche', 'country_of_origin': 'Germany'}, format='json')
        assert res_make.status_code == status.HTTP_201_CREATED
        porsche_id = res_make.json()['id']

        res_model = admin_auth_client.post('/api/v1/catalogue/models/', {'make': porsche_id, 'name': '911', 'year_start': 1964}, format='json')
        assert res_model.status_code == status.HTTP_201_CREATED
        assert res_model.json()['name'] == '911'

    def test_patch_and_deactivate_make(self, admin_auth_client, sample_catalogue):
        make = sample_catalogue['make_bmw']
        res = admin_auth_client.patch(
            f'/api/v1/catalogue/makes/{make.id}/',
            {'country_of_origin': 'Bavaria, Germany', 'is_active': False},
            format='json',
        )
        assert res.status_code == status.HTTP_200_OK
        make.refresh_from_db()
        assert make.country_of_origin == 'Bavaria, Germany'
        assert make.is_active is False

    def test_patch_and_deactivate_model(self, admin_auth_client, sample_catalogue):
        model = sample_catalogue['model_3series']
        res = admin_auth_client.patch(
            f'/api/v1/catalogue/models/{model.id}/',
            {'year_end': 2026, 'is_active': False},
            format='json',
        )
        assert res.status_code == status.HTTP_200_OK
        model.refresh_from_db()
        assert model.year_end == 2026
        assert model.is_active is False

    def test_patch_and_deactivate_variant(self, admin_auth_client, sample_catalogue):
        variant = sample_catalogue['variant_330i']
        res = admin_auth_client.patch(
            f'/api/v1/catalogue/variants/{variant.id}/',
            {'power_bhp': 265, 'is_active': False},
            format='json',
        )
        assert res.status_code == status.HTTP_200_OK
        variant.refresh_from_db()
        assert variant.power_bhp == 265
        assert variant.is_active is False

    def test_patch_and_deactivate_category_and_duplicate_slug(self, admin_auth_client, sample_catalogue):
        cat = sample_catalogue['category_braking']
        res = admin_auth_client.patch(
            f'/api/v1/catalogue/categories/{cat.id}/',
            {'is_active': False},
            format='json',
        )
        assert res.status_code == status.HTTP_200_OK
        cat.refresh_from_db()
        assert cat.is_active is False

        # Attempt to create duplicate category with existing slug returns structured 400
        res_dup = admin_auth_client.post(
            '/api/v1/catalogue/categories/',
            {'name': 'Duplicate Braking', 'slug': 'braking-systems'},
            format='json',
        )
        assert res_dup.status_code == status.HTTP_400_BAD_REQUEST
        assert 'slug' in str(res_dup.json()).lower()

    def test_patch_and_deactivate_part(self, admin_auth_client, sample_catalogue):
        part = sample_catalogue['part_brembo']
        res = admin_auth_client.patch(
            f'/api/v1/catalogue/parts/{part.id}/',
            {'is_active': False},
            format='json',
        )
        assert res.status_code == status.HTTP_200_OK
        part.refresh_from_db()
        assert part.is_active is False

    def test_part_compatibility_patch_and_delete(self, admin_auth_client, sample_catalogue):
        part = sample_catalogue['part_brembo']
        variant = sample_catalogue['variant_330i']

        # Create compatibility record
        compat = PartCompatibility.objects.create(
            part=part,
            vehicle_variant=variant,
            fitment_type=FitmentTypeChoices.CONFIRMED_FIT,
            qualifications='Standard Discs',
            notes='Initial test note',
        )

        # 1. PATCH fitment_type, qualifications, and notes
        res_patch = admin_auth_client.patch(
            f'/api/v1/catalogue/compatibility/{compat.id}/',
            {
                'fitment_type': FitmentTypeChoices.CONDITIONAL_FIT,
                'qualifications': 'Requires M-Sport Braking Package',
                'notes': 'Verified by workshop engineer',
            },
            format='json',
        )
        assert res_patch.status_code == status.HTTP_200_OK
        compat.refresh_from_db()
        assert compat.fitment_type == FitmentTypeChoices.CONDITIONAL_FIT
        assert compat.qualifications == 'Requires M-Sport Braking Package'
        assert compat.notes == 'Verified by workshop engineer'

        # 2. Reject modifying part or vehicle_variant on existing compatibility
        other_part = sample_catalogue['part_universal']
        res_immutable = admin_auth_client.patch(
            f'/api/v1/catalogue/compatibility/{compat.id}/',
            {'part': str(other_part.id)},
            format='json',
        )
        assert res_immutable.status_code == status.HTTP_400_BAD_REQUEST
        assert 'not permitted' in str(res_immutable.json()).lower()

        # 3. DELETE compatibility record
        res_delete = admin_auth_client.delete(f'/api/v1/catalogue/compatibility/{compat.id}/')
        assert res_delete.status_code == status.HTTP_204_NO_CONTENT
        assert not PartCompatibility.objects.filter(id=compat.id).exists()

    def test_catalogue_manage_permission_matrix(self, api_client, buyer_auth_client, seller_auth_client, admin_auth_client, sample_catalogue):
        from rest_framework.test import APIClient
        make = sample_catalogue['make_bmw']

        # 1. Unauthenticated GET succeeds (public read preserved)
        res_unauth_get = api_client.get(f'/api/v1/catalogue/makes/{make.id}/')
        assert res_unauth_get.status_code == status.HTTP_200_OK

        # 2. Unauthenticated write fails with 401
        res_unauth_patch = api_client.patch(
            f'/api/v1/catalogue/makes/{make.id}/',
            {'country_of_origin': 'Germany'},
            format='json',
        )
        assert res_unauth_patch.status_code == status.HTTP_401_UNAUTHORIZED

        # 3. Authenticated BUYER write fails with 403
        res_buyer = buyer_auth_client.patch(
            f'/api/v1/catalogue/makes/{make.id}/',
            {'country_of_origin': 'Germany'},
            format='json',
        )
        assert res_buyer.status_code == status.HTTP_403_FORBIDDEN

        # 4. Authenticated SELLER write fails with 403
        res_seller = seller_auth_client.patch(
            f'/api/v1/catalogue/makes/{make.id}/',
            {'country_of_origin': 'Germany'},
            format='json',
        )
        assert res_seller.status_code == status.HTTP_403_FORBIDDEN

        # 5. Staff user WITHOUT StaffProfile (legacy fallback) lacks catalogue.manage and fails with 403
        legacy_staff = User.objects.create_user(
            email='legacy_staff_officer@driverxtra.com',
            password='Password123!',
            is_staff=True,
            is_email_verified=True,
        )
        legacy_staff.add_role(RoleChoices.STAFF)
        legacy_client = APIClient()
        legacy_client.force_authenticate(user=legacy_staff)

        res_legacy_staff = legacy_client.patch(
            f'/api/v1/catalogue/makes/{make.id}/',
            {'country_of_origin': 'Germany'},
            format='json',
        )
        assert res_legacy_staff.status_code == status.HTTP_403_FORBIDDEN

        # 6. Staff user WITH catalogue.manage permission succeeds with 200
        perm = Permission.objects.get(code='catalogue.manage')
        staff_role, _ = StaffRole.objects.get_or_create(code='CATALOGUE_EDITOR', defaults={'name': 'Catalogue Editor'})
        StaffRolePermission.objects.get_or_create(staff_role=staff_role, permission=perm)

        authorized_staff = User.objects.create_user(
            email='catalogue_authorized@driverxtra.com',
            password='Password123!',
            is_staff=True,
            is_email_verified=True,
        )
        authorized_staff.add_role(RoleChoices.STAFF)
        StaffProfile.objects.create(user=authorized_staff, staff_role=staff_role)

        auth_staff_client = APIClient()
        auth_staff_client.force_authenticate(user=authorized_staff)

        res_auth_staff = auth_staff_client.patch(
            f'/api/v1/catalogue/makes/{make.id}/',
            {'country_of_origin': 'Federal Republic of Germany'},
            format='json',
        )
        assert res_auth_staff.status_code == status.HTTP_200_OK
        make.refresh_from_db()
        assert make.country_of_origin == 'Federal Republic of Germany'

        # 7. ADMIN user succeeds with 200 (all permissions bypass)
        res_admin = admin_auth_client.patch(
            f'/api/v1/catalogue/makes/{make.id}/',
            {'country_of_origin': 'Germany'},
            format='json',
        )
        assert res_admin.status_code == status.HTTP_200_OK

    def test_compatibility_update_does_not_mutate_marketplace_listing_status(self, admin_auth_client, seller_user, sample_catalogue):
        from apps.marketplace.models import SparePartListing, ListingStatusChoices
        part = sample_catalogue['part_brembo']
        variant = sample_catalogue['variant_330i']

        compat = PartCompatibility.objects.create(
            part=part,
            vehicle_variant=variant,
            fitment_type=FitmentTypeChoices.CONFIRMED_FIT,
        )

        listing = SparePartListing.objects.create(
            seller=seller_user,
            catalogue_part=part,
            category=part.category,
            name='Brembo Front Rotors for 330i',
            brand='Brembo',
            mpn='09.C398.13',
            price=149.99,
            stock_quantity=5,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )

        # Update compatibility to DOES_NOT_FIT
        res = admin_auth_client.patch(
            f'/api/v1/catalogue/compatibility/{compat.id}/',
            {'fitment_type': FitmentTypeChoices.DOES_NOT_FIT},
            format='json',
        )
        assert res.status_code == status.HTTP_200_OK

        # Verify listing status remains unchanged as APPROVED
        listing.refresh_from_db()
        assert listing.status == ListingStatusChoices.APPROVED

