import hmac
import hashlib
import json
import time
import uuid
import pytest
from decimal import Decimal
from django.conf import settings
from rest_framework import status
from rest_framework.test import APIClient
from apps.identity.models import User, RoleChoices
from apps.catalogue.models import PartCategory
from apps.marketplace.models import (
    SparePartListing,
    ListingStatusChoices,
    Order,
    OrderStatusChoices,
    PaymentMethodChoices,
    PaymentStatusChoices,
    CODCollectionStatusChoices,
    PaymentTransaction,
    PaymentWebhookEvent,
)


@pytest.fixture
def brake_category(db):
    return PartCategory.objects.create(name="Braking Systems", slug="braking-systems")


@pytest.fixture
def in_part(db, seller_user, brake_category):
    return SparePartListing.objects.create(
        seller=seller_user,
        name="Brembo Front Brake Disc (India)",
        brand="Brembo",
        mpn="BR-FD-IN",
        category=brake_category,
        price=Decimal("4000.00"),
        currency="INR",
        hsn_code="8708",
        gst_rate=Decimal("18.00"),
        status=ListingStatusChoices.APPROVED,
        is_active=True,
        stock_quantity=10,
    )


@pytest.fixture
def uk_part(db, seller_user, brake_category):
    return SparePartListing.objects.create(
        seller=seller_user,
        name="Ferodo Racing Brake Pads (UK)",
        brand="Ferodo",
        mpn="FRP-3000",
        category=brake_category,
        price=Decimal("120.00"),
        currency="GBP",
        hsn_code="8708",
        gst_rate=Decimal("0.00"),
        status=ListingStatusChoices.APPROVED,
        is_active=True,
        stock_quantity=10,
    )


