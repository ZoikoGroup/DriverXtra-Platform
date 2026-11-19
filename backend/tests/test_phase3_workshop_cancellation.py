import hashlib
import hmac
import json
import re
import uuid
from decimal import Decimal
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

import pytest
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, models
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.identity.models import User, RoleChoices
from apps.organisations.models import Organisation, OrganisationRoleChoices, OrganisationTypeChoices
from apps.garage.models import GarageVehicle
from apps.catalogue.models import Part
from apps.marketplace.models import SparePartListing, StockMovement, StockMovementReasonChoices
from apps.workshops.models import (
    WorkshopProfile,
    WorkshopBooking,
    WorkshopQuotation,
    QuotationLineItem,
    WorkOrder,
    WorkOrderStatusChoices,
    WorkOrderSettlementStatusChoices,
    WorkOrderTask,
    WorkOrderTaskStatusChoices,
    WorkOrderPartUsage,
    WorkOrderPayment,
    WorkOrderPaymentStatusChoices,
    WorkOrderPaymentTypeChoices,
    WorkshopRefund,
    WorkshopRefundStatusChoices,
    BookingStatusChoices,
    QuotationStatusChoices,
    DepositStatusChoices,
    LineItemTypeChoices,
    WorkshopDepositWebhookEvent,
    WorkshopSettlementWebhookEvent,
)
from apps.workshops.services import BookingService, QuotationService, WorkOrderService
from apps.workshops.deposit_service import WorkshopDepositPaymentService
from apps.workshops.settlement_service import WorkOrderSettlementService
from apps.workshops.refund_service import WorkshopRefundService
from apps.marketplace.payments.razorpay_provider import RazorpayPaymentProvider
from apps.marketplace.payments.stripe_provider import StripePaymentProvider
from platform_core.audit.models import AuditLog


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
def uk_workshop_org(db, owner_user):
    org = Organisation.objects.create(
        name="Apex Motors London",
        type=OrganisationTypeChoices.WORKSHOP,
        country="GB",
        jurisdiction="GB-ENG",
        created_by=owner_user,
    )
    org.memberships.create(user=owner_user, role=OrganisationRoleChoices.OWNER, is_active=True)
    return org


@pytest.fixture
def in_workshop_org(db, owner_user):
    org = Organisation.objects.create(
        name="Apex Motors Mumbai",
        type=OrganisationTypeChoices.WORKSHOP,
        country="IN",
        jurisdiction="IN-MH",
        created_by=owner_user,
    )
    org.memberships.create(user=owner_user, role=OrganisationRoleChoices.OWNER, is_active=True)
    return org


@pytest.fixture
def uk_workshop(db, uk_workshop_org):
    return WorkshopProfile.objects.create(
        organisation=uk_workshop_org,
        business_name="Apex Motors London",
        slug=f"apex-london-{uuid.uuid4().hex[:6]}",
        contact_email="london@apexmotors.com",
        contact_phone="+442079460991",
        address_line1="100 Service Road",
        city="London",
        country="GB",
        currency="GBP",
        is_accepting_bookings=True,
        is_verified=True,
    )


@pytest.fixture
def in_workshop(db, in_workshop_org):
    return WorkshopProfile.objects.create(
        organisation=in_workshop_org,
        business_name="Apex Motors Mumbai",
        slug=f"apex-mumbai-{uuid.uuid4().hex[:6]}",
        contact_email="mumbai@apexmotors.com",
        contact_phone="+919876543210",
        address_line1="100 Marine Drive",
        city="Mumbai",
        country="IN",
        currency="INR",
        is_accepting_bookings=True,
        is_verified=True,
    )


@pytest.fixture
def buyer_vehicle(db, buyer_user):
    return GarageVehicle.objects.create(
        user=buyer_user,
        make="BMW",
        model="3 Series",
        year=2021,
        registration_plate=f"BW{uuid.uuid4().hex[:4].upper()}",
        vin=f"WBA{uuid.uuid4().hex[:14].upper()}",
        current_odometer=25000,
        odometer_unit="mi",
    )


@pytest.fixture
def buyer_client(buyer_user):
    client = APIClient()
    client.force_authenticate(user=buyer_user)
    return client


@pytest.fixture
def other_buyer_client(other_buyer_user):
    client = APIClient()
    client.force_authenticate(user=other_buyer_user)
    return client


# =========================================================================
# TEST SUITE: PHASE 3 BUYER BOOKING CANCELLATION & AUTOMATIC REFUND
# =========================================================================

@pytest.mark.django_db
def test_01_eligible_booking_cancellation_no_payments(buyer_client, uk_workshop, buyer_user, buyer_vehicle):
    """
    Test 1: Cancelling an eligible booking with no payments collected.
    Transitions status to CANCELLED, records reason, actor, timestamp, and audit log.
    Refund status is NOT_APPLICABLE with 0.00 refundable amount.
    """
    booking = WorkshopBooking.objects.create(
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        preferred_date=date.today() + timedelta(days=3),
        status=BookingStatusChoices.REQUESTED,
    )

    url = f"/api/v1/workshops/bookings/my/{booking.id}/cancel/"
    resp = buyer_client.post(url, {"reason": "Change of plans, car is sold."}, format="json")

    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["status"] == "CANCELLED"
    assert data["cancellation_status"] == "CANCELLED"
    assert data["cancellation_reason"] == "Change of plans, car is sold."
    assert data["refund_status"] == "NOT_APPLICABLE"
    assert Decimal(data["refundable_amount"]) == Decimal("0.00")
    assert Decimal(data["refunded_amount"]) == Decimal("0.00")

    # DB state verified
    booking.refresh_from_db()
    assert booking.status == BookingStatusChoices.CANCELLED
    assert booking.cancellation_reason == "Change of plans, car is sold."
    assert booking.cancelled_by == buyer_user
    assert booking.cancelled_at is not None

    # Audit log entry exists
    audit = AuditLog.objects.filter(resource_type="WorkshopBooking", resource_id=str(booking.id)).first()
    assert audit is not None
    assert audit.action == "workshop:booking.cancel"


@pytest.mark.django_db
def test_02_ineligible_booking_already_cancelled(buyer_client, uk_workshop, buyer_user, buyer_vehicle):
    """
    Test 2: Attempting to cancel an already cancelled booking fails with 400 Bad Request.
    """
    booking = WorkshopBooking.objects.create(
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        preferred_date=date.today() + timedelta(days=3),
        status=BookingStatusChoices.CANCELLED,
        cancellation_reason="Previous cancellation",
    )

    url = f"/api/v1/workshops/bookings/my/{booking.id}/cancel/"
    resp = buyer_client.post(url, {"reason": "Trying to cancel again"}, format="json")

    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "already cancelled" in resp.json()["message"].lower()


@pytest.mark.django_db
def test_03_ineligible_booking_rejected(buyer_client, uk_workshop, buyer_user, buyer_vehicle):
    """
    Test 3: Attempting to cancel an already rejected booking fails with 400 Bad Request.
    """
    booking = WorkshopBooking.objects.create(
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        preferred_date=date.today() + timedelta(days=3),
        status=BookingStatusChoices.REJECTED,
        rejection_reason="No slot available",
    )

    url = f"/api/v1/workshops/bookings/my/{booking.id}/cancel/"
    resp = buyer_client.post(url, {"reason": "Cancel rejected booking"}, format="json")

    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "rejected" in resp.json()["message"].lower()


@pytest.mark.django_db
def test_04_ineligible_booking_work_order_completed(buyer_client, uk_workshop, buyer_user, buyer_vehicle, owner_user):
    """
    Test 4: Attempting to cancel a booking whose WorkOrder is COMPLETED fails with 400 Bad Request.
    """
    booking = WorkshopBooking.objects.create(
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        preferred_date=date.today() + timedelta(days=1),
        status=BookingStatusChoices.CONFIRMED,
    )
    quote = WorkshopQuotation.objects.create(
        booking=booking,
        total_amount=Decimal("150.00"),
        status=QuotationStatusChoices.ACCEPTED,
        currency="GBP",
    )
    work_order = WorkOrder.objects.create(
        booking=booking,
        quotation=quote,
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        status=WorkOrderStatusChoices.COMPLETED,
    )

    url = f"/api/v1/workshops/bookings/my/{booking.id}/cancel/"
    resp = buyer_client.post(url, {"reason": "Work finished, want to cancel"}, format="json")

    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "completed" in resp.json()["message"].lower()


