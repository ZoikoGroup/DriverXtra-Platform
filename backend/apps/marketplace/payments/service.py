import logging
from decimal import Decimal
from typing import Dict, Any, List, Tuple, Optional
from django.conf import settings
from django.utils import timezone
import datetime
from django.db import models, transaction
from apps.marketplace.models import (
    Order,
    OrderStatusChoices,
    PaymentMethodChoices,
    PaymentStatusChoices,
    CODCollectionStatusChoices,
    PaymentTransaction,
    PaymentWebhookEvent,
    StockMovementReasonChoices,
    Refund,
    RefundStatusChoices,
)
from apps.marketplace.services import adjust_stock
from apps.marketplace.payments.razorpay_provider import RazorpayPaymentProvider
from apps.marketplace.payments.stripe_provider import StripePaymentProvider
from platform_core.audit.writer import record_audit_entry

logger = logging.getLogger(__name__)


class PaymentService:
    """
    Central orchestration service for online payment gateways (Stripe/Razorpay)
    and Cash on Delivery (COD) workflows.
    """

    @staticmethod
    def normalize_country_code(country_str: Optional[str]) -> str:
        """Normalizes free-text country string to ISO alpha-2 code."""
        if not country_str:
            return 'IN'
        c = country_str.strip().upper()
        if c in ('IN', 'INDIA', 'BHARAT'):
            return 'IN'
        if c in ('GB', 'UK', 'UNITED KINGDOM', 'GREAT BRITAIN', 'ENGLAND', 'SCOTLAND', 'WALES'):
            return 'GB'
        return c

    @classmethod
    def get_provider_for_currency_and_country(cls, currency: str, country: Optional[str] = None):
        """Resolves the payment provider based on currency and country string."""
        country_code = cls.normalize_country_code(country)
        if currency == 'INR' or country_code == 'IN':
            return RazorpayPaymentProvider()
        elif currency == 'GBP' or country_code == 'GB':
            return StripePaymentProvider()
        else:
            # Default to Stripe for international currency
            return StripePaymentProvider()

    @classmethod
    def get_provider_for_order(cls, order: Order):
        """Resolves the authoritative payment provider based on order currency and country."""
        return cls.get_provider_for_currency_and_country(order.currency, order.shipping_country)

    @classmethod
    def check_cod_eligibility(
        cls,
        country: str,
        currency: str,
        amount: Decimal,
    ) -> Tuple[bool, Optional[str]]:
        """
        Determines whether an order is eligible for Cash on Delivery (COD)
        based on configured business rules.
        """
        cod_enabled = getattr(settings, 'COD_ENABLED', True)
        if not cod_enabled:
            return False, "Cash on Delivery is currently disabled by platform operations."

        country_code = cls.normalize_country_code(country)
        allowed_countries = [c.upper() for c in getattr(settings, 'COD_ALLOWED_COUNTRIES', ['IN', 'GB'])]
        if country_code not in allowed_countries:
            return False, f"Cash on Delivery is not available for deliveries to '{country}'."

        max_inr = Decimal(str(getattr(settings, 'COD_MAX_AMOUNT_INR', Decimal('50000.00'))))
        max_gbp = Decimal(str(getattr(settings, 'COD_MAX_AMOUNT_GBP', Decimal('500.00'))))

        amount_dec = Decimal(str(amount))

        if currency == 'INR' and amount_dec > max_inr:
            return False, f"Order total (₹{amount_dec}) exceeds the maximum Cash on Delivery threshold of ₹{max_inr}."

        if currency == 'GBP' and amount_dec > max_gbp:
            return False, f"Order total (£{amount_dec}) exceeds the maximum Cash on Delivery threshold of £{max_gbp}."

        return True, None

    @classmethod
    def record_payment_failure(
        cls,
        order: Order,
        actor: Optional[Any] = None,
        reason: str = "Payment failed or declined",
        provider_transaction_id: Optional[str] = None,
        extra_details: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Records a failed payment attempt without cancelling the order,
        allowing the buyer to retry payment or choose another payment method.
        """
        if order.payment_status == PaymentStatusChoices.PAID:
            return False, "Cannot record payment failure for an order that is already paid.", {}

        provider = cls.get_provider_for_order(order)
        with transaction.atomic():
            locked_order = Order.objects.select_for_update().get(id=order.id)
            if locked_order.payment_status == PaymentStatusChoices.PAID:
                return False, "Cannot record payment failure for an order that is already paid.", {}

            locked_order.payment_status = PaymentStatusChoices.FAILED
            locked_order.save(update_fields=['payment_status', 'updated_at'])

            PaymentTransaction.objects.create(
                order=locked_order,
                transaction_type=PaymentTransaction.TransactionTypeChoices.PAYMENT,
                provider=provider.provider_name,
                amount=locked_order.total_amount,
                currency=locked_order.currency,
                status=PaymentTransaction.StatusChoices.FAILED,
                error_message=reason,
                provider_transaction_id=provider_transaction_id or '',
                provider_order_id=locked_order.payment_reference or '',
                raw_response=extra_details or {},
            )

            record_audit_entry(
                event_type="marketplace.order.payment_failed",
                action="marketplace:order.payment_fail",
                resource_type="Order",
                resource_id=str(locked_order.id),
                actor_id=getattr(actor, 'id', None) or locked_order.buyer_id,
                metadata={
                    "order_number": locked_order.order_number,
                    "reason": reason,
                    "provider": provider.provider_name,
                    "total_amount": str(locked_order.total_amount),
                    "currency": locked_order.currency,
                },
            )

        return True, f"Payment failure recorded for order {order.order_number}.", {
            "order_number": order.order_number,
            "payment_status": PaymentStatusChoices.FAILED,
        }

    @classmethod
    def cancel_unpaid_order(
        cls,
        order: Order,
        actor: Optional[Any] = None,
        reason: str = "Payment cancelled or abandoned",
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Safely cancels an unpaid online or pending order and immediately restores
        the reserved stock to the catalogue inventory.
        """
        if order.payment_status == PaymentStatusChoices.PAID:
            return False, "Cannot cancel an order that has already been paid.", {}

        if order.status == OrderStatusChoices.CANCELLED:
            return True, f"Order {order.order_number} is already cancelled.", {
                "order_number": order.order_number,
                "status": order.status,
            }

        with transaction.atomic():
            locked_order = Order.objects.select_for_update().get(id=order.id)
            if locked_order.payment_status == PaymentStatusChoices.PAID:
                return False, "Cannot cancel an order that has already been paid.", {}

            if locked_order.status == OrderStatusChoices.CANCELLED:
                return True, f"Order {locked_order.order_number} is already cancelled.", {
                    "order_number": locked_order.order_number,
                    "status": locked_order.status,
                }

            locked_order.status = OrderStatusChoices.CANCELLED
            locked_order.payment_status = PaymentStatusChoices.CANCELLED
            locked_order.save(update_fields=['status', 'payment_status', 'updated_at'])

            for item in locked_order.items.select_related('listing').all():
                if item.listing:
                    adjust_stock(
                        listing=item.listing,
                        delta=item.quantity,
                        reason=StockMovementReasonChoices.RETURN,
                        actor=actor,
                        note=f"Stock restored for cancelled order {locked_order.order_number}: {reason}",
                    )

            provider = cls.get_provider_for_order(locked_order)
            PaymentTransaction.objects.create(
                order=locked_order,
                transaction_type=PaymentTransaction.TransactionTypeChoices.PAYMENT,
                provider=provider.provider_name,
                amount=locked_order.total_amount,
                currency=locked_order.currency,
                status=PaymentTransaction.StatusChoices.CANCELLED,
                error_message=reason,
            )

            record_audit_entry(
                event_type="marketplace.order.payment_cancelled",
                action="marketplace:order.payment_cancel",
                resource_type="Order",
                resource_id=str(locked_order.id),
                actor_id=getattr(actor, 'id', None) or locked_order.buyer_id,
                metadata={
                    "order_number": locked_order.order_number,
                    "reason": reason,
                    "total_amount": str(locked_order.total_amount),
                    "currency": locked_order.currency,
                },
            )

        return True, f"Order {order.order_number} has been cancelled and stock returned.", {
            "order_number": order.order_number,
            "status": OrderStatusChoices.CANCELLED,
            "payment_status": PaymentStatusChoices.CANCELLED,
        }

    @classmethod
    def expire_stale_pending_orders(cls, max_age_minutes: Optional[int] = None) -> int:
        """
        Finds and cancels online orders that have remained unpaid past the reservation timeout,
        releasing the held stock back to seller inventory.
        """
        mins = max_age_minutes if max_age_minutes is not None else getattr(settings, 'PAYMENT_EXPIRY_MINUTES', 30)
        cutoff = timezone.now() - datetime.timedelta(minutes=mins)

        stale_orders = Order.objects.filter(
            payment_method=PaymentMethodChoices.ONLINE,
            payment_status=PaymentStatusChoices.PENDING,
            status=OrderStatusChoices.PENDING_CONFIRMATION,
            created_at__lt=cutoff,
        )

        expired_count = 0
        for order in stale_orders:
            try:
                success, _, _ = cls.cancel_unpaid_order(
                    order=order,
                    reason=f"Auto-expired after {mins} minutes without payment confirmation.",
                )
                if success:
                    expired_count += 1
            except Exception as exc:
                logger.warning("Failed to auto-expire stale order %s: %s", order.order_number, str(exc))

        return expired_count

    @classmethod
    def get_available_payment_methods(
        cls,
        country: str,
        currency: str,
        amount: Decimal,
    ) -> List[Dict[str, Any]]:
        """
        Returns list of available payment options for a given country, currency, and total amount.
        """
        country_code = cls.normalize_country_code(country)
        methods = []

        # 1. Online Provider
        online_provider = cls.get_provider_for_currency_and_country(currency=currency, country=country)
        is_online_ready = bool(getattr(online_provider, 'is_configured', False) or getattr(online_provider, 'test_mode', False))

        if country_code == 'IN' or currency == 'INR':
            methods_info = online_provider.get_account_methods() if hasattr(online_provider, 'get_account_methods') else {}
            methods.append({
                "code": PaymentMethodChoices.ONLINE,
                "provider": "RAZORPAY",
                "name": "Online Payment (UPI, Cards, NetBanking)",
                "currency": "INR",
                "is_available": is_online_ready,
                "reason": None if is_online_ready else "Online payment via Razorpay is currently not configured on this server.",
                "description": "Secure instant checkout via Razorpay supporting all Indian banks and UPI.",
                "methods_info": methods_info,
            })
        else:
            methods.append({
                "code": PaymentMethodChoices.ONLINE,
                "provider": "STRIPE",
                "name": "Card Payment (Stripe / Apple Pay / Google Pay)",
                "currency": "GBP",
                "is_available": is_online_ready,
                "reason": None if is_online_ready else "Online card payment is currently not configured on this server.",
                "description": "Secure card checkout via Stripe supporting UK debit/credit cards and digital wallets.",
            })

        # 2. Cash on Delivery (COD)
        is_eligible, reason = cls.check_cod_eligibility(country=country, currency=currency, amount=amount)
        methods.append({
            "code": PaymentMethodChoices.COD,
            "provider": "COD",
            "name": "Cash on Delivery (COD)",
            "currency": currency,
            "is_available": is_eligible,
            "reason": reason,
            "description": "Pay in cash or card to courier upon physical package delivery.",
        })

        return methods

    @classmethod
    def create_payment_session(cls, order: Order) -> Dict[str, Any]:
        """
        Initiates an authoritative payment session/order with the provider.
        """
        if order.status == OrderStatusChoices.CANCELLED:
            raise ValueError(f"Cannot initialize payment session for cancelled order '{order.order_number}'.")

        expiry_minutes = getattr(settings, 'PAYMENT_EXPIRY_MINUTES', 30)
        if (
            order.payment_method == PaymentMethodChoices.ONLINE
            and order.payment_status == PaymentStatusChoices.PENDING
            and order.created_at
            and order.created_at < timezone.now() - datetime.timedelta(minutes=expiry_minutes)
        ):
            cls.cancel_unpaid_order(order, reason=f"Order payment window ({expiry_minutes} mins) expired.")
            raise ValueError(f"Order '{order.order_number}' payment window has expired. Please create a new order.")
        if order.payment_method == PaymentMethodChoices.COD:
            return {
                "provider": "COD",
                "payment_method": PaymentMethodChoices.COD,
                "payment_status": order.payment_status,
                "cod_collection_status": order.cod_collection_status,
                "amount": str(order.total_amount),
                "currency": order.currency,
                "message": "Order is placed with Cash on Delivery. Payment will be collected upon delivery.",
            }

        provider = cls.get_provider_for_order(order)
        session_data = provider.create_payment_session(order)

        # Record PaymentTransaction in PENDING state
        with transaction.atomic():
            new_provider_order_id = session_data.get('provider_order_id', '')
            PaymentTransaction.objects.create(
                order=order,
                transaction_type=PaymentTransaction.TransactionTypeChoices.PAYMENT,
                provider=provider.provider_name,
                amount=order.total_amount,
                currency=order.currency,
                status=PaymentTransaction.StatusChoices.PENDING,
                provider_order_id=new_provider_order_id,
                idempotency_key=order.idempotency_key,
                raw_response=session_data,
            )
            if new_provider_order_id and order.payment_reference != new_provider_order_id:
                order.payment_reference = new_provider_order_id
                order.save(update_fields=['payment_reference', 'updated_at'])

        return session_data

    @classmethod
    def verify_payment(
        cls,
        order: Order,
        payload: Dict[str, Any],
        actor: Optional[Any] = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Server-authoritative verification of client confirmation payload.
        Never marks order as paid without cryptographic or provider-validated proof.
        """
        if order.payment_method == PaymentMethodChoices.COD:
            return False, "Cannot verify online payment for a Cash on Delivery order.", {}

        if order.status == OrderStatusChoices.CANCELLED:
            return False, f"Cannot verify payment for cancelled order '{order.order_number}'.", {}

        if order.payment_status == PaymentStatusChoices.PAID:
            return True, order.payment_reference, {
                "message": "Order is already marked as paid.",
                "already_paid": True,
            }

        # Amount validation if supplied in verification payload
        req_amount = payload.get('amount')
        if req_amount is not None:
            try:
                dec_amount = Decimal(str(req_amount))
                if dec_amount != Decimal(str(order.total_amount)):
                    return False, f"Payment amount mismatch: expected {order.total_amount} {order.currency}, received {dec_amount} {order.currency}.", {
                        "expected_amount": str(order.total_amount),
                        "received_amount": str(dec_amount),
                    }
            except (ValueError, ArithmeticError):
                return False, f"Invalid payment amount '{req_amount}'.", {}

        # Currency validation if supplied in verification payload
        req_currency = str(payload.get('currency', '')).strip().upper()
        if req_currency and req_currency != order.currency.upper():
            return False, f"Payment currency mismatch: expected {order.currency}, received {req_currency}.", {}

        provider = cls.get_provider_for_order(order)
        is_valid, payment_id_or_error, extra = provider.verify_payment(order, payload)

        with transaction.atomic():
            if is_valid:
                order.payment_status = PaymentStatusChoices.PAID
                order.paid_at = timezone.now()
                order.payment_reference = payment_id_or_error
                if order.status == OrderStatusChoices.PENDING_CONFIRMATION:
                    order.status = OrderStatusChoices.CONFIRMED

                order.save(update_fields=['payment_status', 'paid_at', 'payment_reference', 'status', 'updated_at'])

                # Avoid duplicate SUCCESS transactions on retries
                existing_success = PaymentTransaction.objects.filter(
                    order=order,
                    status=PaymentTransaction.StatusChoices.SUCCESS,
                    provider_transaction_id=payment_id_or_error,
                ).first()

                if not existing_success:
                    PaymentTransaction.objects.create(
                        order=order,
                        transaction_type=PaymentTransaction.TransactionTypeChoices.PAYMENT,
                        provider=provider.provider_name,
                        amount=order.total_amount,
                        currency=order.currency,
                        status=PaymentTransaction.StatusChoices.SUCCESS,
                        provider_transaction_id=payment_id_or_error,
                        provider_order_id=extra.get('razorpay_order_id') or order.payment_reference,
                        provider_signature=payload.get('razorpay_signature', ''),
                        raw_response=extra,
                    )

                record_audit_entry(
                    event_type="marketplace.order.payment_verified",
                    action="marketplace:order.payment_verify",
                    resource_type="Order",
                    resource_id=str(order.id),
                    actor_id=actor.id if actor else order.buyer_id,
                    metadata={
                        "order_number": order.order_number,
                        "provider": provider.provider_name,
                        "payment_reference": payment_id_or_error,
                        "amount": str(order.total_amount),
                        "currency": order.currency,
                    },
                )
                return True, payment_id_or_error, extra
            else:
                # Avoid duplicate identical FAILED transaction records on rapid retry
                last_failed = PaymentTransaction.objects.filter(
                    order=order,
                    status=PaymentTransaction.StatusChoices.FAILED,
                ).order_by('-created_at').first()

                if not (last_failed and last_failed.error_message == payment_id_or_error):
                    PaymentTransaction.objects.create(
                        order=order,
                        transaction_type=PaymentTransaction.TransactionTypeChoices.PAYMENT,
                        provider=provider.provider_name,
                        amount=order.total_amount,
                        currency=order.currency,
                        status=PaymentTransaction.StatusChoices.FAILED,
                        error_message=payment_id_or_error,
                        raw_response=extra,
                    )
                record_audit_entry(
                    event_type="marketplace.order.payment_verification_failed",
                    action="marketplace:order.payment_verify_failed",
                    resource_type="Order",
                    resource_id=str(order.id),
                    actor_id=actor.id if actor else order.buyer_id,
                    metadata={
                        "order_number": order.order_number,
                        "provider": provider.provider_name,
                        "error": payment_id_or_error,
                    },
                )
                return False, payment_id_or_error, extra

    @classmethod
    def process_webhook(
        cls,
        provider_name: str,
        request_body: bytes,
        headers: Dict[str, str],
    ) -> Tuple[bool, int, Dict[str, Any]]:
        """
        Receives, verifies, and idempotently processes provider webhook callbacks.
        """
        p_name = provider_name.strip().upper()
        if p_name == 'RAZORPAY':
            provider = RazorpayPaymentProvider()
        elif p_name == 'STRIPE':
            provider = StripePaymentProvider()
        else:
            return False, 400, {"error": f"Unsupported webhook provider '{provider_name}'."}

        is_valid, event_id, event_type, payload = provider.verify_webhook(request_body, headers)
        if not is_valid:
            return False, 400, payload

        # Webhook Idempotency Check
        existing_event = PaymentWebhookEvent.objects.filter(provider=p_name, event_id=event_id).first()
        if existing_event and existing_event.processed:
            return True, 200, {
                "status": "already_processed",
                "message": f"Webhook event '{event_id}' has already been processed.",
                "replayed": True,
            }

        # Locate associated order and refund
        order = None
        order_number = None
        refund_obj = None
        gateway_refund_id = None

        if p_name == 'RAZORPAY':
            # Razorpay order & refund payload inspection
            payload_data = payload.get('payload', {})
            order_entity = payload_data.get('order', {}).get('entity', {})
            payment_entity = payload_data.get('payment', {}).get('entity', {})
            refund_entity = payload_data.get('refund', {}).get('entity', {})

            if refund_entity:
                gateway_refund_id = refund_entity.get('id')
                rfnd_notes = refund_entity.get('notes', {}) or {}
                order_number = rfnd_notes.get('order_number') or order_number
                rfnd_num = rfnd_notes.get('refund_number')
                if gateway_refund_id:
                    refund_obj = Refund.objects.filter(gateway_refund_id=gateway_refund_id).first()
                if not refund_obj and rfnd_num:
                    refund_obj = Refund.objects.filter(refund_number=rfnd_num).first()

            razorpay_order_id = order_entity.get('id') or payment_entity.get('order_id')
            notes = order_entity.get('notes') or payment_entity.get('notes') or {}
            if not order_number:
                order_number = notes.get('order_number')
            order_id = notes.get('order_id')

            if order_number:
                order = Order.objects.filter(order_number=order_number).first()
            if not order and order_id:
                try:
                    order = Order.objects.filter(id=order_id).first()
                except Exception:
                    pass
            if not order and razorpay_order_id:
                order = Order.objects.filter(payment_reference=razorpay_order_id).first()
            if not order and refund_obj:
                order = refund_obj.order

        elif p_name == 'STRIPE':
            data_obj = payload.get('data', {}).get('object', {})
            obj_type = data_obj.get('object')

            if obj_type == 'refund' or str(data_obj.get('id', '')).startswith('re_'):
                gateway_refund_id = data_obj.get('id')
                rfnd_meta = data_obj.get('metadata', {}) or {}
                rfnd_num = rfnd_meta.get('refund_number')
                order_number = rfnd_meta.get('order_number')
                pi_id = data_obj.get('payment_intent')
                if gateway_refund_id:
                    refund_obj = Refund.objects.filter(gateway_refund_id=gateway_refund_id).first()
                if not refund_obj and rfnd_num:
                    refund_obj = Refund.objects.filter(refund_number=rfnd_num).first()
            elif obj_type == 'charge' or 'refunds' in data_obj or str(data_obj.get('id', '')).startswith('ch_'):
                refunds_data = data_obj.get('refunds', {}).get('data', [])
                if refunds_data:
                    first_rfnd = refunds_data[0]
                    gateway_refund_id = first_rfnd.get('id')
                    rfnd_meta = first_rfnd.get('metadata', {}) or {}
                    rfnd_num = rfnd_meta.get('refund_number')
                    order_number = rfnd_meta.get('order_number')
                    if gateway_refund_id:
                        refund_obj = Refund.objects.filter(gateway_refund_id=gateway_refund_id).first()
                    if not refund_obj and rfnd_num:
                        refund_obj = Refund.objects.filter(refund_number=rfnd_num).first()
                pi_id = data_obj.get('payment_intent')
            else:
                metadata = data_obj.get('metadata', {})
                order_number = metadata.get('order_number')
                pi_id = data_obj.get('id')

            if order_number:
                order = Order.objects.filter(order_number=order_number).first()
            if not order and pi_id:
                order = Order.objects.filter(payment_reference=pi_id).first()
            if not order and refund_obj:
                order = refund_obj.order

        settled_this_request = False

        with transaction.atomic():
            webhook_record, created = PaymentWebhookEvent.objects.select_for_update().get_or_create(
                provider=p_name,
                event_id=event_id,
                defaults={
                    "event_type": event_type or "unknown",
                    "order": order,
                    "payload": payload,
                },
            )

            # Concurrent/retry defense inside transaction lock
            if not created and webhook_record.processed:
                return True, 200, {
                    "status": "already_processed",
                    "message": f"Webhook event '{event_id}' has already been processed.",
                    "replayed": True,
                }

            # Lock order to guard against concurrent settlement races
            locked_order = None
            if order:
                locked_order = Order.objects.select_for_update().filter(id=order.id).first()

            # Process Success Event
            if event_type in (
                'payment_intent.succeeded',
                'order.paid',
                'payment.captured',
                'payment.authorized',
                'checkout.session.completed',
            ):
                # Guard against reviving or settling already cancelled orders
                if locked_order and (
                    locked_order.status == OrderStatusChoices.CANCELLED
                    or locked_order.payment_status == PaymentStatusChoices.CANCELLED
                ):
                    logger.warning(
                        "Payment success webhook %s received for cancelled order %s. Payment confirmation rejected.",
                        event_id, locked_order.order_number
                    )
                    webhook_record.processed = True
                    webhook_record.processed_at = timezone.now()
                    webhook_record.save(update_fields=['processed', 'processed_at'])
                    return True, 200, {
                        "status": "ignored",
                        "message": f"Order {locked_order.order_number} is cancelled. Payment confirmation ignored.",
                        "order_status": locked_order.status,
                        "event_id": event_id,
                    }

                if locked_order and p_name == 'RAZORPAY':
                    # Webhook amount and currency integrity check
                    payment_entity = payload.get('payload', {}).get('payment', {}).get('entity', {})
                    wb_amount_paise = payment_entity.get('amount')
                    wb_currency = payment_entity.get('currency')
                    if wb_amount_paise is not None:
                        expected_paise = int(round(locked_order.total_amount * 100))
                        if wb_amount_paise != expected_paise:
                            logger.error(
                                "Razorpay webhook amount mismatch for %s: expected %s, got %s",
                                locked_order.order_number, expected_paise, wb_amount_paise
                            )
                            return False, 400, {
                                "status": "failed",
                                "error": f"Webhook payment amount mismatch for order {locked_order.order_number}."
                            }
                    if wb_currency and wb_currency.upper() != locked_order.currency.upper():
                        logger.error(
                            "Razorpay webhook currency mismatch for %s: expected %s, got %s",
                            locked_order.order_number, locked_order.currency, wb_currency
                        )
                        return False, 400, {
                            "status": "failed",
                            "error": f"Webhook payment currency mismatch for order {locked_order.order_number}."
                        }
                elif locked_order and p_name == 'STRIPE':
                    data_obj = payload.get('data', {}).get('object', {})
                    wb_amount_pence = data_obj.get('amount')
                    wb_currency = data_obj.get('currency')
                    if wb_amount_pence is not None:
                        expected_pence = int(round(Decimal(str(locked_order.total_amount)) * 100))
                        if wb_amount_pence != expected_pence:
                            logger.error(
                                "Stripe webhook amount mismatch for %s: expected %s, got %s",
                                locked_order.order_number, expected_pence, wb_amount_pence
                            )
                            return False, 400, {
                                "status": "failed",
                                "error": f"Webhook payment amount mismatch for order {locked_order.order_number}."
                            }
                    if wb_currency and wb_currency.upper() != locked_order.currency.upper():
                        logger.error(
                            "Stripe webhook currency mismatch for %s: expected %s, got %s",
                            locked_order.order_number, locked_order.currency, wb_currency
                        )
                        return False, 400, {
                            "status": "failed",
                            "error": f"Webhook payment currency mismatch for order {locked_order.order_number}."
                        }
                if locked_order and locked_order.payment_status != PaymentStatusChoices.PAID:
                    locked_order.payment_status = PaymentStatusChoices.PAID
                    locked_order.paid_at = timezone.now()
                    if locked_order.status == OrderStatusChoices.PENDING_CONFIRMATION:
                        locked_order.status = OrderStatusChoices.CONFIRMED
                    locked_order.save(update_fields=['payment_status', 'paid_at', 'status', 'updated_at'])

                    # Avoid duplicate SUCCESS transactions if one already exists for this event_id
                    existing_success = PaymentTransaction.objects.filter(
                        order=locked_order,
                        status=PaymentTransaction.StatusChoices.SUCCESS,
                        provider_transaction_id=event_id,
                    ).first()
                    if not existing_success:
                        PaymentTransaction.objects.create(
                            order=locked_order,
                            transaction_type=PaymentTransaction.TransactionTypeChoices.PAYMENT,
                            provider=p_name,
                            amount=locked_order.total_amount,
                            currency=locked_order.currency,
                            status=PaymentTransaction.StatusChoices.SUCCESS,
                            provider_transaction_id=event_id,
                            provider_order_id=locked_order.payment_reference,
                            raw_response=payload,
                        )
                    settled_this_request = True

            # Process Failure Event
            elif event_type in (
                'payment_intent.payment_failed',
                'payment.failed',
                'charge.failed',
            ):
                if locked_order and locked_order.payment_status != PaymentStatusChoices.PAID and locked_order.status != OrderStatusChoices.CANCELLED:
                    locked_order.payment_status = PaymentStatusChoices.FAILED
                    locked_order.save(update_fields=['payment_status', 'updated_at'])

                    PaymentTransaction.objects.create(
                        order=locked_order,
                        transaction_type=PaymentTransaction.TransactionTypeChoices.PAYMENT,
                        provider=p_name,
                        amount=locked_order.total_amount,
                        currency=locked_order.currency,
                        status=PaymentTransaction.StatusChoices.FAILED,
                        provider_transaction_id=event_id,
                        provider_order_id=locked_order.payment_reference,
                        raw_response=payload,
                    )

            # Process Cancellation Event
            elif event_type in (
                'payment_intent.canceled',
                'order.cancelled',
            ):
                if locked_order and locked_order.payment_status != PaymentStatusChoices.PAID:
                    locked_order.payment_status = PaymentStatusChoices.CANCELLED
                    locked_order.save(update_fields=['payment_status', 'updated_at'])

                    PaymentTransaction.objects.create(
                        order=locked_order,
                        transaction_type=PaymentTransaction.TransactionTypeChoices.PAYMENT,
                        provider=p_name,
                        amount=locked_order.total_amount,
                        currency=locked_order.currency,
                        status=PaymentTransaction.StatusChoices.CANCELLED,
                        provider_transaction_id=event_id,
                        provider_order_id=locked_order.payment_reference,
                        raw_response=payload,
                    )

            # Process Refund Events
            elif event_type in (
                'refund.processed',
                'charge.refunded',
                'refund.updated',
                'refund.created',
            ):
                if not refund_obj and locked_order:
                    refund_obj = locked_order.refunds.filter(
                        status__in=[
                            RefundStatusChoices.PENDING,
                            RefundStatusChoices.PROCESSING,
                            RefundStatusChoices.PROCESSING_UNKNOWN,
                        ]
                    ).first()
                if not refund_obj and locked_order:
                    refund_obj = locked_order.refunds.order_by('-created_at').first()

                if refund_obj:
                    locked_rfnd = Refund.objects.select_for_update().get(id=refund_obj.id)
                    if gateway_refund_id and not locked_rfnd.gateway_refund_id:
                        locked_rfnd.gateway_refund_id = gateway_refund_id

                    is_succeeded = event_type in ('refund.processed', 'charge.refunded')
                    if event_type in ('refund.updated', 'refund.created'):
                        p_status = str(payload.get('data', {}).get('object', {}).get('status', '')).lower()
                        if p_status in ('succeeded', 'processed'):
                            is_succeeded = True

                    if is_succeeded and locked_rfnd.status != RefundStatusChoices.SUCCEEDED:
                        ord_target = locked_order or locked_rfnd.order
                        is_late_resolution = locked_rfnd.status in (
                            RefundStatusChoices.FAILED,
                            RefundStatusChoices.CANCELLED,
                        )

                        # Check whether replacement refunds exist on this order
                        other_refunds = ord_target.refunds.exclude(id=locked_rfnd.id)
                        replacement_succeeded = other_refunds.filter(status=RefundStatusChoices.SUCCEEDED).exists()
                        replacement_active = other_refunds.filter(status__in=[
                            RefundStatusChoices.PENDING,
                            RefundStatusChoices.PROCESSING,
                            RefundStatusChoices.PROCESSING_UNKNOWN,
                        ]).exists()

                        # Authoritative balance check: ensure total succeeded will not exceed order total paid
                        other_succeeded_total = other_refunds.filter(
                            status=RefundStatusChoices.SUCCEEDED
                        ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')

                        would_over_refund = (other_succeeded_total + locked_rfnd.amount) > ord_target.total_amount

                        # If this is a late success after FAILED/CANCELLED and a replacement exists OR would over-refund:
                        # Prevent duplicate refund execution and balance corruption!
                        if is_late_resolution and (replacement_succeeded or replacement_active or would_over_refund):
                            conflict_reason = (
                                "REPLACEMENT_REFUND_SUCCEEDED" if replacement_succeeded
                                else ("REPLACEMENT_REFUND_ACTIVE" if replacement_active else "ORDER_BALANCE_EXCEEDED")
                            )
                            logger.warning(
                                "Late gateway success webhook %s for %s refund %s detected conflict (%s) on order %s.",
                                event_id, locked_rfnd.status, locked_rfnd.refund_number, conflict_reason, ord_target.order_number
                            )

                            if gateway_refund_id and not locked_rfnd.gateway_refund_id:
                                locked_rfnd.gateway_refund_id = gateway_refund_id

                            conflict_note = (
                                f"[FINANCIAL RECONCILIATION REQUIRED - CONFLICTING GATEWAY SUCCESS]: "
                                f"Late gateway webhook confirmed success ({gateway_refund_id or event_id}), "
                                f"but refund was previously {locked_rfnd.status} and replacement refund or balance limit "
                                f"detected (other succeeded: {ord_target.currency} {other_succeeded_total}, order total: {ord_target.currency} {ord_target.total_amount}). "
                                f"Status preserved as {locked_rfnd.status} to prevent duplicate payout."
                            )
                            locked_rfnd.notes = f"{locked_rfnd.notes}\n{conflict_note}".strip()
                            locked_rfnd.save(update_fields=['gateway_refund_id', 'notes', 'updated_at'])

                            # Record genuine gateway outcome in immutable payment transaction ledger with conflict flag
                            PaymentTransaction.objects.create(
                                order=ord_target,
                                transaction_type=PaymentTransaction.TransactionTypeChoices.REFUND,
                                provider=p_name,
                                amount=locked_rfnd.amount,
                                currency=locked_rfnd.currency,
                                status=PaymentTransaction.StatusChoices.SUCCESS,
                                provider_transaction_id=gateway_refund_id or locked_rfnd.gateway_refund_id or locked_rfnd.refund_number,
                                provider_order_id=ord_target.payment_reference or '',
                                idempotency_key=f"conflict_{event_id}_{locked_rfnd.refund_number}",
                                error_message=f"CONFLICT: Late gateway success for {locked_rfnd.status} refund. Flagged for financial reconciliation.",
                                raw_response={
                                    "conflict": True,
                                    "conflict_reason": conflict_reason,
                                    "manual_reconciliation_required": True,
                                    "original_refund_status": locked_rfnd.status,
                                    "gateway_refund_id": gateway_refund_id,
                                    "other_refunded_total": str(other_succeeded_total),
                                    "order_total": str(ord_target.total_amount),
                                    "payload": payload,
                                },
                            )

                            record_audit_entry(
                                event_type="marketplace.refund.webhook_conflict",
                                action="marketplace:refund.webhook_conflict",
                                resource_type="Refund",
                                resource_id=str(locked_rfnd.id),
                                actor_id=ord_target.buyer_id,
                                metadata={
                                    "conflict_type": conflict_reason,
                                    "refund_number": locked_rfnd.refund_number,
                                    "order_number": ord_target.order_number,
                                    "amount": str(locked_rfnd.amount),
                                    "currency": locked_rfnd.currency,
                                    "gateway_refund_id": gateway_refund_id,
                                    "current_status": locked_rfnd.status,
                                    "reconciliation_required": True,
                                },
                            )
                            settled_this_request = True
                        elif would_over_refund:
                            logger.error(
                                "Gateway success webhook %s for refund %s would exceed order %s total (%s + %s > %s). Flagged.",
                                event_id, locked_rfnd.refund_number, ord_target.order_number,
                                other_succeeded_total, locked_rfnd.amount, ord_target.total_amount
                            )
                            conflict_note = (
                                f"[FINANCIAL RECONCILIATION REQUIRED - OVER-REFUND BLOCKED]: "
                                f"Gateway webhook confirmed success ({gateway_refund_id or event_id}), "
                                f"but adding {ord_target.currency} {locked_rfnd.amount} would exceed order total "
                                f"{ord_target.currency} {ord_target.total_amount} (already succeeded: {ord_target.currency} {other_succeeded_total})."
                            )
                            locked_rfnd.notes = f"{locked_rfnd.notes}\n{conflict_note}".strip()
                            locked_rfnd.save(update_fields=['notes', 'updated_at'])

                            PaymentTransaction.objects.create(
                                order=ord_target,
                                transaction_type=PaymentTransaction.TransactionTypeChoices.REFUND,
                                provider=p_name,
                                amount=locked_rfnd.amount,
                                currency=locked_rfnd.currency,
                                status=PaymentTransaction.StatusChoices.SUCCESS,
                                provider_transaction_id=gateway_refund_id or locked_rfnd.gateway_refund_id or locked_rfnd.refund_number,
                                provider_order_id=ord_target.payment_reference or '',
                                idempotency_key=f"conflict_{event_id}_{locked_rfnd.refund_number}",
                                error_message="CONFLICT: Gateway success would exceed order total refundable balance.",
                                raw_response={
                                    "conflict": True,
                                    "conflict_reason": "ORDER_BALANCE_EXCEEDED",
                                    "manual_reconciliation_required": True,
                                    "payload": payload,
                                },
                            )
                            record_audit_entry(
                                event_type="marketplace.refund.webhook_conflict",
                                action="marketplace:refund.webhook_conflict",
                                resource_type="Refund",
                                resource_id=str(locked_rfnd.id),
                                actor_id=ord_target.buyer_id,
                                metadata={
                                    "conflict_type": "ORDER_BALANCE_EXCEEDED",
                                    "refund_number": locked_rfnd.refund_number,
                                    "order_number": ord_target.order_number,
                                    "amount": str(locked_rfnd.amount),
                                    "reconciliation_required": True,
                                },
                            )
                            settled_this_request = True
                        else:
                            # Genuine gateway success with no replacement conflicts: transition to SUCCEEDED
                            previous_status = locked_rfnd.status
                            locked_rfnd.status = RefundStatusChoices.SUCCEEDED
                            locked_rfnd.processed_at = timezone.now()
                            locked_rfnd.failure_reason = ''
                            locked_rfnd.next_reconciliation_at = None
                            if is_late_resolution:
                                locked_rfnd.notes = f"{locked_rfnd.notes}\n[Processed via Late Gateway Webhook]: Reconciled from {previous_status} to SUCCEEDED. No replacement conflict detected.".strip()
                            locked_rfnd.save(update_fields=['status', 'gateway_refund_id', 'processed_at', 'failure_reason', 'next_reconciliation_at', 'notes', 'updated_at'])

                            existing_rfnd_tx = PaymentTransaction.objects.filter(
                                order=ord_target,
                                transaction_type=PaymentTransaction.TransactionTypeChoices.REFUND,
                                status=PaymentTransaction.StatusChoices.SUCCESS,
                                provider_transaction_id=gateway_refund_id or locked_rfnd.gateway_refund_id or locked_rfnd.refund_number,
                            ).first()

                            if not existing_rfnd_tx:
                                PaymentTransaction.objects.create(
                                    order=ord_target,
                                    transaction_type=PaymentTransaction.TransactionTypeChoices.REFUND,
                                    provider=p_name,
                                    amount=locked_rfnd.amount,
                                    currency=locked_rfnd.currency,
                                    status=PaymentTransaction.StatusChoices.SUCCESS,
                                    provider_transaction_id=gateway_refund_id or locked_rfnd.gateway_refund_id or locked_rfnd.refund_number,
                                    provider_order_id=ord_target.payment_reference or '',
                                    idempotency_key=locked_rfnd.idempotency_key or locked_rfnd.refund_number,
                                    raw_response=payload,
                                )

                            tot_refunded = ord_target.refunds.filter(
                                status=RefundStatusChoices.SUCCEEDED
                            ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')

                            if tot_refunded >= ord_target.total_amount:
                                ord_target.payment_status = PaymentStatusChoices.REFUNDED
                                ord_target.save(update_fields=['payment_status', 'updated_at'])

                            # Check and execute associated ApprovalRequest if any
                            from apps.identity.models import ApprovalRequest, ApprovalStatusChoices
                            app_req = ApprovalRequest.objects.filter(
                                target_type='Refund',
                                target_id=str(locked_rfnd.id),
                                status=ApprovalStatusChoices.APPROVED,
                            ).first()
                            if app_req:
                                if app_req.execution_error:
                                    app_req.execution_error = ""
                                    app_req.save(update_fields=['execution_error', 'updated_at'])
                                app_req.mark_executed(
                                    executor=locked_rfnd.approved_by,
                                    notes=f"Gateway refund confirmed via webhook event {event_id}."
                                )

                            record_audit_entry(
                                event_type="marketplace.refund.processed",
                                action="marketplace:refund.process",
                                resource_type="Refund",
                                resource_id=str(locked_rfnd.id),
                                actor_id=ord_target.buyer_id,
                                metadata={
                                    "refund_number": locked_rfnd.refund_number,
                                    "order_number": ord_target.order_number,
                                    "amount": str(locked_rfnd.amount),
                                    "currency": locked_rfnd.currency,
                                    "gateway_refund_id": gateway_refund_id or locked_rfnd.gateway_refund_id,
                                    "settlement_source": "late_webhook" if is_late_resolution else "webhook",
                                    "revived_from": previous_status if is_late_resolution else None,
                                    "provider": p_name,
                                },
                            )
                            settled_this_request = True

            elif event_type in (
                'refund.failed',
            ):
                if not refund_obj and locked_order:
                    refund_obj = locked_order.refunds.filter(
                        status__in=[
                            RefundStatusChoices.PENDING,
                            RefundStatusChoices.PROCESSING,
                            RefundStatusChoices.PROCESSING_UNKNOWN,
                        ]
                    ).first()
                if not refund_obj and locked_order:
                    refund_obj = locked_order.refunds.order_by('-created_at').first()

                if refund_obj:
                    locked_rfnd = Refund.objects.select_for_update().get(id=refund_obj.id)
                    if locked_rfnd.status != RefundStatusChoices.SUCCEEDED:
                        locked_rfnd.status = RefundStatusChoices.FAILED
                        err_text = payload.get('payload', {}).get('refund', {}).get('entity', {}).get('error_description') or 'Refund failed at payment gateway'
                        locked_rfnd.failure_reason = err_text
                        locked_rfnd.next_reconciliation_at = None
                        locked_rfnd.save(update_fields=['status', 'failure_reason', 'next_reconciliation_at', 'updated_at'])


                        PaymentTransaction.objects.create(
                            order=locked_order or locked_rfnd.order,
                            transaction_type=PaymentTransaction.TransactionTypeChoices.REFUND,
                            provider=p_name,
                            amount=locked_rfnd.amount,
                            currency=locked_rfnd.currency,
                            status=PaymentTransaction.StatusChoices.FAILED,
                            provider_transaction_id=gateway_refund_id or locked_rfnd.refund_number,
                            error_message=err_text,
                            raw_response=payload,
                        )

                        record_audit_entry(
                            event_type="marketplace.refund.failed",
                            action="marketplace:refund.fail",
                            resource_type="Refund",
                            resource_id=str(locked_rfnd.id),
                            actor_id=(locked_order or locked_rfnd.order).buyer_id,
                            metadata={
                                "refund_number": locked_rfnd.refund_number,
                                "order_number": (locked_order or locked_rfnd.order).order_number,
                                "amount": str(locked_rfnd.amount),
                                "failure_reason": err_text,
                                "settlement_source": "webhook",
                                "provider": p_name,
                            },
                        )

            webhook_record.processed = True
            webhook_record.processed_at = timezone.now()
            webhook_record.save(update_fields=['processed', 'processed_at'])

            # Trigger audit entry and buyer notification ONLY on genuine state settlement
            if settled_this_request and locked_order:
                record_audit_entry(
                    event_type="marketplace.order.payment_verified",
                    action="marketplace:order.payment_verify",
                    resource_type="Order",
                    resource_id=str(locked_order.id),
                    actor_id=locked_order.buyer_id,
                    metadata={
                        "order_number": locked_order.order_number,
                        "provider": p_name,
                        "payment_reference": event_id,
                        "amount": str(locked_order.total_amount),
                        "currency": locked_order.currency,
                        "settlement_source": "webhook",
                    },
                )

        return True, 200, {
            "status": "success",
            "event_id": event_id,
            "event_type": event_type,
            "order_number": order.order_number if order else None,
            "settled": settled_this_request,
        }

    @classmethod
    def update_cod_collection(
        cls,
        order: Order,
        actor: Any,
        target_status: str,
        notes: str = '',
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Updates the Cash on Delivery collection state.
        Restricted to operations staff, delivery agents, or admin roles.
        """
        if order.payment_method != PaymentMethodChoices.COD:
            return False, f"Order {order.order_number} is an online payment order, not Cash on Delivery.", {}

        # Permission check
        is_authorized = (
            actor.is_staff
            or actor.is_superuser
            or actor.has_role('STAFF')
            or actor.has_role('ADMIN')
            or actor.has_permission('finance.payout')
        )
        if not is_authorized:
            return False, "Permission denied: Only authorized operations staff can update COD collection status.", {}

        target = target_status.strip().upper()
        valid_targets = [
            CODCollectionStatusChoices.AWAITING_COLLECTION,
            CODCollectionStatusChoices.COLLECTED,
            CODCollectionStatusChoices.FAILED_COLLECTION,
            CODCollectionStatusChoices.CANCELLED,
        ]
        if target not in valid_targets:
            return False, f"Invalid COD collection status '{target}'. Permitted: {valid_targets}.", {}

        with transaction.atomic():
            old_cod_status = order.cod_collection_status
            order.cod_collection_status = target
            order.cod_collection_notes = notes

            if target == CODCollectionStatusChoices.COLLECTED:
                order.payment_status = PaymentStatusChoices.PAID
                order.paid_at = timezone.now()
                order.cod_collected_at = timezone.now()
                order.cod_collected_by = actor

                PaymentTransaction.objects.create(
                    order=order,
                    transaction_type=PaymentTransaction.TransactionTypeChoices.COD_COLLECTION,
                    provider="COD",
                    amount=order.total_amount,
                    currency=order.currency,
                    status=PaymentTransaction.StatusChoices.SUCCESS,
                    error_message=f"Collected by {actor.email}. Notes: {notes}",
                )

            elif target == CODCollectionStatusChoices.FAILED_COLLECTION:
                PaymentTransaction.objects.create(
                    order=order,
                    transaction_type=PaymentTransaction.TransactionTypeChoices.COD_COLLECTION,
                    provider="COD",
                    amount=order.total_amount,
                    currency=order.currency,
                    status=PaymentTransaction.StatusChoices.FAILED,
                    error_message=f"Collection failed. Notes: {notes}",
                )

            elif target == CODCollectionStatusChoices.CANCELLED:
                order.payment_status = PaymentStatusChoices.CANCELLED

            order.save(update_fields=[
                'cod_collection_status',
                'cod_collection_notes',
                'payment_status',
                'paid_at',
                'cod_collected_at',
                'cod_collected_by',
                'updated_at',
            ])

            record_audit_entry(
                event_type="marketplace.order.cod_collection_updated",
                action="marketplace:order.cod_collection",
                resource_type="Order",
                resource_id=str(order.id),
                actor_id=actor.id,
                metadata={
                    "order_number": order.order_number,
                    "previous_cod_status": old_cod_status,
                    "new_cod_status": target,
                    "notes": notes,
                },
            )

        return True, f"COD collection status updated to '{target}'.", {
            "order_number": order.order_number,
            "cod_collection_status": order.cod_collection_status,
            "payment_status": order.payment_status,
        }
