import pytest
from rest_framework import status
from django.utils import timezone
from apps.identity.models import User, RoleChoices
from apps.organisations.models import Organisation, OrganisationMembership, OrganisationRoleChoices, OrganisationTypeChoices
from apps.onboarding.models import SellerApplication, SellerApplicationStatusChoices, BusinessTypeChoices
from apps.catalogue.models import (
    VehicleMake,
    VehicleModel,
    VehicleVariant,
    FuelTypeChoices,
    TransmissionChoices,
)
from apps.marketplace.models import (
    VehicleListing,
    ListingStatusChoices,
    VehicleEnquiry,
    VehicleEnquiryStatusChoices,
)


@pytest.fixture
def make_bmw(db):
    return VehicleMake.objects.create(name='BMW', country_of_origin='Germany')


@pytest.fixture
def model_m3(db, make_bmw):
    return VehicleModel.objects.create(make=make_bmw, name='M3', year_start=2021)


@pytest.fixture
def approved_vehicle(db, seller_user, make_bmw, model_m3):
    return VehicleListing.objects.create(
        seller=seller_user,
        title='2022 BMW M3 Competition',
        make=make_bmw,
        model=model_m3,
        year=2022,
        price=64950.00,
        mileage=12500,
        fuel_type=FuelTypeChoices.PETROL,
        transmission=TransmissionChoices.AUTOMATIC,
        status=ListingStatusChoices.APPROVED,
        is_active=True,
        location_city='Manchester',
        location_postcode='M1 1AA',
    )


@pytest.fixture
def pending_vehicle(db, seller_user, make_bmw, model_m3):
    return VehicleListing.objects.create(
        seller=seller_user,
        title='2021 BMW M3 Draft Listing',
        make=make_bmw,
        model=model_m3,
        year=2021,
        price=58000.00,
        mileage=20000,
        fuel_type=FuelTypeChoices.PETROL,
        transmission=TransmissionChoices.AUTOMATIC,
        status=ListingStatusChoices.PENDING_APPROVAL,
        is_active=True,
        location_city='London',
    )


@pytest.fixture
def approved_seller_app(db, seller_user):
    return SellerApplication.objects.create(
        user=seller_user,
        business_name='Apex Performance Cars Ltd',
        business_type=BusinessTypeChoices.DEALER,
        contact_phone='+44 161 999 8888',
        contact_email='contact@apexperformance.co.uk',
        city='Manchester',
        status=SellerApplicationStatusChoices.APPROVED,
    )


@pytest.fixture
def other_seller(db):
    user = User.objects.create_user(
        email='other_seller@driverxtra.com',
        password='SecurePassword123!',
        first_name='Oliver',
        last_name='Other',
        phone_number='+447000000099',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.SELLER)
    return user


@pytest.fixture
def other_vehicle(db, other_seller, make_bmw, model_m3):
    return VehicleListing.objects.create(
        seller=other_seller,
        title='2023 BMW M3 CS',
        make=make_bmw,
        model=model_m3,
        year=2023,
        price=85000.00,
        mileage=5000,
        fuel_type=FuelTypeChoices.PETROL,
        transmission=TransmissionChoices.AUTOMATIC,
        status=ListingStatusChoices.APPROVED,
        is_active=True,
        location_city='Birmingham',
    )


# =============================================================================
# 1. Buyer Experience: Public Seller Information Inspection
# =============================================================================

@pytest.mark.django_db
def test_public_vehicle_detail_includes_authorized_seller_info(api_client, approved_vehicle, approved_seller_app):
    """
    Ensures buyers viewing a vehicle detail see authorized seller information:
    business name, verified badge, dealership type, location, and sanitized WhatsApp link.
    Private personal credentials or tokens are never exposed.
    """
    url = f"/api/v1/marketplace/browse/vehicles/{approved_vehicle.id}/"
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "seller_info" in data
    seller_info = data["seller_info"]

    assert seller_info["name"] == "Apex Performance Cars Ltd"
    assert seller_info["is_verified"] is True
    assert seller_info["seller_type"] == "DEALERSHIP"
    assert seller_info["location_city"] == "Manchester"
    assert seller_info["phone"] == "+44 161 999 8888"
    assert seller_info["has_phone"] is True
    assert seller_info["whatsapp_url"] == "https://wa.me/441619998888"
    assert seller_info["can_enquire"] is True

    # Security check: Private sensitive info must not be in seller_info
    assert "password" not in str(seller_info).lower()
    assert "token" not in str(seller_info).lower()


