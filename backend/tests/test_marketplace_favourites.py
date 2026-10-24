import pytest
from rest_framework import status
from django.db import IntegrityError
from apps.identity.models import User, RoleChoices
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
    BuyerFavouriteVehicle,
    BuyerFavouritePart,
)


@pytest.fixture
def make_audi(db):
    return VehicleMake.objects.create(name='Audi', country_of_origin='Germany')


@pytest.fixture
def model_a4(db, make_audi):
    return VehicleModel.objects.create(make=make_audi, name='A4', year_start=2020)


@pytest.fixture
def variant_a4(db, model_a4):
    return VehicleVariant.objects.create(
        model=model_a4,
        name='2.0 TDI S Line',
        year=2022,
        engine_code='DFHA',
        fuel_type=FuelTypeChoices.DIESEL,
        transmission=TransmissionChoices.AUTOMATIC,
        power_bhp=190,
    )


@pytest.fixture
def approved_vehicle(db, seller_user, make_audi, model_a4, variant_a4):
    return VehicleListing.objects.create(
        seller=seller_user,
        title='2022 Audi A4 S Line Avant',
        make=make_audi,
        model=model_a4,
        variant=variant_a4,
        year=2022,
        price=28500.00,
        mileage=18000,
        fuel_type=FuelTypeChoices.DIESEL,
        transmission=TransmissionChoices.AUTOMATIC,
        status=ListingStatusChoices.APPROVED,
        is_active=True,
    )


@pytest.fixture
def second_approved_vehicle(db, seller_user, make_audi, model_a4, variant_a4):
    return VehicleListing.objects.create(
        seller=seller_user,
        title='2021 Audi A4 Black Edition',
        make=make_audi,
        model=model_a4,
        variant=variant_a4,
        year=2021,
        price=24950.00,
        mileage=29000,
        fuel_type=FuelTypeChoices.DIESEL,
        transmission=TransmissionChoices.AUTOMATIC,
        status=ListingStatusChoices.APPROVED,
        is_active=True,
    )


@pytest.fixture
def brakes_category(db):
    return PartCategory.objects.create(name='Braking Systems', slug='braking-systems')


@pytest.fixture
def approved_part(db, seller_user, brakes_category):
    return SparePartListing.objects.create(
        seller=seller_user,
        name='Brembo High Performance Brake Pads',
        brand='Brembo',
        mpn='P 06 088',
        category=brakes_category,
        price=65.00,
        stock_quantity=10,
        status=ListingStatusChoices.APPROVED,
        is_active=True,
    )


@pytest.fixture
def second_approved_part(db, seller_user, brakes_category):
    return SparePartListing.objects.create(
        seller=seller_user,
        name='Bosch QuietCast Premium Brake Rotors',
        brand='Bosch',
        mpn='0986479C12',
        category=brakes_category,
        price=120.00,
        stock_quantity=5,
        status=ListingStatusChoices.APPROVED,
        is_active=True,
    )