@pytest.fixture
def other_buyer_user(db):
    user = User.objects.create_user(
        email='otherbuyer@driverxtra.com',
        password='SecurePassword123!',
        first_name='Oliver',
        last_name='Other',
        phone_number='+447000000099',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.fixture
def other_buyer_client(other_buyer_user):
    client = APIClient()
    client.force_authenticate(user=other_buyer_user)
    return client


@pytest.fixture
def staff_auth_client(staff_user):
    client = APIClient()
    client.force_authenticate(user=staff_user)
    return client


def valid_india_shipping_payload(listing_id, quantity=1, **kwargs):
    payload = {
        "items": [{"listing_id": str(listing_id), "quantity": quantity}],
        "place_of_supply": "MH",
        "currency": "INR",
        "payment_method": "ONLINE",
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


def valid_uk_shipping_payload(listing_id, quantity=1, **kwargs):
    payload = {
        "items": [{"listing_id": str(listing_id), "quantity": quantity}],
        "currency": "GBP",
        "payment_method": "ONLINE",
        "shipping_name": "Arthur Pendelton",
        "shipping_phone": "+44 7911 123456",
        "shipping_address_line1": "221B Baker Street",
        "shipping_city": "London",
        "shipping_state": "Greater London",
        "shipping_postal_code": "NW1 6XE",
        "shipping_country": "United Kingdom",
    }
    payload.update(kwargs)
    return payload


# =============================================================================
# 1. AVAILABLE PAYMENT METHODS & COD ELIGIBILITY
# =============================================================================

class TestPaymentMethodsAndEligibility:

    def test_available_methods_for_india(self, api_client):
        res = api_client.get(
            "/api/v1/marketplace/orders/payment-methods/?country=India&currency=INR&amount=5000.00"
        )
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data["country"] == "IN"
        assert data["currency"] == "INR"

        methods = data["payment_methods"]
        assert len(methods) >= 2

        online = next(m for m in methods if m["code"] == "ONLINE")
        assert online["provider"] == "RAZORPAY"
        assert online["is_available"] is True

        cod = next(m for m in methods if m["code"] == "COD")
        assert cod["is_available"] is True

    def test_available_methods_for_uk(self, api_client):
        res = api_client.get(
            "/api/v1/marketplace/orders/payment-methods/?country=United%20Kingdom&currency=GBP&amount=250.00"
        )
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data["country"] == "GB"
        assert data["currency"] == "GBP"

        methods = data["payment_methods"]
        online = next(m for m in methods if m["code"] == "ONLINE")
        assert online["provider"] == "STRIPE"
        assert online["is_available"] is True

        cod = next(m for m in methods if m["code"] == "COD")
        assert cod["is_available"] is True

    def test_cod_unavailable_when_inr_threshold_exceeded(self, api_client):
        # Default INR limit is 50,000.00
        res = api_client.get(
            "/api/v1/marketplace/orders/payment-methods/?country=India&currency=INR&amount=55000.00"
        )
        assert res.status_code == status.HTTP_200_OK
        methods = res.json()["payment_methods"]
        cod = next(m for m in methods if m["code"] == "COD")
        assert cod["is_available"] is False
        assert "exceeds the maximum" in cod["reason"]

    def test_cod_unavailable_when_gbp_threshold_exceeded(self, api_client):
        # Default GBP limit is 500.00
        res = api_client.get(
            "/api/v1/marketplace/orders/payment-methods/?country=United%20Kingdom&currency=GBP&amount=750.00"
        )
        assert res.status_code == status.HTTP_200_OK
        methods = res.json()["payment_methods"]
        cod = next(m for m in methods if m["code"] == "COD")
        assert cod["is_available"] is False
        assert "exceeds the maximum" in cod["reason"]


# =============================================================================
# 2. COUNTRY & CURRENCY CHECKOUT INTEGRATION
# =============================================================================

class TestCountryAndCurrencyCheckout:

    def test_india_inr_checkout_generates_razorpay_session(self, buyer_auth_client, in_part):
        payload = valid_india_shipping_payload(in_part.id, quantity=2, payment_method="ONLINE")
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")

        assert res.status_code == status.HTTP_201_CREATED
        data = res.json()
        assert data["status"] == "success"

        order = data["order"]
        assert order["currency"] == "INR"
        assert order["payment_method"] == "ONLINE"
        assert order["payment_status"] == "PENDING"

        session = data["payment_session"]
        assert session["provider"] == "RAZORPAY"
        assert "provider_order_id" in session
        assert session["provider_order_id"].startswith("order_")
        assert session["amount"] == "9440.00"  # 2 * 4000 = 8000 + 18% GST (1440) = 9440.00

        # Ledger record created
        db_order = Order.objects.get(id=order["id"])
        tx = PaymentTransaction.objects.filter(order=db_order).first()
        assert tx is not None
        assert tx.provider == "RAZORPAY"
        assert tx.status == PaymentTransaction.StatusChoices.PENDING

    def test_uk_gbp_checkout_generates_stripe_session_and_zero_gst(self, buyer_auth_client, uk_part):
        payload = valid_uk_shipping_payload(uk_part.id, quantity=2, payment_method="ONLINE")
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")

        assert res.status_code == status.HTTP_201_CREATED
        data = res.json()
        assert data["status"] == "success"

        order = data["order"]
        assert order["currency"] == "GBP"
        assert order["payment_method"] == "ONLINE"
        assert Decimal(order["total_tax_amount"]) == Decimal("0.00")
        assert Decimal(order["total_amount"]) == Decimal("240.00")  # 2 * 120.00

        session = data["payment_session"]
        assert session["provider"] == "STRIPE"
        assert "client_secret" in session
        assert session["currency"] == "GBP"

    def test_cross_country_currency_mismatch_rejected(self, buyer_auth_client, in_part, uk_part, monkeypatch):
        from django.conf import settings
        # When conversion is not configured, cross-currency checkout without destination price is rejected
        monkeypatch.setattr(settings, 'CURRENCY_EXCHANGE_RATES', {})

        # 1. Attempt to ship INR item to UK with currency GBP
        res1 = buyer_auth_client.post(
            "/api/v1/marketplace/orders/checkout/",
            valid_uk_shipping_payload(in_part.id, quantity=1, currency="GBP"),
            format="json",
        )
        assert res1.status_code == status.HTTP_400_BAD_REQUEST
        assert "does not match order currency" in res1.json()["error"]

        # 2. Attempt to ship INR item with currency INR to UK destination
        res2 = buyer_auth_client.post(
            "/api/v1/marketplace/orders/checkout/",
            valid_uk_shipping_payload(in_part.id, quantity=1, currency="INR"),
            format="json",
        )
        assert res2.status_code == status.HTTP_400_BAD_REQUEST
        assert "INR currency cannot be used for delivery to the United Kingdom" in res2.json()["error"]


# =============================================================================
# 3. ONLINE PAYMENT SERVER VERIFICATION
# =============================================================================

class TestOnlinePaymentVerification:

    def test_razorpay_valid_signature_marks_order_paid(self, buyer_auth_client, in_part):
        # 1. Create order
        payload = valid_india_shipping_payload(in_part.id, quantity=1, payment_method="ONLINE")
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        order_data = res.json()["order"]
        session_data = res.json()["payment_session"]

        order_id = order_data["id"]
        razorpay_order_id = session_data["provider_order_id"]
        razorpay_payment_id = f"pay_test_{uuid.uuid4().hex[:10]}"

        # Generate HMAC-SHA256 signature using test secret
        secret = getattr(settings, 'RAZORPAY_KEY_SECRET', 'test_razorpay_secret')
        msg = f"{razorpay_order_id}|{razorpay_payment_id}".encode("utf-8")
        valid_signature = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()

        # 2. Verify payment endpoint
        verify_payload = {
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": valid_signature,
        }
        v_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order_id}/payment/verify/",
            verify_payload,
            format="json",
        )
        assert v_res.status_code == status.HTTP_200_OK
        v_data = v_res.json()
        assert v_data["status"] == "success"
        assert v_data["payment_status"] == "PAID"

        # Check DB Order
        order = Order.objects.get(id=order_id)
        assert order.payment_status == PaymentStatusChoices.PAID
        assert order.status == OrderStatusChoices.CONFIRMED
        assert order.paid_at is not None
        assert order.payment_reference == razorpay_payment_id

        # Check PaymentTransaction ledger
        success_tx = PaymentTransaction.objects.filter(
            order=order, status=PaymentTransaction.StatusChoices.SUCCESS
        ).first()
        assert success_tx is not None
        assert success_tx.provider == "RAZORPAY"
        assert success_tx.provider_transaction_id == razorpay_payment_id

    def test_razorpay_invalid_signature_rejected(self, buyer_auth_client, in_part):
        payload = valid_india_shipping_payload(in_part.id, quantity=1, payment_method="ONLINE")
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        order_data = res.json()["order"]
        order_id = order_data["id"]

        verify_payload = {
            "razorpay_order_id": "order_mock_test",
            "razorpay_payment_id": "pay_mock_test",
            "razorpay_signature": "invalid_forged_signature_hex",
        }
        v_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order_id}/payment/verify/",
            verify_payload,
            format="json",
        )
        assert v_res.status_code == status.HTTP_400_BAD_REQUEST

        order = Order.objects.get(id=order_id)
        assert order.payment_status == PaymentStatusChoices.PENDING
        assert order.paid_at is None

    def test_cross_buyer_cannot_verify_payment(self, buyer_auth_client, other_buyer_client, in_part):
        payload = valid_india_shipping_payload(in_part.id, quantity=1, payment_method="ONLINE")
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        order_id = res.json()["order"]["id"]

        v_res = other_buyer_client.post(
            f"/api/v1/marketplace/orders/{order_id}/payment/verify/",
            {"razorpay_payment_id": "pay_123"},
            format="json",
        )
        assert v_res.status_code == status.HTTP_403_FORBIDDEN


