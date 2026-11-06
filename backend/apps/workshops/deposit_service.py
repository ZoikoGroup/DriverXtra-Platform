import logging
from decimal import Decimal
from typing import Dict, Any, Tuple, Optional
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone

from apps.identity.models import User
from apps.marketplace.payments.base import BasePaymentProvider
from apps.marketplace.payments.razorpay_provider import RazorpayPaymentProvider
from apps.marketplace.payments.stripe_provider import StripePaymentProvider
from apps.marketplace.payments.service import PaymentService
from apps.workshops.models import (
    WorkshopQuotation,
    WorkshopBooking,
    QuotationStatusChoices,
    DepositStatusChoices,
    WorkshopDepositWebhookEvent,
)
from platform_core.audit.writer import record_audit_entry
from apps.notifications.services import create_notification

logger = logging.getLogger(__name__)


class QuotationDepositAdapter:
    """
    Adapter presenting a WorkshopQuotation deposit obligation
    as an order-like entity compatible with BasePaymentProvider implementations
    (RazorpayPaymentProvider and StripePaymentProvider).
    """
    def __init__(self, quotation: WorkshopQuotation, buyer: User):
        self.id = quotation.id
        self.order_number = f"DEP-{quotation.quotation_number}"
        self.total_amount = quotation.deposit_amount
        self.currency = quotation.currency
        self.buyer = buyer
        self.payment_reference = quotation.deposit_order_id
        self.shipping_name = (
            buyer.full_name
            if hasattr(buyer, 'full_name') and buyer.full_name
            else (buyer.get_full_name() if hasattr(buyer, 'get_full_name') else '')
            or getattr(buyer, 'username', '')
            or 'Valued Customer'
        )
        self.shipping_phone = getattr(buyer, 'phone_number', '') or ''
        self.shipping_country = getattr(quotation.booking.workshop, 'country', 'GB') or 'GB'