@pytest.mark.django_db
def test_unverified_private_seller_phone_is_masked(api_client, other_vehicle):
    """
    For an unverified private seller with no approved business application,
    personal phone number must NOT be disclosed.
    """
    url = f"/api/v1/marketplace/browse/vehicles/{other_vehicle.id}/"
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    seller_info = response.json()["seller_info"]

    assert seller_info["is_verified"] is False
    assert seller_info["seller_type"] == "INDIVIDUAL_SELLER"
    assert seller_info["phone"] is None
    assert seller_info["has_phone"] is False
    assert seller_info["whatsapp_url"] is None
    assert seller_info["can_enquire"] is True


# =============================================================================
# 2. Buyer Experience: Enquiry Submission
# =============================================================================

@pytest.mark.django_db
def test_buyer_can_submit_enquiry_on_approved_listing(api_client, buyer_user, approved_vehicle):
    """Authenticated buyer can submit a valid enquiry on an approved vehicle."""
    api_client.force_authenticate(user=buyer_user)
    url = f"/api/v1/marketplace/vehicles/{approved_vehicle.id}/enquire/"

    payload = {
        "message": "Hello, I am interested in your listed vehicle. Could you please share more details about its condition, availability and final price?",
        "buyer_phone": "+44 7123 456789",
    }
    response = api_client.post(url, payload, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["message"] == payload["message"]
    assert data["buyer_phone"] == payload["buyer_phone"]
    assert data["status"] == "NEW"
    assert data["listing"] == str(approved_vehicle.id)
    assert data["listing_details"]["title"] == approved_vehicle.title

    # Verify database state
    enquiry = VehicleEnquiry.objects.get(pk=data["id"])
    assert enquiry.buyer == buyer_user
    assert enquiry.seller == approved_vehicle.seller
    assert enquiry.status == VehicleEnquiryStatusChoices.NEW


@pytest.mark.django_db
def test_unauthenticated_user_cannot_submit_enquiry(api_client, approved_vehicle):
    """Unauthenticated enquiry submission must return 401."""
    url = f"/api/v1/marketplace/vehicles/{approved_vehicle.id}/enquire/"
    payload = {"message": "Hello, is this car still available for viewing?"}
    response = api_client.post(url, payload, format="json")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_enquiry_rejected_for_unapproved_listing(api_client, buyer_user, pending_vehicle):
    """Enquiries cannot be submitted on DRAFT or PENDING_APPROVAL vehicle listings."""
    api_client.force_authenticate(user=buyer_user)
    url = f"/api/v1/marketplace/vehicles/{pending_vehicle.id}/enquire/"

    payload = {"message": "Is this car available yet?"}
    response = api_client.post(url, payload, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "approved" in response.json()["detail"].lower()


@pytest.mark.django_db
def test_seller_cannot_enquire_on_own_listing(api_client, seller_user, approved_vehicle):
    """A seller cannot enquire on their own vehicle listing."""
    api_client.force_authenticate(user=seller_user)
    url = f"/api/v1/marketplace/vehicles/{approved_vehicle.id}/enquire/"

    payload = {"message": "Can I buy my own car?"}
    response = api_client.post(url, payload, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "own vehicle listing" in response.json()["detail"].lower()


@pytest.mark.django_db
def test_anti_spam_duplicate_enquiry_rate_limiting(api_client, buyer_user, approved_vehicle):
    """Prevents duplicate spam submissions within 60 seconds."""
    api_client.force_authenticate(user=buyer_user)
    url = f"/api/v1/marketplace/vehicles/{approved_vehicle.id}/enquire/"

    payload = {"message": "Hello, I am interested in this vehicle."}
    first_resp = api_client.post(url, payload, format="json")
    assert first_resp.status_code == status.HTTP_201_CREATED

    # Immediate second enquiry on same vehicle triggers rate limit
    second_resp = api_client.post(url, payload, format="json")
    assert second_resp.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.django_db
def test_enquiry_message_validation(api_client, buyer_user, approved_vehicle):
    """Rejects message shorter than 10 characters."""
    api_client.force_authenticate(user=buyer_user)
    url = f"/api/v1/marketplace/vehicles/{approved_vehicle.id}/enquire/"

    response = api_client.post(url, {"message": "Hi"}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "message" in response.json()


# =============================================================================
# 3. Seller Experience: View and Manage Enquiries
# =============================================================================

@pytest.mark.django_db
def test_seller_can_view_own_received_enquiries(api_client, buyer_user, seller_user, approved_vehicle):
    """Seller can view list of enquiries received for their listings."""
    enquiry = VehicleEnquiry.objects.create(
        listing=approved_vehicle,
        buyer=buyer_user,
        seller=seller_user,
        message="Hello, could you provide service history for this vehicle?",
        buyer_phone="+44 7123 000111",
    )

    api_client.force_authenticate(user=seller_user)
    url = "/api/v1/marketplace/seller/enquiries/"
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    raw_data = response.json()
    data = raw_data.get("results", raw_data) if isinstance(raw_data, dict) else raw_data
    assert len(data) >= 1
    item = [e for e in data if e["id"] == str(enquiry.id)][0]
    assert item["buyer_email"] == buyer_user.email
    assert item["buyer_name"] == buyer_user.full_name
    assert item["buyer_phone"] == "+44 7123 000111"
    assert item["status"] == "NEW"
    assert item["listing_details"]["title"] == approved_vehicle.title


@pytest.mark.django_db
def test_seller_cannot_view_other_sellers_enquiries(api_client, buyer_user, seller_user, other_seller, other_vehicle):
    """Strict isolation: Seller cannot view or access enquiries for other sellers' listings."""
    other_enquiry = VehicleEnquiry.objects.create(
        listing=other_vehicle,
        buyer=buyer_user,
        seller=other_seller,
        message="Confidential buyer enquiry for other seller's car",
    )

    api_client.force_authenticate(user=seller_user)

    # 1. In list endpoint, other_enquiry should NOT appear
    list_resp = api_client.get("/api/v1/marketplace/seller/enquiries/")
    assert list_resp.status_code == status.HTTP_200_OK
    raw_list = list_resp.json()
    items = raw_list.get("results", raw_list) if isinstance(raw_list, dict) else raw_list
    assert not any(e["id"] == str(other_enquiry.id) for e in items)

    # 2. In detail endpoint, returns 404
    detail_resp = api_client.get(f"/api/v1/marketplace/seller/enquiries/{other_enquiry.id}/")
    assert detail_resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_seller_can_update_enquiry_status_and_notes(api_client, buyer_user, seller_user, approved_vehicle):
    """Seller can transition enquiry status to RESPONDED or CLOSED and add notes."""
    enquiry = VehicleEnquiry.objects.create(
        listing=approved_vehicle,
        buyer=buyer_user,
        seller=seller_user,
        message="Can I test drive this weekend?",
    )

    api_client.force_authenticate(user=seller_user)
    url = f"/api/v1/marketplace/seller/enquiries/{enquiry.id}/"

    patch_payload = {
        "status": "RESPONDED",
        "seller_notes": "Called buyer via phone, scheduled test drive for Saturday 2pm.",
    }
    response = api_client.patch(url, patch_payload, format="json")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "RESPONDED"
    assert data["seller_notes"] == patch_payload["seller_notes"]
    assert data["responded_at"] is not None

    enquiry.refresh_from_db()
    assert enquiry.status == VehicleEnquiryStatusChoices.RESPONDED
    assert enquiry.responded_at is not None


# =============================================================================
# 4. Buyer Experience: Sent Enquiries List
# =============================================================================

@pytest.mark.django_db
def test_buyer_can_view_sent_enquiries(api_client, buyer_user, seller_user, approved_vehicle):
    """Buyer can retrieve their own sent enquiries."""
    enquiry = VehicleEnquiry.objects.create(
        listing=approved_vehicle,
        buyer=buyer_user,
        seller=seller_user,
        message="My enquiry message for this car",
    )

    api_client.force_authenticate(user=buyer_user)
    url = "/api/v1/marketplace/buyer/enquiries/"
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    raw_data = response.json()
    data = raw_data.get("results", raw_data) if isinstance(raw_data, dict) else raw_data
    assert any(e["id"] == str(enquiry.id) for e in data)


# =============================================================================
# 5. In-Platform Seller Replies and Buyer Enquiry History
# =============================================================================

@pytest.mark.django_db
def test_seller_can_submit_reply_to_buyer(api_client, buyer_user, seller_user, approved_vehicle):
    """Seller can submit an in-platform reply to a buyer's enquiry, auto-setting status to RESPONDED."""
    enquiry = VehicleEnquiry.objects.create(
        listing=approved_vehicle,
        buyer=buyer_user,
        seller=seller_user,
        message="Is this BMW still available for viewing this Saturday?",
        status=VehicleEnquiryStatusChoices.NEW,
    )

    api_client.force_authenticate(user=seller_user)
    url = f"/api/v1/marketplace/seller/enquiries/{enquiry.id}/"

    reply_text = "Yes, it is available! We can schedule your viewing for 2:00 PM this Saturday."
    patch_payload = {
        "seller_reply": reply_text,
    }
    response = api_client.patch(url, patch_payload, format="json")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["seller_reply"] == reply_text
    assert data["replied_at"] is not None
    assert data["status"] == "RESPONDED"
    assert data["responded_at"] is not None

    enquiry.refresh_from_db()
    assert enquiry.seller_reply == reply_text
    assert enquiry.replied_at is not None
    assert enquiry.status == VehicleEnquiryStatusChoices.RESPONDED


@pytest.mark.django_db
def test_buyer_can_view_seller_reply(api_client, buyer_user, seller_user, approved_vehicle):
    """Buyer can retrieve their enquiries and read the seller's reply message and timestamp."""
    reply_time = timezone.now()
    enquiry = VehicleEnquiry.objects.create(
        listing=approved_vehicle,
        buyer=buyer_user,
        seller=seller_user,
        message="Can I get the full service history?",
        seller_reply="Full service history from BMW dealership is available with all stamps.",
        replied_at=reply_time,
        status=VehicleEnquiryStatusChoices.RESPONDED,
    )

    api_client.force_authenticate(user=buyer_user)
    url = "/api/v1/marketplace/buyer/enquiries/"
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    raw_data = response.json()
    items = raw_data.get("results", raw_data) if isinstance(raw_data, dict) else raw_data

    matching = next((e for e in items if e["id"] == str(enquiry.id)), None)
    assert matching is not None
    assert matching["seller_reply"] == "Full service history from BMW dealership is available with all stamps."
    assert matching["replied_at"] is not None
    assert matching["status"] == "RESPONDED"
    assert matching["listing_details"]["title"] == approved_vehicle.title


@pytest.mark.django_db
def test_seller_notes_are_strictly_private_from_buyer(api_client, buyer_user, seller_user, approved_vehicle):
    """Ensure seller private internal notes are never exposed in buyer API responses."""
    enquiry = VehicleEnquiry.objects.create(
        listing=approved_vehicle,
        buyer=buyer_user,
        seller=seller_user,
        message="What is the lowest price for cash?",
        seller_notes="CONFIDENTIAL: Minimum reserve is £62,000. Do not disclose to buyer.",
        seller_reply="We are open to sensible offers in person during inspection.",
        replied_at=timezone.now(),
        status=VehicleEnquiryStatusChoices.RESPONDED,
    )

    api_client.force_authenticate(user=buyer_user)
    response = api_client.get("/api/v1/marketplace/buyer/enquiries/")

    assert response.status_code == status.HTTP_200_OK
    raw_data = response.json()
    items = raw_data.get("results", raw_data) if isinstance(raw_data, dict) else raw_data

    matching = next((e for e in items if e["id"] == str(enquiry.id)), None)
    assert matching is not None
    assert "seller_notes" not in matching
    assert "CONFIDENTIAL" not in str(matching)
    assert "reserve" not in str(matching)


@pytest.mark.django_db
def test_buyer_cannot_read_another_buyers_enquiries(api_client, buyer_user, other_seller, approved_vehicle):
    """Buyer A cannot view enquiries submitted by Buyer B."""
    buyer_b = User.objects.create_user(
        email='buyer_b@example.com',
        password='SecurePassword123!',
        first_name='Buyer',
        last_name='B',
        phone_number='+447000000888',
        is_email_verified=True,
    )
    buyer_b.add_role(RoleChoices.BUYER)

    enquiry_b = VehicleEnquiry.objects.create(
        listing=approved_vehicle,
        buyer=buyer_b,
        seller=approved_vehicle.seller,
        message="Private inquiry from Buyer B",
    )

    # Buyer A logs in
    api_client.force_authenticate(user=buyer_user)
    response = api_client.get("/api/v1/marketplace/buyer/enquiries/")
    assert response.status_code == status.HTTP_200_OK

    raw_data = response.json()
    items = raw_data.get("results", raw_data) if isinstance(raw_data, dict) else raw_data
    assert not any(e["id"] == str(enquiry_b.id) for e in items)


@pytest.mark.django_db
def test_unrelated_seller_cannot_reply_to_other_seller_enquiry(api_client, buyer_user, seller_user, other_seller, approved_vehicle):
    """An unrelated seller cannot reply to or modify another seller's enquiry."""
    enquiry = VehicleEnquiry.objects.create(
        listing=approved_vehicle,
        buyer=buyer_user,
        seller=seller_user,
        message="Can I see the car?",
    )

    # Authenticate as unrelated seller
    api_client.force_authenticate(user=other_seller)
    url = f"/api/v1/marketplace/seller/enquiries/{enquiry.id}/"

    response = api_client.patch(url, {"seller_reply": "Malicious hijacking reply attempt"}, format="json")
    assert response.status_code == status.HTTP_404_NOT_FOUND

    enquiry.refresh_from_db()
    assert enquiry.seller_reply == ""
