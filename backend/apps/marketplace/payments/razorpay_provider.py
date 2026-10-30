import base64
import hashlib
import hmac
import json
import logging
import urllib.error
import urllib.request
import uuid
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple
from django.conf import settings
from apps.marketplace.payments.base import BasePaymentProvider

logger = logging.getLogger(__name__)


class RazorpayPaymentProvider(BasePaymentProvider):
    """
    Razorpay integration tailored for India (INR) domestic payments:
    Supports UPI (Google Pay, PhonePe, Paytm, BHIM, QR, VPA),
    RuPay/Visa/MasterCard domestic and international cards, NetBanking, and Wallets.
    All monetary amounts are strictly represented in integer paise.
    """
    provider_name = 'RAZORPAY'

    def __init__(self):
        self.key_id = getattr(settings, 'RAZORPAY_KEY_ID', 'rzp_test_placeholder_key')
        self.key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', 'rzp_test_placeholder_secret')
        self.webhook_secret = getattr(settings, 'RAZORPAY_WEBHOOK_SECRET', 'rzp_test_webhook_secret')
        self.api_url = getattr(settings, 'RAZORPAY_API_URL', 'https://api.razorpay.com/v1').rstrip('/')
        self.test_mode = self._is_test_mode_allowed()

    @property
    def is_configured(self) -> bool:
        """Indicates whether genuine (non-placeholder) Razorpay API credentials are configured."""
        if not self.key_id or not self.key_secret:
            return False
        clean_key = self.key_id.strip().lower()
        clean_secret = self.key_secret.strip().lower()
        placeholder_keys = {
            'rzp_test_placeholder_key',
            'rzp_test_placeholder',
            'rzp_test_mock_key',
            'placeholder',
        }
        placeholder_secrets = {
            'rzp_test_placeholder_secret',
            'rzp_test_placeholder',
            'rzp_test_mock_secret',
            'test_secret',
            'placeholder',
        }
        if clean_key in placeholder_keys or clean_secret in placeholder_secrets:
            return False
        return len(clean_key) >= 10 and len(clean_secret) >= 10

    @staticmethod
    def _is_test_mode_allowed() -> bool:
        """
        Enforces strict environment restriction:
        Test mode is only permitted if explicitly opted in AND
        running in development (DEBUG=True) or automated testing (IS_TESTING=True).
        In production, test_mode is strictly False regardless of environment variable misconfigurations.
        """
        opted_in = getattr(settings, 'PAYMENT_TEST_MODE', False)
        is_safe_env = getattr(settings, 'DEBUG', False) or getattr(settings, 'IS_TESTING', False)
        return bool(opted_in and is_safe_env)

    def _to_paise(self, amount: Decimal) -> int:
        """Converts decimal amount to integer paise (1 INR = 100 paise)."""
        return int(round(Decimal(str(amount)) * 100))

    def create_payment_session(
        self,
        order: Any,
        return_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Creates an authoritative Razorpay order session.
        If live or test Razorpay credentials are configured, makes an authentic HTTP API call
        to https://api.razorpay.com/v1/orders to register the order with Razorpay.
        In isolated test mode with placeholder keys, generates a deterministic test order ID.
        In production without configured credentials, raises a descriptive RuntimeError.
        """
        if order.currency != 'INR':
            raise ValueError(f"Razorpay provider only supports INR transactions; received '{order.currency}'.")

        amount_paise = self._to_paise(order.total_amount)
        receipt_id = f"rcpt_{order.order_number}"
        buyer = order.buyer
        customer_name = (
            getattr(order, 'shipping_name', '').strip()
            or (buyer.get_full_name() if hasattr(buyer, 'get_full_name') else '')
            or getattr(buyer, 'username', '')
            or 'Valued Customer'
        )
        customer_email = getattr(buyer, 'email', '')
        customer_contact = getattr(order, 'shipping_phone', '').strip() or getattr(buyer, 'phone_number', '') or ''

        notes_dict = {
            "order_number": order.order_number,
            "order_id": str(order.id),
            "buyer_email": customer_email,
            "currency": "INR",
        }

        # Attempt live/sandbox Razorpay Orders API call if credentials are configured
        if self.is_configured:
            create_order_url = f"{self.api_url}/orders"
            payload_data = {
                "amount": amount_paise,
                "currency": "INR",
                "receipt": receipt_id,
                "notes": notes_dict,
                "payment_capture": 1,
            }
            body_bytes = json.dumps(payload_data).encode('utf-8')
            auth_str = f"{self.key_id}:{self.key_secret}"
            auth_header = base64.b64encode(auth_str.encode('utf-8')).decode('ascii')

            req = urllib.request.Request(
                create_order_url,
                data=body_bytes,
                headers={
                    "Authorization": f"Basic {auth_header}",
                    "Content-Type": "application/json",
                    "User-Agent": "DriverXtra-Platform/1.0",
                },
                method="POST",
            )

            try:
                with urllib.request.urlopen(req, timeout=10) as response:
                    raw_json = json.loads(response.read().decode('utf-8'))
                    provider_order_id = raw_json.get('id')
                    logger.info("Successfully created Razorpay order %s for DriverXtra order %s", provider_order_id, order.order_number)
                    return {
                        "provider": self.provider_name,
                        "provider_order_id": provider_order_id,
                        "amount": str(order.total_amount),
                        "amount_minor": amount_paise,
                        "currency": "INR",
                        "key_id": self.key_id,
                        "receipt": receipt_id,
                        "customer_name": customer_name,
                        "customer_email": customer_email,
                        "customer_contact": customer_contact,
                        "notes": notes_dict,
                        "is_test_mode": self.test_mode,
                        "raw_order": raw_json,
                    }
            except urllib.error.HTTPError as http_err:
                err_text = http_err.read().decode('utf-8', errors='replace')
                logger.error("Razorpay Orders API error HTTP %s: %s", http_err.code, err_text)
                if not self.test_mode:
                    raise RuntimeError(f"Razorpay Orders API rejected order creation (HTTP {http_err.code}): {err_text}")
                logger.warning("Falling back to deterministic test session in test mode due to Razorpay HTTP error.")
            except Exception as exc:
                logger.error("Failed to connect to Razorpay API: %s", str(exc))
                if not self.test_mode:
                    raise RuntimeError(f"Failed to communicate with Razorpay API: {str(exc)}")
                logger.warning("Falling back to deterministic test session in test mode due to connection error.")

        # Test mode fallback for offline development or automated tests without live network
        if self.test_mode:
            order_id = f"order_rzp_{uuid.uuid4().hex[:14]}"
            return {
                "provider": self.provider_name,
                "provider_order_id": order_id,
                "amount": str(order.total_amount),
                "amount_minor": amount_paise,
                "currency": "INR",
                "key_id": self.key_id,
                "receipt": receipt_id,
                "customer_name": customer_name,
                "customer_email": customer_email,
                "customer_contact": customer_contact,
                "notes": notes_dict,
                "is_test_mode": True,
            }

        # Production error when credentials are not configured
        raise RuntimeError(
            "Live Razorpay online payments require configured credentials. "
            "Please configure RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in the server environment."
        )

    def verify_payment(
        self,
        order: Any,
        payload: Dict[str, Any],
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Cryptographically validates the Razorpay payment confirmation.
        Expected payload keys: razorpay_order_id, razorpay_payment_id, razorpay_signature.
        """
        razorpay_order_id = payload.get('razorpay_order_id', '').strip()
        razorpay_payment_id = payload.get('razorpay_payment_id', '').strip()
        razorpay_signature = payload.get('razorpay_signature', '').strip()

        if not razorpay_payment_id:
            return False, "Missing razorpay_payment_id in confirmation payload.", {}
        if not razorpay_order_id:
            return False, "Missing razorpay_order_id in confirmation payload.", {}
        if not razorpay_signature:
            return False, "Missing razorpay_signature in confirmation payload.", {}

        # Authoritative session check: Reject fabricated or cross-order Razorpay order IDs
        if order.payment_reference and razorpay_order_id != order.payment_reference:
            return False, f"Razorpay order ID '{razorpay_order_id}' does not match the active session for order {order.order_number}.", {}

        # Signature verification: HMAC-SHA256(key_secret, order_id + "|" + payment_id)
        msg = f"{razorpay_order_id}|{razorpay_payment_id}".encode('utf-8')
        generated_signature = hmac.new(
            self.key_secret.encode('utf-8'),
            msg,
            hashlib.sha256,
        ).hexdigest()

        # In legitimate test mode ONLY, accept designated mock signatures.
        # In production (when test_mode is False), mock signatures are strictly rejected.
        is_valid = hmac.compare_digest(generated_signature, razorpay_signature)
        if not is_valid and self.test_mode and razorpay_signature in ('test_sig_valid', 'mock_valid_signature'):
            is_valid = True

        if not is_valid:
            return False, "Invalid Razorpay payment signature.", {
                "generated_signature": generated_signature,
                "provided_signature": razorpay_signature,
            }

        return True, razorpay_payment_id, {
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "verified": True,
        }

    def verify_webhook(
        self,
        request_body: bytes,
        headers: Dict[str, str],
    ) -> Tuple[bool, Optional[str], Optional[str], Dict[str, Any]]:
        """
        Validates Razorpay webhook signature from X-Razorpay-Signature header.
        """
        # Case-insensitive header lookup
        normalized_headers = {k.lower(): v for k, v in headers.items()}
        signature = normalized_headers.get('x-razorpay-signature', '').strip()

        if not signature:
            return False, None, None, {"error": "Missing X-Razorpay-Signature header."}

        generated = hmac.new(
            self.webhook_secret.encode('utf-8'),
            request_body,
            hashlib.sha256,
        ).hexdigest()

        is_valid = hmac.compare_digest(generated, signature)
        if not is_valid and self.test_mode and signature in ('test_webhook_sig_valid', 'mock_valid_sig'):
            is_valid = True

        if not is_valid:
            return False, None, None, {"error": "Invalid Razorpay webhook signature."}

        try:
            payload = json.loads(request_body.decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            return False, None, None, {"error": "Malformed JSON in webhook request body."}

        event_type = payload.get('event', '')
        # Razorpay event id or deterministic payload hash
        event_id = payload.get('event_id') or f"rzp_evt_{hashlib.sha256(request_body).hexdigest()[:20]}"

        return True, event_id, event_type, payload
