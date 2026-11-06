import hashlib
import hmac
import json
import uuid
from decimal import Decimal
from datetime import date, timedelta

import pytest
from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.identity.models import User, RoleChoices
from apps.organisations.models import (
    Organisation,
    OrganisationRoleChoices,
    OrganisationTypeChoices,
)
from apps.garage.models import GarageVehicle
from apps.marketplace.payments.razorpay_provider import RazorpayPaymentProvider
from apps.marketplace.payments.stripe_provider import StripePaymentProvider
from apps.workshops.models import (
    WorkshopProfile,
    WorkshopBooking,
    WorkshopQuotation,
    QuotationLineItem,
    BookingStatusChoices,
    QuotationStatusChoices,
    DepositStatusChoices,
    LineItemTypeChoices,
    WorkOrder,
    WorkshopDepositWebhookEvent,
)
from apps.workshops.services import QuotationService
from apps.workshops.deposit_service import WorkshopDepositPaymentService
from platform_core.audit.models import AuditLog


def build_razorpay_signature(order_id: str, payment_id: str, secret: str) -> str:
    msg = f"{order_id}|{payment_id}".encode('utf-8')
    return hmac.new(secret.encode('utf-8'), msg, hashlib.sha256).hexdigest()


def build_razorpay_webhook_signature(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode('utf-8'), body, hashlib.sha256).hexdigest()


@pytest.fixture
def owner_user(db):
    user = User.objects.create_user(
        email=f"owner_{uuid.uuid4().hex[:6]}@apexmotors.com",
        password="Password123!",
        first_name="Oliver",
        last_name="Owner",
        is_email_verified=True,
    )
    user.add_role(RoleChoices.WORKSHOP)
    return user


