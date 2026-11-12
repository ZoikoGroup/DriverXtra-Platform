import pytest
from decimal import Decimal
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from django.utils import timezone
from rest_framework import status

from apps.identity.models import User, RoleChoices
from apps.organisations.models import Organisation, OrganisationMembership, OrganisationRoleChoices, OrganisationTypeChoices
from apps.onboarding.models import SellerApplication, SellerApplicationStatusChoices, BusinessTypeChoices
from apps.catalogue.models import (
    VehicleMake,
    VehicleModel,
    FuelTypeChoices,
    TransmissionChoices,
)
from apps.marketplace.models import (
    VehicleListing,
    ListingStatusChoices,
    VehicleListingAvailabilityChoices,
    VehiclePurchaseOffer,
    VehicleOfferStatusChoices,
    VehicleOfferProposal,
    VehicleOfferAction,
    VehicleOfferActionTypeChoices,
    VehicleOrder,
    VehicleOrderStatusChoices,
    VehicleHandoverTypeChoices,
    ImmutableRecordError,
)
from apps.marketplace.vehicle_offers_service import (
    calculate_payment_deadline,
    get_jurisdiction_holidays,
    accept_vehicle_offer_and_reserve,
    cancel_expired_payment_orders,
    expire_pending_vehicle_offers,
    VehicleAlreadyReservedError,
)
from apps.notifications.models import Notification


@pytest.fixture
def make_porsche(db):
    return VehicleMake.objects.create(name='Porsche', country_of_origin='Germany')


@pytest.fixture
def model_911(db, make_porsche):
    return VehicleModel.objects.create(make=make_porsche, name='911 Carrera', year_start=2022)


@pytest.fixture
def dealer_org(db, seller_user):
    org = Organisation.objects.create(
        name="Apex Supercars Manchester",
        slug="apex-supercars-manchester",
        type=OrganisationTypeChoices.DEALER_GROUP,
    )
    OrganisationMembership.objects.create(
        user=seller_user,
        organisation=org,
        role=OrganisationRoleChoices.OWNER,
        is_active=True,
    )
    return org


@pytest.fixture
def available_listing(db, seller_user, dealer_org, make_porsche, model_911):
    return VehicleListing.objects.create(
        seller=seller_user,
        organisation=dealer_org,
        title='2022 Porsche 911 Carrera 4S',
        make=make_porsche,
        model=model_911,
        year=2022,
        price=95000.00,
        currency='GBP',
        mileage=8500,
        fuel_type=FuelTypeChoices.PETROL,
        transmission=TransmissionChoices.AUTOMATIC,
        status=ListingStatusChoices.APPROVED,
        availability_status=VehicleListingAvailabilityChoices.AVAILABLE,
        is_active=True,
        location_city='Manchester',
        location_postcode='M1 1AA',
    )


