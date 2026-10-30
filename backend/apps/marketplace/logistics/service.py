import uuid
import logging
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError
from django.db.models import Sum, Q

from apps.marketplace.models import (
    Order,
    OrderItem,
    OrderStatusChoices,
    PaymentMethodChoices,
    PaymentStatusChoices,
    Shipment,
    ShipmentItem,
    TrackingEvent,
    ShipmentStatusChoices,
    CarrierChoices,
)
from apps.marketplace.logistics.providers import get_carrier_provider
from platform_core.audit.writer import record_audit_entry

logger = logging.getLogger(__name__)

VALID_SHIPMENT_STATUS_TRANSITIONS: Dict[str, List[str]] = {
    ShipmentStatusChoices.CREATED: [
        ShipmentStatusChoices.DISPATCHED,
        ShipmentStatusChoices.CANCELLED,
    ],
    ShipmentStatusChoices.DISPATCHED: [
        ShipmentStatusChoices.IN_TRANSIT,
        ShipmentStatusChoices.OUT_FOR_DELIVERY,
        ShipmentStatusChoices.DELIVERED,
        ShipmentStatusChoices.FAILED_DELIVERY,
        ShipmentStatusChoices.CANCELLED,
    ],
    ShipmentStatusChoices.IN_TRANSIT: [
        ShipmentStatusChoices.OUT_FOR_DELIVERY,
        ShipmentStatusChoices.DELIVERED,
        ShipmentStatusChoices.FAILED_DELIVERY,
        ShipmentStatusChoices.CANCELLED,
    ],
    ShipmentStatusChoices.OUT_FOR_DELIVERY: [
        ShipmentStatusChoices.DELIVERED,
        ShipmentStatusChoices.FAILED_DELIVERY,
        ShipmentStatusChoices.CANCELLED,
    ],
    ShipmentStatusChoices.FAILED_DELIVERY: [
        ShipmentStatusChoices.OUT_FOR_DELIVERY,
        ShipmentStatusChoices.RETURNED,
        ShipmentStatusChoices.CANCELLED,
    ],
    ShipmentStatusChoices.DELIVERED: [],
    ShipmentStatusChoices.RETURNED: [],
    ShipmentStatusChoices.CANCELLED: [],
}


