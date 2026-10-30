import uuid
from decimal import Decimal
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.marketplace.models import (
    Order,
    OrderItem,
    OrderStatusChoices,
    PaymentMethodChoices,
    PaymentStatusChoices,
    CODCollectionStatusChoices,
    SparePartListing,
    ListingStatusChoices,
    PartConditionChoices,
    Shipment,
    ShipmentStatusChoices,
    ReturnRequest,
    ReturnRequestTypeChoices,
    ReturnRequestStatusChoices,
    Refund,
    RefundStatusChoices,
    Dispute,
    DisputeStatusChoices,
    ProductReview,
    ReviewStatusChoices,
)
from apps.catalogue.models import PartCategory
from apps.notifications.handlers import process_audit_entry
from apps.notifications.models import Notification
from platform_core.audit.writer import record_audit_entry


NOTIFICATIONS_URL = "/api/v1/notifications/"
UNREAD_COUNT_URL = "/api/v1/notifications/unread-count/"
READ_ALL_URL = "/api/v1/notifications/read-all/"


def auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def test_category(db):
    return PartCategory.objects.create(name="Brakes", slug="brakes")


@pytest.fixture
def test_part_listing(db, seller_user, test_category):
    return SparePartListing.objects.create(
        seller=seller_user,
        category=test_category,
        name="Performance Brake Pads",
        mpn="BRK-PAD-001",
        price=Decimal("120.00"),
        condition=PartConditionChoices.NEW,
        stock_quantity=10,
        status=ListingStatusChoices.APPROVED,
        is_active=True,
    )


@pytest.fixture
def test_order(db, buyer_user, test_part_listing):
    order = Order.objects.create(
        buyer=buyer_user,
        order_number=f"DX-ORD-TEST-{uuid.uuid4().hex[:6].upper()}",
        status=OrderStatusChoices.PENDING_CONFIRMATION,
        payment_method=PaymentMethodChoices.ONLINE,
        payment_status=PaymentStatusChoices.PENDING,
        currency="GBP",
        shipping_name="John Buyer",
        shipping_phone="+447000000001",
        shipping_address_line1="10 Test Street",
        shipping_city="London",
        shipping_state="Greater London",
        shipping_postal_code="SW1A 1AA",
        shipping_country="GB",
        subtotal_taxable_amount=Decimal("100.00"),
        total_tax_amount=Decimal("20.00"),
        total_amount=Decimal("120.00"),
    )
    OrderItem.objects.create(
        order=order,
        listing=test_part_listing,
        item_type="SPARE_PART",
        title=test_part_listing.name,
        unit_price=Decimal("100.00"),
        quantity=1,
        taxable_amount=Decimal("100.00"),
        tax_amount=Decimal("20.00"),
        total_amount=Decimal("120.00"),
    )
    return order


# ---------------------------------------------------------------------------
# Order & Payment Workflow Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_order_creation_notifies_buyer_and_seller(buyer_user, seller_user, test_order):
    entry = record_audit_entry(
        event_type="marketplace.order.created",
        action="marketplace:order.create",
        resource_type="Order",
        resource_id=str(test_order.id),
        actor_id=buyer_user.id,
        metadata={"order_number": test_order.order_number, "total_amount": str(test_order.total_amount)},
    )

    # Buyer notification
    buyer_notifs = Notification.objects.filter(recipient=buyer_user)
    assert buyer_notifs.count() == 1
    b_notif = buyer_notifs.first()
    assert test_order.order_number in b_notif.title
    assert "placed successfully" in b_notif.message
    assert b_notif.link == "/platform?tab=my_orders"
    assert b_notif.is_read is False

    # Seller notification
    seller_notifs = Notification.objects.filter(recipient=seller_user)
    assert seller_notifs.count() == 1
    s_notif = seller_notifs.first()
    assert "New Order Received" in s_notif.title
    assert test_order.order_number in s_notif.message
    assert s_notif.link == "/platform?tab=seller_orders"
    assert s_notif.is_read is False

    # Idempotency / Duplicate prevention
    reprocessed = process_audit_entry(entry)
    assert reprocessed == []
    assert Notification.objects.filter(recipient=buyer_user).count() == 1
    assert Notification.objects.filter(recipient=seller_user).count() == 1