@pytest.fixture
def buyer_user(db):
    user = User.objects.create_user(
        email=f"buyer_{uuid.uuid4().hex[:6]}@driverxtra.com",
        password="Password123!",
        first_name="Charlie",
        last_name="Customer",
        is_email_verified=True,
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.fixture
def other_buyer_user(db):
    user = User.objects.create_user(
        email=f"other_{uuid.uuid4().hex[:6]}@driverxtra.com",
        password="Password123!",
        first_name="Eve",
        last_name="External",
        is_email_verified=True,
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.fixture
def in_workshop_org(db, owner_user):
    org = Organisation.objects.create(
        name="Apex Motors Mumbai",
        type=OrganisationTypeChoices.WORKSHOP,
        country="IN",
        jurisdiction="IN-MH",
        created_by=owner_user,
    )
    org.add_member(owner_user, role=OrganisationRoleChoices.OWNER)
    return org


@pytest.fixture
def in_workshop_profile(db, in_workshop_org):
    return WorkshopProfile.objects.create(
        organisation=in_workshop_org,
        business_name="Apex Motors India",
        slug=f"apex-in-{uuid.uuid4().hex[:6]}",
        city="Mumbai",
        country="IN",
        currency="INR",
        bay_capacity=3,
        requires_deposit=True,
        default_deposit_percentage=Decimal('20.00'),
        is_tax_registered=False,
        can_collect_tax=False,
        is_accepting_bookings=True,
        is_verified=True,
    )


@pytest.fixture
def gb_workshop_org(db, owner_user):
    org = Organisation.objects.create(
        name="Apex Motors London",
        type=OrganisationTypeChoices.WORKSHOP,
        country="GB",
        created_by=owner_user,
    )
    org.add_member(owner_user, role=OrganisationRoleChoices.OWNER)
    return org


@pytest.fixture
def gb_workshop_profile(db, gb_workshop_org):
    return WorkshopProfile.objects.create(
        organisation=gb_workshop_org,
        business_name="Apex Motors UK",
        slug=f"apex-uk-{uuid.uuid4().hex[:6]}",
        city="London",
        country="GB",
        currency="GBP",
        bay_capacity=3,
        requires_deposit=True,
        default_deposit_percentage=Decimal('15.00'),
        is_tax_registered=True,
        can_collect_tax=True,
        default_tax_rate_percent=Decimal('20.00'),
        is_accepting_bookings=True,
        is_verified=True,
    )


@pytest.fixture
def in_vehicle(db, buyer_user):
    return GarageVehicle.objects.create(
        user=buyer_user,
        make="Hyundai",
        model="Creta",
        year=2022,
        registration_plate="MH01 AB1234",
    )


@pytest.fixture
def in_booking(db, in_workshop_profile, buyer_user, in_vehicle):
    return WorkshopBooking.objects.create(
        workshop=in_workshop_profile,
        buyer=buyer_user,
        vehicle=in_vehicle,
        preferred_date=date.today() + timedelta(days=3),
        status=BookingStatusChoices.REQUESTED,
    )


@pytest.fixture
def gb_vehicle(db, buyer_user):
    return GarageVehicle.objects.create(
        user=buyer_user,
        make="BMW",
        model="330e",
        year=2021,
        registration_plate="GF21 XTR",
    )


@pytest.fixture
def gb_booking(db, gb_workshop_profile, buyer_user, gb_vehicle):
    return WorkshopBooking.objects.create(
        workshop=gb_workshop_profile,
        buyer=buyer_user,
        vehicle=gb_vehicle,
        preferred_date=date.today() + timedelta(days=3),
        status=BookingStatusChoices.REQUESTED,
    )


@pytest.fixture
def buyer_client(buyer_user):
    client = APIClient()
    client.force_authenticate(user=buyer_user)
    return client


@pytest.fixture
def other_client(other_buyer_user):
    client = APIClient()
    client.force_authenticate(user=other_buyer_user)
    return client


# =============================================================================
# 1. QUOTATION DRAFTING & DEPOSIT AUTOMATION
# =============================================================================

@pytest.mark.django_db
def test_quotation_draft_inherits_workshop_deposit_config(in_booking, owner_user):
    """When workshop requires deposit, draft quotation auto-populates deposit settings and calculates amount."""
    quote = QuotationService.create_or_revise_quotation(
        booking=in_booking,
        data={
            "line_items": [
                {
                    "item_type": LineItemTypeChoices.LABOUR,
                    "description": "General Periodic Service",
                    "quantity": Decimal("1.00"),
                    "unit_price": Decimal("5000.00"),
                }
            ],
        },
        actor=owner_user,
    )
    quote.refresh_from_db()
    assert quote.requires_deposit is True
    assert quote.deposit_percentage == Decimal("20.00")
    # 20% of 5000 = 1000.00
    assert quote.deposit_amount == Decimal("1000.00")
    assert quote.deposit_status == DepositStatusChoices.NOT_REQUIRED


@pytest.mark.django_db
def test_quotation_issue_transitions_deposit_to_pending(in_booking, owner_user):
    """Issuing a quotation requiring a deposit sets deposit_status to PENDING."""
    quote = QuotationService.create_or_revise_quotation(
        booking=in_booking,
        data={
            "requires_deposit": True,
            "deposit_percentage": Decimal("25.00"),
            "line_items": [
                {
                    "item_type": LineItemTypeChoices.LABOUR,
                    "description": "Brake Pad Replacement",
                    "quantity": Decimal("1.00"),
                    "unit_price": Decimal("4000.00"),
                }
            ],
        },
        actor=owner_user,
    )
    issued = QuotationService.issue_quotation(quote, actor=owner_user)
    issued.refresh_from_db()
    assert issued.status == QuotationStatusChoices.ISSUED
    assert issued.deposit_status == DepositStatusChoices.PENDING
    assert issued.deposit_amount == Decimal("1000.00")


@pytest.mark.django_db
def test_direct_acceptance_blocked_when_deposit_unpaid(in_booking, owner_user, buyer_user, buyer_client):
    """Customer cannot accept quotation requiring deposit without paying deposit first."""
    quote = QuotationService.create_or_revise_quotation(
        booking=in_booking,
        data={
            "requires_deposit": True,
            "deposit_percentage": Decimal("10.00"),
            "line_items": [
                {
                    "item_type": LineItemTypeChoices.LABOUR,
                    "description": "Oil Change",
                    "quantity": Decimal("1.00"),
                    "unit_price": Decimal("2000.00"),
                }
            ],
        },
        actor=owner_user,
    )
    QuotationService.issue_quotation(quote, actor=owner_user)

    # Direct API accept call must be rejected
    res = buyer_client.post(f"/api/v1/workshops/quotations/{quote.id}/accept/")
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "deposit payment" in res.data["message"].lower()

    # Database state unchanged
    quote.refresh_from_db()
    assert quote.status == QuotationStatusChoices.ISSUED
    assert WorkOrder.objects.filter(booking=in_booking).count() == 0


# =============================================================================
# 2. RAZORPAY DEPOSIT PAYMENT LIFECYCLE
# =============================================================================

@pytest.mark.django_db
def test_razorpay_deposit_session_creation(in_booking, owner_user, buyer_client):
    """Buyer creates payment session via Razorpay gateway."""
    quote = QuotationService.create_or_revise_quotation(
        booking=in_booking,
        data={
            "requires_deposit": True,
            "deposit_percentage": Decimal("20.00"),
            "line_items": [
                {
                    "item_type": LineItemTypeChoices.LABOUR,
                    "description": "Clutch Overhaul",
                    "quantity": Decimal("1.00"),
                    "unit_price": Decimal("10000.00"),
                }
            ],
        },
        actor=owner_user,
    )
    QuotationService.issue_quotation(quote, actor=owner_user)

    res = buyer_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/create/", {
        "preferred_provider": "RAZORPAY",
    }, format="json")

    assert res.status_code == status.HTTP_201_CREATED, res.data
    assert res.data["status"] == "success"
    assert res.data["deposit_amount"] == "2000.00"
    session = res.data["payment_session"]
    assert session["provider"] == "RAZORPAY"
    assert session["currency"] == "INR"
    assert session["amount_minor"] == 200000  # 2000 INR = 200,000 paise
    assert "provider_order_id" in session

    quote.refresh_from_db()
    assert quote.deposit_status == DepositStatusChoices.PROCESSING
    assert quote.deposit_order_id == session["provider_order_id"]
    assert quote.deposit_provider == "RAZORPAY"


