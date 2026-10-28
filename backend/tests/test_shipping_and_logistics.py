import pytest
import uuid
from decimal import Decimal
from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.test import APIClient

from apps.identity.models import User, RoleChoices
from apps.catalogue.models import PartCategory
from apps.marketplace.models import (
    SparePartListing,
    ListingStatusChoices,
    Order,
    OrderItem,
    OrderStatusChoices,
    PaymentMethodChoices,
    PaymentStatusChoices,
    CODCollectionStatusChoices,
    CarrierChoices,
    ShipmentStatusChoices,
    Shipment,
    ShipmentItem,
    TrackingEvent,
)
from apps.marketplace.logistics.service import ShipmentService
from apps.marketplace.logistics.providers import get_available_carriers_for_country, get_carrier_provider


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
def multi_seller_order(db, buyer_user, seller_user, seller_b, brake_category):
    """
    Creates an order containing:
    - 2 units of listing A (seller_user)
    - 1 unit of listing B (seller_b)
    Payment method: COD (pending payment & pending collection)
    """
    listing_a = SparePartListing.objects.create(
        seller=seller_user,
        name="Front Brake Pads",
        brand="Brembo",
        mpn="BP-001",
        category=brake_category,
        price=Decimal("1200.00"),
        currency="INR",
        hsn_code="8708",
        gst_rate=Decimal("18.00"),
        status=ListingStatusChoices.APPROVED,
        is_active=True,
        stock_quantity=50,
    )
    listing_b = SparePartListing.objects.create(
        seller=seller_b,
        name="Rear Brake Discs",
        brand="Bosch",
        mpn="BD-002",
        category=brake_category,
        price=Decimal("2000.00"),
        currency="INR",
        hsn_code="8708",
        gst_rate=Decimal("18.00"),
        status=ListingStatusChoices.APPROVED,
        is_active=True,
        stock_quantity=50,
    )

    order = Order.objects.create(
        buyer=buyer_user,
        order_number=f"DX-ORD-TEST-{uuid.uuid4().hex[:6].upper()}",
        status=OrderStatusChoices.CONFIRMED,
        payment_method=PaymentMethodChoices.COD,
        payment_status=PaymentStatusChoices.PENDING,
        cod_collection_status=CODCollectionStatusChoices.PENDING,
        currency="INR",
        place_of_supply="MH",
        seller_state="MH",
        shipping_name="John Buyer",
        shipping_phone="+919876543210",
        shipping_address_line1="123 Marine Drive",
        shipping_city="Mumbai",
        shipping_state="Maharashtra",
        shipping_postal_code="400001",
        shipping_country="India",
        subtotal_taxable_amount=Decimal("4400.00"),
        cgst_amount=Decimal("396.00"),
        sgst_amount=Decimal("396.00"),
        igst_amount=Decimal("0.00"),
        total_tax_amount=Decimal("792.00"),
        total_amount=Decimal("5192.00"),
    )

    item_a = OrderItem.objects.create(
        order=order,
        listing=listing_a,
        item_type="PART",
        title=listing_a.name,
        brand=listing_a.brand,
        mpn=listing_a.mpn,
        hsn_code=listing_a.hsn_code,
        gst_rate=listing_a.gst_rate,
        unit_price=listing_a.price,
        quantity=2,
        taxable_amount=Decimal("2400.00"),
        cgst_amount=Decimal("216.00"),
        sgst_amount=Decimal("216.00"),
        igst_amount=Decimal("0.00"),
        tax_amount=Decimal("432.00"),
        total_amount=Decimal("2832.00"),
    )

    item_b = OrderItem.objects.create(
        order=order,
        listing=listing_b,
        item_type="PART",
        title=listing_b.name,
        brand=listing_b.brand,
        mpn=listing_b.mpn,
        hsn_code=listing_b.hsn_code,
        gst_rate=listing_b.gst_rate,
        unit_price=listing_b.price,
        quantity=1,
        taxable_amount=Decimal("2000.00"),
        cgst_amount=Decimal("180.00"),
        sgst_amount=Decimal("180.00"),
        igst_amount=Decimal("0.00"),
        tax_amount=Decimal("360.00"),
        total_amount=Decimal("2360.00"),
    )

    return order, item_a, item_b


# ==============================================================================
# 1. CARRIER ABSTRACTION & REGISTRY TESTS
# ==============================================================================

