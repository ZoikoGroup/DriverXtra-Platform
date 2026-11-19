import logging
from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta
from typing import Dict, Any, Tuple, Optional, List
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction, models
from django.utils import timezone

from apps.identity.models import User
from apps.marketplace.payments.base import BasePaymentProvider
from apps.marketplace.payments.razorpay_provider import RazorpayPaymentProvider
from apps.marketplace.payments.stripe_provider import StripePaymentProvider
from apps.marketplace.payments.service import PaymentService
from apps.workshops.models import (
    WorkshopBooking,
    WorkshopQuotation,
    WorkOrder,
    WorkOrderPayment,
    WorkshopRefund,
    BookingStatusChoices,
    QuotationStatusChoices,
    DepositStatusChoices,
    WorkOrderStatusChoices,
    WorkOrderSettlementStatusChoices,
    WorkOrderPaymentStatusChoices,
    WorkOrderPaymentTypeChoices,
    WorkshopRefundStatusChoices,
)
from platform_core.audit.writer import record_audit_entry
from apps.notifications.services import create_notification

logger = logging.getLogger(__name__)


class WorkshopRefundService:
    """
    Authoritative orchestration service for workshop booking cancellations and automatic refunds.
    Supports Razorpay (INR) and Stripe (GBP), deterministic idempotency keys,
    double-refund prevention, PROCESSING_UNKNOWN gateway timeout handling,
    and inquiry-based reconciliation.
    """

    @classmethod
    def get_provider_for_currency(cls, currency: str, preferred_provider: Optional[str] = None) -> BasePaymentProvider:
        """
        Resolves payment gateway provider strictly compatible with currency.
        INR -> Razorpay
        GBP / Other -> Stripe
        """
        c_clean = (currency or '').strip().upper()
        if c_clean == 'INR':
            return RazorpayPaymentProvider()
        elif c_clean == 'GBP':
            return StripePaymentProvider()

        if preferred_provider:
            p_clean = preferred_provider.strip().upper()
            if p_clean == 'RAZORPAY':
                return RazorpayPaymentProvider()
            elif p_clean == 'STRIPE':
                return StripePaymentProvider()

        return StripePaymentProvider()

    @classmethod
    def calculate_refundable_amount(cls, booking: WorkshopBooking) -> Dict[str, Any]:
        """
        Calculates authoritative financial standing and refundable balance for a booking:
        - Accurately accounts for deposits, balance payments, and previous refunds.
        - Strictly prevents double-counting deposits (if WorkOrderPayment DEPOSIT exists, quotation deposit is excluded).
        - Subtracts exact prior partial or full refunds from WorkshopRefund (SUCCEEDED, PROCESSING, PROCESSING_UNKNOWN).
        - Handles legacy REFUNDED status safely without double-deduction when WorkshopRefund records exist.
        - Computes remaining unrefunded balance per payment/deposit and guarantees that net refundable never exceeds
          unrefunded verified collected payments.
        """
        work_order = getattr(booking, 'work_order', None)
        currency = (booking.workshop.currency or 'GBP').upper()

        deposit_collected = Decimal('0.00')
        deposit_already_refunded = Decimal('0.00')
        balance_collected = Decimal('0.00')
        balance_already_refunded = Decimal('0.00')

        refundable_deposits: List[Tuple[WorkshopQuotation, Decimal]] = []
        refundable_payments: List[Tuple[WorkOrderPayment, Decimal]] = []

        # Query all active or completed workshop refunds for this booking (excluding FAILED and CANCELLED)
        active_refund_statuses = [
            WorkshopRefundStatusChoices.SUCCEEDED,
            WorkshopRefundStatusChoices.PROCESSING,
            WorkshopRefundStatusChoices.PROCESSING_UNKNOWN,
            WorkshopRefundStatusChoices.PENDING,
        ]
        existing_booking_refunds = WorkshopRefund.objects.filter(
            booking=booking,
            status__in=active_refund_statuses,
        )

        # 1. Inspect quotation deposit
        has_wop_deposit = False
        if work_order:
            has_wop_deposit = work_order.payments.filter(
                payment_type=WorkOrderPaymentTypeChoices.DEPOSIT,
            ).exists()

        if not has_wop_deposit:
            # Check quotation deposits directly
            quotations = booking.quotations.all()
            for q in quotations:
                if q.currency:
                    currency = q.currency.upper()
                q_amt = (q.deposit_amount or Decimal('0.00')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                if q.deposit_status in (DepositStatusChoices.PAID, DepositStatusChoices.REFUNDED) and q_amt > Decimal('0.00'):
                    deposit_collected += q_amt

                    # Determine prior refunds for this quotation from WorkshopRefund
                    q_rfnds = existing_booking_refunds.filter(quotation=q)
                    if q_rfnds.exists():
                        q_refunded = (q_rfnds.aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    else:
                        # Legacy fallback: if deposit_status is REFUNDED and no WorkshopRefund row exists
                        q_refunded = q_amt if q.deposit_status == DepositStatusChoices.REFUNDED else Decimal('0.00')

                    deposit_already_refunded += q_refunded
                    q_remaining = max(Decimal('0.00'), q_amt - q_refunded).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

                    if q.deposit_status == DepositStatusChoices.PAID and q_remaining > Decimal('0.00'):
                        refundable_deposits.append((q, q_remaining))

        # 2. Inspect WorkOrderPayments
        if work_order:
            if work_order.quotation and work_order.quotation.currency:
                currency = work_order.quotation.currency.upper()

            wops = list(work_order.payments.all())
            for p in wops:
                if p.currency:
                    currency = p.currency.upper()
                p_amt = (p.amount or Decimal('0.00')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

                # Only evaluate verified collected or previously refunded payments
                if p.status in (WorkOrderPaymentStatusChoices.SUCCESS, WorkOrderPaymentStatusChoices.REFUNDED) and p_amt > Decimal('0.00'):
                    is_deposit = (p.payment_type == WorkOrderPaymentTypeChoices.DEPOSIT)
                    if is_deposit:
                        deposit_collected += p_amt
                    else:
                        balance_collected += p_amt

                    # Determine prior refunds for this payment from WorkshopRefund
                    p_rfnds = existing_booking_refunds.filter(work_order_payment=p)
                    if p_rfnds.exists():
                        p_refunded = (p_rfnds.aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    else:
                        # Legacy fallback: if payment status is REFUNDED and no WorkshopRefund row exists
                        p_refunded = p_amt if p.status == WorkOrderPaymentStatusChoices.REFUNDED else Decimal('0.00')

                    if is_deposit:
                        deposit_already_refunded += p_refunded
                    else:
                        balance_already_refunded += p_refunded

                    p_remaining = max(Decimal('0.00'), p_amt - p_refunded).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

                    if p_remaining > Decimal('0.00'):
                        refundable_payments.append((p, p_remaining))

        total_collected = (deposit_collected + balance_collected).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        total_already_refunded = (deposit_already_refunded + balance_already_refunded).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        net_refundable = max(Decimal('0.00'), total_collected - total_already_refunded).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        return {
            "deposit_collected": str(deposit_collected),
            "deposit_already_refunded": str(deposit_already_refunded),
            "balance_collected": str(balance_collected),
            "balance_already_refunded": str(balance_already_refunded),
            "total_collected": str(total_collected),
            "total_already_refunded": str(total_already_refunded),
            "refundable_amount": str(net_refundable),
            "currency": currency,
            "refundable_deposits": refundable_deposits,
            "refundable_payments": refundable_payments,
        }

    @classmethod
    def process_booking_cancellation_refunds(
        cls,
        booking: WorkshopBooking,
        reason: str,
        actor: User,
    ) -> WorkshopBooking:
        """
        Atomically cancels an eligible WorkshopBooking, safely terminates associated WorkOrder,
        and dispatches automated refunds for any recorded unrefunded payments.
        """
        if not reason or not reason.strip():
            raise DjangoValidationError("A cancellation reason is required.")

        clean_reason = reason.strip()

        # Enforce permission: Buyer, workshop staff, or platform admin
        is_owner = (actor.id == booking.buyer_id)
        is_staff = getattr(actor, 'is_staff', False) or getattr(actor, 'is_superuser', False)
        if not is_owner and not is_staff:
            org = getattr(booking.workshop, 'organisation', None)
            is_org_member = False
            if org and hasattr(org, 'memberships'):
                is_org_member = org.memberships.filter(user=actor, is_active=True).exists()
            if not is_org_member:
                raise DjangoValidationError("You do not have permission to cancel this booking.")

        created_refund_jobs: List[Tuple[WorkshopRefund, str, Any]] = []

        with transaction.atomic():
            locked_booking = (
                WorkshopBooking.objects.select_for_update()
                .select_related('workshop', 'workshop__organisation', 'buyer', 'vehicle')
                .get(id=booking.id)
            )

            # Cancellation Eligibility
            if locked_booking.status == BookingStatusChoices.CANCELLED:
                raise DjangoValidationError("Booking is already cancelled.")

            if locked_booking.status == BookingStatusChoices.REJECTED:
                raise DjangoValidationError("Cannot cancel a booking that has already been rejected.")

            # Validate WorkOrder status if present
            work_order = getattr(locked_booking, 'work_order', None)
            locked_wo: Optional[WorkOrder] = None
            if work_order:
                locked_wo = WorkOrder.objects.select_for_update().get(id=work_order.id)
                if locked_wo.status == WorkOrderStatusChoices.COMPLETED:
                    raise DjangoValidationError("Cannot cancel booking because the work order has already been completed.")

            # Calculate refundable items
            financial_info = cls.calculate_refundable_amount(locked_booking)
            refundable_amount = Decimal(financial_info["refundable_amount"])
            currency = financial_info["currency"]

            # Safe cancellation behavior for active work order:
            if locked_wo:
                locked_wo.status = WorkOrderStatusChoices.CANCELLED
                locked_wo.cancellation_reason = clean_reason
                locked_wo.settlement_status = WorkOrderSettlementStatusChoices.UNPAID
                locked_wo.save(update_fields=['status', 'cancellation_reason', 'settlement_status', 'updated_at'])

                # Automatically restock any consumed parts
                import math
                from apps.marketplace.models import SparePartListing, StockMovement, StockMovementReasonChoices

                for pu in locked_wo.parts_used.filter(is_stock_deducted=True, inventory_item__isnull=False).select_related('inventory_item'):
                    listing = SparePartListing.objects.select_for_update().filter(id=pu.inventory_item_id).first()
                    if listing:
                        qty_restore = max(1, int(math.ceil(pu.quantity)))
                        listing.stock_quantity += qty_restore
                        listing.save(update_fields=['stock_quantity', 'updated_at'])

                        StockMovement.objects.create(
                            listing=listing,
                            delta=qty_restore,
                            resulting_quantity=listing.stock_quantity,
                            reason=StockMovementReasonChoices.WORK_ORDER_RESTOCK,
                            actor=actor,
                            note=f"Restocked upon cancellation of booking #{locked_booking.booking_number}",
                        )
                        pu.is_stock_deducted = False
                        pu.save(update_fields=['is_stock_deducted', 'updated_at'])

            # Transition booking to CANCELLED
            locked_booking.status = BookingStatusChoices.CANCELLED
            locked_booking.cancellation_reason = clean_reason
            locked_booking.cancelled_by = actor
            locked_booking.cancelled_at = timezone.now()
            locked_booking.save(update_fields=['status', 'cancellation_reason', 'cancelled_by', 'cancelled_at', 'updated_at'])

            # Create WorkshopRefund records inside atomic transaction
            for q, q_remaining in financial_info["refundable_deposits"]:
                existing_dep_count = WorkshopRefund.objects.filter(quotation=q).count()
                candidate_rfnd_num = f"REF-WB-DEP-{q.quotation_number}" if existing_dep_count == 0 else f"REF-WB-DEP-{q.quotation_number}-{existing_dep_count + 1}"
                seq_idx = existing_dep_count + 1
                while WorkshopRefund.objects.filter(refund_number=candidate_rfnd_num).exists():
                    candidate_rfnd_num = f"REF-WB-DEP-{q.quotation_number}-{seq_idx}"
                    seq_idx += 1
                rfnd_num = candidate_rfnd_num

                target_curr = (q.currency or currency).upper()
                p_provider = 'RAZORPAY' if target_curr == 'INR' else 'STRIPE'
                pay_ref = q.deposit_transaction_id or q.deposit_order_id or ''

                if p_provider.upper() == 'RAZORPAY':
                    idemp_key = RazorpayPaymentProvider.generate_refund_idempotency_key(rfnd_num)
                else:
                    idemp_key = rfnd_num[:40]

                rfnd_record = WorkshopRefund.objects.create(
                    refund_number=rfnd_num,
                    booking=locked_booking,
                    quotation=q,
                    amount=q_remaining,
                    currency=(q.currency or currency).upper(),
                    status=WorkshopRefundStatusChoices.PROCESSING,
                    gateway_provider=p_provider,
                    payment_reference=pay_ref,
                    idempotency_key=idemp_key,
                    reason=f"Cancellation: {clean_reason}"[:255],
                    created_by=actor,
                )
                created_refund_jobs.append((rfnd_record, 'DEPOSIT', q))

            for p, p_remaining in financial_info["refundable_payments"]:
                existing_p_count = WorkshopRefund.objects.filter(work_order_payment=p).count()
                candidate_rfnd_num = f"REF-WB-{p.payment_number}" if existing_p_count == 0 else f"REF-WB-{p.payment_number}-{existing_p_count + 1}"
                seq_idx = existing_p_count + 1
                while WorkshopRefund.objects.filter(refund_number=candidate_rfnd_num).exists():
                    candidate_rfnd_num = f"REF-WB-{p.payment_number}-{seq_idx}"
                    seq_idx += 1
                rfnd_num = candidate_rfnd_num

                target_curr = p.currency.upper()
                p_provider = 'RAZORPAY' if target_curr == 'INR' else 'STRIPE'
                pay_ref = p.provider_payment_id or p.provider_order_id or ''

                if p_provider.upper() == 'RAZORPAY':
                    idemp_key = RazorpayPaymentProvider.generate_refund_idempotency_key(rfnd_num)
                else:
                    idemp_key = rfnd_num[:40]

                rfnd_record = WorkshopRefund.objects.create(
                    refund_number=rfnd_num,
                    booking=locked_booking,
                    work_order=locked_wo,
                    work_order_payment=p,
                    amount=p_remaining,
                    currency=p.currency.upper(),
                    status=WorkshopRefundStatusChoices.PROCESSING,
                    gateway_provider=p_provider,
                    payment_reference=pay_ref,
                    idempotency_key=idemp_key,
                    reason=f"Cancellation: {clean_reason}"[:255],
                    created_by=actor,
                )
                created_refund_jobs.append((rfnd_record, 'WOP', p))

            audit = record_audit_entry(
                event_type="workshop.booking.cancelled",
                action="workshop:booking.cancel",
                resource_type="WorkshopBooking",
                resource_id=str(locked_booking.id),
                actor_id=actor.id,
                metadata={
                    "booking_number": locked_booking.booking_number,
                    "reason": clean_reason,
                    "refundable_amount": str(refundable_amount),
                    "refund_count": len(created_refund_jobs),
                },
            )

            try:
                recipient = locked_booking.workshop.organisation.created_by if actor == locked_booking.buyer else locked_booking.buyer
                if recipient and audit:
                    create_notification(
                        recipient=recipient,
                        audit_entry=audit,
                        title=f"Booking Cancelled #{locked_booking.booking_number}",
                        message=f"Booking #{locked_booking.booking_number} was cancelled by {actor.full_name or actor.email}. Reason: {clean_reason}",
                        link="/platform",
                        resource_type="WorkshopBooking",
                        resource_id=str(locked_booking.id),
                        event_type="workshop.booking.cancelled",
                    )
            except Exception as e:
                logger.warning("Failed to dispatch cancellation notification: %s", e)

        # Gateway Refund Processing (Decoupled from database transaction)
        total_refunded = Decimal('0.00')
        overall_refund_status = "NOT_APPLICABLE" if len(created_refund_jobs) == 0 else "SUCCEEDED"
        refund_details = []

        for rfnd_obj, item_type, target_entity in created_refund_jobs:
            provider = cls.get_provider_for_currency(rfnd_obj.currency, preferred_provider=rfnd_obj.gateway_provider)
            pay_ref = rfnd_obj.payment_reference
            if not pay_ref:
                pay_ref = (
                    f"pay_test_{locked_booking.booking_number}"
                    if rfnd_obj.currency.upper() == 'INR'
                    else f"pi_test_{locked_booking.booking_number}"
                )

            is_timeout_or_ambiguous = False
            try:
                success, ref_id_or_err, extra = provider.issue_refund(
                    payment_reference=pay_ref,
                    amount=rfnd_obj.amount,
                    currency=rfnd_obj.currency,
                    reason=rfnd_obj.reason,
                    refund_number=rfnd_obj.refund_number,
                    notes={
                        "booking_number": locked_booking.booking_number,
                        "refund_number": rfnd_obj.refund_number,
                    },
                )
            except Exception as exc:
                logger.exception("Refund gateway exception for %s: %s", rfnd_obj.refund_number, exc)
                success = False
                ref_id_or_err = f"Payment gateway communication error: {str(exc)}"
                extra = {"error": str(exc), "exception_type": exc.__class__.__name__}
                is_timeout_or_ambiguous = True

            if not success and not is_timeout_or_ambiguous:
                err_lower = (ref_id_or_err or '').lower()
                if any(term in err_lower for term in ['timeout', 'timed out', 'communication error', 'connect', 'bad gateway', '502', '503', '504']):
                    is_timeout_or_ambiguous = True

            with transaction.atomic():
                locked_rfnd = WorkshopRefund.objects.select_for_update().get(id=rfnd_obj.id)
                if success:
                    locked_rfnd.status = WorkshopRefundStatusChoices.SUCCEEDED
                    locked_rfnd.gateway_refund_id = ref_id_or_err
                    locked_rfnd.processed_at = timezone.now()
                    locked_rfnd.failure_reason = ''
                    locked_rfnd.next_reconciliation_at = None
                    locked_rfnd.save(update_fields=['status', 'gateway_refund_id', 'processed_at', 'failure_reason', 'next_reconciliation_at', 'updated_at'])

                    total_refunded += locked_rfnd.amount

                    if item_type == 'DEPOSIT':
                        locked_q = WorkshopQuotation.objects.select_for_update().get(id=target_entity.id)
                        q_refunded_total = WorkshopRefund.objects.filter(
                            quotation=locked_q,
                            status=WorkshopRefundStatusChoices.SUCCEEDED,
                        ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
                        if q_refunded_total >= (locked_q.deposit_amount or Decimal('0.00')):
                            locked_q.deposit_status = DepositStatusChoices.REFUNDED
                            locked_q.save(update_fields=['deposit_status', 'updated_at'])
                    elif item_type == 'WOP':
                        locked_wop = WorkOrderPayment.objects.select_for_update().get(id=target_entity.id)
                        wop_refunded_total = WorkshopRefund.objects.filter(
                            work_order_payment=locked_wop,
                            status=WorkshopRefundStatusChoices.SUCCEEDED,
                        ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
                        if wop_refunded_total >= (locked_wop.amount or Decimal('0.00')):
                            locked_wop.status = WorkOrderPaymentStatusChoices.REFUNDED
                        locked_wop.error_message = f"Refunded via {locked_rfnd.refund_number} (Gateway ref: {ref_id_or_err})"
                        locked_wop.save(update_fields=['status', 'error_message', 'updated_at'])

                    record_audit_entry(
                        event_type="workshop.refund.processed",
                        action="workshop:refund.process",
                        resource_type="WorkshopRefund",
                        resource_id=str(locked_rfnd.id),
                        actor_id=actor.id,
                        metadata={
                            "refund_number": locked_rfnd.refund_number,
                            "booking_number": locked_booking.booking_number,
                            "amount": str(locked_rfnd.amount),
                            "gateway_refund_id": ref_id_or_err,
                            "provider": provider.provider_name,
                        },
                    )

                elif is_timeout_or_ambiguous:
                    locked_rfnd.status = WorkshopRefundStatusChoices.PROCESSING_UNKNOWN
                    locked_rfnd.failure_reason = ref_id_or_err
                    locked_rfnd.reconciliation_attempts = 0
                    locked_rfnd.next_reconciliation_at = timezone.now() + timedelta(minutes=2)
                    locked_rfnd.save(update_fields=['status', 'failure_reason', 'reconciliation_attempts', 'next_reconciliation_at', 'updated_at'])

                    if overall_refund_status == "SUCCEEDED":
                        overall_refund_status = "PROCESSING_UNKNOWN"

                    record_audit_entry(
                        event_type="workshop.refund.gateway_timeout",
                        action="workshop:refund.dispatch",
                        resource_type="WorkshopRefund",
                        resource_id=str(locked_rfnd.id),
                        actor_id=actor.id,
                        metadata={
                            "refund_number": locked_rfnd.refund_number,
                            "booking_number": locked_booking.booking_number,
                            "amount": str(locked_rfnd.amount),
                            "error": ref_id_or_err,
                            "provider": provider.provider_name,
                        },
                    )

                else:
                    locked_rfnd.status = WorkshopRefundStatusChoices.FAILED
                    locked_rfnd.failure_reason = ref_id_or_err
                    locked_rfnd.save(update_fields=['status', 'failure_reason', 'updated_at'])

                    if overall_refund_status in ("SUCCEEDED", "PROCESSING_UNKNOWN"):
                        overall_refund_status = "FAILED"

                    record_audit_entry(
                        event_type="workshop.refund.failed",
                        action="workshop:refund.dispatch",
                        resource_type="WorkshopRefund",
                        resource_id=str(locked_rfnd.id),
                        actor_id=actor.id,
                        metadata={
                            "refund_number": locked_rfnd.refund_number,
                            "booking_number": locked_booking.booking_number,
                            "error": ref_id_or_err,
                            "provider": provider.provider_name,
                        },
                    )

                refund_details.append({
                    "refund_number": locked_rfnd.refund_number,
                    "amount": str(locked_rfnd.amount),
                    "currency": locked_rfnd.currency,
                    "status": locked_rfnd.status,
                    "gateway_refund_id": locked_rfnd.gateway_refund_id,
                    "error": locked_rfnd.failure_reason,
                })

        locked_booking.refund_summary = {
            "refundable_amount": str(refundable_amount),
            "refunded_amount": str(total_refunded),
            "currency": currency,
            "refund_status": overall_refund_status,
            "refund_details": refund_details,
        }

        return locked_booking

    @classmethod
    def reconcile_refund(
        cls,
        refund_id: UUID | str,
        actor: Optional[User] = None,
    ) -> Tuple[WorkshopRefund, str]:
        """
        Authoritatively reconciles an ambiguous or pending WorkshopRefund with the gateway provider.
        Does not issue duplicate refunds; resolves using inquiry.
        """
        with transaction.atomic():
            locked_refund = (
                WorkshopRefund.objects.select_for_update()
                .select_related('booking', 'work_order', 'quotation', 'work_order_payment')
                .get(id=refund_id)
            )

            if locked_refund.status == WorkshopRefundStatusChoices.SUCCEEDED:
                return locked_refund, "ALREADY_SUCCEEDED"

            if locked_refund.status not in (WorkshopRefundStatusChoices.PROCESSING_UNKNOWN, WorkshopRefundStatusChoices.PROCESSING):
                return locked_refund, f"INELIGIBLE_STATUS_{locked_refund.status}"

            provider = cls.get_provider_for_currency(locked_refund.currency, preferred_provider=locked_refund.gateway_provider)
            payment_reference = locked_refund.payment_reference
            if not payment_reference:
                payment_reference = (
                    f"pay_test_{locked_refund.booking.booking_number}"
                    if locked_refund.currency.upper() == 'INR'
                    else f"pi_test_{locked_refund.booking.booking_number}"
                )

            locked_refund.reconciliation_attempts += 1
            locked_refund.last_reconciliation_at = timezone.now()
            locked_refund.save(update_fields=['reconciliation_attempts', 'last_reconciliation_at', 'updated_at'])

            rfnd_num = locked_refund.refund_number
            gw_id = locked_refund.gateway_refund_id

        # External gateway inquiry decoupled from row lock
        try:
            inq_status, ref_id_or_err, extra = provider.inquire_refund(
                payment_reference=payment_reference,
                refund_number=rfnd_num,
                gateway_refund_id=gw_id or None,
            )
        except Exception as exc:
            logger.exception("Inquiry exception for refund %s: %s", rfnd_num, exc)
            inq_status = 'UNKNOWN'
            ref_id_or_err = f"Exception during gateway inquiry: {str(exc)}"
            extra = {"error": str(exc)}

        with transaction.atomic():
            locked_refund = (
                WorkshopRefund.objects.select_for_update()
                .select_related('booking', 'quotation', 'work_order_payment')
                .get(id=refund_id)
            )

            if locked_refund.status == WorkshopRefundStatusChoices.SUCCEEDED:
                return locked_refund, "ALREADY_SUCCEEDED"

            if inq_status == 'SUCCEEDED':
                locked_refund.status = WorkshopRefundStatusChoices.SUCCEEDED
                locked_refund.gateway_refund_id = ref_id_or_err or locked_refund.gateway_refund_id
                locked_refund.processed_at = timezone.now()
                locked_refund.failure_reason = ''
                locked_refund.next_reconciliation_at = None
                locked_refund.save(update_fields=[
                    'status', 'gateway_refund_id', 'processed_at', 'failure_reason', 'next_reconciliation_at', 'updated_at'
                ])

                if locked_refund.quotation:
                    q = WorkshopQuotation.objects.select_for_update().get(id=locked_refund.quotation_id)
                    q_refunded_total = WorkshopRefund.objects.filter(
                        quotation=q,
                        status=WorkshopRefundStatusChoices.SUCCEEDED,
                    ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
                    if q_refunded_total >= (q.deposit_amount or Decimal('0.00')):
                        q.deposit_status = DepositStatusChoices.REFUNDED
                        q.save(update_fields=['deposit_status', 'updated_at'])

                if locked_refund.work_order_payment:
                    p = WorkOrderPayment.objects.select_for_update().get(id=locked_refund.work_order_payment_id)
                    wop_refunded_total = WorkshopRefund.objects.filter(
                        work_order_payment=p,
                        status=WorkshopRefundStatusChoices.SUCCEEDED,
                    ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
                    if wop_refunded_total >= (p.amount or Decimal('0.00')):
                        p.status = WorkOrderPaymentStatusChoices.REFUNDED
                    p.error_message = f"Reconciled refund {locked_refund.refund_number}"
                    p.save(update_fields=['status', 'error_message', 'updated_at'])

                record_audit_entry(
                    event_type="workshop.refund.reconciled_succeeded",
                    action="workshop:refund.reconcile",
                    resource_type="WorkshopRefund",
                    resource_id=str(locked_refund.id),
                    actor_id=actor.id if actor else None,
                    metadata={
                        "refund_number": locked_refund.refund_number,
                        "gateway_refund_id": locked_refund.gateway_refund_id,
                        "status": "SUCCEEDED",
                    },
                )
                return locked_refund, "RECONCILED_SUCCEEDED"

            elif inq_status == 'FAILED':
                locked_refund.status = WorkshopRefundStatusChoices.FAILED
                locked_refund.failure_reason = ref_id_or_err or "Provider reported refund failure during inquiry."
                locked_refund.next_reconciliation_at = None
                locked_refund.save(update_fields=['status', 'failure_reason', 'next_reconciliation_at', 'updated_at'])

                record_audit_entry(
                    event_type="workshop.refund.reconciled_failed",
                    action="workshop:refund.reconcile",
                    resource_type="WorkshopRefund",
                    resource_id=str(locked_refund.id),
                    actor_id=actor.id if actor else None,
                    metadata={
                        "refund_number": locked_refund.refund_number,
                        "error": locked_refund.failure_reason,
                        "status": "FAILED",
                    },
                )
                return locked_refund, "RECONCILED_FAILED"

            else:
                # Bounded exponential backoff: 2min, 4min, 8min, up to 60min
                delay_minutes = min(60, 2 ** min(locked_refund.reconciliation_attempts, 6))
                locked_refund.next_reconciliation_at = timezone.now() + timedelta(minutes=delay_minutes)
                locked_refund.failure_reason = ref_id_or_err or f"Inquiry status: {inq_status}"
                locked_refund.save(update_fields=['next_reconciliation_at', 'failure_reason', 'updated_at'])
                return locked_refund, f"STILL_PENDING_{inq_status}"

    @classmethod
    def reconcile_all_pending_unknown(cls, max_batch: int = 50) -> Dict[str, Any]:
        """
        Reconciles all ambiguous workshop refunds that are due for inquiry.
        """
        now = timezone.now()
        due_refunds = list(
            WorkshopRefund.objects.filter(
                status__in=[WorkshopRefundStatusChoices.PROCESSING_UNKNOWN, WorkshopRefundStatusChoices.PROCESSING],
            ).filter(
                models.Q(next_reconciliation_at__lte=now) | models.Q(next_reconciliation_at__isnull=True)
            ).order_by('created_at')[:max_batch]
        )

        results = {"total": len(due_refunds), "succeeded": 0, "failed": 0, "still_pending": 0}
        for rfnd in due_refunds:
            try:
                _, outcome = cls.reconcile_refund(rfnd.id)
                if outcome == "RECONCILED_SUCCEEDED" or outcome == "ALREADY_SUCCEEDED":
                    results["succeeded"] += 1
                elif outcome == "RECONCILED_FAILED":
                    results["failed"] += 1
                else:
                    results["still_pending"] += 1
            except Exception as e:
                logger.exception("Error reconciling refund %s: %s", rfnd.refund_number, e)
                results["still_pending"] += 1

        return results
