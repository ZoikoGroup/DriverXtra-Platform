import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.storage import default_storage
from rest_framework import status
from apps.identity.models import User, RoleChoices
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
)


def make_dummy_jpeg(name="test_photo.jpg", size_bytes=200):
    header = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
    body = b'\x00' * max(0, size_bytes - len(header))
    return SimpleUploadedFile(name, header + body, content_type="image/jpeg")


def make_dummy_png(name="test_photo.png", size_bytes=200):
    header = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4'
    body = b'\x00' * max(0, size_bytes - len(header))
    return SimpleUploadedFile(name, header + body, content_type="image/png")


def make_dummy_webp(name="test_photo.webp", size_bytes=200):
    header = b'RIFF' + (size_bytes - 8).to_bytes(4, 'little') + b'WEBPVP8 ' + (size_bytes - 20).to_bytes(4, 'little')
    body = b'\x00' * max(0, size_bytes - len(header))
    return SimpleUploadedFile(name, header + body, content_type="image/webp")


@pytest.fixture
def make_audi(db):
    return VehicleMake.objects.create(name='Audi', country_of_origin='Germany')


@pytest.fixture
def model_rs6(db, make_audi):
    return VehicleModel.objects.create(
        make=make_audi,
        name='RS6 Avant',
        year_start=2021,
        image_url='https://images.driverxtra.com/catalogue/audi-rs6-official.jpg',
    )


@pytest.fixture
def variant_rs6(db, model_rs6):
    return VehicleVariant.objects.create(
        model=model_rs6,
        name='V8 Performance',
        year=2023,
        engine_code='DJP',
        fuel_type=FuelTypeChoices.PETROL,
        transmission=TransmissionChoices.AUTOMATIC,
        power_bhp=591,
    )


@pytest.fixture
def exhaust_category(db):
    return PartCategory.objects.create(name='Exhaust Systems', slug='exhaust-systems')


@pytest.fixture
def other_seller(db):
    user = User.objects.create_user(
        email='other_seller@driverxtra.com',
        password='SecurePassword123!',
        first_name='Other',
        last_name='Seller',
        phone_number='+447000000088',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.SELLER)
    return user


@pytest.fixture
def other_seller_client(other_seller):
    from rest_framework.test import APIClient
    client = APIClient()
    client.force_authenticate(user=other_seller)
    return client


