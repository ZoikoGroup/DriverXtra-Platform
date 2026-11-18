import pytest
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone
from rest_framework import status
from django.core.exceptions import ValidationError

from apps.identity.models import User, RoleChoices
from apps.organisations.models import (
    Organisation,
    OrganisationMembership,
    OrganisationRoleChoices,
    OrganisationTypeChoices,
)
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
    VehicleOrder,
    VehicleOrderStatusChoices,
    VehicleHandoverTypeChoices,
    VehiclePaymentReport,
    VehiclePaymentReportStatusChoices,
    VehiclePaymentEscalationLevelChoices,
    VehiclePaymentVerificationEvent,
    VehiclePaymentVerificationEventTypeChoices,
    ImmutableRecordError,
)
from apps.notifications.models import Notification
from apps.marketplace.vehicle_offers_service import (
    accept_vehicle_offer_and_reserve,
    report_vehicle_order_payment,
    confirm_vehicle_order_payment,
    reject_vehicle_order_payment,
    flag_vehicle_order_payment,
    cancel_expired_payment_orders,
    process_vehicle_payment_verification_escalations,
)


@pytest.fixture
def make_bmw(db):
    return VehicleMake.objects.create(name='BMW', country_of_origin='Germany')


@pytest.fixture
def model_m3(db, make_bmw):
    return VehicleModel.objects.create(make=make_bmw, name='M3 Competition', year_start=2023)


