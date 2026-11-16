import uuid
from decimal import Decimal
from datetime import timedelta
import pytest
from rest_framework import status
from rest_framework.test import APIClient
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone

from apps.identity.models import User, RoleChoices, StaffRole, StaffProfile, Permission, StaffRolePermission
from apps.catalogue.models import PartCategory, VehicleMake, VehicleModel, FuelTypeChoices, TransmissionChoices
from apps.marketplace.models import (
    Order,
    OrderItem,
    PaymentStatusChoices,
    OrderStatusChoices,
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
    VehicleOrder,
    VehicleListing,
    VehicleOrderStatusChoices,
    VehiclePurchaseOffer,
    VehicleOfferStatusChoices,
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
def buyer_alice(db):
    user = User.objects.create_user(
        email=f"buyer_alice_{uuid.uuid4().hex[:6]}@example.com",
        password="SecurePassword123!",
        first_name="Alice",
        last_name="Buyer",
        phone_number="+447000000001",
        is_email_verified=True,
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.fixture
def buyer_alice_client(buyer_alice):
    client = APIClient()
    client.force_authenticate(user=buyer_alice)
    return client


@pytest.fixture
def buyer_eve(db):
    user = User.objects.create_user(
        email=f"buyer_eve_{uuid.uuid4().hex[:6]}@example.com",
        password="SecurePassword123!",
        first_name="Eve",
        last_name="Intruder",
        phone_number="+447000000002",
        is_email_verified=True,
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.fixture
def buyer_eve_client(buyer_eve):
    client = APIClient()
    client.force_authenticate(user=buyer_eve)
    return client


@pytest.fixture
def seller_sam(db):
    user = User.objects.create_user(
        email=f"seller_sam_{uuid.uuid4().hex[:6]}@example.com",
        password="SecurePassword123!",
        first_name="Sam",
        last_name="Seller",
        phone_number="+447000000003",
        is_email_verified=True,
    )
    user.add_role(RoleChoices.SELLER)
    return user


@pytest.fixture
def seller_sam_client(seller_sam):
    client = APIClient()
    client.force_authenticate(user=seller_sam)
    return client


@pytest.fixture
def seller_bob(db):
    user = User.objects.create_user(
        email=f"seller_bob_{uuid.uuid4().hex[:6]}@example.com",
        password="SecurePassword123!",
        first_name="Bob",
        last_name="Vendor",
        phone_number="+447000000004",
        is_email_verified=True,
    )
    user.add_role(RoleChoices.SELLER)
    return user


@pytest.fixture
def seller_bob_client(seller_bob):
    client = APIClient()
    client.force_authenticate(user=seller_bob)
    return client


@pytest.fixture
def dispute_manager_staff(db):
    user = User.objects.create_user(
        email=f"disp_mgr_{uuid.uuid4().hex[:6]}@driverxtra.com",
        password="SecurePassword123!",
        first_name="Diane",
        last_name="Mediator",
        is_staff=True,
        is_email_verified=True,
    )
    user.add_role(RoleChoices.STAFF)
    role, _ = StaffRole.objects.get_or_create(code="DISPUTE_MANAGER", defaults={"name": "Dispute Manager"})
    p_disp, _ = Permission.objects.get_or_create(code="dispute.manage", defaults={"name": "Manage Disputes", "module": "marketplace"})
    p_ref, _ = Permission.objects.get_or_create(code="order.refund", defaults={"name": "Create Refunds", "module": "marketplace"})
    StaffRolePermission.objects.get_or_create(staff_role=role, permission=p_disp)
    StaffRolePermission.objects.get_or_create(staff_role=role, permission=p_ref)

    profile, _ = StaffProfile.objects.get_or_create(user=user)
    profile.staff_role = role
    profile.save()
    return user


@pytest.fixture
def dispute_manager_client(dispute_manager_staff):
    client = APIClient()
    client.force_authenticate(user=dispute_manager_staff)
    return client


@pytest.fixture
def finance_officer_staff(db):
    user = User.objects.create_user(
        email=f"finance_{uuid.uuid4().hex[:6]}@driverxtra.com",
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
def finance_officer_client(finance_officer_staff):
    client = APIClient()
    client.force_authenticate(user=finance_officer_staff)
    return client


@pytest.fixture
def general_support_staff(db):
    user = User.objects.create_user(
        email=f"support_{uuid.uuid4().hex[:6]}@driverxtra.com",
        password="SecurePassword123!",
        first_name="Stan",
        last_name="Support",
        is_staff=True,
        is_email_verified=True,
    )
    user.add_role(RoleChoices.STAFF)
    role, _ = StaffRole.objects.get_or_create(code="SUPPORT_AGENT", defaults={"name": "Support Agent"})
    p_tick, _ = Permission.objects.get_or_create(code="support.ticket.manage", defaults={"name": "Manage Tickets", "module": "support"})
    StaffRolePermission.objects.get_or_create(staff_role=role, permission=p_tick)

    profile, _ = StaffProfile.objects.get_or_create(user=user)
    profile.staff_role = role
    profile.save()
    return user


@pytest.fixture
def general_support_client(general_support_staff):
    client = APIClient()
    client.force_authenticate(user=general_support_staff)
    return client


@pytest.fixture
def sam_listing(db, seller_sam, brake_category):
    return SparePartListing.objects.create(
        seller=seller_sam,
        category=brake_category,
        name="Ceramic Front Brake Pads (Sam)",
        brand="Brembo",
        mpn="BP-SAM-01",
        price=Decimal("100.00"),
        stock_quantity=20,
        status=ListingStatusChoices.APPROVED,
        is_active=True,
    )


@pytest.fixture
def bob_listing(db, seller_bob, brake_category):
    return SparePartListing.objects.create(
        seller=seller_bob,
        category=brake_category,
        name="Ceramic Front Brake Pads (Bob)",
        brand="Brembo",
        mpn="BP-BOB-01",
        price=Decimal("150.00"),
        stock_quantity=15,
        status=ListingStatusChoices.APPROVED,
        is_active=True,
    )


@pytest.fixture
def alice_delivered_order_sam(db, buyer_alice, seller_sam, sam_listing):
    order = Order.objects.create(
        buyer=buyer_alice,
        order_number=f"ORD-{uuid.uuid4().hex[:8].upper()}",
        total_amount=Decimal("200.00"),
        subtotal_taxable_amount=Decimal("160.00"),
        cgst_amount=Decimal("20.00"),
        sgst_amount=Decimal("20.00"),
        igst_amount=Decimal("0.00"),
        total_tax_amount=Decimal("40.00"),
        currency="INR",
        shipping_country="IN",
        payment_method="ONLINE",
        payment_status=PaymentStatusChoices.PAID,
        paid_at=timezone.now(),
        status=OrderStatusChoices.COMPLETED,
    )
    order_item = OrderItem.objects.create(
        order=order,
        listing=sam_listing,
        title="Ceramic Front Brake Pads (Sam)",
        brand="Brembo",
        quantity=2,
        unit_price=Decimal("100.00"),
        taxable_amount=Decimal("160.00"),
        cgst_amount=Decimal("20.00"),
        sgst_amount=Decimal("20.00"),
        igst_amount=Decimal("0.00"),
        tax_amount=Decimal("40.00"),
        total_amount=Decimal("200.00"),
    )
    shipment = Shipment.objects.create(
        order=order,
        seller=seller_sam,
        shipment_number=f"SHP-DELIV-{uuid.uuid4().hex[:6].upper()}",
        status=ShipmentStatusChoices.DELIVERED,
        dispatched_at=timezone.now() - timedelta(days=2),
        delivered_at=timezone.now() - timedelta(days=1),
    )
    ShipmentItem.objects.create(shipment=shipment, order_item=order_item, quantity=2)
    return order, order_item


@pytest.fixture
def alice_cod_uncollected_order(db, buyer_alice, sam_listing):
    order = Order.objects.create(
        buyer=buyer_alice,
        order_number=f"ORD-COD-{uuid.uuid4().hex[:8].upper()}",
        total_amount=Decimal("100.00"),
        subtotal_taxable_amount=Decimal("80.00"),
        cgst_amount=Decimal("10.00"),
        sgst_amount=Decimal("10.00"),
        igst_amount=Decimal("0.00"),
        total_tax_amount=Decimal("20.00"),
        currency="INR",
        shipping_country="IN",
        payment_method="COD",
        payment_status=PaymentStatusChoices.PENDING,
        cod_collection_status=CODCollectionStatusChoices.PENDING,
        status=OrderStatusChoices.PROCESSING,
    )
    order_item = OrderItem.objects.create(
        order=order,
        listing=sam_listing,
        title="Ceramic Front Brake Pads (Sam)",
        brand="Brembo",
        quantity=1,
        unit_price=Decimal("100.00"),
        taxable_amount=Decimal("80.00"),
        cgst_amount=Decimal("10.00"),
        sgst_amount=Decimal("10.00"),
        igst_amount=Decimal("0.00"),
        tax_amount=Decimal("20.00"),
        total_amount=Decimal("100.00"),
    )
    return order, order_item


@pytest.fixture
def alice_cod_collected_order(db, buyer_alice, seller_sam, sam_listing):
    order = Order.objects.create(
        buyer=buyer_alice,
        order_number=f"ORD-COD-COL-{uuid.uuid4().hex[:8].upper()}",
        total_amount=Decimal("100.00"),
        subtotal_taxable_amount=Decimal("80.00"),
        cgst_amount=Decimal("10.00"),
        sgst_amount=Decimal("10.00"),
        igst_amount=Decimal("0.00"),
        total_tax_amount=Decimal("20.00"),
        currency="INR",
        shipping_country="IN",
        payment_method="COD",
        payment_status=PaymentStatusChoices.PAID,
        paid_at=timezone.now(),
        cod_collection_status=CODCollectionStatusChoices.COLLECTED,
        status=OrderStatusChoices.COMPLETED,
    )
    order_item = OrderItem.objects.create(
        order=order,
        listing=sam_listing,
        title="Ceramic Front Brake Pads (Sam)",
        brand="Brembo",
        quantity=1,
        unit_price=Decimal("100.00"),
        taxable_amount=Decimal("80.00"),
        cgst_amount=Decimal("10.00"),
        sgst_amount=Decimal("10.00"),
        igst_amount=Decimal("0.00"),
        tax_amount=Decimal("20.00"),
        total_amount=Decimal("100.00"),
    )
    shipment = Shipment.objects.create(
        order=order,
        seller=seller_sam,
        shipment_number=f"SHP-COD-{uuid.uuid4().hex[:6].upper()}",
        status=ShipmentStatusChoices.DELIVERED,
        dispatched_at=timezone.now() - timedelta(days=2),
        delivered_at=timezone.now() - timedelta(days=1),
    )
    ShipmentItem.objects.create(shipment=shipment, order_item=order_item, quantity=1)
    return order, order_item


# =============================================================================
# SCENARIOS 1-3: BUYER RETURNS, TRACKING, AND ACCESS ISOLATION
# =============================================================================

def test_buyer_submits_return_request_success(buyer_alice_client, alice_delivered_order_sam):
    order, order_item = alice_delivered_order_sam
    url = f"/api/v1/marketplace/buyer/orders/{order.id}/returns/"
    payload = {
        "order_item_id": str(order_item.id),
        "request_type": "RETURN",
        "reason": "DEFECTIVE_ITEM",
        "description": "Brake pads have uneven friction surface and crack on corner.",
        "requested_quantity": 2,
        "evidence_urls": ["https://driverxtra.com/media/evidence_pad_crack.jpg"],
    }
    resp = buyer_alice_client.post(url, payload, format="json")
    assert resp.status_code == status.HTTP_201_CREATED
    data = resp.json()
    assert data["status"] == "success"
    assert data["return_request"]["status"] == "PENDING"
    assert data["return_request"]["reason"] == "DEFECTIVE_ITEM"
    assert Decimal(str(data["return_request"]["refund_amount"])) == Decimal("200.00")


def test_buyer_cannot_return_other_buyer_order(buyer_eve_client, alice_delivered_order_sam):
    order, order_item = alice_delivered_order_sam
    url = f"/api/v1/marketplace/buyer/orders/{order.id}/returns/"
    payload = {
        "order_item_id": str(order_item.id),
        "request_type": "RETURN",
        "reason": "DEFECTIVE_ITEM",
        "description": "Attempting to return another buyer's goods",
    }
    resp = buyer_eve_client.post(url, payload, format="json")
    assert resp.status_code == status.HTTP_403_FORBIDDEN


def test_buyer_tracks_return_and_withdrawal(buyer_alice_client, alice_delivered_order_sam, buyer_alice):
    order, order_item = alice_delivered_order_sam
    req = ReturnService.create_return_request(
        order=order,
        buyer=buyer_alice,
        request_type=ReturnRequestTypeChoices.RETURN,
        reason=ReturnReasonChoices.DEFECTIVE_ITEM,
        description="Buyer tracking test",
        order_item=order_item,
        requested_quantity=1,
    )
    # List
    list_resp = buyer_alice_client.get("/api/v1/marketplace/buyer/returns/")
    assert list_resp.status_code == status.HTTP_200_OK
    results = list_resp.json()
    items = results if isinstance(results, list) else results.get("results", [])
    assert any(r["request_number"] == req.request_number for r in items)

    # Withdraw
    withdraw_url = f"/api/v1/marketplace/buyer/returns/{req.request_number}/cancel/"
    with_resp = buyer_alice_client.post(withdraw_url, format="json")
    assert with_resp.status_code == status.HTTP_200_OK
    req.refresh_from_db()
    assert req.status == ReturnRequestStatusChoices.CANCELLED


# =============================================================================
# SCENARIOS 4-9: SELLER RESPONSIBILITY, REVIEW, MANDATORY REASON, AND RESTOCK
# =============================================================================

def test_seller_receives_returns_for_own_items_only(seller_sam_client, seller_bob_client, alice_delivered_order_sam, buyer_alice):
    order, order_item = alice_delivered_order_sam
    req = ReturnService.create_return_request(
        order=order,
        buyer=buyer_alice,
        request_type=ReturnRequestTypeChoices.RETURN,
        reason=ReturnReasonChoices.DEFECTIVE_ITEM,
        description="Test seller isolation",
        order_item=order_item,
    )

    # Sam sees it
    sam_resp = seller_sam_client.get("/api/v1/marketplace/seller/returns/")
    assert sam_resp.status_code == status.HTTP_200_OK
    sam_items = sam_resp.json() if isinstance(sam_resp.json(), list) else sam_resp.json().get("results", [])
    assert any(r["request_number"] == req.request_number for r in sam_items)

    # Bob (different seller) does NOT see it
    bob_resp = seller_bob_client.get("/api/v1/marketplace/seller/returns/")
    assert bob_resp.status_code == status.HTTP_200_OK
    bob_items = bob_resp.json() if isinstance(bob_resp.json(), list) else bob_resp.json().get("results", [])
    assert not any(r["request_number"] == req.request_number for r in bob_items)


def test_seller_bob_cannot_review_seller_sam_return(seller_bob_client, alice_delivered_order_sam, buyer_alice):
    order, order_item = alice_delivered_order_sam
    req = ReturnService.create_return_request(
        order=order,
        buyer=buyer_alice,
        request_type=ReturnRequestTypeChoices.RETURN,
        reason=ReturnReasonChoices.DEFECTIVE_ITEM,
        description="Sam's return request",
        order_item=order_item,
    )
    url = f"/api/v1/marketplace/seller/returns/{req.request_number}/review/"
    resp = seller_bob_client.post(url, {"action": "APPROVE"}, format="json")
    assert resp.status_code == status.HTTP_403_FORBIDDEN


def test_seller_approves_cancellation_restocks_inventory(seller_sam_client, buyer_alice, sam_listing):
    # Pre-dispatch cancellation
    initial_stock = sam_listing.stock_quantity
    order = Order.objects.create(
        buyer=buyer_alice,
        order_number=f"ORD-CANC-{uuid.uuid4().hex[:8].upper()}",
        total_amount=Decimal("300.00"),
        subtotal_taxable_amount=Decimal("300.00"),
        cgst_amount=Decimal("0.00"),
        sgst_amount=Decimal("0.00"),
        igst_amount=Decimal("0.00"),
        total_tax_amount=Decimal("0.00"),
        currency="INR",
        shipping_country="IN",
        payment_method="ONLINE",
        payment_status=PaymentStatusChoices.PAID,
        paid_at=timezone.now(),
        status=OrderStatusChoices.PROCESSING,
    )
    order_item = OrderItem.objects.create(
        order=order,
        listing=sam_listing,
        title="Ceramic Front Brake Pads (Sam)",
        brand="Brembo",
        quantity=3,
        unit_price=Decimal("100.00"),
        taxable_amount=Decimal("300.00"),
        cgst_amount=Decimal("0.00"),
        sgst_amount=Decimal("0.00"),
        igst_amount=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("300.00"),
    )
    req = ReturnService.create_return_request(
        order=order,
        buyer=buyer_alice,
        request_type=ReturnRequestTypeChoices.CANCELLATION,
        reason=ReturnReasonChoices.ORDERED_BY_MISTAKE,
        description="Order cancellation before dispatch",
        order_item=order_item,
        requested_quantity=3,
    )

    url = f"/api/v1/marketplace/seller/returns/{req.request_number}/review/"
    resp = seller_sam_client.post(url, {"action": "APPROVE", "seller_notes": "Cancelled and restocked"}, format="json")
    assert resp.status_code == status.HTTP_200_OK

    req.refresh_from_db()
    assert req.status == ReturnRequestStatusChoices.COMPLETED
    sam_listing.refresh_from_db()
    assert sam_listing.stock_quantity == initial_stock + 3


def test_seller_rejects_return_with_mandatory_reason(seller_sam_client, alice_delivered_order_sam, buyer_alice):
    order, order_item = alice_delivered_order_sam
    req = ReturnService.create_return_request(
        order=order,
        buyer=buyer_alice,
        request_type=ReturnRequestTypeChoices.RETURN,
        reason=ReturnReasonChoices.DEFECTIVE_ITEM,
        description="Defective item",
        order_item=order_item,
    )
    url = f"/api/v1/marketplace/seller/returns/{req.request_number}/review/"

    # Rejection without reason fails
    fail_resp = seller_sam_client.post(url, {"action": "REJECT", "rejection_reason": ""}, format="json")
    assert fail_resp.status_code == status.HTTP_400_BAD_REQUEST

    # Rejection with mandatory reason succeeds
    ok_resp = seller_sam_client.post(
        url,
        {"action": "REJECT", "rejection_reason": "Return period expired and seal was broken by customer."},
        format="json",
    )
    assert ok_resp.status_code == status.HTTP_200_OK
    req.refresh_from_db()
    assert req.status == ReturnRequestStatusChoices.REJECTED
    assert "seal was broken" in req.rejection_reason


def test_seller_completes_physical_return_and_restocks(seller_sam_client, alice_delivered_order_sam, buyer_alice, sam_listing):
    order, order_item = alice_delivered_order_sam
    initial_stock = sam_listing.stock_quantity
    req = ReturnService.create_return_request(
        order=order,
        buyer=buyer_alice,
        request_type=ReturnRequestTypeChoices.RETURN,
        reason=ReturnReasonChoices.DEFECTIVE_ITEM,
        description="Goods received return test",
        order_item=order_item,
        requested_quantity=2,
    )
    ReturnService.review_return_request(
        return_request=req,
        actor=sam_listing.seller,
        action="APPROVE",
    )
    req.refresh_from_db()
    assert req.status == ReturnRequestStatusChoices.APPROVED

    # Complete return on receipt
    url = f"/api/v1/marketplace/seller/returns/{req.request_number}/complete/"
    comp_resp = seller_sam_client.post(url, {"notes": "Inspected at warehouse, restocked to shelf A-12"}, format="json")
    assert comp_resp.status_code == status.HTTP_200_OK

    req.refresh_from_db()
    assert req.status == ReturnRequestStatusChoices.COMPLETED
    sam_listing.refresh_from_db()
    assert sam_listing.stock_quantity == initial_stock + 2


# =============================================================================
# SCENARIOS 10-12: SELLER DIRECT REFUND EVIDENCE & SELLER REFUND ISOLATION
# =============================================================================

def test_seller_records_direct_settlement_refund_with_evidence(seller_sam_client, alice_delivered_order_sam, buyer_alice):
    order, order_item = alice_delivered_order_sam
    req = ReturnService.create_return_request(
        order=order,
        buyer=buyer_alice,
        request_type=ReturnRequestTypeChoices.RETURN,
        reason=ReturnReasonChoices.DEFECTIVE_ITEM,
        description="Need direct settlement",
        order_item=order_item,
        requested_quantity=1,
    )
    ReturnService.review_return_request(
        return_request=req,
        actor=order_item.listing.seller,
        action="APPROVE",
    )

    url = f"/api/v1/marketplace/seller/orders/{order.id}/record-refund/"
    payload = {
        "amount": "100.00",
        "transaction_reference": "UTR9876543210123",
        "refund_method": "BANK_TRANSFER",
        "evidence_url": "https://driverxtra.com/media/receipt_wire_100.png",
        "return_request_id": str(req.id),
        "notes": "Direct IMPS wire to customer registered bank account.",
    }
    resp = seller_sam_client.post(url, payload, format="json")
    assert resp.status_code == status.HTTP_201_CREATED
    data = resp.json()
    assert data["status"] == "success"
    # Evidence submitted represents PROCESSING - does not claim buyer received money merely because UTR is submitted
    assert data["refund"]["status"] == "PROCESSING"
    assert data["refund"]["gateway_provider"] == "SELLER_DIRECT"
    assert data["refund"]["gateway_refund_id"] == "UTR9876543210123"

    req.refresh_from_db()
    # Return remains in APPROVED awaiting buyer confirmation of funds receipt
    assert req.status == ReturnRequestStatusChoices.APPROVED
    order.refresh_from_db()
    assert order.payment_status != PaymentStatusChoices.REFUNDED


def test_buyer_confirms_seller_direct_refund_receipt(
    buyer_alice_client,
    buyer_eve_client,
    alice_delivered_order_sam,
    buyer_alice,
):
    order, order_item = alice_delivered_order_sam
    req = ReturnService.create_return_request(
        order=order,
        buyer=buyer_alice,
        request_type=ReturnRequestTypeChoices.RETURN,
        reason=ReturnReasonChoices.DEFECTIVE_ITEM,
        description="Buyer confirmation flow test",
        order_item=order_item,
        requested_quantity=2,
    )
    ReturnService.review_return_request(
        return_request=req,
        actor=order_item.listing.seller,
        action="APPROVE",
    )

    # Seller records direct refund of total order balance
    refund = RefundService.record_seller_direct_refund(
        order=order,
        amount=Decimal("200.00"),
        actor=order_item.listing.seller,
        transaction_reference="UTR-CONFIRM-999",
        return_request=req,
        notes="Full direct wire payout",
    )
    assert refund.status == RefundStatusChoices.PROCESSING

    # Unrelated buyer Eve CANNOT confirm Alice's refund receipt
    eve_resp = buyer_eve_client.post(
        f"/api/v1/marketplace/buyer/refunds/{refund.id}/confirm-receipt/",
        format="json",
    )
    assert eve_resp.status_code == status.HTTP_403_FORBIDDEN

    # Actual buyer Alice confirms receipt
    alice_resp = buyer_alice_client.post(
        f"/api/v1/marketplace/buyer/refunds/{refund.id}/confirm-receipt/",
        format="json",
    )
    assert alice_resp.status_code == status.HTTP_200_OK
    data = alice_resp.json()
    assert data["status"] == "success"
    assert data["refund"]["status"] == "SUCCEEDED"

    refund.refresh_from_db()
    assert refund.status == RefundStatusChoices.SUCCEEDED
    assert refund.processed_at is not None

    req.refresh_from_db()
    assert req.status == ReturnRequestStatusChoices.COMPLETED

    order.refresh_from_db()
    assert order.payment_status == PaymentStatusChoices.REFUNDED


def test_seller_a_cannot_view_seller_b_refunds(seller_sam_client, seller_bob_client, alice_delivered_order_sam):
    order, _ = alice_delivered_order_sam
    # Create a direct refund by Sam
    refund = RefundService.record_seller_direct_refund(
        order=order,
        amount=Decimal("50.00"),
        actor=order.items.first().listing.seller,
        transaction_reference="UTR-SAM-001",
        notes="Sam refund record",
    )

    # Sam sees it in seller refund list
    sam_resp = seller_sam_client.get("/api/v1/marketplace/seller/refunds/")
    assert sam_resp.status_code == status.HTTP_200_OK
    sam_refunds = sam_resp.json() if isinstance(sam_resp.json(), list) else sam_resp.json().get("results", [])
    assert any(r["refund_number"] == refund.refund_number for r in sam_refunds)

    # Bob does NOT see it in seller refund list
    bob_resp = seller_bob_client.get("/api/v1/marketplace/seller/refunds/")
    assert bob_resp.status_code == status.HTTP_200_OK
    bob_refunds = bob_resp.json() if isinstance(bob_resp.json(), list) else bob_resp.json().get("results", [])
    assert not any(r["refund_number"] == refund.refund_number for r in bob_refunds)

    # Bob cannot view detail
    bob_det = seller_bob_client.get(f"/api/v1/marketplace/seller/refunds/{refund.refund_number}/")
    assert bob_det.status_code == status.HTTP_403_FORBIDDEN


def test_buyer_views_seller_submitted_refund_evidence(buyer_alice_client, alice_delivered_order_sam):
    order, _ = alice_delivered_order_sam
    refund = RefundService.record_seller_direct_refund(
        order=order,
        amount=Decimal("100.00"),
        actor=order.items.first().listing.seller,
        transaction_reference="UTR-NEFT-998877",
        evidence_url="https://driverxtra.com/media/neft_slip.pdf",
        notes="Transferred via NEFT slip",
    )

    resp = buyer_alice_client.get("/api/v1/marketplace/buyer/refunds/")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    items = data if isinstance(data, list) else data.get("results", [])
    rf_data = next((r for r in items if r["refund_number"] == refund.refund_number), None)
    assert rf_data is not None
    assert rf_data["gateway_refund_id"] == "UTR-NEFT-998877"
    assert "neft_slip.pdf" in rf_data["notes"]


# =============================================================================
# SCENARIOS 13-15: DISPUTE ESCALATION & ADMIN MEDIATION VS ROUTINE RETURNS
# =============================================================================

def test_buyer_escalates_rejected_return_to_dispute(buyer_alice_client, alice_delivered_order_sam, buyer_alice):
    order, order_item = alice_delivered_order_sam
    req = ReturnService.create_return_request(
        order=order,
        buyer=buyer_alice,
        request_type=ReturnRequestTypeChoices.RETURN,
        reason=ReturnReasonChoices.DEFECTIVE_ITEM,
        description="Cracked brake disc",
        order_item=order_item,
    )
    ReturnService.review_return_request(
        return_request=req,
        actor=order_item.listing.seller,
        action="REJECT",
        rejection_reason="Seller disputes crack occurred prior to delivery",
    )

    url = f"/api/v1/marketplace/buyer/orders/{order.id}/disputes/"
    payload = {
        "category": "REFUND_NOT_PROCESSED",
        "description": f"Escalating rejected return {req.request_number}: seller refuses refund for cracked brake disc.",
        "priority": "HIGH",
        "evidence_urls": ["https://driverxtra.com/media/evidence_crack_hd.jpg"],
    }
    disp_resp = buyer_alice_client.post(url, payload, format="json")
    assert disp_resp.status_code == status.HTTP_201_CREATED
    disp_data = disp_resp.json()
    assert disp_data["status"] == "success"
    assert disp_data["dispute"]["category"] == "REFUND_NOT_PROCESSED"
    assert disp_data["dispute"]["status"] == "OPEN"


def test_admin_mediates_dispute_and_adjudicates(dispute_manager_client, buyer_alice, alice_delivered_order_sam):
    order, _ = alice_delivered_order_sam
    dispute = DisputeService.create_dispute(
        order=order,
        buyer=buyer_alice,
        category=DisputeCategoryChoices.DAMAGED_OR_DEFECTIVE,
        description="Formal dispute for mediation",
        priority=DisputePriorityChoices.HIGH,
    )

    # Post mediator comment
    msg_url = f"/api/v1/marketplace/disputes/{dispute.dispute_number}/messages/"
    msg_resp = dispute_manager_client.post(
        msg_url,
        {"message": "Operations mediator reviewing invoice and technical report."},
        format="json",
    )
    assert msg_resp.status_code == status.HTTP_201_CREATED

    # Adjudicate
    status_url = f"/api/v1/marketplace/admin/disputes/{dispute.dispute_number}/status/"
    adj_resp = dispute_manager_client.post(
        status_url,
        {
            "status": "RESOLVED",
            "resolution": "REFUND_ISSUED",
            "resolution_notes": "Mediator determined defective part warranty applies.",
        },
        format="json",
    )
    assert adj_resp.status_code == status.HTTP_200_OK
    dispute.refresh_from_db()
    assert dispute.status == DisputeStatusChoices.RESOLVED
    assert dispute.resolution == DisputeResolutionChoices.REFUND_ISSUED


def test_admin_cannot_access_seller_refund_endpoints(dispute_manager_client, finance_officer_client):
    # Pure staff without SELLER role must be blocked from seller refund list
    r1 = dispute_manager_client.get("/api/v1/marketplace/seller/refunds/")
    assert r1.status_code == status.HTTP_403_FORBIDDEN

    r2 = finance_officer_client.get("/api/v1/marketplace/seller/refunds/")
    assert r2.status_code == status.HTTP_403_FORBIDDEN


# =============================================================================
# SCENARIOS 16-19: FINANCE GATEWAY PERMISSIONS, OVER-REFUND, COD & VEHICLES
# =============================================================================

def test_finance_payout_required_for_platform_gateway_dispatch(
    dispute_manager_client,
    finance_officer_client,
    alice_delivered_order_sam,
    dispute_manager_staff,
):
    order, _ = alice_delivered_order_sam
    # Dispute manager creates pending refund
    refund = RefundService.create_refund(
        order=order,
        amount=Decimal("100.00"),
        reason="Dispute resolution payout",
        actor=dispute_manager_staff,
    )
    dispatch_url = f"/api/v1/marketplace/admin/refunds/{refund.refund_number}/dispatch/"

    # Dispute Manager (lacks finance.payout) CANNOT dispatch
    disp_resp = dispute_manager_client.post(dispatch_url, format="json")
    assert disp_resp.status_code == status.HTTP_403_FORBIDDEN

    # Finance Officer (has finance.payout) is authorized
    fin_resp = finance_officer_client.post(dispatch_url, format="json")
    assert fin_resp.status_code == status.HTTP_200_OK
    refund.refresh_from_db()
    assert refund.status == RefundStatusChoices.SUCCEEDED


def test_refund_amount_cannot_exceed_available_paid_balance(alice_delivered_order_sam, dispute_manager_staff):
    order, _ = alice_delivered_order_sam
    # Order total is 200.00. Attempting 250.00 must fail.
    with pytest.raises(DjangoValidationError) as exc:
        RefundService.create_refund(
            order=order,
            amount=Decimal("250.00"),
            reason="Exceeding total amount",
            actor=dispute_manager_staff,
        )
    assert "exceeds maximum available refundable balance" in str(exc.value)


def test_cod_order_cannot_be_refunded_before_collected(alice_cod_uncollected_order, alice_cod_collected_order, dispute_manager_staff):
    uncollected_order, _ = alice_cod_uncollected_order
    # Uncollected COD order fails
    with pytest.raises(DjangoValidationError) as exc:
        RefundService.create_refund(
            order=uncollected_order,
            amount=Decimal("50.00"),
            reason="Uncollected COD refund",
            actor=dispute_manager_staff,
        )
    assert "payment has not been collected" in str(exc.value).lower()

    # Collected COD order succeeds
    collected_order, _ = alice_cod_collected_order
    refund = RefundService.create_refund(
        order=collected_order,
        amount=Decimal("50.00"),
        reason="Collected COD partial refund",
        actor=dispute_manager_staff,
    )
    assert refund.status == RefundStatusChoices.PENDING
    assert refund.refund_method == RefundMethodChoices.BANK_TRANSFER


def test_vehicle_order_segregated_from_marketplace_refund(db, buyer_alice, seller_sam, dispute_manager_staff):
    make_bmw = VehicleMake.objects.create(name=f"BMW-{uuid.uuid4().hex[:4]}", country_of_origin="Germany")
    model_330 = VehicleModel.objects.create(make=make_bmw, name="330i", year_start=2021)
    vehicle = VehicleListing.objects.create(
        seller=seller_sam,
        title="2021 BMW 330i M Sport",
        make=make_bmw,
        model=model_330,
        year=2021,
        price=Decimal("25000.00"),
        currency="GBP",
        mileage=15000,
        fuel_type=FuelTypeChoices.PETROL,
        transmission=TransmissionChoices.AUTOMATIC,
        status=ListingStatusChoices.APPROVED,
    )
    now = timezone.now()
    offer = VehiclePurchaseOffer.objects.create(
        listing=vehicle,
        buyer=buyer_alice,
        seller=seller_sam,
        status=VehicleOfferStatusChoices.ACCEPTED,
        agreed_price=Decimal("25000.00"),
        currency="GBP",
        expires_at=now + timedelta(days=2),
        accepted_at=now,
    )
    vehicle_order = VehicleOrder.objects.create(
        order_number=f"VO-{uuid.uuid4().hex[:8].upper()}",
        listing=vehicle,
        accepted_offer=offer,
        buyer=buyer_alice,
        seller=seller_sam,
        agreed_price=Decimal("25000.00"),
        currency="GBP",
        payment_deadline=now + timedelta(days=5),
        status=VehicleOrderStatusChoices.PAYMENT_CONFIRMED,
    )

    with pytest.raises(DjangoValidationError) as exc:
        RefundService.create_refund(
            order=vehicle_order,
            amount=Decimal("500.00"),
            reason="Attempting refund on offline vehicle wire",
            actor=dispute_manager_staff,
        )
    assert "Vehicle orders use offline direct payment" in str(exc.value)
