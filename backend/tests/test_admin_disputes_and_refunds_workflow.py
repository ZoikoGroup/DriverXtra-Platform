import uuid
from decimal import Decimal
import pytest
from rest_framework import status
from rest_framework.test import APIClient
from django.core.exceptions import ValidationError as DjangoValidationError

from apps.identity.models import User, RoleChoices, StaffRole, StaffProfile, Permission, StaffRolePermission
from apps.marketplace.models import (
    Order,
    OrderItem,
    PaymentStatusChoices,
    CODCollectionStatusChoices,
    ReturnRequest,
    ReturnRequestTypeChoices,
    ReturnRequestStatusChoices,
    ReturnReasonChoices,
    Refund,
    RefundStatusChoices,
    RefundMethodChoices,
    VehicleOrder,
    VehicleListing,
    ListingStatusChoices,
    VehicleOrderStatusChoices,
)
from apps.marketplace.returns.service import ReturnService, RefundService
from apps.marketplace.serializers import ReturnRequestReviewPayloadSerializer


@pytest.fixture
def buyer_user(db):
    user = User.objects.create_user(
        email=f"buyer_{uuid.uuid4().hex[:6]}@example.com",
        password="SecurePassword123!",
        first_name="Alice",
        last_name="Buyer",
        phone_number="+447000000001",
        is_email_verified=True,
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.fixture
def seller_user(db):
    user = User.objects.create_user(
        email=f"seller_{uuid.uuid4().hex[:6]}@example.com",
        password="SecurePassword123!",
        first_name="Sam",
        last_name="Seller",
        phone_number="+447000000002",
        is_email_verified=True,
    )
    user.add_role(RoleChoices.SELLER)
    return user


@pytest.fixture
def dispute_manager_user(db):
    user = User.objects.create_user(
        email=f"dispute_mgr_{uuid.uuid4().hex[:6]}@driverxtra.com",
        password="SecurePassword123!",
        first_name="Diane",
        last_name="Mediator",
        is_staff=True,
        is_email_verified=True,
    )
    user.add_role(RoleChoices.STAFF)
    role, _ = StaffRole.objects.get_or_create(code="DISPUTE_MANAGER", defaults={"name": "Dispute Manager"})
    # Ensure role has dispute.manage and order.refund permissions
    p_disp, _ = Permission.objects.get_or_create(code="dispute.manage", defaults={"name": "Manage Disputes", "module": "marketplace"})
    p_ref, _ = Permission.objects.get_or_create(code="order.refund", defaults={"name": "Create Refunds", "module": "marketplace"})
    StaffRolePermission.objects.get_or_create(staff_role=role, permission=p_disp)
    StaffRolePermission.objects.get_or_create(staff_role=role, permission=p_ref)

    profile, _ = StaffProfile.objects.get_or_create(user=user)
    profile.staff_role = role
    profile.save()
    return user


@pytest.fixture
def finance_officer_user(db):
    user = User.objects.create_user(
        email=f"finance_off_{uuid.uuid4().hex[:6]}@driverxtra.com",
        password="SecurePassword123!",
        first_name="Fiona",
        last_name="Treasurer",
        is_staff=True,
        is_email_verified=True,
    )
    user.add_role(RoleChoices.STAFF)
    role, _ = StaffRole.objects.get_or_create(code="FINANCE_OFFICER", defaults={"name": "Finance Officer"})
    p_payout, _ = Permission.objects.get_or_create(code="finance.payout", defaults={"name": "Execute Payouts", "module": "finance"})
    p_ref, _ = Permission.objects.get_or_create(code="order.refund", defaults={"name": "Create Refunds", "module": "marketplace"})
    StaffRolePermission.objects.get_or_create(staff_role=role, permission=p_payout)
    StaffRolePermission.objects.get_or_create(staff_role=role, permission=p_ref)

    profile, _ = StaffProfile.objects.get_or_create(user=user)
    profile.staff_role = role
    profile.save()
    return user


@pytest.fixture
def paid_spare_part_order(db, buyer_user):
    order = Order.objects.create(
        buyer=buyer_user,
        order_number=f"ORD-{uuid.uuid4().hex[:8].upper()}",
        total_amount=Decimal("250.00"),
        subtotal_taxable_amount=Decimal("200.00"),
        total_tax_amount=Decimal("50.00"),
        currency="GBP",
        shipping_country="GB",
        payment_method="ONLINE",
        payment_status=PaymentStatusChoices.PAID,
        payment_reference="pi_test_stripe_12345",
    )
    OrderItem.objects.create(
        order=order,
        title="Alternator Assembly",
        unit_price=Decimal("200.00"),
        quantity=1,
        taxable_amount=Decimal("200.00"),
        tax_amount=Decimal("50.00"),
        total_amount=Decimal("250.00"),
    )
    return order


@pytest.fixture
def pending_spare_part_order(db, buyer_user):
    return Order.objects.create(
        buyer=buyer_user,
        order_number=f"ORD-{uuid.uuid4().hex[:8].upper()}",
        total_amount=Decimal("150.00"),
        subtotal_taxable_amount=Decimal("120.00"),
        total_tax_amount=Decimal("30.00"),
        currency="GBP",
        shipping_country="GB",
        payment_method="ONLINE",
        payment_status=PaymentStatusChoices.PENDING,
    )


@pytest.fixture
def uncollected_cod_order(db, buyer_user):
    return Order.objects.create(
        buyer=buyer_user,
        order_number=f"ORD-{uuid.uuid4().hex[:8].upper()}",
        total_amount=Decimal("300.00"),
        subtotal_taxable_amount=Decimal("250.00"),
        total_tax_amount=Decimal("50.00"),
        currency="GBP",
        shipping_country="GB",
        payment_method="COD",
        payment_status=PaymentStatusChoices.PENDING,
        cod_collection_status=CODCollectionStatusChoices.PENDING,
    )


@pytest.mark.django_db
def test_refund_summary_finite_calculation_and_keys(paid_spare_part_order):
    """Verifies all numeric fields are finite numbers and canonical keys are present."""
    summary = RefundService.get_order_refund_summary(paid_spare_part_order)

    assert summary["order_number"] == paid_spare_part_order.order_number
    assert summary["currency"] == "GBP"
    assert summary["total_amount"] == Decimal("250.00")
    assert summary["paid_amount"] == Decimal("250.00")
    assert summary["active_refunded_amount"] == Decimal("0.00")
    assert summary["available_refundable_balance"] == Decimal("250.00")
    assert summary["can_refund"] is True
    assert summary["reason_ineligible"] is None

    # Legacy keys
    assert summary["order_total"] == Decimal("250.00")
    assert summary["total_refunded"] == Decimal("0.00")
    assert summary["available_refundable"] == Decimal("250.00")
    assert summary["is_paid"] is True


@pytest.mark.django_db
def test_refund_summary_pending_payment_ineligibility(pending_spare_part_order):
    """Verifies that an order with PENDING payment is marked ineligible with clear explanation."""
    summary = RefundService.get_order_refund_summary(pending_spare_part_order)

    assert summary["can_refund"] is False
    assert summary["paid_amount"] == Decimal("0.00")
    assert summary["available_refundable_balance"] == Decimal("0.00")
    assert summary["reason_ineligible"] == "Payment is still PENDING. No collected funds are available to refund."


@pytest.mark.django_db
def test_refund_summary_uncollected_cod_ineligibility(uncollected_cod_order):
    """Verifies that uncollected Cash on Delivery order is ineligible for refund."""
    summary = RefundService.get_order_refund_summary(uncollected_cod_order)

    assert summary["is_cod"] is True
    assert summary["is_cod_collected"] is False
    assert summary["can_refund"] is False
    assert summary["paid_amount"] == Decimal("0.00")
    assert summary["reason_ineligible"] == "Cash on Delivery payment has not been marked as COLLECTED."


@pytest.mark.django_db
def test_refund_summary_fully_refunded_ineligibility(paid_spare_part_order, dispute_manager_user):
    """Verifies that a fully refunded order has 0 balance and is ineligible for further refunds."""
    RefundService.create_refund(
        order=paid_spare_part_order,
        amount=Decimal("250.00"),
        reason="Full return refund",
        actor=dispute_manager_user,
    )

    summary = RefundService.get_order_refund_summary(paid_spare_part_order)
    assert summary["active_refunded_amount"] == Decimal("250.00")
    assert summary["available_refundable_balance"] == Decimal("0.00")
    assert summary["can_refund"] is False
    assert summary["reason_ineligible"] == "No remaining refundable balance. The order has already been fully refunded."


@pytest.mark.django_db
def test_seller_rejection_requires_mandatory_reason(paid_spare_part_order, buyer_user, seller_user):
    """Ensures seller cannot reject a return request without a documented rejection reason."""
    item = paid_spare_part_order.items.first()
    return_req = ReturnRequest.objects.create(
        request_number=f"RET-{uuid.uuid4().hex[:8].upper()}",
        order=paid_spare_part_order,
        order_item=item,
        buyer=buyer_user,
        seller=seller_user,
        request_type=ReturnRequestTypeChoices.RETURN,
        status=ReturnRequestStatusChoices.PENDING,
        reason=ReturnReasonChoices.DEFECTIVE_ITEM,
        description="Defective item",
    )

    # 1. Serializer validation
    serializer = ReturnRequestReviewPayloadSerializer(data={"action": "REJECT", "rejection_reason": ""})
    assert not serializer.is_valid()
    assert "rejection_reason" in serializer.errors

    serializer_spaces = ReturnRequestReviewPayloadSerializer(data={"action": "REJECT", "rejection_reason": "   "})
    assert not serializer_spaces.is_valid()
    assert "rejection_reason" in serializer_spaces.errors

    # 2. Service layer validation
    with pytest.raises(DjangoValidationError) as exc:
        ReturnService.review_return_request(
            return_request=return_req,
            actor=seller_user,
            action="REJECT",
            rejection_reason="   ",
        )
    assert "mandatory" in str(exc.value).lower()

    # Successful documented rejection
    updated = ReturnService.review_return_request(
        return_request=return_req,
        actor=seller_user,
        action="REJECT",
        rejection_reason="Part shows clear evidence of improper external tampering.",
    )
    assert updated.status == ReturnRequestStatusChoices.REJECTED
    assert updated.rejection_reason == "Part shows clear evidence of improper external tampering."


@pytest.mark.django_db
def test_vehicle_order_separation_from_spare_parts_refund(dispute_manager_user):
    """Ensures VehicleOrder identifiers are rejected by spare-part refund views and service."""
    vo_number = f"VO-{uuid.uuid4().hex[:8].upper()}"

    client = APIClient()
    client.force_authenticate(user=dispute_manager_user)

    # 1. GET refund summary for vehicle order
    res = client.get(f"/api/v1/marketplace/orders/{vo_number}/refund-summary/")
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "Vehicle orders use offline direct payment" in res.data["error"]
    assert res.data.get("is_vehicle_order") is True

    # 2. POST refund create for vehicle order
    res_post = client.post(
        f"/api/v1/marketplace/admin/orders/{vo_number}/refund/",
        {"amount": "500.00", "reason": "Customer cancellation"},
        format="json",
    )
    assert res_post.status_code == status.HTTP_400_BAD_REQUEST
    assert "Vehicle orders use offline direct payment" in res_post.data["error"]
    assert res_post.data.get("is_vehicle_order") is True

    # 3. Service layer rejection check
    dummy_vo = type("MockVehicleOrder", (), {
        "order_number": vo_number,
        "vehicle": True,
        "currency": "GBP",
    })()
    with pytest.raises(DjangoValidationError) as exc:
        RefundService.create_refund(
            order=dummy_vo,
            amount=Decimal("500.00"),
            reason="Test",
            actor=dispute_manager_user,
        )
    assert "Vehicle orders use offline direct payment" in str(exc.value)


@pytest.mark.django_db
def test_refund_amount_bounds_and_finite_validation(paid_spare_part_order, dispute_manager_user):
    """Verifies that create_refund rejects non-positive, non-finite, and excess amounts."""
    # Zero amount
    with pytest.raises(DjangoValidationError) as exc:
        RefundService.create_refund(
            order=paid_spare_part_order,
            amount=Decimal("0.00"),
            reason="Zero refund",
            actor=dispute_manager_user,
        )
    assert "greater than zero" in str(exc.value).lower()

    # Exceeding balance
    with pytest.raises(DjangoValidationError) as exc:
        RefundService.create_refund(
            order=paid_spare_part_order,
            amount=Decimal("300.00"),
            reason="Excessive refund",
            actor=dispute_manager_user,
        )
    assert "exceeds maximum available refundable balance" in str(exc.value).lower()


@pytest.mark.django_db
def test_staff_without_finance_payout_cannot_auto_settle(paid_spare_part_order, dispute_manager_user, finance_officer_user):
    """
    Verifies role separation:
    Dispute Manager (with order.refund) can approve a refund, transitioning it to PROCESSING.
    Finance Officer (with finance.payout) settles the refund.
    """
    refund = RefundService.create_refund(
        order=paid_spare_part_order,
        amount=Decimal("50.00"),
        reason="Goodwill partial refund",
        actor=dispute_manager_user,
        refund_method=RefundMethodChoices.BANK_TRANSFER,
    )
    assert refund.status == RefundStatusChoices.PENDING

    # Dispute Manager approves refund -> transitions to PROCESSING (not settled)
    approved = RefundService.approve_refund(
        refund=refund,
        actor=dispute_manager_user,
        notes="Dispute manager approved goodwill amount",
    )
    assert approved.status == RefundStatusChoices.PROCESSING

    # Finance Officer settles refund -> transitions to SUCCEEDED
    settled = RefundService.process_refund(
        refund=approved,
        actor=finance_officer_user,
        gateway_reference="UTR-BANK-202611-123",
        notes="Bank transfer disbursed",
    )
    assert settled.status == RefundStatusChoices.SUCCEEDED
    assert settled.gateway_refund_id == "UTR-BANK-202611-123"