def test_available_carriers_for_india_and_uk():
    """Verifies that country-specific logistics carriers are correctly returned."""
    in_carriers = get_available_carriers_for_country("IN")
    in_codes = [c["code"] for c in in_carriers]
    assert CarrierChoices.BLUE_DART in in_codes
    assert CarrierChoices.DELHIVERY in in_codes
    assert CarrierChoices.DTDC in in_codes
    assert CarrierChoices.ROYAL_MAIL not in in_codes
    assert CarrierChoices.EVRI not in in_codes

    uk_carriers = get_available_carriers_for_country("GB")
    uk_codes = [c["code"] for c in uk_carriers]
    assert CarrierChoices.ROYAL_MAIL in uk_codes
    assert CarrierChoices.DPD_UK in uk_codes
    assert CarrierChoices.EVRI in uk_codes
    assert CarrierChoices.BLUE_DART not in uk_codes
    assert CarrierChoices.DELHIVERY not in uk_codes


def test_carrier_tracking_url_generation():
    """Tests provider URL generation without mock fake API calls."""
    royal_mail = get_carrier_provider(CarrierChoices.ROYAL_MAIL)
    url = royal_mail.generate_tracking_url("AB123456789GB")
    assert "royalmail.com" in url
    assert "AB123456789GB" in url

    blue_dart = get_carrier_provider(CarrierChoices.BLUE_DART)
    bd_url = blue_dart.generate_tracking_url("1234567890")
    assert "bluedart.com" in bd_url
    assert "1234567890" in bd_url


# ==============================================================================
# 2. SHIPMENT CREATION & QUANTITY ALLOCATION TESTS
# ==============================================================================

@pytest.mark.django_db
def test_seller_shipment_creation_success(multi_seller_order, seller_user):
    order, item_a, _ = multi_seller_order

    shipment = ShipmentService.create_seller_shipment(
        order=order,
        seller=seller_user,
        items_payload=[{"order_item_id": str(item_a.id), "quantity": 2}],
        carrier=CarrierChoices.BLUE_DART,
        tracking_number="BD987654321IN",
        dispatch_immediately=True,
        actor=seller_user,
    )

    assert shipment.shipment_number.startswith("SHP-")
    assert shipment.status == ShipmentStatusChoices.DISPATCHED
    assert shipment.dispatched_at is not None
    assert shipment.carrier == CarrierChoices.BLUE_DART
    assert shipment.items.count() == 1
    assert shipment.items.first().quantity == 2
    # Initial tracking event created
    assert shipment.tracking_events.count() == 1
    assert shipment.tracking_events.first().status == ShipmentStatusChoices.DISPATCHED

    # Order moved to PROCESSING on first dispatch
    order.refresh_from_db()
    assert order.status == OrderStatusChoices.PROCESSING


@pytest.mark.django_db
def test_seller_cannot_ship_another_sellers_item(multi_seller_order, seller_user):
    order, _, item_b = multi_seller_order  # item_b belongs to seller_b

    with pytest.raises(DjangoValidationError) as exc:
        ShipmentService.create_seller_shipment(
            order=order,
            seller=seller_user,
            items_payload=[{"order_item_id": str(item_b.id), "quantity": 1}],
            carrier=CarrierChoices.OTHER,
        )
    assert "another seller" in str(exc.value)


@pytest.mark.django_db
def test_seller_cannot_exceed_order_item_quantity(multi_seller_order, seller_user):
    order, item_a, _ = multi_seller_order  # ordered quantity is 2

    with pytest.raises(DjangoValidationError) as exc:
        ShipmentService.create_seller_shipment(
            order=order,
            seller=seller_user,
            items_payload=[{"order_item_id": str(item_a.id), "quantity": 3}],
            carrier=CarrierChoices.OTHER,
        )
    assert "remaining to fulfill" in str(exc.value)


@pytest.mark.django_db
def test_seller_cannot_overallocate_across_multiple_shipments(multi_seller_order, seller_user):
    order, item_a, _ = multi_seller_order  # ordered quantity is 2

    # Shipment 1: 1 unit
    ShipmentService.create_seller_shipment(
        order=order,
        seller=seller_user,
        items_payload=[{"order_item_id": str(item_a.id), "quantity": 1}],
        carrier=CarrierChoices.OTHER,
    )

    # Shipment 2: Attempting 2 units (only 1 remaining)
    with pytest.raises(DjangoValidationError) as exc:
        ShipmentService.create_seller_shipment(
            order=order,
            seller=seller_user,
            items_payload=[{"order_item_id": str(item_a.id), "quantity": 2}],
            carrier=CarrierChoices.OTHER,
        )
    assert "remaining to fulfill" in str(exc.value)