@pytest.mark.django_db
def test_order_payment_verified_and_failed_notifications(buyer_user, test_order):
    # Success event
    record_audit_entry(
        event_type="marketplace.order.payment_verified",
        action="marketplace:order.payment_verify",
        resource_type="Order",
        resource_id=str(test_order.id),
        actor_id=buyer_user.id,
        metadata={"order_number": test_order.order_number},
    )

    notif = Notification.objects.get(recipient=buyer_user, event_type="marketplace.order.payment_verified")
    assert "Payment Verified" in notif.title
    assert "successfully verified" in notif.message
    assert notif.link == "/platform?tab=my_orders"

    # Failure event
    record_audit_entry(
        event_type="marketplace.order.payment_verification_failed",
        action="marketplace:order.payment_verify_failed",
        resource_type="Order",
        resource_id=str(test_order.id),
        actor_id=buyer_user.id,
        metadata={"order_number": test_order.order_number, "error": "Insufficient funds"},
    )

    failed_notif = Notification.objects.get(
        recipient=buyer_user, event_type="marketplace.order.payment_verification_failed"
    )
    assert "Payment Verification Failed" in failed_notif.title
    assert "Insufficient funds" in failed_notif.message


@pytest.mark.django_db
@pytest.mark.parametrize(
    "new_status,expected_title,notes",
    [
        ("CONFIRMED", "Order Confirmed", ""),
        ("SHIPPED", "Order Shipped", ""),
        ("DELIVERED", "Order Delivered", ""),
        ("CANCELLED", "Order Cancelled", "Out of stock"),
    ],
)
def test_order_status_update_notifications(buyer_user, test_order, new_status, expected_title, notes):
    record_audit_entry(
        event_type="marketplace.order.status_updated",
        action="marketplace:order.update_status",
        resource_type="Order",
        resource_id=str(test_order.id),
        actor_id=test_order.items.first().listing.seller.id,
        metadata={"order_number": test_order.order_number, "new_status": new_status, "notes": notes},
    )

    notif = Notification.objects.get(recipient=buyer_user, event_type="marketplace.order.status_updated")
    assert expected_title in notif.title
    if notes:
        assert notes in notif.message
    assert notif.link == "/platform?tab=my_orders"


@pytest.mark.django_db
def test_buyer_order_cancellation_notifies_seller(seller_user, buyer_user, test_order):
    record_audit_entry(
        event_type="marketplace.order.buyer_cancelled",
        action="marketplace:order.cancel",
        resource_type="Order",
        resource_id=str(test_order.id),
        actor_id=buyer_user.id,
        metadata={"order_number": test_order.order_number},
    )

    notif = Notification.objects.get(recipient=seller_user, event_type="marketplace.order.buyer_cancelled")
    assert "Order Cancelled" in notif.title
    assert test_order.order_number in notif.message
    assert notif.link == "/platform?tab=seller_orders"


@pytest.mark.django_db
def test_cod_collection_notification(buyer_user, test_order):
    record_audit_entry(
        event_type="marketplace.order.cod_collection_updated",
        action="marketplace:order.cod_collection",
        resource_type="Order",
        resource_id=str(test_order.id),
        actor_id=buyer_user.id,
        metadata={"order_number": test_order.order_number, "new_cod_status": "COLLECTED"},
    )

    notif = Notification.objects.get(recipient=buyer_user, event_type="marketplace.order.cod_collection_updated")
    assert "COD Payment Collected" in notif.title
    assert test_order.order_number in notif.message


