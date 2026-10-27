import pytest
import uuid
import threading
from decimal import Decimal
from rest_framework import status
from apps.catalogue.models import PartCategory, Part, VehicleMake, VehicleModel
from apps.marketplace.models import (
    SparePartListing,
    VehicleListing,
    ListingStatusChoices,
    Order,
    OrderItem,
    OrderStatusChoices,
    StockMovement,
    StockMovementReasonChoices,
)


@pytest.fixture
def brake_category(db):
    return PartCategory.objects.create(name="Braking", slug="braking")


@pytest.fixture
def approved_part(db, seller_user, brake_category):
    return SparePartListing.objects.create(
        seller=seller_user,
        name="Bosch High-Performance Brake Pads",
        brand="Bosch",
        mpn="BP-101",
        category=brake_category,
        price=Decimal("2000.00"),
        currency="INR",
        hsn_code="8708",
        gst_rate=Decimal("18.00"),
        status=ListingStatusChoices.APPROVED,
        is_active=True,
        stock_quantity=5,
    )


@pytest.fixture
def approved_vehicle(db, seller_user):
    make = VehicleMake.objects.create(name="BMW", country_of_origin="Germany")
    model = VehicleModel.objects.create(make=make, name="3 Series", year_start=2020)
    return VehicleListing.objects.create(
        seller=seller_user,
        title="2022 BMW 3 Series 330i M Sport",
        make=make,
        model=model,
        year=2022,
        price=Decimal("45000.00"),
        currency="GBP",
        status=ListingStatusChoices.APPROVED,
        is_active=True,
    )


def valid_shipping_payload(listing_id, quantity=1, **kwargs):
    payload = {
        "items": [{"listing_id": str(listing_id), "quantity": quantity}],
        "place_of_supply": "MH",
        "currency": "INR",
        "shipping_name": "Rohan Gupta",
        "shipping_phone": "+91 9876543210",
        "shipping_address_line1": "Flat 4B, Greenfield Heights",
        "shipping_city": "Mumbai",
        "shipping_state": "MH",
        "shipping_postal_code": "400050",
        "shipping_country": "India",
    }
    payload.update(kwargs)
    return payload


# =============================================================================
# PHASE 4 TASK 2: AUTHORITATIVE CHECKOUT & TRANSACTION SAFETY TEST SUITE
# =============================================================================