# ==============================================================================
# 3. STATE MACHINE TRANSITIONS & TRACKING EVENT TESTS
# ==============================================================================

@pytest.mark.django_db
def test_valid_shipment_lifecycle_progression(multi_seller_order, seller_user):
    order, item_a, _ = multi_seller_order

    # Step 1: Created
    shipment = ShipmentService.create_seller_shipment(
        order=order,
        seller=seller_user,
        items_payload=[{"order_item_id": str(item_a.id), "quantity": 2}],
        carrier=CarrierChoices.BLUE_DART,
        tracking_number="BD11223344",
        dispatch_immediately=False,
    )
    assert shipment.status == ShipmentStatusChoices.CREATED

    # Step 2: Dispatched
    shipment = ShipmentService.update_shipment_status(
        shipment=shipment,
        new_status=ShipmentStatusChoices.DISPATCHED,
        location="Mumbai Fulfillment Center",
        actor=seller_user,
    )
    assert shipment.status == ShipmentStatusChoices.DISPATCHED
    assert shipment.dispatched_at is not None

    # Step 3: In Transit
    shipment = ShipmentService.update_shipment_status(
        shipment=shipment,
        new_status=ShipmentStatusChoices.IN_TRANSIT,
        location="Pune Transit Hub",
        actor=seller_user,
    )
    assert shipment.status == ShipmentStatusChoices.IN_TRANSIT

    # Step 4: Out for Delivery
    shipment = ShipmentService.update_shipment_status(
        shipment=shipment,
        new_status=ShipmentStatusChoices.OUT_FOR_DELIVERY,
        location="Local Delivery Station",
        actor=seller_user,
    )
    assert shipment.status == ShipmentStatusChoices.OUT_FOR_DELIVERY

    # Step 5: Delivered
    shipment = ShipmentService.update_shipment_status(
        shipment=shipment,
        new_status=ShipmentStatusChoices.DELIVERED,
        location="Customer Doorstep",
        actor=seller_user,
    )
    assert shipment.status == ShipmentStatusChoices.DELIVERED
    assert shipment.delivered_at is not None
    # All 5 events recorded in chronological history
    assert shipment.tracking_events.count() == 5


@pytest.mark.django_db
def test_invalid_status_transition_rejected(multi_seller_order, seller_user):
    order, item_a, _ = multi_seller_order

    shipment = ShipmentService.create_seller_shipment(
        order=order,
        seller=seller_user,
        items_payload=[{"order_item_id": str(item_a.id), "quantity": 2}],
        carrier=CarrierChoices.OTHER,
        dispatch_immediately=False,
    )
    assert shipment.status == ShipmentStatusChoices.CREATED

    # Attempt direct jump from CREATED to DELIVERED (invalid from CREATED)
    with pytest.raises(DjangoValidationError) as exc:
        ShipmentService.update_shipment_status(
            shipment=shipment,
            new_status=ShipmentStatusChoices.DELIVERED,
        )
    assert "Cannot transition shipment" in str(exc.value)


@pytest.mark.django_db
def test_terminal_delivered_shipment_cannot_be_mutated(multi_seller_order, seller_user):
    order, item_a, _ = multi_seller_order

    shipment = ShipmentService.create_seller_shipment(
        order=order,
        seller=seller_user,
        items_payload=[{"order_item_id": str(item_a.id), "quantity": 2}],
        carrier=CarrierChoices.OTHER,
        dispatch_immediately=True,
    )
    ShipmentService.update_shipment_status(shipment, ShipmentStatusChoices.DELIVERED)

    with pytest.raises(DjangoValidationError) as exc:
        ShipmentService.update_shipment_status(shipment, ShipmentStatusChoices.IN_TRANSIT)
    assert "Cannot transition shipment" in str(exc.value)