@pytest.mark.django_db
def test_razorpay_deposit_verification_success(in_booking, owner_user, buyer_client):
    """Authoritative HMAC signature verification marks deposit PAID, quotation ACCEPTED, and creates WorkOrder."""
    quote = QuotationService.create_or_revise_quotation(
        booking=in_booking,
        data={
            "requires_deposit": True,
            "deposit_percentage": Decimal("20.00"),
            "line_items": [
                {
                    "item_type": LineItemTypeChoices.LABOUR,
                    "description": "Suspension Replacement",
                    "quantity": Decimal("1.00"),
                    "unit_price": Decimal("8000.00"),
                }
            ],
        },
        actor=owner_user,
    )
    QuotationService.issue_quotation(quote, actor=owner_user)

    # 1. Create deposit session
    s_res = buyer_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/create/", format="json")
    order_id = s_res.data["payment_session"]["provider_order_id"]
    payment_id = f"pay_test_{uuid.uuid4().hex[:10]}"

    provider = RazorpayPaymentProvider()
    valid_signature = build_razorpay_signature(order_id, payment_id, provider.key_secret)

    # 2. Verify payment
    v_res = buyer_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/verify/", {
        "razorpay_order_id": order_id,
        "razorpay_payment_id": payment_id,
        "razorpay_signature": valid_signature,
        "amount": "1600.00",
        "currency": "INR",
    }, format="json")

    assert v_res.status_code == status.HTTP_200_OK, v_res.data
    assert v_res.data["status"] == "success"

    quote.refresh_from_db()
    assert quote.deposit_status == DepositStatusChoices.PAID
    assert quote.status == QuotationStatusChoices.ACCEPTED
    assert quote.deposit_transaction_id == payment_id
    assert quote.deposit_paid_at is not None

    in_booking.refresh_from_db()
    assert in_booking.status == BookingStatusChoices.CONFIRMED

    # WorkOrder generated automatically
    wo = WorkOrder.objects.filter(booking=in_booking).first()
    assert wo is not None
    assert wo.quotation_id == quote.id

    # Financial audit entry verified
    audit = AuditLog.objects.filter(
        event_type="workshop.quotation.deposit_paid",
        resource_id=str(quote.id),
    ).first()
    assert audit is not None
    assert audit.metadata["deposit_amount"] == "1600.00"


@pytest.mark.django_db
def test_razorpay_invalid_signature_rejected(in_booking, owner_user, buyer_client):
    """Tampered or invalid Razorpay signature is rejected and status transitions to FAILED."""
    quote = QuotationService.create_or_revise_quotation(
        booking=in_booking,
        data={
            "requires_deposit": True,
            "deposit_percentage": Decimal("20.00"),
            "line_items": [
                {
                    "item_type": LineItemTypeChoices.LABOUR,
                    "description": "Engine Diagnostics",
                    "quantity": Decimal("1.00"),
                    "unit_price": Decimal("3000.00"),
                }
            ],
        },
        actor=owner_user,
    )
    QuotationService.issue_quotation(quote, actor=owner_user)

    s_res = buyer_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/create/", format="json")
    order_id = s_res.data["payment_session"]["provider_order_id"]
    payment_id = f"pay_test_{uuid.uuid4().hex[:10]}"

    # Tampered signature
    v_res = buyer_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/verify/", {
        "razorpay_order_id": order_id,
        "razorpay_payment_id": payment_id,
        "razorpay_signature": "tampered_invalid_signature_9999",
    }, format="json")

    assert v_res.status_code == status.HTTP_400_BAD_REQUEST
    assert "verification failed" in v_res.data["message"].lower()

    quote.refresh_from_db()
    assert quote.deposit_status == DepositStatusChoices.FAILED
    assert quote.status == QuotationStatusChoices.ISSUED
    assert WorkOrder.objects.filter(booking=in_booking).count() == 0


@pytest.mark.django_db
def test_razorpay_order_id_mismatch_rejected(in_booking, owner_user, buyer_client):
    """Mismatched Razorpay order ID is strictly rejected."""
    quote = QuotationService.create_or_revise_quotation(
        booking=in_booking,
        data={
            "requires_deposit": True,
            "deposit_percentage": Decimal("20.00"),
            "line_items": [
                {
                    "item_type": LineItemTypeChoices.LABOUR,
                    "description": "Battery Check",
                    "quantity": Decimal("1.00"),
                    "unit_price": Decimal("1000.00"),
                }
            ],
        },
        actor=owner_user,
    )
    QuotationService.issue_quotation(quote, actor=owner_user)
    buyer_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/create/", format="json")

    v_res = buyer_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/verify/", {
        "razorpay_order_id": "order_completely_wrong_12345",
        "razorpay_payment_id": "pay_test_1234",
        "razorpay_signature": "sig",
    }, format="json")

    assert v_res.status_code == status.HTTP_400_BAD_REQUEST
    assert "does not match" in v_res.data["message"].lower()


