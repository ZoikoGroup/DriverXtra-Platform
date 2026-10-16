import pytest
from rest_framework import status
from apps.catalogue.models import (
    VehicleMake,
    VehicleModel,
    VehicleVariant,
    FuelTypeChoices,
    TransmissionChoices,
)
from apps.garage.models import GarageVehicle


@pytest.fixture
def sample_variant(db):
    bmw = VehicleMake.objects.create(name='BMW')
    model_3 = VehicleModel.objects.create(make=bmw, name='3 Series', year_start=2019)
    return VehicleVariant.objects.create(
        model=model_3,
        name='330i M Sport',
        year=2021,
        engine_code='B48B20',
        fuel_type=FuelTypeChoices.PETROL,
        transmission=TransmissionChoices.AUTOMATIC,
        power_bhp=258,
    )


@pytest.mark.django_db
class TestVehicleGarage:

    def test_unauthenticated_garage_access_denied(self, api_client):
        res = api_client.get('/api/v1/garage/vehicles/')
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

        res = api_client.post('/api/v1/garage/vehicles/', {})
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

    def test_add_vehicle_with_catalogue_variant(self, buyer_auth_client, buyer_user, sample_variant):
        payload = {
            'vehicle_variant': str(sample_variant.id),
            'registration_plate': 'GF21 XTR',
            'vin': 'WBA5R1C50M8219420',
            'current_odometer': 34820,
            'nickname': 'Daily Commuter',
        }
        res = buyer_auth_client.post('/api/v1/garage/vehicles/', payload, format='json')
        assert res.status_code == status.HTTP_201_CREATED
        data = res.json()
        assert data['make'] == 'BMW'
        assert data['model'] == '3 Series'
        assert data['year'] == 2021
        assert data['trim'] == '330i M Sport'
        assert data['is_primary'] is True  # First vehicle defaults to primary

    def test_add_vehicle_with_manual_details(self, buyer_auth_client, buyer_user):
        payload = {
            'make': 'Mercedes-Benz',
            'model': 'C-Class',
            'year': 2022,
            'trim': 'C300 AMG Line',
            'registration_plate': 'MB22 LUX',
            'vin': 'WDD2050401R123456',
            'current_odometer': 18500,
        }
        res = buyer_auth_client.post('/api/v1/garage/vehicles/', payload, format='json')
        assert res.status_code == status.HTTP_201_CREATED
        data = res.json()
        assert data['make'] == 'Mercedes-Benz'
        assert data['model'] == 'C-Class'
        assert data['year'] == 2022

    def test_list_only_current_users_vehicles(self, buyer_auth_client, buyer_user, seller_user):
        # Create vehicle for buyer
        v_buyer = GarageVehicle.objects.create(
            user=buyer_user,
            make='BMW',
            model='330i',
            year=2021,
            registration_plate='BUYER01',
        )
        # Create vehicle for seller
        v_seller = GarageVehicle.objects.create(
            user=seller_user,
            make='Audi',
            model='A4',
            year=2020,
            registration_plate='SELLER01',
        )

        res = buyer_auth_client.get('/api/v1/garage/vehicles/')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        plates = [v['registration_plate'] for v in data['results']]
        assert 'BUYER01' in plates
        assert 'SELLER01' not in plates

    def test_strict_cross_user_isolation(self, buyer_auth_client, seller_auth_client, seller_user):
        # Seller creates a vehicle
        v_seller = GarageVehicle.objects.create(
            user=seller_user,
            make='Porsche',
            model='911',
            year=2022,
            registration_plate='SELLER-911',
        )

        # Buyer attempts to view Seller's vehicle
        res_get = buyer_auth_client.get(f'/api/v1/garage/vehicles/{v_seller.id}/')
        assert res_get.status_code == status.HTTP_404_NOT_FOUND

        # Buyer attempts to update Seller's vehicle
        res_patch = buyer_auth_client.patch(
            f'/api/v1/garage/vehicles/{v_seller.id}/',
            {'current_odometer': 99999},
            format='json',
        )
        assert res_patch.status_code == status.HTTP_404_NOT_FOUND
        v_seller.refresh_from_db()
        assert v_seller.current_odometer == 0

        # Buyer attempts to delete Seller's vehicle
        res_del = buyer_auth_client.delete(f'/api/v1/garage/vehicles/{v_seller.id}/')
        assert res_del.status_code == status.HTTP_404_NOT_FOUND
        assert GarageVehicle.objects.filter(id=v_seller.id).exists()

        # Buyer attempts to set Seller's vehicle as primary
        res_pri = buyer_auth_client.post(f'/api/v1/garage/vehicles/{v_seller.id}/set-primary/')
        assert res_pri.status_code == status.HTTP_404_NOT_FOUND

    def test_set_primary_vehicle(self, buyer_auth_client, buyer_user):
        v1 = GarageVehicle.objects.create(user=buyer_user, make='BMW', model='330i', year=2021, is_primary=True)
        v2 = GarageVehicle.objects.create(user=buyer_user, make='Audi', model='A3', year=2022, is_primary=False)

        res = buyer_auth_client.post(f'/api/v1/garage/vehicles/{v2.id}/set-primary/')
        assert res.status_code == status.HTTP_200_OK

        v1.refresh_from_db()
        v2.refresh_from_db()
        assert v2.is_primary is True
        assert v1.is_primary is False

    def test_archive_vehicle_preserves_record_and_excludes_from_active_list(self, buyer_auth_client, buyer_user):
        v = GarageVehicle.objects.create(user=buyer_user, make='VW', model='Golf', year=2019)
        res = buyer_auth_client.delete(f'/api/v1/garage/vehicles/{v.id}/')
        assert res.status_code == status.HTTP_204_NO_CONTENT

        # Soft-delete audit: verify database record is preserved and marked archived
        v.refresh_from_db()
        assert v.is_archived is True
        assert v.archived_at is not None

        # Verify excluded from default active garage list
        res_list = buyer_auth_client.get('/api/v1/garage/vehicles/')
        assert res_list.status_code == status.HTTP_200_OK
        vehicle_ids = [item['id'] for item in res_list.json()['results']]
        assert str(v.id) not in vehicle_ids

    def test_vin_masked_in_api_responses(self, buyer_auth_client, buyer_user):
        # Create vehicle with full 17-character VIN
        v = GarageVehicle.objects.create(
            user=buyer_user,
            make='BMW',
            model='330i',
            year=2021,
            vin='WBA5R1C50M8219420',
        )

        # GET detail response: full VIN must not be exposed; only last 6 characters visible
        res_detail = buyer_auth_client.get(f'/api/v1/garage/vehicles/{v.id}/')
        assert res_detail.status_code == status.HTTP_200_OK
        masked_vin = res_detail.json()['vin']
        assert 'WBA5R1C50M' not in masked_vin
        assert masked_vin.endswith('219420')
        assert masked_vin.startswith('*')

        # GET list response: full VIN must not be exposed
        res_list = buyer_auth_client.get('/api/v1/garage/vehicles/')
        assert res_list.status_code == status.HTTP_200_OK
        veh_item = next(item for item in res_list.json()['results'] if item['id'] == str(v.id))
        assert veh_item['vin'] == masked_vin

    def test_mot_and_recalls_labeled_self_reported(self, buyer_auth_client, buyer_user):
        v = GarageVehicle.objects.create(
            user=buyer_user,
            make='Audi',
            model='A4',
            year=2020,
            mot_status='VALID',
            active_recalls_count=0,
        )
        res = buyer_auth_client.get(f'/api/v1/garage/vehicles/{v.id}/')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data['mot_data_source'] == 'Self-reported'
        assert data['recalls_data_source'] == 'Self-reported'

    def test_cross_user_archive_isolation(self, buyer_auth_client, seller_user):
        v_seller = GarageVehicle.objects.create(
            user=seller_user,
            make='Mercedes-Benz',
            model='C200',
            year=2021,
        )
        # Buyer cannot archive Seller's vehicle
        res = buyer_auth_client.delete(f'/api/v1/garage/vehicles/{v_seller.id}/')
        assert res.status_code == status.HTTP_404_NOT_FOUND
        v_seller.refresh_from_db()
        assert v_seller.is_archived is False
