import uuid
from decimal import Decimal
from datetime import timedelta
import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from django.core.exceptions import ValidationError as DjangoValidationError

from apps.identity.models import User, RoleChoices, StaffRole, StaffProfile
from apps.catalogue.models import PartCategory
from apps.marketplace.models import (
    Order,
    OrderItem,
    OrderStatusChoices,
    PaymentMethodChoices,
    PaymentStatusChoices,
    CODCollectionStatusChoices,
    SparePartListing,
    ListingStatusChoices,
    Shipment,
    ShipmentItem,
    ShipmentStatusChoices,
    ReturnRequest,
    ReturnRequestTypeChoices,
    ReturnRequestStatusChoices,
    ReturnReasonChoices,
    Refund,
    RefundStatusChoices,
    RefundMethodChoices,
    Dispute,
    DisputeCategoryChoices,
    DisputeStatusChoices,
    DisputeResolutionChoices,
    DisputePriorityChoices,
)
from apps.marketplace.returns.service import (
    ReturnService,
    RefundService,
    DisputeService,
)


@pytest.fixture
def brake_category(db):
    return PartCategory.objects.create(name="Braking Systems", slug="braking-systems")


@pytest.fixture
def seller_b(db):
    user = User.objects.create_user(
        email='seller_b@driverxtra.com',
        password='SecurePassword123!',
        first_name='Bob',
        last_name='Seller',
        phone_number='+447000000022',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.SELLER)
    return user


@pytest.fixture
def seller_b_client(seller_b):
    client = APIClient()
    client.force_authenticate(user=seller_b)
    return client