class WorkshopDepositPaymentService:
    """
    Authoritative orchestration service for workshop quotation deposit payments.
    Integrates directly with DriverXtra payment infrastructure (Razorpay for INR, Stripe for GBP),
    cryptographic HMAC signature verification, idempotent webhooks, and atomic booking confirmation.
    """

    @classmethod
    def get_provider(cls, quotation: WorkshopQuotation, preferred_provider: Optional[str] = None) -> BasePaymentProvider:
        """
        Resolves payment gateway provider for quotation deposit based on preference or currency/country.
        """
        if preferred_provider:
            p_clean = preferred_provider.strip().upper()
            if p_clean == 'RAZORPAY':
                return RazorpayPaymentProvider()
            elif p_clean == 'STRIPE':
                return StripePaymentProvider()

        workshop = getattr(quotation.booking, 'workshop', None)
        country = getattr(workshop, 'country', None) if workshop else None
        return PaymentService.get_provider_for_currency_and_country(quotation.currency, country)

    @classmethod
    def create_deposit_session(
        cls,
        quotation: WorkshopQuotation,
        buyer: User,
        preferred_provider: Optional[str] = None,
        return_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Initiates an authoritative payment session for a workshop quotation deposit.
        Validates quotation eligibility, creates order in payment gateway (Razorpay/Stripe),
        and records deposit session state on the quotation atomically.
        """
        if quotation.booking.buyer_id != buyer.id:
            raise DjangoValidationError("Only the buyer who booked this service can initiate deposit payment.")

        if quotation.deposit_status == DepositStatusChoices.PAID:
            raise DjangoValidationError(
                f"Deposit for quotation #{quotation.quotation_number} has already been paid."
            )

        if quotation.status != QuotationStatusChoices.ISSUED:
            raise DjangoValidationError(
                f"Quotation #{quotation.quotation_number} is in '{quotation.status}' status (must be ISSUED)."
            )

        if not quotation.requires_deposit:
            raise DjangoValidationError(
                f"Quotation #{quotation.quotation_number} does not require an upfront deposit."
            )

        if quotation.deposit_amount <= Decimal('0.00'):
            raise DjangoValidationError("Deposit amount must be greater than zero.")

        provider = cls.get_provider(quotation, preferred_provider=preferred_provider)
        adapter = QuotationDepositAdapter(quotation, buyer)

        # Call payment gateway provider to create order/session
        session = provider.create_payment_session(
            order=adapter,
            return_url=return_url,
            cancel_url=cancel_url,
        )
        if return_url and 'return_url' not in session:
            session['return_url'] = return_url
        if cancel_url and 'cancel_url' not in session:
            session['cancel_url'] = cancel_url

        provider_order_id = session.get('provider_order_id', '')

        with transaction.atomic():
            locked_q = WorkshopQuotation.objects.select_for_update().get(id=quotation.id)
            locked_q.deposit_order_id = provider_order_id
            locked_q.deposit_provider = provider.provider_name
            locked_q.deposit_status = DepositStatusChoices.PROCESSING
            locked_q.save(update_fields=['deposit_order_id', 'deposit_provider', 'deposit_status', 'updated_at'])

            record_audit_entry(
                event_type="workshop.quotation.deposit_session_created",
                action="workshop:quotation.deposit_session_create",
                resource_type="WorkshopQuotation",
                resource_id=str(locked_q.id),
                actor_id=buyer.id,
                metadata={
                    "quotation_number": locked_q.quotation_number,
                    "booking_number": locked_q.booking.booking_number,
                    "provider": provider.provider_name,
                    "provider_order_id": provider_order_id,
                    "deposit_amount": str(locked_q.deposit_amount),
                    "currency": locked_q.currency,
                },
            )

        return {
            "status": "success",
            "quotation_id": str(quotation.id),
            "quotation_number": quotation.quotation_number,
            "deposit_amount": str(quotation.deposit_amount),
            "total_amount": str(quotation.total_amount),
            "currency": quotation.currency,
            "deposit_status": DepositStatusChoices.PROCESSING,
            "payment_session": session,
        }

    @classmethod
    def verify_deposit_payment(
        cls,
        quotation_id: Any,
        payload: Dict[str, Any],
        actor: User,
        preferred_provider: Optional[str] = None,
    ) -> WorkshopQuotation:
        """
        Cryptographically verifies payment signature (Razorpay HMAC-SHA256 or Stripe PaymentIntent),
        updates deposit state to PAID, marks quotation as ACCEPTED, confirms booking,
        and triggers WorkOrder creation.
        """
        from apps.workshops.services import QuotationService

        # Initial validation and verification check
        quotation = (
            WorkshopQuotation.objects.select_related('booking', 'booking__buyer', 'booking__workshop', 'booking__workshop__organisation')
            .get(id=quotation_id)
        )

        # Idempotency: If already verified and paid, return gracefully without duplicate operations
        if quotation.deposit_status == DepositStatusChoices.PAID:
            logger.info(
                "Deposit for quotation %s already verified and marked PAID. Returning idempotent state.",
                quotation.quotation_number,
            )
            return quotation

        # Verify buyer ownership
        if quotation.booking.buyer_id != actor.id:
            raise DjangoValidationError("Only the customer who booked this appointment can verify deposit payment.")

        if quotation.status != QuotationStatusChoices.ISSUED:
            raise DjangoValidationError(
                f"Quotation #{quotation.quotation_number} cannot be verified in '{quotation.status}' status (must be ISSUED)."
            )

        if not quotation.requires_deposit:
            raise DjangoValidationError("This quotation does not require a deposit payment.")

        # Validate matching active order session if razorpay_order_id provided
        client_order_id = (
            payload.get('razorpay_order_id')
            or payload.get('payment_intent_id')
            or payload.get('stripe_payment_intent_id')
            or ''
        ).strip()

        if quotation.deposit_order_id and client_order_id and quotation.deposit_order_id != client_order_id:
            raise DjangoValidationError(
                f"Provided gateway order reference '{client_order_id}' does not match quotation active session '{quotation.deposit_order_id}'."
            )

        provider = cls.get_provider(quotation, preferred_provider=preferred_provider)
        adapter = QuotationDepositAdapter(quotation, actor)

        # Cryptographic signature validation
        is_valid, txn_or_err, extra_details = provider.verify_payment(adapter, payload)
        if not is_valid:
            with transaction.atomic():
                q_failed = WorkshopQuotation.objects.select_for_update().get(id=quotation.id)
                q_failed.deposit_status = DepositStatusChoices.FAILED
                q_failed.save(update_fields=['deposit_status', 'updated_at'])

                record_audit_entry(
                    event_type="workshop.quotation.deposit_failed",
                    action="workshop:quotation.deposit_failed",
                    resource_type="WorkshopQuotation",
                    resource_id=str(q_failed.id),
                    actor_id=actor.id,
                    metadata={
                        "quotation_number": q_failed.quotation_number,
                        "error": txn_or_err,
                        "provider": provider.provider_name,
                        "extra_details": extra_details,
                    },
                )
            raise DjangoValidationError(f"Deposit payment verification failed: {txn_or_err}")

        # Verification successful: atomically transition deposit, quotation, booking, and work order
        with transaction.atomic():
            locked_q = (
                WorkshopQuotation.objects.select_for_update()
                .select_related('booking', 'booking__buyer', 'booking__workshop', 'booking__workshop__organisation')
                .get(id=quotation.id)
            )

            if locked_q.deposit_status == DepositStatusChoices.PAID:
                return locked_q

            transaction_id = txn_or_err
            signature_snapshot = (
                payload.get('razorpay_signature')
                or payload.get('client_secret')
                or ''
            )

            locked_q.deposit_status = DepositStatusChoices.PAID
            locked_q.deposit_transaction_id = transaction_id
            locked_q.deposit_signature = signature_snapshot
            locked_q.deposit_paid_at = timezone.now()
            locked_q.deposit_provider = provider.provider_name
            if client_order_id and not locked_q.deposit_order_id:
                locked_q.deposit_order_id = client_order_id
            locked_q.save(update_fields=[
                'deposit_status',
                'deposit_transaction_id',
                'deposit_signature',
                'deposit_paid_at',
                'deposit_provider',
                'deposit_order_id',
                'updated_at',
            ])

            # Transition quotation to ACCEPTED (which also CONFIRMS booking and creates WorkOrder)
            QuotationService.accept_quotation(quotation=locked_q, buyer=actor)

            # Financial audit entry
            audit = record_audit_entry(
                event_type="workshop.quotation.deposit_paid",
                action="workshop:quotation.deposit_paid",
                resource_type="WorkshopQuotation",
                resource_id=str(quotation.id),
                actor_id=actor.id,
                metadata={
                    "quotation_number": quotation.quotation_number,
                    "booking_number": quotation.booking.booking_number,
                    "deposit_amount": str(quotation.deposit_amount),
                    "total_amount": str(quotation.total_amount),
                    "currency": quotation.currency,
                    "provider": provider.provider_name,
                    "transaction_id": transaction_id,
                },
            )

            # Customer & Workshop notifications
            try:
                if audit:
                    # Notify buyer
                    create_notification(
                        recipient=actor,
                        audit_entry=audit,
                        title=f"Deposit Confirmed #{quotation.quotation_number}",
                        message=f"Your deposit payment of {quotation.currency} {quotation.deposit_amount} for #{quotation.quotation_number} was successfully processed. Your booking is confirmed!",
                        link="/platform?tab=workshops",
                        resource_type="WorkshopQuotation",
                        resource_id=str(quotation.id),
                        event_type="workshop.quotation.deposit_paid",
                    )
                    # Notify workshop owner
                    org_owner = quotation.booking.workshop.organisation.created_by
                    if org_owner:
                        create_notification(
                            recipient=org_owner,
                            audit_entry=audit,
                            title=f"Quotation Deposit Received #{quotation.quotation_number}",
                            message=f"Customer {actor.full_name or actor.email} has paid the upfront deposit of {quotation.currency} {quotation.deposit_amount} for #{quotation.quotation_number}.",
                            link="/platform?tab=workshop_landing",
                            resource_type="WorkshopQuotation",
                            resource_id=str(quotation.id),
                            event_type="workshop.quotation.deposit_paid",
                        )
            except Exception as notify_exc:
                logger.warning("Failed to dispatch deposit payment notifications: %s", notify_exc)

            return quotation

    @classmethod
    def process_deposit_webhook(
        cls,
        provider_name: str,
        request_body: bytes,
        headers: Dict[str, str],
    ) -> Tuple[bool, str]:
        """
        Idempotently processes incoming payment gateway webhook events for workshop deposits.
        Guarantees replay protection using WorkshopDepositWebhookEvent tracking.
        """
        from apps.workshops.services import QuotationService

        p_name = provider_name.strip().upper()
        if p_name == 'RAZORPAY':
            provider: BasePaymentProvider = RazorpayPaymentProvider()
        elif p_name == 'STRIPE':
            provider = StripePaymentProvider()
        else:
            return False, f"Unsupported webhook payment provider '{provider_name}'."

        is_valid, event_id, event_type, payload = provider.verify_webhook(request_body, headers)
        if not is_valid:
            err_msg = payload.get('error', 'Cryptographic signature verification failed.') if isinstance(payload, dict) else 'Signature verification failed.'
            return False, f"Invalid webhook signature: {err_msg}"

        if not event_id:
            return False, "Could not extract authoritative event_id from webhook payload."

        # Idempotent event check
        event_record, created = WorkshopDepositWebhookEvent.objects.get_or_create(
            event_id=event_id,
            defaults={
                'provider': provider.provider_name,
                'event_type': event_type or 'unknown',
                'payload': payload if isinstance(payload, dict) else {},
            },
        )

        if not created and event_record.processed:
            logger.info("Workshop deposit webhook event %s was already processed. Skipping.", event_id)
            return True, f"Webhook event {event_id} already processed (idempotent)."

        # Extract gateway order reference and payment reference
        order_id = ''
        payment_id = ''

        if provider.provider_name == 'RAZORPAY':
            entity = payload.get('payload', {}).get('payment', {}).get('entity', {})
            order_id = entity.get('order_id') or payload.get('payload', {}).get('order', {}).get('entity', {}).get('id') or ''
            payment_id = entity.get('id', '')
        elif provider.provider_name == 'STRIPE':
            data_obj = payload.get('data', {}).get('object', {})
            order_id = data_obj.get('id', '')
            payment_id = data_obj.get('id', '')

        quotation = None
        if order_id:
            quotation = WorkshopQuotation.objects.filter(deposit_order_id=order_id).select_related(
                'booking', 'booking__buyer', 'booking__workshop', 'booking__workshop__organisation'
            ).first()

        if quotation:
            event_record.quotation = quotation

            # Handle payment capture / success
            if event_type in ('payment.captured', 'order.paid', 'payment_intent.succeeded'):
                with transaction.atomic():
                    locked_q = WorkshopQuotation.objects.select_for_update().select_related(
                        'booking', 'booking__buyer', 'booking__workshop', 'booking__workshop__organisation'
                    ).get(id=quotation.id)

                    if locked_q.deposit_status != DepositStatusChoices.PAID:
                        locked_q.deposit_status = DepositStatusChoices.PAID
                        locked_q.deposit_transaction_id = payment_id or locked_q.deposit_transaction_id
                        locked_q.deposit_paid_at = timezone.now()
                        locked_q.save(update_fields=['deposit_status', 'deposit_transaction_id', 'deposit_paid_at', 'updated_at'])

                        # Automatically accept quotation
                        QuotationService.accept_quotation(quotation=locked_q, buyer=locked_q.booking.buyer)

                        record_audit_entry(
                            event_type="workshop.quotation.deposit_paid",
                            action="workshop:quotation.deposit_paid",
                            resource_type="WorkshopQuotation",
                            resource_id=str(locked_q.id),
                            actor_id=locked_q.booking.buyer_id,
                            metadata={
                                "quotation_number": locked_q.quotation_number,
                                "deposit_amount": str(locked_q.deposit_amount),
                                "currency": locked_q.currency,
                                "webhook_event_id": event_id,
                                "provider": provider.provider_name,
                            },
                        )
            elif event_type in ('payment.failed', 'payment_intent.payment_failed'):
                with transaction.atomic():
                    locked_q = WorkshopQuotation.objects.select_for_update().get(id=quotation.id)
                    if locked_q.deposit_status != DepositStatusChoices.PAID:
                        locked_q.deposit_status = DepositStatusChoices.FAILED
                        locked_q.save(update_fields=['deposit_status', 'updated_at'])

        event_record.processed = True
        event_record.save(update_fields=['quotation', 'processed', 'updated_at'])

        return True, f"Webhook {event_id} processed successfully."
