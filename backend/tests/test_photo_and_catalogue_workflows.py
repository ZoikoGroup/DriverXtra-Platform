import pytest
from rest_framework import status
from apps.identity.models import User, RoleChoices, Permission
from apps.catalogue.models import (
    VehicleMake,
    VehicleModel,
    VehicleVariant,
    PartCategory,
    FuelTypeChoices,
    TransmissionChoices,
    VehicleCatalogueApplication,
    CataloguePhotoProposal,
    CatalogueApplicationStatusChoices,
)
from apps.marketplace.models import (
    VehicleListing,
    SparePartListing,
    ListingStatusChoices,
    BuyerFavouriteVehicle,
    BuyerFavouritePart,
)


@pytest.fixture
def make_bmw(db):
    return VehicleMake.objects.create(name='BMW', country_of_origin='Germany')


@pytest.fixture
def model_m3(db, make_bmw):
    return VehicleModel.objects.create(
        make=make_bmw,
        name='M3',
        year_start=2021,
        image_url='https://images.driverxtra.com/catalogue/bmw-m3-canonical.jpg',
    )


@pytest.fixture
def variant_m3(db, model_m3):
    return VehicleVariant.objects.create(
        model=model_m3,
        name='Competition xDrive',
        year=2023,
        engine_code='S58',
        fuel_type=FuelTypeChoices.PETROL,
        transmission=TransmissionChoices.AUTOMATIC,
        power_bhp=503,
    )


@pytest.fixture
def brakes_category(db):
    return PartCategory.objects.create(name='Braking Systems', slug='braking-systems')


@pytest.fixture
def seller_b_user(db):
    user = User.objects.create_user(
        email='seller_b@driverxtra.com',
        password='SecurePassword123!',
        first_name='Bob',
        last_name='Seller',
        phone_number='+447000000099',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.SELLER)
    return user


@pytest.fixture
def seller_b_auth_client(seller_b_user):
    from rest_framework.test import APIClient
    client = APIClient()
    client.force_authenticate(user=seller_b_user)
    return client


@pytest.fixture
def non_superuser_admin(db):
    user = User.objects.create_user(
        email='admin_nosuper@driverxtra.com',
        password='AdminPassword123!',
        first_name='Admin',
        last_name='NoSuper',
        is_staff=True,
        is_email_verified=True,
    )
    user.add_role(RoleChoices.ADMIN)
    return user


@pytest.fixture
def non_superuser_admin_client(non_superuser_admin):
    from rest_framework.test import APIClient
    client = APIClient()
    client.force_authenticate(user=non_superuser_admin)
    return client


# =============================================================================
# 1. Seller Vehicle and Spare-Part Photo Management
# =============================================================================