# ---------------------------------------------------------------------------
# Shipment Workflow Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_shipment_created_and_updated_notifications(buyer_user, seller_user, test_order):
    shipment = Shipment.objects.create(
        order=test_order,
        seller=seller_user,
        shipment_number=f"SHP-TEST-{uuid.uuid4().hex[:6].upper()}",
        carrier="DHL Express",
        tracking_number="DHL-987654321",
        status=ShipmentStatusChoices.DISPATCHED,
    )

    # Shipment created / dispatched
    record_audit_entry(
        event_type="marketplace.shipment.created",
        action="marketplace:shipment.create",
        resource_type="Shipment",
        resource_id=str(shipment.id),
        actor_id=seller_user.id,
        metadata={
            "shipment_number": shipment.shipment_number,
            "order_number": test_order.order_number,
            "carrier": shipment.carrier,
            "tracking_number": shipment.tracking_number,
        },
    )

    created_notif = Notification.objects.get(recipient=buyer_user, event_type="marketplace.shipment.created")
    assert "Shipment Dispatched" in created_notif.title
    assert shipment.shipment_number in created_notif.title
    assert "DHL Express" in created_notif.message
    assert "DHL-987654321" in created_notif.message

    # Shipment delivered
    record_audit_entry(
        event_type="marketplace.shipment.status_updated",
        action="marketplace:shipment.update_status",
        resource_type="Shipment",
        resource_id=str(shipment.id),
        actor_id=seller_user.id,
        metadata={
            "shipment_number": shipment.shipment_number,
            "order_number": test_order.order_number,
            "new_status": "DELIVERED",
        },
    )

    delivered_notif = Notification.objects.get(
        recipient=buyer_user, event_type="marketplace.shipment.status_updated"
    )
    assert "Shipment Delivered" in delivered_notif.title
    assert shipment.shipment_number in delivered_notif.title


# ---------------------------------------------------------------------------
# Return, Refund & Dispute Workflow Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_return_request_lifecycle_notifications(buyer_user, seller_user, test_order):
    req = ReturnRequest.objects.create(
        request_number=f"RET-TEST-{uuid.uuid4().hex[:6].upper()}",
        order=test_order,
        buyer=buyer_user,
        seller=seller_user,
        request_type=ReturnRequestTypeChoices.RETURN,
        status=ReturnRequestStatusChoices.PENDING,
        reason="DEFECTIVE_ITEM",
        description="Item arrived damaged.",
        refund_amount=Decimal("120.00"),
    )

    # 1. Return created -> notifies seller
    record_audit_entry(
        event_type="marketplace.return.created",
        action="marketplace:return.create",
        resource_type="ReturnRequest",
        resource_id=str(req.id),
        actor_id=buyer_user.id,
        metadata={"request_number": req.request_number, "order_number": test_order.order_number},
    )

    s_notif = Notification.objects.get(recipient=seller_user, event_type="marketplace.return.created")
    assert "Return Request" in s_notif.title
    assert req.request_number in s_notif.title
    assert s_notif.link == "/platform?tab=seller_orders"

    # 2. Return approved -> notifies buyer
    req.status = ReturnRequestStatusChoices.APPROVED
    req.save()
    record_audit_entry(
        event_type="marketplace.return.approved",
        action="marketplace:return.approve",
        resource_type="ReturnRequest",
        resource_id=str(req.id),
        actor_id=seller_user.id,
        metadata={"request_number": req.request_number, "order_number": test_order.order_number},
    )

    b_appr = Notification.objects.get(recipient=buyer_user, event_type="marketplace.return.approved")
    assert "Approved" in b_appr.title
    assert req.request_number in b_appr.title
    assert b_appr.link == "/platform?tab=my_orders"

    # 3. Return completed -> notifies buyer
    req.status = ReturnRequestStatusChoices.COMPLETED
    req.save()
    record_audit_entry(
        event_type="marketplace.return.completed",
        action="marketplace:return.complete",
        resource_type="ReturnRequest",
        resource_id=str(req.id),
        actor_id=seller_user.id,
        metadata={"request_number": req.request_number, "order_number": test_order.order_number},
    )

    b_comp = Notification.objects.get(recipient=buyer_user, event_type="marketplace.return.completed")
    assert "Return Completed" in b_comp.title


@pytest.mark.django_db
def test_refund_processed_notifies_buyer(buyer_user, test_order):
    refund = Refund.objects.create(
        refund_number=f"RFND-TEST-{uuid.uuid4().hex[:6].upper()}",
        order=test_order,
        amount=Decimal("120.00"),
        currency="GBP",
        status=RefundStatusChoices.SUCCEEDED,
        refund_method="ORIGINAL_PAYMENT",
    )

    record_audit_entry(
        event_type="marketplace.refund.processed",
        action="marketplace:refund.process",
        resource_type="Refund",
        resource_id=str(refund.id),
        actor_id=buyer_user.id,
        metadata={"refund_number": refund.refund_number, "order_number": test_order.order_number},
    )

    notif = Notification.objects.get(recipient=buyer_user, event_type="marketplace.refund.processed")
    assert "Refund Processed" in notif.title
    assert refund.refund_number in notif.title
    assert "120.00" in notif.message
    assert notif.link == "/platform?tab=my_orders"


