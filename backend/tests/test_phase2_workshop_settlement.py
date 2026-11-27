import hashlib
import hmac
import json
import uuid
from decimal import Decimal
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

import pytest
from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.identity.models import User, RoleChoices
from apps.organisations.models import Organisation, OrganisationRoleChoices, OrganisationTypeChoices
from apps.garage.models import GarageVehicle
from apps.workshops.models import (
    WorkshopProfile,
    WorkshopBooking,
    WorkshopQuotation,
    QuotationLineItem,
    WorkOrder,
    WorkOrderStatusChoices,
    WorkOrderSettlementStatusChoices,
    WorkOrderPayment,
    WorkOrderPaymentStatusChoices,
    WorkOrderPaymentTypeChoices,
    WorkOrderInvoice,
    WorkOrderInvoiceStatusChoices,
    BookingStatusChoices,
    QuotationStatusChoices,
    DepositStatusChoices,
    LineItemTypeChoices,
    ChangeOrder,
    ChangeOrderStatusChoices,
    ChangeOrderLineItem,
    WorkshopSettlementWebhookEvent,
)
from apps.workshops.settlement_service import WorkOrderSettlementService
from platform_core.audit.models import AuditLog
from tests.quotation_states import make_quotation, advance_quotation


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
def gb_vehicle(db, buyer_user):
    return GarageVehicle.objects.create(
        user=buyer_user,
        make="BMW",
        model="330e",
        year=2021,
        registration_plate="GF21 XTR",
    )


@pytest.fixture
def in_work_order(db, in_workshop_profile, buyer_user, in_vehicle):
    booking = WorkshopBooking.objects.create(
        workshop=in_workshop_profile,
        buyer=buyer_user,
        vehicle=in_vehicle,
        preferred_date=date.today() + timedelta(days=3),
        status=BookingStatusChoices.CONFIRMED,
    )
    quote = WorkshopQuotation.objects.create(
        booking=booking,
        status=QuotationStatusChoices.DRAFT,  # line items added below; issued quotations are write-once
        total_amount=Decimal('10000.00'),
        currency='INR',
        requires_deposit=True,
        deposit_percentage=Decimal('20.00'),
        deposit_amount=Decimal('2000.00'),
        deposit_status=DepositStatusChoices.PAID,
        deposit_transaction_id="pay_in_dep_12345",
        deposit_paid_at=timezone.now(),
    )
    QuotationLineItem.objects.create(
        quotation=quote,
        item_type=LineItemTypeChoices.LABOUR,
        description="Full Major Engine Service",
        quantity=Decimal('1.00'),
        unit_price=Decimal('10000.00'),
        line_total=Decimal('10000.00'),
    )
    advance_quotation(quote, QuotationStatusChoices.ACCEPTED)
    wo = WorkOrder.objects.create(
        booking=booking,
        quotation=quote,
        workshop=in_workshop_profile,
        buyer=buyer_user,
        vehicle=in_vehicle,
        status=WorkOrderStatusChoices.QUALITY_CHECK,
    )
    return wo


@pytest.fixture
def gb_work_order(db, gb_workshop_profile, buyer_user, gb_vehicle):
    booking = WorkshopBooking.objects.create(
        workshop=gb_workshop_profile,
        buyer=buyer_user,
        vehicle=gb_vehicle,
        preferred_date=date.today() + timedelta(days=3),
        status=BookingStatusChoices.CONFIRMED,
    )
    quote = WorkshopQuotation.objects.create(
        booking=booking,
        status=QuotationStatusChoices.DRAFT,  # line items added below; issued quotations are write-once
        total_amount=Decimal('500.00'),
        currency='GBP',
        requires_deposit=True,
        deposit_percentage=Decimal('15.00'),
        deposit_amount=Decimal('75.00'),
        deposit_status=DepositStatusChoices.PAID,
        deposit_transaction_id="pi_gb_dep_12345",
        deposit_paid_at=timezone.now(),
        tax_amount=Decimal('83.33'),
        tax_rate_percent=Decimal('20.00'),
    )
    QuotationLineItem.objects.create(
        quotation=quote,
        item_type=LineItemTypeChoices.LABOUR,
        description="Front Brake Disc & Pad Replacement",
        quantity=Decimal('1.00'),
        unit_price=Decimal('500.00'),
        line_total=Decimal('500.00'),
    )
    advance_quotation(quote, QuotationStatusChoices.ACCEPTED)
    wo = WorkOrder.objects.create(
        booking=booking,
        quotation=quote,
        workshop=gb_workshop_profile,
        buyer=buyer_user,
        vehicle=gb_vehicle,
        status=WorkOrderStatusChoices.QUALITY_CHECK,
    )
    return wo


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
# 15 REQUIRED TEST SCENARIOS FOR WORKSHOP SETTLEMENT & ONLINE PAYMENT
# =============================================================================