@pytest.mark.django_db
class TestSellerPhotoManagement:

    def test_seller_creates_vehicle_listing_with_photos(
        self, seller_auth_client, seller_user, make_bmw, model_m3, variant_m3
    ):
        primary = 'https://images.driverxtra.com/seller/m3-front.jpg'
        photos = [
            primary,
            'https://images.driverxtra.com/seller/m3-rear.jpg',
            'https://images.driverxtra.com/seller/m3-interior.jpg',
        ]
        payload = {
            'title': '2023 BMW M3 Competition xDrive',
            'make': str(make_bmw.id),
            'model': str(model_m3.id),
            'variant': str(variant_m3.id),
            'year': 2023,
            'price': '64950.00',
            'mileage': 8500,
            'fuel_type': FuelTypeChoices.PETROL,
            'transmission': TransmissionChoices.AUTOMATIC,
            'primary_image_url': primary,
            'images': photos,
        }
        res = seller_auth_client.post('/api/v1/marketplace/vehicles/', payload, format='json')
        assert res.status_code == status.HTTP_201_CREATED, res.data
        data = res.data
        assert data['primary_image_url'] == primary
        assert len(data['images']) == 3
        assert primary in data['images']

        # Confirm persisted in DB
        listing = VehicleListing.objects.get(id=data['id'])
        assert listing.primary_image_url == primary
        assert listing.images == photos

    def test_primary_image_auto_synced_into_images_list(
        self, seller_auth_client, seller_user, make_bmw, model_m3, variant_m3
    ):
        primary = 'https://images.driverxtra.com/seller/m3-front.jpg'
        other_photo = 'https://images.driverxtra.com/seller/m3-rear.jpg'
        payload = {
            'title': '2023 BMW M3 Competition',
            'make': str(make_bmw.id),
            'model': str(model_m3.id),
            'variant': str(variant_m3.id),
            'year': 2023,
            'price': '63000.00',
            'mileage': 9000,
            'fuel_type': FuelTypeChoices.PETROL,
            'transmission': TransmissionChoices.AUTOMATIC,
            'primary_image_url': primary,
            'images': [other_photo],
        }
        res = seller_auth_client.post('/api/v1/marketplace/vehicles/', payload, format='json')
        assert res.status_code == status.HTTP_201_CREATED
        assert res.data['primary_image_url'] == primary
        assert primary in res.data['images']
        assert res.data['images'][0] == primary

    def test_seller_updates_vehicle_listing_photos(
        self, seller_auth_client, seller_user, make_bmw, model_m3, variant_m3
    ):
        listing = VehicleListing.objects.create(
            seller=seller_user,
            title='2023 BMW M3',
            make=make_bmw,
            model=model_m3,
            variant=variant_m3,
            year=2023,
            price=60000.00,
            mileage=5000,
            fuel_type=FuelTypeChoices.PETROL,
            transmission=TransmissionChoices.AUTOMATIC,
            primary_image_url='https://images.driverxtra.com/seller/m3-old.jpg',
            images=['https://images.driverxtra.com/seller/m3-old.jpg'],
        )

        new_primary = 'https://images.driverxtra.com/seller/m3-new-primary.jpg'
        new_photos = [
            new_primary,
            'https://images.driverxtra.com/seller/m3-side.jpg',
        ]
        patch_res = seller_auth_client.patch(
            f'/api/v1/marketplace/vehicles/{listing.id}/',
            {'primary_image_url': new_primary, 'images': new_photos},
            format='json',
        )
        assert patch_res.status_code == status.HTTP_200_OK
        listing.refresh_from_db()
        assert listing.primary_image_url == new_primary
        assert listing.images == new_photos

    def test_seller_creates_spare_part_listing_with_photos(
        self, seller_auth_client, seller_user, brakes_category
    ):
        primary = 'https://images.driverxtra.com/parts/caliper-front.jpg'
        photos = [primary, 'https://images.driverxtra.com/parts/caliper-box.jpg']
        payload = {
            'name': 'Brembo 6-Piston Caliper Kit',
            'brand': 'Brembo',
            'mpn': 'BREM-CAL-6P',
            'category': str(brakes_category.id),
            'price': '850.00',
            'stock_quantity': 4,
            'condition': 'NEW',
            'primary_image_url': primary,
            'images': photos,
        }
        res = seller_auth_client.post('/api/v1/marketplace/parts/', payload, format='json')
        assert res.status_code == status.HTTP_201_CREATED, res.data
        assert res.data['primary_image_url'] == primary
        assert res.data['images'] == photos

        part = SparePartListing.objects.get(id=res.data['id'])
        assert part.primary_image_url == primary
        assert part.images == photos


# =============================================================================
# 2. Photo URL and Gallery Validation
# =============================================================================