@pytest.fixture
def dealer_org(db, seller_user):
    org = Organisation.objects.create(
        name="Bavarian Motors London",
        slug="bavarian-motors-london",
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
def dealer_colleague(db, dealer_org):
    colleague = User.objects.create_user(
        email='dealer_finance@bavarian.co.uk',
        password='SecurePassword123!',
        first_name='Fiona',
        last_name='Finance',
        is_email_verified=True,
    )
    colleague.add_role(RoleChoices.SELLER)
    OrganisationMembership.objects.create(
        user=colleague,
        organisation=dealer_org,
        role=OrganisationRoleChoices.ADMIN,
        is_active=True,
    )
    return colleague


@pytest.fixture
def available_listing(db, seller_user, dealer_org, make_bmw, model_m3):
    return VehicleListing.objects.create(
        seller=seller_user,
        organisation=dealer_org,
        title='2023 BMW M3 Competition xDrive',
        make=make_bmw,
        model=model_m3,
        year=2023,
        price=82000.00,
        currency='GBP',
        mileage=5200,
        fuel_type=FuelTypeChoices.PETROL,
        transmission=TransmissionChoices.AUTOMATIC,
        status=ListingStatusChoices.APPROVED,
        availability_status=VehicleListingAvailabilityChoices.AVAILABLE,
        is_active=True,
        location_city='London',
        location_postcode='W1K 7AA',
    )


@pytest.fixture
def buyer_b(db):
    user = User.objects.create_user(
        email='buyer_unrelated@driverxtra.com',
        password='SecurePassword123!',
        first_name='Uma',
        last_name='Unrelated',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.fixture
def active_order(db, buyer_user, seller_user, dealer_org, available_listing):
    """
    Creates an accepted offer and active VehicleOrder in PAYMENT_PENDING status.
    """
    now = timezone.now()
    offer = VehiclePurchaseOffer.objects.create(
        listing=available_listing,
        buyer=buyer_user,
        seller=seller_user,
        organisation=dealer_org,
        currency='GBP',
        status=VehicleOfferStatusChoices.PENDING_DEALER,
        current_round=1,
        expires_at=now + timedelta(days=3),
    )
    proposal = VehicleOfferProposal.objects.create(
        offer=offer,
        revision_number=1,
        proposed_by=buyer_user,
        proposed_by_role='BUYER',
        offered_price=Decimal('80000.00'),
        currency='GBP',
        handover_preference=VehicleHandoverTypeChoices.COLLECTION,
        notes='Offer submitted.',
    )
    return accept_vehicle_offer_and_reserve(actor=seller_user, offer_id=offer.id)


# =============================================================================
# 1. Buyer Payment Reporting API Tests
# =============================================================================

@pytest.mark.django_db
def test_buyer_can_report_offline_payment_success(api_client, buyer_user, active_order):
    api_client.force_authenticate(user=buyer_user)

    url = f"/api/v1/marketplace/buyer/vehicle-orders/{active_order.id}/report-payment/"
    payload = {
        "amount_paid": "80000.00",
        "currency": "GBP",
        "payment_reference": "BARC-WIRE-992837",
        "paid_at": timezone.now().isoformat(),
        "payment_notes": "Transferred directly from Santander account.",
    }

    response = api_client.post(url, payload, format="json")
    assert response.status_code == status.HTTP_201_CREATED, response.data
    data = response.data

    assert str(data["order"]) == str(active_order.id)
    assert data["amount_paid"] == "80000.00"
    assert data["currency"] == "GBP"
    assert data["payment_reference"] == "BARC-WIRE-992837"
    assert data["status"] == VehiclePaymentReportStatusChoices.PENDING_VERIFICATION

    # Refresh order and check transitions
    active_order.refresh_from_db()
    assert active_order.status == VehicleOrderStatusChoices.PAYMENT_SUBMITTED
    assert active_order.payment_submitted_at is not None
    assert active_order.listing.availability_status == VehicleListingAvailabilityChoices.RESERVED

    # Verification event created
    report = VehiclePaymentReport.objects.get(pk=data["id"])
    event = report.verification_events.first()
    assert event is not None
    assert event.event_type == VehiclePaymentVerificationEventTypeChoices.PAYMENT_REPORTED
    assert event.actor == buyer_user


@pytest.mark.django_db
def test_other_buyer_cannot_report_payment(api_client, buyer_b, active_order):
    api_client.force_authenticate(user=buyer_b)

    url = f"/api/v1/marketplace/buyer/vehicle-orders/{active_order.id}/report-payment/"
    payload = {
        "amount_paid": "80000.00",
        "currency": "GBP",
        "payment_reference": "BARC-WIRE-992837",
        "paid_at": timezone.now().isoformat(),
    }

    response = api_client.post(url, payload, format="json")
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_amount_mismatch_rejected(api_client, buyer_user, active_order):
    api_client.force_authenticate(user=buyer_user)

    url = f"/api/v1/marketplace/buyer/vehicle-orders/{active_order.id}/report-payment/"
    payload = {
        "amount_paid": "75000.00",  # agreed is 80,000.00
        "currency": "GBP",
        "payment_reference": "BARC-WIRE-992837",
        "paid_at": timezone.now().isoformat(),
    }

    response = api_client.post(url, payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "does not match agreed order price" in str(response.data)


@pytest.mark.django_db
def test_currency_mismatch_rejected(api_client, buyer_user, active_order):
    api_client.force_authenticate(user=buyer_user)

    url = f"/api/v1/marketplace/buyer/vehicle-orders/{active_order.id}/report-payment/"
    payload = {
        "amount_paid": "80000.00",
        "currency": "EUR",  # agreed is GBP
        "payment_reference": "BARC-WIRE-992837",
        "paid_at": timezone.now().isoformat(),
    }

    response = api_client.post(url, payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "currency" in str(response.data).lower()


@pytest.mark.django_db
def test_future_paid_at_rejected(api_client, buyer_user, active_order):
    api_client.force_authenticate(user=buyer_user)

    url = f"/api/v1/marketplace/buyer/vehicle-orders/{active_order.id}/report-payment/"
    payload = {
        "amount_paid": "80000.00",
        "currency": "GBP",
        "payment_reference": "BARC-WIRE-992837",
        "paid_at": (timezone.now() + timedelta(days=1)).isoformat(),
    }

    response = api_client.post(url, payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "future" in str(response.data).lower()


@pytest.mark.django_db
def test_duplicate_pending_payment_report_blocked(api_client, buyer_user, active_order):
    # First report succeeds
    report_vehicle_order_payment(
        actor=buyer_user,
        order_id=str(active_order.id),
        amount_paid=Decimal("80000.00"),
        currency="GBP",
        payment_reference="FIRST-REF-123",
        paid_at=timezone.now(),
    )

    api_client.force_authenticate(user=buyer_user)
    url = f"/api/v1/marketplace/buyer/vehicle-orders/{active_order.id}/report-payment/"
    payload = {
        "amount_paid": "80000.00",
        "currency": "GBP",
        "payment_reference": "SECOND-REF-456",
        "paid_at": timezone.now().isoformat(),
    }

    response = api_client.post(url, payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "already pending" in str(response.data).lower() or "payment can only be reported" in str(response.data).lower()


# =============================================================================
# 2. Dealer Payment Verification API Tests
# =============================================================================

@pytest.mark.django_db
def test_dealer_confirm_payment_success(api_client, seller_user, buyer_user, active_order):
    # Buyer reports payment
    report = report_vehicle_order_payment(
        actor=buyer_user,
        order_id=str(active_order.id),
        amount_paid=Decimal("80000.00"),
        currency="GBP",
        payment_reference="WIRE-REF-999",
        paid_at=timezone.now(),
    )

    api_client.force_authenticate(user=seller_user)
    url = f"/api/v1/marketplace/seller/vehicle-orders/{active_order.id}/confirm-payment/"
    payload = {"notes": "Funds verified in business account."}

    response = api_client.post(url, payload, format="json")
    assert response.status_code == status.HTTP_200_OK, response.data

    report.refresh_from_db()
    assert report.status == VehiclePaymentReportStatusChoices.CONFIRMED
    assert report.verified_by == seller_user
    assert report.verified_at is not None

    active_order.refresh_from_db()
    assert active_order.status == VehicleOrderStatusChoices.PAYMENT_CONFIRMED
    assert active_order.payment_confirmed_at is not None
    assert active_order.confirmed_by == seller_user

    # Event logged
    confirmed_event = report.verification_events.filter(
        event_type=VehiclePaymentVerificationEventTypeChoices.VERIFICATION_CONFIRMED
    ).first()
    assert confirmed_event is not None
    assert confirmed_event.actor == seller_user


@pytest.mark.django_db
def test_dealer_org_colleague_can_confirm_payment(api_client, dealer_colleague, buyer_user, active_order):
    report_vehicle_order_payment(
        actor=buyer_user,
        order_id=str(active_order.id),
        amount_paid=Decimal("80000.00"),
        currency="GBP",
        payment_reference="WIRE-REF-100",
        paid_at=timezone.now(),
    )

    api_client.force_authenticate(user=dealer_colleague)
    url = f"/api/v1/marketplace/seller/vehicle-orders/{active_order.id}/confirm-payment/"
    response = api_client.post(url, {}, format="json")
    assert response.status_code == status.HTTP_200_OK

    active_order.refresh_from_db()
    assert active_order.status == VehicleOrderStatusChoices.PAYMENT_CONFIRMED
    assert active_order.confirmed_by == dealer_colleague


@pytest.mark.django_db
def test_buyer_cannot_confirm_payment(api_client, buyer_user, active_order):
    report_vehicle_order_payment(
        actor=buyer_user,
        order_id=str(active_order.id),
        amount_paid=Decimal("80000.00"),
        currency="GBP",
        payment_reference="WIRE-REF-101",
        paid_at=timezone.now(),
    )

    api_client.force_authenticate(user=buyer_user)
    url = f"/api/v1/marketplace/seller/vehicle-orders/{active_order.id}/confirm-payment/"
    response = api_client.post(url, {}, format="json")
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_dealer_reject_payment_reverts_order_to_payment_pending(api_client, seller_user, buyer_user, active_order):
    report = report_vehicle_order_payment(
        actor=buyer_user,
        order_id=str(active_order.id),
        amount_paid=Decimal("80000.00"),
        currency="GBP",
        payment_reference="WIRE-REF-102",
        paid_at=timezone.now(),
    )

    api_client.force_authenticate(user=seller_user)
    url = f"/api/v1/marketplace/seller/vehicle-orders/{active_order.id}/reject-payment/"
    payload = {"reason": "Payment reference WIRE-REF-102 not found in Barclays bank statement."}

    response = api_client.post(url, payload, format="json")
    assert response.status_code == status.HTTP_200_OK

    report.refresh_from_db()
    assert report.status == VehiclePaymentReportStatusChoices.REJECTED
    assert report.verified_by == seller_user
    assert "WIRE-REF-102 not found" in report.verification_notes

    # Order returns to PAYMENT_PENDING so buyer can re-submit
    active_order.refresh_from_db()
    assert active_order.status == VehicleOrderStatusChoices.PAYMENT_PENDING
    # Vehicle reservation is PRESERVED
    assert active_order.listing.availability_status == VehicleListingAvailabilityChoices.RESERVED

    # Buyer can re-submit with new reference
    new_report = report_vehicle_order_payment(
        actor=buyer_user,
        order_id=str(active_order.id),
        amount_paid=Decimal("80000.00"),
        currency="GBP",
        payment_reference="CORRECTED-WIRE-777",
        paid_at=timezone.now(),
    )
    assert new_report.status == VehiclePaymentReportStatusChoices.PENDING_VERIFICATION
    active_order.refresh_from_db()
    assert active_order.status == VehicleOrderStatusChoices.PAYMENT_SUBMITTED


@pytest.mark.django_db
def test_dealer_reject_payment_requires_reason(api_client, seller_user, buyer_user, active_order):
    report_vehicle_order_payment(
        actor=buyer_user,
        order_id=str(active_order.id),
        amount_paid=Decimal("80000.00"),
        currency="GBP",
        payment_reference="WIRE-REF-103",
        paid_at=timezone.now(),
    )

    api_client.force_authenticate(user=seller_user)
    url = f"/api/v1/marketplace/seller/vehicle-orders/{active_order.id}/reject-payment/"
    payload = {"reason": ""}

    response = api_client.post(url, payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "explanation" in str(response.data).lower() or "reason" in str(response.data).lower()


@pytest.mark.django_db
def test_dealer_flag_discrepancy(api_client, seller_user, buyer_user, active_order):
    report = report_vehicle_order_payment(
        actor=buyer_user,
        order_id=str(active_order.id),
        amount_paid=Decimal("80000.00"),
        currency="GBP",
        payment_reference="WIRE-REF-104",
        paid_at=timezone.now(),
    )

    api_client.force_authenticate(user=seller_user)
    url = f"/api/v1/marketplace/seller/vehicle-orders/{active_order.id}/flag-payment/"
    payload = {"reason": "Received amount is 500 GBP lower than agreed contract."}

    response = api_client.post(url, payload, format="json")
    assert response.status_code == status.HTTP_200_OK

    report.refresh_from_db()
    assert report.status == VehiclePaymentReportStatusChoices.FLAGGED

    # Order stays in PAYMENT_SUBMITTED
    active_order.refresh_from_db()
    assert active_order.status == VehicleOrderStatusChoices.PAYMENT_SUBMITTED


# =============================================================================
# 3. Lifecycle Protection & Maintenance Tasks
# =============================================================================

@pytest.mark.django_db
def test_payment_submitted_orders_excluded_from_unpaid_order_cancellation(buyer_user, active_order):
    # Buyer reports payment while order is within active deadline
    report_vehicle_order_payment(
        actor=buyer_user,
        order_id=str(active_order.id),
        amount_paid=Decimal("80000.00"),
        currency="GBP",
        payment_reference="WIRE-REF-105",
        paid_at=timezone.now(),
    )

    # Time passes: payment deadline elapses while payment is pending verification
    past_time = timezone.now() - timedelta(hours=2)
    active_order.payment_deadline = past_time
    active_order.save(update_fields=['payment_deadline'])

    # Run auto-cancellation
    cancelled = cancel_expired_payment_orders()
    assert cancelled == 0

    active_order.refresh_from_db()
    assert active_order.status == VehicleOrderStatusChoices.PAYMENT_SUBMITTED
    assert active_order.listing.availability_status == VehicleListingAvailabilityChoices.RESERVED


@pytest.mark.django_db
def test_verification_escalation_milestones(buyer_user, active_order):
    now = timezone.now()

    # Create report submitted 49 hours ago (should trigger 48h warning)
    order_48h = active_order
    order_48h.payment_submitted_at = now - timedelta(hours=49)
    order_48h.status = VehicleOrderStatusChoices.PAYMENT_SUBMITTED
    order_48h.save(update_fields=['payment_submitted_at', 'status'])

    report_48h = VehiclePaymentReport.objects.create(
        order=order_48h,
        submitted_by=buyer_user,
        amount_paid=Decimal("80000.00"),
        currency="GBP",
        payment_reference="WIRE-48H",
        paid_at=now - timedelta(hours=49),
        status=VehiclePaymentReportStatusChoices.PENDING_VERIFICATION,
        escalation_level=VehiclePaymentEscalationLevelChoices.NONE,
    )

    # Run escalations
    results = process_vehicle_payment_verification_escalations()
    assert results["warnings_48h"] >= 1

    report_48h.refresh_from_db()
    assert report_48h.escalation_level == VehiclePaymentEscalationLevelChoices.WARNING_48H

    # Test 72h overdue milestone
    order_48h.payment_submitted_at = now - timedelta(hours=75)
    order_48h.save(update_fields=['payment_submitted_at'])

    results2 = process_vehicle_payment_verification_escalations()
    assert results2["overdue_72h"] >= 1

    report_48h.refresh_from_db()
    assert report_48h.escalation_level == VehiclePaymentEscalationLevelChoices.OVERDUE_72H

    # Test 120h operations escalation milestone
    order_48h.payment_submitted_at = now - timedelta(hours=125)
    order_48h.save(update_fields=['payment_submitted_at'])

    results3 = process_vehicle_payment_verification_escalations()
    assert results3["escalated_120h"] >= 1

    report_48h.refresh_from_db()
    assert report_48h.escalation_level == VehiclePaymentEscalationLevelChoices.ESCALATED_120H

    # Monotonic: subsequent runs do not re-escalate or duplicate
    results4 = process_vehicle_payment_verification_escalations()
    assert results4["escalated_120h"] == 0
    assert results4["overdue_72h"] == 0
    assert results4["warnings_48h"] == 0


@pytest.mark.django_db
def test_immutable_payment_verification_event(buyer_user, active_order):
    report = report_vehicle_order_payment(
        actor=buyer_user,
        order_id=str(active_order.id),
        amount_paid=Decimal("80000.00"),
        currency="GBP",
        payment_reference="WIRE-REF-IMMUTABLE",
        paid_at=timezone.now(),
    )
    event = report.verification_events.first()
    assert event is not None

    with pytest.raises(ImmutableRecordError):
        event.notes = "Mutated note"
        event.save()

    with pytest.raises(ImmutableRecordError):
        event.delete()


# =============================================================================
# 4. Phase 2 Workflow Gap Verification Tests
# =============================================================================

@pytest.mark.django_db
def test_dealer_can_confirm_flagged_payment_report(api_client, seller_user, buyer_user, active_order):
    """
    Workflow Gap 1: A dealer can resolve a FLAGGED report by confirming payment
    once the discrepancy is resolved (e.g., funds confirmed received).
    Verifies that the order moves to PAYMENT_CONFIRMED, all historical events
    (SUBMITTED, FLAGGED, CONFIRMED) are preserved, and buyer is notified.
    """
    report = report_vehicle_order_payment(
        actor=buyer_user,
        order_id=str(active_order.id),
        amount_paid=Decimal("80000.00"),
        currency="GBP",
        payment_reference="WIRE-FLAG-CONFIRM-01",
        paid_at=timezone.now(),
    )
    assert report.status == VehiclePaymentReportStatusChoices.PENDING_VERIFICATION

    # Step 1: Dealer flags discrepancy
    api_client.force_authenticate(user=seller_user)
    flag_res = api_client.post(
        f"/api/v1/marketplace/seller/vehicle-orders/{active_order.id}/flag-payment/",
        {"reason": "Payment received was GBP 79,980 due to intermediary bank deduction. Awaiting balance."},
        format="json",
    )
    assert flag_res.status_code == status.HTTP_200_OK
    report.refresh_from_db()
    assert report.status == VehiclePaymentReportStatusChoices.FLAGGED
    active_order.refresh_from_db()
    assert active_order.status == VehicleOrderStatusChoices.PAYMENT_SUBMITTED

    # Step 2: Dealer subsequently confirms payment after balance is settled
    confirm_res = api_client.post(
        f"/api/v1/marketplace/seller/vehicle-orders/{active_order.id}/confirm-payment/",
        {"notes": "Balance received and reconciled. Total GBP 80,000 received."},
        format="json",
    )
    assert confirm_res.status_code == status.HTTP_200_OK

    active_order.refresh_from_db()
    assert active_order.status == VehicleOrderStatusChoices.PAYMENT_CONFIRMED
    assert active_order.payment_confirmed_at is not None

    report.refresh_from_db()
    assert report.status == VehiclePaymentReportStatusChoices.CONFIRMED

    # Step 3: Verify all 3 verification events exist and are immutable
    event_types = list(report.verification_events.values_list('event_type', flat=True))
    assert VehiclePaymentVerificationEventTypeChoices.PAYMENT_REPORTED in event_types
    assert VehiclePaymentVerificationEventTypeChoices.VERIFICATION_FLAGGED in event_types
    assert VehiclePaymentVerificationEventTypeChoices.VERIFICATION_CONFIRMED in event_types

    # Step 4: Verify buyer notification was generated
    assert Notification.objects.filter(
        recipient=buyer_user,
        event_type='marketplace.vehicle_order.payment_confirmed',
    ).exists()


@pytest.mark.django_db
def test_dealer_can_reject_flagged_payment_report(api_client, seller_user, buyer_user, active_order):
    """
    Workflow Gap 1: A dealer can resolve a FLAGGED report by rejecting it
    with a documented reason if the discrepancy cannot be reconciled.
    Verifies that order reverts to PAYMENT_PENDING, listing remains RESERVED,
    and buyer is notified.
    """
    report = report_vehicle_order_payment(
        actor=buyer_user,
        order_id=str(active_order.id),
        amount_paid=Decimal("80000.00"),
        currency="GBP",
        payment_reference="WIRE-FLAG-REJECT-02",
        paid_at=timezone.now(),
    )

    api_client.force_authenticate(user=seller_user)
    # Dealer flags discrepancy first
    flag_res = api_client.post(
        f"/api/v1/marketplace/seller/vehicle-orders/{active_order.id}/flag-payment/",
        {"reason": "Payment reference invalid; investigating with bank."},
        format="json",
    )
    assert flag_res.status_code == status.HTTP_200_OK

    # Dealer resolves by rejecting after confirming with bank
    reject_res = api_client.post(
        f"/api/v1/marketplace/seller/vehicle-orders/{active_order.id}/reject-payment/",
        {"reason": "Bank confirmed no remittance under reference WIRE-FLAG-REJECT-02. Please re-send with correct reference."},
        format="json",
    )
    assert reject_res.status_code == status.HTTP_200_OK

    active_order.refresh_from_db()
    assert active_order.status == VehicleOrderStatusChoices.PAYMENT_PENDING
    assert active_order.listing.availability_status == VehicleListingAvailabilityChoices.RESERVED

    report.refresh_from_db()
    assert report.status == VehiclePaymentReportStatusChoices.REJECTED

    event_types = list(report.verification_events.values_list('event_type', flat=True))
    assert VehiclePaymentVerificationEventTypeChoices.VERIFICATION_FLAGGED in event_types
    assert VehiclePaymentVerificationEventTypeChoices.VERIFICATION_REJECTED in event_types

    assert Notification.objects.filter(
        recipient=buyer_user,
        event_type='marketplace.vehicle_order.payment_rejected',
    ).exists()


@pytest.mark.django_db
def test_rejection_before_original_deadline_allows_resubmission(buyer_user, seller_user, active_order):
    """
    Workflow Gap 2: When payment is rejected BEFORE the original 5-business-day
    deadline, the buyer is permitted to re-submit payment details. The original
    deadline is NOT extended or reset, and the vehicle remains RESERVED.
    """
    # Order has a deadline 3 days in the future
    future_deadline = timezone.now() + timedelta(days=3)
    active_order.payment_deadline = future_deadline
    active_order.save(update_fields=['payment_deadline'])

    # Buyer submits first report
    report1 = report_vehicle_order_payment(
        actor=buyer_user,
        order_id=str(active_order.id),
        amount_paid=Decimal("80000.00"),
        currency="GBP",
        payment_reference="TYPO-REF-001",
        paid_at=timezone.now(),
    )

    # Dealer rejects first report
    reject_vehicle_order_payment(
        order_id=str(active_order.id),
        actor=seller_user,
        reason="Account number typo on remittance",
    )

    active_order.refresh_from_db()
    assert active_order.status == VehicleOrderStatusChoices.PAYMENT_PENDING
    assert active_order.payment_deadline == future_deadline  # Original deadline preserved
    assert active_order.listing.availability_status == VehicleListingAvailabilityChoices.RESERVED

    # Buyer re-submits before deadline
    report2 = report_vehicle_order_payment(
        actor=buyer_user,
        order_id=str(active_order.id),
        amount_paid=Decimal("80000.00"),
        currency="GBP",
        payment_reference="CORRECTED-REF-002",
        paid_at=timezone.now(),
    )

    active_order.refresh_from_db()
    assert active_order.status == VehicleOrderStatusChoices.PAYMENT_SUBMITTED
    assert active_order.payment_reports.count() == 2

    report1.refresh_from_db()
    assert report1.status == VehiclePaymentReportStatusChoices.REJECTED
    assert report2.status == VehiclePaymentReportStatusChoices.PENDING_VERIFICATION


@pytest.mark.django_db
def test_rejection_after_original_deadline_blocks_resubmission(buyer_user, seller_user, active_order):
    """
    Workflow Gap 2: When payment is rejected AFTER the original 5-business-day
    deadline, the buyer is PROHIBITED from submitting a new payment report.
    The order returns to PAYMENT_PENDING in an expired state until cancelled.
    """
    past_deadline = timezone.now() - timedelta(hours=1)
    active_order.payment_deadline = past_deadline
    active_order.status = VehicleOrderStatusChoices.PAYMENT_SUBMITTED
    active_order.save(update_fields=['payment_deadline', 'status'])

    # Existing report submitted prior to deadline
    VehiclePaymentReport.objects.create(
        order=active_order,
        submitted_by=buyer_user,
        amount_paid=Decimal("80000.00"),
        currency="GBP",
        payment_reference="ORIGINAL-PAST-DEADLINE",
        paid_at=past_deadline - timedelta(hours=2),
        status=VehiclePaymentReportStatusChoices.PENDING_VERIFICATION,
    )

    # Dealer rejects after original deadline has elapsed
    reject_vehicle_order_payment(
        order_id=str(active_order.id),
        actor=seller_user,
        reason="Payment never arrived; deadline has passed.",
    )

    active_order.refresh_from_db()
    assert active_order.status == VehicleOrderStatusChoices.PAYMENT_PENDING
    assert active_order.payment_deadline == past_deadline

    # Buyer attempts to re-submit -> must be blocked with ValidationError
    with pytest.raises(ValidationError) as exc_info:
        report_vehicle_order_payment(
            actor=buyer_user,
            order_id=str(active_order.id),
            amount_paid=Decimal("80000.00"),
            currency="GBP",
            payment_reference="LATE-RESUBMIT",
            paid_at=timezone.now(),
        )

    err_msg = str(exc_info.value).lower()
    assert "payment deadline" in err_msg
    assert "expired" in err_msg


@pytest.mark.django_db
def test_expiry_command_cancels_order_rejected_after_deadline(buyer_user, seller_user, active_order):
    """
    Workflow Gap 2: When an order is rejected after the deadline, the scheduled
    expiry job (cancel_expired_payment_orders) safely cancels the order, sets
    the cancellation reason, and restores the listing to AVAILABLE, while
    preserving all payment report and verification event records.
    """
    past_deadline = timezone.now() - timedelta(hours=3)
    active_order.payment_deadline = past_deadline
    active_order.status = VehicleOrderStatusChoices.PAYMENT_SUBMITTED
    active_order.save(update_fields=['payment_deadline', 'status'])

    report = VehiclePaymentReport.objects.create(
        order=active_order,
        submitted_by=buyer_user,
        amount_paid=Decimal("80000.00"),
        currency="GBP",
        payment_reference="EXPIRED-TEST-REF",
        paid_at=past_deadline - timedelta(hours=5),
        status=VehiclePaymentReportStatusChoices.PENDING_VERIFICATION,
    )

    # Dealer rejects after deadline
    reject_vehicle_order_payment(
        order_id=str(active_order.id),
        actor=seller_user,
        reason="Funds not received.",
    )

    # Order is now in PAYMENT_PENDING with past deadline
    cancelled_count = cancel_expired_payment_orders()
    assert cancelled_count >= 1

    active_order.refresh_from_db()
    assert active_order.status == VehicleOrderStatusChoices.CANCELLED
    assert "Payment deadline of 5 business days expired" in active_order.cancellation_reason

    active_order.listing.refresh_from_db()
    assert active_order.listing.availability_status == VehicleListingAvailabilityChoices.AVAILABLE

    # Historical records must be completely preserved
    assert active_order.payment_reports.count() == 1
    report.refresh_from_db()
    assert report.status == VehiclePaymentReportStatusChoices.REJECTED
    assert report.verification_events.count() >= 1


@pytest.mark.django_db
def test_notification_delivery_and_deduplication_on_repeated_escalations(buyer_user, active_order):
    """
    Workflow Gap 3: Notifications are delivered via the audit log signal pipeline,
    and repeated escalation checks do not duplicate notifications or audit entries.
    """
    now = timezone.now()
    active_order.payment_submitted_at = now - timedelta(hours=49)
    active_order.status = VehicleOrderStatusChoices.PAYMENT_SUBMITTED
    active_order.save(update_fields=['payment_submitted_at', 'status'])

    VehiclePaymentReport.objects.create(
        order=active_order,
        submitted_by=buyer_user,
        amount_paid=Decimal("80000.00"),
        currency="GBP",
        payment_reference="WIRE-NOTIF-TEST",
        paid_at=now - timedelta(hours=49),
        status=VehiclePaymentReportStatusChoices.PENDING_VERIFICATION,
        escalation_level=VehiclePaymentEscalationLevelChoices.NONE,
    )

    # First pass: triggers 48h warning
    results1 = process_vehicle_payment_verification_escalations()
    assert results1["warnings_48h"] >= 1

    initial_notif_count = Notification.objects.filter(
        recipient=active_order.seller,
        event_type="marketplace.vehicle_order.verification_warning_48h",
    ).count()
    assert initial_notif_count >= 1

    # Second pass: repeated execution without time passage must not produce new notifications
    results2 = process_vehicle_payment_verification_escalations()
    assert results2["warnings_48h"] == 0

    subsequent_notif_count = Notification.objects.filter(
        recipient=active_order.seller,
        event_type="marketplace.vehicle_order.verification_warning_48h",
    ).count()
    assert subsequent_notif_count == initial_notif_count