@pytest.mark.django_db
def test_deposit_verification_idempotency(in_booking, owner_user, buyer_client):
    """Subsequent verification calls on already PAID deposit return gracefully without duplicate operations."""
    quote = QuotationService.create_or_revise_quotation(
        booking=in_booking,
        data={
            "requires_deposit": True,
            "deposit_percentage": Decimal("50.00"),
            "line_items": [
                {
                    "item_type": LineItemTypeChoices.LABOUR,
                    "description": "Windshield Replacement",
                    "quantity": Decimal("1.00"),
                    "unit_price": Decimal("6000.00"),
                }
            ],
        },
        actor=owner_user,
    )
    QuotationService.issue_quotation(quote, actor=owner_user)

    s_res = buyer_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/create/", format="json")
    order_id = s_res.data["payment_session"]["provider_order_id"]
    payment_id = f"pay_test_{uuid.uuid4().hex[:10]}"
    provider = RazorpayPaymentProvider()
    valid_signature = build_razorpay_signature(order_id, payment_id, provider.key_secret)

    payload = {
        "razorpay_order_id": order_id,
        "razorpay_payment_id": payment_id,
        "razorpay_signature": valid_signature,
    }

    # First verification
    res1 = buyer_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/verify/", payload, format="json")
    assert res1.status_code == status.HTTP_200_OK

    # Second verification (replay)
    res2 = buyer_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/verify/", payload, format="json")
    assert res2.status_code == status.HTTP_200_OK

    # Exactly 1 WorkOrder exists
    assert WorkOrder.objects.filter(booking=in_booking).count() == 1


# =============================================================================
# 3. SECURITY & PERMISSIONS
# =============================================================================

@pytest.mark.django_db
def test_unauthorized_user_cannot_initiate_or_verify_deposit(in_booking, owner_user, other_client):
    """A user who is not the booking customer cannot create session or verify deposit."""
    quote = QuotationService.create_or_revise_quotation(
        booking=in_booking,
        data={
            "requires_deposit": True,
            "deposit_percentage": Decimal("20.00"),
            "line_items": [
                {
                    "item_type": LineItemTypeChoices.LABOUR,
                    "description": "Air Filter Replacement",
                    "quantity": Decimal("1.00"),
                    "unit_price": Decimal("1000.00"),
                }
            ],
        },
        actor=owner_user,
    )
    QuotationService.issue_quotation(quote, actor=owner_user)

    # Eve tries to create session
    c_res = other_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/create/", format="json")
    assert c_res.status_code == status.HTTP_403_FORBIDDEN

    # Eve tries to verify
    v_res = other_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/verify/", {
        "razorpay_order_id": "order_123",
        "razorpay_payment_id": "pay_123",
        "razorpay_signature": "sig",
    }, format="json")
    assert v_res.status_code == status.HTTP_403_FORBIDDEN


# =============================================================================
# 4. WEBHOOK PROCESSING & REPLAY DEFENSE
# =============================================================================

@pytest.mark.django_db
def test_razorpay_webhook_successful_payment(in_booking, owner_user, buyer_client):
    """Razorpay payment.captured webhook atomically transitions quotation to ACCEPTED and booking to CONFIRMED."""
    client = APIClient()
    quote = QuotationService.create_or_revise_quotation(
        booking=in_booking,
        data={
            "requires_deposit": True,
            "deposit_percentage": Decimal("30.00"),
            "line_items": [
                {
                    "item_type": LineItemTypeChoices.LABOUR,
                    "description": "Timing Belt Inspection",
                    "quantity": Decimal("1.00"),
                    "unit_price": Decimal("5000.00"),
                }
            ],
        },
        actor=owner_user,
    )
    QuotationService.issue_quotation(quote, actor=owner_user)

    # Initiate deposit session
    s_res = buyer_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/create/", format="json")
    order_id = s_res.data["payment_session"]["provider_order_id"]
    payment_id = f"pay_hook_{uuid.uuid4().hex[:10]}"
    event_id = f"evt_rzp_{uuid.uuid4().hex[:12]}"

    provider = RazorpayPaymentProvider()

    webhook_payload = {
        "event": "payment.captured",
        "event_id": event_id,
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": order_id,
                    "amount": 150000,
                    "currency": "INR",
                    "status": "captured",
                }
            }
        }
    }
    raw_body = json.dumps(webhook_payload).encode('utf-8')
    sig = build_razorpay_webhook_signature(raw_body, provider.webhook_secret)

    response = client.post(
        "/api/v1/workshops/deposit/webhook/razorpay/",
        data=raw_body,
        content_type="application/json",
        HTTP_X_RAZORPAY_SIGNATURE=sig,
    )

    assert response.status_code == status.HTTP_200_OK, response.data
    assert response.data["status"] == "success"

    quote.refresh_from_db()
    assert quote.deposit_status == DepositStatusChoices.PAID
    assert quote.status == QuotationStatusChoices.ACCEPTED
    assert quote.deposit_transaction_id == payment_id

    # Webhook audit event recorded
    evt = WorkshopDepositWebhookEvent.objects.filter(event_id=event_id).first()
    assert evt is not None
    assert evt.processed is True
    assert evt.quotation_id == quote.id

    # Idempotent replay: Sending the exact same webhook again returns 200 OK without re-processing
    replay_resp = client.post(
        "/api/v1/workshops/deposit/webhook/razorpay/",
        data=raw_body,
        content_type="application/json",
        HTTP_X_RAZORPAY_SIGNATURE=sig,
    )
    assert replay_resp.status_code == status.HTTP_200_OK
    assert "already processed" in replay_resp.data["message"].lower()