@pytest.fixture
def other_buyer_user(db):
    user = User.objects.create_user(
        email='buyer2@driverxtra.com',
        password='SecurePassword123!',
        first_name='Second',
        last_name='Buyer',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.mark.django_db
class TestBuyerFavourites:

    # =========================================================================
    # 1. Successful Addition & Eligibility
    # =========================================================================

    def test_authenticated_buyer_can_favourite_approved_active_vehicle(
        self, buyer_auth_client, buyer_user, approved_vehicle
    ):
        res = buyer_auth_client.post(
            '/api/v1/marketplace/favourites/',
            {'vehicle_id': str(approved_vehicle.id)},
            format='json',
        )
        assert res.status_code == status.HTTP_201_CREATED
        data = res.json()
        assert data['vehicle_id'] == str(approved_vehicle.id)
        assert data['is_available'] is True
        assert data['vehicle']['title'] == approved_vehicle.title
        assert 'id' in data

        # Check DB
        fav = BuyerFavouriteVehicle.objects.get(user=buyer_user, vehicle=approved_vehicle)
        assert fav.buyer == buyer_user
        assert fav.listing == approved_vehicle

    def test_duplicate_favourites_cannot_be_created(
        self, buyer_auth_client, buyer_user, approved_vehicle
    ):
        # First addition: 201 Created
        res1 = buyer_auth_client.post(
            '/api/v1/marketplace/favourites/',
            {'vehicle_id': str(approved_vehicle.id)},
            format='json',
        )
        assert res1.status_code == status.HTTP_201_CREATED

        # Duplicate addition: handles safely without creating duplicate records (200 OK)
        res2 = buyer_auth_client.post(
            '/api/v1/marketplace/favourites/',
            {'vehicle_id': str(approved_vehicle.id)},
            format='json',
        )
        assert res2.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED)

        # Confirm exactly 1 record in database
        assert BuyerFavouriteVehicle.objects.filter(
            user=buyer_user, vehicle=approved_vehicle
        ).count() == 1

        # Direct database insert must violate UniqueConstraint
        with pytest.raises(IntegrityError):
            BuyerFavouriteVehicle.objects.create(
                user=buyer_user,
                vehicle=approved_vehicle,
            )

    def test_unapproved_vehicles_cannot_be_favourited(
        self, buyer_auth_client, buyer_user, seller_user, make_audi, model_a4, variant_a4
    ):
        unapproved_statuses = [
            ListingStatusChoices.DRAFT,
            ListingStatusChoices.PENDING_APPROVAL,
            ListingStatusChoices.REJECTED,
            ListingStatusChoices.CHANGES_REQUESTED,
        ]

        for st in unapproved_statuses:
            veh = VehicleListing.objects.create(
                seller=seller_user,
                title=f'Test Vehicle {st}',
                make=make_audi,
                model=model_a4,
                variant=variant_a4,
                year=2022,
                price=20000.00,
                status=st,
                is_active=True,
            )
            res = buyer_auth_client.post(
                '/api/v1/marketplace/favourites/',
                {'vehicle_id': str(veh.id)},
                format='json',
            )
            assert res.status_code == status.HTTP_400_BAD_REQUEST
            assert not BuyerFavouriteVehicle.objects.filter(user=buyer_user, vehicle=veh).exists()

    def test_inactive_or_unavailable_vehicles_cannot_be_newly_favourited(
        self, buyer_auth_client, buyer_user, seller_user, make_audi, model_a4, variant_a4
    ):
        inactive_veh = VehicleListing.objects.create(
            seller=seller_user,
            title='Inactive Audi A4',
            make=make_audi,
            model=model_a4,
            variant=variant_a4,
            year=2022,
            price=20000.00,
            status=ListingStatusChoices.APPROVED,
            is_active=False,
        )
        res = buyer_auth_client.post(
            '/api/v1/marketplace/favourites/',
            {'vehicle_id': str(inactive_veh.id)},
            format='json',
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert not BuyerFavouriteVehicle.objects.filter(user=buyer_user, vehicle=inactive_veh).exists()

    # =========================================================================
    # 2. Listing & Removal
    # =========================================================================

    def test_buyer_can_list_and_remove_own_favourites(
        self, buyer_auth_client, buyer_user, approved_vehicle, second_approved_vehicle
    ):
        # Favourite two vehicles
        buyer_auth_client.post(
            '/api/v1/marketplace/favourites/',
            {'vehicle_id': str(approved_vehicle.id)},
            format='json',
        )
        buyer_auth_client.post(
            '/api/v1/marketplace/favourites/',
            {'vehicle_id': str(second_approved_vehicle.id)},
            format='json',
        )

        # List favourites
        list_res = buyer_auth_client.get('/api/v1/marketplace/favourites/')
        assert list_res.status_code == status.HTTP_200_OK
        data = list_res.json()
        items = data if isinstance(data, list) else data.get('results', [])
        assert len(items) == 2
        returned_vehicle_ids = [item['vehicle_id'] for item in items]
        assert str(approved_vehicle.id) in returned_vehicle_ids
        assert str(second_approved_vehicle.id) in returned_vehicle_ids

        # Remove first vehicle by vehicle_id
        del_res = buyer_auth_client.delete(f'/api/v1/marketplace/favourites/{approved_vehicle.id}/')
        assert del_res.status_code == status.HTTP_204_NO_CONTENT

        # List again -> only second vehicle remains
        list_res2 = buyer_auth_client.get('/api/v1/marketplace/favourites/')
        items2 = list_res2.json() if isinstance(list_res2.json(), list) else list_res2.json().get('results', [])
        assert len(items2) == 1
        assert items2[0]['vehicle_id'] == str(second_approved_vehicle.id)

    def test_buyer_a_cannot_view_or_remove_buyer_b_favourites(
        self, buyer_auth_client, buyer_user, other_buyer_user, approved_vehicle, second_approved_vehicle, api_client
    ):
        # Buyer A favourites vehicle 1
        fav_a = BuyerFavouriteVehicle.objects.create(user=buyer_user, vehicle=approved_vehicle)
        # Buyer B favourites vehicle 2
        fav_b = BuyerFavouriteVehicle.objects.create(user=other_buyer_user, vehicle=second_approved_vehicle)

        # Buyer A lists favourites -> only sees vehicle 1
        res_a = buyer_auth_client.get('/api/v1/marketplace/favourites/')
        items_a = res_a.json() if isinstance(res_a.json(), list) else res_a.json().get('results', [])
        assert len(items_a) == 1
        assert items_a[0]['vehicle_id'] == str(approved_vehicle.id)

        # Buyer A attempts to remove Buyer B's favourite
        del_res = buyer_auth_client.delete(f'/api/v1/marketplace/favourites/{fav_b.id}/')
        assert del_res.status_code == status.HTTP_404_NOT_FOUND

        # Buyer B's favourite is still in the database
        assert BuyerFavouriteVehicle.objects.filter(id=fav_b.id).exists()

        # Buyer B lists favourites -> only sees vehicle 2
        api_client.force_authenticate(user=other_buyer_user)
        res_b = api_client.get('/api/v1/marketplace/favourites/')
        items_b = res_b.json() if isinstance(res_b.json(), list) else res_b.json().get('results', [])
        assert len(items_b) == 1
        assert items_b[0]['vehicle_id'] == str(second_approved_vehicle.id)

    def test_client_cannot_spoof_another_buyer_identity(
        self, buyer_auth_client, buyer_user, other_buyer_user, approved_vehicle
    ):
        # Client passes user_id / buyer_id in payload attempting to save for other_buyer_user
        res = buyer_auth_client.post(
            '/api/v1/marketplace/favourites/',
            {
                'vehicle_id': str(approved_vehicle.id),
                'user_id': str(other_buyer_user.id),
                'buyer_id': str(other_buyer_user.id),
                'user': str(other_buyer_user.id),
            },
            format='json',
        )
        assert res.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED)

        # Verified: Favourite was created for buyer_user (request.user), NOT other_buyer_user
        fav = BuyerFavouriteVehicle.objects.get(vehicle=approved_vehicle)
        assert fav.user == buyer_user
        assert not BuyerFavouriteVehicle.objects.filter(user=other_buyer_user).exists()

    def test_unauthenticated_requests_are_rejected(self, api_client, approved_vehicle):
        # GET
        assert api_client.get('/api/v1/marketplace/favourites/').status_code == status.HTTP_401_UNAUTHORIZED
        # POST
        assert api_client.post(
            '/api/v1/marketplace/favourites/',
            {'vehicle_id': str(approved_vehicle.id)},
            format='json',
        ).status_code == status.HTTP_401_UNAUTHORIZED
        # DELETE
        assert api_client.delete(
            f'/api/v1/marketplace/favourites/{approved_vehicle.id}/'
        ).status_code == status.HTTP_401_UNAUTHORIZED

    def test_seller_only_and_workshop_only_accounts_cannot_access_buyer_favourites(
        self, seller_auth_client, workshop_user, approved_vehicle, api_client
    ):
        # Seller-only user (holds only SELLER, no BUYER role)
        assert seller_auth_client.get('/api/v1/marketplace/favourites/').status_code == status.HTTP_403_FORBIDDEN
        assert seller_auth_client.post(
            '/api/v1/marketplace/favourites/',
            {'vehicle_id': str(approved_vehicle.id)},
            format='json',
        ).status_code == status.HTTP_403_FORBIDDEN

        # Workshop-only user (holds only WORKSHOP, no BUYER role)
        api_client.force_authenticate(user=workshop_user)
        assert api_client.get('/api/v1/marketplace/favourites/').status_code == status.HTTP_403_FORBIDDEN
        assert api_client.post(
            '/api/v1/marketplace/favourites/',
            {'vehicle_id': str(approved_vehicle.id)},
            format='json',
        ).status_code == status.HTTP_403_FORBIDDEN

    def test_user_with_both_buyer_and_seller_roles_is_permitted(
        self, seller_auth_client, seller_user, approved_vehicle
    ):
        # Grant BUYER role to seller
        seller_user.add_role(RoleChoices.BUYER)
        res = seller_auth_client.post(
            '/api/v1/marketplace/favourites/',
            {'vehicle_id': str(approved_vehicle.id)},
            format='json',
        )
        assert res.status_code == status.HTTP_201_CREATED

    def test_admin_is_permitted(self, admin_auth_client, approved_vehicle):
        res = admin_auth_client.post(
            '/api/v1/marketplace/favourites/',
            {'vehicle_id': str(approved_vehicle.id)},
            format='json',
        )
        assert res.status_code == status.HTTP_201_CREATED

    def test_previously_favourited_vehicle_becoming_unavailable_does_not_break_response(
        self, buyer_auth_client, buyer_user, approved_vehicle
    ):
        # Favourite active approved vehicle
        fav = BuyerFavouriteVehicle.objects.create(user=buyer_user, vehicle=approved_vehicle)

        # Vehicle subsequently becomes unapproved and inactive
        approved_vehicle.status = ListingStatusChoices.CHANGES_REQUESTED
        approved_vehicle.is_active = False
        approved_vehicle.save()

        # Listing endpoint still succeeds gracefully
        res = buyer_auth_client.get('/api/v1/marketplace/favourites/')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        items = data if isinstance(data, list) else data.get('results', [])
        assert len(items) == 1
        assert items[0]['vehicle_id'] == str(approved_vehicle.id)
        assert items[0]['is_available'] is False

        # Buyer can still remove it cleanly
        del_res = buyer_auth_client.delete(f'/api/v1/marketplace/favourites/{fav.id}/')
        assert del_res.status_code == status.HTTP_204_NO_CONTENT
        assert not BuyerFavouriteVehicle.objects.filter(id=fav.id).exists()

    def test_safe_repeated_removals(self, buyer_auth_client, buyer_user, approved_vehicle):
        fav = BuyerFavouriteVehicle.objects.create(user=buyer_user, vehicle=approved_vehicle)

        # First removal
        del1 = buyer_auth_client.delete(f'/api/v1/marketplace/favourites/{fav.id}/')
        assert del1.status_code == status.HTTP_204_NO_CONTENT

        # Second removal of already removed favourite
        del2 = buyer_auth_client.delete(f'/api/v1/marketplace/favourites/{fav.id}/')
        assert del2.status_code == status.HTTP_204_NO_CONTENT

    def test_url_alias_favorites_works(self, buyer_auth_client, approved_vehicle):
        # Test US spelling alias
        res = buyer_auth_client.post(
            '/api/v1/marketplace/favorites/',
            {'vehicle_id': str(approved_vehicle.id)},
            format='json',
        )
        assert res.status_code == status.HTTP_201_CREATED

        list_res = buyer_auth_client.get('/api/v1/marketplace/favorites/')
        assert list_res.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestBuyerFavouriteParts:

    # =========================================================================
    # 1. Successful Addition & Eligibility
    # =========================================================================

    def test_authenticated_buyer_can_favourite_approved_active_part(
        self, buyer_auth_client, buyer_user, approved_part
    ):
        res = buyer_auth_client.post(
            '/api/v1/marketplace/favourites/parts/',
            {'part_id': str(approved_part.id)},
            format='json',
        )
        assert res.status_code == status.HTTP_201_CREATED
        data = res.json()
        assert data['part_id'] == str(approved_part.id)
        assert data['is_available'] is True
        assert data['part']['name'] == approved_part.name
        assert 'id' in data

        # Check DB
        fav = BuyerFavouritePart.objects.get(user=buyer_user, part=approved_part)
        assert fav.buyer == buyer_user
        assert fav.listing == approved_part

    def test_duplicate_part_favourites_cannot_be_created(
        self, buyer_auth_client, buyer_user, approved_part
    ):
        # First addition: 201 Created
        res1 = buyer_auth_client.post(
            '/api/v1/marketplace/favourites/parts/',
            {'part_id': str(approved_part.id)},
            format='json',
        )
        assert res1.status_code == status.HTTP_201_CREATED

        # Duplicate addition: handles safely without creating duplicate records (200 OK)
        res2 = buyer_auth_client.post(
            '/api/v1/marketplace/favourites/parts/',
            {'part_id': str(approved_part.id)},
            format='json',
        )
        assert res2.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED)

        # Confirm exactly 1 record in database
        assert BuyerFavouritePart.objects.filter(
            user=buyer_user, part=approved_part
        ).count() == 1

        # Direct database insert must violate UniqueConstraint
        with pytest.raises(IntegrityError):
            BuyerFavouritePart.objects.create(
                user=buyer_user,
                part=approved_part,
            )

    def test_unapproved_parts_cannot_be_favourited(
        self, buyer_auth_client, buyer_user, seller_user, brakes_category
    ):
        unapproved_statuses = [
            ListingStatusChoices.DRAFT,
            ListingStatusChoices.PENDING_APPROVAL,
            ListingStatusChoices.REJECTED,
            ListingStatusChoices.CHANGES_REQUESTED,
        ]

        for st in unapproved_statuses:
            part = SparePartListing.objects.create(
                seller=seller_user,
                name=f'Test Part {st}',
                brand='TestBrand',
                mpn=f'MPN-{st}',
                category=brakes_category,
                price=50.00,
                status=st,
                is_active=True,
            )
            res = buyer_auth_client.post(
                '/api/v1/marketplace/favourites/parts/',
                {'part_id': str(part.id)},
                format='json',
            )
            assert res.status_code == status.HTTP_400_BAD_REQUEST
            assert not BuyerFavouritePart.objects.filter(user=buyer_user, part=part).exists()

    def test_inactive_or_unavailable_parts_cannot_be_newly_favourited(
        self, buyer_auth_client, buyer_user, seller_user, brakes_category
    ):
        inactive_part = SparePartListing.objects.create(
            seller=seller_user,
            name='Inactive Brake Rotor',
            brand='Bosch',
            mpn='INACT-123',
            category=brakes_category,
            price=80.00,
            status=ListingStatusChoices.APPROVED,
            is_active=False,
        )
        res = buyer_auth_client.post(
            '/api/v1/marketplace/favourites/parts/',
            {'part_id': str(inactive_part.id)},
            format='json',
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert not BuyerFavouritePart.objects.filter(user=buyer_user, part=inactive_part).exists()

    # =========================================================================
    # 2. Listing & Removal
    # =========================================================================

    def test_buyer_can_list_and_remove_own_part_favourites(
        self, buyer_auth_client, buyer_user, approved_part, second_approved_part
    ):
        # Favourite two parts
        buyer_auth_client.post(
            '/api/v1/marketplace/favourites/parts/',
            {'part_id': str(approved_part.id)},
            format='json',
        )
        buyer_auth_client.post(
            '/api/v1/marketplace/favourites/parts/',
            {'part_id': str(second_approved_part.id)},
            format='json',
        )

        # List favourites
        list_res = buyer_auth_client.get('/api/v1/marketplace/favourites/parts/')
        assert list_res.status_code == status.HTTP_200_OK
        data = list_res.json()
        items = data if isinstance(data, list) else data.get('results', [])
        assert len(items) == 2
        returned_part_ids = [item['part_id'] for item in items]
        assert str(approved_part.id) in returned_part_ids
        assert str(second_approved_part.id) in returned_part_ids

        # Remove first part by part_id
        del_res = buyer_auth_client.delete(f'/api/v1/marketplace/favourites/parts/{approved_part.id}/')
        assert del_res.status_code == status.HTTP_204_NO_CONTENT

        # List again -> only second part remains
        list_res2 = buyer_auth_client.get('/api/v1/marketplace/favourites/parts/')
        items2 = list_res2.json() if isinstance(list_res2.json(), list) else list_res2.json().get('results', [])
        assert len(items2) == 1
        assert items2[0]['part_id'] == str(second_approved_part.id)

    def test_buyer_a_cannot_view_or_remove_buyer_b_part_favourites(
        self, buyer_auth_client, buyer_user, other_buyer_user, approved_part, second_approved_part, api_client
    ):
        # Buyer A favourites part 1
        fav_a = BuyerFavouritePart.objects.create(user=buyer_user, part=approved_part)
        # Buyer B favourites part 2
        fav_b = BuyerFavouritePart.objects.create(user=other_buyer_user, part=second_approved_part)

        # Buyer A lists favourites -> only sees part 1
        res_a = buyer_auth_client.get('/api/v1/marketplace/favourites/parts/')
        items_a = res_a.json() if isinstance(res_a.json(), list) else res_a.json().get('results', [])
        assert len(items_a) == 1
        assert items_a[0]['part_id'] == str(approved_part.id)

        # Buyer A attempts to remove Buyer B's favourite
        del_res = buyer_auth_client.delete(f'/api/v1/marketplace/favourites/parts/{fav_b.id}/')
        assert del_res.status_code == status.HTTP_404_NOT_FOUND

        # Buyer B's favourite is still in the database
        assert BuyerFavouritePart.objects.filter(id=fav_b.id).exists()

        # Buyer B lists favourites -> only sees part 2
        api_client.force_authenticate(user=other_buyer_user)
        res_b = api_client.get('/api/v1/marketplace/favourites/parts/')
        items_b = res_b.json() if isinstance(res_b.json(), list) else res_b.json().get('results', [])
        assert len(items_b) == 1
        assert items_b[0]['part_id'] == str(second_approved_part.id)

    def test_client_cannot_spoof_another_buyer_identity_for_part(
        self, buyer_auth_client, buyer_user, other_buyer_user, approved_part
    ):
        # Client passes user_id / buyer_id in payload attempting to save for other_buyer_user
        res = buyer_auth_client.post(
            '/api/v1/marketplace/favourites/parts/',
            {
                'part_id': str(approved_part.id),
                'user_id': str(other_buyer_user.id),
                'buyer_id': str(other_buyer_user.id),
                'user': str(other_buyer_user.id),
            },
            format='json',
        )
        assert res.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED)

        # Verified: Favourite was created for buyer_user (request.user), NOT other_buyer_user
        fav = BuyerFavouritePart.objects.get(part=approved_part)
        assert fav.user == buyer_user
        assert not BuyerFavouritePart.objects.filter(user=other_buyer_user).exists()

    def test_unauthenticated_requests_for_parts_are_rejected(self, api_client, approved_part):
        # GET
        assert api_client.get('/api/v1/marketplace/favourites/parts/').status_code == status.HTTP_401_UNAUTHORIZED
        # POST
        assert api_client.post(
            '/api/v1/marketplace/favourites/parts/',
            {'part_id': str(approved_part.id)},
            format='json',
        ).status_code == status.HTTP_401_UNAUTHORIZED
        # DELETE
        assert api_client.delete(
            f'/api/v1/marketplace/favourites/parts/{approved_part.id}/'
        ).status_code == status.HTTP_401_UNAUTHORIZED

    def test_seller_only_and_workshop_only_cannot_access_buyer_part_favourites(
        self, seller_auth_client, workshop_user, approved_part, api_client
    ):
        # Seller-only user (holds only SELLER, no BUYER role)
        assert seller_auth_client.get('/api/v1/marketplace/favourites/parts/').status_code == status.HTTP_403_FORBIDDEN
        assert seller_auth_client.post(
            '/api/v1/marketplace/favourites/parts/',
            {'part_id': str(approved_part.id)},
            format='json',
        ).status_code == status.HTTP_403_FORBIDDEN

        # Workshop-only user (holds only WORKSHOP, no BUYER role)
        api_client.force_authenticate(user=workshop_user)
        assert api_client.get('/api/v1/marketplace/favourites/parts/').status_code == status.HTTP_403_FORBIDDEN
        assert api_client.post(
            '/api/v1/marketplace/favourites/parts/',
            {'part_id': str(approved_part.id)},
            format='json',
        ).status_code == status.HTTP_403_FORBIDDEN

    def test_previously_favourited_part_becoming_unavailable_does_not_break_response(
        self, buyer_auth_client, buyer_user, approved_part
    ):
        # Favourite active approved part
        fav = BuyerFavouritePart.objects.create(user=buyer_user, part=approved_part)

        # Part subsequently becomes unapproved and inactive
        approved_part.status = ListingStatusChoices.CHANGES_REQUESTED
        approved_part.is_active = False
        approved_part.save()

        # Listing endpoint still succeeds gracefully
        res = buyer_auth_client.get('/api/v1/marketplace/favourites/parts/')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        items = data if isinstance(data, list) else data.get('results', [])
        assert len(items) == 1
        assert items[0]['part_id'] == str(approved_part.id)
        assert items[0]['is_available'] is False

        # Buyer can still remove it cleanly
        del_res = buyer_auth_client.delete(f'/api/v1/marketplace/favourites/parts/{fav.id}/')
        assert del_res.status_code == status.HTTP_204_NO_CONTENT
        assert not BuyerFavouritePart.objects.filter(id=fav.id).exists()

    def test_safe_repeated_part_removals(self, buyer_auth_client, buyer_user, approved_part):
        fav = BuyerFavouritePart.objects.create(user=buyer_user, part=approved_part)

        # First removal
        del1 = buyer_auth_client.delete(f'/api/v1/marketplace/favourites/parts/{fav.id}/')
        assert del1.status_code == status.HTTP_204_NO_CONTENT

        # Second removal of already removed favourite
        del2 = buyer_auth_client.delete(f'/api/v1/marketplace/favourites/parts/{fav.id}/')
        assert del2.status_code == status.HTTP_204_NO_CONTENT

    def test_part_url_alias_favorites_works(self, buyer_auth_client, approved_part):
        # Test US spelling alias
        res = buyer_auth_client.post(
            '/api/v1/marketplace/favorites/parts/',
            {'part_id': str(approved_part.id)},
            format='json',
        )
        assert res.status_code == status.HTTP_201_CREATED

        list_res = buyer_auth_client.get('/api/v1/marketplace/favorites/parts/')
        assert list_res.status_code == status.HTTP_200_OK