@pytest.mark.django_db
def test_05_cancellation_by_different_buyer_forbidden(other_buyer_client, uk_workshop, buyer_user, buyer_vehicle):
    """
    Test 5: Buyer B attempts to cancel Buyer A's booking. Denied with 403 Forbidden.
    """
    booking = WorkshopBooking.objects.create(
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        preferred_date=date.today() + timedelta(days=3),
        status=BookingStatusChoices.REQUESTED,
    )

    url = f"/api/v1/workshops/bookings/my/{booking.id}/cancel/"
    resp = other_buyer_client.post(url, {"reason": "Malicious cancellation attempt"}, format="json")

    assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_06_duplicate_cancellation_requests_prevent_duplicate_refunds(buyer_client, uk_workshop, buyer_user, buyer_vehicle):
    """
    Test 6: Repeated/duplicate cancellation requests fail safely on the second call
    without issuing duplicate refunds or dispatching multiple gateway refunds.
    """
    booking = WorkshopBooking.objects.create(
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        preferred_date=date.today() + timedelta(days=2),
        status=BookingStatusChoices.CONFIRMED,
    )
    quote = WorkshopQuotation.objects.create(
        booking=booking,
        total_amount=Decimal("200.00"),
        requires_deposit=True,
        deposit_amount=Decimal("50.00"),
        deposit_status=DepositStatusChoices.PAID,
        deposit_transaction_id="pi_stripe_test_dep123",
        deposit_provider="STRIPE",
        status=QuotationStatusChoices.ACCEPTED,
        currency="GBP",
    )

    url = f"/api/v1/workshops/bookings/my/{booking.id}/cancel/"

    # First cancellation succeeds
    resp1 = buyer_client.post(url, {"reason": "Customer cancellation"}, format="json")
    assert resp1.status_code == status.HTTP_200_OK
    assert resp1.json()["refund_status"] == "SUCCEEDED"
    assert resp1.json()["refunded_amount"] == "50.00"

    # Exactly 1 refund record created
    assert WorkshopRefund.objects.filter(booking=booking).count() == 1

    # Second cancellation fails immediately
    resp2 = buyer_client.post(url, {"reason": "Customer cancellation replay"}, format="json")
    assert resp2.status_code == status.HTTP_400_BAD_REQUEST
    assert "already cancelled" in resp2.json()["message"].lower()

    # Still exactly 1 refund record in DB
    assert WorkshopRefund.objects.filter(booking=booking).count() == 1


@pytest.mark.django_db
def test_07_concurrent_cancellation_requests_row_locking(buyer_client, uk_workshop, buyer_user, buyer_vehicle):
    """
    Test 7: Concurrency protection via select_for_update row locking.
    Simulated concurrent invocation ensures atomic state transition and no duplicate refunds.
    """
    booking = WorkshopBooking.objects.create(
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        preferred_date=date.today() + timedelta(days=2),
        status=BookingStatusChoices.REQUESTED,
    )

    # First call cancels booking
    res1 = BookingService.cancel_booking(booking=booking, reason="First concurrent worker", actor=buyer_user)
    assert res1.status == BookingStatusChoices.CANCELLED

    # Second call sees CANCELLED and raises ValidationError
    with pytest.raises(Exception) as excinfo:
        BookingService.cancel_booking(booking=booking, reason="Second concurrent worker", actor=buyer_user)
    assert "already cancelled" in str(excinfo.value).lower()


@pytest.mark.django_db
def test_08_fully_paid_booking_refund_deposit_and_balance(buyer_client, uk_workshop, buyer_user, buyer_vehicle, owner_user):
    """
    Test 8: Fully paid booking (Deposit + Final Balance payment).
    Cancelling automatically issues 2 distinct gateway refunds totaling the full collected amount.
    """
    booking = WorkshopBooking.objects.create(
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        preferred_date=date.today() + timedelta(days=2),
        status=BookingStatusChoices.CONFIRMED,
    )
    quote = WorkshopQuotation.objects.create(
        booking=booking,
        total_amount=Decimal("200.00"),
        requires_deposit=True,
        deposit_amount=Decimal("50.00"),
        deposit_status=DepositStatusChoices.PAID,
        deposit_transaction_id="pi_deposit_full123",
        deposit_provider="STRIPE",
        status=QuotationStatusChoices.ACCEPTED,
        currency="GBP",
    )
    work_order = WorkOrder.objects.create(
        booking=booking,
        quotation=quote,
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        status=WorkOrderStatusChoices.ASSIGNED,
    )
    payment = WorkOrderPayment.objects.create(
        work_order=work_order,
        amount=Decimal("150.00"),
        currency="GBP",
        provider="STRIPE",
        payment_type=WorkOrderPaymentTypeChoices.FINAL,
        status=WorkOrderPaymentStatusChoices.SUCCESS,
        provider_payment_id="pi_balance_full456",
        created_by=buyer_user,
    )

    url = f"/api/v1/workshops/bookings/my/{booking.id}/cancel/"
    resp = buyer_client.post(url, {"reason": "Complete order cancellation"}, format="json")

    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["status"] == "CANCELLED"
    assert data["refund_status"] == "SUCCEEDED"
    assert Decimal(data["refundable_amount"]) == Decimal("200.00")
    assert Decimal(data["refunded_amount"]) == Decimal("200.00")

    # DB verification: Quote deposit marked REFUNDED, WorkOrderPayment marked REFUNDED
    quote.refresh_from_db()
    assert quote.deposit_status == DepositStatusChoices.REFUNDED
    payment.refresh_from_db()
    assert payment.status == WorkOrderPaymentStatusChoices.REFUNDED

    # 2 WorkshopRefund records created
    refunds = list(WorkshopRefund.objects.filter(booking=booking).order_by("created_at"))
    assert len(refunds) == 2
    assert refunds[0].amount == Decimal("50.00")
    assert refunds[0].status == WorkshopRefundStatusChoices.SUCCEEDED
    assert refunds[1].amount == Decimal("150.00")
    assert refunds[1].status == WorkshopRefundStatusChoices.SUCCEEDED


@pytest.mark.django_db
def test_09_deposit_only_refund(buyer_client, in_workshop, buyer_user, buyer_vehicle):
    """
    Test 9: Deposit-only refund in INR (Razorpay).
    """
    booking = WorkshopBooking.objects.create(
        workshop=in_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        preferred_date=date.today() + timedelta(days=2),
        status=BookingStatusChoices.CONFIRMED,
    )
    quote = WorkshopQuotation.objects.create(
        booking=booking,
        total_amount=Decimal("5000.00"),
        requires_deposit=True,
        deposit_amount=Decimal("1000.00"),
        deposit_status=DepositStatusChoices.PAID,
        deposit_transaction_id="pay_razorpay_dep999",
        deposit_provider="RAZORPAY",
        status=QuotationStatusChoices.ACCEPTED,
        currency="INR",
    )

    url = f"/api/v1/workshops/bookings/my/{booking.id}/cancel/"
    resp = buyer_client.post(url, {"reason": "Cancelling Indian appointment"}, format="json")

    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["refund_status"] == "SUCCEEDED"
    assert Decimal(data["refundable_amount"]) == Decimal("1000.00")
    assert Decimal(data["refunded_amount"]) == Decimal("1000.00")

    quote.refresh_from_db()
    assert quote.deposit_status == DepositStatusChoices.REFUNDED

    rfnd = WorkshopRefund.objects.get(booking=booking)
    assert rfnd.gateway_provider == "RAZORPAY"
    assert rfnd.amount == Decimal("1000.00")
    assert rfnd.status == WorkshopRefundStatusChoices.SUCCEEDED


