"""ENG-05a — protect shared (multi-seller) orders from cross-seller status changes and refund overreach.

Order fixture (reused from test_shipping_and_logistics): seller_user owns item A (2 units, total 2832.00),
seller_b owns item B (1 unit, total 2360.00); order total 5192.00. Orders are not split.
"""

import uuid
from decimal import Decimal

import pytest
from rest_framework import status

from apps.identity.models import RoleChoices, User
from apps.marketplace.models import (
    CarrierChoices,
    Order,
    OrderItem,
    OrderStatusChoices,
    PaymentMethodChoices,
    PaymentStatusChoices,
    Refund,
    RefundMethodChoices,
    RefundStatusChoices,
    ReturnReasonChoices,
    ReturnRequest,
    ReturnRequestStatusChoices,
    ReturnRequestTypeChoices,
    ShipmentStatusChoices,
)
from apps.marketplace.logistics.service import ShipmentService
from apps.marketplace.returns.service import RefundService, SellerRefundShareViolation
from tests.test_shipping_and_logistics import (  # noqa: F401  (fixtures re-exported for pytest)
    brake_category,
    multi_seller_order,
    seller_b,
    seller_b_client,
)

SHARE_A = Decimal("2832.00")
SHARE_B = Decimal("2360.00")


def status_url(order):
    return f"/api/v1/marketplace/seller/orders/{order.id}/status/"


def record_refund_url(order):
    return f"/api/v1/marketplace/seller/orders/{order.id}/record-refund/"


def _mark_paid_online(order):
    order.payment_method = PaymentMethodChoices.ONLINE
    order.payment_status = PaymentStatusChoices.PAID
    order.save(update_fields=["payment_method", "payment_status", "updated_at"])
    return order


def _record(client, order, amount, **extra):
    payload = {"amount": str(amount), "transaction_reference": f"UTR{uuid.uuid4().hex[:12].upper()}",
               "refund_method": "BANK_TRANSFER"}
    payload.update(extra)
    return client.post(record_refund_url(order), payload, format="json")


def _single_seller_order(buyer, listing, quantity=2):
    total = (listing.price * quantity * Decimal("1.18")).quantize(Decimal("0.01"))
    taxable = listing.price * quantity
    order = Order.objects.create(
        buyer=buyer, order_number=f"DX-ORD-SINGLE-{uuid.uuid4().hex[:6].upper()}",
        status=OrderStatusChoices.CONFIRMED, payment_method=PaymentMethodChoices.ONLINE,
        payment_status=PaymentStatusChoices.PAID, currency="INR", shipping_country="India",
        subtotal_taxable_amount=taxable, total_tax_amount=total - taxable, total_amount=total,
    )
    OrderItem.objects.create(
        order=order, listing=listing, item_type="PART", title=listing.name, brand=listing.brand, mpn=listing.mpn,
        hsn_code=listing.hsn_code, gst_rate=listing.gst_rate, unit_price=listing.price, quantity=quantity,
        taxable_amount=taxable, tax_amount=total - taxable, total_amount=total,
    )
    listing.stock_quantity -= quantity
    listing.save(update_fields=["stock_quantity"])
    return order


# =============================================================================
# 1. Order-level status changes are locked on shared orders
# =============================================================================

@pytest.mark.django_db
@pytest.mark.parametrize("target", ["PROCESSING", "CANCELLED", "COMPLETED"])
def test_seller_cannot_change_status_of_shared_order(seller_auth_client, multi_seller_order, target):
    order, item_a, item_b = multi_seller_order
    res = seller_auth_client.patch(status_url(order), {"status": target}, format="json")

    assert res.status_code == status.HTTP_409_CONFLICT
    assert res.json()["code"] == "MULTI_SELLER_ORDER_STATUS_LOCKED"
    order.refresh_from_db()
    assert order.status == OrderStatusChoices.CONFIRMED
    item_a.listing.refresh_from_db()
    item_b.listing.refresh_from_db()
    assert (item_a.listing.stock_quantity, item_b.listing.stock_quantity) == (50, 50)  # nobody restocked