@pytest.fixture
def unrelated_buyer(db):
    user = User.objects.create_user(
        email='unrelated_buyer@driverxtra.com',
        password='SecurePassword123!',
        first_name='Eve',
        last_name='Intruder',
        phone_number='+447000000033',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.fixture
def unrelated_buyer_client(unrelated_buyer):
    client = APIClient()
    client.force_authenticate(user=unrelated_buyer)
    return client


@pytest.fixture
def dispute_manager_user(db):
    user = User.objects.create_user(
        email='dispute_mgr@driverxtra.com',
        password='SecurePassword123!',
        first_name='Diane',
        last_name='Mediator',
        is_staff=True,
        is_email_verified=True,
    )
    user.add_role(RoleChoices.STAFF)
    role = StaffRole.objects.filter(code='DISPUTE_MANAGER').first()
    if role:
        profile, _ = StaffProfile.objects.get_or_create(user=user)
        profile.staff_role = role
        profile.save()
    return user


@pytest.fixture
def dispute_manager_client(dispute_manager_user):
    client = APIClient()
    client.force_authenticate(user=dispute_manager_user)
    return client


@pytest.fixture
def sample_paid_order(db, buyer_user, seller_user, brake_category):
    listing = SparePartListing.objects.create(
        seller=seller_user,
        name="Front Brake Pads",
        brand="Brembo",
        mpn="BP-001",
        category=brake_category,
        price=Decimal("1000.00"),
        currency="INR",
        hsn_code="8708",
        gst_rate=Decimal("18.00"),
        status=ListingStatusChoices.APPROVED,
        is_active=True,
        stock_quantity=50,
    )
    order = Order.objects.create(
        buyer=buyer_user,
        order_number=f"ORD-TEST-{uuid.uuid4().hex[:6].upper()}",
        status=OrderStatusChoices.CONFIRMED,
        payment_method=PaymentMethodChoices.ONLINE,
        payment_status=PaymentStatusChoices.PAID,
        paid_at=timezone.now(),
        currency="INR",
        subtotal_taxable_amount=Decimal("1000.00"),
        cgst_amount=Decimal("90.00"),
        sgst_amount=Decimal("90.00"),
        igst_amount=Decimal("0.00"),
        total_tax_amount=Decimal("180.00"),
        total_amount=Decimal("1180.00"),
        shipping_country="India",
    )
    item = OrderItem.objects.create(
        order=order,
        listing=listing,
        title="Front Brake Pads",
        brand="Brembo",
        unit_price=Decimal("1000.00"),
        quantity=1,
        taxable_amount=Decimal("1000.00"),
        cgst_amount=Decimal("90.00"),
        sgst_amount=Decimal("90.00"),
        igst_amount=Decimal("0.00"),
        tax_amount=Decimal("180.00"),
        total_amount=Decimal("1180.00"),
    )
    return order, item


@pytest.fixture
def sample_delivered_order(db, buyer_user, seller_user, brake_category):
    listing = SparePartListing.objects.create(
        seller=seller_user,
        name="Rear Brake Rotors",
        brand="Bosch",
        mpn="RR-002",
        category=brake_category,
        price=Decimal("2000.00"),
        currency="INR",
        hsn_code="8708",
        gst_rate=Decimal("18.00"),
        status=ListingStatusChoices.APPROVED,
        is_active=True,
        stock_quantity=30,
    )
    order = Order.objects.create(
        buyer=buyer_user,
        order_number=f"ORD-DELIV-{uuid.uuid4().hex[:6].upper()}",
        status=OrderStatusChoices.COMPLETED,
        payment_method=PaymentMethodChoices.ONLINE,
        payment_status=PaymentStatusChoices.PAID,
        paid_at=timezone.now(),
        currency="INR",
        subtotal_taxable_amount=Decimal("2000.00"),
        cgst_amount=Decimal("180.00"),
        sgst_amount=Decimal("180.00"),
        igst_amount=Decimal("0.00"),
        total_tax_amount=Decimal("360.00"),
        total_amount=Decimal("2360.00"),
        shipping_country="India",
    )
    item = OrderItem.objects.create(
        order=order,
        listing=listing,
        title="Rear Brake Rotors",
        brand="Bosch",
        unit_price=Decimal("2000.00"),
        quantity=1,
        taxable_amount=Decimal("2000.00"),
        cgst_amount=Decimal("180.00"),
        sgst_amount=Decimal("180.00"),
        igst_amount=Decimal("0.00"),
        tax_amount=Decimal("360.00"),
        total_amount=Decimal("2360.00"),
    )
    shipment = Shipment.objects.create(
        order=order,
        seller=seller_user,
        shipment_number=f"SHP-DELIV-{uuid.uuid4().hex[:6].upper()}",
        status=ShipmentStatusChoices.DELIVERED,
        dispatched_at=timezone.now() - timedelta(days=2),
        delivered_at=timezone.now() - timedelta(days=1),
    )
    ShipmentItem.objects.create(shipment=shipment, order_item=item, quantity=1)
    return order, item, shipment


# =============================================================================
# 1. RETURNS & CANCELLATIONS SERVICE TESTS
# =============================================================================

@pytest.mark.django_db
def test_buyer_cancellation_eligibility_and_creation_before_dispatch(sample_paid_order, buyer_user):
    order, item = sample_paid_order

    eligible, reason, amount = ReturnService.get_cancellation_eligibility(order, buyer_user, item)
    assert eligible is True
    assert amount == item.total_amount

    # Create cancellation request
    req = ReturnService.create_return_request(
        order=order,
        buyer=buyer_user,
        request_type=ReturnRequestTypeChoices.CANCELLATION,
        reason=ReturnReasonChoices.BUYER_CANCEL,
        description="Bought wrong variant by accident.",
        order_item=item,
        requested_quantity=1,
    )
    assert req.request_number.startswith("RET-")
    assert req.status == ReturnRequestStatusChoices.PENDING
    assert req.request_type == ReturnRequestTypeChoices.CANCELLATION
    assert req.refund_amount == Decimal("1180.00")


@pytest.mark.django_db
def test_buyer_cannot_cancel_after_shipment_dispatched(sample_paid_order, buyer_user, seller_user):
    order, item = sample_paid_order

    # Create dispatched shipment
    shipment = Shipment.objects.create(
        order=order,
        seller=seller_user,
        shipment_number=f"SHP-{uuid.uuid4().hex[:6].upper()}",
        status=ShipmentStatusChoices.DISPATCHED,
        dispatched_at=timezone.now(),
    )
    ShipmentItem.objects.create(shipment=shipment, order_item=item, quantity=1)

    eligible, reason, _ = ReturnService.get_cancellation_eligibility(order, buyer_user, item)
    assert eligible is False
    assert "already been dispatched" in reason

    with pytest.raises(DjangoValidationError) as exc:
        ReturnService.create_return_request(
            order=order,
            buyer=buyer_user,
            request_type=ReturnRequestTypeChoices.CANCELLATION,
            reason=ReturnReasonChoices.BUYER_CANCEL,
            description="Trying to cancel dispatched order.",
            order_item=item,
        )
    assert "already been dispatched" in str(exc.value)


@pytest.mark.django_db
def test_buyer_return_eligibility_and_creation_after_delivery(sample_delivered_order, buyer_user):
    order, item, _ = sample_delivered_order

    eligible, reason, amount = ReturnService.get_return_eligibility(order, buyer_user, item)
    assert eligible is True
    assert amount == item.total_amount

    req = ReturnService.create_return_request(
        order=order,
        buyer=buyer_user,
        request_type=ReturnRequestTypeChoices.RETURN,
        reason=ReturnReasonChoices.DEFECTIVE_ITEM,
        description="Rotor surface has manufacturing cracks.",
        evidence_urls=["/media/uploads/parts/2026/10/defect.jpg"],
        order_item=item,
        requested_quantity=1,
    )
    assert req.status == ReturnRequestStatusChoices.PENDING
    assert req.request_type == ReturnRequestTypeChoices.RETURN
    assert len(req.evidence_urls) == 1


@pytest.mark.django_db
def test_buyer_cannot_return_undelivered_order(sample_paid_order, buyer_user):
    order, item = sample_paid_order

    eligible, reason, _ = ReturnService.get_return_eligibility(order, buyer_user, item)
    assert eligible is False
    assert "not been marked as delivered" in reason

    with pytest.raises(DjangoValidationError) as exc:
        ReturnService.create_return_request(
            order=order,
            buyer=buyer_user,
            request_type=ReturnRequestTypeChoices.RETURN,
            reason=ReturnReasonChoices.NOT_AS_DESCRIBED,
            description="Item not received yet but want return",
            order_item=item,
        )
    assert "not been marked as delivered" in str(exc.value)


@pytest.mark.django_db
def test_duplicate_open_return_request_prevented(sample_delivered_order, buyer_user):
    order, item, _ = sample_delivered_order

    # First request
    ReturnService.create_return_request(
        order=order,
        buyer=buyer_user,
        request_type=ReturnRequestTypeChoices.RETURN,
        reason=ReturnReasonChoices.DEFECTIVE_ITEM,
        description="First return attempt",
        order_item=item,
    )

    # Second concurrent request must be rejected
    with pytest.raises(DjangoValidationError) as exc:
        ReturnService.create_return_request(
            order=order,
            buyer=buyer_user,
            request_type=ReturnRequestTypeChoices.RETURN,
            reason=ReturnReasonChoices.DEFECTIVE_ITEM,
            description="Duplicate attempt",
            order_item=item,
        )
    assert "already in progress" in str(exc.value)


@pytest.mark.django_db
def test_seller_review_approve_and_cancellation_restocks_inventory(sample_paid_order, buyer_user, seller_user):
    order, item = sample_paid_order
    initial_stock = item.listing.stock_quantity

    req = ReturnService.create_return_request(
        order=order,
        buyer=buyer_user,
        request_type=ReturnRequestTypeChoices.CANCELLATION,
        reason=ReturnReasonChoices.BUYER_CANCEL,
        description="Mistake order",
        order_item=item,
    )

    reviewed = ReturnService.review_return_request(
        return_request=req,
        actor=seller_user,
        action="APPROVE",
        seller_notes="Cancellation approved by seller.",
    )
    assert reviewed.status == ReturnRequestStatusChoices.COMPLETED
    assert reviewed.completed_at is not None

    # Stock was automatically incremented back
    item.listing.refresh_from_db()
    assert item.listing.stock_quantity == initial_stock + 1


@pytest.mark.django_db
def test_seller_review_reject_records_reason(sample_delivered_order, buyer_user, seller_user):
    order, item, _ = sample_delivered_order

    req = ReturnService.create_return_request(
        order=order,
        buyer=buyer_user,
        request_type=ReturnRequestTypeChoices.RETURN,
        reason=ReturnReasonChoices.BUYER_CANCEL,
        description="Changed mind after using part",
        order_item=item,
    )

    rejected = ReturnService.review_return_request(
        return_request=req,
        actor=seller_user,
        action="REJECT",
        rejection_reason="Item opened and installed, return rejected.",
    )
    assert rejected.status == ReturnRequestStatusChoices.REJECTED
    assert "opened and installed" in rejected.rejection_reason


@pytest.mark.django_db
def test_seller_complete_return_restocks_inventory(sample_delivered_order, buyer_user, seller_user):
    order, item, _ = sample_delivered_order
    initial_stock = item.listing.stock_quantity

    req = ReturnService.create_return_request(
        order=order,
        buyer=buyer_user,
        request_type=ReturnRequestTypeChoices.RETURN,
        reason=ReturnReasonChoices.DEFECTIVE_ITEM,
        description="Faulty part",
        order_item=item,
    )

    # Seller approves return (item in transit back to seller)
    approved = ReturnService.review_return_request(
        return_request=req,
        actor=seller_user,
        action="APPROVE",
        seller_notes="Please ship item to our return hub.",
    )
    assert approved.status == ReturnRequestStatusChoices.APPROVED

    # Once physical item is received at warehouse
    completed = ReturnService.complete_return_request(
        return_request=approved,
        actor=seller_user,
        notes="Package received and inspected.",
    )
    assert completed.status == ReturnRequestStatusChoices.COMPLETED

    item.listing.refresh_from_db()
    assert item.listing.stock_quantity == initial_stock + 1


@pytest.mark.django_db
def test_unrelated_seller_cannot_review_or_complete_return(sample_delivered_order, buyer_user, seller_b):
    order, item, _ = sample_delivered_order

    req = ReturnService.create_return_request(
        order=order,
        buyer=buyer_user,
        request_type=ReturnRequestTypeChoices.RETURN,
        reason=ReturnReasonChoices.DEFECTIVE_ITEM,
        description="Faulty part",
        order_item=item,
    )

    with pytest.raises(DjangoValidationError) as exc:
        ReturnService.review_return_request(
            return_request=req,
            actor=seller_b,  # seller_b is not the seller of item
            action="APPROVE",
        )
    assert "Permission denied" in str(exc.value)


@pytest.mark.django_db
def test_buyer_can_withdraw_pending_request(sample_delivered_order, buyer_user):
    order, item, _ = sample_delivered_order

    req = ReturnService.create_return_request(
        order=order,
        buyer=buyer_user,
        request_type=ReturnRequestTypeChoices.RETURN,
        reason=ReturnReasonChoices.DEFECTIVE_ITEM,
        description="Mistake filed",
        order_item=item,
    )
    assert req.status == ReturnRequestStatusChoices.PENDING

    withdrawn = ReturnService.cancel_return_request_by_buyer(req, buyer_user)
    assert withdrawn.status == ReturnRequestStatusChoices.CANCELLED


# =============================================================================
# 2. REFUND MANAGEMENT TESTS
# =============================================================================

@pytest.mark.django_db
def test_order_refund_summary_calculation(sample_paid_order):
    order, _ = sample_paid_order

    summary = RefundService.get_order_refund_summary(order)
    assert summary["is_paid"] is True
    assert summary["paid_amount"] == Decimal("1180.00")
    assert summary["total_refunded"] == Decimal("0.00")
    assert summary["available_refundable"] == Decimal("1180.00")
    assert summary["can_refund"] is True


@pytest.mark.django_db
def test_refund_amount_cannot_exceed_available_paid_balance(sample_paid_order, admin_user):
    order, _ = sample_paid_order

    # Attempting to refund more than paid total (1180.00)
    with pytest.raises(DjangoValidationError) as exc:
        RefundService.create_refund(
            order=order,
            amount=Decimal("1500.00"),
            reason="Over-refund attempt",
            actor=admin_user,
        )
    assert "exceeds maximum available refundable balance" in str(exc.value)


@pytest.mark.django_db
def test_uncollected_cod_order_cannot_be_refunded(db, buyer_user, seller_user, brake_category, admin_user):
    listing = SparePartListing.objects.create(
        seller=seller_user,
        name="Clutch Kit",
        brand="Valeo",
        category=brake_category,
        price=Decimal("3000.00"),
        currency="INR",
        hsn_code="8708",
        gst_rate=Decimal("18.00"),
        status=ListingStatusChoices.APPROVED,
        is_active=True,
    )
    order = Order.objects.create(
        buyer=buyer_user,
        order_number=f"ORD-COD-PENDING-{uuid.uuid4().hex[:6].upper()}",
        status=OrderStatusChoices.CONFIRMED,
        payment_method=PaymentMethodChoices.COD,
        payment_status=PaymentStatusChoices.PENDING,
        cod_collection_status=CODCollectionStatusChoices.PENDING,
        currency="INR",
        subtotal_taxable_amount=Decimal("3000.00"),
        cgst_amount=Decimal("270.00"),
        sgst_amount=Decimal("270.00"),
        igst_amount=Decimal("0.00"),
        total_tax_amount=Decimal("540.00"),
        total_amount=Decimal("3540.00"),
    )

    with pytest.raises(DjangoValidationError) as exc:
        RefundService.create_refund(
            order=order,
            amount=Decimal("1000.00"),
            reason="Refund attempt on uncollected COD",
            actor=admin_user,
        )
    assert "payment has not been collected" in str(exc.value)


@pytest.mark.django_db
def test_collected_cod_order_can_be_refunded(db, buyer_user, seller_user, brake_category, admin_user):
    listing = SparePartListing.objects.create(
        seller=seller_user,
        name="Clutch Kit",
        brand="Valeo",
        category=brake_category,
        price=Decimal("3000.00"),
        currency="INR",
        hsn_code="8708",
        gst_rate=Decimal("18.00"),
        status=ListingStatusChoices.APPROVED,
        is_active=True,
    )
    order = Order.objects.create(
        buyer=buyer_user,
        order_number=f"ORD-COD-PAID-{uuid.uuid4().hex[:6].upper()}",
        status=OrderStatusChoices.COMPLETED,
        payment_method=PaymentMethodChoices.COD,
        payment_status=PaymentStatusChoices.PAID,
        cod_collection_status=CODCollectionStatusChoices.COLLECTED,
        cod_collected_at=timezone.now(),
        currency="INR",
        subtotal_taxable_amount=Decimal("3000.00"),
        cgst_amount=Decimal("270.00"),
        sgst_amount=Decimal("270.00"),
        igst_amount=Decimal("0.00"),
        total_tax_amount=Decimal("540.00"),
        total_amount=Decimal("3540.00"),
    )

    refund = RefundService.create_refund(
        order=order,
        amount=Decimal("3540.00"),
        reason="Defective part on collected COD order",
        actor=admin_user,
        refund_method=RefundMethodChoices.BANK_TRANSFER,
        auto_process=True,
    )
    assert refund.status == RefundStatusChoices.SUCCEEDED
    assert refund.refund_method == RefundMethodChoices.BANK_TRANSFER

    order.refresh_from_db()
    assert order.payment_status == PaymentStatusChoices.REFUNDED


@pytest.mark.django_db
def test_process_refund_updates_order_to_refunded_on_full_refund(sample_paid_order, admin_user):
    order, _ = sample_paid_order

    # Partial refund 500
    r1 = RefundService.create_refund(
        order=order,
        amount=Decimal("500.00"),
        reason="Partial goodwill gesture",
        actor=admin_user,
    )
    RefundService.process_refund(r1, admin_user, gateway_reference="re_123")
    order.refresh_from_db()
    assert order.payment_status == PaymentStatusChoices.PAID  # Still partially unrefunded

    # Remaining refund 680
    r2 = RefundService.create_refund(
        order=order,
        amount=Decimal("680.00"),
        reason="Remaining refund",
        actor=admin_user,
    )
    RefundService.process_refund(r2, admin_user, gateway_reference="re_456")
    order.refresh_from_db()
    # Now order is fully refunded
    assert order.payment_status == PaymentStatusChoices.REFUNDED


@pytest.mark.django_db
def test_non_staff_cannot_issue_refund(sample_paid_order, buyer_user, seller_user):
    order, _ = sample_paid_order

    with pytest.raises(DjangoValidationError) as exc:
        RefundService.create_refund(
            order=order,
            amount=Decimal("100.00"),
            reason="Buyer cannot refund himself",
            actor=buyer_user,
        )
    assert "Permission denied" in str(exc.value)

    with pytest.raises(DjangoValidationError) as exc2:
        RefundService.create_refund(
            order=order,
            amount=Decimal("100.00"),
            reason="Seller without order.refund cannot issue refund",
            actor=seller_user,
        )
    assert "Permission denied" in str(exc2.value)


# =============================================================================
# 3. DISPUTE MANAGEMENT TESTS
# =============================================================================

@pytest.mark.django_db
def test_buyer_creates_dispute_and_duplicate_open_prevented(sample_delivered_order, buyer_user):
    order, _, _ = sample_delivered_order

    dispute = DisputeService.create_dispute(
        order=order,
        buyer=buyer_user,
        category=DisputeCategoryChoices.DAMAGED_OR_DEFECTIVE,
        description="The package arrived severely damaged and items broken.",
        evidence_urls=["/media/uploads/parts/2026/10/box_broken.jpg"],
        priority=DisputePriorityChoices.HIGH,
    )
    assert dispute.dispute_number.startswith("DISP-")
    assert dispute.status == DisputeStatusChoices.OPEN
    assert dispute.priority == DisputePriorityChoices.HIGH
    assert dispute.events.count() == 1

    # Attempt second duplicate dispute
    with pytest.raises(DjangoValidationError) as exc:
        DisputeService.create_dispute(
            order=order,
            buyer=buyer_user,
            category=DisputeCategoryChoices.ITEM_NOT_RECEIVED,
            description="Second dispute while first is active",
        )
    assert "already open" in str(exc.value)


@pytest.mark.django_db
def test_dispute_messaging_thread_access_control(sample_delivered_order, buyer_user, seller_user, unrelated_buyer, dispute_manager_user):
    order, _, _ = sample_delivered_order

    dispute = DisputeService.create_dispute(
        order=order,
        buyer=buyer_user,
        category=DisputeCategoryChoices.DAMAGED_OR_DEFECTIVE,
        description="Broken item",
    )

    # Buyer posts reply
    evt_b = DisputeService.add_dispute_message(dispute, buyer_user, "Here is additional photos of the damage.")
    assert evt_b.actor == buyer_user

    # Seller posts reply
    evt_s = DisputeService.add_dispute_message(dispute, seller_user, "We packed it securely, we are checking with carrier.")
    assert evt_s.actor == seller_user

    # Dispute manager posts mediation guidance
    evt_m = DisputeService.add_dispute_message(dispute, dispute_manager_user, "Staff reviewing courier transit report.")
    assert evt_m.actor == dispute_manager_user

    # Unrelated third-party rejected
    with pytest.raises(DjangoValidationError) as exc:
        DisputeService.add_dispute_message(dispute, unrelated_buyer, "Spam message from random user")
    assert "Permission denied" in str(exc.value)


@pytest.mark.django_db
def test_dispute_status_update_and_decision_recording_by_dispute_manager(sample_delivered_order, buyer_user, dispute_manager_user):
    order, _, _ = sample_delivered_order

    dispute = DisputeService.create_dispute(
        order=order,
        buyer=buyer_user,
        category=DisputeCategoryChoices.DAMAGED_OR_DEFECTIVE,
        description="Broken item",
    )

    # Move to UNDER_REVIEW
    updated = DisputeService.update_dispute_status(
        dispute=dispute,
        actor=dispute_manager_user,
        new_status=DisputeStatusChoices.UNDER_REVIEW,
        resolution_notes="Assigning case to logistics audit.",
    )
    assert updated.status == DisputeStatusChoices.UNDER_REVIEW

    # Adjudicate and resolve in favor of buyer with refund
    resolved = DisputeService.update_dispute_status(
        dispute=dispute,
        actor=dispute_manager_user,
        new_status=DisputeStatusChoices.RESOLVED,
        resolution=DisputeResolutionChoices.REFUND_ISSUED,
        resolution_notes="Transit damage confirmed by carrier report. Full refund approved.",
    )
    assert resolved.status == DisputeStatusChoices.RESOLVED
    assert resolved.resolution == DisputeResolutionChoices.REFUND_ISSUED
    assert resolved.resolved_by == dispute_manager_user


@pytest.mark.django_db
def test_unauthorized_user_cannot_update_dispute_status(sample_delivered_order, buyer_user, seller_user):
    order, _, _ = sample_delivered_order

    dispute = DisputeService.create_dispute(
        order=order,
        buyer=buyer_user,
        category=DisputeCategoryChoices.DAMAGED_OR_DEFECTIVE,
        description="Broken item",
    )

    # Buyer cannot resolve own dispute
    with pytest.raises(DjangoValidationError) as exc:
        DisputeService.update_dispute_status(dispute, buyer_user, DisputeStatusChoices.RESOLVED)
    assert "Permission denied" in str(exc.value)

    # Seller cannot dismiss dispute unilaterally
    with pytest.raises(DjangoValidationError) as exc2:
        DisputeService.update_dispute_status(dispute, seller_user, DisputeStatusChoices.REJECTED)
    assert "Permission denied" in str(exc2.value)


# =============================================================================
# 4. REST API ENDPOINT INTEGRATION TESTS
# =============================================================================

@pytest.mark.django_db
def test_rest_api_buyer_seller_admin_return_and_dispute_lifecycle(
    sample_delivered_order,
    buyer_auth_client,
    seller_auth_client,
    dispute_manager_client,
    unrelated_buyer_client,
):
    order, item, _ = sample_delivered_order

    # 1. Buyer checks return eligibility API
    elig_res = buyer_auth_client.get(f"/api/v1/marketplace/buyer/orders/{order.id}/return-eligibility/")
    assert elig_res.status_code == status.HTTP_200_OK
    assert elig_res.data["order_return"]["eligible"] is True

    # 2. Buyer creates return request API
    create_req_res = buyer_auth_client.post(
        f"/api/v1/marketplace/buyer/orders/{order.id}/returns/",
        {
            "order_item_id": str(item.id),
            "request_type": "RETURN",
            "reason": "DEFECTIVE_ITEM",
            "description": "Item cracked on arrival",
            "requested_quantity": 1,
        },
        format="json",
    )
    assert create_req_res.status_code == status.HTTP_201_CREATED
    req_number = create_req_res.data["return_request"]["request_number"]

    # 3. Seller lists returns -> sees this return request
    seller_returns_res = seller_auth_client.get("/api/v1/marketplace/seller/returns/")
    assert seller_returns_res.status_code == status.HTTP_200_OK
    assert any(r["request_number"] == req_number for r in seller_returns_res.data["results"] if isinstance(seller_returns_res.data, dict) and "results" in seller_returns_res.data) or any(r["request_number"] == req_number for r in (seller_returns_res.data if isinstance(seller_returns_res.data, list) else []))

    # 4. Seller approves return request API
    review_res = seller_auth_client.post(
        f"/api/v1/marketplace/seller/returns/{req_number}/review/",
        {"action": "APPROVE", "seller_notes": "Return authorized, ship back."},
        format="json",
    )
    assert review_res.status_code == status.HTTP_200_OK
    assert review_res.data["return_request"]["status"] == "APPROVED"

    # 5. Buyer raises commercial dispute API
    dispute_res = buyer_auth_client.post(
        f"/api/v1/marketplace/buyer/orders/{order.id}/disputes/",
        {
            "category": "DAMAGED_OR_DEFECTIVE",
            "description": "Seller is delaying return label generation.",
            "priority": "HIGH",
        },
        format="json",
    )
    assert dispute_res.status_code == status.HTTP_201_CREATED
    disp_num = dispute_res.data["dispute"]["dispute_number"]

    # 6. Unrelated buyer rejected from viewing dispute API
    unauth_disp_res = unrelated_buyer_client.get(f"/api/v1/marketplace/disputes/{disp_num}/")
    assert unauth_disp_res.status_code == status.HTTP_403_FORBIDDEN

    # 7. Dispute manager posts message to dispute API
    msg_res = dispute_manager_client.post(
        f"/api/v1/marketplace/disputes/{disp_num}/messages/",
        {"message": "Mediator stepping in: reviewing return request status."},
        format="json",
    )
    assert msg_res.status_code == status.HTTP_201_CREATED

    # 8. Dispute manager adjudicates dispute API
    status_update_res = dispute_manager_client.post(
        f"/api/v1/marketplace/admin/disputes/{disp_num}/status/",
        {
            "status": "RESOLVED",
            "resolution": "REFUND_ISSUED",
            "resolution_notes": "Dispute resolved with full refund.",
        },
        format="json",
    )
    assert status_update_res.status_code == status.HTTP_200_OK
    assert status_update_res.data["dispute"]["status"] == "RESOLVED"

    # 9. Dispute manager issues full refund API
    refund_res = dispute_manager_client.post(
        f"/api/v1/marketplace/admin/orders/{order.id}/refund/",
        {
            "amount": "2360.00",
            "reason": "Mediated dispute refund resolution",
            "dispute_id": str(dispute_res.data["dispute"]["id"]),
            "auto_process": True,
        },
        format="json",
    )
    assert refund_res.status_code == status.HTTP_201_CREATED
    assert refund_res.data["refund"]["status"] == "SUCCEEDED"

    # Order is now completely REFUNDED
    order.refresh_from_db()
    assert order.payment_status == PaymentStatusChoices.REFUNDED
