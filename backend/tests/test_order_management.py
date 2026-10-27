import pytest
import uuid
from decimal import Decimal
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
    StockMovement,
    StockMovementReasonChoices,
)


@pytest.fixture
def brake_category(db):
    return PartCategory.objects.create(name="Braking Systems", slug="braking-systems")


@pytest.fixture
def second_seller(db):
    user = User.objects.create_user(
        email='seller2@driverxtra.com',
        password='SecurePassword123!',
        first_name='Marcus',
        last_name='Vendor',
        phone_number='+447000000088',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.SELLER)
    return user


@pytest.fixture
def second_seller_client(second_seller):
    client = APIClient()
    client.force_authenticate(user=second_seller)
    return client


@pytest.fixture
def third_unrelated_seller(db):
    user = User.objects.create_user(
        email='unrelated@driverxtra.com',
        password='SecurePassword123!',
        first_name='Unrelated',
        last_name='Seller',
        phone_number='+447000000099',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.SELLER)
    return user


@pytest.fixture
def unrelated_seller_client(third_unrelated_seller):
    client = APIClient()
    client.force_authenticate(user=third_unrelated_seller)
    return client


@pytest.fixture
def another_buyer(db):
    user = User.objects.create_user(
        email='anotherbuyer@driverxtra.com',
        password='SecurePassword123!',
        first_name='Alice',
        last_name='Customer',
        phone_number='+447000000055',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.fixture
def another_buyer_client(another_buyer):
    client = APIClient()
    client.force_authenticate(user=another_buyer)
    return client


@pytest.fixture
def seller_a_part(db, seller_user, brake_category):
    return SparePartListing.objects.create(
        seller=seller_user,
        name="Brembo Front Brake Disc",
        brand="Brembo",
        mpn="BR-001",
        category=brake_category,
        price=Decimal("1000.00"),
        currency="INR",
        hsn_code="8708",
        gst_rate=Decimal("18.00"),
        status=ListingStatusChoices.APPROVED,
        is_active=True,
        stock_quantity=10,
    )


@pytest.fixture
def seller_b_part(db, second_seller, brake_category):
    return SparePartListing.objects.create(
        seller=second_seller,
        name="Ferodo Ceramic Brake Pads",
        brand="Ferodo",
        mpn="FD-002",
        category=brake_category,
        price=Decimal("500.00"),
        currency="INR",
        hsn_code="8708",
        gst_rate=Decimal("18.00"),
        status=ListingStatusChoices.APPROVED,
        is_active=True,
        stock_quantity=10,
    )


def build_checkout_payload(items, **kwargs):
    payload = {
        "items": items,
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
# PHASE 4 TASK 3: ORDER HISTORY, DETAILS & SELLER ORDER MANAGEMENT TEST SUITE
# =============================================================================

class TestOrderManagement:

    # -------------------------------------------------------------------------
    # 1. Buyer Order History & Detail Access
    # -------------------------------------------------------------------------

    def test_buyer_order_history_and_isolation(
        self, buyer_auth_client, buyer_user, another_buyer, another_buyer_client, seller_a_part
    ):
        """Authenticated buyer sees only their own orders in history."""
        # Buyer 1 places an order
        res1 = buyer_auth_client.post(
            "/api/v1/marketplace/orders/checkout/",
            build_checkout_payload([{"listing_id": str(seller_a_part.id), "quantity": 1}]),
            format="json",
        )
        assert res1.status_code == status.HTTP_201_CREATED
        order1_num = res1.json()["order"]["order_number"]

        # Buyer 2 places an order
        res2 = another_buyer_client.post(
            "/api/v1/marketplace/orders/checkout/",
            build_checkout_payload([{"listing_id": str(seller_a_part.id), "quantity": 1}]),
            format="json",
        )
        assert res2.status_code == status.HTTP_201_CREATED
        order2_num = res2.json()["order"]["order_number"]

        # Buyer 1 queries history
        list_res1 = buyer_auth_client.get("/api/v1/marketplace/orders/")
        assert list_res1.status_code == status.HTTP_200_OK
        orders1 = list_res1.json()
        if isinstance(orders1, dict) and "results" in orders1:
            orders1 = orders1["results"]
        order_numbers1 = [o["order_number"] for o in orders1]
        assert order1_num in order_numbers1
        assert order2_num not in order_numbers1

        # Buyer 2 queries history
        list_res2 = another_buyer_client.get("/api/v1/marketplace/orders/")
        assert list_res2.status_code == status.HTTP_200_OK
        orders2 = list_res2.json()
        if isinstance(orders2, dict) and "results" in orders2:
            orders2 = orders2["results"]
        order_numbers2 = [o["order_number"] for o in orders2]
        assert order2_num in order_numbers2
        assert order1_num not in order_numbers2

    def test_buyer_order_detail_view_and_seller_info(
        self, buyer_auth_client, buyer_user, seller_user, seller_a_part
    ):
        """Order detail displays items, quantities, prices, taxes, totals, delivery & seller info."""
        res = buyer_auth_client.post(
            "/api/v1/marketplace/orders/checkout/",
            build_checkout_payload([{"listing_id": str(seller_a_part.id), "quantity": 2}]),
            format="json",
        )
        assert res.status_code == status.HTTP_201_CREATED
        order_data = res.json()["order"]
        order_id = order_data["id"]
        order_number = order_data["order_number"]

        # Lookup by UUID
        detail_res = buyer_auth_client.get(f"/api/v1/marketplace/orders/{order_id}/")
        assert detail_res.status_code == status.HTTP_200_OK
        d = detail_res.json()
        assert d["order_number"] == order_number
        assert d["shipping_name"] == "Rohan Gupta"
        assert d["shipping_city"] == "Mumbai"
        assert d["status"] == OrderStatusChoices.PENDING_CONFIRMATION
        assert Decimal(d["total_amount"]) == Decimal("2360.00")  # 2000 + 360 GST

        # Verify item attributes & seller info
        assert len(d["items"]) == 1
        item = d["items"][0]
        assert item["title"] == "Brembo Front Brake Disc"
        assert item["brand"] == "Brembo"
        assert item["mpn"] == "BR-001"
        assert item["hsn_code"] == "8708"
        assert Decimal(item["unit_price"]) == Decimal("1000.00")
        assert item["quantity"] == 2
        assert Decimal(item["taxable_amount"]) == Decimal("2000.00")
        assert Decimal(item["tax_amount"]) == Decimal("360.00")
        assert Decimal(item["total_amount"]) == Decimal("2360.00")
        assert item["seller_name"] == seller_user.full_name or seller_user.email
        assert item["seller_id"] == str(seller_user.id)
        assert item["listing_id"] == str(seller_a_part.id)

        # Lookup by order_number string
        detail_num_res = buyer_auth_client.get(f"/api/v1/marketplace/orders/{order_number}/")
        assert detail_num_res.status_code == status.HTTP_200_OK
        assert detail_num_res.json()["id"] == order_id

    def test_unauthorized_buyer_order_lookup_rejected(
        self, buyer_auth_client, another_buyer_client, seller_a_part
    ):
        """A buyer cannot access another buyer's order details (returns 404)."""
        res = buyer_auth_client.post(
            "/api/v1/marketplace/orders/checkout/",
            build_checkout_payload([{"listing_id": str(seller_a_part.id), "quantity": 1}]),
            format="json",
        )
        assert res.status_code == status.HTTP_201_CREATED
        order_id = res.json()["order"]["id"]

        # Other buyer attempts lookup
        forbidden_res = another_buyer_client.get(f"/api/v1/marketplace/orders/{order_id}/")
        assert forbidden_res.status_code == status.HTTP_404_NOT_FOUND

    # -------------------------------------------------------------------------
    # 2. Buyer Order Cancellation & Restocking
    # -------------------------------------------------------------------------

    def test_buyer_cancel_pending_order_and_restock(
        self, buyer_auth_client, buyer_user, seller_a_part
    ):
        """Buyer can cancel an order in PENDING_CONFIRMATION, restocking inventory."""
        seller_a_part.refresh_from_db()
        initial_stock = seller_a_part.stock_quantity

        # Checkout 2 units
        res = buyer_auth_client.post(
            "/api/v1/marketplace/orders/checkout/",
            build_checkout_payload([{"listing_id": str(seller_a_part.id), "quantity": 2}]),
            format="json",
        )
        assert res.status_code == status.HTTP_201_CREATED
        order_id = res.json()["order"]["id"]

        seller_a_part.refresh_from_db()
        assert seller_a_part.stock_quantity == initial_stock - 2

        # Buyer cancels order
        cancel_res = buyer_auth_client.post(f"/api/v1/marketplace/orders/{order_id}/cancel/")
        assert cancel_res.status_code == status.HTTP_200_OK
        assert cancel_res.json()["status"] == "success"
        assert cancel_res.json()["order"]["status"] == OrderStatusChoices.CANCELLED

        # Stock is restored!
        seller_a_part.refresh_from_db()
        assert seller_a_part.stock_quantity == initial_stock

        # StockMovement log reflects RETURN
        last_movement = StockMovement.objects.filter(listing=seller_a_part).order_by('-created_at').first()
        assert last_movement.delta == 2
        assert last_movement.reason == StockMovementReasonChoices.RETURN

    def test_buyer_cannot_cancel_confirmed_or_completed_order(
        self, buyer_auth_client, seller_auth_client, seller_a_part
    ):
        """Buyer cancellation is disallowed once seller confirms the order."""
        res = buyer_auth_client.post(
            "/api/v1/marketplace/orders/checkout/",
            build_checkout_payload([{"listing_id": str(seller_a_part.id), "quantity": 1}]),
            format="json",
        )
        assert res.status_code == status.HTTP_201_CREATED
        order_id = res.json()["order"]["id"]

        # Seller confirms order
        confirm_res = seller_auth_client.patch(
            f"/api/v1/marketplace/seller/orders/{order_id}/status/",
            {"status": OrderStatusChoices.CONFIRMED},
            format="json",
        )
        assert confirm_res.status_code == status.HTTP_200_OK

        # Buyer attempts cancellation -> 400 Bad Request
        cancel_res = buyer_auth_client.post(f"/api/v1/marketplace/orders/{order_id}/cancel/")
        assert cancel_res.status_code == status.HTTP_400_BAD_REQUEST
        assert "CONFIRMED" in cancel_res.json()["error"]

    # -------------------------------------------------------------------------
    # 3. Seller Order Management & Multi-Seller Isolation
    # -------------------------------------------------------------------------

    def test_multi_seller_order_isolation(
        self,
        buyer_auth_client,
        seller_auth_client,
        second_seller_client,
        unrelated_seller_client,
        seller_a_part,
        seller_b_part,
    ):
        """
        In a multi-seller order:
        - Seller A sees only Seller A's items and subtotal/total.
        - Seller B sees only Seller B's items and subtotal/total.
        - Unrelated Seller C sees nothing (404 / empty).
        """
        # Buyer checks out items from Seller A (2 x 1000 = 2000) and Seller B (1 x 500 = 500)
        res = buyer_auth_client.post(
            "/api/v1/marketplace/orders/checkout/",
            build_checkout_payload([
                {"listing_id": str(seller_a_part.id), "quantity": 2},
                {"listing_id": str(seller_b_part.id), "quantity": 1},
            ]),
            format="json",
        )
        assert res.status_code == status.HTTP_201_CREATED
        order_data = res.json()["order"]
        order_id = order_data["id"]
        # Overall order total = (2000 + 360 GST) + (500 + 90 GST) = 2950.00
        assert Decimal(order_data["total_amount"]) == Decimal("2950.00")

        # Seller A queries list
        seller_a_list = seller_auth_client.get("/api/v1/marketplace/seller/orders/")
        assert seller_a_list.status_code == status.HTTP_200_OK
        orders_a = seller_a_list.json()
        if isinstance(orders_a, dict) and "results" in orders_a:
            orders_a = orders_a["results"]
        matching_a = next(o for o in orders_a if o["id"] == order_id)

        # Seller A's view: ONLY 1 item (Seller A's brake disc)
        assert len(matching_a["items"]) == 1
        assert matching_a["items"][0]["title"] == "Brembo Front Brake Disc"
        assert Decimal(matching_a["seller_subtotal_taxable_amount"]) == Decimal("2000.00")
        assert Decimal(matching_a["seller_total_tax_amount"]) == Decimal("360.00")
        assert Decimal(matching_a["seller_total_amount"]) == Decimal("2360.00")
        assert matching_a["seller_item_count"] == 2

        # Seller B queries detail
        seller_b_detail = second_seller_client.get(f"/api/v1/marketplace/seller/orders/{order_id}/")
        assert seller_b_detail.status_code == status.HTTP_200_OK
        b_data = seller_b_detail.json()

        # Seller B's view: ONLY 1 item (Seller B's brake pads)
        assert len(b_data["items"]) == 1
        assert b_data["items"][0]["title"] == "Ferodo Ceramic Brake Pads"
        assert Decimal(b_data["seller_subtotal_taxable_amount"]) == Decimal("500.00")
        assert Decimal(b_data["seller_total_tax_amount"]) == Decimal("90.00")
        assert Decimal(b_data["seller_total_amount"]) == Decimal("590.00")
        assert b_data["seller_item_count"] == 1

        # Unrelated Seller C queries detail -> 404 NOT FOUND
        seller_c_detail = unrelated_seller_client.get(f"/api/v1/marketplace/seller/orders/{order_id}/")
        assert seller_c_detail.status_code == status.HTTP_404_NOT_FOUND

        # Unrelated Seller C list -> does not contain this order
        seller_c_list = unrelated_seller_client.get("/api/v1/marketplace/seller/orders/")
        orders_c = seller_c_list.json()
        if isinstance(orders_c, dict) and "results" in orders_c:
            orders_c = orders_c["results"]
        assert not any(o["id"] == order_id for o in orders_c)

    # -------------------------------------------------------------------------
    # 4. Status Workflow & Valid Transitions
    # -------------------------------------------------------------------------

    def test_seller_status_workflow_transitions(
        self, buyer_auth_client, seller_auth_client, seller_a_part
    ):
        """Test forward transitions: PENDING_CONFIRMATION -> CONFIRMED -> PROCESSING -> COMPLETED."""
        res = buyer_auth_client.post(
            "/api/v1/marketplace/orders/checkout/",
            build_checkout_payload([{"listing_id": str(seller_a_part.id), "quantity": 1}]),
            format="json",
        )
        assert res.status_code == status.HTTP_201_CREATED
        order_id = res.json()["order"]["id"]

        # Initial status
        order = Order.objects.get(id=order_id)
        assert order.status == OrderStatusChoices.PENDING_CONFIRMATION

        # 1. PENDING_CONFIRMATION -> CONFIRMED
        patch1 = seller_auth_client.patch(
            f"/api/v1/marketplace/seller/orders/{order_id}/status/",
            {"status": OrderStatusChoices.CONFIRMED, "notes": "Stock confirmed and allocated."},
            format="json",
        )
        assert patch1.status_code == status.HTTP_200_OK
        assert patch1.json()["order"]["status"] == OrderStatusChoices.CONFIRMED

        # Visible to buyer!
        buyer_view1 = buyer_auth_client.get(f"/api/v1/marketplace/orders/{order_id}/")
        assert buyer_view1.json()["status"] == OrderStatusChoices.CONFIRMED

        # 2. CONFIRMED -> PROCESSING
        patch2 = seller_auth_client.patch(
            f"/api/v1/marketplace/seller/orders/{order_id}/status/",
            {"status": OrderStatusChoices.PROCESSING, "notes": "Packaging item for dispatch."},
            format="json",
        )
        assert patch2.status_code == status.HTTP_200_OK
        assert patch2.json()["order"]["status"] == OrderStatusChoices.PROCESSING

        # Visible to buyer!
        buyer_view2 = buyer_auth_client.get(f"/api/v1/marketplace/orders/{order_id}/")
        assert buyer_view2.json()["status"] == OrderStatusChoices.PROCESSING

        # 3. PROCESSING -> COMPLETED
        patch3 = seller_auth_client.patch(
            f"/api/v1/marketplace/seller/orders/{order_id}/status/",
            {"status": OrderStatusChoices.COMPLETED, "notes": "Delivered successfully."},
            format="json",
        )
        assert patch3.status_code == status.HTTP_200_OK
        assert patch3.json()["order"]["status"] == OrderStatusChoices.COMPLETED

        # Visible to buyer!
        buyer_view3 = buyer_auth_client.get(f"/api/v1/marketplace/orders/{order_id}/")
        assert buyer_view3.json()["status"] == OrderStatusChoices.COMPLETED

    def test_invalid_status_transitions_rejected(
        self, buyer_auth_client, seller_auth_client, seller_a_part
    ):
        """Invalid or skipped transitions are rejected with 400 Bad Request."""
        res = buyer_auth_client.post(
            "/api/v1/marketplace/orders/checkout/",
            build_checkout_payload([{"listing_id": str(seller_a_part.id), "quantity": 1}]),
            format="json",
        )
        assert res.status_code == status.HTTP_201_CREATED
        order_id = res.json()["order"]["id"]

        # Attempt to jump straight from PENDING_CONFIRMATION to COMPLETED (skipping CONFIRMED & PROCESSING)
        bad_jump = seller_auth_client.patch(
            f"/api/v1/marketplace/seller/orders/{order_id}/status/",
            {"status": OrderStatusChoices.COMPLETED},
            format="json",
        )
        assert bad_jump.status_code == status.HTTP_400_BAD_REQUEST

        # Advance to COMPLETED properly
        seller_auth_client.patch(
            f"/api/v1/marketplace/seller/orders/{order_id}/status/",
            {"status": OrderStatusChoices.CONFIRMED},
            format="json",
        )
        seller_auth_client.patch(
            f"/api/v1/marketplace/seller/orders/{order_id}/status/",
            {"status": OrderStatusChoices.PROCESSING},
            format="json",
        )
        seller_auth_client.patch(
            f"/api/v1/marketplace/seller/orders/{order_id}/status/",
            {"status": OrderStatusChoices.COMPLETED},
            format="json",
        )

        # Attempt to transition terminal COMPLETED state back to PENDING_CONFIRMATION
        revert = seller_auth_client.patch(
            f"/api/v1/marketplace/seller/orders/{order_id}/status/",
            {"status": OrderStatusChoices.PENDING_CONFIRMATION},
            format="json",
        )
        assert revert.status_code == status.HTTP_400_BAD_REQUEST

    def test_seller_cancellation_restocks_inventory(
        self, buyer_auth_client, seller_auth_client, seller_a_part
    ):
        """When seller cancels an order, stock is automatically restocked."""
        seller_a_part.refresh_from_db()
        initial_stock = seller_a_part.stock_quantity

        res = buyer_auth_client.post(
            "/api/v1/marketplace/orders/checkout/",
            build_checkout_payload([{"listing_id": str(seller_a_part.id), "quantity": 3}]),
            format="json",
        )
        assert res.status_code == status.HTTP_201_CREATED
        order_id = res.json()["order"]["id"]

        seller_a_part.refresh_from_db()
        assert seller_a_part.stock_quantity == initial_stock - 3

        # Seller confirms order
        seller_auth_client.patch(
            f"/api/v1/marketplace/seller/orders/{order_id}/status/",
            {"status": OrderStatusChoices.CONFIRMED},
            format="json",
        )

        # Seller cancels order
        cancel_res = seller_auth_client.patch(
            f"/api/v1/marketplace/seller/orders/{order_id}/status/",
            {"status": OrderStatusChoices.CANCELLED, "notes": "Buyer requested cancellation before dispatch."},
            format="json",
        )
        assert cancel_res.status_code == status.HTTP_200_OK
        assert cancel_res.json()["order"]["status"] == OrderStatusChoices.CANCELLED

        # Stock is restocked
        seller_a_part.refresh_from_db()
        assert seller_a_part.stock_quantity == initial_stock

    def test_unauthorized_seller_cannot_update_status(
        self, buyer_auth_client, unrelated_seller_client, seller_a_part
    ):
        """A seller who owns no items in an order cannot update its status."""
        res = buyer_auth_client.post(
            "/api/v1/marketplace/orders/checkout/",
            build_checkout_payload([{"listing_id": str(seller_a_part.id), "quantity": 1}]),
            format="json",
        )
        assert res.status_code == status.HTTP_201_CREATED
        order_id = res.json()["order"]["id"]

        # Unrelated seller attempts status update -> 404
        unauth_res = unrelated_seller_client.patch(
            f"/api/v1/marketplace/seller/orders/{order_id}/status/",
            {"status": OrderStatusChoices.CONFIRMED},
            format="json",
        )
        assert unauth_res.status_code == status.HTTP_404_NOT_FOUND

    def test_unauthenticated_requests_rejected(self, api_client, buyer_auth_client, seller_a_part):
        """Unauthenticated requests are rejected with 401."""
        # Unauthenticated buyer list
        res1 = api_client.get("/api/v1/marketplace/orders/")
        assert res1.status_code == status.HTTP_401_UNAUTHORIZED

        # Create order first with auth
        c_res = buyer_auth_client.post(
            "/api/v1/marketplace/orders/checkout/",
            build_checkout_payload([{"listing_id": str(seller_a_part.id), "quantity": 1}]),
            format="json",
        )
        order_id = c_res.json()["order"]["id"]

        # Unauthenticated detail
        res2 = api_client.get(f"/api/v1/marketplace/orders/{order_id}/")
        assert res2.status_code == status.HTTP_401_UNAUTHORIZED

        # Unauthenticated seller list
        res3 = api_client.get("/api/v1/marketplace/seller/orders/")
        assert res3.status_code == status.HTTP_401_UNAUTHORIZED

        # Unauthenticated seller detail
        res4 = api_client.get(f"/api/v1/marketplace/seller/orders/{order_id}/")
        assert res4.status_code == status.HTTP_401_UNAUTHORIZED

        # Unauthenticated seller status update
        res5 = api_client.patch(f"/api/v1/marketplace/seller/orders/{order_id}/status/", {"status": "CONFIRMED"})
        assert res5.status_code == status.HTTP_401_UNAUTHORIZED

        # Unauthenticated buyer cancel
        res6 = api_client.post(f"/api/v1/marketplace/orders/{order_id}/cancel/")
        assert res6.status_code == status.HTTP_401_UNAUTHORIZED