@pytest.mark.django_db
class TestPhotoValidation:

    def test_exceeding_max_10_images_rejected(
        self, seller_auth_client, make_bmw, model_m3, variant_m3
    ):
        too_many_images = [f'https://images.driverxtra.com/test/{i}.jpg' for i in range(11)]
        payload = {
            'title': '2023 BMW M3',
            'make': str(make_bmw.id),
            'model': str(model_m3.id),
            'variant': str(variant_m3.id),
            'year': 2023,
            'price': '60000.00',
            'mileage': 5000,
            'fuel_type': FuelTypeChoices.PETROL,
            'transmission': TransmissionChoices.AUTOMATIC,
            'images': too_many_images,
        }
        res = seller_auth_client.post('/api/v1/marketplace/vehicles/', payload, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        err_msg = str(res.data)
        assert 'Cannot exceed 10 images' in err_msg or 'images' in err_msg

    def test_invalid_image_url_format_rejected(
        self, seller_auth_client, make_bmw, model_m3, variant_m3
    ):
        payload = {
            'title': '2023 BMW M3',
            'make': str(make_bmw.id),
            'model': str(model_m3.id),
            'variant': str(variant_m3.id),
            'year': 2023,
            'price': '60000.00',
            'mileage': 5000,
            'fuel_type': FuelTypeChoices.PETROL,
            'transmission': TransmissionChoices.AUTOMATIC,
            'primary_image_url': 'javascript:alert(1)',
            'images': ['not-a-valid-url'],
        }
        res = seller_auth_client.post('/api/v1/marketplace/vehicles/', payload, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST


# =============================================================================
# 3. Ownership and Unauthorized Modifications
# =============================================================================

@pytest.mark.django_db
class TestPhotoOwnershipAndSecurity:

    def test_seller_b_cannot_update_seller_a_vehicle_photos(
        self, seller_user, seller_b_auth_client, make_bmw, model_m3, variant_m3
    ):
        listing = VehicleListing.objects.create(
            seller=seller_user,
            title="Seller A's M3",
            make=make_bmw,
            model=model_m3,
            variant=variant_m3,
            year=2023,
            price=60000.00,
            mileage=5000,
            fuel_type=FuelTypeChoices.PETROL,
            transmission=TransmissionChoices.AUTOMATIC,
            primary_image_url='https://images.driverxtra.com/a/car.jpg',
            images=['https://images.driverxtra.com/a/car.jpg'],
        )
        res = seller_b_auth_client.patch(
            f'/api/v1/marketplace/vehicles/{listing.id}/',
            {'primary_image_url': 'https://images.driverxtra.com/hacked/car.jpg'},
            format='json',
        )
        assert res.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)
        listing.refresh_from_db()
        assert listing.primary_image_url == 'https://images.driverxtra.com/a/car.jpg'

    def test_seller_b_cannot_update_seller_a_part_photos(
        self, seller_user, seller_b_auth_client, brakes_category
    ):
        part = SparePartListing.objects.create(
            seller=seller_user,
            name="Seller A's Brake Pads",
            brand='Brembo',
            mpn='P 06 088',
            category=brakes_category,
            price=65.00,
            stock_quantity=10,
            primary_image_url='https://images.driverxtra.com/a/pads.jpg',
        )
        res = seller_b_auth_client.patch(
            f'/api/v1/marketplace/parts/{part.id}/',
            {'primary_image_url': 'https://images.driverxtra.com/hacked/pads.jpg'},
            format='json',
        )
        assert res.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)
        part.refresh_from_db()
        assert part.primary_image_url == 'https://images.driverxtra.com/a/pads.jpg'

    def test_unauthenticated_client_cannot_modify_listing_photos(
        self, api_client, seller_user, make_bmw, model_m3, variant_m3
    ):
        listing = VehicleListing.objects.create(
            seller=seller_user,
            title="Seller A's M3",
            make=make_bmw,
            model=model_m3,
            variant=variant_m3,
            year=2023,
            price=60000.00,
            mileage=5000,
            fuel_type=FuelTypeChoices.PETROL,
            transmission=TransmissionChoices.AUTOMATIC,
        )
        res = api_client.patch(
            f'/api/v1/marketplace/vehicles/{listing.id}/',
            {'primary_image_url': 'https://images.driverxtra.com/unauth.jpg'},
            format='json',
        )
        assert res.status_code == status.HTTP_401_UNAUTHORIZED


# =============================================================================
# 4. Vehicle Catalogue Application Workflow
# =============================================================================