@pytest.mark.django_db
def test_1_successful_inr_balance_payment_through_razorpay(in_work_order, buyer_client):
    """1. Successful INR balance payment through Razorpay."""
    calc = WorkOrderSettlementService.calculate_outstanding_balance(in_work_order)
    assert calc["authorized_total_amount"] == "10000.00"
    assert calc["deposit_paid_amount"] == "2000.00"
    assert calc["outstanding_balance"] == "8000.00"
    assert calc["currency"] == "INR"

    # Step A: Initiate settlement session
    res_session = buyer_client.post(
        f"/api/v1/workshops/work-orders/{in_work_order.id}/settle/session/",
        {"preferred_provider": "RAZORPAY"},
        format="json",
    )
    assert res_session.status_code == status.HTTP_201_CREATED
    data = res_session.data
    assert data["status"] == "success"
    assert data["amount"] == "8000.00"
    provider_order_id = data["payment_session"]["provider_order_id"]

    # Step B: Verify gateway payment
    secret = getattr(settings, 'RAZORPAY_KEY_SECRET', 'test_razorpay_secret')
    test_pid = f"pay_test_{uuid.uuid4().hex[:8]}"
    sig = build_razorpay_signature(provider_order_id, test_pid, secret)

    res_verify = buyer_client.post(
        f"/api/v1/workshops/work-orders/{in_work_order.id}/settle/verify/",
        {
            "razorpay_order_id": provider_order_id,
            "razorpay_payment_id": test_pid,
            "razorpay_signature": sig,
            "preferred_provider": "RAZORPAY",
        },
        format="json",
    )
    assert res_verify.status_code == status.HTTP_200_OK
    verify_data = res_verify.data
    assert verify_data["payment_status"] == WorkOrderPaymentStatusChoices.SUCCESS
    assert verify_data["settlement_status"] == WorkOrderSettlementStatusChoices.FULLY_PAID
    assert verify_data["is_fully_settled"] is True
    assert verify_data["outstanding_balance"] == "0.00"

    in_work_order.refresh_from_db()
    assert in_work_order.settlement_status == WorkOrderSettlementStatusChoices.FULLY_PAID
    assert in_work_order.outstanding_balance == Decimal('0.00')


@pytest.mark.django_db
def test_2_successful_gbp_balance_payment_through_stripe(gb_work_order, buyer_client):
    """2. Successful GBP balance payment through Stripe."""
    calc = WorkOrderSettlementService.calculate_outstanding_balance(gb_work_order)
    assert calc["authorized_total_amount"] == "500.00"
    assert calc["deposit_paid_amount"] == "75.00"
    assert calc["outstanding_balance"] == "425.00"
    assert calc["currency"] == "GBP"

    # Step A: Initiate settlement session
    res_session = buyer_client.post(
        f"/api/v1/workshops/work-orders/{gb_work_order.id}/settle/session/",
        {"preferred_provider": "STRIPE"},
        format="json",
    )
    assert res_session.status_code == status.HTTP_201_CREATED
    data = res_session.data
    provider_order_id = data["payment_session"]["provider_order_id"]

    # Step B: Verify Stripe payment
    res_verify = buyer_client.post(
        f"/api/v1/workshops/work-orders/{gb_work_order.id}/settle/verify/",
        {
            "payment_intent_id": provider_order_id,
            "provider_order_id": provider_order_id,
            "preferred_provider": "STRIPE",
        },
        format="json",
    )
    assert res_verify.status_code == status.HTTP_200_OK
    gb_work_order.refresh_from_db()
    assert gb_work_order.settlement_status == WorkOrderSettlementStatusChoices.FULLY_PAID
    assert gb_work_order.outstanding_balance == Decimal('0.00')
    assert gb_work_order.is_fully_settled is True


@pytest.mark.django_db
def test_3_partial_balance_payment(gb_work_order, buyer_client):
    """3. Partial balance payment."""
    # Outstanding is 425.00 GBP. Buyer pays partial 150.00 GBP.
    res_session = buyer_client.post(
        f"/api/v1/workshops/work-orders/{gb_work_order.id}/settle/session/",
        {
            "partial_amount": "150.00",
            "preferred_provider": "STRIPE",
        },
        format="json",
    )
    assert res_session.status_code == status.HTTP_201_CREATED
    assert res_session.data["amount"] == "150.00"
    provider_order_id = res_session.data["payment_session"]["provider_order_id"]

    res_verify = buyer_client.post(
        f"/api/v1/workshops/work-orders/{gb_work_order.id}/settle/verify/",
        {
            "payment_intent_id": provider_order_id,
            "provider_order_id": provider_order_id,
            "preferred_provider": "STRIPE",
        },
        format="json",
    )
    assert res_verify.status_code == status.HTTP_200_OK
    assert res_verify.data["settlement_status"] == WorkOrderSettlementStatusChoices.PARTIALLY_PAID
    assert res_verify.data["is_fully_settled"] is False
    assert res_verify.data["outstanding_balance"] == "275.00"  # 425.00 - 150.00 = 275.00

    gb_work_order.refresh_from_db()
    assert gb_work_order.settlement_status == WorkOrderSettlementStatusChoices.PARTIALLY_PAID
    assert gb_work_order.outstanding_balance == Decimal('275.00')


