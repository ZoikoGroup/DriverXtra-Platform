import pytest
from rest_framework import status
from apps.catalogue.models import (
    VehicleMake,
    VehicleModel,
    VehicleVariant,
    PartCategory,
    Part,
    FuelTypeChoices,
    TransmissionChoices,
)


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