@pytest.mark.django_db
def test_razorpay_webhook_invalid_signature_rejected():
    """Incoming webhook with invalid signature is rejected with 400 Bad Request."""
    client = APIClient()
    payload = {"event": "payment.captured", "id": "fake_evt"}
    raw_body = json.dumps(payload).encode('utf-8')

    response = client.post(
        "/api/v1/workshops/deposit/webhook/razorpay/",
        data=raw_body,
        content_type="application/json",
        HTTP_X_RAZORPAY_SIGNATURE="invalid_signature_9999",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "invalid webhook signature" in response.data["message"].lower()


# =============================================================================
# 5. STRIPE DEPOSIT PAYMENTS (GBP / UK WORKSHOPS)
# =============================================================================

@pytest.mark.django_db
def test_stripe_deposit_session_and_verification_gbp(gb_booking, owner_user, buyer_client):
    """GBP UK quotations correctly use Stripe provider for deposit sessions and verification."""
    quote = QuotationService.create_or_revise_quotation(
        booking=gb_booking,
        data={
            "requires_deposit": True,
            "deposit_percentage": Decimal("20.00"),
            "tax_rate_percent": Decimal("20.00"),
            "line_items": [
                {
                    "item_type": LineItemTypeChoices.LABOUR,
                    "description": "Class 4 MOT & Health Check",
                    "quantity": Decimal("1.00"),
                    "unit_price": Decimal("100.00"),
                }
            ],
        },
        actor=owner_user,
    )
    QuotationService.issue_quotation(quote, actor=owner_user)

    # 1. Create session (total = £120.00 incl VAT, deposit 20% = £24.00)
    s_res = buyer_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/create/", format="json")
    assert s_res.status_code == status.HTTP_201_CREATED, s_res.data
    session = s_res.data["payment_session"]
    assert session["provider"] == "STRIPE"
    assert session["currency"] == "GBP"
    assert session["amount_minor"] == 2400  # £24.00 = 2400 pence

    pi_id = session["provider_order_id"]

    # 2. Verify payment
    v_res = buyer_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/verify/", {
        "payment_intent_id": pi_id,
        "amount": "24.00",
        "currency": "GBP",
    }, format="json")

    assert v_res.status_code == status.HTTP_200_OK, v_res.data
    quote.refresh_from_db()
    assert quote.deposit_status == DepositStatusChoices.PAID
    assert quote.status == QuotationStatusChoices.ACCEPTED
    assert quote.deposit_transaction_id == pi_id

    gb_booking.refresh_from_db()
    assert gb_booking.status == BookingStatusChoices.CONFIRMED


# =============================================================================
# 6. COMPREHENSIVE GATEWAY CHECKOUT & EDGE CASE TESTS
# =============================================================================

@pytest.mark.django_db
def test_razorpay_checkout_failure_flow(in_booking, owner_user, buyer_client):
    """
    When payment fails or is declined at checkout, verification payload is rejected,
    deposit_status transitions to FAILED, quotation remains ISSUED (not accepted),
    booking is not confirmed, and no WorkOrder is generated.
    """
    quote = QuotationService.create_or_revise_quotation(
        booking=in_booking,
        data={
            "requires_deposit": True,
            "deposit_percentage": Decimal("20.00"),
            "line_items": [
                {
                    "item_type": LineItemTypeChoices.LABOUR,
                    "description": "Brake Rotor Skimming",
                    "quantity": Decimal("1.00"),
                    "unit_price": Decimal("5000.00"),
                }
            ],
        },
        actor=owner_user,
    )
    QuotationService.issue_quotation(quote, actor=owner_user)

    # 1. Create session
    s_res = buyer_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/create/", format="json")
    order_id = s_res.data["payment_session"]["provider_order_id"]

    # 2. Buyer attempts verification with failed/invalid credentials
    v_res = buyer_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/verify/", {
        "razorpay_order_id": order_id,
        "razorpay_payment_id": f"pay_failed_{uuid.uuid4().hex[:8]}",
        "razorpay_signature": "invalid_declined_signature",
        "amount": "1000.00",
        "currency": "INR",
    }, format="json")

    assert v_res.status_code == status.HTTP_400_BAD_REQUEST
    assert "verification failed" in v_res.data["message"].lower()

    # Authoritative verification
    quote.refresh_from_db()
    assert quote.deposit_status == DepositStatusChoices.FAILED
    assert quote.status == QuotationStatusChoices.ISSUED
    assert quote.deposit_paid_at is None

    in_booking.refresh_from_db()
    assert in_booking.status != BookingStatusChoices.CONFIRMED

    # Ensure no work order created on failure
    assert WorkOrder.objects.filter(booking=in_booking).count() == 0