@pytest.mark.django_db
def test_dispute_lifecycle_notifications(buyer_user, seller_user, staff_user, test_order):
    dispute = Dispute.objects.create(
        dispute_number=f"DSP-TEST-{uuid.uuid4().hex[:6].upper()}",
        order=test_order,
        buyer=buyer_user,
        seller=seller_user,
        category="ITEM_NOT_RECEIVED",
        status=DisputeStatusChoices.OPEN,
        description="Package was not received.",
    )

    # 1. Dispute created -> notifies seller
    record_audit_entry(
        event_type="marketplace.dispute.created",
        action="marketplace:dispute.create",
        resource_type="Dispute",
        resource_id=str(dispute.id),
        actor_id=buyer_user.id,
        metadata={"dispute_number": dispute.dispute_number, "order_number": test_order.order_number},
    )

    s_notif = Notification.objects.get(recipient=seller_user, event_type="marketplace.dispute.created")
    assert "Dispute Opened" in s_notif.title
    assert dispute.dispute_number in s_notif.title

    # 2. Staff updates dispute status -> notifies both buyer and seller
    record_audit_entry(
        event_type="marketplace.dispute.status_updated",
        action="marketplace:dispute.status_update",
        resource_type="Dispute",
        resource_id=str(dispute.id),
        actor_id=staff_user.id,
        metadata={"dispute_number": dispute.dispute_number, "new_status": "UNDER_REVIEW"},
    )

    assert Notification.objects.filter(recipient=buyer_user, event_type="marketplace.dispute.status_updated").exists()
    assert Notification.objects.filter(recipient=seller_user, event_type="marketplace.dispute.status_updated").exists()

    # 3. Buyer adds message -> notifies seller
    record_audit_entry(
        event_type="marketplace.dispute.message_added",
        action="marketplace:dispute.message_add",
        resource_type="Dispute",
        resource_id=str(dispute.id),
        actor_id=buyer_user.id,
        metadata={"dispute_number": dispute.dispute_number},
    )

    msg_notif = Notification.objects.get(recipient=seller_user, event_type="marketplace.dispute.message_added")
    assert "New Message on Dispute" in msg_notif.title


# ---------------------------------------------------------------------------
# Reviews Workflow Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_review_lifecycle_notifications(buyer_user, seller_user, staff_user, test_order, test_part_listing):
    review = ProductReview.objects.create(
        order=test_order,
        order_item=test_order.items.first(),
        listing=test_part_listing,
        buyer=buyer_user,
        seller=seller_user,
        rating=5,
        title="Excellent fitment",
        comment="Installed in 20 minutes, perfect performance.",
        status=ReviewStatusChoices.APPROVED,
        is_verified_purchase=True,
    )

    # 1. Review created -> notifies seller
    record_audit_entry(
        event_type="marketplace.product_review.created",
        action="marketplace:review.create",
        resource_type="ProductReview",
        resource_id=str(review.id),
        actor_id=buyer_user.id,
        metadata={"review_id": str(review.id)},
    )

    s_notif = Notification.objects.get(recipient=seller_user, event_type="marketplace.product_review.created")
    assert "New Review" in s_notif.title
    assert "5-star review" in s_notif.message

    # 2. Seller replies -> notifies buyer
    review.seller_reply = "Thank you for trusting our parts!"
    review.save()
    record_audit_entry(
        event_type="marketplace.productreview.replied",
        action="marketplace:review.reply",
        resource_type="ProductReview",
        resource_id=str(review.id),
        actor_id=seller_user.id,
        metadata={"review_id": str(review.id)},
    )

    b_reply = Notification.objects.get(recipient=buyer_user, event_type="marketplace.productreview.replied")
    assert "Seller Replied to Your Review" in b_reply.title
    assert "Thank you for trusting" in b_reply.message

    # 3. Review moderated (hidden) -> notifies buyer
    record_audit_entry(
        event_type="marketplace.review.moderated",
        action="marketplace:review.hide",
        resource_type="ProductReview",
        resource_id=str(review.id),
        actor_id=staff_user.id,
        metadata={"action": "HIDE"},
    )

    b_mod = Notification.objects.get(recipient=buyer_user, event_type="marketplace.review.moderated")
    assert "Review Moderation Notice" in b_mod.title