@pytest.mark.django_db
def test_4_multiple_approved_change_orders(gb_work_order, owner_user, buyer_user):
    """4. Multiple approved change orders increase authorized total and balance."""
    # Base quotation: 500, Deposit: 75 -> Base balance: 425
    co1 = ChangeOrder.objects.create(
        work_order=gb_work_order,
        version=1,
        status=ChangeOrderStatusChoices.APPROVED,
        reason="Brake fluid flush",
        additional_amount=Decimal('100.00'),
        currency='GBP',
        created_by=owner_user,
        reviewed_by=buyer_user,
    )
    co2 = ChangeOrder.objects.create(
        work_order=gb_work_order,
        version=2,
        status=ChangeOrderStatusChoices.APPROVED,
        reason="Front tyre replacement",
        additional_amount=Decimal('250.00'),
        currency='GBP',
        created_by=owner_user,
        reviewed_by=buyer_user,
    )

    calc = WorkOrderSettlementService.calculate_outstanding_balance(gb_work_order)
    # Authorized total: 500 + 100 + 250 = 850.00
    assert calc["authorized_total_amount"] == "850.00"
    assert calc["approved_change_orders_amount"] == "350.00"
    assert calc["deposit_paid_amount"] == "75.00"
    # Outstanding balance: 850 - 75 = 775.00
    assert calc["outstanding_balance"] == "775.00"


@pytest.mark.django_db
def test_5_rejected_and_pending_change_orders_excluded_from_calculation(gb_work_order, owner_user, buyer_user):
    """5. Rejected and pending change orders excluded from calculation."""
    # Approved CO
    ChangeOrder.objects.create(
        work_order=gb_work_order,
        version=1,
        status=ChangeOrderStatusChoices.APPROVED,
        reason="Wiper blades",
        additional_amount=Decimal('40.00'),
        currency='GBP',
        created_by=owner_user,
        reviewed_by=buyer_user,
    )
    # Pending CO (submitted)
    ChangeOrder.objects.create(
        work_order=gb_work_order,
        version=2,
        status=ChangeOrderStatusChoices.SUBMITTED,
        reason="Suspension arm",
        additional_amount=Decimal('200.00'),
        currency='GBP',
        created_by=owner_user,
    )
    # Rejected CO
    ChangeOrder.objects.create(
        work_order=gb_work_order,
        version=3,
        status=ChangeOrderStatusChoices.REJECTED,
        reason="Premium battery upgrade",
        additional_amount=Decimal('300.00'),
        currency='GBP',
        created_by=owner_user,
        reviewed_by=buyer_user,
    )
    # Cancelled CO
    ChangeOrder.objects.create(
        work_order=gb_work_order,
        version=4,
        status=ChangeOrderStatusChoices.CANCELLED,
        reason="Alloy refurbishment",
        additional_amount=Decimal('150.00'),
        currency='GBP',
        created_by=owner_user,
    )

    calc = WorkOrderSettlementService.calculate_outstanding_balance(gb_work_order)
    # Only approved CO (40.00) is included: 500 + 40 = 540.00
    assert calc["authorized_total_amount"] == "540.00"
    assert calc["approved_change_orders_amount"] == "40.00"
    # Outstanding balance: 540 - 75 = 465.00
    assert calc["outstanding_balance"] == "465.00"


@pytest.mark.django_db
def test_6_failed_deposit_excluded_from_paid_total(gb_work_order):
    """6. Failed deposit excluded from paid total."""
    quote = gb_work_order.quotation
    quote.deposit_status = DepositStatusChoices.FAILED
    quote.save(update_fields=['deposit_status'])

    calc = WorkOrderSettlementService.calculate_outstanding_balance(gb_work_order)
    assert calc["deposit_paid_amount"] == "0.00"
    # Full authorized total is due because deposit failed
    assert calc["outstanding_balance"] == "500.00"


@pytest.mark.django_db
def test_7_duplicate_payment_prevention(in_work_order, buyer_client):
    """7. Duplicate payment prevention: verifying same payment ID twice returns idempotent state."""
    res_session = buyer_client.post(
        f"/api/v1/workshops/work-orders/{in_work_order.id}/settle/session/",
        {"preferred_provider": "RAZORPAY"},
        format="json",
    )
    provider_order_id = res_session.data["payment_session"]["provider_order_id"]
    secret = getattr(settings, 'RAZORPAY_KEY_SECRET', 'test_razorpay_secret')
    test_pid = f"pay_dup_{uuid.uuid4().hex[:8]}"
    sig = build_razorpay_signature(provider_order_id, test_pid, secret)

    payload = {
        "razorpay_order_id": provider_order_id,
        "razorpay_payment_id": test_pid,
        "razorpay_signature": sig,
        "preferred_provider": "RAZORPAY",
    }

    # Attempt 1
    res1 = buyer_client.post(f"/api/v1/workshops/work-orders/{in_work_order.id}/settle/verify/", payload, format="json")
    assert res1.status_code == status.HTTP_200_OK

    # Attempt 2 (Identical payload)
    res2 = buyer_client.post(f"/api/v1/workshops/work-orders/{in_work_order.id}/settle/verify/", payload, format="json")
    assert res2.status_code == status.HTTP_200_OK
    assert in_work_order.payments.filter(provider_payment_id=test_pid).count() == 1


