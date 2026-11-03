import hashlib
import hmac
import json
import time
import uuid
from decimal import Decimal
import pytest
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
    PaymentTransaction,
    PaymentWebhookEvent,
)
from apps.marketplace.payments.razorpay_provider import RazorpayPaymentProvider
from apps.marketplace.payments.stripe_provider import StripePaymentProvider
from apps.marketplace.payments.service import PaymentService


@pytest.fixture
def brake_cat(db):
    return PartCategory.objects.create(name="Braking Category", slug=f"braking-{uuid.uuid4().hex[:6]}")


@pytest.fixture
def second_seller_user(db):
    user = User.objects.create_user(
        email=f"seller2_{uuid.uuid4().hex[:6]}@driverxtra.com",
        password="SecurePassword123!",
        first_name="Second",
        last_name="Seller",
        is_email_verified=True,
    )
    user.add_role(RoleChoices.SELLER)
    return user


@pytest.fixture
def in_part_listing(db, seller_user, brake_cat):
    return SparePartListing.objects.create(
        seller=seller_user,
        name="Stage E Brembo Rotors (IN)",
        brand="Brembo",
        mpn=f"BR-IN-{uuid.uuid4().hex[:4]}",
        category=brake_cat,
        price=Decimal("5000.00"),
        currency="INR",
        hsn_code="8708",
        gst_rate=Decimal("18.00"),
        status=ListingStatusChoices.APPROVED,
        is_active=True,
        stock_quantity=20,
    )


@pytest.fixture
def in_part_seller2(db, second_seller_user, brake_cat):
    return SparePartListing.objects.create(
        seller=second_seller_user,
        name="Stage E Ferodo Pads (IN MultiSeller)",
        brand="Ferodo",
        mpn=f"FD-IN-{uuid.uuid4().hex[:4]}",
        category=brake_cat,
        price=Decimal("2500.00"),
        currency="INR",
        hsn_code="8708",
        gst_rate=Decimal("18.00"),
        status=ListingStatusChoices.APPROVED,
        is_active=True,
        stock_quantity=15,
    )


@pytest.fixture
def uk_part_listing(db, seller_user, brake_cat):
    return SparePartListing.objects.create(
        seller=seller_user,
        name="Stage E EBC Brake Pads (UK)",
        brand="EBC",
        mpn=f"EBC-UK-{uuid.uuid4().hex[:4]}",
        category=brake_cat,
        price=Decimal("150.00"),
        currency="GBP",
        hsn_code="8708",
        gst_rate=Decimal("0.00"),
        status=ListingStatusChoices.APPROVED,
        is_active=True,
        stock_quantity=10,
    )


def build_razorpay_signature(order_id: str, payment_id: str, secret: str) -> str:
    msg = f"{order_id}|{payment_id}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def build_stripe_signature(body_bytes: bytes, secret: str, timestamp: int) -> str:
    signed_payload = f"{timestamp}.{body_bytes.decode('utf-8')}".encode("utf-8")
    v1_sig = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={v1_sig}"


# =============================================================================
# STAGE E – 15 PAYMENT INTEGRATION SCENARIOS
# =============================================================================