# =============================================================================
# 4. WEBHOOK PROCESSING & REPLAY IDEMPOTENCY
# =============================================================================

class TestPaymentWebhooksAndIdempotency:

    def test_razorpay_webhook_signature_and_idempotency(self, api_client, buyer_auth_client, in_part):
        payload = valid_india_shipping_payload(in_part.id, quantity=1, payment_method="ONLINE")
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        order_data = res.json()["order"]
        order = Order.objects.get(id=order_data["id"])

        webhook_payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_webhook_001",
                        "order_id": order.payment_reference,
                        "status": "captured",
                        "amount": int(order.total_amount * 100),
                        "currency": "INR",
                        "notes": {
                            "order_number": order.order_number,
                        },
                    }
                }
            }
        }
        body_bytes = json.dumps(webhook_payload).encode("utf-8")
        secret = getattr(settings, 'RAZORPAY_WEBHOOK_SECRET', 'test_razorpay_webhook_secret')
        valid_signature = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()

        # 1. First webhook delivery
        wh_res = api_client.post(
            "/api/v1/marketplace/payments/webhook/razorpay/",
            data=body_bytes,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=valid_signature,
        )
        assert wh_res.status_code == status.HTTP_200_OK

        order.refresh_from_db()
        assert order.payment_status == PaymentStatusChoices.PAID
        assert order.status == OrderStatusChoices.CONFIRMED

        # 2. Duplicate / replayed webhook delivery
        wh_res_duplicate = api_client.post(
            "/api/v1/marketplace/payments/webhook/razorpay/",
            data=body_bytes,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=valid_signature,
        )
        assert wh_res_duplicate.status_code == status.HTTP_200_OK
        dup_data = wh_res_duplicate.json()
        assert dup_data.get("replayed") is True or dup_data.get("status") in ("already_processed", "success")

    def test_stripe_webhook_signature_and_processing(self, api_client, buyer_auth_client, uk_part):
        payload = valid_uk_shipping_payload(uk_part.id, quantity=1, payment_method="ONLINE")
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        order = Order.objects.get(id=res.json()["order"]["id"])

        timestamp = int(time.time())
        event_id = f"evt_test_{uuid.uuid4().hex[:8]}"
        webhook_payload = {
            "id": event_id,
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": order.payment_reference,
                    "status": "succeeded",
                    "amount": int(order.total_amount * 100),
                    "currency": "gbp",
                    "metadata": {
                        "order_number": order.order_number,
                    },
                }
            }
        }
        body_bytes = json.dumps(webhook_payload).encode("utf-8")
        secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', 'test_stripe_webhook_secret')
        signed_payload = f"{timestamp}.{body_bytes.decode('utf-8')}".encode("utf-8")
        valid_v1 = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
        stripe_header = f"t={timestamp},v1={valid_v1}"

        wh_res = api_client.post(
            "/api/v1/marketplace/payments/webhook/stripe/",
            data=body_bytes,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE=stripe_header,
        )
        assert wh_res.status_code == status.HTTP_200_OK

        order.refresh_from_db()
        assert order.payment_status == PaymentStatusChoices.PAID


# =============================================================================
# 5. CASH ON DELIVERY (COD) & AUTHORIZED COLLECTION WORKFLOW
# =============================================================================