@pytest.mark.django_db
def test_idempotent_duplicate_external_checkpoint(multi_seller_order, seller_user):
    order, item_a, _ = multi_seller_order

    shipment = ShipmentService.create_seller_shipment(
        order=order,
        seller=seller_user,
        items_payload=[{"order_item_id": str(item_a.id), "quantity": 2}],
        carrier=CarrierChoices.OTHER,
    )

    evt1 = ShipmentService.add_tracking_event(
        shipment=shipment,
        status=ShipmentStatusChoices.IN_TRANSIT,
        description="Scanned at sorting hub",
        external_checkpoint_id="CHK-998877",
    )
    # Replay with same checkpoint ID
    evt2 = ShipmentService.add_tracking_event(
        shipment=shipment,
        status=ShipmentStatusChoices.IN_TRANSIT,
        description="Duplicate webhook payload",
        external_checkpoint_id="CHK-998877",
    )
    assert evt1.id == evt2.id
    # Only 1 unique checkpoint recorded
    assert shipment.tracking_events.filter(external_checkpoint_id="CHK-998877").count() == 1


# ==============================================================================
# 4. ORDER STATUS SYNCHRONIZATION & PAYMENT INDEPENDENCE TESTS
# ==============================================================================

@pytest.mark.django_db
def test_order_completion_requires_all_sellers_delivered(multi_seller_order, seller_user, seller_b):
    """
    Verifies that multi-seller orders are marked COMPLETED only when ALL items from
    all sellers are fully delivered.
    """
    order, item_a, item_b = multi_seller_order

    # Seller A ships item A (2 units)
    shipment_a = ShipmentService.create_seller_shipment(
        order=order,
        seller=seller_user,
        items_payload=[{"order_item_id": str(item_a.id), "quantity": 2}],
        carrier=CarrierChoices.BLUE_DART,
        dispatch_immediately=True,
    )
    order.refresh_from_db()
    assert order.status == OrderStatusChoices.PROCESSING

    # Seller B ships item B (1 unit)
    shipment_b = ShipmentService.create_seller_shipment(
        order=order,
        seller=seller_b,
        items_payload=[{"order_item_id": str(item_b.id), "quantity": 1}],
        carrier=CarrierChoices.DELHIVERY,
        dispatch_immediately=True,
    )
    order.refresh_from_db()
    assert order.status == OrderStatusChoices.PROCESSING

    # Seller A delivers their shipment
    ShipmentService.update_shipment_status(shipment_a, ShipmentStatusChoices.DELIVERED)
    order.refresh_from_db()
    # Order MUST remain PROCESSING because Seller B has not delivered yet!
    assert order.status == OrderStatusChoices.PROCESSING

    # Seller B delivers their shipment
    ShipmentService.update_shipment_status(shipment_b, ShipmentStatusChoices.DELIVERED)
    order.refresh_from_db()
    # Now that every item unit across both sellers is delivered, order becomes COMPLETED
    assert order.status == OrderStatusChoices.COMPLETED


@pytest.mark.django_db
def test_delivery_does_not_mutate_payment_or_cod_status(multi_seller_order, seller_user, seller_b):
    """
    Critical specification requirement:
    Never mark an order paid or COD collected merely because a shipment is delivered.
    """
    order, item_a, item_b = multi_seller_order
    assert order.payment_status == PaymentStatusChoices.PENDING
    assert order.cod_collection_status == CODCollectionStatusChoices.PENDING

    shipment_a = ShipmentService.create_seller_shipment(
        order=order,
        seller=seller_user,
        items_payload=[{"order_item_id": str(item_a.id), "quantity": 2}],
        carrier=CarrierChoices.OTHER,
        dispatch_immediately=True,
    )
    shipment_b = ShipmentService.create_seller_shipment(
        order=order,
        seller=seller_b,
        items_payload=[{"order_item_id": str(item_b.id), "quantity": 1}],
        carrier=CarrierChoices.OTHER,
        dispatch_immediately=True,
    )

    ShipmentService.update_shipment_status(shipment_a, ShipmentStatusChoices.DELIVERED)
    ShipmentService.update_shipment_status(shipment_b, ShipmentStatusChoices.DELIVERED)

    order.refresh_from_db()
    assert order.status == OrderStatusChoices.COMPLETED
    # Payment and COD statuses MUST remain untouched
    assert order.payment_status == PaymentStatusChoices.PENDING
    assert order.cod_collection_status == CODCollectionStatusChoices.PENDING


# ==============================================================================
# 5. REST API ENDPOINTS & AUTHORIZATION PERMISSION TESTS
# ==============================================================================