@pytest.mark.django_db
class TestStageEPaymentIntegration:

    # -------------------------------------------------------------------------
    # Scenario 1: Razorpay Order Creation
    # -------------------------------------------------------------------------
    def test_01_razorpay_order_creation(self, buyer_auth_client, in_part_listing):
        """Authoritative Razorpay order/session initialization in INR."""
        checkout_payload = {
            "items": [{"listing_id": str(in_part_listing.id), "quantity": 2}],
            "place_of_supply": "MH",
            "currency": "INR",
            "payment_method": "ONLINE",
            "shipping_name": "Rajesh Sharma",
            "shipping_phone": "+91 9876543210",
            "shipping_address_line1": "101 Marine Drive",
            "shipping_city": "Mumbai",
            "shipping_state": "MH",
            "shipping_postal_code": "400020",
            "shipping_country": "India",
        }
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", checkout_payload, format="json")
        assert res.status_code == status.HTTP_201_CREATED, res.data

        order_data = res.data["order"]
        order = Order.objects.get(order_number=order_data["order_number"])
        assert order.currency == "INR"
        assert order.payment_method == PaymentMethodChoices.ONLINE

        session = PaymentService.create_payment_session(order)
        assert session["provider"] == "RAZORPAY"
        assert session["currency"] == "INR"
        assert session["amount_minor"] == int(round(order.total_amount * 100))
        assert session["provider_order_id"].startswith("order_")
        assert order.payment_reference == session["provider_order_id"]

        # Transaction created in PENDING state
        tx = PaymentTransaction.objects.filter(order=order, provider="RAZORPAY").first()
        assert tx is not None
        assert tx.status == PaymentTransaction.StatusChoices.PENDING
        assert tx.amount == order.total_amount
        assert tx.currency == "INR"

    # -------------------------------------------------------------------------
    # Scenario 2: Razorpay Signature Verification
    # -------------------------------------------------------------------------
    def test_02_razorpay_signature_verification(self, buyer_auth_client, in_part_listing):
        """Cryptographic server-side HMAC-SHA256 signature verification."""
        checkout_payload = {
            "items": [{"listing_id": str(in_part_listing.id), "quantity": 1}],
            "place_of_supply": "MH",
            "currency": "INR",
            "payment_method": "ONLINE",
            "shipping_name": "Aarav Patel",
            "shipping_phone": "+91 9876500001",
            "shipping_address_line1": "12 Bandra West",
            "shipping_city": "Mumbai",
            "shipping_state": "MH",
            "shipping_postal_code": "400050",
            "shipping_country": "India",
        }
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", checkout_payload, format="json")
        order = Order.objects.get(order_number=res.data["order"]["order_number"])
        session = PaymentService.create_payment_session(order)
        rzp_order_id = session["provider_order_id"]
        rzp_payment_id = "pay_test_valid_sig_123"

        provider = RazorpayPaymentProvider()
        secret = provider.key_secret

        # Valid signature
        valid_sig = build_razorpay_signature(rzp_order_id, rzp_payment_id, secret)
        is_valid, payment_id, extra = provider.verify_payment(order, {
            "razorpay_order_id": rzp_order_id,
            "razorpay_payment_id": rzp_payment_id,
            "razorpay_signature": valid_sig,
        })
        assert is_valid is True
        assert payment_id == rzp_payment_id

        # Tampered signature
        is_valid_fake, err, _ = provider.verify_payment(order, {
            "razorpay_order_id": rzp_order_id,
            "razorpay_payment_id": rzp_payment_id,
            "razorpay_signature": "tampered_signature_99999",
        })
        assert is_valid_fake is False
        assert "signature mismatch" in err.lower() or "invalid" in err.lower()

    # -------------------------------------------------------------------------
    # Scenario 3: Razorpay Successful Payment
    # -------------------------------------------------------------------------
    def test_03_razorpay_successful_payment(self, buyer_auth_client, in_part_listing):
        """Verification endpoint successfully transitions order to PAID and CONFIRMED."""
        checkout_payload = {
            "items": [{"listing_id": str(in_part_listing.id), "quantity": 1}],
            "place_of_supply": "DL",
            "currency": "INR",
            "payment_method": "ONLINE",
            "shipping_name": "Vikram Sethi",
            "shipping_phone": "+91 9876511111",
            "shipping_address_line1": "22 Connaught Place",
            "shipping_city": "New Delhi",
            "shipping_state": "DL",
            "shipping_postal_code": "110001",
            "shipping_country": "India",
        }
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", checkout_payload, format="json")
        order = Order.objects.get(order_number=res.data["order"]["order_number"])
        session = res.data["payment_session"]
        rzp_order_id = session["provider_order_id"]
        rzp_payment_id = f"pay_test_{uuid.uuid4().hex[:10]}"

        provider = RazorpayPaymentProvider()
        valid_sig = build_razorpay_signature(rzp_order_id, rzp_payment_id, provider.key_secret)

        verify_payload = {
            "razorpay_order_id": rzp_order_id,
            "razorpay_payment_id": rzp_payment_id,
            "razorpay_signature": valid_sig,
            "amount": str(order.total_amount),
            "currency": "INR",
        }
        v_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order.order_number}/payment/verify/",
            verify_payload,
            format="json",
        )
        assert v_res.status_code == status.HTTP_200_OK, v_res.data
        assert v_res.data["status"] == "success"

        order.refresh_from_db()
        assert order.payment_status == PaymentStatusChoices.PAID
        assert order.status == OrderStatusChoices.CONFIRMED
        assert order.paid_at is not None
        assert order.payment_reference == rzp_payment_id

        # Verify PaymentTransaction record
        success_tx = PaymentTransaction.objects.filter(
            order=order,
            status=PaymentTransaction.StatusChoices.SUCCESS,
            provider="RAZORPAY",
        ).first()
        assert success_tx is not None
        assert success_tx.provider_transaction_id == rzp_payment_id

    # -------------------------------------------------------------------------
    # Scenario 4: Razorpay Failed Payment
    # -------------------------------------------------------------------------
    def test_04_razorpay_failed_payment(self, buyer_auth_client, in_part_listing):
        """Client-reported failure records FAILED transaction and keeps order retryable."""
        checkout_payload = {
            "items": [{"listing_id": str(in_part_listing.id), "quantity": 1}],
            "place_of_supply": "MH",
            "currency": "INR",
            "payment_method": "ONLINE",
            "shipping_name": "Pooja Hegde",
            "shipping_phone": "+91 9876522222",
            "shipping_address_line1": "45 Worli Sea Face",
            "shipping_city": "Mumbai",
            "shipping_state": "MH",
            "shipping_postal_code": "400018",
            "shipping_country": "India",
        }
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", checkout_payload, format="json")
        order = Order.objects.get(order_number=res.data["order"]["order_number"])

        fail_payload = {
            "reason": "Customer bank OTP expired or declined",
            "error_description": "OTP expired",
            "payment_id": "pay_failed_test_456",
        }
        f_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order.order_number}/payment/failed/",
            fail_payload,
            format="json",
        )
        assert f_res.status_code == status.HTTP_200_OK

        order.refresh_from_db()
        assert order.payment_status == PaymentStatusChoices.FAILED
        # Order status remains PENDING_CONFIRMATION to allow buyer to retry payment
        assert order.status == OrderStatusChoices.PENDING_CONFIRMATION

        fail_tx = PaymentTransaction.objects.filter(
            order=order,
            status=PaymentTransaction.StatusChoices.FAILED,
        ).first()
        assert fail_tx is not None
        assert "OTP expired" in fail_tx.error_message

    # -------------------------------------------------------------------------
    # Scenario 5: Stripe Session / Payment Creation
    # -------------------------------------------------------------------------
    def test_05_stripe_session_creation(self, buyer_auth_client, uk_part_listing):
        """Authoritative Stripe PaymentIntent creation for UK GBP orders."""
        checkout_payload = {
            "items": [{"listing_id": str(uk_part_listing.id), "quantity": 1}],
            "currency": "GBP",
            "payment_method": "ONLINE",
            "shipping_name": "Oliver Twist",
            "shipping_phone": "+44 7911 123456",
            "shipping_address_line1": "48 Doughty Street",
            "shipping_city": "London",
            "shipping_state": "Greater London",
            "shipping_postal_code": "WC1N 2LX",
            "shipping_country": "United Kingdom",
        }
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", checkout_payload, format="json")
        assert res.status_code == status.HTTP_201_CREATED, res.data

        order = Order.objects.get(order_number=res.data["order"]["order_number"])
        assert order.currency == "GBP"

        session = PaymentService.create_payment_session(order)
        assert session["provider"] == "STRIPE"
        assert session["currency"] == "GBP"
        assert session["amount_minor"] == int(round(order.total_amount * 100))
        assert session["provider_order_id"].startswith("pi_")
        assert "_secret_" in session["client_secret"]
        assert order.payment_reference == session["provider_order_id"]

        # Currency mismatch rejected by provider
        stripe_provider = StripePaymentProvider()
        fake_inr_order = Order(currency="INR", total_amount=Decimal("100.00"))
        with pytest.raises(ValueError, match="only supports GBP"):
            stripe_provider.create_payment_session(fake_inr_order)

    # -------------------------------------------------------------------------
    # Scenario 6: Stripe Webhook Verification
    # -------------------------------------------------------------------------
    def test_06_stripe_webhook_verification(self):
        """Stripe webhook cryptographic signature validation."""
        provider = StripePaymentProvider()
        secret = provider.webhook_secret
        body = json.dumps({"id": "evt_test_123", "type": "payment_intent.succeeded"}).encode("utf-8")
        timestamp = int(time.time())

        # Valid signature header
        sig_header = build_stripe_signature(body, secret, timestamp)
        is_valid, event_id, event_type, payload = provider.verify_webhook(body, {"stripe-signature": sig_header})
        assert is_valid is True
        assert event_id == "evt_test_123"
        assert event_type == "payment_intent.succeeded"

        # Invalid signature
        is_valid_fake, _, _, _ = provider.verify_webhook(body, {"stripe-signature": "t=12345,v1=bad_signature"})
        assert is_valid_fake is False

        # Missing header
        is_valid_missing, _, _, _ = provider.verify_webhook(body, {})
        assert is_valid_missing is False

    # -------------------------------------------------------------------------
    # Scenario 7: Successful, Failed, and Cancelled Stripe Payments
    # -------------------------------------------------------------------------
    def test_07_successful_and_failed_stripe_payments(self, buyer_auth_client, uk_part_listing):
        """Stripe webhooks for succeeded, failed, and canceled PaymentIntents."""
        checkout_payload = {
            "items": [{"listing_id": str(uk_part_listing.id), "quantity": 1}],
            "currency": "GBP",
            "payment_method": "ONLINE",
            "shipping_name": "Arthur Pendelton",
            "shipping_phone": "+44 7911 222333",
            "shipping_address_line1": "10 Downing Street",
            "shipping_city": "London",
            "shipping_state": "Greater London",
            "shipping_postal_code": "SW1A 2AA",
            "shipping_country": "United Kingdom",
        }
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", checkout_payload, format="json")
        order = Order.objects.get(order_number=res.data["order"]["order_number"])
        session = PaymentService.create_payment_session(order)
        pi_id = session["provider_order_id"]

        # 1. Successful payment webhook
        client = APIClient()
        success_event_id = f"evt_pi_succ_{uuid.uuid4().hex[:10]}"
        succ_body = {
            "id": success_event_id,
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": pi_id,
                    "amount": int(round(order.total_amount * 100)),
                    "currency": "gbp",
                    "metadata": {
                        "order_number": order.order_number,
                    },
                }
            }
        }
        body_bytes = json.dumps(succ_body).encode("utf-8")
        timestamp = int(time.time())
        sig = build_stripe_signature(body_bytes, settings.STRIPE_WEBHOOK_SECRET, timestamp)

        wb_res = client.post(
            "/api/v1/marketplace/payments/webhook/STRIPE/",
            data=body_bytes,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE=sig,
        )
        assert wb_res.status_code == status.HTTP_200_OK

        order.refresh_from_db()
        assert order.payment_status == PaymentStatusChoices.PAID
        assert order.status == OrderStatusChoices.CONFIRMED

        # 2. Failed payment webhook on fresh order
        res_fail = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", checkout_payload, format="json")
        order_fail = Order.objects.get(order_number=res_fail.data["order"]["order_number"])
        session_fail = PaymentService.create_payment_session(order_fail)
        pi_id_fail = session_fail["provider_order_id"]

        fail_event_id = f"evt_pi_fail_{uuid.uuid4().hex[:10]}"
        fail_body = {
            "id": fail_event_id,
            "type": "payment_intent.payment_failed",
            "data": {
                "object": {
                    "id": pi_id_fail,
                    "metadata": {
                        "order_number": order_fail.order_number,
                    },
                }
            }
        }
        fail_bytes = json.dumps(fail_body).encode("utf-8")
        sig_fail = build_stripe_signature(fail_bytes, settings.STRIPE_WEBHOOK_SECRET, int(time.time()))

        wb_fail_res = client.post(
            "/api/v1/marketplace/payments/webhook/STRIPE/",
            data=fail_bytes,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE=sig_fail,
        )
        assert wb_fail_res.status_code == status.HTTP_200_OK

        order_fail.refresh_from_db()
        assert order_fail.payment_status == PaymentStatusChoices.FAILED

    # -------------------------------------------------------------------------
    # Scenario 8: Duplicate Webhook Events (Idempotency)
    # -------------------------------------------------------------------------
    def test_08_duplicate_webhook_events_idempotency(self, buyer_auth_client, in_part_listing):
        """Webhook replaying identical event_id is safely ignored (status=already_processed)."""
        checkout_payload = {
            "items": [{"listing_id": str(in_part_listing.id), "quantity": 1}],
            "place_of_supply": "MH",
            "currency": "INR",
            "payment_method": "ONLINE",
            "shipping_name": "Idempotent Buyer",
            "shipping_phone": "+91 9876533333",
            "shipping_address_line1": "77 Nariman Point",
            "shipping_city": "Mumbai",
            "shipping_state": "MH",
            "shipping_postal_code": "400021",
            "shipping_country": "India",
        }
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", checkout_payload, format="json")
        order = Order.objects.get(order_number=res.data["order"]["order_number"])
        session = PaymentService.create_payment_session(order)
        rzp_order_id = session["provider_order_id"]

        event_id = f"evt_replay_test_{uuid.uuid4().hex[:8]}"
        wb_body = {
            "entity": "event",
            "event": "order.paid",
            "payload": {
                "order": {
                    "entity": {
                        "id": rzp_order_id,
                        "amount": int(round(order.total_amount * 100)),
                        "currency": "INR",
                        "notes": {"order_number": order.order_number},
                    }
                },
                "payment": {
                    "entity": {
                        "id": "pay_replay_123",
                        "amount": int(round(order.total_amount * 100)),
                        "currency": "INR",
                    }
                }
            }
        }
        raw_body = json.dumps(wb_body).encode("utf-8")
        secret = settings.RAZORPAY_WEBHOOK_SECRET
        sig = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

        client = APIClient()

        # First delivery
        r1 = client.post(
            "/api/v1/marketplace/payments/webhook/RAZORPAY/",
            data=raw_body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=sig,
            HTTP_X_RAZORPAY_EVENT_ID=event_id,
        )
        assert r1.status_code == status.HTTP_200_OK
        assert r1.data.get("status") == "success"

        # Count transactions
        tx_count_1 = PaymentTransaction.objects.filter(order=order, status=PaymentTransaction.StatusChoices.SUCCESS).count()
        assert tx_count_1 == 1

        # Second delivery (replay)
        r2 = client.post(
            "/api/v1/marketplace/payments/webhook/RAZORPAY/",
            data=raw_body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=sig,
            HTTP_X_RAZORPAY_EVENT_ID=event_id,
        )
        assert r2.status_code == status.HTTP_200_OK
        assert r2.data.get("status") == "already_processed"
        assert r2.data.get("replayed") is True

        # Transaction count must remain exactly 1
        tx_count_2 = PaymentTransaction.objects.filter(order=order, status=PaymentTransaction.StatusChoices.SUCCESS).count()
        assert tx_count_2 == 1

    # -------------------------------------------------------------------------
    # Scenario 9: Duplicate Checkout Submissions (Idempotency Key)
    # -------------------------------------------------------------------------
    def test_09_duplicate_checkout_submissions_idempotency_key(self, buyer_auth_client, in_part_listing):
        """Checkout with identical idempotency_key returns original order without double booking."""
        idem_key = f"idem_stage_e_{uuid.uuid4().hex[:12]}"
        initial_stock = in_part_listing.stock_quantity

        checkout_payload = {
            "items": [{"listing_id": str(in_part_listing.id), "quantity": 2}],
            "place_of_supply": "MH",
            "currency": "INR",
            "payment_method": "ONLINE",
            "shipping_name": "Rohan Double",
            "shipping_phone": "+91 9876544444",
            "shipping_address_line1": "88 Juhu Tara Road",
            "shipping_city": "Mumbai",
            "shipping_state": "MH",
            "shipping_postal_code": "400049",
            "shipping_country": "India",
            "idempotency_key": idem_key,
        }

        # Submission 1
        r1 = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", checkout_payload, format="json")
        assert r1.status_code == status.HTTP_201_CREATED
        order_num_1 = r1.data["order"]["order_number"]

        in_part_listing.refresh_from_db()
        assert in_part_listing.stock_quantity == initial_stock - 2

        # Submission 2 with same idempotency key
        r2 = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", checkout_payload, format="json")
        assert r2.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED)
        order_num_2 = r2.data["order"]["order_number"]
        assert order_num_1 == order_num_2

        # Stock must NOT be deducted twice
        in_part_listing.refresh_from_db()
        assert in_part_listing.stock_quantity == initial_stock - 2

    # -------------------------------------------------------------------------
    # Scenario 10: Incorrect Payment Amounts Rejected
    # -------------------------------------------------------------------------
    def test_10_incorrect_payment_amounts_rejected(self, buyer_auth_client, in_part_listing):
        """Payment verification and webhooks reject amount mismatches."""
        checkout_payload = {
            "items": [{"listing_id": str(in_part_listing.id), "quantity": 1}],
            "place_of_supply": "MH",
            "currency": "INR",
            "payment_method": "ONLINE",
            "shipping_name": "Amount Test",
            "shipping_phone": "+91 9876555555",
            "shipping_address_line1": "99 Linking Road",
            "shipping_city": "Mumbai",
            "shipping_state": "MH",
            "shipping_postal_code": "400050",
            "shipping_country": "India",
        }
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", checkout_payload, format="json")
        order = Order.objects.get(order_number=res.data["order"]["order_number"])
        session = PaymentService.create_payment_session(order)

        # 1. Verification payload amount mismatch
        tampered_amount = order.total_amount + Decimal("500.00")
        v_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order.order_number}/payment/verify/",
            {
                "razorpay_order_id": session["provider_order_id"],
                "razorpay_payment_id": "pay_test_tampered_amt",
                "razorpay_signature": "mock_sig",
                "amount": str(tampered_amount),
                "currency": "INR",
            },
            format="json",
        )
        assert v_res.status_code == status.HTTP_400_BAD_REQUEST
        assert "amount mismatch" in str(v_res.data).lower()

        # 2. Webhook amount mismatch for Stripe
        uk_order = Order.objects.create(
            buyer=order.buyer,
            order_number=f"ORD-UK-MISM-{uuid.uuid4().hex[:6]}",
            currency="GBP",
            total_amount=Decimal("150.00"),
            subtotal_taxable_amount=Decimal("150.00"),
            total_tax_amount=Decimal("0.00"),
            payment_method=PaymentMethodChoices.ONLINE,
            payment_status=PaymentStatusChoices.PENDING,
            payment_reference="pi_test_mismatch_amt_123",
        )
        fake_webhook_body = {
            "id": f"evt_mismatch_{uuid.uuid4().hex[:8]}",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": uk_order.payment_reference,
                    "amount": 9999,  # Mismatched amount
                    "currency": "gbp",
                    "metadata": {"order_number": uk_order.order_number},
                }
            }
        }
        body_bytes = json.dumps(fake_webhook_body).encode("utf-8")
        sig = build_stripe_signature(body_bytes, settings.STRIPE_WEBHOOK_SECRET, int(time.time()))
        client = APIClient()
        wb_res = client.post(
            "/api/v1/marketplace/payments/webhook/STRIPE/",
            data=body_bytes,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE=sig,
        )
        assert wb_res.status_code == status.HTTP_400_BAD_REQUEST
        assert "amount mismatch" in str(wb_res.data).lower()

    # -------------------------------------------------------------------------
    # Scenario 11: Currency Mismatch Rejected
    # -------------------------------------------------------------------------
    def test_11_currency_mismatch_rejected(self, buyer_auth_client, in_part_listing, uk_part_listing):
        """Cross-currency payloads and provider mismatches are strictly rejected."""
        # 1. INR order submitted with foreign currency in verification
        checkout_payload = {
            "items": [{"listing_id": str(in_part_listing.id), "quantity": 1}],
            "place_of_supply": "MH",
            "currency": "INR",
            "payment_method": "ONLINE",
            "shipping_name": "Currency Test",
            "shipping_phone": "+91 9876566666",
            "shipping_address_line1": "123 Churchgate",
            "shipping_city": "Mumbai",
            "shipping_state": "MH",
            "shipping_postal_code": "400020",
            "shipping_country": "India",
        }
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", checkout_payload, format="json")
        order = Order.objects.get(order_number=res.data["order"]["order_number"])
        session = PaymentService.create_payment_session(order)

        v_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order.order_number}/payment/verify/",
            {
                "razorpay_order_id": session["provider_order_id"],
                "razorpay_payment_id": "pay_test_curr_mismatch",
                "razorpay_signature": "mock_sig",
                "amount": str(order.total_amount),
                "currency": "USD",  # Mismatched currency
            },
            format="json",
        )
        assert v_res.status_code == status.HTTP_400_BAD_REQUEST
        assert "currency mismatch" in str(v_res.data).lower()

        # 2. Razorpay provider called with UK GBP order
        rzp_provider = RazorpayPaymentProvider()
        fake_gbp_order = Order(currency="GBP", total_amount=Decimal("100.00"))
        with pytest.raises(ValueError, match="only supports INR"):
            rzp_provider.create_payment_session(fake_gbp_order)

    # -------------------------------------------------------------------------
    # Scenario 12: Payment-to-Order Consistency
    # -------------------------------------------------------------------------
    def test_12_payment_to_order_consistency(self, buyer_auth_client, in_part_listing):
        """Verifies session locking: cannot verify payment using another order's session."""
        # Order 1
        res1 = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", {
            "items": [{"listing_id": str(in_part_listing.id), "quantity": 1}],
            "place_of_supply": "MH",
            "currency": "INR",
            "payment_method": "ONLINE",
            "shipping_name": "Buyer 1",
            "shipping_phone": "+91 9876577777",
            "shipping_address_line1": "Road 1",
            "shipping_city": "Mumbai",
            "shipping_state": "MH",
            "shipping_postal_code": "400050",
            "shipping_country": "India",
        }, format="json")
        order1 = Order.objects.get(order_number=res1.data["order"]["order_number"])
        session1 = PaymentService.create_payment_session(order1)

        # Order 2
        res2 = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", {
            "items": [{"listing_id": str(in_part_listing.id), "quantity": 1}],
            "place_of_supply": "MH",
            "currency": "INR",
            "payment_method": "ONLINE",
            "shipping_name": "Buyer 2",
            "shipping_phone": "+91 9876588888",
            "shipping_address_line1": "Road 2",
            "shipping_city": "Mumbai",
            "shipping_state": "MH",
            "shipping_postal_code": "400050",
            "shipping_country": "India",
        }, format="json")
        order2 = Order.objects.get(order_number=res2.data["order"]["order_number"])
        session2 = PaymentService.create_payment_session(order2)

        # Attempt to confirm Order 2 using Order 1's Razorpay order ID
        rzp_provider = RazorpayPaymentProvider()
        secret = rzp_provider.key_secret
        fake_sig = build_razorpay_signature(session1["provider_order_id"], "pay_fake_xorder", secret)

        v_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order2.order_number}/payment/verify/",
            {
                "razorpay_order_id": session1["provider_order_id"],  # Belongs to Order 1!
                "razorpay_payment_id": "pay_fake_xorder",
                "razorpay_signature": fake_sig,
            },
            format="json",
        )
        assert v_res.status_code == status.HTTP_400_BAD_REQUEST
        assert "does not match" in str(v_res.data).lower()

    # -------------------------------------------------------------------------
    # Scenario 13: Tax Snapshot Preservation from Stage D
    # -------------------------------------------------------------------------
    def test_13_tax_snapshot_preservation_from_stage_d(self, buyer_auth_client, in_part_listing):
        """Tax breakdown snapshot calculated during Stage D remains strictly unchanged after payment."""
        checkout_payload = {
            "items": [{"listing_id": str(in_part_listing.id), "quantity": 2}],
            "place_of_supply": "MH",
            "currency": "INR",
            "payment_method": "ONLINE",
            "shipping_name": "Tax Snapshot User",
            "shipping_phone": "+91 9876599999",
            "shipping_address_line1": "Flat 303 Tax View",
            "shipping_city": "Mumbai",
            "shipping_state": "MH",
            "shipping_postal_code": "400050",
            "shipping_country": "India",
        }
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", checkout_payload, format="json")
        order = Order.objects.get(order_number=res.data["order"]["order_number"])

        # Capture Stage D snapshot before payment
        pre_tax_breakdown = order.tax_breakdown
        pre_cgst = order.cgst_amount
        pre_sgst = order.sgst_amount
        pre_igst = order.igst_amount
        pre_total_tax = order.total_tax_amount
        pre_subtotal = order.subtotal_taxable_amount

        assert pre_tax_breakdown is not None
        assert pre_total_tax > 0

        # Create session and complete payment
        session = PaymentService.create_payment_session(order)
        rzp_order_id = session["provider_order_id"]
        rzp_payment_id = f"pay_snap_{uuid.uuid4().hex[:10]}"
        valid_sig = build_razorpay_signature(rzp_order_id, rzp_payment_id, settings.RAZORPAY_KEY_SECRET)

        v_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order.order_number}/payment/verify/",
            {
                "razorpay_order_id": rzp_order_id,
                "razorpay_payment_id": rzp_payment_id,
                "razorpay_signature": valid_sig,
            },
            format="json",
        )
        assert v_res.status_code == status.HTTP_200_OK

        order.refresh_from_db()
        assert order.payment_status == PaymentStatusChoices.PAID

        # Strictly verify tax fields are preserved
        assert order.tax_breakdown == pre_tax_breakdown
        assert order.cgst_amount == pre_cgst
        assert order.sgst_amount == pre_sgst
        assert order.igst_amount == pre_igst
        assert order.total_tax_amount == pre_total_tax
        assert order.subtotal_taxable_amount == pre_subtotal

    # -------------------------------------------------------------------------
    # Scenario 14: Multi-Seller Order Payment Consistency
    # -------------------------------------------------------------------------
    def test_14_multi_seller_order_payment_consistency(self, buyer_auth_client, in_part_listing, in_part_seller2):
        """Multi-seller cart creates one unified order with a single authoritative payment session."""
        checkout_payload = {
            "items": [
                {"listing_id": str(in_part_listing.id), "quantity": 1},
                {"listing_id": str(in_part_seller2.id), "quantity": 2},
            ],
            "place_of_supply": "MH",
            "currency": "INR",
            "payment_method": "ONLINE",
            "shipping_name": "Multi Seller Buyer",
            "shipping_phone": "+91 9876500002",
            "shipping_address_line1": "Multi Plaza",
            "shipping_city": "Mumbai",
            "shipping_state": "MH",
            "shipping_postal_code": "400050",
            "shipping_country": "India",
        }
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", checkout_payload, format="json")
        assert res.status_code == status.HTTP_201_CREATED, res.data

        order = Order.objects.get(order_number=res.data["order"]["order_number"])
        order_items = list(order.items.all())
        assert len(order_items) == 2

        # Verify distinct sellers
        sellers = {item.listing.seller_id for item in order_items}
        assert len(sellers) == 2

        # Unified payment session covers the whole order total across both sellers
        session = PaymentService.create_payment_session(order)
        expected_minor = int(round(order.total_amount * 100))
        assert session["amount_minor"] == expected_minor

        # Verify payment settles both sellers' items under the single order
        rzp_order_id = session["provider_order_id"]
        rzp_payment_id = f"pay_multi_{uuid.uuid4().hex[:10]}"
        valid_sig = build_razorpay_signature(rzp_order_id, rzp_payment_id, settings.RAZORPAY_KEY_SECRET)

        v_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order.order_number}/payment/verify/",
            {
                "razorpay_order_id": rzp_order_id,
                "razorpay_payment_id": rzp_payment_id,
                "razorpay_signature": valid_sig,
            },
            format="json",
        )
        assert v_res.status_code == status.HTTP_200_OK

        order.refresh_from_db()
        assert order.payment_status == PaymentStatusChoices.PAID
        assert order.status == OrderStatusChoices.CONFIRMED

    # -------------------------------------------------------------------------
    # Scenario 15: Frontend Payment Success and Failure Flows (API Parity)
    # -------------------------------------------------------------------------
    def test_15_frontend_payment_flows_and_cancellation(self, buyer_auth_client, in_part_listing):
        """Simulates frontend CartDrawer flow: checkout, session init, cancellation & stock restoration."""
        initial_stock = in_part_listing.stock_quantity

        # Step 1: Checkout
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", {
            "items": [{"listing_id": str(in_part_listing.id), "quantity": 3}],
            "place_of_supply": "MH",
            "currency": "INR",
            "payment_method": "ONLINE",
            "shipping_name": "Cancel Flow Buyer",
            "shipping_phone": "+91 9876500003",
            "shipping_address_line1": "Cancel Lane",
            "shipping_city": "Mumbai",
            "shipping_state": "MH",
            "shipping_postal_code": "400050",
            "shipping_country": "India",
        }, format="json")
        assert res.status_code == status.HTTP_201_CREATED
        order = Order.objects.get(order_number=res.data["order"]["order_number"])

        # Stock deducted on order placement
        in_part_listing.refresh_from_db()
        assert in_part_listing.stock_quantity == initial_stock - 3

        # Step 2: Session created
        s_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order.order_number}/payment/create/",
            format="json",
        )
        assert s_res.status_code == status.HTTP_200_OK
        assert s_res.data["payment_session"]["provider"] == "RAZORPAY"

        # Step 3: Buyer cancels payment modal from CartDrawer UI
        c_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order.order_number}/payment/cancel/",
            {"reason": "Buyer changed mind in payment modal"},
            format="json",
        )
        assert c_res.status_code == status.HTTP_200_OK
        assert c_res.data["status"] == "success"

        order.refresh_from_db()
        assert order.status == OrderStatusChoices.CANCELLED
        assert order.payment_status == PaymentStatusChoices.CANCELLED

        # Stock immediately restored
        in_part_listing.refresh_from_db()
        assert in_part_listing.stock_quantity == initial_stock

        # Cancelled transaction created
        cancel_tx = PaymentTransaction.objects.filter(
            order=order,
            status=PaymentTransaction.StatusChoices.CANCELLED,
        ).first()
        assert cancel_tx is not None
        assert "Buyer changed mind" in cancel_tx.error_message


