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
)


@pytest.fixture
def fitment_catalogue(db):
    bmw = VehicleMake.objects.create(name='BMW')
    audi = VehicleMake.objects.create(name='Audi')

    bmw_model = VehicleModel.objects.create(make=bmw, name='3 Series', year_start=2019)
    audi_model = VehicleModel.objects.create(make=audi, name='A4', year_start=2016)

    variant_bmw = VehicleVariant.objects.create(
        model=bmw_model,
        name='330i M Sport',
        year=2021,
        engine_code='B48B20',
        fuel_type=FuelTypeChoices.PETROL,
    )
    variant_audi = VehicleVariant.objects.create(
        model=audi_model,
        name='2.0 TFSI S Line',
        year=2020,
        engine_code='DADA',
        fuel_type=FuelTypeChoices.PETROL,
    )

    category = PartCategory.objects.create(name='Braking', slug='braking')

    part_brembo = Part.objects.create(
        name='Brembo Front Rotors 348mm',
        brand='Brembo',
        mpn='09.C398.13',
        category=category,
    )

    part_pads = Part.objects.create(
        name='Ferodo Track Brake Pads',
        brand='Ferodo',
        mpn='FRP3100H',
        category=category,
    )

    part_incompatible = Part.objects.create(
        name='Ford Fiesta Drum Brakes',
        brand='Generic',
        mpn='DRUM-FIESTA-01',
        category=category,
    )

    part_universal = Part.objects.create(
        name='Universal Windscreen Washer Fluid (5L)',
        brand='Prestone',
        mpn='PRE-WASHER-5L',
        category=category,
        is_universal=True,
    )

    # Establish compatibility relationships
    PartCompatibility.objects.create(
        part=part_brembo,
        vehicle_variant=variant_bmw,
        fitment_type=FitmentTypeChoices.CONFIRMED_FIT,
        qualifications='Direct bolt-on OEM fit for 348mm front rotor packages.',
    )

    PartCompatibility.objects.create(
        part=part_pads,
        vehicle_variant=variant_bmw,
        fitment_type=FitmentTypeChoices.CONDITIONAL_FIT,
        qualifications='Requires M Sport caliper package; not compatible with standard single-piston calipers.',
    )

    PartCompatibility.objects.create(
        part=part_incompatible,
        vehicle_variant=variant_bmw,
        fitment_type=FitmentTypeChoices.DOES_NOT_FIT,
        qualifications='Drum brake assembly incompatible with BMW disc brake hubs.',
    )

    return {
        'bmw_variant': variant_bmw,
        'audi_variant': variant_audi,
        'part_brembo': part_brembo,
        'part_pads': part_pads,
        'part_incompatible': part_incompatible,
        'part_universal': part_universal,
    }


@pytest.mark.django_db
class TestCompatibilityAndFitment:

    def test_fitment_confirmed_fit(self, api_client, fitment_catalogue):
        part_id = fitment_catalogue['part_brembo'].id
        variant_id = fitment_catalogue['bmw_variant'].id

        res = api_client.get(f'/api/v1/catalogue/fitment/?part_id={part_id}&vehicle_variant_id={variant_id}')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data['status'] == FitmentTypeChoices.CONFIRMED_FIT
        assert data['is_compatible'] is True
        assert data['confidence'] == 'HIGH'
        assert '348mm' in data['qualifications']

    def test_fitment_conditional_fit(self, api_client, fitment_catalogue):
        part_id = fitment_catalogue['part_pads'].id
        variant_id = fitment_catalogue['bmw_variant'].id

        res = api_client.get(f'/api/v1/catalogue/fitment/?part_id={part_id}&vehicle_variant_id={variant_id}')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data['status'] == FitmentTypeChoices.CONDITIONAL_FIT
        assert data['is_compatible'] is True
        assert data['confidence'] == 'MEDIUM'
        assert 'M Sport' in data['qualifications']

    def test_fitment_does_not_fit(self, api_client, fitment_catalogue):
        part_id = fitment_catalogue['part_incompatible'].id
        variant_id = fitment_catalogue['bmw_variant'].id

        res = api_client.get(f'/api/v1/catalogue/fitment/?part_id={part_id}&vehicle_variant_id={variant_id}')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data['status'] == FitmentTypeChoices.DOES_NOT_FIT
        assert data['is_compatible'] is False

    def test_fitment_unknown_when_no_record_exists(self, api_client, fitment_catalogue):
        # Brembo rotor tested against Audi variant with no mapping
        part_id = fitment_catalogue['part_brembo'].id
        audi_variant_id = fitment_catalogue['audi_variant'].id

        res = api_client.get(f'/api/v1/catalogue/fitment/?part_id={part_id}&vehicle_variant_id={audi_variant_id}')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        # Must return UNKNOWN - never pretend or assume it fits
        assert data['status'] == FitmentTypeChoices.UNKNOWN
        assert data['is_compatible'] is False
        assert data['confidence'] == 'NONE'
        assert 'No verified compatibility' in data['qualifications']

    def test_universal_part_conditional_fit_and_evidence_level(self, api_client, fitment_catalogue):
        part_id = fitment_catalogue['part_universal'].id
        audi_variant_id = fitment_catalogue['audi_variant'].id

        res = api_client.get(f'/api/v1/catalogue/fitment/?part_id={part_id}&vehicle_variant_id={audi_variant_id}')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        # Universal parts must NOT receive an automatic CONFIRMED_FIT or HIGH confidence guarantee
        assert data['status'] == FitmentTypeChoices.CONDITIONAL_FIT
        assert data['is_compatible'] is True
        assert data['confidence'] == 'LOW'
        assert data['evidence_level'] == 'UNVERIFIED_UNIVERSAL_DECLARATION'
        assert 'reason' in data
        assert 'universal' in data['reason'].lower()

    def test_fitment_check_post_endpoint(self, api_client, fitment_catalogue):
        payload = {
            'part_id': str(fitment_catalogue['part_brembo'].id),
            'vehicle_variant_id': str(fitment_catalogue['bmw_variant'].id),
        }
        res = api_client.post('/api/v1/catalogue/fitment/', payload, format='json')
        assert res.status_code == status.HTTP_200_OK
        assert res.json()['status'] == FitmentTypeChoices.CONFIRMED_FIT

    def test_prevent_duplicate_compatibility_mapping(self, admin_auth_client, fitment_catalogue):
        # Attempt to create duplicate mapping for Brembo on BMW
        payload = {
            'part': str(fitment_catalogue['part_brembo'].id),
            'vehicle_variant': str(fitment_catalogue['bmw_variant'].id),
            'fitment_type': FitmentTypeChoices.CONFIRMED_FIT,
        }
        res = admin_auth_client.post('/api/v1/catalogue/compatibility/', payload, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST
