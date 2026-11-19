import hashlib
import hmac
import json
import uuid
from decimal import Decimal
import datetime
import pytest
from django.conf import settings
from django.utils import timezone
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
    Refund,
    RefundStatusChoices,
    RefundMethodChoices,
)
from apps.marketplace.payments.service import PaymentService
from apps.marketplace.payments.razorpay_provider import RazorpayPaymentProvider
from apps.marketplace.returns.service import RefundService
from platform_core.audit.models import AuditLog
from unittest.mock import patch
from django.core.exceptions import ValidationError as DjangoValidationError


class MockHTTPResponse:
    def __init__(self, body_bytes: bytes, status_code: int = 200):
        self._body = body_bytes
        self.status = status_code
        self.code = status_code

    def read(self, *args, **kwargs):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


def build_razorpay_signature(order_id: str, payment_id: str, secret: str) -> str:
    msg = f"{order_id}|{payment_id}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def build_stripe_signature(body_bytes: bytes, secret: str, timestamp: int) -> str:
    signed_payload = f"{timestamp}.{body_bytes.decode('utf-8')}".encode("utf-8")
    v1_sig = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={v1_sig}"


@pytest.fixture
def brake_category(db):
    return PartCategory.objects.create(name="Brakes", slug=f"brakes-{uuid.uuid4().hex[:6]}")


@pytest.fixture
def parts_seller(db):
    user = User.objects.create_user(
        email=f"seller_{uuid.uuid4().hex[:6]}@driverxtra.com",
        password="SecurePassword123!",
        first_name="Parts",
        last_name="Seller",
        is_email_verified=True,
    )
    user.add_role(RoleChoices.SELLER)
    return user


@pytest.fixture
def test_part_listing(db, parts_seller, brake_category):
    return SparePartListing.objects.create(
        seller=parts_seller,
        category=brake_category,
        name="Brembo Front Brake Rotor",
        brand="Brembo",
        mpn=f"BR-IN-{uuid.uuid4().hex[:4]}",
        price=Decimal("1500.00"),
        currency="INR",
        hsn_code="8708",
        gst_rate=Decimal("18.00"),
        stock_quantity=10,
        status=ListingStatusChoices.APPROVED,
        is_active=True,
    )


@pytest.fixture
def test_uk_part_listing(db, parts_seller, brake_category):
    return SparePartListing.objects.create(
        seller=parts_seller,
        category=brake_category,
        name="EBC Brake Pads (UK)",
        brand="EBC",
        mpn=f"EBC-UK-{uuid.uuid4().hex[:4]}",
        price=Decimal("120.00"),
        currency="GBP",
        hsn_code="8708",
        gst_rate=Decimal("0.00"),
        stock_quantity=10,
        status=ListingStatusChoices.APPROVED,
        is_active=True,
    )


@pytest.mark.django_db
class TestP0PaymentExpiryAndReconciliation:
    def test_payment_session_includes_expiry_metadata(self, buyer_auth_client, test_part_listing):
        """Authoritative payment session includes expires_at and expires_in_seconds."""
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", {
            "items": [{"listing_id": str(test_part_listing.id), "quantity": 1}],
            "place_of_supply": "MH",
            "currency": "INR",
            "payment_method": "ONLINE",
            "shipping_name": "Expiry Test Buyer",
            "shipping_phone": "+91 9876543210",
            "shipping_address_line1": "123 Marine Drive",
            "shipping_city": "Mumbai",
            "shipping_state": "MH",
            "shipping_postal_code": "400001",
            "shipping_country": "India",
        }, format="json")
        assert res.status_code == status.HTTP_201_CREATED
        session = res.data.get("payment_session", {})
        assert "expires_at" in session
        assert "expires_in_seconds" in session
        assert session["expires_in_seconds"] > 0
        assert session["is_expired"] is False

    def test_expired_session_auto_cancels_and_restores_inventory(self, buyer_auth_client, test_part_listing):
        """Order created in past beyond expiry window cannot create new payment session and restores stock."""
        initial_stock = test_part_listing.stock_quantity
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", {
            "items": [{"listing_id": str(test_part_listing.id), "quantity": 2}],
            "place_of_supply": "MH",
            "currency": "INR",
            "payment_method": "ONLINE",
            "shipping_name": "Expiry Buyer",
            "shipping_phone": "+91 9876543210",
            "shipping_address_line1": "123 Marine Drive",
            "shipping_city": "Mumbai",
            "shipping_state": "MH",
            "shipping_postal_code": "400001",
            "shipping_country": "India",
        }, format="json")
        order_number = res.data["order"]["order_number"]
        order = Order.objects.get(order_number=order_number)

        # Backdate order beyond PAYMENT_EXPIRY_MINUTES (default 30 min)
        past_time = timezone.now() - datetime.timedelta(minutes=35)
        Order.objects.filter(id=order.id).update(created_at=past_time)
        order.refresh_from_db()

        # Attempt to create payment session for expired order
        with pytest.raises(ValueError) as exc_info:
            PaymentService.create_payment_session(order)
        assert "payment window has expired" in str(exc_info.value).lower()

        # Verify order auto-cancelled and stock restored
        order.refresh_from_db()
        assert order.status == OrderStatusChoices.CANCELLED
        assert order.payment_status == PaymentStatusChoices.CANCELLED
        test_part_listing.refresh_from_db()
        assert test_part_listing.stock_quantity == initial_stock

    def test_late_client_verification_on_cancelled_order_initiates_auto_refund(self, buyer_auth_client, test_part_listing):
        """
        When a buyer captures payment at gateway after order expiry/cancellation,
        backend blocks order revival, leaves stock intact, but safely captures payment and dispatches refund.
        """
        initial_stock = test_part_listing.stock_quantity
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", {
            "items": [{"listing_id": str(test_part_listing.id), "quantity": 1}],
            "place_of_supply": "MH",
            "currency": "INR",
            "payment_method": "ONLINE",
            "shipping_name": "Late Buyer",
            "shipping_phone": "+91 9876543210",
            "shipping_address_line1": "123 Marine Drive",
            "shipping_city": "Mumbai",
            "shipping_state": "MH",
            "shipping_postal_code": "400001",
            "shipping_country": "India",
        }, format="json")
        order = Order.objects.get(order_number=res.data["order"]["order_number"])
        session = res.data["payment_session"]
        rzp_order_id = session["provider_order_id"]

        # Cancel the order (simulating auto-expiry)
        PaymentService.cancel_unpaid_order(order, reason="Simulated auto-expiry")
        order.refresh_from_db()
        assert order.status == OrderStatusChoices.CANCELLED
        test_part_listing.refresh_from_db()
        assert test_part_listing.stock_quantity == initial_stock

        # Client submits genuine payment captured in Razorpay
        pay_id = f"pay_late_{uuid.uuid4().hex[:10]}"
        valid_sig = build_razorpay_signature(rzp_order_id, pay_id, settings.RAZORPAY_KEY_SECRET)

        verify_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order.order_number}/payment/verify/",
            {
                "razorpay_order_id": rzp_order_id,
                "razorpay_payment_id": pay_id,
                "razorpay_signature": valid_sig,
            },
            format="json",
        )
        assert verify_res.status_code == status.HTTP_400_BAD_REQUEST
        assert "cancelled" in str(verify_res.data["error"]).lower()
        assert "refund" in str(verify_res.data["error"]).lower()

        # Verify order remains cancelled and stock NOT re-deducted
        order.refresh_from_db()
        assert order.status == OrderStatusChoices.CANCELLED
        test_part_listing.refresh_from_db()
        assert test_part_listing.stock_quantity == initial_stock

        # Verify automated refund record created
        auto_refund = Refund.objects.filter(order=order, refund_method=RefundMethodChoices.ORIGINAL_PAYMENT).first()
        assert auto_refund is not None
        assert auto_refund.amount == order.total_amount
        assert auto_refund.status in (RefundStatusChoices.SUCCEEDED, RefundStatusChoices.PROCESSING_UNKNOWN)

        # Verify audit entry recorded
        assert AuditLog.objects.filter(event_type="marketplace.order.late_payment_refunded", resource_id=str(order.id)).exists()

    def test_late_webhook_on_cancelled_order_initiates_auto_refund(self, buyer_auth_client, test_part_listing):
        """
        When gateway webhook reports successful capture on an already-cancelled order,
        system ignores order confirmation, leaves stock intact, and triggers auto-refund.
        """
        initial_stock = test_part_listing.stock_quantity
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", {
            "items": [{"listing_id": str(test_part_listing.id), "quantity": 1}],
            "place_of_supply": "MH",
            "currency": "INR",
            "payment_method": "ONLINE",
            "shipping_name": "Webhook Buyer",
            "shipping_phone": "+91 9876543210",
            "shipping_address_line1": "123 Marine Drive",
            "shipping_city": "Mumbai",
            "shipping_state": "MH",
            "shipping_postal_code": "400001",
            "shipping_country": "India",
        }, format="json")
        order = Order.objects.get(order_number=res.data["order"]["order_number"])
        session = res.data["payment_session"]
        rzp_order_id = session["provider_order_id"]

        # Cancel the order (simulating auto-expiry)
        PaymentService.cancel_unpaid_order(order, reason="Simulated auto-expiry")
        order.refresh_from_db()
        assert order.status == OrderStatusChoices.CANCELLED

        # Late webhook arrives with captured payment
        event_id = f"evt_p0_late_{uuid.uuid4().hex[:8]}"
        pay_id = f"pay_wb_late_{uuid.uuid4().hex[:8]}"
        wb_body = {
            "entity": "event",
            "event": "payment.captured",
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
                        "id": pay_id,
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

        # Order remains CANCELLED and stock restored
        order.refresh_from_db()
        assert order.status == OrderStatusChoices.CANCELLED
        test_part_listing.refresh_from_db()
        assert test_part_listing.stock_quantity == initial_stock

        # Auto refund created
        auto_refund = Refund.objects.filter(order=order, notes__icontains=pay_id).first()
        assert auto_refund is not None
        assert auto_refund.amount == order.total_amount
        assert auto_refund.status in (RefundStatusChoices.SUCCEEDED, RefundStatusChoices.PROCESSING_UNKNOWN)

    def test_client_verification_followed_by_webhook_does_not_duplicate_refund(self, buyer_auth_client, test_part_listing):
        """When client verification creates the auto-refund, subsequent webhook does NOT create a second refund."""
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", {
            "items": [{"listing_id": str(test_part_listing.id), "quantity": 1}],
            "place_of_supply": "MH",
            "currency": "INR",
            "payment_method": "ONLINE",
            "shipping_name": "No Dupe Buyer",
            "shipping_phone": "+91 9876543210",
            "shipping_address_line1": "123 Marine Drive",
            "shipping_city": "Mumbai",
            "shipping_state": "MH",
            "shipping_postal_code": "400001",
            "shipping_country": "India",
        }, format="json")
        order = Order.objects.get(order_number=res.data["order"]["order_number"])
        session = res.data["payment_session"]
        rzp_order_id = session["provider_order_id"]

        # Cancel order
        PaymentService.cancel_unpaid_order(order, reason="Simulated auto-expiry")

        # 1. Client verification arrives
        pay_id = f"pay_dedup_{uuid.uuid4().hex[:8]}"
        valid_sig = build_razorpay_signature(rzp_order_id, pay_id, settings.RAZORPAY_KEY_SECRET)
        v_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order.order_number}/payment/verify/",
            {
                "razorpay_order_id": rzp_order_id,
                "razorpay_payment_id": pay_id,
                "razorpay_signature": valid_sig,
            },
            format="json",
        )
        assert v_res.status_code == status.HTTP_400_BAD_REQUEST

        # 1 refund created
        assert Refund.objects.filter(order=order).count() == 1

        # 2. Webhook for the same payment arrives
        event_id = f"evt_dedup_{uuid.uuid4().hex[:8]}"
        wb_body = {
            "entity": "event",
            "event": "payment.captured",
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
                        "id": pay_id,
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

        # MUST still be exactly 1 refund record (no duplicate refund created!)
        assert Refund.objects.filter(order=order).count() == 1

    def test_repeated_webhooks_do_not_duplicate_refund(self, buyer_auth_client, test_part_listing):
        """Repeated delivery of webhooks with same payment ID does not trigger multiple refunds."""
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", {
            "items": [{"listing_id": str(test_part_listing.id), "quantity": 1}],
            "place_of_supply": "MH",
            "currency": "INR",
            "payment_method": "ONLINE",
            "shipping_name": "Webhook Replay Buyer",
            "shipping_phone": "+91 9876543210",
            "shipping_address_line1": "123 Marine Drive",
            "shipping_city": "Mumbai",
            "shipping_state": "MH",
            "shipping_postal_code": "400001",
            "shipping_country": "India",
        }, format="json")
        order = Order.objects.get(order_number=res.data["order"]["order_number"])
        session = res.data["payment_session"]
        rzp_order_id = session["provider_order_id"]

        PaymentService.cancel_unpaid_order(order, reason="Simulated auto-expiry")

        pay_id = f"pay_replay_{uuid.uuid4().hex[:8]}"
        wb_body = {
            "entity": "event",
            "event": "payment.captured",
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
                        "id": pay_id,
                        "amount": int(round(order.total_amount * 100)),
                        "currency": "INR",
                    }
                }
            }
        }
        raw_body = json.dumps(wb_body).encode("utf-8")
        wb_sig = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

        client = APIClient()
        # Delivery 1
        client.post(
            "/api/v1/marketplace/payments/webhook/RAZORPAY/",
            data=raw_body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=wb_sig,
            HTTP_X_RAZORPAY_EVENT_ID=f"evt_1_{uuid.uuid4().hex[:6]}",
        )
        assert Refund.objects.filter(order=order).count() == 1

        # Delivery 2 (different event ID but same captured payment)
        client.post(
            "/api/v1/marketplace/payments/webhook/RAZORPAY/",
            data=raw_body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=wb_sig,
            HTTP_X_RAZORPAY_EVENT_ID=f"evt_2_{uuid.uuid4().hex[:6]}",
        )
        # Still exactly 1 refund record
        assert Refund.objects.filter(order=order).count() == 1

    def test_stripe_late_client_verification_initiates_auto_refund(self, buyer_auth_client, test_uk_part_listing):
        """Stripe GBP: Late payment verification on cancelled order triggers auto-refund."""
        initial_stock = test_uk_part_listing.stock_quantity
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", {
            "items": [{"listing_id": str(test_uk_part_listing.id), "quantity": 1}],
            "currency": "GBP",
            "payment_method": "ONLINE",
            "shipping_name": "Stripe Late Buyer",
            "shipping_phone": "+44 7911 123456",
            "shipping_address_line1": "10 Downing St",
            "shipping_city": "London",
            "shipping_state": "Greater London",
            "shipping_postal_code": "SW1A 2AA",
            "shipping_country": "United Kingdom",
        }, format="json")
        order = Order.objects.get(order_number=res.data["order"]["order_number"])
        session = res.data["payment_session"]
        pi_id = session["provider_order_id"]

        PaymentService.cancel_unpaid_order(order, reason="Simulated auto-expiry")

        v_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order.order_number}/payment/verify/",
            {
                "payment_intent_id": pi_id,
            },
            format="json",
        )
        assert v_res.status_code == status.HTTP_400_BAD_REQUEST
        assert "cancelled" in str(v_res.data["error"]).lower()
        assert "refund" in str(v_res.data["error"]).lower()

        # Order remains cancelled and stock intact
        order.refresh_from_db()
        assert order.status == OrderStatusChoices.CANCELLED
        test_uk_part_listing.refresh_from_db()
        assert test_uk_part_listing.stock_quantity == initial_stock

        # Auto refund created
        auto_refund = Refund.objects.filter(order=order, gateway_provider="STRIPE").first()
        assert auto_refund is not None
        assert auto_refund.amount == order.total_amount
        assert auto_refund.currency == "GBP"

    def test_razorpay_gateway_refund_succeeds_but_db_fails_reconciliation_recovers_without_duplicate(self, buyer_auth_client, test_part_listing, monkeypatch):
        """
        Simulates Razorpay INR:
        1. Late payment received on cancelled order.
        2. Gateway successfully refunds money (mocked).
        3. Database fails while saving the refund record.
        4. Subsequent reconciliation / retry.
        5. Confirmation that the exact same idempotency key is reused and customer is NOT refunded twice.
        """
        from django.db import DatabaseError
        from apps.marketplace.payments.razorpay_provider import RazorpayPaymentProvider

        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", {
            "items": [{"listing_id": str(test_part_listing.id), "quantity": 1}],
            "place_of_supply": "MH",
            "currency": "INR",
            "payment_method": "ONLINE",
            "shipping_name": "Failure Sim Buyer",
            "shipping_phone": "+91 9876543210",
            "shipping_address_line1": "123 Marine Drive",
            "shipping_city": "Mumbai",
            "shipping_state": "MH",
            "shipping_postal_code": "400001",
            "shipping_country": "India",
        }, format="json")
        order = Order.objects.get(order_number=res.data["order"]["order_number"])
        session = res.data["payment_session"]
        rzp_order_id = session["provider_order_id"]

        PaymentService.cancel_unpaid_order(order, reason="Simulated auto-expiry")

        pay_id = f"pay_db_fail_{uuid.uuid4().hex[:8]}"
        valid_sig = build_razorpay_signature(rzp_order_id, pay_id, settings.RAZORPAY_KEY_SECRET)

        # Track external gateway calls
        gateway_calls = []

        def mock_issue_refund(self, payment_reference, amount, currency, reason='', refund_number='', notes=None):
            gateway_calls.append({
                "payment_reference": payment_reference,
                "amount": amount,
                "currency": currency,
                "refund_number": refund_number,
            })
            # Simulated gateway: honors idempotency key refund_number
            # If refund_number is the same, return the same gateway refund ID!
            h = hashlib.sha256(str(refund_number).encode('utf-8')).hexdigest()[:12]
            return True, f"rfnd_mock_{h}", {"status": "processed", "idempotency_key": refund_number}

        monkeypatch.setattr(RazorpayPaymentProvider, "issue_refund", mock_issue_refund)

        # Attempt 1: Simulate database failure while saving Refund record
        real_refund_create = Refund.objects.create
        def failing_refund_create(**kwargs):
            raise DatabaseError("Simulated database failure during Refund.objects.create")

        monkeypatch.setattr(Refund.objects, "create", failing_refund_create)

        with pytest.raises(DatabaseError):
            buyer_auth_client.post(
                f"/api/v1/marketplace/orders/{order.order_number}/payment/verify/",
                {
                    "razorpay_order_id": rzp_order_id,
                    "razorpay_payment_id": pay_id,
                    "razorpay_signature": valid_sig,
                },
                format="json",
            )

        # Gateway was called once
        assert len(gateway_calls) == 1
        first_call_key = gateway_calls[0]["refund_number"]
        assert first_call_key.startswith("REF-LATE-")

        # Because DB rolled back, zero Refund records exist in DB
        assert Refund.objects.filter(order=order).count() == 0

        # Attempt 2: Database recovers, reconciliation / retry runs
        monkeypatch.setattr(Refund.objects, "create", real_refund_create)

        retry_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order.order_number}/payment/verify/",
            {
                "razorpay_order_id": rzp_order_id,
                "razorpay_payment_id": pay_id,
                "razorpay_signature": valid_sig,
            },
            format="json",
        )
        assert retry_res.status_code == status.HTTP_400_BAD_REQUEST
        assert "refund" in str(retry_res.data["error"]).lower()

        # Gateway was called a second time
        assert len(gateway_calls) == 2
        second_call_key = gateway_calls[1]["refund_number"]

        # CRITICAL ASSERTION: The EXACT SAME idempotency key was reused for the retry!
        assert first_call_key == second_call_key

        # Exactly ONE Refund record now exists in the database
        assert Refund.objects.filter(order=order).count() == 1
        db_refund = Refund.objects.filter(order=order).first()
        h = hashlib.sha256(str(first_call_key).encode('utf-8')).hexdigest()[:12]
        assert db_refund.gateway_refund_id == f"rfnd_mock_{h}"
        assert db_refund.status == RefundStatusChoices.SUCCEEDED

    def test_stripe_late_webhook_initiates_auto_refund(self, buyer_auth_client, test_uk_part_listing):
        """Stripe GBP: Late payment_intent.succeeded webhook on cancelled order triggers auto-refund."""
        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", {
            "items": [{"listing_id": str(test_uk_part_listing.id), "quantity": 1}],
            "currency": "GBP",
            "payment_method": "ONLINE",
            "shipping_name": "Stripe Webhook Buyer",
            "shipping_phone": "+44 7911 123456",
            "shipping_address_line1": "10 Downing St",
            "shipping_city": "London",
            "shipping_state": "Greater London",
            "shipping_postal_code": "SW1A 2AA",
            "shipping_country": "United Kingdom",
        }, format="json")
        order = Order.objects.get(order_number=res.data["order"]["order_number"])
        session = res.data["payment_session"]
        pi_id = session["provider_order_id"]

        PaymentService.cancel_unpaid_order(order, reason="Simulated auto-expiry")

        event_id = f"evt_stripe_late_{uuid.uuid4().hex[:8]}"
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
        timestamp = int(timezone.now().timestamp())
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

        auto_refund = Refund.objects.filter(order=order, gateway_provider="STRIPE").first()
        assert auto_refund is not None
        assert auto_refund.amount == order.total_amount
        assert auto_refund.currency == "GBP"

    def test_stripe_gateway_refund_succeeds_but_db_fails_reconciliation_recovers_without_duplicate(self, buyer_auth_client, test_uk_part_listing, monkeypatch):
        """
        Simulates Stripe GBP:
        1. Late payment received on cancelled order.
        2. Stripe gateway successfully refunds money (mocked).
        3. Database fails while saving the refund record.
        4. Subsequent reconciliation / retry.
        5. Confirmation that the exact same idempotency key is reused and customer is NOT refunded twice.
        """
        from django.db import DatabaseError
        from apps.marketplace.payments.stripe_provider import StripePaymentProvider

        res = buyer_auth_client.post("/api/v1/marketplace/orders/checkout/", {
            "items": [{"listing_id": str(test_uk_part_listing.id), "quantity": 1}],
            "currency": "GBP",
            "payment_method": "ONLINE",
            "shipping_name": "Failure Sim UK Buyer",
            "shipping_phone": "+44 7911 123456",
            "shipping_address_line1": "10 Downing St",
            "shipping_city": "London",
            "shipping_state": "Greater London",
            "shipping_postal_code": "SW1A 2AA",
            "shipping_country": "United Kingdom",
        }, format="json")
        order = Order.objects.get(order_number=res.data["order"]["order_number"])
        session = res.data["payment_session"]
        pi_id = session["provider_order_id"]

        PaymentService.cancel_unpaid_order(order, reason="Simulated auto-expiry")

        # Track external gateway calls
        gateway_calls = []

        def mock_issue_refund(self, payment_reference, amount, currency, reason='', refund_number='', notes=None):
            gateway_calls.append({
                "payment_reference": payment_reference,
                "amount": amount,
                "currency": currency,
                "refund_number": refund_number,
            })
            # Simulated gateway: honors idempotency key refund_number
            # If refund_number is the same, return the same gateway refund ID!
            h = hashlib.sha256(str(refund_number).encode('utf-8')).hexdigest()[:12]
            return True, f"re_mock_{h}", {"status": "succeeded", "idempotency_key": refund_number}

        monkeypatch.setattr(StripePaymentProvider, "issue_refund", mock_issue_refund)

        # Attempt 1: Simulate database failure while saving Refund record
        real_refund_create = Refund.objects.create
        def failing_refund_create(**kwargs):
            raise DatabaseError("Simulated database failure during Refund.objects.create")

        monkeypatch.setattr(Refund.objects, "create", failing_refund_create)

        with pytest.raises(DatabaseError):
            buyer_auth_client.post(
                f"/api/v1/marketplace/orders/{order.order_number}/payment/verify/",
                {
                    "payment_intent_id": pi_id,
                },
                format="json",
            )

        # Gateway was called once
        assert len(gateway_calls) == 1
        first_call_key = gateway_calls[0]["refund_number"]
        assert first_call_key.startswith("REF-LATE-")

        # Because DB rolled back, zero Refund records exist in DB
        assert Refund.objects.filter(order=order).count() == 0

        # Attempt 2: Database recovers, reconciliation / retry runs
        monkeypatch.setattr(Refund.objects, "create", real_refund_create)

        retry_res = buyer_auth_client.post(
            f"/api/v1/marketplace/orders/{order.order_number}/payment/verify/",
            {
                "payment_intent_id": pi_id,
            },
            format="json",
        )
        assert retry_res.status_code == status.HTTP_400_BAD_REQUEST
        assert "refund" in str(retry_res.data["error"]).lower()

        # Gateway was called a second time
        assert len(gateway_calls) == 2
        second_call_key = gateway_calls[1]["refund_number"]

        # CRITICAL ASSERTION: The EXACT SAME idempotency key was reused for the retry!
        assert first_call_key == second_call_key

        # Exactly ONE Refund record now exists in the database
        assert Refund.objects.filter(order=order).count() == 1
        db_refund = Refund.objects.filter(order=order).first()
        h = hashlib.sha256(str(first_call_key).encode('utf-8')).hexdigest()[:12]
        assert db_refund.gateway_refund_id == f"re_mock_{h}"
        assert db_refund.status == RefundStatusChoices.SUCCEEDED


