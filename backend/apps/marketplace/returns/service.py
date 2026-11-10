import logging
import uuid
from decimal import Decimal
from datetime import timedelta
from typing import Dict, Any, List, Tuple, Optional

from django.conf import settings
from django.utils import timezone
from django.db import models, transaction
from django.core.exceptions import ValidationError as DjangoValidationError

from apps.marketplace.models import (
    Order,
    OrderItem,
    OrderStatusChoices,
    PaymentStatusChoices,
    CODCollectionStatusChoices,
    PaymentTransaction,
    Shipment,
    ShipmentStatusChoices,
    ReturnRequest,
    ReturnRequestTypeChoices,
    ReturnRequestStatusChoices,
    ReturnReasonChoices,
    Refund,
    RefundStatusChoices,
    RefundMethodChoices,
    Dispute,
    DisputeCategoryChoices,
    DisputeStatusChoices,
    DisputeResolutionChoices,
    DisputePriorityChoices,
    DisputeEvent,
    DisputeEventTypeChoices,
    StockMovementReasonChoices,
)
from apps.marketplace.services import adjust_stock
from platform_core.audit.writer import record_audit_entry, record_denied_audit_entry

logger = logging.getLogger(__name__)


def _is_platform_admin(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    return bool(
        user.is_superuser
        or getattr(user, 'role', '') in ('ADMIN', 'MARKETPLACE_ADMIN')
        or (hasattr(user, 'has_role') and (user.has_role('ADMIN') or user.has_role('MARKETPLACE_ADMIN')))
    )


def _is_staff_or_admin(user) -> bool:
    """Legacy helper: platform admins only for administrative bypass."""
    return _is_platform_admin(user)


def _has_permission(user, perm_code: str) -> bool:
    if not user or not user.is_authenticated:
        return False
    if _is_platform_admin(user):
        return True
    if hasattr(user, 'has_permission'):
        return user.has_permission(perm_code)
    return False


def _is_seller_authorized_for_order(user, order: Order) -> bool:
    """Checks if user is the direct seller or organisation admin for any item in the order."""
    if _is_staff_or_admin(user):
        return True
    if not user or not user.is_authenticated:
        return False

    from apps.organisations.models import OrganisationMembership, OrganisationRoleChoices
    user_org_ids = set(OrganisationMembership.objects.filter(
        user=user,
        is_active=True,
        role__in=[OrganisationRoleChoices.OWNER, OrganisationRoleChoices.ADMIN],
    ).values_list('organisation_id', flat=True))

    return order.items.filter(
        models.Q(listing__seller=user) | models.Q(listing__organisation_id__in=user_org_ids)
    ).exists()


def _is_seller_authorized_for_return(user, return_request: ReturnRequest) -> bool:
    """Checks if user is the direct seller or organisation admin for this return request."""
    if not user or not user.is_authenticated:
        return False

    if return_request.seller_id == user.id:
        return True

    from apps.organisations.models import OrganisationMembership, OrganisationRoleChoices
    if return_request.order_item and return_request.order_item.listing:
        org_id = return_request.order_item.listing.organisation_id
        if org_id:
            return OrganisationMembership.objects.filter(
                user=user,
                organisation_id=org_id,
                is_active=True,
                role__in=[OrganisationRoleChoices.OWNER, OrganisationRoleChoices.ADMIN],
            ).exists()
    return False


# =============================================================================
# 1. RETURN & CANCELLATION SERVICE
# =============================================================================

class ReturnService:
    """
    Manages buyer cancellation requests, physical item return requests,
    seller reviews, and inventory restocking transitions.
    """

    @classmethod
    def get_cancellation_eligibility(
        cls,
        order: Order,
        user: Any,
        order_item: Optional[OrderItem] = None,
    ) -> Tuple[bool, str, Decimal]:
        """
        Determines whether an order or order item can be cancelled.
        Cancellations are permitted before package dispatch.
        """
        if order.status == OrderStatusChoices.CANCELLED:
            return False, f"Order {order.order_number} is already cancelled.", Decimal('0.00')

        if order.status == OrderStatusChoices.COMPLETED:
            return False, f"Order {order.order_number} is already completed. Please request a return instead.", Decimal('0.00')

        # Check if shipments for this order/item have already been dispatched
        if order_item:
            dispatched_shipments = Shipment.objects.filter(
                order=order,
                items__order_item=order_item,
                status__in=[
                    ShipmentStatusChoices.DISPATCHED,
                    ShipmentStatusChoices.IN_TRANSIT,
                    ShipmentStatusChoices.OUT_FOR_DELIVERY,
                    ShipmentStatusChoices.DELIVERED,
                ],
            ).exists()
            if dispatched_shipments:
                return False, f"Item '{order_item.title}' has already been dispatched. Please request a return after delivery.", Decimal('0.00')
        else:
            dispatched_any = Shipment.objects.filter(
                order=order,
                status__in=[
                    ShipmentStatusChoices.DISPATCHED,
                    ShipmentStatusChoices.IN_TRANSIT,
                    ShipmentStatusChoices.OUT_FOR_DELIVERY,
                    ShipmentStatusChoices.DELIVERED,
                ],
            ).exists()
            if dispatched_any:
                return False, f"Shipments for order {order.order_number} are already in transit or delivered. Please request a return instead.", Decimal('0.00')

        # Check for existing open cancellation/return requests
        open_req = ReturnRequest.objects.filter(
            order=order,
            order_item=order_item,
            status__in=[ReturnRequestStatusChoices.PENDING, ReturnRequestStatusChoices.APPROVED],
        ).first()
        if open_req:
            return False, f"An active {open_req.request_type.lower()} request ({open_req.request_number}) is already in progress.", Decimal('0.00')

        # Calculate estimated refund amount
        if order_item:
            refund_amount = order_item.total_amount
        else:
            refund_amount = order.total_amount

        return True, "Eligible for cancellation.", refund_amount

    @classmethod
    def get_return_eligibility(
        cls,
        order: Order,
        user: Any,
        order_item: Optional[OrderItem] = None,
    ) -> Tuple[bool, str, Decimal]:
        """
        Determines whether an order item is eligible for physical return.
        Returns are permitted only after delivery within the return policy window.
        """
        if order.status == OrderStatusChoices.CANCELLED:
            return False, f"Order {order.order_number} is cancelled.", Decimal('0.00')

        # Check delivery status
        if order_item:
            delivered_shipment = Shipment.objects.filter(
                order=order,
                items__order_item=order_item,
                status=ShipmentStatusChoices.DELIVERED,
            ).order_by('-delivered_at').first()

            if not delivered_shipment:
                # If order completed, consider delivered
                if order.status != OrderStatusChoices.COMPLETED:
                    return False, f"Item '{order_item.title}' has not been marked as delivered yet.", Decimal('0.00')
                delivered_at = order.updated_at
            else:
                delivered_at = delivered_shipment.delivered_at or delivered_shipment.updated_at
        else:
            has_delivered = Shipment.objects.filter(
                order=order,
                status=ShipmentStatusChoices.DELIVERED,
            ).exists() or order.status == OrderStatusChoices.COMPLETED

            if not has_delivered:
                return False, f"No shipments have been marked as delivered for order {order.order_number}.", Decimal('0.00')
            delivered_at = order.updated_at

        # Check return window policy
        window_days = getattr(settings, 'MARKETPLACE_RETURN_WINDOW_DAYS', 14)
        if delivered_at and (timezone.now() - delivered_at) > timedelta(days=window_days):
            return False, f"The {window_days}-day return window for this order has expired.", Decimal('0.00')

        # Check for existing open return request
        open_req = ReturnRequest.objects.filter(
            order=order,
            order_item=order_item,
            status__in=[ReturnRequestStatusChoices.PENDING, ReturnRequestStatusChoices.APPROVED],
        ).first()
        if open_req:
            return False, f"An active {open_req.request_type.lower()} request ({open_req.request_number}) is already in progress.", Decimal('0.00')

        if order_item:
            refund_amount = order_item.total_amount
        else:
            refund_amount = order.total_amount

        return True, "Eligible for return.", refund_amount

    @classmethod
    def create_return_request(
        cls,
        order: Order,
        buyer: Any,
        request_type: str,
        reason: str,
        description: str,
        evidence_urls: Optional[List[str]] = None,
        order_item: Optional[OrderItem] = None,
        requested_quantity: int = 1,
        actor: Optional[Any] = None,
    ) -> ReturnRequest:
        """
        Creates a new cancellation or return request initiated by the buyer.
        """
        actor = actor or buyer
        if order.buyer_id != buyer.id and not _is_staff_or_admin(actor):
            raise DjangoValidationError("Permission denied: You can only create requests for your own orders.")

        req_type = request_type.strip().upper()
        if req_type not in ReturnRequestTypeChoices.values:
            raise DjangoValidationError(f"Invalid request type '{req_type}'. Must be CANCELLATION or RETURN.")

        if req_type == ReturnRequestTypeChoices.CANCELLATION:
            eligible, msg, est_refund = cls.get_cancellation_eligibility(order, buyer, order_item)
            if not eligible:
                raise DjangoValidationError(msg)
        else:
            eligible, msg, est_refund = cls.get_return_eligibility(order, buyer, order_item)
            if not eligible:
                raise DjangoValidationError(msg)

        # Quantity validation for item returns
        if order_item:
            if requested_quantity < 1 or requested_quantity > order_item.quantity:
                raise DjangoValidationError(
                    f"Requested return quantity ({requested_quantity}) must be between 1 and {order_item.quantity}."
                )
            # Prorated refund calculation
            unit_price_with_tax = order_item.total_amount / Decimal(str(order_item.quantity))
            calc_refund = (unit_price_with_tax * Decimal(str(requested_quantity))).quantize(Decimal('0.01'))
            seller = order_item.listing.seller if (order_item.listing and order_item.listing.seller) else order.buyer
        else:
            calc_refund = order.total_amount
            # Primary seller for the order
            first_item = order.items.select_related('listing__seller').first()
            seller = first_item.listing.seller if (first_item and first_item.listing and first_item.listing.seller) else order.buyer

        with transaction.atomic():
            request_num = f"RET-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

            req = ReturnRequest.objects.create(
                request_number=request_num,
                order=order,
                order_item=order_item,
                buyer=buyer,
                seller=seller,
                request_type=req_type,
                status=ReturnRequestStatusChoices.PENDING,
                reason=reason,
                description=description,
                evidence_urls=evidence_urls or [],
                requested_quantity=requested_quantity,
                refund_amount=calc_refund,
            )

            record_audit_entry(
                event_type="marketplace.return.created",
                action="marketplace:return.create",
                resource_type="ReturnRequest",
                resource_id=str(req.id),
                actor_id=actor.id if actor else buyer.id,
                metadata={
                    "request_number": req.request_number,
                    "order_number": order.order_number,
                    "request_type": req.request_type,
                    "reason": req.reason,
                    "refund_amount": str(req.refund_amount),
                },
            )

        return req

    @classmethod
    def review_return_request(
        cls,
        return_request: ReturnRequest,
        actor: Any,
        action: str,
        seller_notes: str = '',
        rejection_reason: str = '',
    ) -> ReturnRequest:
        """
        Sellers or authorized operations staff review pending return/cancellation requests.
        action: 'APPROVE' or 'REJECT'
        """
        if not _is_seller_authorized_for_return(actor, return_request):
            record_denied_audit_entry(
                action="marketplace:return.review",
                resource_type="ReturnRequest",
                resource_id=str(return_request.id),
                actor_id=actor.id if actor else None,
                reason_code="SELLER_UNAUTHORIZED_FOR_RETURN",
            )
            raise DjangoValidationError("Permission denied: You are not authorized to review this request.")

        if return_request.status != ReturnRequestStatusChoices.PENDING:
            raise DjangoValidationError(
                f"Cannot review request {return_request.request_number} with status '{return_request.status}'. Only PENDING requests can be reviewed."
            )

        act = action.strip().upper()
        if act not in ('APPROVE', 'REJECT'):
            raise DjangoValidationError("Action must be either 'APPROVE' or 'REJECT'.")

        with transaction.atomic():
            return_request.reviewed_by = actor
            return_request.reviewed_at = timezone.now()
            return_request.seller_notes = seller_notes

            if act == 'APPROVE':
                return_request.status = ReturnRequestStatusChoices.APPROVED

                # If this is a pre-dispatch cancellation, automatically restock and complete
                if return_request.request_type == ReturnRequestTypeChoices.CANCELLATION:
                    cls._execute_cancellation_completion(return_request, actor)

                record_audit_entry(
                    event_type="marketplace.return.approved",
                    action="marketplace:return.approve",
                    resource_type="ReturnRequest",
                    resource_id=str(return_request.id),
                    actor_id=actor.id,
                    metadata={
                        "request_number": return_request.request_number,
                        "order_number": return_request.order.order_number,
                        "notes": seller_notes,
                    },
                )
            else:
                return_request.status = ReturnRequestStatusChoices.REJECTED
                return_request.rejection_reason = rejection_reason or "Request rejected by seller/operations."

                record_audit_entry(
                    event_type="marketplace.return.rejected",
                    action="marketplace:return.reject",
                    resource_type="ReturnRequest",
                    resource_id=str(return_request.id),
                    actor_id=actor.id,
                    metadata={
                        "request_number": return_request.request_number,
                        "order_number": return_request.order.order_number,
                        "rejection_reason": return_request.rejection_reason,
                    },
                )

            return_request.save()

        return return_request

    @classmethod
    def _execute_cancellation_completion(cls, return_request: ReturnRequest, actor: Any):
        """Restocks inventory and sets order status on cancellation approval."""
        order = return_request.order
        if return_request.order_item:
            # Restock specific item
            if return_request.order_item.listing:
                adjust_stock(
                    listing=return_request.order_item.listing,
                    delta=return_request.requested_quantity,
                    reason=StockMovementReasonChoices.RETURN,
                    actor=actor,
                    note=f"Cancellation restock {return_request.request_number}",
                )
        else:
            # Restock all items and cancel order
            for item in order.items.select_related('listing').all():
                if item.listing:
                    adjust_stock(
                        listing=item.listing,
                        delta=item.quantity,
                        reason=StockMovementReasonChoices.RETURN,
                        actor=actor,
                        note=f"Full order cancellation restock {return_request.request_number}",
                    )
            order.status = OrderStatusChoices.CANCELLED
            order.save(update_fields=['status', 'updated_at'])

        return_request.status = ReturnRequestStatusChoices.COMPLETED
        return_request.completed_at = timezone.now()

    @classmethod
    def complete_return_request(
        cls,
        return_request: ReturnRequest,
        actor: Any,
        notes: str = '',
    ) -> ReturnRequest:
        """
        Marks an approved physical return as completed once items are received at seller warehouse.
        Restocks returned inventory items.
        """
        if not _is_seller_authorized_for_return(actor, return_request):
            record_denied_audit_entry(
                action="marketplace:return.complete",
                resource_type="ReturnRequest",
                resource_id=str(return_request.id),
                actor_id=actor.id if actor else None,
                reason_code="SELLER_UNAUTHORIZED_FOR_RETURN_COMPLETION",
            )
            raise DjangoValidationError("Permission denied: You are not authorized to complete this return.")

        if return_request.status != ReturnRequestStatusChoices.APPROVED:
            raise DjangoValidationError(
                f"Cannot complete return request {return_request.request_number} with status '{return_request.status}'. It must be APPROVED first."
            )

        with transaction.atomic():
            return_request.status = ReturnRequestStatusChoices.COMPLETED
            return_request.completed_at = timezone.now()
            if notes:
                return_request.seller_notes = f"{return_request.seller_notes}\n[Completed]: {notes}".strip()
            return_request.save()

            # Restock items
            if return_request.order_item and return_request.order_item.listing:
                adjust_stock(
                    listing=return_request.order_item.listing,
                    delta=return_request.requested_quantity,
                    reason=StockMovementReasonChoices.RETURN,
                    actor=actor,
                    note=f"Goods received return {return_request.request_number}",
                )

            record_audit_entry(
                event_type="marketplace.return.completed",
                action="marketplace:return.complete",
                resource_type="ReturnRequest",
                resource_id=str(return_request.id),
                actor_id=actor.id,
                metadata={
                    "request_number": return_request.request_number,
                    "order_number": return_request.order.order_number,
                    "restocked_qty": return_request.requested_quantity,
                },
            )

        return return_request

    @classmethod
    def cancel_return_request_by_buyer(cls, return_request: ReturnRequest, buyer: Any) -> ReturnRequest:
        """Allows buyer to withdraw their pending cancellation or return request."""
        if return_request.buyer_id != buyer.id and not _is_staff_or_admin(buyer):
            raise DjangoValidationError("Permission denied: You can only withdraw your own requests.")

        if return_request.status != ReturnRequestStatusChoices.PENDING:
            raise DjangoValidationError(
                f"Cannot withdraw request {return_request.request_number} with status '{return_request.status}'."
            )

        with transaction.atomic():
            return_request.status = ReturnRequestStatusChoices.CANCELLED
            return_request.save(update_fields=['status', 'updated_at'])

            record_audit_entry(
                event_type="marketplace.return.buyer_withdrawn",
                action="marketplace:return.withdraw",
                resource_type="ReturnRequest",
                resource_id=str(return_request.id),
                actor_id=buyer.id,
                metadata={
                    "request_number": return_request.request_number,
                    "order_number": return_request.order.order_number,
                },
            )

        return return_request


# =============================================================================
# 2. REFUND MANAGEMENT SERVICE
# =============================================================================

class RefundService:
    """
    Orchestrates refund ledger records, remaining balance validations,
    COD collection integrity, payment gateway refund tracking, and payment transaction logs.
    """

    @classmethod
    def get_order_refund_summary(cls, order: Order) -> Dict[str, Any]:
        """
        Authoritatively calculates paid amount, existing refunds, and maximum refundable balance.
        """
        # Determine actual paid amount
        if order.payment_method == 'COD':
            is_paid = (
                order.cod_collection_status == CODCollectionStatusChoices.COLLECTED
                and order.payment_status == PaymentStatusChoices.PAID
            )
            paid_amount = order.total_amount if is_paid else Decimal('0.00')
        else:
            is_paid = order.payment_status in (PaymentStatusChoices.PAID, PaymentStatusChoices.REFUNDED)
            paid_amount = order.total_amount if is_paid else Decimal('0.00')

        # Existing active refunds (exclude FAILED and CANCELLED)
        active_refunds = order.refunds.filter(
            status__in=[
                RefundStatusChoices.PENDING,
                RefundStatusChoices.PROCESSING,
                RefundStatusChoices.PROCESSING_UNKNOWN,
                RefundStatusChoices.SUCCEEDED,
            ]
        )
        total_refunded = active_refunds.aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')

        available_refundable = max(Decimal('0.00'), (paid_amount - total_refunded).quantize(Decimal('0.01')))

        return {
            "order_number": order.order_number,
            "currency": order.currency,
            "order_total": order.total_amount,
            "payment_method": order.payment_method,
            "payment_status": order.payment_status,
            "cod_collection_status": order.cod_collection_status,
            "is_paid": is_paid,
            "paid_amount": paid_amount,
            "total_refunded": total_refunded,
            "available_refundable": available_refundable,
            "can_refund": bool(is_paid and available_refundable > Decimal('0.00')),
        }

    @classmethod
    def create_refund(
        cls,
        order: Order,
        amount: Decimal,
        reason: str,
        actor: Any,
        return_request: Optional[ReturnRequest] = None,
        dispute: Optional[Dispute] = None,
        refund_method: Optional[str] = None,
        notes: str = '',
        auto_process: bool = False,
    ) -> Refund:
        """
        Creates a refund request or record.
        Strictly enforces that refund cannot exceed remaining paid balance.
        Never pretends a refund was paid if automated gateway has not processed it.
        """
        # Permission check: staff with 'order.refund' or admin
        has_perm = (
            _has_permission(actor, 'order.refund')
            or _has_permission(actor, 'finance.payout')
        )
        if not has_perm:
            record_denied_audit_entry(
                action="marketplace:order.refund",
                resource_type="Order",
                resource_id=str(order.id),
                actor_id=actor.id if actor else None,
                reason_code="PERMISSION_DENIED_ORDER_REFUND",
            )
            raise DjangoValidationError("Permission denied: You do not have the 'order.refund' permission.")

        amt = Decimal(str(amount)).quantize(Decimal('0.01'))
        if amt <= Decimal('0.00'):
            raise DjangoValidationError("Refund amount must be greater than zero.")

        with transaction.atomic():
            locked_order = Order.objects.select_for_update().get(id=order.id)
            if locked_order.refunds.filter(status=RefundStatusChoices.PROCESSING_UNKNOWN).exists():
                raise DjangoValidationError(
                    f"Cannot issue a new refund for order {locked_order.order_number}: an ambiguous refund is currently awaiting gateway reconciliation. "
                    "Please resolve the pending transaction before issuing additional refunds."
                )
            summary = cls.get_order_refund_summary(locked_order)
            if not summary['is_paid']:
                if locked_order.payment_method == 'COD':
                    raise DjangoValidationError(
                        "Cannot issue refund for Cash on Delivery order because payment has not been collected."
                    )
                raise DjangoValidationError(
                    f"Cannot issue refund for order with payment status '{locked_order.payment_status}'. Order must be PAID."
                )

            if amt > summary['available_refundable']:
                raise DjangoValidationError(
                    f"Requested refund amount ({locked_order.currency} {amt}) exceeds maximum available refundable balance ({locked_order.currency} {summary['available_refundable']})."
                )

            refund_num = f"REF-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

            # Method resolution
            if not refund_method:
                if locked_order.payment_method == 'COD':
                    resolved_method = RefundMethodChoices.BANK_TRANSFER
                else:
                    resolved_method = RefundMethodChoices.ORIGINAL_PAYMENT
            else:
                resolved_method = refund_method

            # Provider resolution
            if locked_order.payment_method == 'COD':
                provider = 'COD_MANUAL'
            else:
                provider = 'RAZORPAY' if locked_order.currency == 'INR' else 'STRIPE'

            refund = Refund.objects.create(
                refund_number=refund_num,
                order=locked_order,
                return_request=return_request,
                dispute=dispute,
                amount=amt,
                currency=locked_order.currency,
                status=RefundStatusChoices.PENDING,
                refund_method=resolved_method,
                gateway_provider=provider,
                reason=reason,
                notes=notes,
                created_by=actor,
                approved_by=actor,
            )

            record_audit_entry(
                event_type="marketplace.refund.created",
                action="marketplace:refund.create",
                resource_type="Refund",
                resource_id=str(refund.id),
                actor_id=actor.id if actor else None,
                metadata={
                    "refund_number": refund.refund_number,
                    "order_number": locked_order.order_number,
                    "amount": str(amt),
                    "currency": locked_order.currency,
                    "reason": reason,
                    "method": resolved_method,
                },
            )

        if auto_process:
            if resolved_method == RefundMethodChoices.ORIGINAL_PAYMENT:
                refund = cls.dispatch_gateway_refund(refund, actor)
            else:
                refund = cls.process_refund(refund, actor, notes="Auto-processed settlement.")

        return refund

    @classmethod
    def process_refund(
        cls,
        refund: Refund,
        actor: Any,
        gateway_reference: str = '',
        notes: str = '',
    ) -> Refund:
        """
        Marks an approved refund as successfully processed/settled.
        Updates order payment_status if fully refunded and creates a PaymentTransaction ledger entry.
        """
        has_perm = (
            _is_platform_admin(actor)
            or _has_permission(actor, 'finance.payout')
        )
        if not has_perm:
            raise DjangoValidationError("Permission denied: You do not have the 'finance.payout' permission.")

        if refund.status not in (RefundStatusChoices.PENDING, RefundStatusChoices.PROCESSING):
            raise DjangoValidationError(
                f"Cannot process refund {refund.refund_number} with status '{refund.status}'."
            )

        with transaction.atomic():
            refund.status = RefundStatusChoices.SUCCEEDED
            refund.processed_at = timezone.now()
            if gateway_reference:
                refund.gateway_refund_id = gateway_reference
            if notes:
                refund.notes = f"{refund.notes}\n[Processed]: {notes}".strip()
            refund.save()

            # Record in immutable payment transaction ledger
            PaymentTransaction.objects.create(
                order=refund.order,
                transaction_type=PaymentTransaction.TransactionTypeChoices.REFUND,
                provider=refund.gateway_provider or 'MANUAL',
                amount=refund.amount,
                currency=refund.currency,
                status=PaymentTransaction.StatusChoices.SUCCESS,
                provider_transaction_id=refund.gateway_refund_id or refund.refund_number,
                provider_order_id=refund.order.payment_reference,
                raw_response={"refund_number": refund.refund_number, "reason": refund.reason},
            )

            # Check if total refunded equals or exceeds order total
            total_succeeded = refund.order.refunds.filter(
                status=RefundStatusChoices.SUCCEEDED
            ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')

            if total_succeeded >= refund.order.total_amount:
                refund.order.payment_status = PaymentStatusChoices.REFUNDED
                refund.order.save(update_fields=['payment_status', 'updated_at'])

            record_audit_entry(
                event_type="marketplace.refund.processed",
                action="marketplace:refund.process",
                resource_type="Refund",
                resource_id=str(refund.id),
                actor_id=actor.id,
                metadata={
                    "refund_number": refund.refund_number,
                    "order_number": refund.order.order_number,
                    "amount": str(refund.amount),
                    "gateway_refund_id": refund.gateway_refund_id,
                },
            )

        return refund

    @classmethod
    def fail_refund(
        cls,
        refund: Refund,
        actor: Any,
        failure_reason: str,
    ) -> Refund:
        """Records gateway or manual payout failure for a refund."""
        if not (_has_permission(actor, 'order.refund') or _has_permission(actor, 'finance.payout')):
            raise DjangoValidationError("Permission denied: You do not have the 'order.refund' permission.")

        with transaction.atomic():
            refund.status = RefundStatusChoices.FAILED
            refund.failure_reason = failure_reason
            refund.save(update_fields=['status', 'failure_reason', 'updated_at'])

            PaymentTransaction.objects.create(
                order=refund.order,
                transaction_type=PaymentTransaction.TransactionTypeChoices.REFUND,
                provider=refund.gateway_provider or 'MANUAL',
                amount=refund.amount,
                currency=refund.currency,
                status=PaymentTransaction.StatusChoices.FAILED,
                error_message=failure_reason,
            )

            record_audit_entry(
                event_type="marketplace.refund.failed",
                action="marketplace:refund.fail",
                resource_type="Refund",
                resource_id=str(refund.id),
                actor_id=actor.id,
                metadata={
                    "refund_number": refund.refund_number,
                    "failure_reason": failure_reason,
                },
            )

        return refund

    @classmethod
    def dispatch_gateway_refund(
        cls,
        refund: Refund,
        actor: Any,
        approved_request: Optional[Any] = None,
    ) -> Refund:
        """
        Dispatches an authoritative refund request to the external payment gateway (Razorpay/Stripe).
        Guards idempotency and creates immutable ledger records.
        Enforces Maker-Checker dual authorization for high-value refunds exceeding threshold.
        """
        has_perm = (
            _is_platform_admin(actor)
            or _has_permission(actor, 'finance.payout')
        )
        if not has_perm:
            raise DjangoValidationError("Permission denied: You do not have the 'finance.payout' permission.")

        from apps.identity.approval_service import ApprovalService
        from apps.identity.models import ApprovalRequest, ApprovalStatusChoices

        # Check Maker-Checker requirement if amount exceeds dual-authorization threshold
        if ApprovalService.is_approval_required(action_type='REFUND_DISPATCH', amount=refund.amount, currency=refund.currency):
            if approved_request is None:
                # Find latest approved request for this refund
                approved_req = ApprovalRequest.objects.filter(
                    target_type='Refund',
                    target_id=str(refund.id),
                    status=ApprovalStatusChoices.APPROVED,
                ).order_by('-reviewed_at').first()

                if not approved_req:
                    # Look for existing pending request or create one
                    pending_req = ApprovalRequest.objects.filter(
                        target_type='Refund',
                        target_id=str(refund.id),
                        status=ApprovalStatusChoices.PENDING,
                    ).first()
                    if not pending_req:
                        pending_req = ApprovalService.create_request(
                            requester=actor,
                            action_type='REFUND_DISPATCH',
                            target_type='Refund',
                            target_id=str(refund.id),
                            amount=refund.amount,
                            currency=refund.currency,
                            reason=refund.reason or f"Gateway refund for Order {refund.order.order_number}",
                            payload={
                                "refund_id": str(refund.id),
                                "refund_number": refund.refund_number,
                                "order_id": str(refund.order.id),
                                "order_number": refund.order.order_number,
                                "amount": str(refund.amount),
                                "currency": refund.currency,
                            },
                        )
                    threshold = ApprovalService.get_threshold_for_currency(refund.currency)
                    raise DjangoValidationError(
                        f"High-value refund ({refund.currency} {refund.amount}) exceeds the maker-checker threshold ({refund.currency} {threshold}). "
                        f"Dual authorization approval is required before gateway dispatch (Request ID: {pending_req.id})."
                    )
                approved_request = approved_req

        # Strict integrity validation for approved requests
        if approved_request is not None:
            if approved_request.target_type != 'Refund' or str(approved_request.target_id) != str(refund.id):
                raise DjangoValidationError(
                    f"Integrity violation: Approval request target ({approved_request.target_type}:{approved_request.target_id}) does not match this refund ({refund.id})."
                )
            if approved_request.action_type != 'REFUND_DISPATCH':
                raise DjangoValidationError(
                    f"Integrity violation: Approval request action type is '{approved_request.action_type}', expected 'REFUND_DISPATCH'."
                )
            if approved_request.status == ApprovalStatusChoices.EXECUTED:
                raise DjangoValidationError("Approval request has already been executed.")
            if approved_request.status != ApprovalStatusChoices.APPROVED:
                raise DjangoValidationError(
                    f"Cannot dispatch refund: Approval request is in '{approved_request.status}' status, not APPROVED."
                )
            if approved_request.amount is not None and Decimal(str(approved_request.amount)) != Decimal(str(refund.amount)):
                raise DjangoValidationError(
                    f"Integrity violation: Approved amount ({approved_request.currency} {approved_request.amount}) does not match current refund amount ({refund.currency} {refund.amount}). Re-authorization is required."
                )
            if approved_request.currency and approved_request.currency.upper() != refund.currency.upper():
                raise DjangoValidationError(
                    f"Integrity violation: Approved currency ({approved_request.currency}) does not match current refund currency ({refund.currency}). Re-authorization is required."
                )

        with transaction.atomic():
            locked_refund = Refund.objects.select_for_update().select_related('order').get(id=refund.id)

            # Idempotency check: if already succeeded, do not dispatch again
            if locked_refund.status == RefundStatusChoices.SUCCEEDED:
                return locked_refund

            # Concurrent execution protection: do not dispatch if already processing
            if locked_refund.status == RefundStatusChoices.PROCESSING:
                raise DjangoValidationError(f"Refund {locked_refund.refund_number} is currently being processed by the payment gateway.")

            # Ambiguous state protection: must reconcile before retrying
            if locked_refund.status == RefundStatusChoices.PROCESSING_UNKNOWN:
                raise DjangoValidationError(
                    f"Refund {locked_refund.refund_number} is in 'PROCESSING_UNKNOWN' status. "
                    "The outcome of the previous gateway transaction is ambiguous. "
                    "Reconciliation must be performed before any retry."
                )

            if locked_refund.status == RefundStatusChoices.CANCELLED:
                raise DjangoValidationError(f"Cannot dispatch cancelled refund {locked_refund.refund_number}.")

            if locked_refund.refund_method != RefundMethodChoices.ORIGINAL_PAYMENT:
                return cls.process_refund(locked_refund, actor, notes="Settled non-gateway refund.")

            # Resolve payment reference for the gateway
            order = locked_refund.order
            from apps.marketplace.payments.service import PaymentService
            provider = PaymentService.get_provider_for_order(order)

            # Look for payment transaction
            pay_tx = PaymentTransaction.objects.filter(
                order=order,
                status=PaymentTransaction.StatusChoices.SUCCESS,
                transaction_type=PaymentTransaction.TransactionTypeChoices.PAYMENT,
            ).order_by('-created_at').first()

            payment_reference = ''
            if locked_refund.currency == 'INR':
                # Razorpay needs pay_xxx
                if pay_tx and pay_tx.provider_transaction_id and str(pay_tx.provider_transaction_id).startswith('pay_'):
                    payment_reference = pay_tx.provider_transaction_id
                elif order.payment_reference and str(order.payment_reference).startswith('pay_'):
                    payment_reference = order.payment_reference
                elif pay_tx and pay_tx.provider_transaction_id:
                    payment_reference = pay_tx.provider_transaction_id
                else:
                    payment_reference = order.payment_reference or ''
            else:
                # Stripe needs pi_xxx
                if order.payment_reference and str(order.payment_reference).startswith('pi_'):
                    payment_reference = order.payment_reference
                elif pay_tx and pay_tx.provider_order_id and str(pay_tx.provider_order_id).startswith('pi_'):
                    payment_reference = pay_tx.provider_order_id
                elif pay_tx and pay_tx.provider_transaction_id and str(pay_tx.provider_transaction_id).startswith('pi_'):
                    payment_reference = pay_tx.provider_transaction_id
                else:
                    payment_reference = order.payment_reference or (pay_tx.provider_transaction_id if pay_tx else '')

            if not payment_reference:
                if getattr(settings, 'IS_TESTING', False) or getattr(settings, 'PAYMENT_TEST_MODE', False):
                    payment_reference = (
                        f"pay_test_{order.order_number}"
                        if locked_refund.currency == 'INR'
                        else f"pi_test_{order.order_number}"
                    )
                else:
                    raise DjangoValidationError(
                        f"Cannot dispatch gateway refund: Order {order.order_number} has no recorded payment reference."
                    )

            if not locked_refund.idempotency_key:
                locked_refund.idempotency_key = locked_refund.refund_number
            locked_refund.status = RefundStatusChoices.PROCESSING
            locked_refund.gateway_provider = provider.provider_name
            locked_refund.save(update_fields=['status', 'gateway_provider', 'idempotency_key', 'updated_at'])

            rfnd_id_copy = locked_refund.id
            amount_copy = locked_refund.amount
            currency_copy = locked_refund.currency
            reason_copy = locked_refund.reason
            refund_num_copy = locked_refund.refund_number
            order_num_copy = order.order_number
            idemp_key_copy = locked_refund.idempotency_key

        # Decouple external network gateway call from the initial database lock
        is_timeout_or_ambiguous = False
        try:
            success, ref_id_or_err, extra = provider.issue_refund(
                payment_reference=payment_reference,
                amount=amount_copy,
                currency=currency_copy,
                reason=reason_copy,
                refund_number=refund_num_copy,
                notes={
                    "order_number": order_num_copy,
                    "refund_number": refund_num_copy,
                },
            )
        except Exception as exc:
            logger.exception("Payment gateway issue_refund raised an unexpected exception for refund %s: %s", refund_num_copy, exc)
            success = False
            ref_id_or_err = f"Payment gateway communication error: {str(exc)}"
            extra = {"error": str(exc), "exception_type": exc.__class__.__name__}
            is_timeout_or_ambiguous = True

        if not success and not is_timeout_or_ambiguous:
            err_lower = (ref_id_or_err or '').lower()
            if any(term in err_lower for term in ['timeout', 'timed out', 'communication error', 'connect', 'bad gateway', 'gateway timeout', '502', '503', '504']):
                is_timeout_or_ambiguous = True

        with transaction.atomic():
            locked_refund = Refund.objects.select_for_update().select_related('order').get(id=rfnd_id_copy)
            order = locked_refund.order

            if success:
                locked_refund.status = RefundStatusChoices.SUCCEEDED
                locked_refund.gateway_refund_id = ref_id_or_err
                locked_refund.processed_at = timezone.now()
                locked_refund.failure_reason = ''
                locked_refund.next_reconciliation_at = None
                locked_refund.save(update_fields=['status', 'gateway_refund_id', 'processed_at', 'failure_reason', 'next_reconciliation_at', 'updated_at'])

                PaymentTransaction.objects.create(
                    order=order,
                    transaction_type=PaymentTransaction.TransactionTypeChoices.REFUND,
                    provider=provider.provider_name,
                    amount=locked_refund.amount,
                    currency=locked_refund.currency,
                    status=PaymentTransaction.StatusChoices.SUCCESS,
                    provider_transaction_id=ref_id_or_err,
                    provider_order_id=payment_reference,
                    idempotency_key=idemp_key_copy,
                    raw_response=extra,
                )

                # Check if total refunded covers order total
                total_succeeded = order.refunds.filter(
                    status=RefundStatusChoices.SUCCEEDED
                ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')

                if total_succeeded >= order.total_amount:
                    order.payment_status = PaymentStatusChoices.REFUNDED
                    order.save(update_fields=['payment_status', 'updated_at'])

                record_audit_entry(
                    event_type="marketplace.refund.processed",
                    action="marketplace:refund.process",
                    resource_type="Refund",
                    resource_id=str(locked_refund.id),
                    actor_id=actor.id if actor else None,
                    metadata={
                        "refund_number": locked_refund.refund_number,
                        "order_number": order.order_number,
                        "amount": str(locked_refund.amount),
                        "currency": locked_refund.currency,
                        "gateway_refund_id": ref_id_or_err,
                        "provider": provider.provider_name,
                    },
                )

                if approved_request:
                    from apps.identity.models import ApprovalStatusChoices
                    if approved_request.status != ApprovalStatusChoices.EXECUTED:
                        if approved_request.execution_error:
                            approved_request.execution_error = ""
                            approved_request.save(update_fields=['execution_error', 'updated_at'])
                        approved_request.mark_executed(executor=actor, notes=f"Gateway refund dispatched with id {ref_id_or_err}.")
                        record_audit_entry(
                            event_type="approval.request.execution.success",
                            action="approval:request.execute",
                            resource_type="ApprovalRequest",
                            resource_id=str(approved_request.id),
                            actor_id=actor.id if actor else None,
                            metadata={
                                "gateway_refund_id": ref_id_or_err,
                                "refund_number": locked_refund.refund_number,
                            },
                        )

                return locked_refund
            elif is_timeout_or_ambiguous:
                # Ambiguous state: Gateway call timed out or raised a network exception.
                # Must transition to PROCESSING_UNKNOWN to prevent duplicate refunds.
                import datetime
                locked_refund.status = RefundStatusChoices.PROCESSING_UNKNOWN
                locked_refund.failure_reason = ref_id_or_err
                locked_refund.reconciliation_attempts = 0
                locked_refund.next_reconciliation_at = timezone.now() + datetime.timedelta(minutes=2)
                locked_refund.save(update_fields=['status', 'failure_reason', 'reconciliation_attempts', 'next_reconciliation_at', 'updated_at'])

                PaymentTransaction.objects.create(
                    order=order,
                    transaction_type=PaymentTransaction.TransactionTypeChoices.REFUND,
                    provider=provider.provider_name,
                    amount=locked_refund.amount,
                    currency=locked_refund.currency,
                    status=PaymentTransaction.StatusChoices.PENDING,
                    error_message=ref_id_or_err,
                    provider_transaction_id='',
                    provider_order_id=payment_reference,
                    idempotency_key=idemp_key_copy,
                    raw_response=extra,
                )

                record_audit_entry(
                    event_type="marketplace.refund.gateway_timeout",
                    action="marketplace:refund.dispatch",
                    resource_type="Refund",
                    resource_id=str(locked_refund.id),
                    actor_id=actor.id if actor else None,
                    metadata={
                        "refund_number": locked_refund.refund_number,
                        "order_number": order.order_number,
                        "amount": str(locked_refund.amount),
                        "currency": locked_refund.currency,
                        "error": ref_id_or_err,
                        "status": RefundStatusChoices.PROCESSING_UNKNOWN,
                        "idempotency_key": idemp_key_copy,
                        "provider": provider.provider_name,
                    },
                )

                if approved_request:
                    approved_request.execution_error = (
                        f"Payment gateway timeout for refund {locked_refund.refund_number}. "
                        f"Status is '{RefundStatusChoices.PROCESSING_UNKNOWN}'. Awaiting reconciliation."
                    )
                    approved_request.save(update_fields=['execution_error', 'updated_at'])
                    record_audit_entry(
                        event_type="approval.request.execution.ambiguous",
                        action="approval:request.execute",
                        resource_type="ApprovalRequest",
                        resource_id=str(approved_request.id),
                        actor_id=actor.id if actor else None,
                        metadata={"error": ref_id_or_err},
                    )
            else:
                locked_refund.status = RefundStatusChoices.FAILED
                locked_refund.failure_reason = ref_id_or_err
                locked_refund.next_reconciliation_at = None
                locked_refund.save(update_fields=['status', 'failure_reason', 'next_reconciliation_at', 'updated_at'])

                PaymentTransaction.objects.create(
                    order=order,
                    transaction_type=PaymentTransaction.TransactionTypeChoices.REFUND,
                    provider=provider.provider_name,
                    amount=locked_refund.amount,
                    currency=locked_refund.currency,
                    status=PaymentTransaction.StatusChoices.FAILED,
                    error_message=ref_id_or_err,
                    provider_order_id=payment_reference,
                    idempotency_key=idemp_key_copy,
                    raw_response=extra,
                )

                record_audit_entry(
                    event_type="marketplace.refund.failed",
                    action="marketplace:refund.fail",
                    resource_type="Refund",
                    resource_id=str(locked_refund.id),
                    actor_id=actor.id if actor else None,
                    metadata={
                        "refund_number": locked_refund.refund_number,
                        "order_number": order.order_number,
                        "amount": str(locked_refund.amount),
                        "failure_reason": ref_id_or_err,
                        "provider": provider.provider_name,
                    },
                )

                if approved_request:
                    approved_request.execution_error = ref_id_or_err or "Gateway refund dispatch failed."
                    approved_request.save(update_fields=['execution_error', 'updated_at'])
                    record_audit_entry(
                        event_type="approval.request.execution.failed",
                        action="approval:request.execute",
                        resource_type="ApprovalRequest",
                        resource_id=str(approved_request.id),
                        actor_id=actor.id if actor else None,
                        metadata={"error": ref_id_or_err},
                    )

        if is_timeout_or_ambiguous:
            raise DjangoValidationError(
                f"Payment gateway communication timeout for refund {refund_num_copy}. "
                f"Status is '{RefundStatusChoices.PROCESSING_UNKNOWN}'. Awaiting reconciliation."
            )
        raise DjangoValidationError(f"Payment gateway refund failed: {ref_id_or_err}")

    @classmethod
    def reconcile_refund(
        cls,
        refund: Refund,
        actor: Optional[Any] = None,
    ) -> Tuple[Refund, str]:
        """
        Inquires the external gateway provider to reconcile an ambiguous or pending refund.
        Transitions the refund to SUCCEEDED or FAILED only upon definitive provider confirmation.
        If the status remains ambiguous, increments reconciliation_attempts with bounded exponential backoff.
        """
        import datetime
        import uuid
        from apps.marketplace.payments.service import PaymentService

        target_refund_id = refund if isinstance(refund, (str, uuid.UUID)) else refund.id

        with transaction.atomic():
            locked_refund = Refund.objects.select_for_update().select_related('order').get(id=target_refund_id)
            order = locked_refund.order

            if locked_refund.status == RefundStatusChoices.SUCCEEDED:
                return locked_refund, "ALREADY_SUCCEEDED"

            if locked_refund.status not in (RefundStatusChoices.PROCESSING_UNKNOWN, RefundStatusChoices.PROCESSING):
                return locked_refund, f"INELIGIBLE_STATUS_{locked_refund.status}"

            provider = PaymentService.get_provider_for_order(order)
            payment_reference = order.payment_reference or ''
            if not payment_reference:
                pay_tx = PaymentTransaction.objects.filter(
                    order=order,
                    status=PaymentTransaction.StatusChoices.SUCCESS,
                    transaction_type=PaymentTransaction.TransactionTypeChoices.PAYMENT,
                ).order_by('-created_at').first()
                payment_reference = pay_tx.provider_transaction_id if pay_tx else ''

            if not payment_reference:
                payment_reference = (
                    f"pay_test_{order.order_number}"
                    if locked_refund.currency == 'INR'
                    else f"pi_test_{order.order_number}"
                )

            locked_refund.reconciliation_attempts += 1
            locked_refund.last_reconciliation_at = timezone.now()
            locked_refund.save(update_fields=['reconciliation_attempts', 'last_reconciliation_at', 'updated_at'])

            rfnd_id = locked_refund.id
            rfnd_num = locked_refund.refund_number
            gw_id = locked_refund.gateway_refund_id
            attempts = locked_refund.reconciliation_attempts
            idemp_key = locked_refund.idempotency_key or rfnd_num

        # Inquire outside the row lock
        try:
            inq_status, ref_id_or_err, extra = provider.inquire_refund(
                payment_reference=payment_reference,
                refund_number=rfnd_num,
                gateway_refund_id=gw_id or None,
            )
        except Exception as exc:
            logger.exception("Error during provider.inquire_refund for %s: %s", rfnd_num, exc)
            inq_status = 'UNKNOWN'
            ref_id_or_err = f"Exception during gateway inquiry: {str(exc)}"
            extra = {"error": str(exc)}

        with transaction.atomic():
            locked_refund = Refund.objects.select_for_update().select_related('order').get(id=rfnd_id)
            order = locked_refund.order

            if locked_refund.status == RefundStatusChoices.SUCCEEDED:
                return locked_refund, "ALREADY_SUCCEEDED"

            if inq_status == 'SUCCEEDED':
                locked_refund.status = RefundStatusChoices.SUCCEEDED
                locked_refund.gateway_refund_id = ref_id_or_err or locked_refund.gateway_refund_id
                locked_refund.processed_at = timezone.now()
                locked_refund.failure_reason = ''
                locked_refund.next_reconciliation_at = None
                locked_refund.save(update_fields=[
                    'status', 'gateway_refund_id', 'processed_at', 'failure_reason', 'next_reconciliation_at', 'updated_at'
                ])

                existing_tx = PaymentTransaction.objects.filter(
                    order=order,
                    transaction_type=PaymentTransaction.TransactionTypeChoices.REFUND,
                    status=PaymentTransaction.StatusChoices.SUCCESS,
                    provider_transaction_id=locked_refund.gateway_refund_id,
                ).first()
                if not existing_tx:
                    PaymentTransaction.objects.create(
                        order=order,
                        transaction_type=PaymentTransaction.TransactionTypeChoices.REFUND,
                        provider=provider.provider_name,
                        amount=locked_refund.amount,
                        currency=locked_refund.currency,
                        status=PaymentTransaction.StatusChoices.SUCCESS,
                        provider_transaction_id=locked_refund.gateway_refund_id,
                        provider_order_id=payment_reference,
                        idempotency_key=idemp_key,
                        raw_response=extra,
                    )

                total_succeeded = order.refunds.filter(
                    status=RefundStatusChoices.SUCCEEDED
                ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
                if total_succeeded >= order.total_amount:
                    order.payment_status = PaymentStatusChoices.REFUNDED
                    order.save(update_fields=['payment_status', 'updated_at'])

                from apps.identity.models import ApprovalRequest, ApprovalStatusChoices
                app_req = ApprovalRequest.objects.filter(
                    target_type='Refund',
                    target_id=str(locked_refund.id),
                    status=ApprovalStatusChoices.APPROVED,
                ).first()
                if app_req:
                    if app_req.execution_error:
                        app_req.execution_error = ""
                        app_req.save(update_fields=['execution_error', 'updated_at'])
                    app_req.mark_executed(
                        executor=actor or locked_refund.approved_by,
                        notes=f"Reconciled successfully via gateway inquiry. Ref: {locked_refund.gateway_refund_id}"
                    )

                record_audit_entry(
                    event_type="marketplace.refund.reconciled_success",
                    action="marketplace:refund.reconcile",
                    resource_type="Refund",
                    resource_id=str(locked_refund.id),
                    actor_id=actor.id if actor else None,
                    metadata={
                        "refund_number": locked_refund.refund_number,
                        "order_number": order.order_number,
                        "amount": str(locked_refund.amount),
                        "currency": locked_refund.currency,
                        "gateway_refund_id": locked_refund.gateway_refund_id,
                        "provider": provider.provider_name,
                        "attempts": attempts,
                    },
                )
                return locked_refund, "SUCCEEDED"

            elif inq_status == 'FAILED':
                # Definitive provider confirmation of failure transitions to FAILED
                locked_refund.status = RefundStatusChoices.FAILED
                locked_refund.failure_reason = ref_id_or_err or "Provider confirmed refund failed."
                locked_refund.next_reconciliation_at = None
                locked_refund.save(update_fields=['status', 'failure_reason', 'next_reconciliation_at', 'updated_at'])

                PaymentTransaction.objects.create(
                    order=order,
                    transaction_type=PaymentTransaction.TransactionTypeChoices.REFUND,
                    provider=provider.provider_name,
                    amount=locked_refund.amount,
                    currency=locked_refund.currency,
                    status=PaymentTransaction.StatusChoices.FAILED,
                    error_message=locked_refund.failure_reason,
                    provider_transaction_id=locked_refund.gateway_refund_id or '',
                    provider_order_id=payment_reference,
                    idempotency_key=idemp_key,
                    raw_response=extra,
                )

                record_audit_entry(
                    event_type="marketplace.refund.reconciled_failed",
                    action="marketplace:refund.reconcile",
                    resource_type="Refund",
                    resource_id=str(locked_refund.id),
                    actor_id=actor.id if actor else None,
                    metadata={
                        "refund_number": locked_refund.refund_number,
                        "order_number": order.order_number,
                        "reason": locked_refund.failure_reason,
                        "provider": provider.provider_name,
                        "attempts": attempts,
                    },
                )
                return locked_refund, "FAILED"

            else:
                # INCONCLUSIVE / NOT_FOUND / UNKNOWN / PROCESSING:
                # Treat NOT_FOUND as inconclusive by default.
                # Keep refund in PROCESSING_UNKNOWN while the outcome remains ambiguous.
                # Apply bounded exponential backoff: min(2^attempts, 60) minutes.
                backoff_minutes = min(2 ** attempts, 60)
                locked_refund.status = RefundStatusChoices.PROCESSING_UNKNOWN
                locked_refund.next_reconciliation_at = timezone.now() + datetime.timedelta(minutes=backoff_minutes)
                if inq_status == 'NOT_FOUND':
                    locked_refund.failure_reason = (
                        f"Provider reported no record found (attempt {attempts}). "
                        "Status remains ambiguous; awaiting gateway propagation, webhook, or authorized manual resolution."
                    )
                else:
                    locked_refund.failure_reason = f"Reconciliation attempt {attempts} inconclusive ({inq_status}): {ref_id_or_err}"
                locked_refund.save(update_fields=['status', 'next_reconciliation_at', 'failure_reason', 'updated_at'])

                record_audit_entry(
                    event_type="marketplace.refund.reconciliation_inconclusive",
                    action="marketplace:refund.reconcile",
                    resource_type="Refund",
                    resource_id=str(locked_refund.id),
                    actor_id=actor.id if actor else None,
                    metadata={
                        "refund_number": locked_refund.refund_number,
                        "order_number": order.order_number,
                        "attempts": attempts,
                        "next_retry": locked_refund.next_reconciliation_at.isoformat(),
                        "inq_status": inq_status,
                        "detail": ref_id_or_err,
                    },
                )
                return locked_refund, "INCONCLUSIVE"

    @classmethod
    def manual_resolve_unknown_refund(
        cls,
        refund: Any,
        actor: Any,
        resolution: str,
        reason: str = '',
        evidence: Optional[Dict[str, Any]] = None,
        approved_request: Optional[Any] = None,
        gateway_reference: Optional[str] = None,
        ticket_reference: Optional[str] = None,
    ) -> Refund:
        """
        Explicit authorized manual resolution procedure to release a refund hold
        from PROCESSING_UNKNOWN when reliable external provider evidence has been
        verified out-of-band by authorized personnel.
        Requires 'finance.payout' or Platform Administrator.
        Enforces server-side structured evidence validation (reason, gateway_reference, ticket_reference).
        Enforces Maker-Checker dual authorization for high-value financial resolutions.
        """
        has_perm = _is_platform_admin(actor) or _has_permission(actor, 'finance.payout')
        if not has_perm:
            raise DjangoValidationError("Permission denied: Manual resolution requires 'finance.payout' permission.")

        clean_reason = (reason or '').strip()
        if not clean_reason or len(clean_reason) < 10:
            raise DjangoValidationError("A comprehensive justification (minimum 10 characters) is required for manual resolution.")

        clean_res = (resolution or '').strip().upper()
        if clean_res not in (RefundStatusChoices.FAILED, RefundStatusChoices.CANCELLED):
            raise DjangoValidationError(f"Invalid manual resolution '{resolution}'. Allowed targets: FAILED, CANCELLED.")

        # Structured evidence server-side validation
        clean_gw_ref = ''
        clean_ticket_ref = ''
        if evidence and isinstance(evidence, dict):
            clean_gw_ref = str(
                gateway_reference
                or evidence.get('gateway_reference')
                or evidence.get('inquiry_evidence')
                or evidence.get('gateway_ref')
                or ''
            ).strip()
            clean_ticket_ref = str(
                ticket_reference
                or evidence.get('ticket_reference')
                or evidence.get('ticket_number')
                or evidence.get('reference_number')
                or evidence.get('support_ticket')
                or ''
            ).strip()
        else:
            clean_gw_ref = str(gateway_reference or '').strip()
            clean_ticket_ref = str(ticket_reference or '').strip()

        if not clean_gw_ref or len(clean_gw_ref) < 3:
            raise DjangoValidationError(
                "Structured evidence error: 'gateway_reference' (or verified inquiry evidence) is required for manual resolution. "
                "A free-text justification alone is not sufficient."
            )

        if not clean_ticket_ref or len(clean_ticket_ref) < 3:
            raise DjangoValidationError(
                "Structured evidence error: 'ticket_reference' (supporting ticket or incident number) is required for manual resolution. "
                "A free-text justification alone is not sufficient."
            )

        resolution_timestamp = timezone.now()
        structured_evidence = {
            "reason": clean_reason,
            "gateway_reference": clean_gw_ref,
            "ticket_reference": clean_ticket_ref,
            "actor_id": str(getattr(actor, 'id', '')),
            "actor_email": getattr(actor, 'email', str(actor)),
            "resolved_at": resolution_timestamp.isoformat(),
        }

        target_refund_id = refund if isinstance(refund, (str, uuid.UUID)) else refund.id
        refund_obj = refund if isinstance(refund, Refund) else Refund.objects.select_related('order').get(id=target_refund_id)

        # Maker-Checker dual authorization for high-value financial resolution
        from apps.identity.approval_service import ApprovalService
        from apps.identity.models import ApprovalRequest, ApprovalStatusChoices

        if ApprovalService.is_approval_required(action_type='MANUAL_REFUND_RESOLUTION', amount=refund_obj.amount, currency=refund_obj.currency):
            if approved_request is None:
                approved_req = ApprovalRequest.objects.filter(
                    target_type='Refund',
                    target_id=str(refund_obj.id),
                    action_type='MANUAL_REFUND_RESOLUTION',
                    status=ApprovalStatusChoices.APPROVED,
                ).order_by('-reviewed_at').first()

                if not approved_req:
                    pending_req = ApprovalRequest.objects.filter(
                        target_type='Refund',
                        target_id=str(refund_obj.id),
                        action_type='MANUAL_REFUND_RESOLUTION',
                        status=ApprovalStatusChoices.PENDING,
                    ).first()
                    if not pending_req:
                        pending_req = ApprovalService.create_request(
                            requester=actor,
                            action_type='MANUAL_REFUND_RESOLUTION',
                            target_type='Refund',
                            target_id=str(refund_obj.id),
                            amount=refund_obj.amount,
                            currency=refund_obj.currency,
                            reason=clean_reason,
                            payload={
                                "refund_id": str(refund_obj.id),
                                "refund_number": refund_obj.refund_number,
                                "order_id": str(refund_obj.order.id),
                                "order_number": refund_obj.order.order_number,
                                "amount": str(refund_obj.amount),
                                "currency": refund_obj.currency,
                                "resolution": clean_res,
                                "reason": clean_reason,
                                "gateway_reference": clean_gw_ref,
                                "ticket_reference": clean_ticket_ref,
                                "evidence": structured_evidence,
                            },
                        )
                    threshold = ApprovalService.get_threshold_for_currency(refund_obj.currency)
                    raise DjangoValidationError(
                        f"High-value manual refund resolution ({refund_obj.currency} {refund_obj.amount}) exceeds the maker-checker threshold ({refund_obj.currency} {threshold}). "
                        f"Dual authorization approval is required before execution (Request ID: {pending_req.id})."
                    )
                approved_request = approved_req

        with transaction.atomic():
            locked = Refund.objects.select_for_update().select_related('order').get(id=target_refund_id)
            if locked.status != RefundStatusChoices.PROCESSING_UNKNOWN:
                raise DjangoValidationError(
                    f"Cannot manually resolve refund {locked.refund_number}: current status is '{locked.status}', expected 'PROCESSING_UNKNOWN'."
                )

            if approved_request is not None:
                if approved_request.target_type != 'Refund' or str(approved_request.target_id) != str(locked.id):
                    raise DjangoValidationError(
                        f"Integrity violation: Approval request target ({approved_request.target_type}:{approved_request.target_id}) does not match this refund ({locked.id})."
                    )
                if approved_request.action_type != 'MANUAL_REFUND_RESOLUTION':
                    raise DjangoValidationError(
                        f"Integrity violation: Approval request action type is '{approved_request.action_type}', expected 'MANUAL_REFUND_RESOLUTION'."
                    )
                if approved_request.status == ApprovalStatusChoices.EXECUTED:
                    raise DjangoValidationError("Approval request has already been executed.")
                if approved_request.status != ApprovalStatusChoices.APPROVED:
                    raise DjangoValidationError(
                        f"Cannot execute resolution: Approval request is in '{approved_request.status}' status, not APPROVED."
                    )
                if approved_request.amount is not None and Decimal(str(approved_request.amount)) != Decimal(str(locked.amount)):
                    raise DjangoValidationError(
                        f"Integrity violation: Approved amount ({approved_request.currency} {approved_request.amount}) does not match current refund amount ({locked.currency} {locked.amount}). Re-authorization is required."
                    )
                if approved_request.currency and approved_request.currency.upper() != locked.currency.upper():
                    raise DjangoValidationError(
                        f"Integrity violation: Approved currency ({approved_request.currency}) does not match current refund currency ({locked.currency}). Re-authorization is required."
                    )

                # Payload resolution integrity validation
                approved_payload = approved_request.payload if isinstance(approved_request.payload, dict) else {}
                raw_approved_res = approved_payload.get("resolution")
                if not raw_approved_res or not str(raw_approved_res).strip():
                    raise DjangoValidationError("Integrity violation: Approval request payload is missing approved resolution.")
                approved_res = str(raw_approved_res).strip().upper()
                if approved_res not in (RefundStatusChoices.FAILED, RefundStatusChoices.CANCELLED):
                    raise DjangoValidationError(
                        f"Integrity violation: Approval request payload contains invalid resolution '{raw_approved_res}'. Allowed targets: FAILED, CANCELLED."
                    )
                if approved_res != clean_res:
                    raise DjangoValidationError(
                        f"Integrity violation: Requested resolution '{clean_res}' does not match approved resolution '{approved_res}'. Changing resolution after approval is prohibited."
                    )

                if approved_request.approver:
                    structured_evidence["approver_id"] = str(approved_request.approver.id)
                    structured_evidence["approver_email"] = approved_request.approver.email

            locked.status = clean_res
            locked.failure_reason = f"[Manual Resolution by {getattr(actor, 'email', str(actor))} | Ref: {clean_gw_ref} | Ticket: {clean_ticket_ref}]: {clean_reason}"
            locked.next_reconciliation_at = None
            locked.save(update_fields=['status', 'failure_reason', 'next_reconciliation_at', 'updated_at'])

            PaymentTransaction.objects.create(
                order=locked.order,
                transaction_type=PaymentTransaction.TransactionTypeChoices.REFUND,
                provider=locked.gateway_provider or 'MANUAL_OVERRIDE',
                amount=locked.amount,
                currency=locked.currency,
                status=PaymentTransaction.StatusChoices.FAILED if clean_res == RefundStatusChoices.FAILED else PaymentTransaction.StatusChoices.CANCELLED,
                error_message=locked.failure_reason,
                provider_order_id=locked.order.payment_reference or '',
                idempotency_key=locked.idempotency_key or locked.refund_number,
                raw_response={
                    "manual_override": True,
                    "structured_evidence": structured_evidence,
                    "actor_id": str(getattr(actor, 'id', '')),
                    "reason": clean_reason,
                    "gateway_reference": clean_gw_ref,
                    "ticket_reference": clean_ticket_ref,
                },
            )

            record_audit_entry(
                event_type="marketplace.refund.manual_resolution",
                action="marketplace:refund.manual_resolve",
                resource_type="Refund",
                resource_id=str(locked.id),
                actor_id=getattr(actor, 'id', None),
                metadata={
                    "refund_number": locked.refund_number,
                    "order_number": locked.order.order_number,
                    "previous_status": RefundStatusChoices.PROCESSING_UNKNOWN,
                    "resolved_status": clean_res,
                    "reason": clean_reason,
                    "gateway_reference": clean_gw_ref,
                    "ticket_reference": clean_ticket_ref,
                    "evidence": structured_evidence,
                },
            )

            if approved_request:
                approved_request.mark_executed(
                    executor=actor,
                    notes=f"Manual resolution to {clean_res} executed. Ref: {clean_gw_ref}, Ticket: {clean_ticket_ref}"
                )
                record_audit_entry(
                    event_type="approval.request.execution.success",
                    action="approval:request.execute",
                    resource_type="ApprovalRequest",
                    resource_id=str(approved_request.id),
                    actor_id=actor.id if actor else None,
                    metadata={
                        "action_type": "MANUAL_REFUND_RESOLUTION",
                        "refund_number": locked.refund_number,
                        "resolved_status": clean_res,
                        "gateway_reference": clean_gw_ref,
                        "ticket_reference": clean_ticket_ref,
                    },
                )

            return locked

    @classmethod
    def reconcile_all_pending_unknown(cls, max_batch: int = 50, **kwargs) -> Dict[str, Any]:
        """
        Background reconciliation runner to process all refunds currently in PROCESSING_UNKNOWN status
        whose next_reconciliation_at is in the past.
        Uses concurrency-safe batch reservation with select_for_update(skip_locked=True) where supported,
        preventing duplicate external gateway inquiries and ensuring multi-worker safety without holding
        database locks during external HTTP requests.
        """
        import datetime
        from django.db import connection

        limit = kwargs.get('limit') or kwargs.get('batch_size') or max_batch
        now = timezone.now()
        lease_window = now + datetime.timedelta(minutes=10)

        # 1. Concurrency-safe reservation phase: atomically select and advance next_reconciliation_at
        reserved_refund_ids = []
        with transaction.atomic():
            base_qs = Refund.objects.filter(
                status=RefundStatusChoices.PROCESSING_UNKNOWN,
            ).filter(
                models.Q(next_reconciliation_at__isnull=True) | models.Q(next_reconciliation_at__lte=now)
            )

            # PostgreSQL supports skip_locked=True to allow parallel workers to claim disjoint batches
            if connection.vendor == 'postgresql':
                claimed_qs = base_qs.select_for_update(skip_locked=True)[:limit]
            else:
                claimed_qs = base_qs[:limit]

            reserved_refund_ids = list(claimed_qs.values_list('id', flat=True))
            if reserved_refund_ids:
                Refund.objects.filter(id__in=reserved_refund_ids).update(
                    next_reconciliation_at=lease_window,
                    updated_at=now,
                )

        # 2. Execution phase: inquire external gateway provider OUTSIDE any database transaction or row lock
        results: Dict[str, Any] = {
            "total_evaluated": 0,
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "unknown": 0,
            "refund_details": [],
        }

        for rfnd_id in reserved_refund_ids:
            results["total_evaluated"] += 1
            results["processed"] += 1
            try:
                reconciled_rfnd, outcome = cls.reconcile_refund(rfnd_id)
                if outcome == "SUCCEEDED":
                    results["succeeded"] += 1
                elif outcome == "FAILED":
                    results["failed"] += 1
                else:
                    results["unknown"] += 1
                results["refund_details"].append({
                    "refund_number": reconciled_rfnd.refund_number,
                    "outcome": outcome,
                    "status": reconciled_rfnd.status,
                })
            except Exception as item_err:
                logger.exception("Error reconciling refund %s during batch execution: %s", rfnd_id, item_err)
                results["unknown"] += 1
                results["refund_details"].append({
                    "refund_id": str(rfnd_id),
                    "outcome": "ERROR",
                    "error": str(item_err),
                })

        return results


    @classmethod
    def approve_refund(
        cls,
        refund: Refund,
        actor: Any,
        notes: str = '',
    ) -> Refund:
        """
        Approves a pending refund and dispatches gateway refund or marks manual payout as settled.
        """
        has_perm = (
            _is_platform_admin(actor)
            or _has_permission(actor, 'order.refund')
            or _has_permission(actor, 'finance.payout')
        )
        if not has_perm:
            raise DjangoValidationError("Permission denied: You do not have the 'order.refund' permission.")

        with transaction.atomic():
            locked = Refund.objects.select_for_update().get(id=refund.id)
            if locked.status not in (RefundStatusChoices.PENDING, RefundStatusChoices.FAILED):
                raise DjangoValidationError(
                    f"Cannot approve refund {locked.refund_number} with status '{locked.status}'."
                )

            locked.approved_by = actor
            if notes:
                locked.notes = f"{locked.notes}\n[Approved]: {notes}".strip()
            locked.save(update_fields=['approved_by', 'notes', 'updated_at'])

            record_audit_entry(
                event_type="marketplace.refund.approved",
                action="marketplace:refund.approve",
                resource_type="Refund",
                resource_id=str(locked.id),
                actor_id=actor.id if actor else None,
                metadata={
                    "refund_number": locked.refund_number,
                    "order_number": locked.order.order_number,
                    "amount": str(locked.amount),
                    "method": locked.refund_method,
                },
            )

            has_payout_perm = _is_platform_admin(actor) or _has_permission(actor, 'finance.payout')
            if locked.refund_method == RefundMethodChoices.ORIGINAL_PAYMENT:
                if has_payout_perm:
                    return cls.dispatch_gateway_refund(locked, actor)
                else:
                    # Approved by staff with 'order.refund' (e.g. Dispute Manager); transitioned to PROCESSING awaiting Finance Officer dispatch
                    locked.status = RefundStatusChoices.PROCESSING
                    locked.save(update_fields=['status', 'updated_at'])
                    return locked
            else:
                return cls.process_refund(locked, actor, notes=notes)

    @classmethod
    def reject_refund(
        cls,
        refund: Refund,
        actor: Any,
        reason: str,
    ) -> Refund:
        """
        Rejects a refund request, recording cancellation and failure reason.
        """
        has_perm = (
            _is_platform_admin(actor)
            or _has_permission(actor, 'order.refund')
            or _has_permission(actor, 'finance.payout')
        )
        if not has_perm:
            raise DjangoValidationError("Permission denied: You do not have the 'order.refund' permission.")

        rejection_reason = (reason or '').strip()
        if not rejection_reason:
            raise DjangoValidationError("A rejection reason must be provided.")

        with transaction.atomic():
            locked = Refund.objects.select_for_update().get(id=refund.id)
            if locked.status not in (RefundStatusChoices.PENDING, RefundStatusChoices.FAILED):
                raise DjangoValidationError(
                    f"Cannot reject refund {locked.refund_number} with status '{locked.status}'."
                )

            locked.status = RefundStatusChoices.CANCELLED
            locked.failure_reason = rejection_reason
            locked.approved_by = actor
            locked.save(update_fields=['status', 'failure_reason', 'approved_by', 'updated_at'])

            record_audit_entry(
                event_type="marketplace.refund.rejected",
                action="marketplace:refund.reject",
                resource_type="Refund",
                resource_id=str(locked.id),
                actor_id=actor.id if actor else None,
                metadata={
                    "refund_number": locked.refund_number,
                    "order_number": locked.order.order_number,
                    "amount": str(locked.amount),
                    "rejection_reason": rejection_reason,
                },
            )

        return locked


# =============================================================================
# 3. DISPUTE MANAGEMENT SERVICE
# =============================================================================

class DisputeService:
    """
    Manages commercial dispute creation, multi-party messaging, decision recording,
    and resolution lifecycle with full audit tracking.
    """

    @classmethod
    def create_dispute(
        cls,
        order: Order,
        buyer: Any,
        category: str,
        description: str,
        evidence_urls: Optional[List[str]] = None,
        priority: str = 'MEDIUM',
    ) -> Dispute:
        """
        Allows buyer to raise a commercial dispute for an order.
        """
        if order.buyer_id != buyer.id and not _is_staff_or_admin(buyer):
            raise DjangoValidationError("Permission denied: You can only raise disputes on your own orders.")

        cat = category.strip().upper()
        if cat not in DisputeCategoryChoices.values:
            raise DjangoValidationError(f"Invalid dispute category '{category}'.")

        prio = priority.strip().upper()
        if prio not in DisputePriorityChoices.values:
            prio = DisputePriorityChoices.MEDIUM

        # Check for open duplicate disputes on this order
        existing_open = Dispute.objects.filter(
            order=order,
            status__in=[DisputeStatusChoices.OPEN, DisputeStatusChoices.UNDER_REVIEW, DisputeStatusChoices.ESCALATED],
        ).first()
        if existing_open:
            raise DjangoValidationError(
                f"An active dispute ({existing_open.dispute_number}) is already open for order {order.order_number}."
            )

        # Resolve primary seller
        first_item = order.items.select_related('listing__seller').first()
        seller = first_item.listing.seller if (first_item and first_item.listing and first_item.listing.seller) else order.buyer

        with transaction.atomic():
            disp_num = f"DISP-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

            dispute = Dispute.objects.create(
                dispute_number=disp_num,
                order=order,
                buyer=buyer,
                seller=seller,
                category=cat,
                status=DisputeStatusChoices.OPEN,
                priority=prio,
                description=description,
                evidence_urls=evidence_urls or [],
            )

            # Create initial milestone event
            DisputeEvent.objects.create(
                dispute=dispute,
                actor=buyer,
                event_type=DisputeEventTypeChoices.STATUS_CHANGE,
                message=f"Dispute opened by buyer: {description[:100]}...",
                attachments=evidence_urls or [],
            )

            record_audit_entry(
                event_type="marketplace.dispute.created",
                action="marketplace:dispute.create",
                resource_type="Dispute",
                resource_id=str(dispute.id),
                actor_id=buyer.id,
                metadata={
                    "dispute_number": dispute.dispute_number,
                    "order_number": order.order_number,
                    "category": dispute.category,
                    "priority": dispute.priority,
                },
            )

        return dispute

    @classmethod
    def update_dispute_status(
        cls,
        dispute: Dispute,
        actor: Any,
        new_status: str,
        resolution: str = '',
        resolution_notes: str = '',
    ) -> Dispute:
        """
        Operations staff (with 'dispute.manage' permission) or platform admins
        update dispute status, escalate, or record official decisions.
        """
        has_perm = _has_permission(actor, 'dispute.manage')
        if not has_perm:
            record_denied_audit_entry(
                action="marketplace:dispute.status_update",
                resource_type="Dispute",
                resource_id=str(dispute.id),
                actor_id=actor.id if actor else None,
                reason_code="PERMISSION_DENIED_DISPUTE_MANAGE",
            )
            raise DjangoValidationError("Permission denied: You do not have the 'dispute.manage' permission.")

        target = new_status.strip().upper()
        if target not in DisputeStatusChoices.values:
            raise DjangoValidationError(f"Invalid dispute status '{target}'.")

        with transaction.atomic():
            old_status = dispute.status
            dispute.status = target

            if target in (DisputeStatusChoices.RESOLVED, DisputeStatusChoices.REJECTED):
                dispute.resolution = resolution or (
                    DisputeResolutionChoices.REFUND_ISSUED if target == DisputeStatusChoices.RESOLVED else DisputeResolutionChoices.BUYER_REJECTED
                )
                dispute.resolution_notes = resolution_notes
                dispute.resolved_by = actor
                dispute.resolved_at = timezone.now()

                DisputeEvent.objects.create(
                    dispute=dispute,
                    actor=actor,
                    event_type=DisputeEventTypeChoices.DECISION_RECORDED,
                    message=f"Dispute {target.lower()}: {resolution_notes or dispute.resolution}",
                )
            else:
                DisputeEvent.objects.create(
                    dispute=dispute,
                    actor=actor,
                    event_type=DisputeEventTypeChoices.STATUS_CHANGE,
                    message=f"Dispute status moved from {old_status} to {target}. Notes: {resolution_notes}",
                )

            dispute.save()

            record_audit_entry(
                event_type="marketplace.dispute.status_updated",
                action="marketplace:dispute.status_update",
                resource_type="Dispute",
                resource_id=str(dispute.id),
                actor_id=actor.id,
                metadata={
                    "dispute_number": dispute.dispute_number,
                    "previous_status": old_status,
                    "new_status": target,
                    "resolution": dispute.resolution,
                    "resolution_notes": resolution_notes,
                },
            )

        return dispute

    @classmethod
    def add_dispute_message(
        cls,
        dispute: Dispute,
        actor: Any,
        message: str,
        attachments: Optional[List[str]] = None,
    ) -> DisputeEvent:
        """
        Adds a message or evidence document to a dispute.
        Restricted to the buyer, seller, or authorized operations staff.
        """
        is_buyer = dispute.buyer_id == actor.id
        is_seller = dispute.seller_id == actor.id or _is_seller_authorized_for_order(actor, dispute.order)
        is_staff = _has_permission(actor, 'dispute.manage')

        if not (is_buyer or is_seller or is_staff):
            record_denied_audit_entry(
                action="marketplace:dispute.add_message",
                resource_type="Dispute",
                resource_id=str(dispute.id),
                actor_id=actor.id if actor else None,
                reason_code="UNAUTHORIZED_DISPUTE_PARTICIPANT",
            )
            raise DjangoValidationError("Permission denied: You are not a party to this dispute.")

        if not message.strip():
            raise DjangoValidationError("Message content cannot be blank.")

        with transaction.atomic():
            evt = DisputeEvent.objects.create(
                dispute=dispute,
                actor=actor,
                event_type=DisputeEventTypeChoices.COMMENT,
                message=message.strip(),
                attachments=attachments or [],
            )

            record_audit_entry(
                event_type="marketplace.dispute.message_added",
                action="marketplace:dispute.message_add",
                resource_type="Dispute",
                resource_id=str(dispute.id),
                actor_id=actor.id,
                metadata={
                    "dispute_number": dispute.dispute_number,
                    "has_attachments": bool(attachments),
                },
            )

        return evt