# ---------------------------------------------------------------------------
# API Authorization, Filtering, and Deletion Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_notification_authorization_and_recipient_isolation(buyer_user, seller_user):
    # Create notification for buyer
    entry = record_audit_entry(
        event_type="test.event",
        action="test:action",
        resource_type="Test",
        resource_id="123",
        actor_id=buyer_user.id,
    )
    b_notif = Notification.objects.create(
        source_audit_id=entry.id,
        recipient=buyer_user,
        event_type="test.event",
        title="Buyer Secret Notification",
        message="Confidential content",
    )

    # Buyer can see it
    buyer_client = auth_client(buyer_user)
    res = buyer_client.get(NOTIFICATIONS_URL)
    assert res.status_code == status.HTTP_200_OK
    assert len(res.data["results"]) == 1
    assert res.data["results"][0]["id"] == str(b_notif.id)

    # Seller CANNOT see buyer's notification
    seller_client = auth_client(seller_user)
    res_seller = seller_client.get(NOTIFICATIONS_URL)
    assert res_seller.status_code == status.HTTP_200_OK
    assert len(res_seller.data["results"]) == 0

    # Seller CANNOT mark buyer's notification as read (returns 404)
    res_mark = seller_client.post(f"/api/v1/notifications/{b_notif.id}/read/")
    assert res_mark.status_code == status.HTTP_404_NOT_FOUND

    # Seller CANNOT delete buyer's notification (returns 404)
    res_del = seller_client.delete(f"/api/v1/notifications/{b_notif.id}/")
    assert res_del.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_notification_unread_filtering_and_lifecycle(buyer_user):
    client = auth_client(buyer_user)

    # Create 3 notifications for buyer (2 unread, 1 read)
    n1 = Notification.objects.create(
        source_audit_id=uuid.uuid4(),
        recipient=buyer_user,
        event_type="type.a",
        title="Unread 1",
        is_read=False,
    )
    n2 = Notification.objects.create(
        source_audit_id=uuid.uuid4(),
        recipient=buyer_user,
        event_type="type.b",
        title="Unread 2",
        is_read=False,
    )
    n3 = Notification.objects.create(
        source_audit_id=uuid.uuid4(),
        recipient=buyer_user,
        event_type="type.a",
        title="Already Read",
        is_read=True,
    )

    # Check unread count API
    count_res = client.get(UNREAD_COUNT_URL)
    assert count_res.status_code == status.HTTP_200_OK
    assert count_res.data["unread_count"] == 2

    # Filter ?unread=true
    unread_res = client.get(f"{NOTIFICATIONS_URL}?unread=true")
    assert unread_res.status_code == status.HTTP_200_OK
    assert len(unread_res.data["results"]) == 2

    # Filter ?event_type=type.a
    event_res = client.get(f"{NOTIFICATIONS_URL}?event_type=type.a")
    assert event_res.status_code == status.HTTP_200_OK
    assert len(event_res.data["results"]) == 2

    # Mark single read
    mark_res = client.post(f"/api/v1/notifications/{n1.id}/read/")
    assert mark_res.status_code == status.HTTP_200_OK
    n1.refresh_from_db()
    assert n1.is_read is True
    assert n1.read_at is not None

    # Mark all read
    all_res = client.post(READ_ALL_URL)
    assert all_res.status_code == status.HTTP_200_OK
    assert all_res.data["updated_count"] == 1  # n2 was the remaining unread

    # Unread count should now be 0
    count_res2 = client.get(UNREAD_COUNT_URL)
    assert count_res2.data["unread_count"] == 0

    # Delete single notification
    del_res = client.delete(f"/api/v1/notifications/{n3.id}/")
    assert del_res.status_code == status.HTTP_200_OK
    assert not Notification.objects.filter(id=n3.id).exists()