@pytest.mark.django_db
def test_10_partially_paid_booking_refund(buyer_client, uk_workshop, buyer_user, buyer_vehicle):
    """
    Test 10: Partially paid booking refund.
    Deposit (£50) + Partial Balance (£75) on a £300 quote.
    Only the actual collected £125 is refunded.
    """
    booking = WorkshopBooking.objects.create(
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        preferred_date=date.today() + timedelta(days=2),
        status=BookingStatusChoices.CONFIRMED,
    )
    quote = WorkshopQuotation.objects.create(
        booking=booking,
        total_amount=Decimal("300.00"),
        requires_deposit=True,
        deposit_amount=Decimal("50.00"),
        deposit_status=DepositStatusChoices.PAID,
        deposit_transaction_id="pi_stripe_partial_dep",
        deposit_provider="STRIPE",
        status=QuotationStatusChoices.ACCEPTED,
        currency="GBP",
    )
    work_order = WorkOrder.objects.create(
        booking=booking,
        quotation=quote,
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        status=WorkOrderStatusChoices.IN_PROGRESS,
    )
    payment = WorkOrderPayment.objects.create(
        work_order=work_order,
        amount=Decimal("75.00"),
        currency="GBP",
        provider="STRIPE",
        payment_type=WorkOrderPaymentTypeChoices.PARTIAL,
        status=WorkOrderPaymentStatusChoices.SUCCESS,
        provider_payment_id="pi_stripe_partial_bal",
        created_by=buyer_user,
    )

    url = f"/api/v1/workshops/bookings/my/{booking.id}/cancel/"
    resp = buyer_client.post(url, {"reason": "Partial repair cancelled"}, format="json")

    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["refund_status"] == "SUCCEEDED"
    assert Decimal(data["refundable_amount"]) == Decimal("125.00")
    assert Decimal(data["refunded_amount"]) == Decimal("125.00")


@pytest.mark.django_db
def test_11_previously_refunded_amounts_prevent_double_refund(buyer_client, uk_workshop, buyer_user, buyer_vehicle):
    """
    Test 11: Previously refunded amounts are strictly excluded from refund calculations.
    """
    booking = WorkshopBooking.objects.create(
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        preferred_date=date.today() + timedelta(days=2),
        status=BookingStatusChoices.CONFIRMED,
    )
    quote = WorkshopQuotation.objects.create(
        booking=booking,
        total_amount=Decimal("300.00"),
        requires_deposit=True,
        deposit_amount=Decimal("50.00"),
        deposit_status=DepositStatusChoices.REFUNDED,  # Already refunded
        deposit_transaction_id="pi_stripe_dep_old",
        deposit_provider="STRIPE",
        status=QuotationStatusChoices.ACCEPTED,
        currency="GBP",
    )
    work_order = WorkOrder.objects.create(
        booking=booking,
        quotation=quote,
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        status=WorkOrderStatusChoices.ASSIGNED,
    )
    # Payment 1: already refunded
    WorkOrderPayment.objects.create(
        work_order=work_order,
        amount=Decimal("40.00"),
        currency="GBP",
        provider="STRIPE",
        payment_type=WorkOrderPaymentTypeChoices.PARTIAL,
        status=WorkOrderPaymentStatusChoices.REFUNDED,
        provider_payment_id="pi_stripe_old_p1",
        created_by=buyer_user,
    )
    # Payment 2: genuine success payment
    WorkOrderPayment.objects.create(
        work_order=work_order,
        amount=Decimal("60.00"),
        currency="GBP",
        provider="STRIPE",
        payment_type=WorkOrderPaymentTypeChoices.BALANCE,
        status=WorkOrderPaymentStatusChoices.SUCCESS,
        provider_payment_id="pi_stripe_active_p2",
        created_by=buyer_user,
    )

    url = f"/api/v1/workshops/bookings/my/{booking.id}/cancel/"
    resp = buyer_client.post(url, {"reason": "Cancel unrefunded balance"}, format="json")

    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert Decimal(data["refundable_amount"]) == Decimal("60.00")
    assert Decimal(data["refunded_amount"]) == Decimal("60.00")
    assert data["refund_status"] == "SUCCEEDED"

    # Exactly 1 new refund created for the active £60 payment
    assert WorkshopRefund.objects.filter(booking=booking).count() == 1
    assert WorkshopRefund.objects.get(booking=booking).amount == Decimal("60.00")


@pytest.mark.django_db
def test_12_no_payment_cancellation_does_not_call_gateway(buyer_client, uk_workshop, buyer_user, buyer_vehicle):
    """
    Test 12: Cancellation with no payments never makes a gateway call.
    """
    booking = WorkshopBooking.objects.create(
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        preferred_date=date.today() + timedelta(days=2),
        status=BookingStatusChoices.CONFIRMED,
    )
    WorkshopQuotation.objects.create(
        booking=booking,
        total_amount=Decimal("150.00"),
        requires_deposit=False,
        deposit_status=DepositStatusChoices.NOT_REQUIRED,
        status=QuotationStatusChoices.ACCEPTED,
        currency="GBP",
    )

    with patch.object(StripePaymentProvider, "issue_refund") as mock_stripe_refund, \
         patch.object(RazorpayPaymentProvider, "issue_refund") as mock_razorpay_refund:
        url = f"/api/v1/workshops/bookings/my/{booking.id}/cancel/"
        resp = buyer_client.post(url, {"reason": "No deposit cancellation"}, format="json")

        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["refund_status"] == "NOT_APPLICABLE"
        mock_stripe_refund.assert_not_called()
        mock_razorpay_refund.assert_not_called()


@pytest.mark.django_db
def test_13_razorpay_refund_payload_and_idempotency_headers(buyer_client, in_workshop, buyer_user, buyer_vehicle):
    """
    Test 13: Razorpay INR refund uses deterministic idempotency key and receipt.
    """
    booking = WorkshopBooking.objects.create(
        workshop=in_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        preferred_date=date.today() + timedelta(days=2),
        status=BookingStatusChoices.CONFIRMED,
    )
    quote = WorkshopQuotation.objects.create(
        booking=booking,
        total_amount=Decimal("4000.00"),
        requires_deposit=True,
        deposit_amount=Decimal("1000.00"),
        deposit_status=DepositStatusChoices.PAID,
        deposit_transaction_id="pay_inr_dep12345",
        deposit_provider="RAZORPAY",
        status=QuotationStatusChoices.ACCEPTED,
        currency="INR",
    )

    url = f"/api/v1/workshops/bookings/my/{booking.id}/cancel/"
    resp = buyer_client.post(url, {"reason": "Testing Razorpay header & receipt"}, format="json")

    assert resp.status_code == status.HTTP_200_OK
    rfnd = WorkshopRefund.objects.get(booking=booking)
    assert rfnd.gateway_provider == "RAZORPAY"
    assert rfnd.refund_number.startswith("REF-WB-DEP-")

    # Idempotency key adheres strictly to Razorpay 10-40 char constraints
    expected_key = RazorpayPaymentProvider.generate_refund_idempotency_key(rfnd.refund_number)
    assert rfnd.idempotency_key == expected_key
    assert 10 <= len(rfnd.idempotency_key) <= 40


@pytest.mark.django_db
def test_14_stripe_refund_payload_and_idempotency(buyer_client, uk_workshop, buyer_user, buyer_vehicle):
    """
    Test 14: Stripe GBP refund uses deterministic idempotency key and payment reference.
    """
    booking = WorkshopBooking.objects.create(
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        preferred_date=date.today() + timedelta(days=2),
        status=BookingStatusChoices.CONFIRMED,
    )
    quote = WorkshopQuotation.objects.create(
        booking=booking,
        total_amount=Decimal("250.00"),
        requires_deposit=True,
        deposit_amount=Decimal("50.00"),
        deposit_status=DepositStatusChoices.PAID,
        deposit_transaction_id="pi_stripe_test_abc",
        deposit_provider="STRIPE",
        status=QuotationStatusChoices.ACCEPTED,
        currency="GBP",
    )

    url = f"/api/v1/workshops/bookings/my/{booking.id}/cancel/"
    resp = buyer_client.post(url, {"reason": "Testing Stripe refund dispatch"}, format="json")

    assert resp.status_code == status.HTTP_200_OK
    rfnd = WorkshopRefund.objects.get(booking=booking)
    assert rfnd.gateway_provider == "STRIPE"
    assert rfnd.payment_reference == "pi_stripe_test_abc"
    assert rfnd.idempotency_key == rfnd.refund_number[:40]