@pytest.mark.django_db
class TestImageUploadApi:

    def test_unauthenticated_upload_rejected(self, api_client):
        file = make_dummy_jpeg()
        response = api_client.post(
            '/api/v1/marketplace/upload-image/',
            {'file': file},
            format='multipart'
        )
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    def test_successful_single_jpeg_upload(self, seller_auth_client):
        file = make_dummy_jpeg("car_front.jpg")
        response = seller_auth_client.post(
            '/api/v1/marketplace/upload-image/',
            {'file': file, 'listing_type': 'vehicle'},
            format='multipart'
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data['status'] == 'success'
        assert 'id' in data
        assert 'url' in data
        assert data['url'].startswith('/media/uploads/vehicles/')
        assert data['url'].endswith('.jpg')
        assert data['filename'] == 'car_front.jpg'

    def test_successful_single_png_upload(self, seller_auth_client):
        file = make_dummy_png("part_diagram.png")
        response = seller_auth_client.post(
            '/api/v1/marketplace/upload-image/',
            {'file': file, 'listing_type': 'part'},
            format='multipart'
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data['status'] == 'success'
        assert data['url'].startswith('/media/uploads/parts/')
        assert data['url'].endswith('.png')

    def test_successful_single_webp_upload(self, seller_auth_client):
        file = make_dummy_webp("catalogue_press.webp")
        response = seller_auth_client.post(
            '/api/v1/marketplace/upload-image/',
            {'file': file, 'listing_type': 'catalogue'},
            format='multipart'
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data['status'] == 'success'
        assert data['url'].startswith('/media/uploads/catalogues/')
        assert data['url'].endswith('.webp')

    def test_successful_multiple_files_upload(self, seller_auth_client):
        files = [
            make_dummy_jpeg("photo1.jpg"),
            make_dummy_png("photo2.png"),
            make_dummy_webp("photo3.webp"),
        ]
        response = seller_auth_client.post(
            '/api/v1/marketplace/upload-image/',
            {'files': files, 'listing_type': 'vehicle'},
            format='multipart'
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data['status'] == 'success'
        assert data['count'] == 3
        assert len(data['images']) == 3

    def test_unsupported_file_extension_rejected(self, seller_auth_client):
        text_file = SimpleUploadedFile("notes.txt", b"Hello text file", content_type="text/plain")
        response = seller_auth_client.post(
            '/api/v1/marketplace/upload-image/',
            {'file': text_file},
            format='multipart'
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert 'unsupported extension' in str(data).lower()

    def test_spoofed_mime_type_with_invalid_magic_bytes_rejected(self, seller_auth_client):
        spoofed = SimpleUploadedFile("fake_photo.jpg", b"PK\x03\x04ThisIsAZipFileNotAJpeg", content_type="image/jpeg")
        response = seller_auth_client.post(
            '/api/v1/marketplace/upload-image/',
            {'file': spoofed},
            format='multipart'
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert 'invalid or corrupted image data' in str(data).lower()

    def test_oversized_file_rejected(self, seller_auth_client):
        # Header + 6MB of data (exceeds default 5MB limit)
        header = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
        oversized = SimpleUploadedFile("huge.jpg", header + b'\x00' * (6 * 1024 * 1024), content_type="image/jpeg")
        response = seller_auth_client.post(
            '/api/v1/marketplace/upload-image/',
            {'file': oversized},
            format='multipart'
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert 'exceeds the maximum allowed size' in str(data).lower()

    def test_upload_exceeding_10_files_at_once_rejected(self, seller_auth_client):
        files = [make_dummy_jpeg(f"img_{i}.jpg") for i in range(11)]
        response = seller_auth_client.post(
            '/api/v1/marketplace/upload-image/',
            {'files': files},
            format='multipart'
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert 'cannot upload more than 10 images' in str(data).lower()

    def test_seller_cannot_upload_to_other_sellers_listing(
        self, other_seller_client, seller_user, make_audi, model_rs6, variant_rs6
    ):
        # Create listing owned by seller_user
        listing = VehicleListing.objects.create(
            seller=seller_user,
            title="Seller's Audi RS6",
            make=make_audi,
            model=model_rs6,
            variant=variant_rs6,
            year=2023,
            price=85000,
            status=ListingStatusChoices.DRAFT,
        )

        # other_seller attempts to upload to this listing
        file = make_dummy_jpeg("unauthorized.jpg")
        response = other_seller_client.post(
            '/api/v1/marketplace/upload-image/',
            {'file': file, 'listing_type': 'vehicle', 'listing_id': str(listing.id)},
            format='multipart'
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_upload_exceeding_listing_max_10_photos_rejected(
        self, seller_auth_client, seller_user, make_audi, model_rs6, variant_rs6
    ):
        # Listing already has 9 photos
        existing_photos = [f"/media/uploads/vehicles/2026/10/img_{i}.jpg" for i in range(9)]
        listing = VehicleListing.objects.create(
            seller=seller_user,
            title="Nearly Full Gallery Audi",
            make=make_audi,
            model=model_rs6,
            variant=variant_rs6,
            year=2023,
            price=85000,
            images=existing_photos,
            primary_image_url=existing_photos[0],
            status=ListingStatusChoices.DRAFT,
        )

        # Attempt to upload 2 more photos (9 + 2 = 11 > 10)
        files = [make_dummy_jpeg("extra1.jpg"), make_dummy_jpeg("extra2.jpg")]
        response = seller_auth_client.post(
            '/api/v1/marketplace/upload-image/',
            {'files': files, 'listing_type': 'vehicle', 'listing_id': str(listing.id)},
            format='multipart'
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert 'exceed the maximum limit of 10 photos' in str(data).lower()

    def test_delete_uploaded_image(self, seller_auth_client):
        # Upload an image first
        file = make_dummy_jpeg("to_delete.jpg")
        upload_res = seller_auth_client.post(
            '/api/v1/marketplace/upload-image/',
            {'file': file, 'listing_type': 'vehicle'},
            format='multipart'
        )
        assert upload_res.status_code == status.HTTP_201_CREATED
        url = upload_res.json()['url']

        # Delete image
        delete_res = seller_auth_client.delete(
            '/api/v1/marketplace/upload-image/',
            {'url': url},
            format='json'
        )
        assert delete_res.status_code == status.HTTP_200_OK
        assert delete_res.json()['status'] == 'success'


@pytest.mark.django_db
class TestVehicleAndPartListingCreationWithUploadedImages:

    def test_create_vehicle_listing_with_uploaded_media_urls(
        self, seller_auth_client, make_audi, model_rs6, variant_rs6
    ):
        # Upload two photos
        f1 = make_dummy_jpeg("exterior.jpg")
        f2 = make_dummy_jpeg("cockpit.jpg")
        up1 = seller_auth_client.post('/api/v1/marketplace/upload-image/', {'file': f1, 'listing_type': 'vehicle'}, format='multipart')
        up2 = seller_auth_client.post('/api/v1/marketplace/upload-image/', {'file': f2, 'listing_type': 'vehicle'}, format='multipart')
        url1 = up1.json()['url']
        url2 = up2.json()['url']

        # Create vehicle listing using these media URLs
        payload = {
            'title': '2023 Audi RS6 Avant Performance',
            'make': str(make_audi.id),
            'model': str(model_rs6.id),
            'variant': str(variant_rs6.id),
            'year': 2023,
            'price': '89500.00',
            'mileage': 12000,
            'fuel_type': 'PETROL',
            'transmission': 'AUTOMATIC',
            'body_type': 'Estate',
            'primary_image_url': url1,
            'images': [url1, url2],
            'description': 'Pristine condition RS6 Avant with twin-turbo V8.',
            'status': 'DRAFT',
        }
        res = seller_auth_client.post('/api/v1/marketplace/vehicles/', payload, format='json')
        assert res.status_code == status.HTTP_201_CREATED, res.data
        data = res.json()
        assert data['primary_image_url'] == url1
        assert len(data['images']) == 2
        assert url1 in data['images']
        assert url2 in data['images']

    def test_create_spare_part_listing_with_uploaded_media_urls(
        self, seller_auth_client, exhaust_category
    ):
        f = make_dummy_png("exhaust_downpipe.png")
        up = seller_auth_client.post('/api/v1/marketplace/upload-image/', {'file': f, 'listing_type': 'part'}, format='multipart')
        part_url = up.json()['url']

        payload = {
            'name': 'Audi RS6 Titanium Sport Exhaust Downpipe',
            'brand': 'Akrapovic',
            'mpn': 'AKR-RS6-2023',
            'category': str(exhaust_category.id),
            'price': '3450.00',
            'stock_quantity': 4,
            'condition': 'NEW',
            'primary_image_url': part_url,
            'images': [part_url],
            'status': 'DRAFT',
        }
        res = seller_auth_client.post('/api/v1/marketplace/parts/', payload, format='json')
        assert res.status_code == status.HTTP_201_CREATED, res.data
        data = res.json()
        assert data['primary_image_url'] == part_url
        assert data['images'] == [part_url]


@pytest.mark.django_db
class TestCataloguePhotoProposalUploadAndReviewWorkflow:

    def test_seller_proposes_catalogue_photo_via_upload_and_admin_approves(
        self, seller_auth_client, admin_user, model_rs6
    ):
        # 1. Upload photo file
        photo = make_dummy_jpeg("high_res_rs6.jpg")
        upload_res = seller_auth_client.post(
            '/api/v1/marketplace/upload-image/',
            {'file': photo, 'listing_type': 'catalogue'},
            format='multipart'
        )
        proposed_url = upload_res.json()['url']

        # 2. Submit proposal
        proposal_payload = {
            'model': str(model_rs6.id),
            'proposed_image_url': proposed_url,
            'notes': 'High-resolution press photo from official Audi media room.',
        }
        prop_res = seller_auth_client.post('/api/v1/catalogue/photo-proposals/', proposal_payload, format='json')
        assert prop_res.status_code == status.HTTP_201_CREATED, prop_res.data
        proposal_id = prop_res.json()['id']
        assert prop_res.json()['status'] == 'PENDING'

        # Canonical model image must NOT change while pending
        model_rs6.refresh_from_db()
        assert model_rs6.image_url == 'https://images.driverxtra.com/catalogue/audi-rs6-official.jpg'

        # 3. Admin approves proposal
        from rest_framework.test import APIClient
        admin_client = APIClient()
        admin_client.force_authenticate(user=admin_user)

        review_res = admin_client.post(
            f'/api/v1/catalogue/photo-proposals/{proposal_id}/review/',
            {'action': 'APPROVE', 'admin_notes': 'Verified genuine press image.'},
            format='json'
        )
        assert review_res.status_code == status.HTTP_200_OK

        # 4. Verify canonical catalogue image updated to approved image
        model_rs6.refresh_from_db()
        assert model_rs6.image_url == proposed_url

    def test_seller_proposes_catalogue_photo_and_admin_rejects(
        self, seller_auth_client, admin_user, model_rs6
    ):
        photo = make_dummy_jpeg("low_res.jpg")
        upload_res = seller_auth_client.post(
            '/api/v1/marketplace/upload-image/',
            {'file': photo, 'listing_type': 'catalogue'},
            format='multipart'
        )
        proposed_url = upload_res.json()['url']

        prop_res = seller_auth_client.post(
            '/api/v1/catalogue/photo-proposals/',
            {
                'model': str(model_rs6.id),
                'proposed_image_url': proposed_url,
                'notes': 'Mobile phone snapshot.',
            },
            format='json'
        )
        assert prop_res.status_code == status.HTTP_201_CREATED, prop_res.data
        proposal_id = prop_res.json()['id']

        # Admin rejects
        from rest_framework.test import APIClient
        admin_client = APIClient()
        admin_client.force_authenticate(user=admin_user)

        review_res = admin_client.post(
            f'/api/v1/catalogue/photo-proposals/{proposal_id}/review/',
            {'action': 'REJECT', 'rejection_reason': 'Photo is low resolution and poorly lit.'},
            format='json'
        )
        assert review_res.status_code == status.HTTP_200_OK

        # Canonical model image must remain untouched
        model_rs6.refresh_from_db()
        assert model_rs6.image_url == 'https://images.driverxtra.com/catalogue/audi-rs6-official.jpg'