class TestCashOnDeliveryWorkflow:

    def test_cod_order_creation_success(self, buyer_auth_client, in_part):
        payload = valid_india_shipping_payload(in_part.id, quantity=1, payment_method="COD")
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")

        assert res.status_code == status.HTTP_201_CREATED
        order_data = res.json()["order"]
        assert order_data["payment_method"] == "COD"
        assert order_data["payment_status"] == "PENDING"
        assert order_data["cod_collection_status"] == "PENDING"

        # Stock deducted
        in_part.refresh_from_db()
        assert in_part.stock_quantity == 9

    def test_cod_order_exceeding_threshold_rejected(self, buyer_auth_client, in_part):
        # 15 * 4000 = 60,000 + 18% GST = 70,800 > threshold 50,000
        in_part.stock_quantity = 50
        in_part.save(update_fields=['stock_quantity'])

        payload = valid_india_shipping_payload(in_part.id, quantity=15, payment_method="COD")
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")

        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "Cash on Delivery is not available" in res.json()["error"]

    def test_unauthorized_buyer_cannot_update_cod_collection(self, buyer_auth_client, in_part):
        payload = valid_india_shipping_payload(in_part.id, quantity=1, payment_method="COD")
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        order_id = res.json()["order"]["id"]

        cod_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order_id}/cod-collection/",
            {"cod_collection_status": "COLLECTED", "notes": "Buyer self collection attempt"},
            format="json",
        )
        assert cod_res.status_code == status.HTTP_403_FORBIDDEN

    def test_unauthorized_seller_cannot_update_cod_collection(self, seller_auth_client, buyer_auth_client, in_part):
        payload = valid_india_shipping_payload(in_part.id, quantity=1, payment_method="COD")
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        order_id = res.json()["order"]["id"]

        cod_res = seller_auth_client.post(
            f"/api/v1/marketplace/orders/{order_id}/cod-collection/",
            {"cod_collection_status": "COLLECTED", "notes": "Seller marking collected"},
            format="json",
        )
        assert cod_res.status_code == status.HTTP_403_FORBIDDEN

    def test_authorized_staff_can_mark_cod_collected(self, staff_auth_client, buyer_auth_client, in_part, staff_user):
        payload = valid_india_shipping_payload(in_part.id, quantity=1, payment_method="COD")
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        order_id = res.json()["order"]["id"]

        cod_res = staff_auth_client.post(
            f"/api/v1/marketplace/orders/{order_id}/cod-collection/",
            {"cod_collection_status": "COLLECTED", "notes": "Cash of ₹4,720 received by courier agent"},
            format="json",
        )
        assert cod_res.status_code == status.HTTP_200_OK
        data = cod_res.json()
        assert data["status"] == "success"

        order = Order.objects.get(id=order_id)
        assert order.cod_collection_status == CODCollectionStatusChoices.COLLECTED
        assert order.payment_status == PaymentStatusChoices.PAID
        assert order.cod_collected_by == staff_user
        assert order.cod_collected_at is not None

        # Ledger contains COD collection
        tx = PaymentTransaction.objects.filter(
            order=order, transaction_type=PaymentTransaction.TransactionTypeChoices.COD_COLLECTION
        ).first()
        assert tx is not None
        assert tx.status == PaymentTransaction.StatusChoices.SUCCESS

    def test_authorized_staff_can_mark_cod_failed_collection(self, staff_auth_client, buyer_auth_client, in_part):
        payload = valid_india_shipping_payload(in_part.id, quantity=1, payment_method="COD")
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        order_id = res.json()["order"]["id"]

        cod_res = staff_auth_client.post(
            f"/api/v1/marketplace/orders/{order_id}/cod-collection/",
            {"cod_collection_status": "FAILED_COLLECTION", "notes": "Customer refused package delivery"},
            format="json",
        )
        assert cod_res.status_code == status.HTTP_200_OK

        order = Order.objects.get(id=order_id)
        assert order.cod_collection_status == CODCollectionStatusChoices.FAILED_COLLECTION
        assert order.payment_status == PaymentStatusChoices.PENDING


# =============================================================================
# 6. ORDER CANCELLATION RESTOCKING & PAYMENT LEDGER ACCESS
# =============================================================================

class TestCancellationAndLedgerAccess:

    def test_buyer_can_cancel_pending_cod_order_and_restock(self, buyer_auth_client, in_part):
        initial_stock = in_part.stock_quantity
        payload = valid_india_shipping_payload(in_part.id, quantity=2, payment_method="COD")
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        order_id = res.json()["order"]["id"]

        in_part.refresh_from_db()
        assert in_part.stock_quantity == initial_stock - 2

        cancel_res = buyer_auth_client.post(f"/api/v1/marketplace/orders/{order_id}/cancel/", format="json")
        assert cancel_res.status_code == status.HTTP_200_OK

        order = Order.objects.get(id=order_id)
        assert order.status == OrderStatusChoices.CANCELLED

        in_part.refresh_from_db()
        assert in_part.stock_quantity == initial_stock

    def test_payment_detail_ledger_access_permissions(
        self, buyer_auth_client, seller_auth_client, staff_auth_client, other_buyer_client, in_part
    ):
        payload = valid_india_shipping_payload(in_part.id, quantity=1, payment_method="ONLINE")
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        order_id = res.json()["order"]["id"]

        # 1. Buyer who placed order can view
        res1 = buyer_auth_client.get(f"/api/v1/marketplace/orders/{order_id}/payment/")
        assert res1.status_code == status.HTTP_200_OK
        assert "transactions" in res1.json()

        # 2. Seller of part in order can view
        res2 = seller_auth_client.get(f"/api/v1/marketplace/orders/{order_id}/payment/")
        assert res2.status_code == status.HTTP_200_OK

        # 3. Staff can view
        res3 = staff_auth_client.get(f"/api/v1/marketplace/orders/{order_id}/payment/")
        assert res3.status_code == status.HTTP_200_OK

        # 4. Unrelated buyer is rejected
        res4 = other_buyer_client.get(f"/api/v1/marketplace/orders/{order_id}/payment/")
        assert res4.status_code == status.HTTP_403_FORBIDDEN


# =============================================================================
# 7. REGRESSION TESTS: BUG 1 (COUNTRY & CURRENCY SYNCHRONIZATION)
# =============================================================================