@pytest.mark.django_db
class TestRazorpayRefundIdempotencyKeySafety:
    """
    Targeted audit tests for Razorpay refund idempotency key generation:
    1. Missing refund number safe failure (no UUID fallback, no dispatch).
    2. Unicode refund numbers hashed to valid ASCII keys.
    3. Unsupported special characters hashed to valid ASCII keys.
    4. Common prefix > 40 chars collision resistance test.
    5. Strings < 10 chars collision resistance & length constraint test.
    6. Two distinct refunds on the same payment produce unique keys and receipts.
    7. Retry after timeout uses exact same amount, speed, receipt, notes, and key.
    8. An uncertain refund is blocked from redispatch and resolved via inquiry.
    """

    def test_missing_refund_number_fails_safely_before_dispatch(self):
        """
        Missing or empty refund_number must fail safely before any network request is sent.
        No random UUIDs should be generated, and no dispatch should be attempted.
        """
        provider = RazorpayPaymentProvider()

        # 1. Direct generator call raises ValueError for empty/None/whitespace inputs
        with pytest.raises(ValueError) as exc:
            provider.generate_refund_idempotency_key(None)
        assert "refund_number is required" in str(exc.value)

        with pytest.raises(ValueError) as exc:
            provider.generate_refund_idempotency_key("")
        assert "refund_number is required" in str(exc.value)

        with pytest.raises(ValueError) as exc:
            provider.generate_refund_idempotency_key("   ")
        assert "refund_number is required" in str(exc.value)

        # 2. issue_refund returns False safely before dispatching
        ok_none, err_none, _ = provider.issue_refund(
            payment_reference="pay_valid_123",
            amount=Decimal("500.00"),
            currency="INR",
            refund_number=None,
        )
        assert ok_none is False
        assert "Missing required refund_number" in err_none

        ok_empty, err_empty, _ = provider.issue_refund(
            payment_reference="pay_valid_123",
            amount=Decimal("500.00"),
            currency="INR",
            refund_number="",
        )
        assert ok_empty is False
        assert "Missing required refund_number" in err_empty

    def test_unicode_refund_numbers_hashed_to_valid_ascii_key(self):
        """
        Refund numbers containing non-ASCII Unicode characters must be hashed into
        a strict ASCII key meeting Razorpay's [10, 40] length constraint.
        """
        unicode_inputs = [
            "REF-ÜNICODE-001",
            "REF-₹-INR-123",
            "REF-日本語-456",
            "REF-مرحبا-789",
            "REF-ACCÉNT-999",
        ]

        generated_keys = {}
        for u in unicode_inputs:
            k = RazorpayPaymentProvider.generate_refund_idempotency_key(u)

            # Strictly ASCII
            assert k.isascii()
            # Allowed characters: A-Z, a-z, 0-9, hyphen, underscore
            assert all(c.isalnum() or c in ('-', '_') for c in k)
            # Length constraints: 10 <= len <= 40
            assert 10 <= len(k) <= 40
            assert len(k) == 34  # "h_" + 32-char hex digest
            assert k.startswith("h_")

            # Determinism: same input produces same key
            assert RazorpayPaymentProvider.generate_refund_idempotency_key(u) == k

            # Uniqueness: distinct unicode inputs produce distinct keys
            assert k not in generated_keys.values()
            generated_keys[u] = k

    def test_unsupported_special_characters_hashed_to_valid_ascii_key(self):
        """
        Refund numbers containing spaces, punctuation, or unsupported characters
        must be safely hashed to a valid ASCII key meeting Razorpay constraints.
        """
        special_inputs = [
            "REF 2026/11/19 001",
            "REF:ITEM@123#456",
            "REF.PART!REFUND$999",
            "REF*ORDER(TEST)",
            "REF+TEST=123",
        ]

        generated_keys = {}
        for s in special_inputs:
            k = RazorpayPaymentProvider.generate_refund_idempotency_key(s)

            # Strictly ASCII
            assert k.isascii()
            # Allowed characters only
            assert all(c.isalnum() or c in ('-', '_') for c in k)
            # Length constraints: 10 <= len <= 40
            assert 10 <= len(k) <= 40
            assert len(k) == 34
            assert k.startswith("h_")

            # Determinism
            assert RazorpayPaymentProvider.generate_refund_idempotency_key(s) == k

            # Uniqueness
            assert k not in generated_keys.values()
            generated_keys[s] = k

    def test_two_refund_numbers_with_common_prefix_longer_than_40_chars_do_not_collide(self):
        """
        Two distinct refund numbers sharing a common prefix > 40 chars must NEVER
        produce the same X-Refund-Idempotency key or receipt.
        Naive truncation [:40] would collide; our hashing strategy guarantees uniqueness.
        """
        prefix = "REF-20261118-LONG-ORDER-IDENTIFIER-BATCH-"
        assert len(prefix) > 40  # 41 chars

        rfnd_1 = f"{prefix}ALPHA-001"
        rfnd_2 = f"{prefix}OMEGA-002"
        assert rfnd_1 != rfnd_2
        assert rfnd_1[:40] == rfnd_2[:40]  # Demonstrating naive truncation collision

        key_1 = RazorpayPaymentProvider.generate_refund_idempotency_key(rfnd_1)
        key_2 = RazorpayPaymentProvider.generate_refund_idempotency_key(rfnd_2)

        # CRITICAL: Keys must NOT collide
        assert key_1 != key_2

        # Both keys must strictly satisfy Razorpay constraints
        for k in (key_1, key_2):
            assert 10 <= len(k) <= 40
            assert all(c.isalnum() or c in ('-', '_') for c in k)

        # Determinism check: repeated generation yields identical key
        assert RazorpayPaymentProvider.generate_refund_idempotency_key(rfnd_1) == key_1
        assert RazorpayPaymentProvider.generate_refund_idempotency_key(rfnd_2) == key_2

    def test_refund_numbers_shorter_than_10_chars_do_not_collide_and_meet_length_requirement(self):
        """
        Refund numbers < 10 chars must be formatted to length >= 10 without collisions.
        Naive padding (e.g. .ljust(10, '0')) would cause collisions (RF1 -> RF10000000 vs RF10 -> RF10000000).
        Our hashing strategy guarantees distinct, safe keys for all inputs.
        """
        short_inputs = ["RF1", "RF10", "RF100", "R", "REFUND"]

        generated_keys = {}
        for s in short_inputs:
            k = RazorpayPaymentProvider.generate_refund_idempotency_key(s)
            assert 10 <= len(k) <= 40, f"Key '{k}' for '{s}' does not meet length constraints (len={len(k)})."
            assert all(c.isalnum() or c in ('-', '_') for c in k)
            assert k not in generated_keys.values(), f"Collision detected: input '{s}' produced existing key '{k}'."
            generated_keys[s] = k

    def test_two_distinct_refunds_on_same_payment_produce_unique_keys_and_receipts(self, monkeypatch):
        """
        Two distinct refund operations on the same Razorpay payment must produce
        distinct X-Refund-Idempotency keys and distinct receipt values (both <= 40 chars).
        """
        provider = RazorpayPaymentProvider()
        provider.force_network_call = True
        provider.test_mode = False
        provider.key_id = "rzp_test_key"
        provider.key_secret = "rzp_test_secret"

        dispatched_requests = []

        def mock_urlopen(req, timeout=10):
            body_dict = json.loads(req.data.decode('utf-8'))
            headers_dict = dict(req.headers)
            dispatched_requests.append({
                "url": req.full_url,
                "headers": headers_dict,
                "body": body_dict,
            })
            h = hashlib.sha256(body_dict["receipt"].encode('utf-8')).hexdigest()[:12]
            mock_resp_body = json.dumps({
                "id": f"rfnd_{h}",
                "entity": "refund",
                "amount": body_dict["amount"],
                "status": "processed",
                "receipt": body_dict["receipt"],
            }).encode('utf-8')
            return MockHTTPResponse(mock_resp_body)

        import urllib.request
        monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

        # Dispatch Refund 1 (Partial 500 INR)
        ok1, ref1, _ = provider.issue_refund(
            payment_reference="pay_order_shared_999",
            amount=Decimal("500.00"),
            currency="INR",
            refund_number="REF-ORD-999-PARTIAL-1",
            notes={"order_number": "ORD-999"},
        )
        assert ok1 is True

        # Dispatch Refund 2 (Partial 750 INR)
        ok2, ref2, _ = provider.issue_refund(
            payment_reference="pay_order_shared_999",
            amount=Decimal("750.00"),
            currency="INR",
            refund_number="REF-ORD-999-PARTIAL-2",
            notes={"order_number": "ORD-999"},
        )
        assert ok2 is True

        assert len(dispatched_requests) == 2
        req1 = dispatched_requests[0]
        req2 = dispatched_requests[1]

        # Receipts must be unique, non-empty, and <= 40 characters
        receipt1 = req1["body"]["receipt"]
        receipt2 = req2["body"]["receipt"]
        assert receipt1 != receipt2
        assert len(receipt1) <= 40
        assert len(receipt2) <= 40

        # Idempotency headers must be unique and present
        idemp1 = req1["headers"].get("X-refund-idempotency") or req1["headers"].get("X-Refund-Idempotency")
        idemp2 = req2["headers"].get("X-refund-idempotency") or req2["headers"].get("X-Refund-Idempotency")
        assert idemp1 is not None and idemp2 is not None
        assert idemp1 != idemp2
        assert 10 <= len(idemp1) <= 40
        assert 10 <= len(idemp2) <= 40

        # Undocumented header must NOT be sent
        assert "X-Razorpay-Idempotency-Key" not in req1["headers"]
        assert "X-razorpay-idempotency-key" not in req1["headers"]

    def test_retry_after_timeout_sends_exact_same_amount_speed_receipt_notes_and_key(self, monkeypatch):
        """
        Retrying a refund after a timeout sends the EXACT same request payload
        (amount, speed, receipt, notes) and exact same X-Refund-Idempotency header.
        """
        provider = RazorpayPaymentProvider()
        provider.force_network_call = True
        provider.test_mode = False
        provider.key_id = "rzp_test_key"
        provider.key_secret = "rzp_test_secret"

        dispatched_requests = []
        call_count = [0]

        def mock_urlopen(req, timeout=10):
            call_count[0] += 1
            body_dict = json.loads(req.data.decode('utf-8'))
            headers_dict = dict(req.headers)
            dispatched_requests.append({
                "headers": headers_dict,
                "body": body_dict,
            })
            if call_count[0] == 1:
                # Simulate network drop / timeout on first attempt
                import urllib.error
                raise urllib.error.URLError("Connection timed out")

            # Second attempt succeeds
            return MockHTTPResponse(json.dumps({
                "id": "rfnd_retry_success_123",
                "entity": "refund",
                "amount": body_dict["amount"],
                "status": "processed",
                "receipt": body_dict["receipt"],
            }).encode('utf-8'))

        import urllib.request
        monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

        rfnd_num = "REF-RETRY-DETERMINISTIC-001"
        rfnd_amt = Decimal("1500.00")
        notes = {"order_number": "ORD-TIMEOUT-001", "actor": "finance_admin"}

        # Attempt 1: Encounters timeout
        ok1, err1, _ = provider.issue_refund(
            payment_reference="pay_timeout_payment_001",
            amount=rfnd_amt,
            currency="INR",
            reason="Damaged item returned",
            refund_number=rfnd_num,
            notes=notes,
        )
        assert ok1 is False
        assert "timed out" in err1.lower() or "connection" in err1.lower()

        # Attempt 2: Retry with identical parameters
        ok2, ref2, extra2 = provider.issue_refund(
            payment_reference="pay_timeout_payment_001",
            amount=rfnd_amt,
            currency="INR",
            reason="Damaged item returned",
            refund_number=rfnd_num,
            notes=notes,
        )
        assert ok2 is True
        assert ref2 == "rfnd_retry_success_123"

        assert len(dispatched_requests) == 2
        req1 = dispatched_requests[0]
        req2 = dispatched_requests[1]

        # 1. Exact same idempotency header
        header_key = "X-refund-idempotency" if "X-refund-idempotency" in req1["headers"] else "X-Refund-Idempotency"
        assert req1["headers"][header_key] == req2["headers"][header_key]

        # 2. Exact same amount, speed, receipt, notes
        assert req1["body"]["amount"] == req2["body"]["amount"] == 150000
        assert req1["body"]["speed"] == req2["body"]["speed"] == "normal"
        assert req1["body"]["receipt"] == req2["body"]["receipt"]
        assert req1["body"]["notes"] == req2["body"]["notes"]

        # 3. Request payloads are identical
        assert req1["body"] == req2["body"]

    def test_uncertain_refund_blocked_from_redispatch_and_resolved_via_inquiry(self, admin_user, buyer_user):
        """
        When a refund is in PROCESSING_UNKNOWN (uncertain outcome):
        1. dispatch_gateway_refund is strictly blocked from re-dispatching to prevent duplicate payouts.
        2. Reconciliation via inquiry queries gateway status and resolves the refund to SUCCEEDED safely.
        """
        order = Order.objects.create(
            buyer=buyer_user,
            order_number=f"ORD-UNC-{uuid.uuid4().hex[:6].upper()}",
            total_amount=Decimal('450.00'),
            subtotal_taxable_amount=Decimal('375.00'),
            total_tax_amount=Decimal('75.00'),
            currency='INR',
            shipping_country='IN',
            payment_status=PaymentStatusChoices.PAID,
            payment_reference='pay_inr_uncertain_123',
        )

        refund = Refund.objects.create(
            order=order,
            refund_number=f"REF-UNCERTAIN-{uuid.uuid4().hex[:8].upper()}",
            amount=Decimal("150.00"),
            currency="INR",
            status=RefundStatusChoices.PROCESSING_UNKNOWN,
            gateway_provider="RAZORPAY",
            idempotency_key="idemp_uncertain_test",
            created_by=admin_user,
        )

        # Step 1: Verify redispatch is blocked
        with pytest.raises(DjangoValidationError) as exc:
            RefundService.dispatch_gateway_refund(refund, actor=admin_user)
        assert "processing_unknown" in str(exc.value).lower() or "reconciliation" in str(exc.value).lower()

        # Step 2: Inquire resolves status to SUCCEEDED without issuing a new gateway dispatch
        mock_gateway_refund_id = f"rfnd_resolved_{uuid.uuid4().hex[:8]}"

        def mock_inquire(self, payment_reference, refund_number, gateway_refund_id=None):
            return "SUCCEEDED", mock_gateway_refund_id, {"status": "processed", "id": mock_gateway_refund_id}

        with patch.object(RazorpayPaymentProvider, "inquire_refund", mock_inquire):
            reconciled_refund, outcome = RefundService.reconcile_refund(refund, actor=admin_user)

        assert outcome == "SUCCEEDED"
        assert reconciled_refund.status == RefundStatusChoices.SUCCEEDED
        assert reconciled_refund.gateway_refund_id == mock_gateway_refund_id