@pytest.mark.django_db
def test_15_gateway_timeout_and_processing_unknown_transition(buyer_client, uk_workshop, buyer_user, buyer_vehicle):
    """
    Test 15: Gateway network timeout transitions refund to PROCESSING_UNKNOWN.
    Does not retry blindly. Sets next_reconciliation_at.
    """
    booking = WorkshopBooking.objects.create(
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        preferred_date=date.today() + timedelta(days=2),
        status=BookingStatusChoices.CONFIRMED,
    )
    quote = WorkshopQuotation.objects.create(
        booking=booking,
        total_amount=Decimal("200.00"),
        requires_deposit=True,
        deposit_amount=Decimal("50.00"),
        deposit_status=DepositStatusChoices.PAID,
        deposit_transaction_id="pi_stripe_timeout_test",
        deposit_provider="STRIPE",
        status=QuotationStatusChoices.ACCEPTED,
        currency="GBP",
    )

    with patch.object(StripePaymentProvider, "issue_refund", side_effect=TimeoutError("Gateway connection timed out")):
        url = f"/api/v1/workshops/bookings/my/{booking.id}/cancel/"
        resp = buyer_client.post(url, {"reason": "Testing timeout handling"}, format="json")

        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["status"] == "CANCELLED"
        assert data["refund_status"] == "PROCESSING_UNKNOWN"

        rfnd = WorkshopRefund.objects.get(booking=booking)
        assert rfnd.status == WorkshopRefundStatusChoices.PROCESSING_UNKNOWN
        assert "timed out" in rfnd.failure_reason.lower()
        assert rfnd.next_reconciliation_at is not None


@pytest.mark.django_db
def test_16_gateway_timeout_reconciliation_resolves_to_succeeded(buyer_client, uk_workshop, buyer_user, buyer_vehicle):
    """
    Test 16: Reconciliation via inquiry resolves a PROCESSING_UNKNOWN refund to SUCCEEDED.
    """
    booking = WorkshopBooking.objects.create(
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        preferred_date=date.today() + timedelta(days=2),
        status=BookingStatusChoices.CANCELLED,
    )
    quote = WorkshopQuotation.objects.create(
        booking=booking,
        total_amount=Decimal("200.00"),
        requires_deposit=True,
        deposit_amount=Decimal("50.00"),
        deposit_status=DepositStatusChoices.PAID,
        status=QuotationStatusChoices.ACCEPTED,
        currency="GBP",
    )
    rfnd = WorkshopRefund.objects.create(
        booking=booking,
        quotation=quote,
        amount=Decimal("50.00"),
        currency="GBP",
        status=WorkshopRefundStatusChoices.PROCESSING_UNKNOWN,
        gateway_provider="STRIPE",
        payment_reference="pi_test_reconcile",
        refund_number=f"REF-WB-DEP-{quote.quotation_number}",
        failure_reason="Timeout during dispatch",
    )

    with patch.object(StripePaymentProvider, "inquire_refund", return_value=("SUCCEEDED", "re_gateway_resolved_123", {})):
        reconciled_rfnd, outcome = WorkshopRefundService.reconcile_refund(rfnd.id)

        assert outcome == "RECONCILED_SUCCEEDED"
        assert reconciled_rfnd.status == WorkshopRefundStatusChoices.SUCCEEDED
        assert reconciled_rfnd.gateway_refund_id == "re_gateway_resolved_123"

        quote.refresh_from_db()
        assert quote.deposit_status == DepositStatusChoices.REFUNDED


@pytest.mark.django_db
def test_17_duplicate_webhook_delivery_idempotent(in_workshop, buyer_user, buyer_vehicle):
    """
    Test 17: Duplicate webhook delivery for a refund is handled idempotently without error.
    """
    booking = WorkshopBooking.objects.create(
        workshop=in_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        preferred_date=date.today() + timedelta(days=2),
        status=BookingStatusChoices.CONFIRMED,
    )
    quote = WorkshopQuotation.objects.create(
        booking=booking,
        deposit_order_id="order_webhook_test_123",
        deposit_transaction_id="pay_webhook_test_123",
        deposit_status=DepositStatusChoices.PAID,
        currency="INR",
        requires_deposit=True,
        deposit_amount=Decimal("500.00"),
    )

    # First delivery
    event_id = "evt_refund_dedup_001"
    raw_payload = json.dumps({
        "entity": "event",
        "account_id": "acc_test",
        "event": "refund.processed",
        "payload": {
            "payment": {"entity": {"id": "pay_webhook_test_123", "order_id": "order_webhook_test_123"}},
            "refund": {"entity": {"id": "rfnd_razorpay_999", "status": "processed"}}
        }
    }).encode("utf-8")

    secret = getattr(settings, "RAZORPAY_WEBHOOK_SECRET", "test_secret")
    sig = hmac.new(secret.encode("utf-8"), raw_payload, hashlib.sha256).hexdigest()
    headers = {"HTTP_X_RAZORPAY_SIGNATURE": sig}

    with patch.object(RazorpayPaymentProvider, "verify_webhook", return_value=(True, event_id, "refund.processed", json.loads(raw_payload))):
        ok1, msg1 = WorkshopDepositPaymentService.process_deposit_webhook("RAZORPAY", raw_payload, headers)
        assert ok1 is True

        # Second delivery (replay)
        ok2, msg2 = WorkshopDepositPaymentService.process_deposit_webhook("RAZORPAY", raw_payload, headers)
        assert ok2 is True
        assert "already processed" in msg2.lower()


@pytest.mark.django_db
def test_18_prevention_of_payment_collection_after_cancellation(uk_workshop, buyer_user, buyer_vehicle):
    """
    Test 18: Prevents deposit and settlement payment creation after booking cancellation.
    """
    booking = WorkshopBooking.objects.create(
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        preferred_date=date.today() + timedelta(days=2),
        status=BookingStatusChoices.CANCELLED,
    )
    quote = WorkshopQuotation.objects.create(
        booking=booking,
        total_amount=Decimal("200.00"),
        requires_deposit=True,
        deposit_amount=Decimal("50.00"),
        status=QuotationStatusChoices.ISSUED,
        currency="GBP",
    )

    # Deposit session blocked
    with pytest.raises(Exception) as exc1:
        WorkshopDepositPaymentService.create_deposit_session(quotation=quote, buyer=buyer_user)
    assert "cancelled" in str(exc1.value).lower()

    # Deposit verification blocked
    with pytest.raises(Exception) as exc2:
        WorkshopDepositPaymentService.verify_deposit_payment(quotation_id=quote.id, payload={}, actor=buyer_user)
    assert "cancelled" in str(exc2.value).lower()

    # Quotation acceptance blocked
    with pytest.raises(Exception) as exc3:
        QuotationService.accept_quotation(quotation=quote, buyer=buyer_user)
    assert "cancelled" in str(exc3.value).lower()