class TestBug1CountryCurrencySynchronization:
    """
    Regression tests verifying:
    1. Selecting India enforces INR, MH/Indian states, statutory GST, and Razorpay.
    2. Selecting UK enforces GBP, UK regions, 0% Indian GST, and Stripe.
    3. Changing from UK to India during a session synchronizes currency, state, and tax calculations.
    4. Cross-country currency mismatches are strictly rejected by the backend.
    """

    def test_india_inr_checkout_synchronization(self, buyer_auth_client, in_part):
        payload = valid_india_shipping_payload(in_part.id, quantity=1)
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        assert res.status_code == status.HTTP_201_CREATED
        data = res.json()
        assert data["status"] == "success"
        order_data = data["order"]
        assert order_data["currency"] == "INR"
        assert order_data["shipping_country"] == "India"
        assert order_data["shipping_state"] == "MH"
        assert Decimal(order_data["subtotal_taxable_amount"]) == Decimal("4000.00")
        assert Decimal(order_data["total_tax_amount"]) == Decimal("720.00")
        assert Decimal(order_data["total_amount"]) == Decimal("4720.00")
        assert data["payment_session"]["provider"] == "RAZORPAY"
        assert data["payment_session"]["currency"] == "INR"

    def test_uk_gbp_checkout_synchronization(self, buyer_auth_client, uk_part):
        payload = valid_uk_shipping_payload(uk_part.id, quantity=1)
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        assert res.status_code == status.HTTP_201_CREATED
        data = res.json()
        assert data["status"] == "success"
        order_data = data["order"]
        assert order_data["currency"] == "GBP"
        assert order_data["shipping_country"] == "United Kingdom"
        assert order_data["shipping_state"] == "Greater London"
        assert Decimal(order_data["subtotal_taxable_amount"]) == Decimal("120.00")
        assert Decimal(order_data["total_tax_amount"]) == Decimal("0.00")
        assert Decimal(order_data["total_amount"]) == Decimal("120.00")
        assert data["payment_session"]["provider"] == "STRIPE"
        assert data["payment_session"]["currency"] == "GBP"

    def test_change_from_uk_to_india_during_session(self, buyer_auth_client, uk_part, in_part):
        # Step 1: Session starts with UK destination & GBP
        uk_calc_payload = valid_uk_shipping_payload(uk_part.id, quantity=1)
        calc_uk_res = buyer_auth_client.post("/api/v1/marketplace/orders/calculate/", uk_calc_payload, format="json")
        assert calc_uk_res.status_code == status.HTTP_200_OK
        assert calc_uk_res.json()["currency"] == "GBP"

        # Step 2: Buyer switches destination country to India, setting currency INR & state MH
        india_calc_payload = valid_india_shipping_payload(in_part.id, quantity=1)
        calc_in_res = buyer_auth_client.post("/api/v1/marketplace/orders/calculate/", india_calc_payload, format="json")
        assert calc_in_res.status_code == status.HTTP_200_OK
        assert calc_in_res.json()["currency"] == "INR"
        assert calc_in_res.json()["country"] == "IN"

        # Step 3: Checkout for India succeeds with INR without encountering GBP mismatch error
        checkout_res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", india_calc_payload, format="json")
        assert checkout_res.status_code == status.HTTP_201_CREATED
        assert checkout_res.json()["order"]["currency"] == "INR"
        assert checkout_res.json()["order"]["shipping_country"] == "India"

    def test_strict_rejection_of_country_currency_mismatch(self, buyer_auth_client, in_part, uk_part):
        # Mismatch 1: India destination with GBP currency
        mismatch_india = valid_india_shipping_payload(in_part.id, currency="GBP")
        res1 = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", mismatch_india, format="json")
        assert res1.status_code == status.HTTP_400_BAD_REQUEST
        assert "GBP currency cannot be used for delivery to India. India orders must use INR." in res1.json()["error"]

        # Mismatch 2: UK destination with INR currency
        mismatch_uk = valid_uk_shipping_payload(uk_part.id, currency="INR")
        res2 = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", mismatch_uk, format="json")
        assert res2.status_code == status.HTTP_400_BAD_REQUEST
        assert "INR currency cannot be used for delivery to the United Kingdom. UK orders must use GBP." in res2.json()["error"]


# =============================================================================
# 8. REGRESSION TESTS: BUG 2 (PAYMENT VERIFICATION & SERVER-SIDE ISOLATION)
# =============================================================================