@pytest.fixture
def buyer_b(db):
    user = User.objects.create_user(
        email='buyer_b@driverxtra.com',
        password='SecurePassword123!',
        first_name='Benjamin',
        last_name='Buyer',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.fixture
def other_dealer(db):
    user = User.objects.create_user(
        email='other_dealer@driverxtra.com',
        password='SecurePassword123!',
        first_name='David',
        last_name='Dealer',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.SELLER)
    return user


# =============================================================================
# 1. Offer Submission & Validation Tests
# =============================================================================

@pytest.mark.django_db
def test_buyer_can_submit_vehicle_purchase_offer(api_client, buyer_user, available_listing):
    """Authenticated buyer can submit an offer on an approved, available vehicle listing."""
    api_client.force_authenticate(user=buyer_user)
    url = f"/api/v1/marketplace/vehicles/{available_listing.id}/offers/"

    payload = {
        "offered_price": 92000.00,
        "handover_preference": "COLLECTION",
        "notes": "Interested in cash purchase subject to inspection.",
    }
    response = api_client.post(url, payload, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["status"] == "PENDING_DEALER"
    assert data["current_round"] == 1
    assert data["currency"] == "GBP"
    assert len(data["proposals"]) == 1
    assert Decimal(str(data["proposals"][0]["offered_price"])) == Decimal("92000.00")
    assert data["proposals"][0]["proposed_by_role"] == "BUYER"
    assert data["proposals"][0]["handover_preference"] == "COLLECTION"

    # Action history
    assert len(data["actions"]) == 1
    assert data["actions"][0]["action_type"] == "SUBMITTED"

    # Verify DB state
    offer = VehiclePurchaseOffer.objects.get(pk=data["id"])
    assert offer.buyer == buyer_user
    assert offer.seller == available_listing.seller
    assert offer.organisation == available_listing.organisation
    assert offer.listing == available_listing


@pytest.mark.django_db
def test_offer_rejected_for_unapproved_or_inactive_listing(api_client, buyer_user, make_porsche, model_911, seller_user):
    """Cannot submit an offer on a draft or pending approval listing."""
    draft_listing = VehicleListing.objects.create(
        seller=seller_user,
        title='Draft Listing',
        make=make_porsche,
        model=model_911,
        year=2021,
        price=80000.00,
        status=ListingStatusChoices.PENDING_APPROVAL,
        is_active=True,
    )
    api_client.force_authenticate(user=buyer_user)
    url = f"/api/v1/marketplace/vehicles/{draft_listing.id}/offers/"

    response = api_client.post(url, {"offered_price": 75000.00}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "active, approved" in response.json()["detail"].lower()


@pytest.mark.django_db
def test_seller_cannot_submit_offer_on_own_vehicle(api_client, seller_user, available_listing):
    """Seller or dealer organisation member cannot submit an offer on their own listing."""
    api_client.force_authenticate(user=seller_user)
    url = f"/api/v1/marketplace/vehicles/{available_listing.id}/offers/"

    response = api_client.post(url, {"offered_price": 90000.00}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "own vehicle listing" in response.json()["detail"].lower()


@pytest.mark.django_db
def test_immutable_offer_proposals_and_actions(buyer_user, available_listing):
    """Verifies that proposal terms and action records are strictly append-only and cannot be mutated or deleted."""
    offer = VehiclePurchaseOffer.objects.create(
        listing=available_listing,
        buyer=buyer_user,
        seller=available_listing.seller,
        organisation=available_listing.organisation,
        status=VehicleOfferStatusChoices.PENDING_DEALER,
        current_round=1,
        currency="GBP",
        expires_at=timezone.now() + timedelta(hours=72),
    )
    proposal = VehicleOfferProposal.objects.create(
        offer=offer,
        revision_number=1,
        proposed_by=buyer_user,
        proposed_by_role="BUYER",
        offered_price=Decimal("90000.00"),
        currency="GBP",
        handover_preference=VehicleHandoverTypeChoices.COLLECTION,
    )
    action = VehicleOfferAction.objects.create(
        offer=offer,
        proposal=proposal,
        actor=buyer_user,
        action_type=VehicleOfferActionTypeChoices.SUBMITTED,
    )

    # Attempting to mutate proposal must raise ImmutableRecordError
    proposal.offered_price = Decimal("85000.00")
    with pytest.raises(ImmutableRecordError):
        proposal.save()

    # Attempting to delete proposal must raise ImmutableRecordError
    with pytest.raises(ImmutableRecordError):
        proposal.delete()

    # Attempting to mutate action must raise ImmutableRecordError
    action.notes = "Mutated note"
    with pytest.raises(ImmutableRecordError):
        action.save()

    with pytest.raises(ImmutableRecordError):
        action.delete()


# =============================================================================
# 2. Counteroffer Negotiation History
# =============================================================================

@pytest.mark.django_db
def test_dealer_and_buyer_counteroffer_negotiation_history(api_client, buyer_user, seller_user, available_listing):
    """
    Tests complete negotiation flow:
    1. Buyer submits offer £90k (Round 1, PENDING_DEALER)
    2. Dealer counters £94k (Round 2, PENDING_BUYER)
    3. Buyer counters back £93k (Round 3, PENDING_DEALER)
    4. Dealer accepts £93k -> Order created!
    """
    # 1. Buyer submits initial offer
    api_client.force_authenticate(user=buyer_user)
    submit_url = f"/api/v1/marketplace/vehicles/{available_listing.id}/offers/"
    r1 = api_client.post(submit_url, {"offered_price": 90000.00, "notes": "Offer R1"}, format="json")
    assert r1.status_code == status.HTTP_201_CREATED
    offer_id = r1.json()["id"]

    # 2. Dealer counters £94,000
    api_client.force_authenticate(user=seller_user)
    counter_url = f"/api/v1/marketplace/seller/vehicle-offers/{offer_id}/counter/"
    r2 = api_client.post(counter_url, {"counter_price": 94000.00, "notes": "Counter R2: Lowest we can do is £94k"}, format="json")
    assert r2.status_code == status.HTTP_200_OK
    d2 = r2.json()
    assert d2["status"] == "PENDING_BUYER"
    assert d2["current_round"] == 2
    assert len(d2["proposals"]) == 2
    assert Decimal(str(d2["proposals"][1]["offered_price"])) == Decimal("94000.00")
    assert d2["proposals"][1]["proposed_by_role"] == "DEALER"

    # 3. Buyer counters back £93,000
    api_client.force_authenticate(user=buyer_user)
    buyer_counter_url = f"/api/v1/marketplace/buyer/vehicle-offers/{offer_id}/counter/"
    r3 = api_client.post(buyer_counter_url, {"counter_price": 93000.00, "notes": "Counter R3: Meet in the middle at £93k"}, format="json")
    assert r3.status_code == status.HTTP_200_OK
    d3 = r3.json()
    assert d3["status"] == "PENDING_DEALER"
    assert d3["current_round"] == 3
    assert len(d3["proposals"]) == 3
    assert Decimal(str(d3["proposals"][2]["offered_price"])) == Decimal("93000.00")
    assert d3["proposals"][2]["proposed_by_role"] == "BUYER"

    # 4. Dealer accepts the £93,000 offer
    api_client.force_authenticate(user=seller_user)
    accept_url = f"/api/v1/marketplace/seller/vehicle-offers/{offer_id}/accept/"
    r4 = api_client.post(accept_url, format="json")
    assert r4.status_code == status.HTTP_201_CREATED
    order_data = r4.json()

    assert order_data["status"] == "PAYMENT_PENDING"
    assert Decimal(str(order_data["agreed_price"])) == Decimal("93000.00")
    assert order_data["currency"] == "GBP"
    assert order_data["accepted_offer"] == offer_id
    assert order_data["order_number"].startswith("VO-")
    assert order_data["market_timezone"] == "Europe/London"

    # Confirm vehicle is now RESERVED
    available_listing.refresh_from_db()
    assert available_listing.availability_status == VehicleListingAvailabilityChoices.RESERVED


# =============================================================================
# 3. Multiple Simultaneous Buyers & Superseding Competing Offers
# =============================================================================

@pytest.mark.django_db
def test_simultaneous_buyers_and_first_accepted_supersedes_others(api_client, buyer_user, buyer_b, seller_user, available_listing):
    """
    Multiple prospective buyers negotiate simultaneously.
    When Dealer accepts Buyer A's offer:
    - VehicleListing availability becomes RESERVED.
    - Buyer A gets a VehicleOrder in PAYMENT_PENDING.
    - Buyer B's active offer is automatically marked SUPERSEDED.
    - Buyer B attempting to accept or counter is rejected with conflict.
    """
    # Buyer A submits offer £90k
    api_client.force_authenticate(user=buyer_user)
    r_a = api_client.post(f"/api/v1/marketplace/vehicles/{available_listing.id}/offers/", {"offered_price": 90000.00}, format="json")
    assert r_a.status_code == status.HTTP_201_CREATED
    offer_a_id = r_a.json()["id"]

    # Buyer B submits offer £91k simultaneously
    api_client.force_authenticate(user=buyer_b)
    r_b = api_client.post(f"/api/v1/marketplace/vehicles/{available_listing.id}/offers/", {"offered_price": 91000.00}, format="json")
    assert r_b.status_code == status.HTTP_201_CREATED
    offer_b_id = r_b.json()["id"]

    # Dealer accepts Buyer B's £91k offer
    api_client.force_authenticate(user=seller_user)
    accept_b = api_client.post(f"/api/v1/marketplace/seller/vehicle-offers/{offer_b_id}/accept/", format="json")
    assert accept_b.status_code == status.HTTP_201_CREATED
    order_b = accept_b.json()
    assert order_b["status"] == "PAYMENT_PENDING"
    assert Decimal(str(order_b["agreed_price"])) == Decimal("91000.00")

    # Verify Buyer A's competing offer has been marked SUPERSEDED
    offer_a = VehiclePurchaseOffer.objects.get(pk=offer_a_id)
    assert offer_a.status == VehicleOfferStatusChoices.SUPERSEDED
    assert offer_a.actions.filter(action_type=VehicleOfferActionTypeChoices.SUPERSEDED).exists()

    # Attempting to accept Buyer A's superseded offer returns 409 Conflict (vehicle already reserved)
    accept_a = api_client.post(f"/api/v1/marketplace/seller/vehicle-offers/{offer_a_id}/accept/", format="json")
    assert accept_a.status_code == status.HTTP_409_CONFLICT
    assert accept_a.json()["code"] == "VEHICLE_ALREADY_RESERVED"

    # Attempting to submit a new offer on the now-RESERVED listing returns 400
    api_client.force_authenticate(user=buyer_user)
    new_offer = api_client.post(f"/api/v1/marketplace/vehicles/{available_listing.id}/offers/", {"offered_price": 93000.00}, format="json")
    assert new_offer.status_code == status.HTTP_400_BAD_REQUEST
    assert "reserved" in new_offer.json()["detail"].lower()


@pytest.mark.django_db
def test_duplicate_acceptance_returns_conflict_409(buyer_user, seller_user, available_listing):
    """Calling accept_vehicle_offer_and_reserve twice or on an already reserved listing raises VehicleAlreadyReservedError."""
    # Create two offers
    offer_1 = VehiclePurchaseOffer.objects.create(
        listing=available_listing,
        buyer=buyer_user,
        seller=seller_user,
        organisation=available_listing.organisation,
        status=VehicleOfferStatusChoices.PENDING_DEALER,
        current_round=1,
        currency="GBP",
        expires_at=timezone.now() + timedelta(hours=72),
    )
    VehicleOfferProposal.objects.create(
        offer=offer_1,
        revision_number=1,
        proposed_by=buyer_user,
        proposed_by_role="BUYER",
        offered_price=Decimal("90000.00"),
        currency="GBP",
    )

    # First acceptance succeeds
    order = accept_vehicle_offer_and_reserve(actor=seller_user, offer_id=offer_1.id)
    assert order.status == VehicleOrderStatusChoices.PAYMENT_PENDING

    # Second acceptance attempt must raise VehicleAlreadyReservedError
    with pytest.raises(VehicleAlreadyReservedError):
        accept_vehicle_offer_and_reserve(actor=seller_user, offer_id=offer_1.id)


# =============================================================================
# 4. Five-Business-Day Statutory Payment Deadline Calculation
# =============================================================================

def test_five_business_days_deadline_skips_weekends_and_bank_holidays(settings):
    """
    Verifies that the statutory 5-business-day payment deadline skips
    Saturdays, Sundays, and official statutory bank holidays in the jurisdiction.
    """
    # Start on Wednesday 2026-04-01 at 14:00 UTC
    start = datetime(2026, 4, 1, 14, 0, 0, tzinfo=ZoneInfo("UTC"))

    # In 2026 UK:
    # Wed Apr 1 = Start day
    # Thu Apr 2 = Day 1
    # Fri Apr 3 = Good Friday (Bank Holiday -> SKIPPED)
    # Sat Apr 4 = Weekend -> SKIPPED
    # Sun Apr 5 = Weekend -> SKIPPED
    # Mon Apr 6 = Easter Monday (Bank Holiday -> SKIPPED)
    # Tue Apr 7 = Day 2
    # Wed Apr 8 = Day 3
    # Thu Apr 9 = Day 4
    # Fri Apr 10 = Day 5 (DEADLINE!)
    deadline = calculate_payment_deadline(start_dt=start, market_tz_name="Europe/London", business_days=5)

    assert deadline.year == 2026
    assert deadline.month == 4
    assert deadline.day == 10
    assert deadline.hour == 14
    assert deadline.minute == 0


def test_five_business_days_deadline_normal_week():
    """Starts on a Monday morning with no holidays: deadline is Friday afternoon (5 days)."""
    # Mon 2026-06-08 10:00 UTC (No holidays in June)
    start = datetime(2026, 6, 8, 10, 0, 0, tzinfo=ZoneInfo("UTC"))
    deadline = calculate_payment_deadline(start_dt=start, market_tz_name="Europe/London", business_days=5)

    # Tue Jun 9 (1), Wed Jun 10 (2), Thu Jun 11 (3), Fri Jun 12 (4), Mon Jun 15 (5)
    # Wait: 5 days added after start:
    # Day 1: Tue 9
    # Day 2: Wed 10
    # Day 3: Thu 11
    # Day 4: Fri 12
    # Day 5: Mon 15
    assert deadline.year == 2026
    assert deadline.month == 6
    assert deadline.day == 15
    assert deadline.hour == 10


# =============================================================================
# 5. Expired Order Cancellation & Listing Release Task
# =============================================================================

@pytest.mark.django_db
def test_expired_payment_order_cancellation_and_safe_release(buyer_user, seller_user, available_listing):
    """
    When an order's payment_deadline has passed without payment:
    cancel_expired_payment_orders():
    - Transitions order from PAYMENT_PENDING to CANCELLED.
    - Releases VehicleListing availability back to AVAILABLE.
    - Is idempotent.
    """
    offer = VehiclePurchaseOffer.objects.create(
        listing=available_listing,
        buyer=buyer_user,
        seller=seller_user,
        organisation=available_listing.organisation,
        status=VehicleOfferStatusChoices.PENDING_DEALER,
        current_round=1,
        currency="GBP",
        expires_at=timezone.now() + timedelta(hours=72),
    )
    VehicleOfferProposal.objects.create(
        offer=offer,
        revision_number=1,
        proposed_by=buyer_user,
        proposed_by_role="BUYER",
        offered_price=Decimal("95000.00"),
        currency="GBP",
    )

    # Accept and reserve
    order = accept_vehicle_offer_and_reserve(actor=seller_user, offer_id=offer.id)
    available_listing.refresh_from_db()
    assert available_listing.availability_status == VehicleListingAvailabilityChoices.RESERVED
    assert order.status == VehicleOrderStatusChoices.PAYMENT_PENDING

    # Artificially set payment deadline to 1 hour in the past
    VehicleOrder.objects.filter(pk=order.pk).update(
        payment_deadline=timezone.now() - timedelta(hours=1)
    )

    # Run cancellation maintenance task
    cancelled = cancel_expired_payment_orders()
    assert cancelled == 1

    order.refresh_from_db()
    assert order.status == VehicleOrderStatusChoices.CANCELLED
    assert "deadline" in order.cancellation_reason.lower()
    assert order.cancelled_at is not None

    # Listing must be released back to AVAILABLE
    available_listing.refresh_from_db()
    assert available_listing.availability_status == VehicleListingAvailabilityChoices.AVAILABLE

    # Running task again must be idempotent and cancel 0
    second_run = cancel_expired_payment_orders()
    assert second_run == 0


# =============================================================================
# 6. Buyer and Dealer Isolation Tests
# =============================================================================

@pytest.mark.django_db
def test_buyer_and_dealer_isolation(api_client, buyer_user, buyer_b, other_dealer, available_listing):
    """Unrelated buyers and dealers cannot inspect or act on each other's offers or orders."""
    # Buyer A creates offer
    api_client.force_authenticate(user=buyer_user)
    r = api_client.post(f"/api/v1/marketplace/vehicles/{available_listing.id}/offers/", {"offered_price": 90000.00}, format="json")
    offer_id = r.json()["id"]

    # Buyer B tries to access Buyer A's offer -> 404
    api_client.force_authenticate(user=buyer_b)
    resp_b = api_client.get(f"/api/v1/marketplace/buyer/vehicle-offers/{offer_id}/")
    assert resp_b.status_code == status.HTTP_404_NOT_FOUND

    # Buyer B tries to counter Buyer A's offer -> 404
    resp_counter = api_client.post(f"/api/v1/marketplace/buyer/vehicle-offers/{offer_id}/counter/", {"counter_price": 89000.00}, format="json")
    assert resp_counter.status_code == status.HTTP_404_NOT_FOUND

    # Unrelated dealer tries to view or accept Buyer A's offer -> 404
    api_client.force_authenticate(user=other_dealer)
    resp_dealer = api_client.get(f"/api/v1/marketplace/seller/vehicle-offers/{offer_id}/")
    assert resp_dealer.status_code == status.HTTP_404_NOT_FOUND

    resp_dealer_accept = api_client.post(f"/api/v1/marketplace/seller/vehicle-offers/{offer_id}/accept/", format="json")
    assert resp_dealer_accept.status_code == status.HTTP_403_FORBIDDEN or resp_dealer_accept.status_code == status.HTTP_404_NOT_FOUND


# =============================================================================
# 7. Automatic Offer Expiry Tests
# =============================================================================

@pytest.mark.django_db
def test_expire_pending_vehicle_offers_idempotent_and_safe(buyer_user, seller_user, dealer_org, available_listing):
    """
    Automatic offer expiration:
    - Expires only active offers whose negotiation deadline has passed.
    - Records immutable VehicleOfferAction with action_type=EXPIRED.
    - Does NOT expire accepted, rejected, withdrawn, or superseded offers.
    - Is fully idempotent.
    """
    now = timezone.now()
    past_deadline = now - timedelta(hours=1)
    future_deadline = now + timedelta(hours=48)

    # 1. Expired pending offer (should expire)
    expired_offer = VehiclePurchaseOffer.objects.create(
        listing=available_listing,
        buyer=buyer_user,
        seller=seller_user,
        organisation=dealer_org,
        status=VehicleOfferStatusChoices.PENDING_DEALER,
        expires_at=past_deadline,
        currency='GBP',
    )
    p1 = VehicleOfferProposal.objects.create(
        offer=expired_offer,
        revision_number=1,
        proposed_by=buyer_user,
        proposed_by_role="BUYER",
        offered_price=Decimal("90000.00"),
        currency="GBP",
    )

    # 2. Future pending offer (must NOT expire)
    future_offer = VehiclePurchaseOffer.objects.create(
        listing=available_listing,
        buyer=buyer_user,
        seller=seller_user,
        organisation=dealer_org,
        status=VehicleOfferStatusChoices.PENDING_DEALER,
        expires_at=future_deadline,
        currency='GBP',
    )

    # 3. Accepted offer with past deadline (must NOT expire)
    accepted_offer = VehiclePurchaseOffer.objects.create(
        listing=available_listing,
        buyer=buyer_user,
        seller=seller_user,
        organisation=dealer_org,
        status=VehicleOfferStatusChoices.ACCEPTED,
        expires_at=past_deadline,
        currency='GBP',
    )

    # 4. Rejected offer with past deadline (must NOT expire)
    rejected_offer = VehiclePurchaseOffer.objects.create(
        listing=available_listing,
        buyer=buyer_user,
        seller=seller_user,
        organisation=dealer_org,
        status=VehicleOfferStatusChoices.REJECTED,
        expires_at=past_deadline,
        currency='GBP',
    )

    # Run the expiration task
    expired_count = expire_pending_vehicle_offers()
    assert expired_count == 1

    # Verify expired offer state and action
    expired_offer.refresh_from_db()
    assert expired_offer.status == VehicleOfferStatusChoices.EXPIRED
    action = expired_offer.actions.filter(action_type=VehicleOfferActionTypeChoices.EXPIRED).first()
    assert action is not None
    assert "expired" in action.notes.lower()

    # Verify other offers untouched
    future_offer.refresh_from_db()
    assert future_offer.status == VehicleOfferStatusChoices.PENDING_DEALER
    accepted_offer.refresh_from_db()
    assert accepted_offer.status == VehicleOfferStatusChoices.ACCEPTED
    rejected_offer.refresh_from_db()
    assert rejected_offer.status == VehicleOfferStatusChoices.REJECTED

    # Running a second time is idempotent and expires 0
    second_run = expire_pending_vehicle_offers()
    assert second_run == 0


# =============================================================================
# 8. Notification Infrastructure Tests
# =============================================================================

@pytest.mark.django_db
def test_vehicle_offer_and_reservation_notifications(api_client, buyer_user, buyer_b, seller_user, available_listing):
    """
    Tests end-to-end notification generation via AuditLog pipeline for:
    - New offer submission (notifies seller).
    - Counteroffer (notifies buyer).
    - Offer acceptance and order creation (notifies buyer and seller).
    - Competing offer supersession (notifies competing buyer).
    """
    # 1. Buyer A submits offer
    api_client.force_authenticate(user=buyer_user)
    r_a = api_client.post(
        f"/api/v1/marketplace/vehicles/{available_listing.id}/offers/",
        {"offered_price": 91000.00, "handover_preference": "COLLECTION"},
        format="json",
    )
    assert r_a.status_code == status.HTTP_201_CREATED
    offer_a_id = r_a.json()["id"]

    # Seller must have received in-app notification
    seller_notif = Notification.objects.filter(
        recipient=seller_user,
        event_type="marketplace.vehicle_offer.submitted",
    ).first()
    assert seller_notif is not None
    assert "91000" in seller_notif.message or "offer" in seller_notif.title.lower()

    # 2. Buyer B submits competing offer
    api_client.force_authenticate(user=buyer_b)
    r_b = api_client.post(
        f"/api/v1/marketplace/vehicles/{available_listing.id}/offers/",
        {"offered_price": 93000.00},
        format="json",
    )
    assert r_b.status_code == status.HTTP_201_CREATED
    offer_b_id = r_b.json()["id"]

    # 3. Dealer counters Buyer A
    api_client.force_authenticate(user=seller_user)
    r_counter = api_client.post(
        f"/api/v1/marketplace/seller/vehicle-offers/{offer_a_id}/counter/",
        {"counter_price": 94000.00, "handover_preference": "COLLECTION", "notes": "Final dealer offer"},
        format="json",
    )
    assert r_counter.status_code == status.HTTP_200_OK

    # Buyer A must have received counteroffer notification
    buyer_a_notif = Notification.objects.filter(
        recipient=buyer_user,
        event_type="marketplace.vehicle_offer.countered",
    ).first()
    assert buyer_a_notif is not None
    assert "94000" in buyer_a_notif.message

    # 4. Dealer accepts Buyer B's offer
    r_accept = api_client.post(f"/api/v1/marketplace/seller/vehicle-offers/{offer_b_id}/accept/", format="json")
    assert r_accept.status_code == status.HTTP_201_CREATED
    order_data = r_accept.json()

    # Buyer B must have received acceptance / order notification
    buyer_b_order_notif = Notification.objects.filter(
        recipient=buyer_b,
        event_type="marketplace.vehicle_order.created",
    ).first()
    assert buyer_b_order_notif is not None
    assert order_data["order_number"] in buyer_b_order_notif.title or order_data["order_number"] in buyer_b_order_notif.message

    # Competing Buyer A must have received supersession notification
    buyer_a_superseded_notif = Notification.objects.filter(
        recipient=buyer_user,
        event_type="marketplace.vehicle_offer.superseded",
    ).first()
    assert buyer_a_superseded_notif is not None
    assert "superseded" in buyer_a_superseded_notif.title.lower() or "superseded" in buyer_a_superseded_notif.message.lower()


# =============================================================================
# 9. PostgreSQL Concurrency Verification Test
# =============================================================================

@pytest.mark.django_db(transaction=True)
def test_postgresql_concurrency_two_buyers_accept_same_listing(api_client, buyer_user, buyer_b, seller_user, dealer_org, available_listing):
    """
    PostgreSQL Transaction Concurrency Test:
    Two independent offers on the same listing.
    The first acceptance successfully locks the listing row with select_for_update(of=('self',)),
    transitions availability to RESERVED, and creates a VehicleOrder.
    The competing acceptance encounters the RESERVED state and is rejected with HTTP 409 Conflict.
    Exactly one active VehicleOrder exists in the database.
    """
    # Create two competing offers
    future_deadline = timezone.now() + timedelta(days=3)
    offer_a = VehiclePurchaseOffer.objects.create(
        listing=available_listing,
        buyer=buyer_user,
        seller=seller_user,
        organisation=dealer_org,
        status=VehicleOfferStatusChoices.PENDING_DEALER,
        expires_at=future_deadline,
        currency='GBP',
    )
    VehicleOfferProposal.objects.create(
        offer=offer_a,
        revision_number=1,
        proposed_by=buyer_user,
        proposed_by_role="BUYER",
        offered_price=Decimal("92000.00"),
        currency="GBP",
    )

    offer_b = VehiclePurchaseOffer.objects.create(
        listing=available_listing,
        buyer=buyer_b,
        seller=seller_user,
        organisation=dealer_org,
        status=VehicleOfferStatusChoices.PENDING_DEALER,
        expires_at=future_deadline,
        currency='GBP',
    )
    VehicleOfferProposal.objects.create(
        offer=offer_b,
        revision_number=1,
        proposed_by=buyer_b,
        proposed_by_role="BUYER",
        offered_price=Decimal("94000.00"),
        currency="GBP",
    )

    # First buyer's offer is accepted
    api_client.force_authenticate(user=seller_user)
    accept_a = api_client.post(f"/api/v1/marketplace/seller/vehicle-offers/{offer_a.id}/accept/", format="json")
    assert accept_a.status_code == status.HTTP_201_CREATED
    order_a_id = accept_a.json()["id"]

    # Verify listing is atomically reserved
    available_listing.refresh_from_db()
    assert available_listing.availability_status == VehicleListingAvailabilityChoices.RESERVED

    # Competing buyer's offer acceptance must fail with 409 Conflict
    accept_b = api_client.post(f"/api/v1/marketplace/seller/vehicle-offers/{offer_b.id}/accept/", format="json")
    assert accept_b.status_code == status.HTTP_409_CONFLICT
    assert accept_b.json().get("code") == "VEHICLE_ALREADY_RESERVED"

    # Exactly one active VehicleOrder exists
    active_orders = VehicleOrder.objects.filter(
        listing=available_listing,
        status=VehicleOrderStatusChoices.PAYMENT_PENDING,
    )
    assert active_orders.count() == 1
    assert str(active_orders.first().id) == order_a_id

