import hashlib
import hmac
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, Tuple, Optional
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction, IntegrityError
from django.db import models
from django.utils import timezone

from apps.identity.models import User
from apps.marketplace.payments.base import BasePaymentProvider
from apps.marketplace.payments.razorpay_provider import RazorpayPaymentProvider
from apps.marketplace.payments.stripe_provider import StripePaymentProvider
from apps.marketplace.payments.service import PaymentService
from apps.workshops.models import (
    WorkOrder,
    WorkOrderStatusChoices,
    WorkOrderSettlementStatusChoices,
    WorkOrderPayment,
    WorkOrderPaymentStatusChoices,
    WorkOrderPaymentTypeChoices,
    WorkOrderInvoice,
    WorkOrderInvoiceStatusChoices,
    WorkshopQuotation,
    DepositStatusChoices,
    ChangeOrderStatusChoices,
    WorkshopSettlementWebhookEvent,
    generate_work_order_payment_number,
    generate_work_order_invoice_number,
)
from platform_core.audit.writer import record_audit_entry
from apps.notifications.services import create_notification

logger = logging.getLogger(__name__)


class WorkOrderPaymentAdapter:
    """
    Adapter presenting a WorkOrder payment obligation as an order-like entity
    compatible with BasePaymentProvider implementations (RazorpayPaymentProvider and StripePaymentProvider).
    """
    def __init__(self, work_order: WorkOrder, buyer: User, amount: Decimal, payment_number: str, payment_reference: str = ''):
        self.id = work_order.id
        self.order_number = payment_number
        self.total_amount = amount
        self.currency = (
            work_order.quotation.currency
            if work_order.quotation and work_order.quotation.currency
            else (getattr(work_order.workshop, 'currency', 'GBP') or 'GBP')
        ).upper()
        self.buyer = buyer
        self.payment_reference = payment_reference
        self.shipping_name = (
            buyer.full_name
            if hasattr(buyer, 'full_name') and buyer.full_name
            else (buyer.get_full_name() if hasattr(buyer, 'get_full_name') else '')
            or getattr(buyer, 'username', '')
            or 'Valued Customer'
        )
        self.shipping_phone = getattr(buyer, 'phone_number', '') or ''
        self.shipping_country = getattr(work_order.workshop, 'country', 'GB') or 'GB'