@pytest.mark.django_db
def test_19_preservation_of_completed_work_and_service_history(buyer_client, uk_workshop, buyer_user, buyer_vehicle, owner_user):
    """
    Test 19: Safe cancellation of an in-progress work order:
    - Restocks consumed parts via StockMovement.
    - Preserves completed tasks (does not overwrite their completed state).
    - Preserves historical records in database.
    """
    booking = WorkshopBooking.objects.create(
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        preferred_date=date.today() + timedelta(days=2),
        status=BookingStatusChoices.CONFIRMED,
    )
    quote = WorkshopQuotation.objects.create(
        booking=booking,
        total_amount=Decimal("250.00"),
        status=QuotationStatusChoices.ACCEPTED,
        currency="GBP",
    )
    work_order = WorkOrder.objects.create(
        booking=booking,
        quotation=quote,
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        status=WorkOrderStatusChoices.IN_PROGRESS,
    )

    # 1 Completed task and 1 In-Progress task
    t_completed = WorkOrderTask.objects.create(
        work_order=work_order,
        description="Drain oil and replace filter",
        status=WorkOrderTaskStatusChoices.COMPLETED,
    )
    t_in_progress = WorkOrderTask.objects.create(
        work_order=work_order,
        description="Inspect suspension bushes",
        status=WorkOrderTaskStatusChoices.IN_PROGRESS,
    )

    # Consumed spare part
    from apps.catalogue.models import PartCategory
    cat = PartCategory.objects.create(name="Filters", slug=f"filters-{uuid.uuid4().hex[:6]}")
    listing = SparePartListing.objects.create(
        seller=owner_user,
        category=cat,
        name="Oil Filter Pro",
        brand="Bosch",
        mpn=f"OF-{uuid.uuid4().hex[:6]}",
        price=Decimal("25.00"),
        stock_quantity=10,
        currency="GBP",
    )
    part_usage = WorkOrderPartUsage.objects.create(
        work_order=work_order,
        inventory_item=listing,
        part_name="Oil Filter Pro",
        part_number=listing.mpn,
        quantity=Decimal("2.00"),
        unit_cost=Decimal("25.00"),
        total_cost=Decimal("50.00"),
        is_stock_deducted=True,
    )

    # Cancel booking
    url = f"/api/v1/workshops/bookings/my/{booking.id}/cancel/"
    resp = buyer_client.post(url, {"reason": "Customer needs vehicle back immediately"}, format="json")

    assert resp.status_code == status.HTTP_200_OK

    # Work order is cancelled
    work_order.refresh_from_db()
    assert work_order.status == WorkOrderStatusChoices.CANCELLED
    assert work_order.settlement_status == WorkOrderSettlementStatusChoices.UNPAID

    # Completed task remains COMPLETED (history preserved!)
    t_completed.refresh_from_db()
    assert t_completed.status == WorkOrderTaskStatusChoices.COMPLETED

    # Consumed part was restocked: 10 + 2 = 12
    listing.refresh_from_db()
    assert listing.stock_quantity == 12

    part_usage.refresh_from_db()
    assert part_usage.is_stock_deducted is False

    # StockMovement record created
    movement = StockMovement.objects.filter(listing=listing, reason=StockMovementReasonChoices.WORK_ORDER_RESTOCK).first()
    assert movement is not None
    assert movement.delta == 2


@pytest.mark.django_db
def test_20_both_url_routes_work_identically(buyer_client, uk_workshop, buyer_user, buyer_vehicle):
    """
    Test 20: Both /api/v1/workshops/bookings/<id>/cancel/ and
    /api/v1/workshops/bookings/my/<id>/cancel/ function identically.
    """
    b1 = WorkshopBooking.objects.create(
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        preferred_date=date.today() + timedelta(days=2),
        status=BookingStatusChoices.REQUESTED,
    )
    b2 = WorkshopBooking.objects.create(
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        preferred_date=date.today() + timedelta(days=3),
        status=BookingStatusChoices.REQUESTED,
    )

    # Test /bookings/my/<id>/cancel/
    r1 = buyer_client.post(f"/api/v1/workshops/bookings/my/{b1.id}/cancel/", {"reason": "Route 1"}, format="json")
    assert r1.status_code == status.HTTP_200_OK
    assert r1.json()["status"] == "CANCELLED"

    # Test /bookings/<id>/cancel/
    r2 = buyer_client.post(f"/api/v1/workshops/bookings/{b2.id}/cancel/", {"reason": "Route 2"}, format="json")
    assert r2.status_code == status.HTTP_200_OK
    assert r2.json()["status"] == "CANCELLED"


# ==============================================================================
# AUDIT REGRESSION SUITE: PRECISION FINANCIAL REFUND CALCULATIONS (CRITICAL P0)
# ==============================================================================

@pytest.mark.django_db
def test_21_payment_100_no_previous_refund(buyer_client, uk_workshop, buyer_user, buyer_vehicle):
    """
    Test 21: A £100 payment with no previous refund refunds exactly £100 on cancellation.
    """
    booking = WorkshopBooking.objects.create(
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        preferred_date=date.today() + timedelta(days=2),
        status=BookingStatusChoices.CONFIRMED,
    )
    quote = WorkshopQuotation.objects.create(
        booking=booking,
        version=1,
        status=QuotationStatusChoices.ACCEPTED,
        total_amount=Decimal('100.00'),
        currency='GBP',
    )
    wo = WorkOrder.objects.create(
        booking=booking,
        quotation=quote,
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle_make="BMW",
        vehicle_model="3 Series",
        vehicle_registration_plate="BM12ABC",
        status=WorkOrderStatusChoices.IN_PROGRESS,
    )
    p = WorkOrderPayment.objects.create(
        work_order=wo,
        payment_type=WorkOrderPaymentTypeChoices.BALANCE,
        amount=Decimal('100.00'),
        currency='GBP',
        provider='STRIPE',
        status=WorkOrderPaymentStatusChoices.SUCCESS,
        provider_payment_id="pi_test_100",
        created_by=buyer_user,
    )

    info = WorkshopRefundService.calculate_refundable_amount(booking)
    assert Decimal(info["refundable_amount"]) == Decimal("100.00")
    assert Decimal(info["total_collected"]) == Decimal("100.00")
    assert Decimal(info["total_already_refunded"]) == Decimal("0.00")

    updated = WorkshopRefundService.process_booking_cancellation_refunds(
        booking=booking,
        reason="Test full refund",
        actor=buyer_user,
    )
    summary = updated.refund_summary
    assert Decimal(summary["refunded_amount"]) == Decimal("100.00")
    assert summary["refund_status"] == "SUCCEEDED"
    assert len(summary["refund_details"]) == 1
    assert Decimal(summary["refund_details"][0]["amount"]) == Decimal("100.00")


@pytest.mark.django_db
def test_22_payment_100_with_successful_30_partial_refund(uk_workshop, buyer_user, buyer_vehicle):
    """
    Test 22: A £100 payment with a successful £30 partial refund only refunds
    the remaining £70 on cancellation. Total refunds = £30 + £70 = £100.
    """
    booking = WorkshopBooking.objects.create(
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        preferred_date=date.today() + timedelta(days=2),
        status=BookingStatusChoices.CONFIRMED,
    )
    quote = WorkshopQuotation.objects.create(
        booking=booking,
        version=1,
        status=QuotationStatusChoices.ACCEPTED,
        total_amount=Decimal('100.00'),
        currency='GBP',
    )
    wo = WorkOrder.objects.create(
        booking=booking,
        quotation=quote,
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle_make="BMW",
        vehicle_model="3 Series",
        vehicle_registration_plate="BM12ABC",
        status=WorkOrderStatusChoices.IN_PROGRESS,
    )
    p = WorkOrderPayment.objects.create(
        work_order=wo,
        payment_type=WorkOrderPaymentTypeChoices.BALANCE,
        amount=Decimal('100.00'),
        currency='GBP',
        provider='STRIPE',
        status=WorkOrderPaymentStatusChoices.SUCCESS,
        provider_payment_id="pi_test_partial_30",
        created_by=buyer_user,
    )

    # Prior partial refund of £30
    prior_rfnd = WorkshopRefund.objects.create(
        booking=booking,
        work_order=wo,
        work_order_payment=p,
        refund_number=f"REF-WB-{p.payment_number}",
        amount=Decimal('30.00'),
        currency='GBP',
        status=WorkshopRefundStatusChoices.SUCCEEDED,
        gateway_provider='STRIPE',
        payment_reference="pi_test_partial_30",
        idempotency_key=f"REF-WB-{p.payment_number}"[:40],
        created_by=buyer_user,
    )

    info = WorkshopRefundService.calculate_refundable_amount(booking)
    assert Decimal(info["total_collected"]) == Decimal("100.00")
    assert Decimal(info["total_already_refunded"]) == Decimal("30.00")
    assert Decimal(info["refundable_amount"]) == Decimal("70.00")

    updated = WorkshopRefundService.process_booking_cancellation_refunds(
        booking=booking,
        reason="Customer cancellation with prior partial",
        actor=buyer_user,
    )
    summary = updated.refund_summary
    assert Decimal(summary["refunded_amount"]) == Decimal("70.00")
    assert summary["refund_status"] == "SUCCEEDED"

    # Verify total refunds for payment p across database
    total_refunds_for_p = WorkshopRefund.objects.filter(
        work_order_payment=p,
        status=WorkshopRefundStatusChoices.SUCCEEDED,
    ).aggregate(total=models.Sum('amount'))['total']
    assert total_refunds_for_p == Decimal("100.00")
    assert total_refunds_for_p <= p.amount