@pytest.mark.django_db
def test_lock_applies_to_every_seller_of_the_shared_order(seller_b_client, multi_seller_order):
    order, item_a, item_b = multi_seller_order
    res = seller_b_client.post(status_url(order), {"status": "CANCELLED"}, format="json")
    assert res.status_code == status.HTTP_409_CONFLICT
    assert res.json()["code"] == "MULTI_SELLER_ORDER_STATUS_LOCKED"
    order.refresh_from_db()
    assert order.status == OrderStatusChoices.CONFIRMED


@pytest.mark.django_db
def test_item_without_a_determinable_seller_locks_status_fail_closed(seller_auth_client, multi_seller_order):
    order, item_a, item_b = multi_seller_order
    listing_b = item_b.listing
    listing_b.delete()  # OrderItem.listing is SET_NULL: the item's seller can no longer be determined
    res = seller_auth_client.patch(status_url(order), {"status": "CANCELLED"}, format="json")
    assert res.status_code == status.HTTP_409_CONFLICT
    assert res.json()["code"] == "MULTI_SELLER_ORDER_STATUS_LOCKED"


@pytest.mark.django_db
def test_single_seller_order_status_changes_unchanged(seller_auth_client, buyer_user, multi_seller_order):
    _, item_a, _ = multi_seller_order
    listing_a = item_a.listing
    order = _single_seller_order(buyer_user, listing_a, quantity=2)
    stock_before = SparePartListingStock.get(listing_a)

    processing = seller_auth_client.patch(status_url(order), {"status": "PROCESSING"}, format="json")
    assert processing.status_code == status.HTTP_200_OK, processing.content
    order.refresh_from_db()
    assert order.status == OrderStatusChoices.PROCESSING

    cancelled = seller_auth_client.patch(status_url(order), {"status": "CANCELLED"}, format="json")
    assert cancelled.status_code == status.HTTP_200_OK, cancelled.content
    order.refresh_from_db()
    assert order.status == OrderStatusChoices.CANCELLED
    assert SparePartListingStock.get(listing_a) == stock_before + 2  # own items restocked as before


@pytest.mark.django_db
def test_shipment_driven_status_still_completes_shared_order(seller_auth_client, multi_seller_order, seller_user,
                                                           seller_b):
    order, item_a, item_b = multi_seller_order
    assert seller_auth_client.patch(status_url(order), {"status": "COMPLETED"}, format="json").status_code == 409

    shipment_a = ShipmentService.create_seller_shipment(
        order=order, seller=seller_user, items_payload=[{"order_item_id": str(item_a.id), "quantity": 2}],
        carrier=CarrierChoices.BLUE_DART, dispatch_immediately=True,
    )
    shipment_b = ShipmentService.create_seller_shipment(
        order=order, seller=seller_b, items_payload=[{"order_item_id": str(item_b.id), "quantity": 1}],
        carrier=CarrierChoices.DELHIVERY, dispatch_immediately=True,
    )
    order.refresh_from_db()
    assert order.status == OrderStatusChoices.PROCESSING
    ShipmentService.update_shipment_status(shipment_a, ShipmentStatusChoices.DELIVERED)
    order.refresh_from_db()
    assert order.status == OrderStatusChoices.PROCESSING
    ShipmentService.update_shipment_status(shipment_b, ShipmentStatusChoices.DELIVERED)
    order.refresh_from_db()
    assert order.status == OrderStatusChoices.COMPLETED


class SparePartListingStock:
    @staticmethod
    def get(listing):
        listing.refresh_from_db()
        return listing.stock_quantity


# =============================================================================
# 2. Seller refunds are limited to the seller's own share of a shared order
# =============================================================================

