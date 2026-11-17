import hmac
import hashlib
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
import uuid
from decimal import Decimal
from typing import Dict, Any, Tuple, Optional
from django.conf import settings
from apps.marketplace.payments.base import BasePaymentProvider

logger = logging.getLogger(__name__)


class StripePaymentProvider(BasePaymentProvider):
    """
    Stripe integration tailored for United Kingdom (GBP) & International card payments:
    Supports UK Debit/Credit cards, Apple Pay, Google Pay, and BACS Direct Debit.
    All monetary amounts are strictly represented in integer pence (minor units).
    """
    provider_name = 'STRIPE'

    def __init__(self):
        self.publishable_key = getattr(settings, 'STRIPE_PUBLISHABLE_KEY', 'pk_test_placeholder_key')
        self.secret_key = getattr(settings, 'STRIPE_SECRET_KEY', 'sk_test_placeholder_secret')
        self.webhook_secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', 'whsec_test_placeholder_secret')
        self.test_mode = self._is_test_mode_allowed()

    @property
    def is_configured(self) -> bool:
        """Indicates whether genuine (non-placeholder) Stripe credentials are configured."""
        if not self.secret_key or not self.publishable_key:
            return False
        clean_secret = self.secret_key.strip().lower()
        if 'placeholder' in clean_secret or 'sk_test_mock' in clean_secret:
            return False
        return len(clean_secret) >= 10 and clean_secret.startswith(('sk_live_', 'sk_test_'))

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

    def _to_pence(self, amount: Decimal) -> int:
        """Converts decimal amount to integer pence (1 GBP = 100 pence)."""
        return int(round(Decimal(str(amount)) * 100))

    def create_payment_session(
        self,
        order: Any,
        return_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Creates a Stripe PaymentIntent / Checkout session.
        If genuine Stripe credentials are configured, registers the PaymentIntent via Stripe API.
        In test mode or mock settings, creates a deterministic test PaymentIntent.
        """
        if order.currency != 'GBP':
            raise ValueError(f"Stripe UK provider only supports GBP transactions; received '{order.currency}'.")

        amount_pence = self._to_pence(order.total_amount)
        buyer_email = getattr(order.buyer, 'email', '') if hasattr(order, 'buyer') and order.buyer else ''

        # Attempt live Stripe API call if configured
        if self.is_configured:
            url = "https://api.stripe.com/v1/payment_intents"
            params = {
                "amount": str(amount_pence),
                "currency": "gbp",
                "payment_method_types[]": "card",
                "description": f"DriverXtra Order {order.order_number}",
                "receipt_email": buyer_email,
                "metadata[order_number]": str(order.order_number),
                "metadata[order_id]": str(order.id),
                "metadata[buyer_email]": buyer_email,
            }
            if return_url:
                params["return_url"] = return_url

            encoded_data = urllib.parse.urlencode(params).encode('utf-8')
            req = urllib.request.Request(
                url,
                data=encoded_data,
                headers={
                    "Authorization": f"Bearer {self.secret_key}",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "DriverXtra-Platform/1.0",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    stripe_data = json.loads(resp.read().decode('utf-8'))
                    pi_id = stripe_data.get('id')
                    client_sec = stripe_data.get('client_secret')
                    return {
                        "provider": self.provider_name,
                        "provider_order_id": pi_id,
                        "client_secret": client_sec,
                        "amount": str(order.total_amount),
                        "amount_minor": amount_pence,
                        "currency": "GBP",
                        "publishable_key": self.publishable_key,
                        "metadata": {
                            "order_number": order.order_number,
                            "order_id": str(order.id),
                            "buyer_email": buyer_email,
                        },
                        "is_test_mode": self.test_mode,
                        "raw_response": stripe_data,
                    }
            except urllib.error.HTTPError as http_err:
                err_text = http_err.read().decode('utf-8', errors='replace')
                logger.error("Stripe PaymentIntent creation error HTTP %s: %s", http_err.code, err_text)
                if not getattr(settings, 'IS_TESTING', False):
                    raise RuntimeError(f"Stripe API rejected payment session creation (HTTP {http_err.code}): {err_text}")
                logger.warning("Falling back to deterministic test session in IS_TESTING environment due to Stripe HTTP error.")
            except Exception as exc:
                logger.error("Failed to connect to Stripe API: %s", str(exc))
                if not getattr(settings, 'IS_TESTING', False):
                    raise RuntimeError(f"Failed to communicate with Stripe API: {str(exc)}")
                logger.warning("Falling back to deterministic test session in IS_TESTING environment due to connection error.")

        if self.test_mode:
            payment_intent_id = f"pi_test_{uuid.uuid4().hex[:18]}"
            client_secret = f"{payment_intent_id}_secret_{uuid.uuid4().hex[:12]}"

            return {
                "provider": self.provider_name,
                "provider_order_id": payment_intent_id,
                "client_secret": client_secret,
                "amount": str(order.total_amount),
                "amount_minor": amount_pence,
                "currency": "GBP",
                "publishable_key": self.publishable_key,
                "metadata": {
                    "order_number": order.order_number,
                    "order_id": str(order.id),
                    "buyer_email": buyer_email,
                },
                "is_test_mode": True,
            }

        # In production, check if real Stripe API credentials are configured
        raise RuntimeError(
            "Live Stripe online payments are currently disabled. Real Stripe checkout requires "
            "production Stripe API credentials (STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY)."
        )

    def verify_payment(
        self,
        order: Any,
        payload: Dict[str, Any],
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Validates Stripe payment intent confirmation payload.
        Expected payload keys: payment_intent_id (or stripe_payment_intent_id, or client_secret).
        Rejects fabricated PaymentIntent IDs not associated with the order's session.
        """
        # Strict currency enforcement
        if getattr(order, 'currency', '') != 'GBP':
            return False, f"Stripe UK provider only supports GBP transactions; received '{getattr(order, 'currency', '')}'.", {}

        payload_currency = str(payload.get('currency', '')).strip().upper()
        if payload_currency and payload_currency != 'GBP':
            return False, f"Stripe verification received invalid currency '{payload_currency}'; expected GBP.", {}

        # Amount validation if supplied in payload
        if 'amount' in payload and payload.get('amount') is not None:
            try:
                dec_amount = Decimal(str(payload['amount']))
                if dec_amount != Decimal(str(order.total_amount)):
                    return False, f"Stripe verification amount ({dec_amount}) does not match order amount ({order.total_amount} GBP).", {}
            except (ValueError, ArithmeticError):
                return False, f"Invalid payment amount '{payload.get('amount')}'.", {}

        payment_intent_id = (
            payload.get('payment_intent_id')
            or payload.get('stripe_payment_intent_id')
            or ''
        ).strip()
        client_secret = payload.get('client_secret', '').strip()

        if not payment_intent_id and client_secret and '_secret_' in client_secret:
            payment_intent_id = client_secret.split('_secret_')[0].strip()

        if not payment_intent_id:
            return False, "Missing payment_intent_id in confirmation payload.", {}

        if not payment_intent_id.startswith('pi_'):
            return False, f"Invalid Stripe PaymentIntent ID format: '{payment_intent_id}'.", {}

        # Authoritative session check: Reject fabricated or cross-order PaymentIntent IDs
        if order.payment_reference and payment_intent_id != order.payment_reference:
            return False, f"PaymentIntent ID '{payment_intent_id}' does not match the active session for order {order.order_number}.", {}

        # If live credentials or non-test environment, query the Stripe API server-side
        has_real_stripe_key = (
            bool(self.secret_key)
            and not self.secret_key.startswith('sk_test_placeholder')
            and self.secret_key.startswith(('sk_live_', 'sk_test_'))
        )

        if not self.test_mode or has_real_stripe_key:
            if not has_real_stripe_key:
                return False, "Production Stripe verification requires valid Stripe API keys.", {}
            url = f"https://api.stripe.com/v1/payment_intents/{payment_intent_id}"
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.secret_key}"})
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    stripe_data = json.loads(resp.read().decode('utf-8'))
                    stripe_status = stripe_data.get('status')
                    if stripe_status != 'succeeded':
                        return False, f"Stripe payment intent status is '{stripe_status}', not 'succeeded'.", stripe_data

                    stripe_amount = stripe_data.get('amount')
                    expected_pence = self._to_pence(order.total_amount)
                    if stripe_amount != expected_pence:
                        return False, f"Stripe payment amount ({stripe_amount}) does not match order amount ({expected_pence} pence).", stripe_data

                    stripe_currency = str(stripe_data.get('currency', '')).strip().upper()
                    if stripe_currency != 'GBP':
                        return False, f"Stripe payment currency ({stripe_currency}) does not match order currency (GBP).", stripe_data

                    return True, payment_intent_id, {
                        "payment_intent_id": payment_intent_id,
                        "status": "succeeded",
                        "verified": True,
                        "stripe_response": stripe_data,
                    }
            except urllib.error.HTTPError as e:
                err_body = e.read().decode('utf-8', errors='ignore')
                return False, f"Stripe API error ({e.code}): {err_body}", {}
            except Exception as e:
                return False, f"Failed to communicate with Stripe API: {str(e)}", {}

        # Deterministic sandbox verification in legitimate test mode only
        if self.test_mode:
            return True, payment_intent_id, {
                "payment_intent_id": payment_intent_id,
                "status": "succeeded",
                "verified": True,
                "test_mode": True,
            }

        return False, "Live Stripe verification requires valid Stripe API keys.", {}

    def verify_webhook(
        self,
        request_body: bytes,
        headers: Dict[str, str],
    ) -> Tuple[bool, Optional[str], Optional[str], Dict[str, Any]]:
        """
        Validates Stripe webhook signature from Stripe-Signature header:
        Header format: t=<timestamp>,v1=<signature>
        Expected: HMAC-SHA256(webhook_secret, t + "." + payload)
        """
        normalized_headers = {k.lower(): v for k, v in headers.items()}
        signature_header = normalized_headers.get('stripe-signature', '').strip()

        if not signature_header:
            return False, None, None, {"error": "Missing Stripe-Signature header."}

        parts = {}
        for item in signature_header.split(','):
            if '=' in item:
                k, v = item.split('=', 1)
                parts[k.strip()] = v.strip()

        timestamp = parts.get('t', '')
        v1_sig = parts.get('v1', '')

        is_valid = False
        if timestamp and v1_sig:
            signed_payload = f"{timestamp}.{request_body.decode('utf-8')}".encode('utf-8')
            expected = hmac.new(
                self.webhook_secret.encode('utf-8'),
                signed_payload,
                hashlib.sha256,
            ).hexdigest()
            is_valid = hmac.compare_digest(expected, v1_sig)

        if not is_valid and self.test_mode and (signature_header in ('test_stripe_sig_valid', 'mock_valid_sig') or v1_sig == 'test_stripe_sig_valid'):
            is_valid = True

        if not is_valid:
            return False, None, None, {"error": "Invalid Stripe webhook signature."}

        try:
            payload = json.loads(request_body.decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            return False, None, None, {"error": "Malformed JSON in Stripe webhook body."}

        event_id = payload.get('id') or f"evt_{hashlib.sha256(request_body).hexdigest()[:20]}"
        event_type = payload.get('type', '')

        return True, event_id, event_type, payload

    def issue_refund(
        self,
        payment_reference: str,
        amount: Any,
        currency: str,
        reason: str = '',
        refund_number: str = '',
        notes: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Issues an authentic refund via Stripe Refunds API.
        POST https://api.stripe.com/v1/refunds
        Falls back to deterministic test mode when test_mode is enabled.
        """
        if str(currency).strip().upper() != 'GBP':
            return False, f"Stripe UK provider only supports GBP refunds; received '{currency}'.", {}

        try:
            amount_pence = self._to_pence(Decimal(str(amount)))
        except Exception:
            return False, f"Invalid refund amount '{amount}'.", {}

        if amount_pence <= 0:
            return False, "Refund amount must be greater than zero.", {}

        payment_id = (payment_reference or '').strip()
        if not payment_id:
            return False, "Missing payment_reference for Stripe refund dispatch.", {}

        # Live / Sandbox Stripe API call
        if self.is_configured and not getattr(settings, 'IS_TESTING', False):
            url = "https://api.stripe.com/v1/refunds"
            params = {
                "amount": str(amount_pence),
                "payment_intent": payment_id,
                "reason": "requested_by_customer",
            }
            if refund_number:
                params["metadata[refund_number]"] = str(refund_number)
            if reason:
                params["metadata[reason_detail]"] = str(reason)[:255]
            if notes:
                for k, v in notes.items():
                    params[f"metadata[{k}]"] = str(v)[:255]

            encoded_data = urllib.parse.urlencode(params).encode('utf-8')
            idempotency_key = refund_number or f"idemp_{uuid.uuid4().hex}"
            req = urllib.request.Request(
                url,
                data=encoded_data,
                headers={
                    "Authorization": f"Bearer {self.secret_key}",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "DriverXtra-Platform/1.0",
                    "Idempotency-Key": idempotency_key,
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    stripe_data = json.loads(resp.read().decode('utf-8'))
                    re_id = stripe_data.get('id')
                    logger.info("Successfully dispatched Stripe refund %s for payment %s", re_id, payment_id)
                    return True, re_id, stripe_data
            except urllib.error.HTTPError as http_err:
                err_text = http_err.read().decode('utf-8', errors='replace')
                logger.error("Stripe Refund API error HTTP %s: %s", http_err.code, err_text)
                if not getattr(settings, 'IS_TESTING', False):
                    return False, f"Stripe Refund API error (HTTP {http_err.code}): {err_text}", {"http_code": http_err.code}
                logger.warning("Falling back to deterministic test refund in IS_TESTING environment.")
            except Exception as exc:
                logger.error("Failed to connect to Stripe Refund API: %s", str(exc))
                if not getattr(settings, 'IS_TESTING', False):
                    return False, f"Failed to connect to Stripe Refund API: {str(exc)}", {}
                logger.warning("Falling back to deterministic test refund in IS_TESTING environment.")

        # Test mode fallback for isolated test suites or development
        if self.test_mode:
            re_id = f"re_test_{uuid.uuid4().hex[:18]}"
            metadata = {
                "refund_number": refund_number,
                "reason": reason,
            }
            if notes:
                metadata.update(notes)

            return True, re_id, {
                "id": re_id,
                "object": "refund",
                "amount": amount_pence,
                "currency": "gbp",
                "payment_intent": payment_id,
                "status": "succeeded",
                "metadata": metadata,
                "test_mode": True,
            }

        return False, "Live Stripe refunds require configured credentials (STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY).", {}

    def inquire_refund(
        self,
        payment_reference: str,
        refund_number: str,
        gateway_refund_id: Optional[str] = None,
    ) -> Tuple[str, Optional[str], Dict[str, Any]]:
        """
        Inquires Stripe to determine the authoritative status of a refund.
        Queries https://api.stripe.com/v1/refunds/{gateway_refund_id} if ID is known,
        or lists refunds for the payment_intent and matches by metadata[refund_number].
        Returns:
            status: 'SUCCEEDED' | 'FAILED' | 'PROCESSING' | 'NOT_FOUND' | 'UNKNOWN'
            gateway_refund_id_or_error: string
            extra_details: dict
        """
        payment_id = (payment_reference or '').strip()
        rfnd_num = (refund_number or '').strip()
        gw_id = (gateway_refund_id or '').strip()

        # Live / Sandbox call when configured (or when force_network_call is enabled for tests)
        if (self.is_configured and not getattr(settings, 'IS_TESTING', False)) or getattr(self, 'force_network_call', False):
            # 1. Query by known gateway_refund_id if available
            if gw_id:
                url = f"https://api.stripe.com/v1/refunds/{urllib.parse.quote(gw_id)}"
                req = urllib.request.Request(
                    url,
                    headers={
                        "Authorization": f"Bearer {self.secret_key}",
                        "User-Agent": "DriverXtra-Platform/1.0",
                    },
                    method="GET",
                )
                try:
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        data = json.loads(resp.read().decode('utf-8'))
                        st = data.get('status', '').lower()
                        if st == 'succeeded':
                            return 'SUCCEEDED', data.get('id'), data
                        elif st == 'pending':
                            return 'PROCESSING', data.get('id'), data
                        elif st in ('failed', 'canceled'):
                            return 'FAILED', data.get('failure_reason') or 'Stripe refund failed or canceled', data
                        return 'UNKNOWN', f"Unrecognized Stripe refund status '{st}'", data
                except urllib.error.HTTPError as http_err:
                    if http_err.code == 404:
                        return 'NOT_FOUND', f"Refund '{gw_id}' not found on Stripe", {}
                    err_text = http_err.read().decode('utf-8', errors='replace')
                    return 'UNKNOWN', f"Stripe API error (HTTP {http_err.code}): {err_text}", {}
                except Exception as exc:
                    return 'UNKNOWN', f"Connection error querying Stripe: {str(exc)}", {}

            # 2. Query by payment_intent to find refund by metadata[refund_number] with cursor-based pagination
            if payment_id:
                has_more = True
                starting_after = None
                max_pages = 5
                page_count = 0
                last_data = {}

                while has_more and page_count < max_pages:
                    page_count += 1
                    query_params = f"payment_intent={urllib.parse.quote(payment_id)}&limit=50"
                    if starting_after:
                        query_params += f"&starting_after={urllib.parse.quote(starting_after)}"
                    url = f"https://api.stripe.com/v1/refunds?{query_params}"
                    req = urllib.request.Request(
                        url,
                        headers={
                            "Authorization": f"Bearer {self.secret_key}",
                            "User-Agent": "DriverXtra-Platform/1.0",
                        },
                        method="GET",
                    )
                    try:
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            data = json.loads(resp.read().decode('utf-8'))
                            last_data = data
                            items = data.get('data', [])
                            for item in items:
                                meta = item.get('metadata', {}) or {}
                                if meta.get('refund_number') == rfnd_num or (gw_id and item.get('id') == gw_id):
                                    st = item.get('status', '').lower()
                                    if st == 'succeeded':
                                        return 'SUCCEEDED', item.get('id'), item
                                    elif st == 'pending':
                                        return 'PROCESSING', item.get('id'), item
                                    elif st in ('failed', 'canceled'):
                                        return 'FAILED', item.get('failure_reason') or 'Stripe refund failed or canceled', item
                                    return 'UNKNOWN', f"Unrecognized Stripe refund status '{st}'", item

                            has_more = bool(data.get('has_more', False))
                            if items:
                                starting_after = items[-1].get('id')
                            else:
                                has_more = False

                    except urllib.error.HTTPError as http_err:
                        if http_err.code == 404:
                            return 'NOT_FOUND', f"PaymentIntent '{payment_id}' not found on Stripe", {}
                        err_text = http_err.read().decode('utf-8', errors='replace')
                        return 'UNKNOWN', f"Stripe API error on page {page_count} (HTTP {http_err.code}): {err_text}", {}
                    except Exception as exc:
                        return 'UNKNOWN', f"Connection error querying Stripe on page {page_count}: {str(exc)}", {}

                if has_more:
                    return 'UNKNOWN', f"Refund '{rfnd_num}' not found within first {max_pages * 50} Stripe records. Inquiry limit reached.", last_data

                return 'NOT_FOUND', f"No refund with number '{rfnd_num}' found on Stripe for PaymentIntent '{payment_id}' across {page_count} page(s)", last_data

        # Test mode / sandbox mock behavior
        if self.test_mode or getattr(settings, 'IS_TESTING', False):
            check_key = f"{gw_id}_{rfnd_num}".lower()
            if "fail" in check_key:
                return 'FAILED', "Simulated Stripe refund failure", {"status": "failed", "test_mode": True}
            if "unknown" in check_key or "timeout" in check_key:
                return 'UNKNOWN', "Simulated gateway connection error during inquiry", {"test_mode": True}
            if "not_found" in check_key:
                return 'NOT_FOUND', "Simulated Stripe refund not found", {"test_mode": True}
            if "processing" in check_key or "pending" in check_key:
                return 'PROCESSING', gw_id or f"re_test_{rfnd_num}", {"status": "pending", "test_mode": True}

            re_id = gw_id or f"re_test_reconciled_{rfnd_num}"
            return 'SUCCEEDED', re_id, {
                "id": re_id,
                "status": "succeeded",
                "payment_intent": payment_id,
                "test_mode": True,
            }

        return 'UNKNOWN', "Live Stripe inquiry requires configured credentials.", {}