@pytest.mark.django_db
def test_razorpay_checkout_cancelled_or_dismissed(in_booking, owner_user, buyer_client):
    """
    When a buyer dismisses or cancels the checkout modal without completing payment,
    quotation remains in ISSUED status, deposit is not paid, booking remains unconfirmed,
    and no WorkOrder is generated.
    """
    quote = QuotationService.create_or_revise_quotation(
        booking=in_booking,
        data={
            "requires_deposit": True,
            "deposit_percentage": Decimal("20.00"),
            "line_items": [
                {
                    "item_type": LineItemTypeChoices.LABOUR,
                    "description": "Oil & Filter Service",
                    "quantity": Decimal("1.00"),
                    "unit_price": Decimal("4000.00"),
                }
            ],
        },
        actor=owner_user,
    )
    QuotationService.issue_quotation(quote, actor=owner_user)

    # 1. Create session (modal opened)
    s_res = buyer_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/create/", format="json")
    assert s_res.status_code == status.HTTP_201_CREATED

    quote.refresh_from_db()
    assert quote.deposit_status == DepositStatusChoices.PROCESSING
    assert quote.status == QuotationStatusChoices.ISSUED

    # Buyer dismisses checkout (no verification request submitted)
    # Check that database records remain protected
    in_booking.refresh_from_db()
    assert in_booking.status != BookingStatusChoices.CONFIRMED
    assert WorkOrder.objects.filter(booking=in_booking).count() == 0


@pytest.mark.django_db
def test_invalid_verification_payload_variations(in_booking, owner_user, buyer_client):
    """
    Mismatched amounts, empty payment IDs, or missing signatures are strictly rejected.
    """
    quote = QuotationService.create_or_revise_quotation(
        booking=in_booking,
        data={
            "requires_deposit": True,
            "deposit_percentage": Decimal("20.00"),
            "line_items": [
                {
                    "item_type": LineItemTypeChoices.LABOUR,
                    "description": "Alternator Testing",
                    "quantity": Decimal("1.00"),
                    "unit_price": Decimal("5000.00"),
                }
            ],
        },
        actor=owner_user,
    )
    QuotationService.issue_quotation(quote, actor=owner_user)

    s_res = buyer_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/create/", format="json")
    order_id = s_res.data["payment_session"]["provider_order_id"]

    # 1. Missing razorpay_payment_id
    r1 = buyer_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/verify/", {
        "razorpay_order_id": order_id,
        "razorpay_signature": "some_sig",
    }, format="json")
    assert r1.status_code == status.HTTP_400_BAD_REQUEST

    # 2. Missing razorpay_order_id
    r2 = buyer_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/verify/", {
        "razorpay_payment_id": "pay_test_123",
        "razorpay_signature": "some_sig",
    }, format="json")
    assert r2.status_code == status.HTTP_400_BAD_REQUEST

    # 3. Missing razorpay_signature
    r3 = buyer_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/verify/", {
        "razorpay_order_id": order_id,
        "razorpay_payment_id": "pay_test_123",
    }, format="json")
    assert r3.status_code == status.HTTP_400_BAD_REQUEST

    # 4. Mismatched amount
    provider = RazorpayPaymentProvider()
    valid_sig = build_razorpay_signature(order_id, "pay_test_valid", provider.key_secret)
    r4 = buyer_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/verify/", {
        "razorpay_order_id": order_id,
        "razorpay_payment_id": "pay_test_valid",
        "razorpay_signature": valid_sig,
        "amount": "999.00",  # Deposit is 1000.00
        "currency": "INR",
    }, format="json")
    assert r4.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_stripe_checkout_redirect_and_session_urls(gb_booking, owner_user, buyer_client):
    """
    Passing return_url and cancel_url to deposit session creation includes them in the session payload
    for Stripe Checkout redirection.
    """
    quote = QuotationService.create_or_revise_quotation(
        booking=gb_booking,
        data={
            "requires_deposit": True,
            "deposit_percentage": Decimal("25.00"),
            "line_items": [
                {
                    "item_type": LineItemTypeChoices.LABOUR,
                    "description": "Full Service Inspection",
                    "quantity": Decimal("1.00"),
                    "unit_price": Decimal("200.00"),
                }
            ],
        },
        actor=owner_user,
    )
    QuotationService.issue_quotation(quote, actor=owner_user)

    return_url = f"https://driverxtra.example/platform?tab=workshops&deposit_quote_id={quote.id}"
    cancel_url = "https://driverxtra.example/platform?tab=workshops&deposit_cancelled=true"

    res = buyer_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/create/", {
        "return_url": return_url,
        "cancel_url": cancel_url,
    }, format="json")

    assert res.status_code == status.HTTP_201_CREATED, res.data
    session = res.data["payment_session"]
    assert session["provider"] == "STRIPE"
    assert session["currency"] == "GBP"
    assert session["return_url"] == return_url
    assert session["cancel_url"] == cancel_url
    assert "provider_order_id" in session
    assert "client_secret" in session