@pytest.mark.django_db
def test_8_concurrent_payment_attempts_auto_refunds_excess(in_work_order, buyer_user):
    """8. Concurrent payment attempts: second payment after full settlement is safely auto-refunded."""
    secret = getattr(settings, 'RAZORPAY_KEY_SECRET', 'test_razorpay_secret')
    sig1 = build_razorpay_signature("order_first_123", "pay_first_123", secret)
    # First payment settles work order
    WorkOrderSettlementService.verify_settlement_payment(
        work_order_id=in_work_order.id,
        payload={"razorpay_payment_id": "pay_first_123", "razorpay_order_id": "order_first_123", "razorpay_signature": sig1, "amount": "8000.00"},
        actor=buyer_user,
        preferred_provider="RAZORPAY",
    )
    in_work_order.refresh_from_db()
    assert in_work_order.settlement_status == WorkOrderSettlementStatusChoices.FULLY_PAID

    # Second concurrent payment arrives for already settled work order
    sig2 = build_razorpay_signature("order_second_456", "pay_second_456", secret)
    wo, late_payment = WorkOrderSettlementService.verify_settlement_payment(
        work_order_id=in_work_order.id,
        payload={"razorpay_payment_id": "pay_second_456", "razorpay_order_id": "order_second_456", "razorpay_signature": sig2, "amount": "8000.00"},
        actor=buyer_user,
        preferred_provider="RAZORPAY",
    )
    assert late_payment.status == WorkOrderPaymentStatusChoices.REFUNDED
    assert late_payment.is_late_payment is True


@pytest.mark.django_db
def test_9_invalid_gateway_signature(in_work_order, buyer_client):
    """9. Invalid gateway signature rejected with HTTP 400 and recorded as FAILED."""
    res_session = buyer_client.post(
        f"/api/v1/workshops/work-orders/{in_work_order.id}/settle/session/",
        {"preferred_provider": "RAZORPAY"},
        format="json",
    )
    provider_order_id = res_session.data["payment_session"]["provider_order_id"]

    res_verify = buyer_client.post(
        f"/api/v1/workshops/work-orders/{in_work_order.id}/settle/verify/",
        {
            "razorpay_order_id": provider_order_id,
            "razorpay_payment_id": "pay_tampered_123",
            "razorpay_signature": "invalid_tampered_signature_hex",
            "preferred_provider": "RAZORPAY",
        },
        format="json",
    )
    assert res_verify.status_code == status.HTTP_400_BAD_REQUEST
    assert "verification failed" in res_verify.data["message"].lower()

    failed_payment = in_work_order.payments.filter(status=WorkOrderPaymentStatusChoices.FAILED).first()
    assert failed_payment is not None
    assert failed_payment.status == WorkOrderPaymentStatusChoices.FAILED


@pytest.mark.django_db
def test_10_webhook_confirmation(in_work_order, buyer_user):
    """10. Webhook confirmation updates settlement and protects against replays."""
    # Create pending payment session
    session_data = WorkOrderSettlementService.create_settlement_session(
        work_order=in_work_order,
        buyer=buyer_user,
        preferred_provider="RAZORPAY",
    )
    provider_order_id = session_data["payment_session"]["provider_order_id"]
    test_payment_id = f"pay_wb_{uuid.uuid4().hex[:8]}"

    webhook_payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": test_payment_id,
                    "order_id": provider_order_id,
                    "amount": 800000,
                    "currency": "INR",
                    "status": "captured",
                }
            }
        }
    }
    raw_body = json.dumps(webhook_payload).encode('utf-8')
    secret = getattr(settings, 'RAZORPAY_WEBHOOK_SECRET', 'test_razorpay_webhook_secret')
    sig = build_razorpay_webhook_signature(raw_body, secret)

    headers = {
        'HTTP_X_RAZORPAY_SIGNATURE': sig,
        'X-Razorpay-Signature': sig,
        'x-razorpay-signature': sig,
    }

    # Delivery 1
    success, msg = WorkOrderSettlementService.process_settlement_webhook(
        provider_name="RAZORPAY",
        request_body=raw_body,
        headers=headers,
    )
    assert success is True, f"process_settlement_webhook failed with: {msg}"
    in_work_order.refresh_from_db()
    assert in_work_order.settlement_status == WorkOrderSettlementStatusChoices.FULLY_PAID

    # Delivery 2 (Replay)
    success2, msg2 = WorkOrderSettlementService.process_settlement_webhook(
        provider_name="RAZORPAY",
        request_body=raw_body,
        headers=headers,
    )
    assert success2 is True
    assert "already processed" in msg2


@pytest.mark.django_db
def test_11_gateway_timeout_and_retry(in_work_order, buyer_user):
    """11. Gateway timeout and retry succeeds idempotently without duplicate debit."""
    p_num = "WP-RETRY-001"
    session_data = WorkOrderSettlementService.create_settlement_session(
        work_order=in_work_order,
        buyer=buyer_user,
        preferred_provider="RAZORPAY",
    )
    order_id = session_data["payment_session"]["provider_order_id"]

    secret = getattr(settings, 'RAZORPAY_KEY_SECRET', 'test_razorpay_secret')
    sig = build_razorpay_signature(order_id, "pay_retry_123", secret)

    # Retry with valid credentials
    wo, payment = WorkOrderSettlementService.verify_settlement_payment(
        work_order_id=in_work_order.id,
        payload={"razorpay_payment_id": "pay_retry_123", "razorpay_order_id": order_id, "razorpay_signature": sig, "amount": "8000.00"},
        actor=buyer_user,
        preferred_provider="RAZORPAY",
    )
    assert payment.status == WorkOrderPaymentStatusChoices.SUCCESS
    assert wo.settlement_status == WorkOrderSettlementStatusChoices.FULLY_PAID