@pytest.mark.django_db
def test_seller_can_refund_up_to_own_share_and_not_beyond(seller_auth_client, multi_seller_order):
    order = _mark_paid_online(multi_seller_order[0])

    over = _record(seller_auth_client, order, SHARE_A + Decimal("0.01"))
    assert over.status_code == status.HTTP_400_BAD_REQUEST
    assert over.json()["code"] == "SELLER_REFUND_LIMIT_EXCEEDED"
    assert Refund.objects.filter(order=order).count() == 0

    exact = _record(seller_auth_client, order, SHARE_A)
    assert exact.status_code == status.HTTP_201_CREATED, exact.content

    again = _record(seller_auth_client, order, Decimal("0.01"))
    assert again.status_code == status.HTTP_400_BAD_REQUEST
    assert again.json()["code"] == "SELLER_REFUND_LIMIT_EXCEEDED"
    assert Refund.objects.filter(order=order).count() == 1


@pytest.mark.django_db
def test_cumulative_seller_refunds_respect_remaining_share(seller_auth_client, multi_seller_order):
    order = _mark_paid_online(multi_seller_order[0])
    assert _record(seller_auth_client, order, Decimal("2000.00")).status_code == 201
    rejected = _record(seller_auth_client, order, Decimal("832.01"))
    assert rejected.status_code == 400 and rejected.json()["code"] == "SELLER_REFUND_LIMIT_EXCEEDED"
    assert _record(seller_auth_client, order, Decimal("832.00")).status_code == 201


@pytest.mark.django_db
def test_other_sellers_refunds_do_not_consume_own_share(seller_auth_client, seller_b_client, multi_seller_order):
    order = _mark_paid_online(multi_seller_order[0])
    over_b = _record(seller_b_client, order, SHARE_B + Decimal("0.01"))
    assert over_b.status_code == 400 and over_b.json()["code"] == "SELLER_REFUND_LIMIT_EXCEEDED"
    assert _record(seller_b_client, order, SHARE_B).status_code == 201
    assert _record(seller_auth_client, order, SHARE_A).status_code == 201
    total = sum(r.amount for r in Refund.objects.filter(order=order))
    assert total == order.total_amount == SHARE_A + SHARE_B


@pytest.mark.django_db
def test_unattributable_existing_refund_fails_closed(seller_auth_client, seller_b_client, multi_seller_order):
    order = _mark_paid_online(multi_seller_order[0])
    ops = User.objects.create_user(email="ops.refunds@driverxtra.test", password="Str0ng-Passw0rd!x",
                                   is_staff=True, is_email_verified=True)
    Refund.objects.create(
        refund_number=f"REF-OPS-{uuid.uuid4().hex[:8].upper()}", order=order, amount=Decimal("10.00"),
        currency=order.currency, status=RefundStatusChoices.PENDING,
        refund_method=RefundMethodChoices.ORIGINAL_PAYMENT, created_by=ops,
    )
    for client in (seller_auth_client, seller_b_client):
        res = _record(client, order, Decimal("1.00"))
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert res.json()["code"] == "REFUND_ATTRIBUTION_AMBIGUOUS"
    assert Refund.objects.filter(order=order).count() == 1


@pytest.mark.django_db
def test_failed_refunds_do_not_consume_share(seller_auth_client, multi_seller_order, seller_user):
    order = _mark_paid_online(multi_seller_order[0])
    Refund.objects.create(
        refund_number=f"REF-FAILED-{uuid.uuid4().hex[:8].upper()}", order=order, amount=SHARE_A,
        currency=order.currency, status=RefundStatusChoices.FAILED,
        refund_method=RefundMethodChoices.BANK_TRANSFER, created_by=seller_user,
    )
    assert _record(seller_auth_client, order, SHARE_A).status_code == 201


def _return_request(order, item, buyer, seller):
    return ReturnRequest.objects.create(
        request_number=f"RR-{uuid.uuid4().hex[:8].upper()}", order=order, order_item=item, buyer=buyer,
        seller=seller, request_type=ReturnRequestTypeChoices.RETURN, status=ReturnRequestStatusChoices.APPROVED,
        reason=ReturnReasonChoices.DEFECTIVE_ITEM, requested_quantity=1,
    )