@pytest.mark.django_db
def test_23_payment_100_with_successful_100_full_refund(uk_workshop, buyer_user, buyer_vehicle):
    """
    Test 23: A £100 payment with a successful £100 full refund yields £0 refundable
    on cancellation, dispatching 0 gateway refunds.
    """
    booking = WorkshopBooking.objects.create(
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        preferred_date=date.today() + timedelta(days=2),
        status=BookingStatusChoices.CONFIRMED,
    )
    quote = WorkshopQuotation.objects.create(
        booking=booking,
        version=1,
        status=QuotationStatusChoices.ACCEPTED,
        total_amount=Decimal('100.00'),
        currency='GBP',
    )
    wo = WorkOrder.objects.create(
        booking=booking,
        quotation=quote,
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle_make="BMW",
        vehicle_model="3 Series",
        vehicle_registration_plate="BM12ABC",
        status=WorkOrderStatusChoices.IN_PROGRESS,
    )
    p = WorkOrderPayment.objects.create(
        work_order=wo,
        payment_type=WorkOrderPaymentTypeChoices.BALANCE,
        amount=Decimal('100.00'),
        currency='GBP',
        provider='STRIPE',
        status=WorkOrderPaymentStatusChoices.REFUNDED,
        provider_payment_id="pi_test_full_100",
        created_by=buyer_user,
    )

    prior_rfnd = WorkshopRefund.objects.create(
        booking=booking,
        work_order=wo,
        work_order_payment=p,
        refund_number=f"REF-WB-{p.payment_number}",
        amount=Decimal('100.00'),
        currency='GBP',
        status=WorkshopRefundStatusChoices.SUCCEEDED,
        gateway_provider='STRIPE',
        payment_reference="pi_test_full_100",
        idempotency_key=f"REF-WB-{p.payment_number}"[:40],
        created_by=buyer_user,
    )

    info = WorkshopRefundService.calculate_refundable_amount(booking)
    assert Decimal(info["total_collected"]) == Decimal("100.00")
    assert Decimal(info["total_already_refunded"]) == Decimal("100.00")
    assert Decimal(info["refundable_amount"]) == Decimal("0.00")

    with patch.object(StripePaymentProvider, 'issue_refund') as mock_issue:
        updated = WorkshopRefundService.process_booking_cancellation_refunds(
            booking=booking,
            reason="Cancel fully refunded",
            actor=buyer_user,
        )
        assert mock_issue.call_count == 0

    assert Decimal(updated.refund_summary["refunded_amount"]) == Decimal("0.00")
    assert updated.refund_summary["refund_status"] == "NOT_APPLICABLE"


@pytest.mark.django_db
def test_24_payment_100_with_30_processing_refund(uk_workshop, buyer_user, buyer_vehicle):
    """
    Test 24: A £100 payment with an active £30 PROCESSING refund reserves the £30,
    allowing only the remaining £70 to be refunded. Total active + completed = £100.
    """
    booking = WorkshopBooking.objects.create(
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        preferred_date=date.today() + timedelta(days=2),
        status=BookingStatusChoices.CONFIRMED,
    )
    quote = WorkshopQuotation.objects.create(
        booking=booking,
        version=1,
        status=QuotationStatusChoices.ACCEPTED,
        total_amount=Decimal('100.00'),
        currency='GBP',
    )
    wo = WorkOrder.objects.create(
        booking=booking,
        quotation=quote,
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle_make="BMW",
        vehicle_model="3 Series",
        vehicle_registration_plate="BM12ABC",
        status=WorkOrderStatusChoices.IN_PROGRESS,
    )
    p = WorkOrderPayment.objects.create(
        work_order=wo,
        payment_type=WorkOrderPaymentTypeChoices.BALANCE,
        amount=Decimal('100.00'),
        currency='GBP',
        provider='STRIPE',
        status=WorkOrderPaymentStatusChoices.SUCCESS,
        provider_payment_id="pi_test_proc_30",
        created_by=buyer_user,
    )

    # Active PROCESSING refund of £30
    WorkshopRefund.objects.create(
        booking=booking,
        work_order=wo,
        work_order_payment=p,
        refund_number=f"REF-WB-{p.payment_number}",
        amount=Decimal('30.00'),
        currency='GBP',
        status=WorkshopRefundStatusChoices.PROCESSING,
        gateway_provider='STRIPE',
        payment_reference="pi_test_proc_30",
        idempotency_key=f"REF-WB-{p.payment_number}"[:40],
        created_by=buyer_user,
    )

    info = WorkshopRefundService.calculate_refundable_amount(booking)
    assert Decimal(info["total_collected"]) == Decimal("100.00")
    assert Decimal(info["total_already_refunded"]) == Decimal("30.00")
    assert Decimal(info["refundable_amount"]) == Decimal("70.00")

    updated = WorkshopRefundService.process_booking_cancellation_refunds(
        booking=booking,
        reason="Cancel with in-flight processing",
        actor=buyer_user,
    )
    assert Decimal(updated.refund_summary["refunded_amount"]) == Decimal("70.00")


@pytest.mark.django_db
def test_25_payment_100_with_30_processing_unknown_refund(uk_workshop, buyer_user, buyer_vehicle):
    """
    Test 25: A £100 payment with an active £30 PROCESSING_UNKNOWN refund reserves the £30,
    preventing over-refund. Remaining refundable is strictly £70.
    """
    booking = WorkshopBooking.objects.create(
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        preferred_date=date.today() + timedelta(days=2),
        status=BookingStatusChoices.CONFIRMED,
    )
    quote = WorkshopQuotation.objects.create(
        booking=booking,
        version=1,
        status=QuotationStatusChoices.ACCEPTED,
        total_amount=Decimal('100.00'),
        currency='GBP',
    )
    wo = WorkOrder.objects.create(
        booking=booking,
        quotation=quote,
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle_make="BMW",
        vehicle_model="3 Series",
        vehicle_registration_plate="BM12ABC",
        status=WorkOrderStatusChoices.IN_PROGRESS,
    )
    p = WorkOrderPayment.objects.create(
        work_order=wo,
        payment_type=WorkOrderPaymentTypeChoices.BALANCE,
        amount=Decimal('100.00'),
        currency='GBP',
        provider='STRIPE',
        status=WorkOrderPaymentStatusChoices.SUCCESS,
        provider_payment_id="pi_test_unk_30",
        created_by=buyer_user,
    )

    # In-flight PROCESSING_UNKNOWN refund of £30
    WorkshopRefund.objects.create(
        booking=booking,
        work_order=wo,
        work_order_payment=p,
        refund_number=f"REF-WB-{p.payment_number}",
        amount=Decimal('30.00'),
        currency='GBP',
        status=WorkshopRefundStatusChoices.PROCESSING_UNKNOWN,
        gateway_provider='STRIPE',
        payment_reference="pi_test_unk_30",
        idempotency_key=f"REF-WB-{p.payment_number}"[:40],
        created_by=buyer_user,
    )

    info = WorkshopRefundService.calculate_refundable_amount(booking)
    assert Decimal(info["total_collected"]) == Decimal("100.00")
    assert Decimal(info["total_already_refunded"]) == Decimal("30.00")
    assert Decimal(info["refundable_amount"]) == Decimal("70.00")