@pytest.mark.django_db
def test_seller_shipment_create_and_list_api(multi_seller_order, seller_auth_client, seller_b_client):
    order, item_a, item_b = multi_seller_order

    url = f"/api/v1/marketplace/seller/orders/{order.id}/shipments/"
    payload = {
        "carrier": "BLUE_DART",
        "tracking_number": "BD-API-123456",
        "dispatch_immediately": True,
        "items": [{"order_item_id": str(item_a.id), "quantity": 2}],
    }

    # Seller A creates shipment for their item
    res = seller_auth_client.post(url, payload, format="json")
    assert res.status_code == status.HTTP_201_CREATED
    assert res.data["shipment"]["tracking_number"] == "BD-API-123456"
    assert res.data["shipment"]["status"] == "DISPATCHED"

    # Seller A lists shipments for this order -> sees only their shipment
    res_list = seller_auth_client.get(url)
    assert res_list.status_code == status.HTTP_200_OK
    assert len(res_list.data) == 1

    # Seller B lists shipments for this order -> sees 0 shipments (multi-seller privacy)
    res_b_list = seller_b_client.get(url)
    assert res_b_list.status_code == status.HTTP_200_OK
    assert len(res_b_list.data) == 0


@pytest.mark.django_db
def test_unrelated_seller_cannot_update_another_sellers_shipment(multi_seller_order, seller_auth_client, seller_b_client):
    order, item_a, _ = multi_seller_order

    # Seller A creates a shipment
    create_res = seller_auth_client.post(
        f"/api/v1/marketplace/seller/orders/{order.id}/shipments/",
        {
            "carrier": "OTHER",
            "tracking_number": "TRK-SELLER-A",
            "dispatch_immediately": False,
            "items": [{"order_item_id": str(item_a.id), "quantity": 2}],
        },
        format="json",
    )
    shipment_id = create_res.data["shipment"]["id"]

    # Seller B attempts to advance Seller A's shipment
    update_url = f"/api/v1/marketplace/seller/shipments/{shipment_id}/status/"
    res_forbidden = seller_b_client.patch(update_url, {"status": "DISPATCHED"}, format="json")
    assert res_forbidden.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_buyer_views_shipments_and_unrelated_buyer_rejected(multi_seller_order, buyer_auth_client, unrelated_buyer_client, seller_auth_client):
    order, item_a, _ = multi_seller_order

    # Create a shipment
    seller_auth_client.post(
        f"/api/v1/marketplace/seller/orders/{order.id}/shipments/",
        {
            "carrier": "BLUE_DART",
            "tracking_number": "BD-BUYER-VIEW-123",
            "dispatch_immediately": True,
            "items": [{"order_item_id": str(item_a.id), "quantity": 2}],
        },
        format="json",
    )

    buyer_url = f"/api/v1/marketplace/buyer/orders/{order.id}/shipments/"

    # Authorized buyer views shipments
    res = buyer_auth_client.get(buyer_url)
    assert res.status_code == status.HTTP_200_OK
    assert len(res.data) == 1
    assert res.data[0]["tracking_number"] == "BD-BUYER-VIEW-123"

    # Unrelated buyer is rejected with HTTP 403
    res_intruder = unrelated_buyer_client.get(buyer_url)
    assert res_intruder.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_tracking_lookup_endpoint(multi_seller_order, buyer_auth_client, seller_auth_client, unrelated_buyer_client):
    order, item_a, _ = multi_seller_order

    create_res = seller_auth_client.post(
        f"/api/v1/marketplace/seller/orders/{order.id}/shipments/",
        {
            "carrier": "DELHIVERY",
            "tracking_number": "DEL-LOOKUP-9988",
            "dispatch_immediately": True,
            "items": [{"order_item_id": str(item_a.id), "quantity": 2}],
        },
        format="json",
    )
    tracking_num = create_res.data["shipment"]["tracking_number"]
    track_url = f"/api/v1/marketplace/shipments/track/{tracking_num}/"

    # Buyer of the order can track
    res_buyer = buyer_auth_client.get(track_url)
    assert res_buyer.status_code == status.HTTP_200_OK
    assert res_buyer.data["tracking_number"] == "DEL-LOOKUP-9988"

    # Seller of the shipment can track
    res_seller = seller_auth_client.get(track_url)
    assert res_seller.status_code == status.HTTP_200_OK

    # Unrelated user cannot track private shipment
    res_unrelated = unrelated_buyer_client.get(track_url)
    assert res_unrelated.status_code == status.HTTP_403_FORBIDDEN