# =============================================================================
# STAGE E – RETRY, DELAYED WEBHOOK & EDGE CASE VERIFICATION
# =============================================================================

@pytest.mark.django_db
class TestStageERetryAndEdgeCaseVerification:

    def test_failed_payment_followed_by_successful_retry(self, buyer_auth_client, in_part_listing):
        """Failed payment records FAILED transaction, allows new session and successful verification."""
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", {
            "items": [{"listing_id": str(in_part_listing.id), "quantity": 1}],
            "place_of_supply": "MH",
            "currency": "INR",
            "payment_method": "ONLINE",
            "shipping_name": "Retry Buyer",
            "shipping_phone": "+91 9876500010",
            "shipping_address_line1": "Retry Street 1",
            "shipping_city": "Mumbai",
            "shipping_state": "MH",
            "shipping_postal_code": "400050",
            "shipping_country": "India",
        }, format="json")
        order = Order.objects.get(order_number=res.data["order"]["order_number"])

        # 1. Report failure
        f_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order.order_number}/payment/failed/",
            {"reason": "Card declined by issuing bank", "payment_id": "pay_fail_001"},
            format="json",
        )
        assert f_res.status_code == status.HTTP_200_OK
        order.refresh_from_db()
        assert order.payment_status == PaymentStatusChoices.FAILED
        assert order.status == OrderStatusChoices.PENDING_CONFIRMATION

        # 2. Buyer initiates retry (creates fresh payment session)
        s_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order.order_number}/payment/create/",
            format="json",
        )
        assert s_res.status_code == status.HTTP_200_OK
        new_session = s_res.data["payment_session"]
        new_order_id = new_session["provider_order_id"]
        order.refresh_from_db()
        assert order.payment_reference == new_order_id

        # 3. Successful payment verification for retry
        new_payment_id = f"pay_retry_{uuid.uuid4().hex[:10]}"
        valid_sig = build_razorpay_signature(new_order_id, new_payment_id, settings.RAZORPAY_KEY_SECRET)
        v_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order.order_number}/payment/verify/",
            {
                "razorpay_order_id": new_order_id,
                "razorpay_payment_id": new_payment_id,
                "razorpay_signature": valid_sig,
            },
            format="json",
        )
        assert v_res.status_code == status.HTTP_200_OK
        order.refresh_from_db()
        assert order.payment_status == PaymentStatusChoices.PAID
        assert order.status == OrderStatusChoices.CONFIRMED

        # Audit both FAILED and SUCCESS transactions exist on the order ledger
        statuses = list(PaymentTransaction.objects.filter(order=order).values_list("status", flat=True))
        assert PaymentTransaction.StatusChoices.FAILED in statuses
        assert PaymentTransaction.StatusChoices.SUCCESS in statuses

    def test_retry_after_payment_modal_dismissal(self, buyer_auth_client, in_part_listing):
        """Dismissing checkout modal keeps order pending and allows immediate retry with same session."""
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", {
            "items": [{"listing_id": str(in_part_listing.id), "quantity": 1}],
            "place_of_supply": "MH",
            "currency": "INR",
            "payment_method": "ONLINE",
            "shipping_name": "Modal Dismiss Buyer",
            "shipping_phone": "+91 9876500011",
            "shipping_address_line1": "Dismiss St",
            "shipping_city": "Mumbai",
            "shipping_state": "MH",
            "shipping_postal_code": "400050",
            "shipping_country": "India",
        }, format="json")
        order = Order.objects.get(order_number=res.data["order"]["order_number"])
        session = res.data["payment_session"]

        # Modal is closed by user (frontend reports nothing or keeps order as is)
        order.refresh_from_db()
        assert order.status == OrderStatusChoices.PENDING_CONFIRMATION
        assert order.payment_status == PaymentStatusChoices.PENDING

        # Buyer clicks "Pay Now" again and succeeds
        rzp_order_id = session["provider_order_id"]
        rzp_pay_id = f"pay_after_dismiss_{uuid.uuid4().hex[:8]}"
        valid_sig = build_razorpay_signature(rzp_order_id, rzp_pay_id, settings.RAZORPAY_KEY_SECRET)

        v_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order.order_number}/payment/verify/",
            {
                "razorpay_order_id": rzp_order_id,
                "razorpay_payment_id": rzp_pay_id,
                "razorpay_signature": valid_sig,
            },
            format="json",
        )
        assert v_res.status_code == status.HTTP_200_OK
        order.refresh_from_db()
        assert order.payment_status == PaymentStatusChoices.PAID

    def test_cancelled_order_blocks_payment_verification(self, buyer_auth_client, in_part_listing):
        """If an order was cancelled and inventory restored, payment verification is strictly blocked."""
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", {
            "items": [{"listing_id": str(in_part_listing.id), "quantity": 1}],
            "place_of_supply": "MH",
            "currency": "INR",
            "payment_method": "ONLINE",
            "shipping_name": "Block Test Buyer",
            "shipping_phone": "+91 9876500012",
            "shipping_address_line1": "Block Lane",
            "shipping_city": "Mumbai",
            "shipping_state": "MH",
            "shipping_postal_code": "400050",
            "shipping_country": "India",
        }, format="json")
        order = Order.objects.get(order_number=res.data["order"]["order_number"])
        session = res.data["payment_session"]

        # Cancel the unpaid order
        c_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order.order_number}/payment/cancel/",
            {"reason": "Order cancelled by buyer"},
            format="json",
        )
        assert c_res.status_code == status.HTTP_200_OK

        order.refresh_from_db()
        assert order.status == OrderStatusChoices.CANCELLED

        # Attempt payment verification on cancelled order
        rzp_order_id = session["provider_order_id"]
        pay_id = "pay_on_cancelled_order"
        sig = build_razorpay_signature(rzp_order_id, pay_id, settings.RAZORPAY_KEY_SECRET)

        v_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order.order_number}/payment/verify/",
            {
                "razorpay_order_id": rzp_order_id,
                "razorpay_payment_id": pay_id,
                "razorpay_signature": sig,
            },
            format="json",
        )
        assert v_res.status_code == status.HTTP_400_BAD_REQUEST
        assert "cancelled" in str(v_res.data).lower()

    def test_delayed_webhook_delivery_after_client_verification(self, buyer_auth_client, in_part_listing):
        """When client verification already confirmed the order, a delayed webhook does not overwrite or duplicate."""
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", {
            "items": [{"listing_id": str(in_part_listing.id), "quantity": 1}],
            "place_of_supply": "MH",
            "currency": "INR",
            "payment_method": "ONLINE",
            "shipping_name": "Delayed Webhook Buyer",
            "shipping_phone": "+91 9876500013",
            "shipping_address_line1": "Delayed Webhook Rd",
            "shipping_city": "Mumbai",
            "shipping_state": "MH",
            "shipping_postal_code": "400050",
            "shipping_country": "India",
        }, format="json")
        order = Order.objects.get(order_number=res.data["order"]["order_number"])
        session = res.data["payment_session"]
        rzp_order_id = session["provider_order_id"]
        rzp_pay_id = f"pay_client_first_{uuid.uuid4().hex[:8]}"

        # 1. Client verifies first
        sig = build_razorpay_signature(rzp_order_id, rzp_pay_id, settings.RAZORPAY_KEY_SECRET)
        v_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order.order_number}/payment/verify/",
            {
                "razorpay_order_id": rzp_order_id,
                "razorpay_payment_id": rzp_pay_id,
                "razorpay_signature": sig,
            },
            format="json",
        )
        assert v_res.status_code == status.HTTP_200_OK
        order.refresh_from_db()
        assert order.payment_status == PaymentStatusChoices.PAID
        initial_paid_at = order.paid_at
        tx_count_before = PaymentTransaction.objects.filter(order=order, status=PaymentTransaction.StatusChoices.SUCCESS).count()

        # 2. Delayed webhook arrives minutes later
        wb_body = {
            "entity": "event",
            "event": "order.paid",
            "payload": {
                "order": {
                    "entity": {
                        "id": rzp_order_id,
                        "amount": int(round(order.total_amount * 100)),
                        "currency": "INR",
                        "notes": {"order_number": order.order_number},
                    }
                },
                "payment": {
                    "entity": {
                        "id": rzp_pay_id,
                        "amount": int(round(order.total_amount * 100)),
                        "currency": "INR",
                    }
                }
            }
        }
        raw_body = json.dumps(wb_body).encode("utf-8")
        wb_sig = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        client = APIClient()
        wb_res = client.post(
            "/api/v1/marketplace/payments/webhook/RAZORPAY/",
            data=raw_body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=wb_sig,
            HTTP_X_RAZORPAY_EVENT_ID=f"evt_delayed_{uuid.uuid4().hex[:8]}",
        )
        assert wb_res.status_code == status.HTTP_200_OK

        order.refresh_from_db()
        assert order.payment_status == PaymentStatusChoices.PAID
        assert order.paid_at == initial_paid_at

    def test_client_verification_after_early_webhook(self, buyer_auth_client, in_part_listing):
        """When webhook confirms order before client verification, verification returns already_paid."""
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", {
            "items": [{"listing_id": str(in_part_listing.id), "quantity": 1}],
            "place_of_supply": "MH",
            "currency": "INR",
            "payment_method": "ONLINE",
            "shipping_name": "Early Webhook Buyer",
            "shipping_phone": "+91 9876500014",
            "shipping_address_line1": "Early Webhook Blvd",
            "shipping_city": "Mumbai",
            "shipping_state": "MH",
            "shipping_postal_code": "400050",
            "shipping_country": "India",
        }, format="json")
        order = Order.objects.get(order_number=res.data["order"]["order_number"])
        session = res.data["payment_session"]
        rzp_order_id = session["provider_order_id"]

        # 1. Early webhook arrives first
        wb_body = {
            "entity": "event",
            "event": "order.paid",
            "payload": {
                "order": {
                    "entity": {
                        "id": rzp_order_id,
                        "amount": int(round(order.total_amount * 100)),
                        "currency": "INR",
                        "notes": {"order_number": order.order_number},
                    }
                },
                "payment": {
                    "entity": {
                        "id": "pay_early_wb_001",
                        "amount": int(round(order.total_amount * 100)),
                        "currency": "INR",
                    }
                }
            }
        }
        raw_body = json.dumps(wb_body).encode("utf-8")
        wb_sig = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        client = APIClient()
        wb_res = client.post(
            "/api/v1/marketplace/payments/webhook/RAZORPAY/",
            data=raw_body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=wb_sig,
            HTTP_X_RAZORPAY_EVENT_ID=f"evt_early_{uuid.uuid4().hex[:8]}",
        )
        assert wb_res.status_code == status.HTTP_200_OK

        order.refresh_from_db()
        assert order.payment_status == PaymentStatusChoices.PAID
        assert order.status == OrderStatusChoices.CONFIRMED

        # 2. Client verification arrives later
        sig = build_razorpay_signature(rzp_order_id, "pay_early_wb_001", settings.RAZORPAY_KEY_SECRET)
        v_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order.order_number}/payment/verify/",
            {
                "razorpay_order_id": rzp_order_id,
                "razorpay_payment_id": "pay_early_wb_001",
                "razorpay_signature": sig,
            },
            format="json",
        )
        assert v_res.status_code == status.HTTP_200_OK
        assert v_res.data.get("extra", {}).get("already_paid") is True

    def test_multiple_payment_attempts_against_same_order(self, buyer_auth_client, in_part_listing):
        """Multiple failed or abandoned attempts are tracked, but only one success can finalize the order."""
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", {
            "items": [{"listing_id": str(in_part_listing.id), "quantity": 1}],
            "place_of_supply": "MH",
            "currency": "INR",
            "payment_method": "ONLINE",
            "shipping_name": "Multi Attempt Buyer",
            "shipping_phone": "+91 9876500015",
            "shipping_address_line1": "Multi Lane",
            "shipping_city": "Mumbai",
            "shipping_state": "MH",
            "shipping_postal_code": "400050",
            "shipping_country": "India",
        }, format="json")
        order = Order.objects.get(order_number=res.data["order"]["order_number"])

        # Attempt 1: Failed
        buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order.order_number}/payment/failed/",
            {"reason": "Attempt 1 network dropped", "payment_id": "pay_att_1"},
            format="json",
        )

        # Attempt 2: Failed
        buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order.order_number}/payment/failed/",
            {"reason": "Attempt 2 user cancelled at bank", "payment_id": "pay_att_2"},
            format="json",
        )

        # Attempt 3: New session and Success
        s_res = buyer_auth_client.post(f"/api/v1/marketplace/orders/{order.order_number}/payment/create/", format="json")
        session3 = s_res.data["payment_session"]
        rzp_order_id = session3["provider_order_id"]
        pay_id_3 = "pay_att_3_success"
        sig = build_razorpay_signature(rzp_order_id, pay_id_3, settings.RAZORPAY_KEY_SECRET)

        v_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order.order_number}/payment/verify/",
            {
                "razorpay_order_id": rzp_order_id,
                "razorpay_payment_id": pay_id_3,
                "razorpay_signature": sig,
            },
            format="json",
        )
        assert v_res.status_code == status.HTTP_200_OK

        order.refresh_from_db()
        assert order.payment_status == PaymentStatusChoices.PAID
        assert order.status == OrderStatusChoices.CONFIRMED

        # Attempt 4 after already paid returns already_paid, does not create another transaction
        v_res_4 = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order.order_number}/payment/verify/",
            {
                "razorpay_order_id": rzp_order_id,
                "razorpay_payment_id": "pay_att_4_redundant",
                "razorpay_signature": "mock",
            },
            format="json",
        )
        assert v_res_4.status_code == status.HTTP_200_OK
        assert v_res_4.data.get("extra", {}).get("already_paid") is True

        # Exactly 1 SUCCESS transaction exists
        assert PaymentTransaction.objects.filter(order=order, status=PaymentTransaction.StatusChoices.SUCCESS).count() == 1

    def test_razorpay_success_webhook_on_cancelled_order_ignored(self, buyer_auth_client, in_part_listing):
        """A valid Razorpay order.paid webhook cannot revive a CANCELLED order to PAID or CONFIRMED."""
        initial_stock = in_part_listing.stock_quantity
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", {
            "items": [{"listing_id": str(in_part_listing.id), "quantity": 2}],
            "place_of_supply": "MH",
            "currency": "INR",
            "payment_method": "ONLINE",
            "shipping_name": "Cancelled Order Webhook Buyer",
            "shipping_phone": "+91 9876500016",
            "shipping_address_line1": "Cancelled Webhook St",
            "shipping_city": "Mumbai",
            "shipping_state": "MH",
            "shipping_postal_code": "400050",
            "shipping_country": "India",
        }, format="json")
        order = Order.objects.get(order_number=res.data["order"]["order_number"])
        session = res.data["payment_session"]
        rzp_order_id = session["provider_order_id"]

        # 1. Order is cancelled by buyer and inventory restored
        c_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order.order_number}/payment/cancel/",
            {"reason": "Buyer abandoned and cancelled"},
            format="json",
        )
        assert c_res.status_code == status.HTTP_200_OK

        order.refresh_from_db()
        assert order.status == OrderStatusChoices.CANCELLED
        assert order.payment_status == PaymentStatusChoices.CANCELLED
        in_part_listing.refresh_from_db()
        assert in_part_listing.stock_quantity == initial_stock

        # 2. Late Razorpay order.paid webhook arrives with valid signature
        event_id = f"evt_late_rzp_{uuid.uuid4().hex[:8]}"
        wb_body = {
            "entity": "event",
            "event": "order.paid",
            "payload": {
                "order": {
                    "entity": {
                        "id": rzp_order_id,
                        "amount": int(round(order.total_amount * 100)),
                        "currency": "INR",
                        "notes": {"order_number": order.order_number},
                    }
                },
                "payment": {
                    "entity": {
                        "id": f"pay_late_{uuid.uuid4().hex[:8]}",
                        "amount": int(round(order.total_amount * 100)),
                        "currency": "INR",
                    }
                }
            }
        }
        raw_body = json.dumps(wb_body).encode("utf-8")
        wb_sig = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

        client = APIClient()
        wb_res = client.post(
            "/api/v1/marketplace/payments/webhook/RAZORPAY/",
            data=raw_body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=wb_sig,
            HTTP_X_RAZORPAY_EVENT_ID=event_id,
        )
        assert wb_res.status_code == status.HTTP_200_OK
        assert wb_res.data.get("status") == "ignored"

        # 3. Order MUST remain CANCELLED, never PAID or CONFIRMED
        order.refresh_from_db()
        assert order.status == OrderStatusChoices.CANCELLED
        assert order.payment_status == PaymentStatusChoices.CANCELLED

        # 4. No SUCCESS PaymentTransaction created
        assert PaymentTransaction.objects.filter(order=order, status=PaymentTransaction.StatusChoices.SUCCESS).count() == 0

        # 5. Restored inventory is NOT re-deducted
        in_part_listing.refresh_from_db()
        assert in_part_listing.stock_quantity == initial_stock

        # 6. Replayed webhook remains idempotent
        replay_res = client.post(
            "/api/v1/marketplace/payments/webhook/RAZORPAY/",
            data=raw_body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=wb_sig,
            HTTP_X_RAZORPAY_EVENT_ID=event_id,
        )
        assert replay_res.status_code == status.HTTP_200_OK
        assert replay_res.data.get("status") == "already_processed"
        assert replay_res.data.get("replayed") is True

    def test_stripe_success_webhook_on_cancelled_order_ignored(self, buyer_auth_client, uk_part_listing):
        """A valid Stripe payment_intent.succeeded webhook cannot revive a CANCELLED order to PAID or CONFIRMED."""
        initial_stock = uk_part_listing.stock_quantity
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", {
            "items": [{"listing_id": str(uk_part_listing.id), "quantity": 1}],
            "currency": "GBP",
            "payment_method": "ONLINE",
            "shipping_name": "Cancelled UK Webhook Buyer",
            "shipping_phone": "+44 7911 000017",
            "shipping_address_line1": "Cancelled UK Rd",
            "shipping_city": "London",
            "shipping_state": "Greater London",
            "shipping_postal_code": "SW1A 1AA",
            "shipping_country": "United Kingdom",
        }, format="json")
        order = Order.objects.get(order_number=res.data["order"]["order_number"])
        session = PaymentService.create_payment_session(order)
        pi_id = session["provider_order_id"]

        # 1. Order is cancelled by buyer and inventory restored
        c_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order.order_number}/payment/cancel/",
            {"reason": "Buyer decided to cancel"},
            format="json",
        )
        assert c_res.status_code == status.HTTP_200_OK

        order.refresh_from_db()
        assert order.status == OrderStatusChoices.CANCELLED
        assert order.payment_status == PaymentStatusChoices.CANCELLED
        uk_part_listing.refresh_from_db()
        assert uk_part_listing.stock_quantity == initial_stock

        # 2. Late Stripe payment_intent.succeeded webhook arrives with valid signature
        event_id = f"evt_late_stripe_{uuid.uuid4().hex[:8]}"
        succ_body = {
            "id": event_id,
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": pi_id,
                    "amount": int(round(order.total_amount * 100)),
                    "currency": "gbp",
                    "metadata": {
                        "order_number": order.order_number,
                    },
                }
            }
        }
        body_bytes = json.dumps(succ_body).encode("utf-8")
        timestamp = int(time.time())
        sig = build_stripe_signature(body_bytes, settings.STRIPE_WEBHOOK_SECRET, timestamp)

        client = APIClient()
        wb_res = client.post(
            "/api/v1/marketplace/payments/webhook/STRIPE/",
            data=body_bytes,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE=sig,
        )
        assert wb_res.status_code == status.HTTP_200_OK
        assert wb_res.data.get("status") == "ignored"

        # 3. Order MUST remain CANCELLED, never PAID or CONFIRMED
        order.refresh_from_db()
        assert order.status == OrderStatusChoices.CANCELLED
        assert order.payment_status == PaymentStatusChoices.CANCELLED

        # 4. No SUCCESS PaymentTransaction created
        assert PaymentTransaction.objects.filter(order=order, status=PaymentTransaction.StatusChoices.SUCCESS).count() == 0

        # 5. Restored inventory remains restored
        uk_part_listing.refresh_from_db()
        assert uk_part_listing.stock_quantity == initial_stock

        # 6. Replayed webhook remains idempotent
        replay_res = client.post(
            "/api/v1/marketplace/payments/webhook/STRIPE/",
            data=body_bytes,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE=sig,
        )
        assert replay_res.status_code == status.HTTP_200_OK
        assert replay_res.data.get("status") == "already_processed"
        assert replay_res.data.get("replayed") is True