class TestMarketplaceCheckout:

    # 1. Successful Authenticated Checkout
    def test_successful_authenticated_checkout(self, buyer_auth_client, buyer_user, approved_part):
        payload = valid_shipping_payload(approved_part.id, quantity=2)
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")

        assert res.status_code == status.HTTP_201_CREATED
        data = res.json()
        assert data["status"] == "success"
        order_data = data["order"]
        assert order_data["buyer_email"] == buyer_user.email
        assert order_data["shipping_name"] == "Rohan Gupta"

        # 2 units * 2000 = 4000.00 taxable, 18% GST = 720.00 -> total = 4720.00
        assert Decimal(order_data["subtotal_taxable_amount"]) == Decimal("4000.00")
        assert Decimal(order_data["total_tax_amount"]) == Decimal("720.00")
        assert Decimal(order_data["total_amount"]) == Decimal("4720.00")

        # Database assertions
        order = Order.objects.get(id=order_data["id"])
        assert order.buyer == buyer_user
        assert order.items.count() == 1
        item = order.items.first()
        assert item.listing == approved_part
        assert item.quantity == 2
        assert item.total_amount == Decimal("4720.00")

    # 2. Unauthenticated Checkout Rejection
    def test_unauthenticated_checkout_rejection(self, api_client, approved_part):
        payload = valid_shipping_payload(approved_part.id, quantity=1)
        res = api_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

    # 3. Invalid or Missing Required Shipping / Contact Details
    @pytest.mark.parametrize("missing_field", [
        "shipping_name",
        "shipping_phone",
        "shipping_address_line1",
        "shipping_city",
        "shipping_postal_code",
    ])
    def test_missing_required_shipping_details(self, buyer_auth_client, approved_part, missing_field):
        payload = valid_shipping_payload(approved_part.id, quantity=1)
        payload[missing_field] = ""
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")

        assert res.status_code == status.HTTP_400_BAD_REQUEST
        data = res.json()
        assert "field_errors" in data
        assert missing_field in data["field_errors"]
        assert Order.objects.count() == 0

    def test_invalid_phone_number_rejected(self, buyer_auth_client, approved_part):
        payload = valid_shipping_payload(approved_part.id, shipping_phone="123")
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "shipping_phone" in res.json().get("field_errors", {})

    # 4. Invalid Quantities & Malformed Payloads
    @pytest.mark.parametrize("bad_quantity", [0, -1, -5])
    def test_invalid_quantities_rejected(self, buyer_auth_client, approved_part, bad_quantity):
        payload = valid_shipping_payload(approved_part.id, quantity=bad_quantity)
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_empty_items_payload_rejected(self, buyer_auth_client):
        payload = valid_shipping_payload(uuid.uuid4())
        payload["items"] = []
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    # 5. Inactive, Unapproved or Missing Spare Part Listings
    def test_unapproved_listing_rejected(self, buyer_auth_client, approved_part):
        approved_part.status = ListingStatusChoices.PENDING_APPROVAL
        approved_part.save()

        payload = valid_shipping_payload(approved_part.id)
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "not available for purchase" in res.json()["error"]

    def test_missing_listing_uuid_rejected(self, buyer_auth_client):
        missing_id = uuid.uuid4()
        payload = valid_shipping_payload(missing_id)
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        assert res.status_code == status.HTTP_404_NOT_FOUND
        assert f"Spare part listing with ID {missing_id} not found" in res.json()["error"]

    def test_inactive_listing_rejected(self, buyer_auth_client, approved_part):
        approved_part.is_active = False
        approved_part.save()

        payload = valid_shipping_payload(approved_part.id)
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        assert res.status_code == status.HTTP_404_NOT_FOUND

    # 6. Insufficient Stock
    def test_insufficient_stock_rejection(self, buyer_auth_client, approved_part):
        assert approved_part.stock_quantity == 5
        payload = valid_shipping_payload(approved_part.id, quantity=6)
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")

        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "Insufficient stock" in res.json()["error"]
        approved_part.refresh_from_db()
        assert approved_part.stock_quantity == 5
        assert Order.objects.count() == 0

    # 7. Price Changes Between Calculation & Checkout (HTTP 409 PRICE_CHANGED)
    def test_price_change_guard_rejects_and_requires_reconfirmation(self, buyer_auth_client, approved_part):
        # 1 unit * 2000 = 2000 taxable + 360 GST = 2360.00
        original_expected_total = "2360.00"

        # Seller changes price to 2500.00 before buyer submits
        approved_part.price = Decimal("2500.00")
        approved_part.save()
        # New total: 2500 + 450 GST = 2950.00

        payload = valid_shipping_payload(approved_part.id, quantity=1, expected_total_amount=original_expected_total)
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")

        assert res.status_code == status.HTTP_409_CONFLICT
        data = res.json()
        assert data["code"] == "PRICE_CHANGED"
        assert data["reviewed_total_amount"] == original_expected_total
        assert Decimal(data["updated_total_amount"]) == Decimal("2950.00")
        assert Order.objects.count() == 0

        # Buyer explicitly confirms updated total -> succeeds!
        payload["expected_total_amount"] = "2950.00"
        res_confirmed = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        assert res_confirmed.status_code == status.HTTP_201_CREATED
        assert Decimal(res_confirmed.json()["order"]["total_amount"]) == Decimal("2950.00")

    # 8. Tax Changes Between Calculation & Checkout
    def test_tax_change_guard_rejects_and_requires_reconfirmation(self, buyer_auth_client, approved_part):
        # Initial: 2000 at 18% = 2360.00
        original_expected = "2360.00"

        # Statutory classification updated to 28% GST: 2000 + 560 = 2560.00
        approved_part.gst_rate = Decimal("28.00")
        approved_part.save()

        payload = valid_shipping_payload(approved_part.id, quantity=1, expected_total_amount=original_expected)
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")

        assert res.status_code == status.HTTP_409_CONFLICT
        data = res.json()
        assert data["code"] == "PRICE_CHANGED"
        assert Decimal(data["updated_total_amount"]) == Decimal("2560.00")

    # 9. Correct Server-Calculated Totals & Order Items (Tampering Ignored)
    def test_client_tampering_of_amounts_ignored(self, buyer_auth_client, approved_part):
        payload = valid_shipping_payload(
            approved_part.id,
            quantity=1,
            subtotal_taxable_amount="1.00",
            total_tax_amount="0.50",
            total_amount="1.50",
            gst_rate="0.00",
        )
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        assert res.status_code == status.HTTP_201_CREATED
        order_data = res.json()["order"]
        # Must reflect server-calculated values (2000 + 360 = 2360)
        assert Decimal(order_data["subtotal_taxable_amount"]) == Decimal("2000.00")
        assert Decimal(order_data["total_tax_amount"]) == Decimal("360.00")
        assert Decimal(order_data["total_amount"]) == Decimal("2360.00")

    # 10. Correct Stock Deduction & Movement Audit
    def test_stock_deduction_and_movement_audit(self, buyer_auth_client, approved_part):
        initial_stock = approved_part.stock_quantity
        payload = valid_shipping_payload(approved_part.id, quantity=2)
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        assert res.status_code == status.HTTP_201_CREATED

        approved_part.refresh_from_db()
        assert approved_part.stock_quantity == initial_stock - 2

        # Verify StockMovement audit log
        movement = StockMovement.objects.filter(listing=approved_part).order_by("-created_at").first()
        assert movement is not None
        assert movement.delta == -2
        assert movement.reason == StockMovementReasonChoices.SALE
        assert "Customer order" in movement.note

    # 11. Rollback on Operation Failure
    def test_rollback_on_partial_failure(self, buyer_auth_client, approved_part, seller_user, brake_category):
        second_part = SparePartListing.objects.create(
            seller=seller_user,
            name="Clutch Kit",
            brand="LuK",
            mpn="CK-200",
            category=brake_category,
            price=Decimal("5000.00"),
            currency="INR",
            status=ListingStatusChoices.APPROVED,
            is_active=True,
            stock_quantity=1,
        )

        initial_part_stock = approved_part.stock_quantity
        initial_second_stock = second_part.stock_quantity

        # Request 1 unit of approved_part (valid) and 5 units of second_part (exceeds stock 1)
        payload = {
            "items": [
                {"listing_id": str(approved_part.id), "quantity": 1},
                {"listing_id": str(second_part.id), "quantity": 5},
            ],
            "place_of_supply": "MH",
            "currency": "INR",
            "shipping_name": "Test User",
            "shipping_phone": "+91 9876543210",
            "shipping_address_line1": "Street 1",
            "shipping_city": "Mumbai",
            "shipping_postal_code": "400001",
        }

        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        assert res.status_code == status.HTTP_400_BAD_REQUEST

        # Atomic rollback verification
        approved_part.refresh_from_db()
        second_part.refresh_from_db()
        assert approved_part.stock_quantity == initial_part_stock
        assert second_part.stock_quantity == initial_second_stock
        assert Order.objects.count() == 0

    # 12. Duplicate Submissions & Idempotent Retries
    def test_idempotent_duplicate_submission(self, buyer_auth_client, approved_part):
        idempotency_key = f"idem-key-{uuid.uuid4()}"
        payload = valid_shipping_payload(approved_part.id, quantity=1, idempotency_key=idempotency_key)

        # 1st request
        res1 = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        assert res1.status_code == status.HTTP_201_CREATED
        order1 = res1.json()["order"]
        approved_part.refresh_from_db()
        stock_after_first = approved_part.stock_quantity

        # 2nd request with exact same idempotency_key (e.g. repeated click / network retry)
        res2 = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        assert res2.status_code == status.HTTP_200_OK
        data2 = res2.json()
        assert data2["replayed"] is True
        assert data2["order"]["id"] == order1["id"]
        assert data2["order"]["order_number"] == order1["order_number"]

        # Stock is NOT deducted a second time
        approved_part.refresh_from_db()
        assert approved_part.stock_quantity == stock_after_first
        assert Order.objects.count() == 1

    # 13. Order Status is PENDING_CONFIRMATION (Never Falsely Marked as Paid)
    def test_order_status_is_pending_confirmation(self, buyer_auth_client, approved_part):
        payload = valid_shipping_payload(approved_part.id, quantity=1)
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        assert res.status_code == status.HTTP_201_CREATED

        order = Order.objects.get(id=res.json()["order"]["id"])
        assert order.status == OrderStatusChoices.PENDING_CONFIRMATION
        assert order.status != "PAID"
        assert res.json()["order"]["status"] == "PENDING_CONFIRMATION"

    # 14. Vehicle Checkout Rejection & Unchanged Vehicle Enquiry Behavior
    def test_vehicle_listing_rejected_at_checkout_and_enquiry_works(
        self, buyer_auth_client, buyer_user, approved_vehicle
    ):
        # 1. Calculation preview rejects vehicle
        calc_res = buyer_auth_client.post(
            "/api/v1/marketplace/orders/calculate/",
            {"items": [{"listing_id": str(approved_vehicle.id), "quantity": 1}], "currency": "GBP"},
            format="json",
        )
        assert calc_res.status_code == status.HTTP_404_NOT_FOUND

        # 2. Checkout rejects vehicle
        checkout_res = buyer_auth_client.post(
            "/api/v1/marketplace/orders/checkout/",
            valid_shipping_payload(approved_vehicle.id, quantity=1, currency="GBP"),
            format="json",
        )
        assert checkout_res.status_code == status.HTTP_404_NOT_FOUND

        # 3. Vehicle enquiry works seamlessly as designed
        enquiry_res = buyer_auth_client.post(
            f"/api/v1/marketplace/vehicles/{approved_vehicle.id}/enquire/",
            {
                "message": "Hi, I am interested in viewing this BMW 330i. Is a test drive available this Saturday?",
                "preferred_contact_method": "EMAIL",
            },
            format="json",
        )
        assert enquiry_res.status_code == status.HTTP_201_CREATED
        assert enquiry_res.json()["status"] == "NEW"

    # 15. Buyer Order History & Detail Endpoints
    def test_buyer_order_history_and_detail_lookup(self, buyer_auth_client, buyer_user, approved_part):
        payload = valid_shipping_payload(approved_part.id, quantity=1)
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        order_number = res.json()["order"]["order_number"]
        order_id = res.json()["order"]["id"]

        # List orders
        list_res = buyer_auth_client.get("/api/v1/marketplace/orders/")
        assert list_res.status_code == status.HTTP_200_OK
        orders_data = list_res.json()
        order_list = orders_data.get("results", orders_data) if isinstance(orders_data, dict) else orders_data
        assert any(o["order_number"] == order_number for o in order_list)

        # Lookup by order_number
        detail_res = buyer_auth_client.get(f"/api/v1/marketplace/orders/{order_number}/")
        assert detail_res.status_code == status.HTTP_200_OK
        assert detail_res.json()["id"] == order_id

        # Lookup by UUID
        uuid_res = buyer_auth_client.get(f"/api/v1/marketplace/orders/{order_id}/")
        assert uuid_res.status_code == status.HTTP_200_OK
        assert uuid_res.json()["order_number"] == order_number