class WorkOrderSettlementService:
    """
    Authoritative orchestration service for WorkOrder balance settlement and online payments.
    Supports Razorpay (INR) and Stripe (GBP), cryptographic signature verification,
    idempotent retries, partial balance payments, final settlement invoices,
    and Phase 1 late-payment refund protections.
    """

    @classmethod
    def get_provider(cls, work_order: WorkOrder, preferred_provider: Optional[str] = None) -> BasePaymentProvider:
        """
        Resolves payment gateway provider based on preference or currency/country.
        """
        if preferred_provider:
            p_clean = preferred_provider.strip().upper()
            if p_clean == 'RAZORPAY':
                return RazorpayPaymentProvider()
            elif p_clean == 'STRIPE':
                return StripePaymentProvider()

        currency = (
            work_order.quotation.currency
            if work_order.quotation and work_order.quotation.currency
            else (getattr(work_order.workshop, 'currency', 'GBP') or 'GBP')
        ).upper()
        workshop = getattr(work_order, 'workshop', None)
        country = getattr(workshop, 'country', None) if workshop else None
        return PaymentService.get_provider_for_currency_and_country(currency, country)

    @classmethod
    def calculate_outstanding_balance(cls, work_order: WorkOrder) -> Dict[str, Any]:
        """
        Calculates authoritative financial standing for a WorkOrder:
        Outstanding Balance = Original Quotation + Approved Change Orders - Verified Deposits - Verified Balance Payments.
        Never negative. Excludes rejected/pending change orders and unverified payments.
        """
        quotation = work_order.quotation
        original_quote = (
            quotation.total_amount if quotation else Decimal('0.00')
        ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        # Exclude rejected, cancelled, or pending change orders
        approved_change_orders = (
            work_order.change_orders.filter(status=ChangeOrderStatusChoices.APPROVED).aggregate(
                total=models.Sum('additional_amount')
            )['total'] or Decimal('0.00')
        ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        authorized_total = (original_quote + approved_change_orders).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        # 1. Verified deposits: check WorkOrderPayment first; use quotation fallback only if not in WorkOrderPayment
        wop_deposit = (
            work_order.payments.filter(
                payment_type=WorkOrderPaymentTypeChoices.DEPOSIT,
                status=WorkOrderPaymentStatusChoices.SUCCESS,
            ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
        ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        if wop_deposit > Decimal('0.00'):
            deposit_paid = wop_deposit
        elif quotation and getattr(quotation, 'requires_deposit', False) and quotation.deposit_status == DepositStatusChoices.PAID:
            deposit_paid = (quotation.deposit_amount or Decimal('0.00')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        else:
            deposit_paid = Decimal('0.00')

        # 2. Verified balance payments: strictly exclude DEPOSIT payments to prevent double-counting
        balance_paid = (
            work_order.payments.filter(
                status=WorkOrderPaymentStatusChoices.SUCCESS,
            ).exclude(
                payment_type=WorkOrderPaymentTypeChoices.DEPOSIT,
            ).aggregate(
                total=models.Sum('amount')
            )['total'] or Decimal('0.00')
        ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        total_paid = (deposit_paid + balance_paid).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        diff = authorized_total - total_paid
        outstanding_balance = max(Decimal('0.00'), diff).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        currency = (
            quotation.currency
            if quotation and quotation.currency
            else (getattr(work_order.workshop, 'currency', 'GBP') or 'GBP')
        ).upper()

        is_settled = (outstanding_balance == Decimal('0.00'))

        return {
            "original_quotation_amount": str(original_quote),
            "approved_change_orders_amount": str(approved_change_orders),
            "authorized_total_amount": str(authorized_total),
            "deposit_paid_amount": str(deposit_paid),
            "balance_paid_amount": str(balance_paid),
            "total_paid_amount": str(total_paid),
            "outstanding_balance": str(outstanding_balance),
            "is_fully_settled": is_settled,
            "settlement_status": (
                WorkOrderSettlementStatusChoices.FULLY_PAID if is_settled
                else (WorkOrderSettlementStatusChoices.PARTIALLY_PAID if total_paid > Decimal('0.00') else WorkOrderSettlementStatusChoices.UNPAID)
            ),
            "currency": currency,
        }

    @classmethod
    def create_settlement_session(
        cls,
        work_order: WorkOrder,
        buyer: User,
        partial_amount: Optional[Decimal] = None,
        preferred_provider: Optional[str] = None,
        return_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Creates an authoritative payment session for paying the outstanding balance (or partial balance)
        of a WorkOrder. Validates authorization, active balance, creates gateway order, and returns session metadata.
        """
        if work_order.buyer_id != buyer.id:
            raise DjangoValidationError("Only the authorized buyer who owns this work order can initiate payment.")

        if work_order.status == WorkOrderStatusChoices.CANCELLED or getattr(work_order.booking, 'status', None) == 'CANCELLED':
            raise DjangoValidationError(f"Work order #{work_order.work_order_number} is cancelled.")

        balance_info = cls.calculate_outstanding_balance(work_order)
        outstanding = Decimal(balance_info["outstanding_balance"])

        if outstanding <= Decimal('0.00'):
            raise DjangoValidationError(f"Work order #{work_order.work_order_number} has already been fully settled.")

        # Determine charge amount: full outstanding balance or valid partial amount
        if partial_amount is not None:
            partial_dec = Decimal(str(partial_amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            if partial_dec <= Decimal('0.00'):
                raise DjangoValidationError("Payment amount must be greater than zero.")
            if partial_dec > outstanding:
                raise DjangoValidationError(
                    f"Payment amount ({partial_dec}) cannot exceed outstanding balance ({outstanding})."
                )
            charge_amount = partial_dec
            payment_type = WorkOrderPaymentTypeChoices.PARTIAL if charge_amount < outstanding else WorkOrderPaymentTypeChoices.FINAL
        else:
            charge_amount = outstanding
            payment_type = WorkOrderPaymentTypeChoices.FINAL

        currency = balance_info["currency"]
        provider = cls.get_provider(work_order, preferred_provider=preferred_provider)
        payment_number = generate_work_order_payment_number()
        adapter = WorkOrderPaymentAdapter(work_order, buyer, charge_amount, payment_number)

        # Call gateway provider to create order/session
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

        # Record payment intent atomically in ledger
        with transaction.atomic():
            payment = WorkOrderPayment.objects.create(
                work_order=work_order,
                payment_number=payment_number,
                payment_type=payment_type,
                amount=charge_amount,
                currency=currency,
                provider=provider.provider_name,
                status=WorkOrderPaymentStatusChoices.PENDING,
                provider_order_id=provider_order_id,
                created_by=buyer,
                metadata={
                    "session_created_at": timezone.now().isoformat(),
                    "expires_at": session.get("expires_at"),
                    "outstanding_before": str(outstanding),
                },
            )

            record_audit_entry(
                event_type="workshop.work_order.settlement_session_created",
                action="workshop:work_order.settlement_session_create",
                resource_type="WorkOrder",
                resource_id=str(work_order.id),
                actor_id=buyer.id,
                metadata={
                    "work_order_number": work_order.work_order_number,
                    "payment_number": payment_number,
                    "provider": provider.provider_name,
                    "provider_order_id": provider_order_id,
                    "amount": str(charge_amount),
                    "currency": currency,
                    "payment_type": payment_type,
                },
            )

        return {
            "status": "success",
            "work_order_id": str(work_order.id),
            "work_order_number": work_order.work_order_number,
            "payment_number": payment_number,
            "amount": str(charge_amount),
            "outstanding_balance": str(outstanding),
            "currency": currency,
            "payment_session": session,
        }

    @classmethod
    def verify_settlement_payment(
        cls,
        work_order_id: Any,
        payload: Dict[str, Any],
        actor: User,
        preferred_provider: Optional[str] = None,
    ) -> Tuple[WorkOrder, WorkOrderPayment]:
        """
        Cryptographically verifies gateway payment signature (Razorpay HMAC-SHA256 or Stripe PaymentIntent),
        records payment in ledger, updates WorkOrder settlement status, generates final invoice,
        and safely auto-refunds late/duplicate payments.
        """
        work_order = (
            WorkOrder.objects.select_related('quotation', 'workshop', 'booking', 'buyer')
            .get(id=work_order_id)
        )

        if work_order.buyer_id != actor.id and not (actor.is_staff or actor.is_superuser):
            raise DjangoValidationError("Only the authorized buyer can verify payment for this work order.")

        client_payment_id = (
            payload.get('razorpay_payment_id')
            or payload.get('payment_intent_id')
            or payload.get('stripe_payment_intent_id')
            or payload.get('payment_id')
            or ''
        ).strip()

        client_order_id = (
            payload.get('razorpay_order_id')
            or payload.get('provider_order_id')
            or ''
        ).strip()

        # Idempotency: Check if this payment has already been verified and recorded
        if client_payment_id:
            existing_success = work_order.payments.filter(
                provider_payment_id=client_payment_id,
                status=WorkOrderPaymentStatusChoices.SUCCESS,
            ).first()
            if existing_success:
                logger.info(
                    "Payment %s for WorkOrder %s already verified. Returning idempotent state.",
                    client_payment_id,
                    work_order.work_order_number,
                )
                return work_order, existing_success

        provider = cls.get_provider(work_order, preferred_provider=preferred_provider)

        # Match in-flight pending payment record if exists
        pending_payment = None
        if client_order_id:
            pending_payment = work_order.payments.filter(
                provider_order_id=client_order_id,
                status=WorkOrderPaymentStatusChoices.PENDING,
            ).first()

        amount_to_verify = pending_payment.amount if pending_payment else Decimal(str(payload.get('amount') or '0.00'))
        if amount_to_verify <= Decimal('0.00'):
            calc = cls.calculate_outstanding_balance(work_order)
            amount_to_verify = Decimal(calc["outstanding_balance"])

        p_number = pending_payment.payment_number if pending_payment else generate_work_order_payment_number()

        # Session reference for gateway validation matching
        session_ref = ''
        if pending_payment and pending_payment.provider_order_id:
            session_ref = pending_payment.provider_order_id
        elif client_order_id:
            session_ref = client_order_id
        elif client_payment_id and client_payment_id.startswith('pi_'):
            session_ref = client_payment_id

        adapter = WorkOrderPaymentAdapter(work_order, actor, amount_to_verify, p_number, payment_reference=session_ref)

        # Verify cryptographic signature
        is_valid, txn_or_err, extra_details = provider.verify_payment(adapter, payload)
        if not is_valid:
            # Record failed payment atomically without rolling back failure record
            with transaction.atomic():
                failed_payment = pending_payment or WorkOrderPayment(
                    work_order=work_order,
                    payment_number=p_number,
                    amount=amount_to_verify,
                    currency=adapter.currency,
                    provider=provider.provider_name,
                    created_by=actor,
                )
                failed_payment.status = WorkOrderPaymentStatusChoices.FAILED
                failed_payment.error_message = str(txn_or_err)
                failed_payment.provider_order_id = client_order_id
                failed_payment.provider_payment_id = client_payment_id
                failed_payment.save()

                record_audit_entry(
                    event_type="workshop.work_order.settlement_failed",
                    action="workshop:work_order.settlement_failed",
                    resource_type="WorkOrder",
                    resource_id=str(work_order.id),
                    actor_id=actor.id,
                    metadata={
                        "work_order_number": work_order.work_order_number,
                        "payment_number": p_number,
                        "error": str(txn_or_err),
                        "provider": provider.provider_name,
                    },
                )
            raise DjangoValidationError(f"Payment verification failed: {txn_or_err}")

        transaction_id = txn_or_err
        signature_snapshot = (
            payload.get('razorpay_signature')
            or payload.get('client_secret')
            or ''
        )

        # Verification succeeded: atomically update work order, record payment, and generate invoice
        with transaction.atomic():
            locked_wo = (
                WorkOrder.objects.select_for_update()
                .select_related('quotation', 'workshop', 'booking', 'buyer')
                .get(id=work_order.id)
            )

            # Re-check idempotency under lock
            pid_to_check = transaction_id or client_payment_id
            if pid_to_check:
                existing_under_lock = locked_wo.payments.filter(
                    provider_payment_id=pid_to_check,
                    status=WorkOrderPaymentStatusChoices.SUCCESS,
                ).first()
                if existing_under_lock:
                    return locked_wo, existing_under_lock

                existing_refunded = locked_wo.payments.filter(
                    provider_payment_id=pid_to_check,
                    status=WorkOrderPaymentStatusChoices.REFUNDED,
                ).first()
                if existing_refunded:
                    return locked_wo, existing_refunded

            # Recalculate balance under lock before applying funds
            balance_info = cls.calculate_outstanding_balance(locked_wo)
            current_outstanding = Decimal(balance_info["outstanding_balance"])

            # Late or excess payment protection: If work order is cancelled, already fully settled, or payment exceeds remaining balance
            if (
                locked_wo.status == WorkOrderStatusChoices.CANCELLED
                or current_outstanding <= Decimal('0.00')
                or amount_to_verify > current_outstanding
            ):
                clean_pid = transaction_id.replace('-', '_').replace(' ', '_')[:35]
                rfnd_num = f"REF-LATE-{clean_pid}"
                idemp_key = f"late_refund_{clean_pid}"

                reason_msg = (
                    f"Auto-refund: Work order {locked_wo.work_order_number} is cancelled."
                    if locked_wo.status == WorkOrderStatusChoices.CANCELLED
                    else (
                        f"Auto-refund: Work order {locked_wo.work_order_number} is already fully settled."
                        if current_outstanding <= Decimal('0.00')
                        else f"Auto-refund: Payment amount {amount_to_verify} exceeds outstanding balance {current_outstanding}."
                    )
                )

                refund_res = provider.issue_refund(
                    payment_reference=transaction_id,
                    amount=amount_to_verify,
                    currency=adapter.currency,
                    reason=reason_msg,
                    refund_number=rfnd_num,
                )
                refund_ok = refund_res[0] if isinstance(refund_res, tuple) else bool(refund_res)
                rfnd_ref = refund_res[1] if isinstance(refund_res, tuple) and len(refund_res) > 1 else str(refund_res)

                late_payment = pending_payment or WorkOrderPayment(
                    work_order=locked_wo,
                    payment_number=p_number,
                    amount=amount_to_verify,
                    currency=adapter.currency,
                    provider=provider.provider_name,
                    created_by=actor,
                )
                late_payment.status = WorkOrderPaymentStatusChoices.REFUNDED
                late_payment.is_late_payment = True
                late_payment.provider_payment_id = transaction_id
                late_payment.provider_order_id = client_order_id
                late_payment.provider_signature = signature_snapshot
                late_payment.error_message = f"Late payment auto-refunded. Ref: {rfnd_ref}"
                late_payment.paid_at = timezone.now()
                late_payment.save()

                record_audit_entry(
                    event_type="workshop.work_order.late_settlement_refunded",
                    action="workshop:work_order.late_settlement_refund",
                    resource_type="WorkOrder",
                    resource_id=str(locked_wo.id),
                    actor_id=actor.id,
                    metadata={
                        "work_order_number": locked_wo.work_order_number,
                        "payment_id": transaction_id,
                        "amount": str(amount_to_verify),
                        "refund_reference": rfnd_ref,
                        "refund_success": refund_ok,
                    },
                )
                return locked_wo, late_payment

            # Genuine successful payment: record in ledger
            payment_record = pending_payment or WorkOrderPayment(
                work_order=locked_wo,
                payment_number=p_number,
                amount=amount_to_verify,
                currency=adapter.currency,
                provider=provider.provider_name,
                created_by=actor,
            )
            payment_record.status = WorkOrderPaymentStatusChoices.SUCCESS
            payment_record.provider_payment_id = transaction_id
            payment_record.provider_order_id = client_order_id
            payment_record.provider_signature = signature_snapshot
            payment_record.paid_at = timezone.now()
            payment_record.save()

            # Recalculate settlement status after payment
            new_balance_info = cls.calculate_outstanding_balance(locked_wo)
            new_outstanding = Decimal(new_balance_info["outstanding_balance"])

            if new_outstanding == Decimal('0.00'):
                locked_wo.settlement_status = WorkOrderSettlementStatusChoices.FULLY_PAID
            else:
                locked_wo.settlement_status = WorkOrderSettlementStatusChoices.PARTIALLY_PAID
            locked_wo.save(update_fields=['settlement_status', 'updated_at'])

            # Generate or update final official invoice
            cls.generate_or_update_invoice(locked_wo)

            # Audit entry
            audit = record_audit_entry(
                event_type="workshop.work_order.balance_paid",
                action="workshop:work_order.balance_paid",
                resource_type="WorkOrder",
                resource_id=str(locked_wo.id),
                actor_id=actor.id,
                metadata={
                    "work_order_number": locked_wo.work_order_number,
                    "payment_number": payment_record.payment_number,
                    "amount": str(payment_record.amount),
                    "currency": payment_record.currency,
                    "provider": provider.provider_name,
                    "transaction_id": transaction_id,
                    "new_outstanding_balance": str(new_outstanding),
                    "settlement_status": locked_wo.settlement_status,
                },
            )

            # Dispatch notifications
            try:
                if audit:
                    create_notification(
                        recipient=actor,
                        audit_entry=audit,
                        title=f"Payment Received #{locked_wo.work_order_number}",
                        message=f"Your balance payment of {payment_record.currency} {payment_record.amount} for Work Order #{locked_wo.work_order_number} has been verified.",
                        link="/platform?tab=workshops",
                        resource_type="WorkOrder",
                        resource_id=str(locked_wo.id),
                        event_type="workshop.work_order.balance_paid",
                    )
                    org_owner = getattr(locked_wo.workshop.organisation, 'created_by', None)
                    if org_owner:
                        create_notification(
                            recipient=org_owner,
                            audit_entry=audit,
                            title=f"Work Order Payment #{locked_wo.work_order_number}",
                            message=f"Customer {actor.full_name or actor.email} paid {payment_record.currency} {payment_record.amount} towards Work Order #{locked_wo.work_order_number}.",
                            link="/platform?tab=workshop_landing",
                            resource_type="WorkOrder",
                            resource_id=str(locked_wo.id),
                            event_type="workshop.work_order.balance_paid",
                        )
            except Exception as notify_exc:
                logger.warning("Failed to dispatch settlement notification: %s", notify_exc)

            return locked_wo, payment_record

    @classmethod
    def generate_or_update_invoice(cls, work_order: WorkOrder) -> WorkOrderInvoice:
        """
        Generates or updates the final commercial/tax invoice for a WorkOrder.
        Accurately aggregates quotation, approved change orders, deposits, balance payments,
        taxes, and remaining balance.
        """
        balance_info = cls.calculate_outstanding_balance(work_order)
        quotation = work_order.quotation
        workshop = work_order.workshop

        # Tax and statutory document classification
        can_collect_tax = getattr(workshop, 'can_collect_tax', False)
        tax_rate = quotation.tax_rate_percent if quotation else Decimal('0.00')
        tax_amt = quotation.tax_amount if quotation else Decimal('0.00')

        # Add approved change order taxes
        for co in work_order.change_orders.filter(status=ChangeOrderStatusChoices.APPROVED):
            tax_amt += (co.tax_amount or Decimal('0.00'))

        document_type = 'TAX_INVOICE' if can_collect_tax else 'COMMERCIAL_INVOICE'

        # Determine invoice status based on work order and settlement standing
        if work_order.status == WorkOrderStatusChoices.CANCELLED:
            inv_status = WorkOrderInvoiceStatusChoices.VOID
        elif balance_info["is_fully_settled"] and Decimal(balance_info["total_paid_amount"]) > Decimal('0.00'):
            inv_status = WorkOrderInvoiceStatusChoices.PAID
        else:
            inv_status = WorkOrderInvoiceStatusChoices.ISSUED

        # Line item details snapshot
        line_items_snapshot = []
        if quotation:
            for item in quotation.line_items.all():
                line_items_snapshot.append({
                    "source": "QUOTATION",
                    "item_type": item.item_type,
                    "description": item.description,
                    "quantity": str(item.quantity),
                    "unit_price": str(item.unit_price),
                    "line_total": str(item.line_total),
                })

        for co in work_order.change_orders.filter(status=ChangeOrderStatusChoices.APPROVED):
            if co.line_items.exists():
                for item in co.line_items.all():
                    line_items_snapshot.append({
                        "source": f"CHANGE_ORDER_{co.change_order_number}",
                        "item_type": item.item_type,
                        "description": item.description,
                        "quantity": str(item.quantity),
                        "unit_price": str(item.unit_price),
                        "line_total": str(item.line_total),
                    })
            else:
                line_items_snapshot.append({
                    "source": f"CHANGE_ORDER_{co.change_order_number}",
                    "item_type": "CHANGE_ORDER",
                    "description": f"Approved Scope Change: {co.reason}",
                    "quantity": "1.00",
                    "unit_price": str(co.additional_amount),
                    "line_total": str(co.additional_amount),
                })

        # Payment history snapshot - avoid double-counting deposit representation
        payment_history = []
        has_wop_deposit = work_order.payments.filter(
            payment_type=WorkOrderPaymentTypeChoices.DEPOSIT,
            status=WorkOrderPaymentStatusChoices.SUCCESS,
        ).exists()

        if not has_wop_deposit and quotation and getattr(quotation, 'requires_deposit', False) and quotation.deposit_status == DepositStatusChoices.PAID:
            payment_history.append({
                "type": "DEPOSIT",
                "amount": str(quotation.deposit_amount),
                "currency": quotation.currency,
                "provider": quotation.deposit_provider,
                "reference": quotation.deposit_transaction_id,
                "paid_at": quotation.deposit_paid_at.isoformat() if quotation.deposit_paid_at else None,
            })

        for p in work_order.payments.filter(status=WorkOrderPaymentStatusChoices.SUCCESS):
            payment_history.append({
                "type": p.payment_type,
                "payment_number": p.payment_number,
                "amount": str(p.amount),
                "currency": p.currency,
                "provider": p.provider,
                "reference": p.provider_payment_id,
                "paid_at": p.paid_at.isoformat() if p.paid_at else None,
            })

        invoice_data = {
            "workshop": {
                "name": workshop.display_name,
                "city": workshop.city,
                "country": getattr(workshop, 'country', 'GB'),
                "contact_email": workshop.contact_email,
                "contact_phone": workshop.contact_phone,
                "can_collect_tax": can_collect_tax,
            },
            "customer": {
                "name": (
                    work_order.buyer.full_name
                    if hasattr(work_order.buyer, 'full_name') and work_order.buyer.full_name
                    else (work_order.buyer.get_full_name() if hasattr(work_order.buyer, 'get_full_name') else '')
                    or work_order.buyer.email
                ),
                "email": work_order.buyer.email,
            },
            "vehicle": {
                "make": work_order.vehicle_make,
                "model": work_order.vehicle_model,
                "year": work_order.vehicle_year,
                "registration_plate": work_order.vehicle_registration_plate,
                "vin": work_order.vehicle_vin,
                "odometer": work_order.current_odometer,
                "odometer_unit": work_order.odometer_unit,
            },
            "line_items": line_items_snapshot,
            "payment_history": payment_history,
        }

        invoice, _ = WorkOrderInvoice.objects.update_or_create(
            work_order=work_order,
            defaults={
                "status": inv_status,
                "document_type": document_type,
                "quotation_amount": Decimal(balance_info["original_quotation_amount"]),
                "approved_change_orders_amount": Decimal(balance_info["approved_change_orders_amount"]),
                "deposit_paid_amount": Decimal(balance_info["deposit_paid_amount"]),
                "balance_paid_amount": Decimal(balance_info["balance_paid_amount"]),
                "total_paid_amount": Decimal(balance_info["total_paid_amount"]),
                "tax_amount": tax_amt.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
                "tax_rate_percent": tax_rate,
                "total_authorized_amount": Decimal(balance_info["authorized_total_amount"]),
                "outstanding_balance": Decimal(balance_info["outstanding_balance"]),
                "currency": balance_info["currency"],
                "is_fully_settled": balance_info["is_fully_settled"],
                "invoice_data": invoice_data,
            },
        )
        return invoice

    @classmethod
    def process_settlement_webhook(
        cls,
        provider_name: str,
        request_body: bytes,
        headers: Dict[str, str],
    ) -> Tuple[bool, str]:
        """
        Idempotently processes incoming payment gateway webhook events for WorkOrder settlements.
        Guarantees replay protection using WorkshopSettlementWebhookEvent tracking.
        """
        p_name = provider_name.strip().upper()
        if p_name == 'RAZORPAY':
            provider = RazorpayPaymentProvider()
        elif p_name == 'STRIPE':
            provider = StripePaymentProvider()
        else:
            return False, f"Unsupported payment provider: {provider_name}"

        is_valid, event_id, event_type, payload = provider.verify_webhook(request_body, headers)
        if not is_valid:
            err_msg = payload.get('error', 'Cryptographic signature verification failed.') if isinstance(payload, dict) else 'Signature verification failed.'
            return False, f"Invalid webhook signature: {err_msg}"

        if not event_id:
            event_id = hashlib.sha256(request_body).hexdigest()

        # Idempotent replay protection
        webhook_record, created = WorkshopSettlementWebhookEvent.objects.get_or_create(
            event_id=event_id,
            defaults={
                'provider': p_name,
                'event_type': event_type,
                'payload': payload,
            },
        )

        if not created and webhook_record.processed:
            logger.info("Settlement webhook event %s already processed. Replay skipped.", event_id)
            return True, "Event already processed"

        # Resolve work order reference
        payment_order_id = ''
        payment_id = ''
        if p_name == 'RAZORPAY':
            payment_entity = payload.get('payload', {}).get('payment', {}).get('entity', {})
            payment_order_id = payment_entity.get('order_id', '')
            payment_id = payment_entity.get('id', '')
        elif p_name == 'STRIPE':
            data_obj = payload.get('data', {}).get('object', {})
            payment_order_id = data_obj.get('id', '')
            payment_id = data_obj.get('payment_intent') or data_obj.get('id', '')

        # Locate payment in ledger
        payment = WorkOrderPayment.objects.filter(
            models.Q(provider_order_id=payment_order_id) | models.Q(provider_payment_id=payment_id)
        ).first()

        if not payment:
            webhook_record.processed = True
            webhook_record.error_message = f"No work order payment found for provider order {payment_order_id}."
            webhook_record.save(update_fields=['processed', 'error_message'])
            return True, "Payment record not found; event acknowledged"

        work_order = payment.work_order
        webhook_record.work_order = work_order

        # Handle refund events
        if event_type in ('refund.processed', 'charge.refunded', 'refund.created', 'refund.updated'):
            from apps.workshops.models import WorkshopRefund, WorkshopRefundStatusChoices
            with transaction.atomic():
                p_locked = WorkOrderPayment.objects.select_for_update().get(id=payment.id)
                rfnd = WorkshopRefund.objects.filter(
                    models.Q(work_order_payment=p_locked) | models.Q(payment_reference=payment_id)
                ).first()
                if rfnd and rfnd.status != WorkshopRefundStatusChoices.SUCCEEDED:
                    rfnd.status = WorkshopRefundStatusChoices.SUCCEEDED
                    rfnd.processed_at = timezone.now()
                    rfnd.save(update_fields=['status', 'processed_at', 'updated_at'])

                wop_refunded_total = WorkshopRefund.objects.filter(
                    work_order_payment=p_locked,
                    status=WorkshopRefundStatusChoices.SUCCEEDED,
                ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
                if wop_refunded_total >= (p_locked.amount or Decimal('0.00')):
                    p_locked.status = WorkOrderPaymentStatusChoices.REFUNDED
                    p_locked.save(update_fields=['status', 'updated_at'])

            webhook_record.processed = True
            webhook_record.save(update_fields=['processed', 'work_order', 'updated_at'])
            return True, "Refund processed successfully via webhook"

        # Dispatch verification
        try:
            if p_name == 'RAZORPAY':
                valid_payment_sig = hmac.new(
                    provider.key_secret.encode('utf-8'),
                    f"{payment_order_id}|{payment_id}".encode('utf-8'),
                    hashlib.sha256,
                ).hexdigest()
                verification_payload = {
                    'razorpay_order_id': payment_order_id,
                    'razorpay_payment_id': payment_id,
                    'razorpay_signature': valid_payment_sig,
                }
            else:
                verification_payload = payload

            cls.verify_settlement_payment(
                work_order_id=work_order.id,
                payload=verification_payload,
                actor=payment.created_by,
                preferred_provider=p_name,
            )
            webhook_record.processed = True
            webhook_record.save(update_fields=['processed', 'work_order', 'updated_at'])
            return True, "Payment verified successfully"
        except Exception as exc:
            webhook_record.error_message = str(exc)
            webhook_record.save(update_fields=['error_message', 'work_order', 'updated_at'])
            return False, f"Failed to verify settlement payment: {exc}"
