import base64
import hashlib
import hmac
import json
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


# =============================================================================
# RAZORPAY TEST MODE INTEGRATION - 8 SCENARIOS
# =============================================================================

class TestRazorpayActualTestModeIntegration:
    """
    Comprehensive test suite verifying the 8 specific payment scenarios required:
    1. Successful Razorpay test payment.
    2. Failed payment.
    3. Cancelled checkout.
    4. Invalid payment signature.
    5. Duplicate payment callback.
    6. Order amount mismatch.
    7. COD checkout still works.
    8. Order status updates correctly after verified payment.
    """

    # -------------------------------------------------------------------------
    # Scenario 1: Successful Razorpay test payment
    # -------------------------------------------------------------------------
    def test_scenario_1_successful_razorpay_test_payment(self, buyer_auth_client, in_part):
        payload = valid_india_shipping_payload(in_part.id, quantity=1, payment_method="ONLINE")
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        assert res.status_code == status.HTTP_201_CREATED
        order_data = res.json()["order"]
        session_data = res.json()["payment_session"]

        order_id = order_data["id"]
        razorpay_order_id = session_data["provider_order_id"]
        assert razorpay_order_id.startswith("order_")
        assert session_data["key_id"] == settings.RAZORPAY_KEY_ID
        assert session_data["currency"] == "INR"

        # Generate genuine HMAC-SHA256 signature using the backend Key Secret
        sim_payment_id = f"pay_test_{uuid.uuid4().hex[:12]}"
        msg = f"{razorpay_order_id}|{sim_payment_id}".encode("utf-8")
        secret = settings.RAZORPAY_KEY_SECRET
        valid_signature = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()

        # Submit verification
        v_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order_id}/payment/verify/",
            {
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": sim_payment_id,
                "razorpay_signature": valid_signature,
                "amount": order_data["total_amount"],
                "currency": "INR",
            },
            format="json",
        )
        assert v_res.status_code == status.HTTP_200_OK
        v_data = v_res.json()
        assert v_data["status"] == "success"
        assert v_data["payment_status"] == "PAID"
        assert v_data["payment_reference"] == sim_payment_id

        # Verify DB state
        order = Order.objects.get(id=order_id)
        assert order.payment_status == PaymentStatusChoices.PAID
        assert order.status == OrderStatusChoices.CONFIRMED
        assert order.paid_at is not None
        assert order.payment_reference == sim_payment_id

        # Verify Transaction Ledger
        tx = PaymentTransaction.objects.filter(order=order, status=PaymentTransaction.StatusChoices.SUCCESS).first()
        assert tx is not None
        assert tx.provider == "RAZORPAY"
        assert tx.provider_transaction_id == sim_payment_id
        assert tx.amount == order.total_amount

    # -------------------------------------------------------------------------
    # Scenario 2: Failed payment
    # -------------------------------------------------------------------------
    def test_scenario_2_failed_payment_handling(self, buyer_auth_client, in_part):
        payload = valid_india_shipping_payload(in_part.id, quantity=1, payment_method="ONLINE")
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        order_id = res.json()["order"]["id"]

        # Report client-side failure (e.g. from Razorpay modal on payment failure)
        fail_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order_id}/payment/failed/",
            {
                "reason": "Payment was declined by issuing bank (Insufficient funds).",
                "payment_id": "pay_declined_123",
                "error_code": "BAD_REQUEST_ERROR",
            },
            format="json",
        )
        assert fail_res.status_code == status.HTTP_200_OK
        assert fail_res.json()["payment_status"] == "FAILED"

        order = Order.objects.get(id=order_id)
        assert order.payment_status == PaymentStatusChoices.FAILED
        # Order is NOT cancelled (buyer can retry payment)
        assert order.status == OrderStatusChoices.PENDING_CONFIRMATION

        tx = PaymentTransaction.objects.filter(order=order, status=PaymentTransaction.StatusChoices.FAILED).first()
        assert tx is not None
        assert "Payment was declined" in tx.error_message
        assert tx.provider_transaction_id == "pay_declined_123"

    # -------------------------------------------------------------------------
    # Scenario 3: Cancelled checkout
    # -------------------------------------------------------------------------
    def test_scenario_3_cancelled_checkout_restores_inventory(self, buyer_auth_client, in_part):
        initial_stock = in_part.stock_quantity
        payload = valid_india_shipping_payload(in_part.id, quantity=2, payment_method="ONLINE")
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        order_id = res.json()["order"]["id"]

        # Stock was reserved/deducted upon order creation
        in_part.refresh_from_db()
        assert in_part.stock_quantity == initial_stock - 2

        # Buyer cancels checkout
        cancel_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order_id}/payment/cancel/",
            {"reason": "Buyer closed checkout modal and cancelled"},
            format="json",
        )
        assert cancel_res.status_code == status.HTTP_200_OK
        data = cancel_res.json()
        assert data["status"] == "success"
        assert data["order"]["status"] == "CANCELLED"
        assert data["order"]["payment_status"] == "CANCELLED"

        # Stock is immediately restored to catalogue!
        in_part.refresh_from_db()
        assert in_part.stock_quantity == initial_stock

        # Cancelling an already paid order via payment cancel is strictly rejected
        paid_payload = valid_india_shipping_payload(in_part.id, quantity=1)
        p_res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", paid_payload, format="json")
        paid_order_id = p_res.json()["order"]["id"]
        Order.objects.filter(id=paid_order_id).update(payment_status=PaymentStatusChoices.PAID)

        c_paid_res = buyer_auth_client.post(f"/api/v1/marketplace/orders/{paid_order_id}/payment/cancel/")
        assert c_paid_res.status_code == status.HTTP_400_BAD_REQUEST
        assert "already been paid" in c_paid_res.json()["error"]

    # -------------------------------------------------------------------------
    # Scenario 4: Invalid payment signature
    # -------------------------------------------------------------------------
    def test_scenario_4_invalid_payment_signature_rejected(self, buyer_auth_client, in_part):
        payload = valid_india_shipping_payload(in_part.id, quantity=1, payment_method="ONLINE")
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        order_data = res.json()["order"]
        session_data = res.json()["payment_session"]
        order_id = order_data["id"]

        # Send forged/tampered signature
        verify_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order_id}/payment/verify/",
            {
                "razorpay_order_id": session_data["provider_order_id"],
                "razorpay_payment_id": "pay_fake_signature_123",
                "razorpay_signature": "bad_signature_00000000000000000000000000000000",
            },
            format="json",
        )
        assert verify_res.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid Razorpay payment signature" in verify_res.json()["error"]

        order = Order.objects.get(id=order_id)
        assert order.payment_status == PaymentStatusChoices.PENDING
        assert order.paid_at is None

        # Failed transaction recorded in ledger
        failed_tx = PaymentTransaction.objects.filter(order=order, status=PaymentTransaction.StatusChoices.FAILED).first()
        assert failed_tx is not None
        assert "Invalid Razorpay payment signature" in failed_tx.error_message

    # -------------------------------------------------------------------------
    # Scenario 5: Duplicate payment callback
    # -------------------------------------------------------------------------
    def test_scenario_5_duplicate_payment_callback_is_idempotent(self, buyer_auth_client, in_part):
        payload = valid_india_shipping_payload(in_part.id, quantity=1, payment_method="ONLINE")
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        order_data = res.json()["order"]
        session_data = res.json()["payment_session"]
        order_id = order_data["id"]

        rzp_order_id = session_data["provider_order_id"]
        rzp_pay_id = f"pay_idem_{uuid.uuid4().hex[:10]}"
        msg = f"{rzp_order_id}|{rzp_pay_id}".encode("utf-8")
        valid_sig = hmac.new(settings.RAZORPAY_KEY_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()

        verify_body = {
            "razorpay_order_id": rzp_order_id,
            "razorpay_payment_id": rzp_pay_id,
            "razorpay_signature": valid_sig,
        }

        # 1. First verification: marks PAID
        res1 = buyer_auth_client.post(f"/api/v1/marketplace/orders/{order_id}/payment/verify/", verify_body, format="json")
        assert res1.status_code == status.HTTP_200_OK
        assert res1.json()["payment_status"] == "PAID"

        order = Order.objects.get(id=order_id)
        first_paid_at = order.paid_at
        tx_count_1 = PaymentTransaction.objects.filter(order=order, status=PaymentTransaction.StatusChoices.SUCCESS).count()
        assert tx_count_1 == 1

        # 2. Duplicate verification call (replay)
        res2 = buyer_auth_client.post(f"/api/v1/marketplace/orders/{order_id}/payment/verify/", verify_body, format="json")
        assert res2.status_code == status.HTTP_200_OK
        assert res2.json()["payment_status"] == "PAID"
        assert res2.json()["extra"].get("already_paid") is True

        order.refresh_from_db()
        assert order.paid_at == first_paid_at
        tx_count_2 = PaymentTransaction.objects.filter(order=order, status=PaymentTransaction.StatusChoices.SUCCESS).count()
        assert tx_count_2 == 1  # No duplicate transaction created!

    # -------------------------------------------------------------------------
    # Scenario 6: Order amount mismatch
    # -------------------------------------------------------------------------
    def test_scenario_6_order_amount_mismatch_rejected(self, buyer_auth_client, in_part):
        payload = valid_india_shipping_payload(in_part.id, quantity=1, payment_method="ONLINE")
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        order_data = res.json()["order"]
        session_data = res.json()["payment_session"]
        order_id = order_data["id"]
        rzp_order_id = session_data["provider_order_id"]

        sim_payment_id = f"pay_mismatch_{uuid.uuid4().hex[:10]}"
        msg = f"{rzp_order_id}|{sim_payment_id}".encode("utf-8")
        valid_sig = hmac.new(settings.RAZORPAY_KEY_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()

        # Submit verification with mismatched amount (e.g. 500.00 instead of 4720.00)
        verify_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order_id}/payment/verify/",
            {
                "razorpay_order_id": rzp_order_id,
                "razorpay_payment_id": sim_payment_id,
                "razorpay_signature": valid_sig,
                "amount": "500.00",
                "currency": "INR",
            },
            format="json",
        )
        assert verify_res.status_code == status.HTTP_400_BAD_REQUEST
        assert "Payment amount mismatch" in verify_res.json()["error"]

        order = Order.objects.get(id=order_id)
        assert order.payment_status == PaymentStatusChoices.PENDING

        # Currency mismatch test
        curr_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order_id}/payment/verify/",
            {
                "razorpay_order_id": rzp_order_id,
                "razorpay_payment_id": sim_payment_id,
                "razorpay_signature": valid_sig,
                "amount": str(order.total_amount),
                "currency": "USD",
            },
            format="json",
        )
        assert curr_res.status_code == status.HTTP_400_BAD_REQUEST
        assert "currency mismatch" in curr_res.json()["error"].lower()

    # -------------------------------------------------------------------------
    # Scenario 7: COD checkout still works
    # -------------------------------------------------------------------------
    def test_scenario_7_cod_checkout_preserved(self, buyer_auth_client, staff_user, in_part):
        initial_stock = in_part.stock_quantity
        payload = valid_india_shipping_payload(in_part.id, quantity=1, payment_method="COD")
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")

        assert res.status_code == status.HTTP_201_CREATED
        order_data = res.json()["order"]
        session_data = res.json()["payment_session"]

        assert order_data["payment_method"] == "COD"
        assert order_data["payment_status"] == "PENDING"
        assert order_data["cod_collection_status"] == "PENDING"
        assert session_data["provider"] == "COD"

        # Stock was deducted for COD
        in_part.refresh_from_db()
        assert in_part.stock_quantity == initial_stock - 1

        order = Order.objects.get(id=order_data["id"])

        # Attempting online verification on COD order is strictly rejected
        v_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order.id}/payment/verify/",
            {"razorpay_payment_id": "pay_test", "razorpay_order_id": "order_test", "razorpay_signature": "sig"},
            format="json",
        )
        assert v_res.status_code == status.HTTP_400_BAD_REQUEST
        assert "Cash on Delivery" in v_res.json()["error"]

        # Staff marks COD collected
        staff_client = APIClient()
        staff_client.force_authenticate(user=staff_user)
        cod_update_res = staff_client.post(
            f"/api/v1/marketplace/orders/{order.id}/cod-collection/",
            {"cod_collection_status": "COLLECTED", "notes": "Cash collected by delivery agent."},
            format="json",
        )
        assert cod_update_res.status_code == status.HTTP_200_OK

        order.refresh_from_db()
        assert order.cod_collection_status == CODCollectionStatusChoices.COLLECTED
        assert order.payment_status == PaymentStatusChoices.PAID
        assert order.cod_collected_at is not None

    # -------------------------------------------------------------------------
    # Scenario 8: Order status updates correctly after verified payment
    # -------------------------------------------------------------------------
    def test_scenario_8_order_status_transitions_verified_payment(self, buyer_auth_client, in_part):
        # 1. State before checkout
        payload = valid_india_shipping_payload(in_part.id, quantity=1, payment_method="ONLINE")
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        order_id = res.json()["order"]["id"]
        order = Order.objects.get(id=order_id)

        # 2. State immediately after checkout: PENDING_CONFIRMATION, PENDING
        assert order.status == OrderStatusChoices.PENDING_CONFIRMATION
        assert order.payment_status == PaymentStatusChoices.PENDING
        assert order.paid_at is None
        assert order.payment_reference.startswith("order_")

        # 3. Cryptographically valid payment verification
        pay_id = f"pay_verified_{uuid.uuid4().hex[:10]}"
        msg = f"{order.payment_reference}|{pay_id}".encode("utf-8")
        sig = hmac.new(settings.RAZORPAY_KEY_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()

        v_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order_id}/payment/verify/",
            {
                "razorpay_order_id": order.payment_reference,
                "razorpay_payment_id": pay_id,
                "razorpay_signature": sig,
            },
            format="json",
        )
        assert v_res.status_code == status.HTTP_200_OK

        # 4. State immediately after verified payment: CONFIRMED, PAID
        order.refresh_from_db()
        assert order.status == OrderStatusChoices.CONFIRMED
        assert order.payment_status == PaymentStatusChoices.PAID
        assert order.paid_at is not None
        assert order.payment_reference == pay_id
    # -------------------------------------------------------------------------
    # Scenario 9: Live Razorpay account methods discovery
    # -------------------------------------------------------------------------
    def test_scenario_9_razorpay_account_methods_discovery(self):
        """
        Verifies that RazorpayPaymentProvider discovers live payment method capabilities
        from Razorpay /v1/methods without hardcoding unsupported methods.
        """
        from apps.marketplace.payments.razorpay_provider import RazorpayPaymentProvider
        provider = RazorpayPaymentProvider()
        methods = provider.get_account_methods()

        assert "card" in methods
        assert "netbanking" in methods
        assert "wallet" in methods
        assert "upi" in methods
        assert "upi_intent" in methods
        assert methods["card"] is True

    # -------------------------------------------------------------------------
    # Scenario 10: UPI payment verification and state transition
    # -------------------------------------------------------------------------
    def test_scenario_10_upi_payment_verification_and_state_transition(self, buyer_auth_client, in_part):
        """
        Verifies that completing a payment via UPI (using UPI Intent or VPA callback)
        is verified cryptographically and successfully marks the order PAID and CONFIRMED.
        """
        payload = valid_india_shipping_payload(in_part.id, quantity=1, payment_method="ONLINE")
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        assert res.status_code == status.HTTP_201_CREATED
        order_data = res.json()["order"]
        order_id = order_data["id"]
        order = Order.objects.get(id=order_id)
        order_ref = order.payment_reference

        # Simulate UPI payment callback (e.g. from Google Pay / PhonePe / Paytm / VPA test)
        upi_pay_id = f"pay_upi_{uuid.uuid4().hex[:10]}"
        msg = f"{order_ref}|{upi_pay_id}".encode("utf-8")
        sig = hmac.new(settings.RAZORPAY_KEY_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()

        verify_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order_id}/payment/verify/",
            {
                "razorpay_order_id": order_ref,
                "razorpay_payment_id": upi_pay_id,
                "razorpay_signature": sig,
                "amount": str(order.total_amount),
                "currency": "INR",
            },
            format="json",
        )
        assert verify_res.status_code == status.HTTP_200_OK
        verify_data = verify_res.json()
        assert verify_data["status"] == "success"
        assert verify_data["order"]["payment_status"] == "PAID"

        order.refresh_from_db()
        assert order.payment_status == PaymentStatusChoices.PAID
        assert order.status == OrderStatusChoices.CONFIRMED
        assert order.payment_reference == upi_pay_id

    # -------------------------------------------------------------------------
    # Scenario 11: Payment session includes methods_info metadata
    # -------------------------------------------------------------------------
    def test_scenario_11_payment_session_includes_methods_info_metadata(self, buyer_auth_client, in_part):
        """
        Verifies that payment session creation returns methods_info with UPI and card capabilities.
        """
        payload = valid_india_shipping_payload(in_part.id, quantity=1, payment_method="ONLINE")
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", payload, format="json")
        assert res.status_code == status.HTTP_201_CREATED
        session_data = res.json()["payment_session"]

        assert "methods_info" in session_data
        methods_info = session_data["methods_info"]
        assert "card" in methods_info
        assert "upi" in methods_info
        assert "upi_intent" in methods_info