@pytest.mark.django_db
def test_12_late_payment_after_work_order_cancellation(in_work_order, buyer_user):
    """12. Late payment after work order cancellation initiates auto-refund."""
    in_work_order.status = WorkOrderStatusChoices.CANCELLED
    in_work_order.save(update_fields=['status'])

    secret = getattr(settings, 'RAZORPAY_KEY_SECRET', 'test_razorpay_secret')
    sig = build_razorpay_signature("order_late_123", "pay_late_cancelled_123", secret)
    wo, late_payment = WorkOrderSettlementService.verify_settlement_payment(
        work_order_id=in_work_order.id,
        payload={"razorpay_payment_id": "pay_late_cancelled_123", "razorpay_order_id": "order_late_123", "razorpay_signature": sig, "amount": "8000.00"},
        actor=buyer_user,
        preferred_provider="RAZORPAY",
    )
    assert late_payment.status == WorkOrderPaymentStatusChoices.REFUNDED
    assert late_payment.is_late_payment is True
    assert "auto-refunded" in late_payment.error_message.lower()


@pytest.mark.django_db
def test_13_unauthorized_buyer_access(in_work_order, other_client):
    """13. Unauthorized buyer access returns HTTP 403 PermissionDenied."""
    # Attempt to create settlement session for another customer's work order
    res_session = other_client.post(
        f"/api/v1/workshops/work-orders/{in_work_order.id}/settle/session/",
        {"preferred_provider": "RAZORPAY"},
        format="json",
    )
    assert res_session.status_code == status.HTTP_403_FORBIDDEN

    # Attempt to verify settlement for another customer's work order
    res_verify = other_client.post(
        f"/api/v1/workshops/work-orders/{in_work_order.id}/settle/verify/",
        {"razorpay_order_id": "order_fake", "razorpay_payment_id": "pay_fake"},
        format="json",
    )
    assert res_verify.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_14_final_invoice_generation(gb_work_order, buyer_user, buyer_client):
    """14. Final invoice generation accurately reflects all figures and line items."""
    # Settle the balance
    session_data = WorkOrderSettlementService.create_settlement_session(
        work_order=gb_work_order,
        buyer=buyer_user,
        preferred_provider="STRIPE",
    )
    pi_id = session_data["payment_session"]["provider_order_id"]
    WorkOrderSettlementService.verify_settlement_payment(
        work_order_id=gb_work_order.id,
        payload={"payment_intent_id": pi_id, "amount": "425.00"},
        actor=buyer_user,
        preferred_provider="STRIPE",
    )
    gb_work_order.refresh_from_db()

    # Query invoice endpoint
    res_inv = buyer_client.get(f"/api/v1/workshops/work-orders/{gb_work_order.id}/invoice/")
    assert res_inv.status_code == status.HTTP_200_OK
    inv = res_inv.data

    assert inv["total_authorized_amount"] == "500.00"
    assert inv["deposit_paid_amount"] == "75.00"
    assert inv["balance_paid_amount"] == "425.00"
    assert inv["total_paid_amount"] == "500.00"
    assert inv["outstanding_balance"] == "0.00"
    assert inv["is_fully_settled"] is True
    assert inv["currency"] == "GBP"
    assert inv["document_type"] == "TAX_INVOICE"
    assert "invoice_data" in inv
    assert inv["invoice_data"]["workshop"]["name"] == gb_work_order.workshop.display_name


@pytest.mark.django_db
def test_15_fully_settled_work_order_cannot_be_charged_again(gb_work_order, buyer_client, buyer_user):
    """15. Fully settled work order cannot be charged again."""
    # Pay full balance
    session_data = WorkOrderSettlementService.create_settlement_session(
        work_order=gb_work_order,
        buyer=buyer_user,
        preferred_provider="STRIPE",
    )
    pi_id = session_data["payment_session"]["provider_order_id"]
    WorkOrderSettlementService.verify_settlement_payment(
        work_order_id=gb_work_order.id,
        payload={"payment_intent_id": pi_id, "amount": "425.00"},
        actor=buyer_user,
        preferred_provider="STRIPE",
    )
    gb_work_order.refresh_from_db()
    assert gb_work_order.is_fully_settled is True

    # Attempt to create another payment session
    res_session = buyer_client.post(
        f"/api/v1/workshops/work-orders/{gb_work_order.id}/settle/session/",
        {"preferred_provider": "STRIPE"},
        format="json",
    )
    assert res_session.status_code == status.HTTP_400_BAD_REQUEST
    assert "already been fully settled" in res_session.data["message"].lower()