@pytest.mark.django_db
def test_stripe_cancellation_and_authoritative_return(gb_booking, owner_user, buyer_client):
    """
    Stripe return flow:
    - Never trust URL parameters alone: forged or missing payment credentials fail verification.
    - Cancellation return leaves quotation in ISSUED status and booking unconfirmed.
    - Genuine authoritative verification confirms booking.
    """
    quote = QuotationService.create_or_revise_quotation(
        booking=gb_booking,
        data={
            "requires_deposit": True,
            "deposit_percentage": Decimal("20.00"),
            "line_items": [
                {
                    "item_type": LineItemTypeChoices.LABOUR,
                    "description": "Wheel Alignment & Balance",
                    "quantity": Decimal("1.00"),
                    "unit_price": Decimal("80.00"),
                }
            ],
        },
        actor=owner_user,
    )
    QuotationService.issue_quotation(quote, actor=owner_user)

    s_res = buyer_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/create/", format="json")
    pi_id = s_res.data["payment_session"]["provider_order_id"]

    # 1. Attempt verification with forged / bogus payment intent ID
    bad_res = buyer_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/verify/", {
        "payment_intent_id": "pi_forged_intent_12345",
        "amount": str(quote.deposit_amount),
        "currency": "GBP",
    }, format="json")
    assert bad_res.status_code == status.HTTP_400_BAD_REQUEST

    quote.refresh_from_db()
    assert quote.deposit_status != DepositStatusChoices.PAID

    # 2. Genuine verification with the real PaymentIntent ID from session
    good_res = buyer_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/verify/", {
        "payment_intent_id": pi_id,
        "amount": str(quote.deposit_amount),
        "currency": "GBP",
    }, format="json")
    assert good_res.status_code == status.HTTP_200_OK, good_res.data

    quote.refresh_from_db()
    assert quote.deposit_status == DepositStatusChoices.PAID
    assert quote.status == QuotationStatusChoices.ACCEPTED

    gb_booking.refresh_from_db()
    assert gb_booking.status == BookingStatusChoices.CONFIRMED


@pytest.mark.django_db
def test_duplicate_payment_initiation_concurrency_and_protection(in_booking, owner_user, buyer_client):
    """
    Initiating deposit sessions multiple times while in progress safely updates/reuses session,
    and once PAID, further initiation is strictly rejected.
    """
    quote = QuotationService.create_or_revise_quotation(
        booking=in_booking,
        data={
            "requires_deposit": True,
            "deposit_percentage": Decimal("20.00"),
            "line_items": [
                {
                    "item_type": LineItemTypeChoices.LABOUR,
                    "description": "Air Conditioning Regas",
                    "quantity": Decimal("1.00"),
                    "unit_price": Decimal("6000.00"),
                }
            ],
        },
        actor=owner_user,
    )
    QuotationService.issue_quotation(quote, actor=owner_user)

    # First session creation
    r1 = buyer_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/create/", format="json")
    assert r1.status_code == status.HTTP_201_CREATED

    # Second session creation (concurrent or retried before payment)
    r2 = buyer_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/create/", format="json")
    assert r2.status_code == status.HTTP_201_CREATED
    active_order_id = r2.data["payment_session"]["provider_order_id"]

    # Now verify and pay deposit
    provider = RazorpayPaymentProvider()
    valid_sig = build_razorpay_signature(active_order_id, "pay_duplicate_test", provider.key_secret)
    v_res = buyer_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/verify/", {
        "razorpay_order_id": active_order_id,
        "razorpay_payment_id": "pay_duplicate_test",
        "razorpay_signature": valid_sig,
        "amount": "1200.00",
        "currency": "INR",
    }, format="json")
    assert v_res.status_code == status.HTTP_200_OK

    quote.refresh_from_db()
    assert quote.deposit_status == DepositStatusChoices.PAID

    # Third session creation: Attempt to initiate payment after already PAID is strictly blocked
    r3 = buyer_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/create/", format="json")
    assert r3.status_code == status.HTTP_400_BAD_REQUEST
    assert "already been paid" in r3.data["message"].lower()