@pytest.mark.django_db
def test_seller_cannot_link_refund_to_other_sellers_return(seller_auth_client, multi_seller_order, buyer_user,
                                                           seller_b):
    order, _, item_b = multi_seller_order
    _mark_paid_online(order)
    rr_b = _return_request(order, item_b, buyer_user, seller_b)
    res = _record(seller_auth_client, order, Decimal("100.00"), return_request_id=str(rr_b.id))
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert res.json()["code"] == "REFUND_NOT_SELLER_ITEM"
    assert Refund.objects.filter(order=order).count() == 0


@pytest.mark.django_db
def test_refund_linked_to_own_return_counts_against_own_share(seller_auth_client, seller_b_client,
                                                              multi_seller_order, buyer_user, seller_user):
    order, item_a, _ = multi_seller_order
    _mark_paid_online(order)
    rr_a = _return_request(order, item_a, buyer_user, seller_user)
    assert _record(seller_auth_client, order, Decimal("2000.00"), return_request_id=str(rr_a.id)).status_code == 201
    over = _record(seller_auth_client, order, Decimal("832.01"))
    assert over.status_code == 400 and over.json()["code"] == "SELLER_REFUND_LIMIT_EXCEEDED"
    # Seller B's share is untouched by A's return-linked refund.
    assert _record(seller_b_client, order, SHARE_B).status_code == 201


@pytest.mark.django_db
def test_single_seller_order_refund_limits_unchanged(seller_auth_client, buyer_user, multi_seller_order):
    _, item_a, _ = multi_seller_order
    order = _single_seller_order(buyer_user, item_a.listing, quantity=2)
    full = _record(seller_auth_client, order, order.total_amount)
    assert full.status_code == status.HTTP_201_CREATED, full.content
    over = _record(seller_auth_client, order, Decimal("0.01"))
    assert over.status_code == status.HTTP_400_BAD_REQUEST
    assert "code" not in over.json()                  # existing order-level message, unchanged
    assert "exceeds maximum available refundable balance" in over.json()["error"]


# =============================================================================
# 3. Platform refund requests: seller share enforced only when requested by the seller path
# =============================================================================

@pytest.mark.django_db
def test_create_refund_enforces_share_only_for_seller_initiated_requests(multi_seller_order, seller_user):
    order = _mark_paid_online(multi_seller_order[0])
    seller_user.add_role(RoleChoices.ADMIN)  # holds order.refund, and still sells item A

    with pytest.raises(SellerRefundShareViolation) as excinfo:
        RefundService.create_refund(order=order, amount=SHARE_A + Decimal("0.01"), reason="Seller request",
                                    actor=seller_user, enforce_seller_share=True)
    assert excinfo.value.code == "SELLER_REFUND_LIMIT_EXCEEDED"
    assert Refund.objects.filter(order=order).count() == 0

    within = RefundService.create_refund(order=order, amount=SHARE_A, reason="Seller request", actor=seller_user,
                                         enforce_seller_share=True)
    assert within.status == RefundStatusChoices.PENDING

    # Default (admin / dispute callers): only the existing order-level balance applies.
    admin_refund = RefundService.create_refund(order=order, amount=SHARE_B, reason="Ops refund", actor=seller_user)
    assert admin_refund.amount == SHARE_B


@pytest.mark.django_db
def test_seller_platform_refund_request_without_permission_still_denied(seller_auth_client, multi_seller_order):
    order = _mark_paid_online(multi_seller_order[0])
    res = seller_auth_client.post(f"/api/v1/marketplace/seller/orders/{order.id}/request-platform-refund/",
                                  {"amount": "10.00", "reason": "Customer return"}, format="json")
    assert res.status_code == status.HTTP_403_FORBIDDEN
    assert Refund.objects.filter(order=order).count() == 0