class ShipmentService:
    """
    Authoritative logistics orchestration service managing multi-seller shipments,
    lifecycle transitions, tracking checkpoints, and parent order fulfillment synchronization.
    """

    @staticmethod
    def generate_shipment_number() -> str:
        date_str = timezone.now().strftime("%Y%m%d")
        rand_hex = uuid.uuid4().hex[:8].upper()
        return f"SHP-{date_str}-{rand_hex}"

    @classmethod
    def create_seller_shipment(
        cls,
        order: Order,
        seller: Any,
        items_payload: List[Dict[str, Any]],
        carrier: str = CarrierChoices.OTHER,
        carrier_name: str = "",
        tracking_number: str = "",
        tracking_url: str = "",
        estimated_delivery_at: Optional[Any] = None,
        delivery_notes: str = "",
        dispatch_immediately: bool = False,
        actor: Optional[Any] = None,
    ) -> Shipment:
        """
        Creates a new shipment for the seller's items in an order.
        Enforces item ownership, prevents excessive quantity allocations,
        and records initial tracking events.
        """
        if order.status == OrderStatusChoices.CANCELLED:
            raise ValidationError("Cannot create shipment for a cancelled order.")

        # Online orders must be paid before dispatch
        if order.payment_method == PaymentMethodChoices.ONLINE and order.payment_status != PaymentStatusChoices.PAID:
            raise ValidationError("Cannot create shipment for an unpaid online order. Payment must be confirmed first.")

        if not items_payload:
            raise ValidationError("At least one order item must be included in the shipment.")

        carrier_adapter = get_carrier_provider(carrier)
        if tracking_number and not carrier_adapter.validate_tracking_reference(tracking_number):
            raise ValidationError(f"Invalid tracking reference format for carrier '{carrier}'.")

        if not tracking_url and tracking_number:
            tracking_url = carrier_adapter.generate_tracking_url(tracking_number)

        clean_carrier_name = carrier_name.strip()
        if not clean_carrier_name:
            clean_carrier_name = dict(CarrierChoices.choices).get(carrier, carrier)

        with transaction.atomic():
            # Validate each item belongs to the seller and has remaining unfulfilled quantity
            allocated_items: List[Tuple[OrderItem, int]] = []
            seller_org_ids = set()
            if hasattr(seller, 'organisation_memberships'):
                seller_org_ids = set(
                    seller.organisation_memberships.filter(is_active=True).values_list('organisation_id', flat=True)
                )

            for alloc in items_payload:
                order_item_id = str(alloc.get('order_item_id') or alloc.get('order_item') or '')
                qty = int(alloc.get('quantity', 1))
                if qty <= 0:
                    raise ValidationError("Allocated shipment quantity must be greater than zero.")

                order_item = order.items.filter(id=order_item_id).select_related('listing').first()
                if not order_item:
                    raise ValidationError(f"Order item '{order_item_id}' not found in order {order.order_number}.")

                # Enforce seller authorization: item must belong to seller or seller's organisation
                listing = order_item.listing
                is_authorized = False
                if listing and (listing.seller_id == seller.id or listing.organisation_id in seller_org_ids):
                    is_authorized = True

                if not is_authorized:
                    raise ValidationError(
                        f"You are not authorized to fulfill item '{order_item.title}' (belongs to another seller)."
                    )

                # Check already shipped quantity across active shipments
                already_allocated = (
                    order_item.shipment_items.exclude(shipment__status=ShipmentStatusChoices.CANCELLED).aggregate(
                        total=Sum('quantity')
                    )['total']
                    or 0
                )
                remaining_qty = order_item.quantity - already_allocated
                if qty > remaining_qty:
                    raise ValidationError(
                        f"Cannot allocate {qty} unit(s) of '{order_item.title}'. "
                        f"Only {remaining_qty} unit(s) remaining to fulfill."
                    )

                allocated_items.append((order_item, qty))

            initial_status = ShipmentStatusChoices.DISPATCHED if dispatch_immediately else ShipmentStatusChoices.CREATED
            dispatched_timestamp = timezone.now() if dispatch_immediately else None

            shipment = Shipment.objects.create(
                order=order,
                seller=seller,
                organisation=order_item.listing.organisation if order_item.listing else None,
                shipment_number=cls.generate_shipment_number(),
                carrier=carrier,
                carrier_name=clean_carrier_name,
                tracking_number=tracking_number.strip(),
                tracking_url=tracking_url.strip(),
                status=initial_status,
                dispatched_at=dispatched_timestamp,
                estimated_delivery_at=estimated_delivery_at,
                delivery_notes=delivery_notes.strip(),
            )

            for order_item, qty in allocated_items:
                ShipmentItem.objects.create(
                    shipment=shipment,
                    order_item=order_item,
                    quantity=qty,
                )

            # Record initial tracking event
            initial_desc = (
                f"Package dispatched with {clean_carrier_name} (Tracking: {tracking_number})"
                if dispatch_immediately
                else f"Shipment package created with {len(allocated_items)} item(s)."
            )
            TrackingEvent.objects.create(
                shipment=shipment,
                status=initial_status,
                location=order.seller_state or "Seller Warehouse",
                description=initial_desc,
                event_timestamp=timezone.now(),
            )

            # If dispatched immediately, synchronize order status
            if dispatch_immediately:
                cls._synchronize_order_status(order, actor=actor or seller)

            record_audit_entry(
                event_type="marketplace.shipment.created",
                action="marketplace:shipment.create",
                resource_type="Shipment",
                resource_id=str(shipment.id),
                actor_id=(actor.id if actor else seller.id),
                metadata={
                    "shipment_number": shipment.shipment_number,
                    "order_number": order.order_number,
                    "status": initial_status,
                    "carrier": carrier,
                    "tracking_number": tracking_number,
                    "item_count": len(allocated_items),
                },
            )

            return shipment

    @classmethod
    def update_shipment_status(
        cls,
        shipment: Shipment,
        new_status: str,
        location: str = "",
        description: str = "",
        carrier_reference: str = "",
        actor: Optional[Any] = None,
    ) -> Shipment:
        """
        Advances shipment status according to permitted state machine rules.
        Appends tracking event, synchronizes parent order, and records audit trail.
        """
        current_status = shipment.status
        if current_status == new_status:
            return shipment

        valid_targets = VALID_SHIPMENT_STATUS_TRANSITIONS.get(current_status, [])
        if new_status not in valid_targets:
            raise ValidationError(
                f"Cannot transition shipment from '{current_status}' to '{new_status}'. "
                f"Permitted next transitions: {valid_targets or 'None (Terminal state)'}."
            )

        with transaction.atomic():
            now = timezone.now()
            shipment.status = new_status

            if new_status == ShipmentStatusChoices.DISPATCHED and not shipment.dispatched_at:
                shipment.dispatched_at = now
            elif new_status == ShipmentStatusChoices.DELIVERED and not shipment.delivered_at:
                shipment.delivered_at = now

            if carrier_reference and not shipment.tracking_number:
                shipment.tracking_number = carrier_reference.strip()

            shipment.save(update_fields=['status', 'dispatched_at', 'delivered_at', 'tracking_number', 'updated_at'])

            # Default status description if not provided
            event_desc = description.strip()
            if not event_desc:
                default_descriptions = {
                    ShipmentStatusChoices.DISPATCHED: f"Package dispatched via {shipment.carrier_name}.",
                    ShipmentStatusChoices.IN_TRANSIT: "Package is in transit between distribution hubs.",
                    ShipmentStatusChoices.OUT_FOR_DELIVERY: "Package is out for delivery with local courier.",
                    ShipmentStatusChoices.DELIVERED: "Package successfully delivered to destination address.",
                    ShipmentStatusChoices.FAILED_DELIVERY: "Delivery attempt was unsuccessful. Awaiting re-attempt or instructions.",
                    ShipmentStatusChoices.RETURNED: "Package returned to seller.",
                    ShipmentStatusChoices.CANCELLED: "Shipment was cancelled.",
                }
                event_desc = default_descriptions.get(new_status, f"Shipment status updated to {new_status}.")

            TrackingEvent.objects.create(
                shipment=shipment,
                status=new_status,
                location=location.strip() or shipment.order.shipping_city,
                description=event_desc,
                event_timestamp=now,
            )

            # Synchronize parent order status
            cls._synchronize_order_status(shipment.order, actor=actor)

            record_audit_entry(
                event_type="marketplace.shipment.status_updated",
                action="marketplace:shipment.update_status",
                resource_type="Shipment",
                resource_id=str(shipment.id),
                actor_id=(actor.id if actor else shipment.seller_id),
                metadata={
                    "shipment_number": shipment.shipment_number,
                    "order_number": shipment.order.order_number,
                    "previous_status": current_status,
                    "new_status": new_status,
                    "location": location,
                },
            )

            return shipment

    @classmethod
    def add_tracking_event(
        cls,
        shipment: Shipment,
        status: str,
        description: str,
        location: str = "",
        event_timestamp: Optional[Any] = None,
        external_checkpoint_id: str = "",
        actor: Optional[Any] = None,
    ) -> TrackingEvent:
        """
        Appends an event to the shipment's tracking timeline.
        Guarantees idempotent handling for external checkpoint IDs.
        """
        clean_ext_id = (external_checkpoint_id or "").strip()
        if clean_ext_id:
            existing = shipment.tracking_events.filter(external_checkpoint_id=clean_ext_id).first()
            if existing:
                logger.info(
                    "Duplicate external checkpoint '%s' received for shipment %s; skipping.",
                    clean_ext_id,
                    shipment.shipment_number,
                )
                return existing

        ts = event_timestamp or timezone.now()
        with transaction.atomic():
            event = TrackingEvent.objects.create(
                shipment=shipment,
                status=status,
                location=location.strip(),
                description=description.strip(),
                event_timestamp=ts,
                external_checkpoint_id=clean_ext_id,
            )

            # If the event represents a valid forward transition, update the shipment status
            if status != shipment.status and status in VALID_SHIPMENT_STATUS_TRANSITIONS.get(shipment.status, []):
                cls.update_shipment_status(
                    shipment=shipment,
                    new_status=status,
                    location=location,
                    description=description,
                    actor=actor,
                )

            return event

    @classmethod
    def _synchronize_order_status(cls, order: Order, actor: Optional[Any] = None) -> None:
        """
        Synchronizes parent order fulfillment status based on constituent shipments.
        - If any shipment is dispatched/in-transit and order is confirmed: advances to PROCESSING.
        - If ALL order items are delivered across all shipments: advances to COMPLETED.
        - Preserves existing CANCELLED status.
        - Never touches payment or COD collection statuses.
        """
        if order.status == OrderStatusChoices.CANCELLED:
            return

        all_shipments = list(order.shipments.exclude(status=ShipmentStatusChoices.CANCELLED))
        if not all_shipments:
            return

        has_active_fulfillment = any(
            s.status in (
                ShipmentStatusChoices.DISPATCHED,
                ShipmentStatusChoices.IN_TRANSIT,
                ShipmentStatusChoices.OUT_FOR_DELIVERY,
                ShipmentStatusChoices.DELIVERED,
            )
            for s in all_shipments
        )

        old_order_status = order.status
        new_order_status = old_order_status

        # 1. Advance to PROCESSING if active dispatch underway and order was confirmed/pending
        if has_active_fulfillment and old_order_status in (
            OrderStatusChoices.CONFIRMED,
            OrderStatusChoices.PENDING_CONFIRMATION,
        ):
            new_order_status = OrderStatusChoices.PROCESSING

        # 2. Check if all items in order are 100% delivered
        all_items = list(order.items.all())
        all_delivered = True
        if not all_items:
            all_delivered = False

        for item in all_items:
            delivered_units = (
                item.shipment_items.filter(
                    shipment__status=ShipmentStatusChoices.DELIVERED
                ).aggregate(total=Sum('quantity'))['total']
                or 0
            )
            if delivered_units < item.quantity:
                all_delivered = False
                break

        if all_delivered and old_order_status != OrderStatusChoices.COMPLETED:
            new_order_status = OrderStatusChoices.COMPLETED

        if new_order_status != old_order_status:
            order.status = new_order_status
            order.save(update_fields=['status', 'updated_at'])

            record_audit_entry(
                event_type="marketplace.order.status_synchronized",
                action="marketplace:order.synchronize_fulfillment",
                resource_type="Order",
                resource_id=str(order.id),
                actor_id=(actor.id if actor else None),
                metadata={
                    "order_number": order.order_number,
                    "previous_status": old_order_status,
                    "new_status": new_order_status,
                    "reason": "Synchronized from shipment progress",
                },
            )