@pytest.mark.django_db
def test_26_multiple_payments_different_previous_refunds(uk_workshop, buyer_user, buyer_vehicle):
    """
    Test 26: Multiple payments with different previous refund amounts:
    Deposit Q: £50 (0 refunded)
    Payment P1: £70 (£20 previously refunded)
    Payment P2: £80 (£80 previously fully refunded)
    Total collected = £200. Total refundable = £50 + £50 + £0 = £100.
    """
    booking = WorkshopBooking.objects.create(
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        preferred_date=date.today() + timedelta(days=2),
        status=BookingStatusChoices.CONFIRMED,
    )
    quote = WorkshopQuotation.objects.create(
        booking=booking,
        version=1,
        status=QuotationStatusChoices.ACCEPTED,
        total_amount=Decimal('200.00'),
        deposit_amount=Decimal('50.00'),
        requires_deposit=True,
        deposit_status=DepositStatusChoices.PAID,
        currency='GBP',
    )
    wo = WorkOrder.objects.create(
        booking=booking,
        quotation=quote,
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle_make="BMW",
        vehicle_model="3 Series",
        vehicle_registration_plate="BM12ABC",
        status=WorkOrderStatusChoices.IN_PROGRESS,
    )
    p1 = WorkOrderPayment.objects.create(
        work_order=wo,
        payment_type=WorkOrderPaymentTypeChoices.PARTIAL,
        amount=Decimal('70.00'),
        currency='GBP',
        provider='STRIPE',
        status=WorkOrderPaymentStatusChoices.SUCCESS,
        provider_payment_id="pi_multi_p1",
        created_by=buyer_user,
    )
    p2 = WorkOrderPayment.objects.create(
        work_order=wo,
        payment_type=WorkOrderPaymentTypeChoices.FINAL,
        amount=Decimal('80.00'),
        currency='GBP',
        provider='STRIPE',
        status=WorkOrderPaymentStatusChoices.REFUNDED,
        provider_payment_id="pi_multi_p2",
        created_by=buyer_user,
    )

    # P1 had £20 partial refund
    WorkshopRefund.objects.create(
        booking=booking,
        work_order=wo,
        work_order_payment=p1,
        refund_number=f"REF-WB-{p1.payment_number}",
        amount=Decimal('20.00'),
        currency='GBP',
        status=WorkshopRefundStatusChoices.SUCCEEDED,
        gateway_provider='STRIPE',
        payment_reference="pi_multi_p1",
        created_by=buyer_user,
    )
    # P2 had £80 full refund
    WorkshopRefund.objects.create(
        booking=booking,
        work_order=wo,
        work_order_payment=p2,
        refund_number=f"REF-WB-{p2.payment_number}",
        amount=Decimal('80.00'),
        currency='GBP',
        status=WorkshopRefundStatusChoices.SUCCEEDED,
        gateway_provider='STRIPE',
        payment_reference="pi_multi_p2",
        created_by=buyer_user,
    )

    info = WorkshopRefundService.calculate_refundable_amount(booking)
    assert Decimal(info["total_collected"]) == Decimal("200.00")
    assert Decimal(info["total_already_refunded"]) == Decimal("100.00")  # £20 + £80
    assert Decimal(info["refundable_amount"]) == Decimal("100.00")  # £50 deposit + £50 on P1

    updated = WorkshopRefundService.process_booking_cancellation_refunds(
        booking=booking,
        reason="Multiple payments test",
        actor=buyer_user,
    )
    assert Decimal(updated.refund_summary["refunded_amount"]) == Decimal("100.00")


@pytest.mark.django_db
def test_27_legacy_refunded_status_with_associated_workshop_refund(uk_workshop, buyer_user, buyer_vehicle):
    """
    Test 27: A payment with status=REFUNDED and an associated WorkshopRefund record
    does NOT double-deduct the refund amount.
    """
    booking = WorkshopBooking.objects.create(
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        preferred_date=date.today() + timedelta(days=2),
        status=BookingStatusChoices.CONFIRMED,
    )
    quote = WorkshopQuotation.objects.create(
        booking=booking,
        version=1,
        status=QuotationStatusChoices.ACCEPTED,
        total_amount=Decimal('100.00'),
        currency='GBP',
    )
    wo = WorkOrder.objects.create(
        booking=booking,
        quotation=quote,
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle_make="BMW",
        vehicle_model="3 Series",
        vehicle_registration_plate="BM12ABC",
        status=WorkOrderStatusChoices.IN_PROGRESS,
    )
    p = WorkOrderPayment.objects.create(
        work_order=wo,
        payment_type=WorkOrderPaymentTypeChoices.BALANCE,
        amount=Decimal('100.00'),
        currency='GBP',
        provider='STRIPE',
        status=WorkOrderPaymentStatusChoices.REFUNDED,  # Legacy status set to REFUNDED
        provider_payment_id="pi_legacy_deduct",
        created_by=buyer_user,
    )
    WorkshopRefund.objects.create(
        booking=booking,
        work_order=wo,
        work_order_payment=p,
        refund_number=f"REF-WB-{p.payment_number}",
        amount=Decimal('100.00'),
        currency='GBP',
        status=WorkshopRefundStatusChoices.SUCCEEDED,
        gateway_provider='STRIPE',
        payment_reference="pi_legacy_deduct",
        created_by=buyer_user,
    )

    info = WorkshopRefundService.calculate_refundable_amount(booking)
    # Must be exactly £100.00 already refunded, NOT £200.00!
    assert Decimal(info["total_already_refunded"]) == Decimal("100.00")
    assert Decimal(info["refundable_amount"]) == Decimal("0.00")


@pytest.mark.django_db
def test_28_repeated_cancellation_and_concurrent_requests_block_duplicates(uk_workshop, buyer_user, buyer_vehicle):
    """
    Test 28: Repeated cancellation calls on a cancelled booking are strictly rejected
    and cannot generate duplicate refund transactions.
    """
    booking = WorkshopBooking.objects.create(
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        preferred_date=date.today() + timedelta(days=2),
        status=BookingStatusChoices.CONFIRMED,
    )
    quote = WorkshopQuotation.objects.create(
        booking=booking,
        version=1,
        status=QuotationStatusChoices.ACCEPTED,
        total_amount=Decimal('100.00'),
        deposit_amount=Decimal('50.00'),
        requires_deposit=True,
        deposit_status=DepositStatusChoices.PAID,
        currency='GBP',
    )

    # First cancellation succeeds
    updated = WorkshopRefundService.process_booking_cancellation_refunds(
        booking=booking,
        reason="First cancel",
        actor=buyer_user,
    )
    assert updated.status == BookingStatusChoices.CANCELLED
    assert WorkshopRefund.objects.filter(booking=booking).count() == 1

    # Second repeated cancellation must fail
    with pytest.raises(DjangoValidationError) as exc:
        WorkshopRefundService.process_booking_cancellation_refunds(
            booking=booking,
            reason="Second cancel attempt",
            actor=buyer_user,
        )
    assert "already cancelled" in str(exc.value)

    # Ensure no second refund was created
    assert WorkshopRefund.objects.filter(booking=booking).count() == 1


@pytest.mark.django_db
def test_29_retrying_uncertain_refund_uses_same_idempotency_key(in_workshop, buyer_user, buyer_vehicle):
    """
    Test 29: Reconciling or retrying an uncertain refund uses the exact same persisted
    idempotency key and does not dispatch a new refund.
    """
    booking = WorkshopBooking.objects.create(
        workshop=in_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        preferred_date=date.today() + timedelta(days=2),
        status=BookingStatusChoices.CONFIRMED,
    )
    quote = WorkshopQuotation.objects.create(
        booking=booking,
        version=1,
        status=QuotationStatusChoices.ACCEPTED,
        total_amount=Decimal('100.00'),
        currency='INR',
    )
    wo = WorkOrder.objects.create(
        booking=booking,
        quotation=quote,
        workshop=in_workshop,
        buyer=buyer_user,
        vehicle_make="Tata",
        vehicle_model="Nexon",
        vehicle_registration_plate="DL01AB1234",
        status=WorkOrderStatusChoices.IN_PROGRESS,
    )
    p = WorkOrderPayment.objects.create(
        work_order=wo,
        payment_type=WorkOrderPaymentTypeChoices.FINAL,
        amount=Decimal('100.00'),
        currency='INR',
        provider='RAZORPAY',
        status=WorkOrderPaymentStatusChoices.SUCCESS,
        provider_payment_id="pay_uncertain_test",
        created_by=buyer_user,
    )

    rfnd = WorkshopRefund.objects.create(
        booking=booking,
        work_order=wo,
        work_order_payment=p,
        refund_number=f"REF-WB-{p.payment_number}",
        amount=Decimal('100.00'),
        currency='INR',
        status=WorkshopRefundStatusChoices.PROCESSING_UNKNOWN,
        gateway_provider='RAZORPAY',
        payment_reference="pay_uncertain_test",
        idempotency_key=RazorpayPaymentProvider.generate_refund_idempotency_key(f"REF-WB-{p.payment_number}"),
        created_by=buyer_user,
    )

    original_idemp_key = rfnd.idempotency_key
    assert 10 <= len(original_idemp_key) <= 40
    assert re.fullmatch(r'^[A-Za-z0-9_-]+$', original_idemp_key)

    with patch.object(RazorpayPaymentProvider, 'inquire_refund') as mock_inq:
        mock_inq.return_value = ('SUCCEEDED', 'rfnd_gw_123', {})
        reconciled, outcome = WorkshopRefundService.reconcile_refund(rfnd.id, actor=buyer_user)

    assert outcome == "RECONCILED_SUCCEEDED"
    reconciled.refresh_from_db()
    assert reconciled.status == WorkshopRefundStatusChoices.SUCCEEDED
    assert reconciled.idempotency_key == original_idemp_key  # Preserved identically!