@pytest.mark.django_db
def test_16_change_order_with_tax_and_multiple_approved_changes_no_double_tax(gb_work_order):
    """16. Verify change orders with statutory tax and multiple revisions do not double-count tax."""
    co1 = ChangeOrder.objects.create(
        work_order=gb_work_order,
        status=ChangeOrderStatusChoices.DRAFT,
        reason="Additional front suspension arm replacement required",
        subtotal_parts=Decimal('100.00'),
        tax_amount=Decimal('20.00'),
        tax_rate_percent=Decimal('20.00'),
        additional_amount=Decimal('120.00'),
        revised_authorized_total=Decimal('620.00'),
    )
    ChangeOrderLineItem.objects.create(
        change_order=co1,
        item_type=LineItemTypeChoices.PART,
        description="Front suspension arm",
        quantity=Decimal('1.00'),
        unit_price=Decimal('100.00'),
        line_total=Decimal('100.00'),
    )
    co1.status = ChangeOrderStatusChoices.APPROVED
    co1.save(update_fields=['status'])

    co2 = ChangeOrder.objects.create(
        work_order=gb_work_order,
        status=ChangeOrderStatusChoices.DRAFT,
        reason="Wheel realignment labour",
        subtotal_labour=Decimal('50.00'),
        tax_amount=Decimal('10.00'),
        tax_rate_percent=Decimal('20.00'),
        additional_amount=Decimal('60.00'),
        revised_authorized_total=Decimal('680.00'),
    )
    ChangeOrderLineItem.objects.create(
        change_order=co2,
        item_type=LineItemTypeChoices.LABOUR,
        description="Wheel realignment labour",
        quantity=Decimal('1.00'),
        unit_price=Decimal('50.00'),
        line_total=Decimal('50.00'),
    )
    co2.status = ChangeOrderStatusChoices.APPROVED
    co2.save(update_fields=['status'])

    co3 = ChangeOrder.objects.create(
        work_order=gb_work_order,
        status=ChangeOrderStatusChoices.REJECTED,
        reason="Windshield repair declined by customer",
        additional_amount=Decimal('200.00'),
    )

    balance_info = WorkOrderSettlementService.calculate_outstanding_balance(gb_work_order)
    assert Decimal(balance_info["original_quotation_amount"]) == Decimal('500.00')
    assert Decimal(balance_info["approved_change_orders_amount"]) == Decimal('180.00')
    assert Decimal(balance_info["authorized_total_amount"]) == Decimal('680.00')
    assert Decimal(balance_info["deposit_paid_amount"]) == Decimal('75.00')
    assert Decimal(balance_info["balance_paid_amount"]) == Decimal('0.00')
    assert Decimal(balance_info["outstanding_balance"]) == Decimal('605.00')
    assert balance_info["is_fully_settled"] is False

    invoice = WorkOrderSettlementService.generate_or_update_invoice(gb_work_order)
    assert invoice.total_authorized_amount == Decimal('680.00')
    assert invoice.tax_amount == Decimal('113.33')
    assert invoice.subtotal_amount == Decimal('566.67')
    assert invoice.total_amount == Decimal('680.00')
    assert invoice.amount_due == Decimal('605.00')
    assert invoice.outstanding_balance == Decimal('605.00')
    assert invoice.status == WorkOrderInvoiceStatusChoices.ISSUED


@pytest.mark.django_db
def test_17_deposit_in_work_order_payment_not_double_counted_with_quotation_fallback(gb_work_order):
    """17. A deposit recorded in WorkOrderPayment is never double-deducted alongside quotation fallback."""
    WorkOrderPayment.objects.create(
        work_order=gb_work_order,
        payment_number="WOP-DEP-001",
        payment_type=WorkOrderPaymentTypeChoices.DEPOSIT,
        amount=Decimal('75.00'),
        currency='GBP',
        provider='STRIPE',
        provider_payment_id='pi_gb_dep_12345',
        status=WorkOrderPaymentStatusChoices.SUCCESS,
        paid_at=timezone.now(),
        created_by=gb_work_order.buyer,
    )

    balance_info = WorkOrderSettlementService.calculate_outstanding_balance(gb_work_order)
    assert Decimal(balance_info["deposit_paid_amount"]) == Decimal('75.00')
    assert Decimal(balance_info["balance_paid_amount"]) == Decimal('0.00')
    assert Decimal(balance_info["total_paid_amount"]) == Decimal('75.00')
    assert Decimal(balance_info["outstanding_balance"]) == Decimal('425.00')

    invoice = WorkOrderSettlementService.generate_or_update_invoice(gb_work_order)
    dep_entries = [p for p in invoice.invoice_data["payment_history"] if p.get("type") == "DEPOSIT"]
    assert len(dep_entries) == 1
    assert dep_entries[0]["amount"] == "75.00"


@pytest.mark.django_db
def test_18_failed_or_pending_or_refunded_deposits_excluded(in_work_order):
    """18. Failed, pending, and refunded deposits are excluded from balance reductions."""
    quote = in_work_order.quotation
    quote.deposit_status = DepositStatusChoices.FAILED
    quote.save(update_fields=['deposit_status'])

    WorkOrderPayment.objects.create(
        work_order=in_work_order,
        payment_number="WOP-DEP-FAIL",
        payment_type=WorkOrderPaymentTypeChoices.DEPOSIT,
        amount=Decimal('2000.00'),
        currency='INR',
        provider='RAZORPAY',
        status=WorkOrderPaymentStatusChoices.FAILED,
        created_by=in_work_order.buyer,
    )
    WorkOrderPayment.objects.create(
        work_order=in_work_order,
        payment_number="WOP-DEP-PEND",
        payment_type=WorkOrderPaymentTypeChoices.DEPOSIT,
        amount=Decimal('2000.00'),
        currency='INR',
        provider='RAZORPAY',
        status=WorkOrderPaymentStatusChoices.PENDING,
        created_by=in_work_order.buyer,
    )
    WorkOrderPayment.objects.create(
        work_order=in_work_order,
        payment_number="WOP-DEP-REF",
        payment_type=WorkOrderPaymentTypeChoices.DEPOSIT,
        amount=Decimal('2000.00'),
        currency='INR',
        provider='RAZORPAY',
        status=WorkOrderPaymentStatusChoices.REFUNDED,
        created_by=in_work_order.buyer,
    )

    balance_info = WorkOrderSettlementService.calculate_outstanding_balance(in_work_order)
    assert Decimal(balance_info["deposit_paid_amount"]) == Decimal('0.00')
    assert Decimal(balance_info["balance_paid_amount"]) == Decimal('0.00')
    assert Decimal(balance_info["total_paid_amount"]) == Decimal('0.00')
    assert Decimal(balance_info["outstanding_balance"]) == Decimal('10000.00')