@pytest.mark.django_db
def test_page_refresh_authoritative_state_retrieval(in_booking, owner_user, buyer_client):
    """
    After payment, refreshing the page queries GET /deposit/ and GET /bookings/:
    Confirms authoritative state: deposit_status=PAID, booking=CONFIRMED, quotation=ACCEPTED.
    """
    quote = QuotationService.create_or_revise_quotation(
        booking=in_booking,
        data={
            "requires_deposit": True,
            "deposit_percentage": Decimal("20.00"),
            "line_items": [
                {
                    "item_type": LineItemTypeChoices.LABOUR,
                    "description": "Timing Belt Kit Replacement",
                    "quantity": Decimal("1.00"),
                    "unit_price": Decimal("12000.00"),
                }
            ],
        },
        actor=owner_user,
    )
    QuotationService.issue_quotation(quote, actor=owner_user)

    s_res = buyer_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/create/", format="json")
    order_id = s_res.data["payment_session"]["provider_order_id"]
    pay_id = f"pay_refresh_{uuid.uuid4().hex[:8]}"

    provider = RazorpayPaymentProvider()
    sig = build_razorpay_signature(order_id, pay_id, provider.key_secret)
    buyer_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/verify/", {
        "razorpay_order_id": order_id,
        "razorpay_payment_id": pay_id,
        "razorpay_signature": sig,
        "amount": "2400.00",
        "currency": "INR",
    }, format="json")

    # 1. Simulating page refresh checking GET /deposit/
    d_res = buyer_client.get(f"/api/v1/workshops/quotations/{quote.id}/deposit/")
    assert d_res.status_code == status.HTTP_200_OK
    assert d_res.data["deposit_status"] == DepositStatusChoices.PAID
    assert d_res.data["requires_deposit"] is True
    assert d_res.data["deposit_amount"] == "2400.00"
    assert d_res.data["deposit_transaction_id"] == pay_id
    assert d_res.data["deposit_paid_at"] is not None

    # 2. Simulating page refresh checking GET /bookings/ (buyer's booking list)
    b_res = buyer_client.get("/api/v1/workshops/bookings/")
    assert b_res.status_code == status.HTTP_200_OK
    matching_bk = next((b for b in b_res.data["results"] if b["id"] == str(in_booking.id)), None)
    assert matching_bk is not None
    assert matching_bk["status"] == BookingStatusChoices.CONFIRMED
    assert matching_bk["active_quotation"]["status"] == QuotationStatusChoices.ACCEPTED
    assert matching_bk["active_quotation"]["deposit_status"] == DepositStatusChoices.PAID


@pytest.mark.django_db
def test_webhook_confirmation_arriving_before_frontend_callback(in_booking, owner_user, buyer_client):
    """
    When the payment gateway webhook arrives and processes BEFORE the buyer's frontend callback,
    the frontend verification callback executes idempotently with 200 OK without double-processing.
    """
    quote = QuotationService.create_or_revise_quotation(
        booking=in_booking,
        data={
            "requires_deposit": True,
            "deposit_percentage": Decimal("20.00"),
            "line_items": [
                {
                    "item_type": LineItemTypeChoices.LABOUR,
                    "description": "Suspension Bushing Replacement",
                    "quantity": Decimal("1.00"),
                    "unit_price": Decimal("7500.00"),
                }
            ],
        },
        actor=owner_user,
    )
    QuotationService.issue_quotation(quote, actor=owner_user)

    s_res = buyer_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/create/", format="json")
    order_id = s_res.data["payment_session"]["provider_order_id"]
    payment_id = f"pay_webhook_first_{uuid.uuid4().hex[:8]}"

    # STEP 1: Gateway webhook arrives FIRST
    webhook_client = APIClient()
    provider = RazorpayPaymentProvider()
    webhook_secret = provider.webhook_secret or "mock_webhook_secret_key_12345"

    webhook_payload = {
        "entity": "event",
        "account_id": "acc_test_123",
        "event": "payment.captured",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": order_id,
                    "amount": 150000,
                    "currency": "INR",
                    "status": "captured",
                    "notes": {
                        "quotation_id": str(quote.id),
                    },
                }
            }
        },
        "created_at": 1700000000,
    }
    raw_body = json.dumps(webhook_payload).encode("utf-8")
    webhook_signature = hmac.new(webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    wh_res = webhook_client.post(
        "/api/v1/workshops/deposit/webhook/razorpay/",
        data=raw_body,
        content_type="application/json",
        HTTP_X_RAZORPAY_SIGNATURE=webhook_signature,
    )
    assert wh_res.status_code == status.HTTP_200_OK

    quote.refresh_from_db()
    assert quote.deposit_status == DepositStatusChoices.PAID
    assert quote.status == QuotationStatusChoices.ACCEPTED
    in_booking.refresh_from_db()
    assert in_booking.status == BookingStatusChoices.CONFIRMED

    # STEP 2: Buyer's frontend verification callback arrives SECOND
    valid_sig = build_razorpay_signature(order_id, payment_id, provider.key_secret)
    v_res = buyer_client.post(f"/api/v1/workshops/quotations/{quote.id}/deposit/verify/", {
        "razorpay_order_id": order_id,
        "razorpay_payment_id": payment_id,
        "razorpay_signature": valid_sig,
        "amount": "1500.00",
        "currency": "INR",
    }, format="json")

    # Gracefully idempotent
    assert v_res.status_code == status.HTTP_200_OK, v_res.data
    assert v_res.data["status"] == "success"

    # Exactly ONE work order exists (no duplicates)
    assert WorkOrder.objects.filter(booking=in_booking).count() == 1