class TestBug2PaymentVerificationAndIsolation:
    """
    Regression tests verifying:
    1. Verification supports both stripe_payment_intent_id and payment_intent_id.
    2. Fabricated payment intent IDs not matching the order session are rejected.
    3. Razorpay verification requires valid order ID, payment ID, and signature.
    4. Verification retries are idempotent and do not create duplicate success records.
    5. Isolated server-side test simulation works in dev/test but is blocked in production.
    """

    def test_stripe_verification_with_stripe_payment_intent_id(self, buyer_auth_client, uk_part):
        payload = valid_uk_shipping_payload(uk_part.id, quantity=1)
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        order_id = res.json()["order"]["id"]
        order = Order.objects.get(id=order_id)
        assert order.payment_status == PaymentStatusChoices.PENDING
        assert order.payment_reference is not None

        verify_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order_id}/payment/verify/",
            {"stripe_payment_intent_id": order.payment_reference},
            format="json",
        )
        assert verify_res.status_code == status.HTTP_200_OK
        data = verify_res.json()
        assert data["status"] == "success"
        assert data["payment_status"] == "PAID"

        order.refresh_from_db()
        assert order.payment_status == PaymentStatusChoices.PAID
        assert order.paid_at is not None

    def test_stripe_verification_with_payment_intent_id(self, buyer_auth_client, uk_part):
        payload = valid_uk_shipping_payload(uk_part.id, quantity=1)
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        order_id = res.json()["order"]["id"]
        order = Order.objects.get(id=order_id)

        verify_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order_id}/payment/verify/",
            {"payment_intent_id": order.payment_reference},
            format="json",
        )
        assert verify_res.status_code == status.HTTP_200_OK
        assert verify_res.json()["status"] == "success"
        order.refresh_from_db()
        assert order.payment_status == PaymentStatusChoices.PAID

    def test_stripe_verification_rejects_fabricated_payment_intent_id(self, buyer_auth_client, uk_part):
        payload = valid_uk_shipping_payload(uk_part.id, quantity=1)
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        order_id = res.json()["order"]["id"]
        order = Order.objects.get(id=order_id)

        verify_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order_id}/payment/verify/",
            {"stripe_payment_intent_id": "pi_fabricated_attacker_injection_999"},
            format="json",
        )
        assert verify_res.status_code == status.HTTP_400_BAD_REQUEST
        data = verify_res.json()
        assert data["status"] == "failed"
        assert "does not match the active session" in data["error"]

        order.refresh_from_db()
        assert order.payment_status == PaymentStatusChoices.PENDING

    def test_razorpay_verification_requires_order_and_payment_and_signature(self, buyer_auth_client, in_part):
        payload = valid_india_shipping_payload(in_part.id, quantity=1)
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        order_id = res.json()["order"]["id"]
        order = Order.objects.get(id=order_id)

        # Missing signature
        verify_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order_id}/payment/verify/",
            {
                "razorpay_order_id": order.payment_reference,
                "razorpay_payment_id": "pay_test_123",
            },
            format="json",
        )
        assert verify_res.status_code == status.HTTP_400_BAD_REQUEST
        assert verify_res.json()["status"] == "failed"

        # Fabricated order ID
        verify_res2 = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order_id}/payment/verify/",
            {
                "razorpay_order_id": "order_fabricated_999",
                "razorpay_payment_id": "pay_test_123",
                "razorpay_signature": "mock_signature",
            },
            format="json",
        )
        assert verify_res2.status_code == status.HTTP_400_BAD_REQUEST
        assert "does not match the active session" in verify_res2.json()["error"]

        order.refresh_from_db()
        assert order.payment_status == PaymentStatusChoices.PENDING

    def test_payment_verification_retry_is_idempotent(self, buyer_auth_client, uk_part):
        payload = valid_uk_shipping_payload(uk_part.id, quantity=1)
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        order_id = res.json()["order"]["id"]
        order = Order.objects.get(id=order_id)

        # First verification
        v1 = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order_id}/payment/verify/",
            {"stripe_payment_intent_id": order.payment_reference},
            format="json",
        )
        assert v1.status_code == status.HTTP_200_OK
        assert v1.json()["status"] == "success"

        success_tx_count_before = PaymentTransaction.objects.filter(
            order=order, status=PaymentTransaction.StatusChoices.SUCCESS
        ).count()
        assert success_tx_count_before == 1

        # Second verification (retry)
        v2 = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order_id}/payment/verify/",
            {"stripe_payment_intent_id": order.payment_reference},
            format="json",
        )
        assert v2.status_code == status.HTTP_200_OK
        assert v2.json()["status"] == "success"
        assert v2.json().get("extra", {}).get("already_paid") is True

        success_tx_count_after = PaymentTransaction.objects.filter(
            order=order, status=PaymentTransaction.StatusChoices.SUCCESS
        ).count()
        assert success_tx_count_after == 1  # No duplicate transaction!

    def test_server_simulated_payment_in_test_mode(self, buyer_auth_client, in_part):
        payload = valid_india_shipping_payload(in_part.id, quantity=1)
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        order_id = res.json()["order"]["id"]

        sim_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order_id}/payment/simulate/",
            format="json",
        )
        assert sim_res.status_code == status.HTTP_200_OK
        data = sim_res.json()
        assert data["status"] == "success"
        assert data["payment_status"] == "PAID"

        order = Order.objects.get(id=order_id)
        assert order.payment_status == PaymentStatusChoices.PAID

        # Retry is idempotent
        sim_res2 = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order_id}/payment/simulate/",
            format="json",
        )
        assert sim_res2.status_code == status.HTTP_200_OK
        assert sim_res2.json()["already_paid"] is True

    def test_server_simulated_payment_blocked_in_production(self, buyer_auth_client, in_part, monkeypatch):
        from django.conf import settings
        monkeypatch.setattr(settings, 'PAYMENT_TEST_MODE', False)
        monkeypatch.setattr(settings, 'DEBUG', False)
        monkeypatch.setattr(settings, 'IS_TESTING', False)

        payload = valid_india_shipping_payload(in_part.id, quantity=1)
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        order_id = res.json()["order"]["id"]

        sim_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order_id}/payment/simulate/",
            {"force_test": True, "test_mode": True},  # client cannot bypass
            format="json",
        )
        assert sim_res.status_code == status.HTTP_403_FORBIDDEN
        assert "strictly disabled in production" in sim_res.json()["error"]

        order = Order.objects.get(id=order_id)
        assert order.payment_status == PaymentStatusChoices.PENDING


