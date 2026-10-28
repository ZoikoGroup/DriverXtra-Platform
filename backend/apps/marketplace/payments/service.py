import logging
from decimal import Decimal
from typing import Dict, Any, List, Tuple, Optional
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from apps.marketplace.models import (
    Order,
    OrderStatusChoices,
    PaymentMethodChoices,
    PaymentStatusChoices,
    CODCollectionStatusChoices,
    PaymentTransaction,
    PaymentWebhookEvent,
    StockMovementReasonChoices,
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
    def get_provider_for_order(cls, order: Order):
        """Resolves the authoritative payment provider based on order currency and country."""
        country_code = cls.normalize_country_code(order.shipping_country)
        if order.currency == 'INR' or country_code == 'IN':
            return RazorpayPaymentProvider()
        elif order.currency == 'GBP' or country_code == 'GB':
            return StripePaymentProvider()
        else:
            # Default to Stripe for international currency
            return StripePaymentProvider()

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
        if country_code == 'IN' or currency == 'INR':
            methods.append({
                "code": PaymentMethodChoices.ONLINE,
                "provider": "RAZORPAY",
                "name": "Online Payment (UPI, Cards, NetBanking)",
                "currency": "INR",
                "is_available": True,
                "description": "Secure instant checkout via Razorpay supporting all Indian banks and UPI.",
            })
        else:
            methods.append({
                "code": PaymentMethodChoices.ONLINE,
                "provider": "STRIPE",
                "name": "Card Payment (Stripe / Apple Pay / Google Pay)",
                "currency": "GBP",
                "is_available": True,
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
            PaymentTransaction.objects.create(
                order=order,
                transaction_type=PaymentTransaction.TransactionTypeChoices.PAYMENT,
                provider=provider.provider_name,
                amount=order.total_amount,
                currency=order.currency,
                status=PaymentTransaction.StatusChoices.PENDING,
                provider_order_id=session_data.get('provider_order_id', ''),
                idempotency_key=order.idempotency_key,
                raw_response=session_data,
            )
            if not order.payment_reference:
                order.payment_reference = session_data.get('provider_order_id', '')
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

        if order.payment_status == PaymentStatusChoices.PAID:
            return True, order.payment_reference, {
                "message": "Order is already marked as paid.",
                "already_paid": True,
            }

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

        # Locate associated order
        order = None
        order_number = None

        if p_name == 'RAZORPAY':
            # Razorpay order payload inspection
            payload_data = payload.get('payload', {})
            order_entity = payload_data.get('order', {}).get('entity', {})
            payment_entity = payload_data.get('payment', {}).get('entity', {})

            razorpay_order_id = order_entity.get('id') or payment_entity.get('order_id')
            notes = order_entity.get('notes') or payment_entity.get('notes') or {}
            order_number = notes.get('order_number')

            if order_number:
                order = Order.objects.filter(order_number=order_number).first()
            if not order and razorpay_order_id:
                order = Order.objects.filter(payment_reference=razorpay_order_id).first()

        elif p_name == 'STRIPE':
            data_obj = payload.get('data', {}).get('object', {})
            metadata = data_obj.get('metadata', {})
            order_number = metadata.get('order_number')
            pi_id = data_obj.get('id')

            if order_number:
                order = Order.objects.filter(order_number=order_number).first()
            if not order and pi_id:
                order = Order.objects.filter(payment_reference=pi_id).first()

        with transaction.atomic():
            webhook_record, _ = PaymentWebhookEvent.objects.get_or_create(
                provider=p_name,
                event_id=event_id,
                defaults={
                    "event_type": event_type or "unknown",
                    "order": order,
                    "payload": payload,
                },
            )

            # Process Success Event
            if event_type in (
                'payment_intent.succeeded',
                'order.paid',
                'payment.captured',
                'checkout.session.completed',
            ):
                if order and order.payment_status != PaymentStatusChoices.PAID:
                    order.payment_status = PaymentStatusChoices.PAID
                    order.paid_at = timezone.now()
                    if order.status == OrderStatusChoices.PENDING_CONFIRMATION:
                        order.status = OrderStatusChoices.CONFIRMED
                    order.save(update_fields=['payment_status', 'paid_at', 'status', 'updated_at'])

                    PaymentTransaction.objects.create(
                        order=order,
                        transaction_type=PaymentTransaction.TransactionTypeChoices.PAYMENT,
                        provider=p_name,
                        amount=order.total_amount,
                        currency=order.currency,
                        status=PaymentTransaction.StatusChoices.SUCCESS,
                        provider_transaction_id=event_id,
                        provider_order_id=order.payment_reference,
                        raw_response=payload,
                    )

            # Process Failure Event
            elif event_type in (
                'payment_intent.payment_failed',
                'payment.failed',
                'charge.failed',
            ):
                if order and order.payment_status != PaymentStatusChoices.PAID:
                    order.payment_status = PaymentStatusChoices.FAILED
                    order.save(update_fields=['payment_status', 'updated_at'])

                    PaymentTransaction.objects.create(
                        order=order,
                        transaction_type=PaymentTransaction.TransactionTypeChoices.PAYMENT,
                        provider=p_name,
                        amount=order.total_amount,
                        currency=order.currency,
                        status=PaymentTransaction.StatusChoices.FAILED,
                        provider_transaction_id=event_id,
                        provider_order_id=order.payment_reference,
                        raw_response=payload,
                    )

            webhook_record.processed = True
            webhook_record.processed_at = timezone.now()
            webhook_record.save(update_fields=['processed', 'processed_at'])

        return True, 200, {
            "status": "success",
            "event_id": event_id,
            "event_type": event_type,
            "order_number": order.order_number if order else None,
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