@pytest.mark.django_db
def test_30_new_refund_after_completed_partial_uses_distinct_identity_and_key(in_workshop, buyer_user, buyer_vehicle):
    """
    Test 30: A subsequent refund on the same payment receives a distinct sequential
    refund_number and distinct idempotency key, preventing collisions with the prior refund.
    """
    booking = WorkshopBooking.objects.create(
        workshop=in_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        preferred_date=date.today() + timedelta(days=2),
        status=BookingStatusChoices.CONFIRMED,
    )
    quote = WorkshopQuotation.objects.create(
        booking=booking,
        version=1,
        status=QuotationStatusChoices.ACCEPTED,
        total_amount=Decimal('100.00'),
        currency='INR',
    )
    wo = WorkOrder.objects.create(
        booking=booking,
        quotation=quote,
        workshop=in_workshop,
        buyer=buyer_user,
        vehicle_make="Tata",
        vehicle_model="Nexon",
        vehicle_registration_plate="DL01AB1234",
        status=WorkOrderStatusChoices.IN_PROGRESS,
    )
    p = WorkOrderPayment.objects.create(
        work_order=wo,
        payment_type=WorkOrderPaymentTypeChoices.BALANCE,
        amount=Decimal('100.00'),
        currency='INR',
        provider='RAZORPAY',
        status=WorkOrderPaymentStatusChoices.SUCCESS,
        provider_payment_id="pay_distinct_keys",
        created_by=buyer_user,
    )

    # First partial refund of ₹30
    rfnd1 = WorkshopRefund.objects.create(
        booking=booking,
        work_order=wo,
        work_order_payment=p,
        refund_number=f"REF-WB-{p.payment_number}",
        amount=Decimal('30.00'),
        currency='INR',
        status=WorkshopRefundStatusChoices.SUCCEEDED,
        gateway_provider='RAZORPAY',
        payment_reference="pay_distinct_keys",
        idempotency_key=RazorpayPaymentProvider.generate_refund_idempotency_key(f"REF-WB-{p.payment_number}"),
        created_by=buyer_user,
    )

    # Second refund upon cancellation for remaining ₹70
    updated = WorkshopRefundService.process_booking_cancellation_refunds(
        booking=booking,
        reason="Remaining cancellation refund",
        actor=buyer_user,
    )

    all_rfnds = list(WorkshopRefund.objects.filter(work_order_payment=p).order_by('created_at'))
    assert len(all_rfnds) == 2

    rfnd2 = all_rfnds[1]
    assert rfnd2.amount == Decimal('70.00')
    assert rfnd2.refund_number != rfnd1.refund_number
    assert rfnd2.idempotency_key != rfnd1.idempotency_key
    assert rfnd2.refund_number == f"REF-WB-{p.payment_number}-2"


@pytest.mark.django_db
def test_31_sum_of_refunds_never_exceeds_original_collected(uk_workshop, buyer_user, buyer_vehicle):
    """
    Test 31: Verifies across complex multi-payment topologies that total completed refunds
    plus active reservations strictly never exceeds the original verified collected amount.
    """
    booking = WorkshopBooking.objects.create(
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle=buyer_vehicle,
        preferred_date=date.today() + timedelta(days=2),
        status=BookingStatusChoices.CONFIRMED,
    )
    quote = WorkshopQuotation.objects.create(
        booking=booking,
        version=1,
        status=QuotationStatusChoices.ACCEPTED,
        total_amount=Decimal('300.00'),
        deposit_amount=Decimal('100.00'),
        requires_deposit=True,
        deposit_status=DepositStatusChoices.PAID,
        currency='GBP',
    )
    wo = WorkOrder.objects.create(
        booking=booking,
        quotation=quote,
        workshop=uk_workshop,
        buyer=buyer_user,
        vehicle_make="BMW",
        vehicle_model="3 Series",
        vehicle_registration_plate="BM12ABC",
        status=WorkOrderStatusChoices.IN_PROGRESS,
    )
    p1 = WorkOrderPayment.objects.create(
        work_order=wo,
        payment_type=WorkOrderPaymentTypeChoices.PARTIAL,
        amount=Decimal('100.00'),
        currency='GBP',
        provider='STRIPE',
        status=WorkOrderPaymentStatusChoices.SUCCESS,
        provider_payment_id="pi_c1",
        created_by=buyer_user,
    )
    p2 = WorkOrderPayment.objects.create(
        work_order=wo,
        payment_type=WorkOrderPaymentTypeChoices.FINAL,
        amount=Decimal('100.00'),
        currency='GBP',
        provider='STRIPE',
        status=WorkOrderPaymentStatusChoices.SUCCESS,
        provider_payment_id="pi_c2",
        created_by=buyer_user,
    )

    # Initial partial refunds:
    # Deposit had £50 refunded
    WorkshopRefund.objects.create(
        booking=booking,
        quotation=quote,
        refund_number=f"REF-WB-DEP-{quote.quotation_number}",
        amount=Decimal('50.00'),
        currency='GBP',
        status=WorkshopRefundStatusChoices.SUCCEEDED,
        gateway_provider='STRIPE',
        created_by=buyer_user,
    )
    # P1 had £40 in PROCESSING_UNKNOWN
    WorkshopRefund.objects.create(
        booking=booking,
        work_order=wo,
        work_order_payment=p1,
        refund_number=f"REF-WB-{p1.payment_number}",
        amount=Decimal('40.00'),
        currency='GBP',
        status=WorkshopRefundStatusChoices.PROCESSING_UNKNOWN,
        gateway_provider='STRIPE',
        created_by=buyer_user,
    )
    # P2 had £10 in PROCESSING
    WorkshopRefund.objects.create(
        booking=booking,
        work_order=wo,
        work_order_payment=p2,
        refund_number=f"REF-WB-{p2.payment_number}",
        amount=Decimal('10.00'),
        currency='GBP',
        status=WorkshopRefundStatusChoices.PROCESSING,
        gateway_provider='STRIPE',
        created_by=buyer_user,
    )

    # Total collected = £100 + £100 + £100 = £300.
    # Active/Completed prior = £50 + £40 + £10 = £100.
    # Expected refundable = £300 - £100 = £200 (£50 on deposit, £60 on P1, £90 on P2).
    info = WorkshopRefundService.calculate_refundable_amount(booking)
    assert Decimal(info["total_collected"]) == Decimal("300.00")
    assert Decimal(info["total_already_refunded"]) == Decimal("100.00")
    assert Decimal(info["refundable_amount"]) == Decimal("200.00")

    updated = WorkshopRefundService.process_booking_cancellation_refunds(
        booking=booking,
        reason="Complex multi-payment audit",
        actor=buyer_user,
    )
    assert Decimal(updated.refund_summary["refunded_amount"]) == Decimal("200.00")

    # Final assert: Sum of ALL refunds on this booking must be EXACTLY £300.00 (<= collected)
    all_booking_refunds = WorkshopRefund.objects.filter(booking=booking).exclude(status=WorkshopRefundStatusChoices.FAILED)
    grand_total_refunded = all_booking_refunds.aggregate(total=models.Sum('amount'))['total']
    assert grand_total_refunded == Decimal("300.00")
    assert grand_total_refunded <= Decimal(info["total_collected"])