@pytest.mark.django_db
def test_19_partially_settled_work_order_invoice_is_issued_not_paid(in_work_order, buyer_user):
    """19. Partially settled work order invoice displays status ISSUED, never PAID, and transitions properly."""
    secret = getattr(settings, 'RAZORPAY_KEY_SECRET', 'test_razorpay_secret')
    test_pid = f"pay_partial_{uuid.uuid4().hex[:8]}"
    sig = build_razorpay_signature("order_partial_test", test_pid, secret)

    with patch('apps.marketplace.payments.razorpay_provider.RazorpayPaymentProvider.verify_payment', return_value=(True, test_pid, {})):
        locked_wo, p = WorkOrderSettlementService.verify_settlement_payment(
            work_order_id=in_work_order.id,
            payload={
                "razorpay_order_id": "order_partial_test",
                "razorpay_payment_id": test_pid,
                "razorpay_signature": sig,
                "amount": "3000.00",
            },
            actor=buyer_user,
            preferred_provider="RAZORPAY",
        )

    in_work_order.refresh_from_db()
    assert in_work_order.settlement_status == WorkOrderSettlementStatusChoices.PARTIALLY_PAID
    assert in_work_order.outstanding_balance == Decimal('5000.00')

    inv = in_work_order.invoice
    assert inv.status == WorkOrderInvoiceStatusChoices.ISSUED
    assert inv.is_fully_settled is False
    assert inv.outstanding_balance == Decimal('5000.00')
    assert inv.total_paid_amount == Decimal('5000.00')

    test_pid_2 = f"pay_final_{uuid.uuid4().hex[:8]}"
    with patch('apps.marketplace.payments.razorpay_provider.RazorpayPaymentProvider.verify_payment', return_value=(True, test_pid_2, {})):
        locked_wo, p2 = WorkOrderSettlementService.verify_settlement_payment(
            work_order_id=in_work_order.id,
            payload={
                "razorpay_order_id": "order_final_test",
                "razorpay_payment_id": test_pid_2,
                "razorpay_signature": sig,
                "amount": "5000.00",
            },
            actor=buyer_user,
            preferred_provider="RAZORPAY",
        )

    in_work_order.refresh_from_db()
    assert in_work_order.settlement_status == WorkOrderSettlementStatusChoices.FULLY_PAID
    inv.refresh_from_db()
    assert inv.status == WorkOrderInvoiceStatusChoices.PAID
    assert inv.is_fully_settled is True
    assert inv.outstanding_balance == Decimal('0.00')

    in_work_order.status = WorkOrderStatusChoices.CANCELLED
    in_work_order.save(update_fields=['status'])
    WorkOrderSettlementService.generate_or_update_invoice(in_work_order)
    inv.refresh_from_db()
    assert inv.status == WorkOrderInvoiceStatusChoices.VOID


@pytest.mark.django_db
def test_20_concurrent_excess_payment_auto_refunded(gb_work_order, buyer_user):
    """20. Excessive balance payment is detected, safely rejected from ledger, and auto-refunded."""
    calc = WorkOrderSettlementService.calculate_outstanding_balance(gb_work_order)
    assert calc["outstanding_balance"] == "425.00"

    pi_id = f"pi_excess_{uuid.uuid4().hex[:8]}"
    with patch('apps.marketplace.payments.stripe_provider.StripePaymentProvider.verify_payment', return_value=(True, pi_id, {})):
        with patch('apps.marketplace.payments.stripe_provider.StripePaymentProvider.issue_refund', return_value=(True, "re_excess_12345", {})) as mock_refund:
            locked_wo, p = WorkOrderSettlementService.verify_settlement_payment(
                work_order_id=gb_work_order.id,
                payload={"payment_intent_id": pi_id, "amount": "500.00"},
                actor=buyer_user,
                preferred_provider="STRIPE",
            )
            assert mock_refund.called
            assert p.status == WorkOrderPaymentStatusChoices.REFUNDED
            assert p.is_late_payment is True
            assert "Late payment auto-refunded" in p.error_message
            assert "exceeds outstanding balance" in mock_refund.call_args.kwargs["reason"]

    gb_work_order.refresh_from_db()
    assert gb_work_order.settlement_status != WorkOrderSettlementStatusChoices.FULLY_PAID
    assert gb_work_order.outstanding_balance == Decimal('425.00')