@pytest.mark.django_db
class TestVehicleCatalogueApplicationWorkflow:

    def test_seller_submits_catalogue_application_pending_status(
        self, seller_auth_client, make_bmw
    ):
        app_photos = [
            'https://images.driverxtra.com/proposals/m2-front.jpg',
            'https://images.driverxtra.com/proposals/m2-rear.jpg',
        ]
        payload = {
            'make': str(make_bmw.id),
            'make_name': 'BMW',
            'model_name': 'M2 CS',
            'year_start': 2024,
            'year_end': None,
            'variant_name': 'M2 CS Manual',
            'year': 2024,
            'fuel_type': FuelTypeChoices.PETROL,
            'transmission': TransmissionChoices.MANUAL,
            'power_bhp': 473,
            'primary_image_url': app_photos[0],
            'images': app_photos,
            'notes': 'New upcoming limited edition M2 CS model not currently in the approved catalogue.',
        }
        res = seller_auth_client.post('/api/v1/catalogue/applications/', payload, format='json')
        assert res.status_code == status.HTTP_201_CREATED, res.data
        data = res.data
        assert data['status'] == CatalogueApplicationStatusChoices.PENDING
        assert data['model_name'] == 'M2 CS'
        assert data['primary_image_url'] == app_photos[0]
        assert data['images'] == app_photos

        # Verify application is NOT in official approved catalogue models
        cat_res = seller_auth_client.get(f'/api/v1/catalogue/models/?make_id={make_bmw.id}')
        assert cat_res.status_code == status.HTTP_200_OK
        models_data = cat_res.data.get('results', cat_res.data) if isinstance(cat_res.data, dict) else cat_res.data
        catalogue_model_names = [m['name'] for m in models_data]
        assert 'M2 CS' not in catalogue_model_names

    def test_admin_approves_catalogue_application(
        self, seller_user, admin_auth_client, make_bmw
    ):
        app = VehicleCatalogueApplication.objects.create(
            seller=seller_user,
            make=make_bmw,
            make_name='BMW',
            model_name='M4 CSL',
            year_start=2023,
            variant_name='CSL Lightweight',
            year=2023,
            fuel_type=FuelTypeChoices.PETROL,
            transmission=TransmissionChoices.AUTOMATIC,
            power_bhp=543,
            primary_image_url='https://images.driverxtra.com/proposals/m4-csl.jpg',
            images=['https://images.driverxtra.com/proposals/m4-csl.jpg'],
            status=CatalogueApplicationStatusChoices.PENDING,
        )

        review_payload = {
            'action': 'APPROVE',
            'admin_notes': 'Verified against BMW official press release specifications.',
        }
        res = admin_auth_client.post(
            f'/api/v1/catalogue/applications/{app.id}/review/',
            review_payload,
            format='json',
        )
        assert res.status_code == status.HTTP_200_OK, res.data
        assert res.data['application']['status'] == CatalogueApplicationStatusChoices.APPROVED

        # Verify VehicleModel and VehicleVariant were automatically created
        created_model = VehicleModel.objects.get(make=make_bmw, name='M4 CSL')
        assert created_model.image_url == 'https://images.driverxtra.com/proposals/m4-csl.jpg'
        assert created_model.year_start == 2023

        created_variant = VehicleVariant.objects.get(model=created_model, name='CSL Lightweight')
        assert created_variant.power_bhp == 543
        assert created_variant.fuel_type == FuelTypeChoices.PETROL

        # Verify model now appears in official catalogue models
        cat_res = admin_auth_client.get(f'/api/v1/catalogue/models/?make_id={make_bmw.id}')
        assert cat_res.status_code == status.HTTP_200_OK
        models_data = cat_res.data.get('results', cat_res.data) if isinstance(cat_res.data, dict) else cat_res.data
        catalogue_model_names = [m['name'] for m in models_data]
        assert 'M4 CSL' in catalogue_model_names

    def test_admin_rejects_catalogue_application(
        self, seller_user, admin_auth_client, make_bmw
    ):
        app = VehicleCatalogueApplication.objects.create(
            seller=seller_user,
            make=make_bmw,
            make_name='BMW',
            model_name='Fictional Car 9000',
            year_start=2030,
            status=CatalogueApplicationStatusChoices.PENDING,
        )

        res = admin_auth_client.post(
            f'/api/v1/catalogue/applications/{app.id}/review/',
            {
                'action': 'REJECT',
                'rejection_reason': 'Vehicle model does not exist or lacks manufacturer documentation.',
            },
            format='json',
        )
        assert res.status_code == status.HTTP_200_OK
        app.refresh_from_db()
        assert app.status == CatalogueApplicationStatusChoices.REJECTED
        assert 'does not exist' in app.rejection_reason

        # Ensure no catalogue model was created
        assert not VehicleModel.objects.filter(name='Fictional Car 9000').exists()

    def test_non_superuser_author_cannot_self_approve_application(
        self, non_superuser_admin, non_superuser_admin_client, make_bmw
    ):
        app = VehicleCatalogueApplication.objects.create(
            seller=non_superuser_admin,
            make=make_bmw,
            make_name='BMW',
            model_name='M8 Competition',
            year_start=2022,
            status=CatalogueApplicationStatusChoices.PENDING,
        )

        res = non_superuser_admin_client.post(
            f'/api/v1/catalogue/applications/{app.id}/review/',
            {'action': 'APPROVE'},
            format='json',
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert 'Self-approval violation' in res.data['error']


# =============================================================================
# 5. Catalogue Photo Proposals
# =============================================================================

@pytest.mark.django_db
class TestCataloguePhotoProposalWorkflow:

    def test_seller_proposes_catalogue_photo_pending_status(
        self, seller_auth_client, model_m3
    ):
        proposed_url = 'https://images.driverxtra.com/canonical/m3-facelift.jpg'
        payload = {
            'model': str(model_m3.id),
            'proposed_image_url': proposed_url,
            'notes': 'Official press photo for the 2024 LCI facelift model.',
        }
        res = seller_auth_client.post('/api/v1/catalogue/photo-proposals/', payload, format='json')
        assert res.status_code == status.HTTP_201_CREATED, res.data
        assert res.data['status'] == CatalogueApplicationStatusChoices.PENDING
        assert res.data['proposed_image_url'] == proposed_url

        # Canonical model image must NOT change while proposal is pending
        model_m3.refresh_from_db()
        assert model_m3.image_url == 'https://images.driverxtra.com/catalogue/bmw-m3-canonical.jpg'

    def test_admin_approves_catalogue_photo_proposal(
        self, seller_user, admin_auth_client, model_m3
    ):
        proposed_url = 'https://images.driverxtra.com/canonical/m3-new-approved.jpg'
        proposal = CataloguePhotoProposal.objects.create(
            seller=seller_user,
            model=model_m3,
            proposed_image_url=proposed_url,
            status=CatalogueApplicationStatusChoices.PENDING,
        )

        res = admin_auth_client.post(
            f'/api/v1/catalogue/photo-proposals/{proposal.id}/review/',
            {'action': 'APPROVE', 'admin_notes': 'High quality official press shot.'},
            format='json',
        )
        assert res.status_code == status.HTTP_200_OK
        proposal.refresh_from_db()
        assert proposal.status == CatalogueApplicationStatusChoices.APPROVED

        # Canonical model image must now be updated
        model_m3.refresh_from_db()
        assert model_m3.image_url == proposed_url

    def test_admin_rejects_catalogue_photo_proposal(
        self, seller_user, admin_auth_client, model_m3
    ):
        original_canonical = model_m3.image_url
        proposal = CataloguePhotoProposal.objects.create(
            seller=seller_user,
            model=model_m3,
            proposed_image_url='https://images.driverxtra.com/low-res-shot.jpg',
            status=CatalogueApplicationStatusChoices.PENDING,
        )

        res = admin_auth_client.post(
            f'/api/v1/catalogue/photo-proposals/{proposal.id}/review/',
            {'action': 'REJECT', 'rejection_reason': 'Resolution is too low and has watermarks.'},
            format='json',
        )
        assert res.status_code == status.HTTP_200_OK
        proposal.refresh_from_db()
        assert proposal.status == CatalogueApplicationStatusChoices.REJECTED

        # Canonical model image must be preserved
        model_m3.refresh_from_db()
        assert model_m3.image_url == original_canonical


# =============================================================================
# 6. Separation Between Catalogue and Seller Listing Images
# =============================================================================

@pytest.mark.django_db
class TestSeparationBetweenCatalogueAndSellerImages:

    def test_seller_listing_photos_do_not_modify_catalogue_image(
        self, seller_auth_client, seller_user, make_bmw, model_m3, variant_m3
    ):
        canonical_image_before = model_m3.image_url
        listing_photo = 'https://images.driverxtra.com/seller-private/car.jpg'

        res = seller_auth_client.post(
            '/api/v1/marketplace/vehicles/',
            {
                'title': 'BMW M3 Individual Color',
                'make': str(make_bmw.id),
                'model': str(model_m3.id),
                'variant': str(variant_m3.id),
                'year': 2023,
                'price': '70000.00',
                'mileage': 2000,
                'fuel_type': FuelTypeChoices.PETROL,
                'transmission': TransmissionChoices.AUTOMATIC,
                'primary_image_url': listing_photo,
                'images': [listing_photo],
            },
            format='json',
        )
        assert res.status_code == status.HTTP_201_CREATED

        # Ensure catalogue model image is unaffected
        model_m3.refresh_from_db()
        assert model_m3.image_url == canonical_image_before
        assert model_m3.image_url != listing_photo

    def test_catalogue_photo_approval_does_not_modify_seller_listing_photos(
        self, seller_user, admin_auth_client, make_bmw, model_m3, variant_m3
    ):
        seller_photo = 'https://images.driverxtra.com/seller-unique/unit-123.jpg'
        listing = VehicleListing.objects.create(
            seller=seller_user,
            title='BMW M3 For Sale',
            make=make_bmw,
            model=model_m3,
            variant=variant_m3,
            year=2023,
            price=60000.00,
            mileage=5000,
            fuel_type=FuelTypeChoices.PETROL,
            transmission=TransmissionChoices.AUTOMATIC,
            primary_image_url=seller_photo,
            images=[seller_photo],
        )

        # Propose and approve a new catalogue photo
        new_catalogue_url = 'https://images.driverxtra.com/canonical/bmw-m3-2024.jpg'
        proposal = CataloguePhotoProposal.objects.create(
            seller=seller_user,
            model=model_m3,
            proposed_image_url=new_catalogue_url,
            status=CatalogueApplicationStatusChoices.PENDING,
        )
        admin_auth_client.post(
            f'/api/v1/catalogue/photo-proposals/{proposal.id}/review/',
            {'action': 'APPROVE'},
            format='json',
        )

        # Listing photo must remain the seller's specific unit photo
        listing.refresh_from_db()
        assert listing.primary_image_url == seller_photo
        assert listing.images == [seller_photo]


# =============================================================================
# 7. Regression: Favourites with Multi-Photo Listings
# =============================================================================

@pytest.mark.django_db
class TestFavouritesWithMultiPhotoListings:

    def test_buyer_favourites_vehicle_with_photos(
        self, buyer_auth_client, buyer_user, seller_user, make_bmw, model_m3, variant_m3
    ):
        photos = [
            'https://images.driverxtra.com/v/1.jpg',
            'https://images.driverxtra.com/v/2.jpg',
            'https://images.driverxtra.com/v/3.jpg',
        ]
        listing = VehicleListing.objects.create(
            seller=seller_user,
            title='2023 BMW M3 Competition',
            make=make_bmw,
            model=model_m3,
            variant=variant_m3,
            year=2023,
            price=65000.00,
            mileage=6000,
            fuel_type=FuelTypeChoices.PETROL,
            transmission=TransmissionChoices.AUTOMATIC,
            primary_image_url=photos[0],
            images=photos,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )

        fav_res = buyer_auth_client.post(
            '/api/v1/marketplace/favourites/',
            {'vehicle_id': str(listing.id)},
            format='json',
        )
        assert fav_res.status_code == status.HTTP_201_CREATED
        assert fav_res.data['vehicle']['primary_image_url'] == photos[0]

        # List favourites
        list_res = buyer_auth_client.get('/api/v1/marketplace/favourites/')
        assert list_res.status_code == status.HTTP_200_OK
        results = list_res.data.get('results', list_res.data)
        assert len(results) == 1
        assert results[0]['vehicle']['primary_image_url'] == photos[0]
        assert results[0]['vehicle']['images'] == photos