class TestPaymentSecurityHardeningAndWebhookSettlement:
    """
    Verifies the security fixes from the DriverXtra payment flow audit:
    1. Production mock-signature rejection:
       - 'test_sig_valid' and 'mock_valid_signature' rejected even if PAYMENT_TEST_MODE is True in production (DEBUG=False, IS_TESTING=False).
       - Valid real-format HMAC signatures undergo proper cryptographic check.
       - Stripe mock signature 'test_stripe_sig_valid' rejected in production.
    2. Webhook notification delivery on successful settlement:
       - Valid success webhook settles order and dispatches in-app notification to buyer.
    3. Webhook retries & duplicate settlement idempotency:
       - Retried webhook returns already_processed without re-notifying.
       - Consecutive webhook event for already PAID order does not re-notify.
    """

    def test_production_rejects_mock_signature_even_if_misconfigured(self, buyer_auth_client, in_part, monkeypatch):
        from apps.marketplace.payments.razorpay_provider import RazorpayPaymentProvider
        from django.conf import settings

        # Simulate production environment with misconfigured PAYMENT_TEST_MODE=True
        monkeypatch.setattr(settings, 'DEBUG', False)
        monkeypatch.setattr(settings, 'IS_TESTING', False)
        monkeypatch.setattr(settings, 'PAYMENT_TEST_MODE', True)

        provider = RazorpayPaymentProvider()
        assert provider.test_mode is False, "Provider must enforce test_mode=False in production regardless of settings.PAYMENT_TEST_MODE"

        # Create order in normal test mode first
        monkeypatch.setattr(settings, 'IS_TESTING', True)
        payload = valid_india_shipping_payload(in_part.id, quantity=1)
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        order_id = res.json()["order"]["id"]
        order = Order.objects.get(id=order_id)

        # Switch back to production simulation
        monkeypatch.setattr(settings, 'DEBUG', False)
        monkeypatch.setattr(settings, 'IS_TESTING', False)
        monkeypatch.setattr(settings, 'PAYMENT_TEST_MODE', True)

        # Attempt to verify using mock signature 'test_sig_valid'
        verify_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order_id}/payment/verify/",
            {
                "razorpay_order_id": order.payment_reference,
                "razorpay_payment_id": "pay_mock_attacker_123",
                "razorpay_signature": "test_sig_valid",
            },
            format="json",
        )
        assert verify_res.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid Razorpay payment signature" in verify_res.json()["error"]

        order.refresh_from_db()
        assert order.payment_status == PaymentStatusChoices.PENDING

    def test_production_accepts_valid_hmac_and_rejects_invalid_hmac(self, buyer_auth_client, in_part, monkeypatch):
        from django.conf import settings

        # Create order
        payload = valid_india_shipping_payload(in_part.id, quantity=1)
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        order_id = res.json()["order"]["id"]
        order = Order.objects.get(id=order_id)

        # Switch to production simulation
        monkeypatch.setattr(settings, 'DEBUG', False)
        monkeypatch.setattr(settings, 'IS_TESTING', False)
        monkeypatch.setattr(settings, 'PAYMENT_TEST_MODE', False)

        # 1. Invalid signature format
        bad_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order_id}/payment/verify/",
            {
                "razorpay_order_id": order.payment_reference,
                "razorpay_payment_id": "pay_test_prod_123",
                "razorpay_signature": "0000000000000000000000000000000000000000000000000000000000000000",
            },
            format="json",
        )
        assert bad_res.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid Razorpay payment signature" in bad_res.json()["error"]
        order.refresh_from_db()
        assert order.payment_status == PaymentStatusChoices.PENDING

        # 2. Authentic HMAC-SHA256 signature calculated with server secret
        secret = getattr(settings, 'RAZORPAY_KEY_SECRET', 'rzp_test_placeholder_secret')
        pay_id = "pay_real_sig_123"
        msg = f"{order.payment_reference}|{pay_id}".encode('utf-8')
        valid_sig = hmac.new(secret.encode('utf-8'), msg, hashlib.sha256).hexdigest()

        good_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order_id}/payment/verify/",
            {
                "razorpay_order_id": order.payment_reference,
                "razorpay_payment_id": pay_id,
                "razorpay_signature": valid_sig,
            },
            format="json",
        )
        assert good_res.status_code == status.HTTP_200_OK
        order.refresh_from_db()
        assert order.payment_status == PaymentStatusChoices.PAID
        assert order.status == OrderStatusChoices.CONFIRMED

    def test_production_rejects_stripe_mock_signature(self, buyer_auth_client, uk_part, monkeypatch):
        from apps.marketplace.payments.stripe_provider import StripePaymentProvider
        from django.conf import settings

        monkeypatch.setattr(settings, 'DEBUG', False)
        monkeypatch.setattr(settings, 'IS_TESTING', False)
        monkeypatch.setattr(settings, 'PAYMENT_TEST_MODE', True)

        provider = StripePaymentProvider()
        assert provider.test_mode is False, "Stripe provider must enforce test_mode=False in production"

        # Webhook verification rejects mock signature
        is_valid, _, _, err = provider.verify_webhook(
            b'{"id": "evt_test", "type": "payment_intent.succeeded"}',
            {"stripe-signature": "test_stripe_sig_valid"},
        )
        assert is_valid is False
        assert "Invalid Stripe webhook signature" in err.get("error", "")

    def test_webhook_settlement_creates_buyer_notification(self, api_client, buyer_auth_client, in_part):
        from apps.notifications.models import Notification

        # 1. Create order
        payload = valid_india_shipping_payload(in_part.id, quantity=1)
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        order_data = res.json()["order"]
        order_number = order_data["order_number"]
        order = Order.objects.get(order_number=order_number)
        buyer = order.buyer

        # Initial state
        assert order.payment_status == PaymentStatusChoices.PENDING
        notif_count_before = Notification.objects.filter(
            recipient=buyer,
            event_type="marketplace.order.payment_verified",
        ).count()
        assert notif_count_before == 0

        # 2. Receive valid payment webhook event
        event_id = f"rzp_evt_test_{uuid.uuid4().hex[:10]}"
        webhook_body = json.dumps({
            "event": "order.paid",
            "event_id": event_id,
            "payload": {
                "order": {
                    "entity": {
                        "id": order.payment_reference,
                        "notes": {"order_number": order_number},
                    }
                }
            }
        }).encode('utf-8')

        secret = getattr(settings, 'RAZORPAY_WEBHOOK_SECRET', 'rzp_test_webhook_secret')
        valid_signature = hmac.new(secret.encode('utf-8'), webhook_body, hashlib.sha256).hexdigest()

        response = api_client.post(
            "/api/v1/marketplace/payments/webhook/razorpay/",
            data=webhook_body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=valid_signature,
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["settled"] is True

        # 3. Verify order settled and notification created
        order.refresh_from_db()
        assert order.payment_status == PaymentStatusChoices.PAID
        assert order.status == OrderStatusChoices.CONFIRMED

        notif = Notification.objects.get(
            recipient=buyer,
            event_type="marketplace.order.payment_verified",
        )
        assert order_number in notif.title
        assert "Payment Verified" in notif.title
        assert "successfully verified" in notif.message

    def test_webhook_retry_and_duplicate_events_do_not_duplicate_notifications(self, api_client, buyer_auth_client, in_part):
        from apps.notifications.models import Notification

        payload = valid_india_shipping_payload(in_part.id, quantity=1)
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        order_number = res.json()["order"]["order_number"]
        order = Order.objects.get(order_number=order_number)
        buyer = order.buyer

        event_id = f"rzp_evt_idem_{uuid.uuid4().hex[:10]}"
        webhook_body = json.dumps({
            "event": "payment.captured",
            "event_id": event_id,
            "payload": {
                "order": {
                    "entity": {
                        "id": order.payment_reference,
                        "notes": {"order_number": order_number},
                    }
                }
            }
        }).encode('utf-8')

        secret = getattr(settings, 'RAZORPAY_WEBHOOK_SECRET', 'rzp_test_webhook_secret')
        valid_signature = hmac.new(secret.encode('utf-8'), webhook_body, hashlib.sha256).hexdigest()

        # First delivery: settles order
        res1 = api_client.post(
            "/api/v1/marketplace/payments/webhook/razorpay/",
            data=webhook_body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=valid_signature,
        )
        assert res1.status_code == status.HTTP_200_OK
        assert res1.json()["settled"] is True

        notifs_after_first = Notification.objects.filter(
            recipient=buyer,
            event_type="marketplace.order.payment_verified",
        ).count()
        assert notifs_after_first == 1

        # Second delivery (retry with exact same event_id): must return already_processed
        res2 = api_client.post(
            "/api/v1/marketplace/payments/webhook/razorpay/",
            data=webhook_body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=valid_signature,
        )
        assert res2.status_code == status.HTTP_200_OK
        assert res2.json().get("status") == "already_processed"
        assert res2.json().get("replayed") is True

        notifs_after_retry = Notification.objects.filter(
            recipient=buyer,
            event_type="marketplace.order.payment_verified",
        ).count()
        assert notifs_after_retry == 1, "Webhook retry must not generate duplicate notifications!"

        # Third delivery (different event_id, e.g. order.paid, for already PAID order):
        event_id_2 = f"rzp_evt_second_{uuid.uuid4().hex[:10]}"
        webhook_body_2 = json.dumps({
            "event": "order.paid",
            "event_id": event_id_2,
            "payload": {
                "order": {
                    "entity": {
                        "id": order.payment_reference,
                        "notes": {"order_number": order_number},
                    }
                }
            }
        }).encode('utf-8')
        sig_2 = hmac.new(secret.encode('utf-8'), webhook_body_2, hashlib.sha256).hexdigest()

        res3 = api_client.post(
            "/api/v1/marketplace/payments/webhook/razorpay/",
            data=webhook_body_2,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=sig_2,
        )
        assert res3.status_code == status.HTTP_200_OK
        assert res3.json()["settled"] is False, "Order was already PAID so settled flag must be False"

        notifs_after_third = Notification.objects.filter(
            recipient=buyer,
            event_type="marketplace.order.payment_verified",
        ).count()
        assert notifs_after_third == 1, "Subsequent webhook event on settled order must not duplicate notifications!"