@pytest.mark.django_db
def test_21_gateway_refund_succeeds_db_fails_retry_does_not_duplicate_refund(gb_work_order, buyer_user):
    """21. Gateway refund succeeds but database save fails; retry reuses identical idempotency key and recovers."""
    gb_work_order.status = WorkOrderStatusChoices.CANCELLED
    gb_work_order.save(update_fields=['status'])

    pi_id = f"pi_late_{uuid.uuid4().hex[:8]}"
    refund_calls = []

    def mock_issue_refund(**kwargs):
        refund_calls.append(kwargs)
        return True, "re_stripe_idemp_12345", {"id": "re_stripe_idemp_12345"}

    original_save = WorkOrderPayment.save
    first_attempt = True

    def fail_first_save(self, *args, **kwargs):
        nonlocal first_attempt
        if first_attempt and self.status == WorkOrderPaymentStatusChoices.REFUNDED:
            first_attempt = False
            raise IntegrityError("Simulated database constraint failure during refund record persist")
        return original_save(self, *args, **kwargs)

    with patch('apps.marketplace.payments.stripe_provider.StripePaymentProvider.verify_payment', return_value=(True, pi_id, {})):
        with patch('apps.marketplace.payments.stripe_provider.StripePaymentProvider.issue_refund', side_effect=mock_issue_refund):
            with patch.object(WorkOrderPayment, 'save', fail_first_save):
                with pytest.raises(IntegrityError):
                    WorkOrderSettlementService.verify_settlement_payment(
                        work_order_id=gb_work_order.id,
                        payload={"payment_intent_id": pi_id, "amount": "425.00"},
                        actor=buyer_user,
                        preferred_provider="STRIPE",
                    )

    assert len(refund_calls) == 1
    first_idemp_key = refund_calls[0].get("refund_number")
    assert first_idemp_key is not None
    assert "REF-LATE-" in first_idemp_key
    assert not gb_work_order.payments.filter(provider_payment_id=pi_id).exists()

    with patch('apps.marketplace.payments.stripe_provider.StripePaymentProvider.verify_payment', return_value=(True, pi_id, {})):
        with patch('apps.marketplace.payments.stripe_provider.StripePaymentProvider.issue_refund', side_effect=mock_issue_refund):
            locked_wo, p = WorkOrderSettlementService.verify_settlement_payment(
                work_order_id=gb_work_order.id,
                payload={"payment_intent_id": pi_id, "amount": "425.00"},
                actor=buyer_user,
                preferred_provider="STRIPE",
            )

    assert len(refund_calls) == 2
    assert refund_calls[1].get("refund_number") == first_idemp_key
    assert p.status == WorkOrderPaymentStatusChoices.REFUNDED
    assert p.is_late_payment is True
    assert gb_work_order.payments.filter(provider_payment_id=pi_id).count() == 1

    with patch('apps.marketplace.payments.stripe_provider.StripePaymentProvider.verify_payment', return_value=(True, pi_id, {})):
        with patch('apps.marketplace.payments.stripe_provider.StripePaymentProvider.issue_refund', side_effect=mock_issue_refund):
            locked_wo_3, p_3 = WorkOrderSettlementService.verify_settlement_payment(
                work_order_id=gb_work_order.id,
                payload={"payment_intent_id": pi_id, "amount": "425.00"},
                actor=buyer_user,
                preferred_provider="STRIPE",
            )

    assert len(refund_calls) == 2
    assert p_3.id == p.id
    assert gb_work_order.payments.filter(provider_payment_id=pi_id).count() == 1


@pytest.mark.django_db
def test_22_duplicate_webhook_delivery_does_not_duplicate_ledger_or_refund(in_work_order, buyer_user):
    """22. Repeated webhook deliveries for the same event do not create duplicate ledger entries."""
    session_data = WorkOrderSettlementService.create_settlement_session(
        work_order=in_work_order,
        buyer=buyer_user,
        preferred_provider="RAZORPAY",
    )
    provider_order_id = session_data["payment_session"]["provider_order_id"]
    test_payment_id = f"pay_wb_dup_{uuid.uuid4().hex[:8]}"

    webhook_payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": test_payment_id,
                    "order_id": provider_order_id,
                    "amount": 800000,
                    "currency": "INR",
                    "status": "captured",
                }
            }
        }
    }
    raw_body = json.dumps(webhook_payload).encode('utf-8')
    secret = getattr(settings, 'RAZORPAY_WEBHOOK_SECRET', 'test_razorpay_webhook_secret')
    sig = build_razorpay_webhook_signature(raw_body, secret)
    headers = {
        'X-Razorpay-Signature': sig,
        'HTTP_X_RAZORPAY_SIGNATURE': sig,
    }

    success1, msg1 = WorkOrderSettlementService.process_settlement_webhook(
        provider_name="RAZORPAY",
        request_body=raw_body,
        headers=headers,
    )
    assert success1 is True, f"process_settlement_webhook failed with: {msg1}"
    assert in_work_order.payments.filter(status=WorkOrderPaymentStatusChoices.SUCCESS).count() == 1

    success2, msg2 = WorkOrderSettlementService.process_settlement_webhook(
        provider_name="RAZORPAY",
        request_body=raw_body,
        headers=headers,
    )
    assert success2 is True
    assert "already processed" in msg2.lower()
    assert in_work_order.payments.filter(status=WorkOrderPaymentStatusChoices.SUCCESS).count() == 1

    success3, msg3 = WorkOrderSettlementService.process_settlement_webhook(
        provider_name="RAZORPAY",
        request_body=raw_body,
        headers=headers,
    )
    assert success3 is True
    assert in_work_order.payments.filter(status=WorkOrderPaymentStatusChoices.SUCCESS).count() == 1

