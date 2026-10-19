from django.db import transaction
from django.core.exceptions import ValidationError
from platform_core.audit.writer import record_audit_entry
from common.middleware import get_current_correlation_id
from .models import SparePartListing, StockMovement, StockMovementReasonChoices


def adjust_stock(
    listing: SparePartListing,
    delta: int,
    reason: str,
    actor=None,
    note: str = "",
) -> StockMovement:
    """Adjusts stock for a SparePartListing under a row-level lock.

    Appends an immutable StockMovement ledger entry and records an audit log.
    Rejects delta == 0 and any adjustment that would result in negative stock.
    Stock changes on an APPROVED listing keep it APPROVED (no re-review triggered).
    """
    if delta == 0:
        raise ValidationError("Stock adjustment delta cannot be zero.")

    with transaction.atomic():
        # Row-level locking to prevent concurrent lost updates or race conditions
        locked_listing = SparePartListing.objects.select_for_update().get(pk=listing.pk)
        previous_quantity = locked_listing.stock_quantity
        resulting_quantity = previous_quantity + delta

        if resulting_quantity < 0:
            raise ValidationError(
                f"Stock adjustment would result in negative stock ({resulting_quantity}). "
                f"Current stock is {previous_quantity}."
            )

        # Update stock quantity without altering approval status
        locked_listing.stock_quantity = resulting_quantity
        locked_listing.save(update_fields=['stock_quantity', 'updated_at'])

        # Keep the in-memory object synchronized
        listing.stock_quantity = resulting_quantity
        listing.updated_at = locked_listing.updated_at

        # Append immutable StockMovement record
        movement = StockMovement.objects.create(
            listing=locked_listing,
            delta=delta,
            resulting_quantity=resulting_quantity,
            reason=reason,
            actor=actor,
            note=note or "",
        )

        # Write audit ledger entry
        actor_id = getattr(actor, 'id', None)
        record_audit_entry(
            event_type="inventory.stock.adjusted",
            action="marketplace:stock.adjust",
            resource_type="SparePartListing",
            resource_id=str(locked_listing.id),
            actor_id=actor_id,
            operating_org_id=locked_listing.organisation_id,
            correlation_id=get_current_correlation_id(),
            metadata={
                "listing_id": str(locked_listing.id),
                "part_name": locked_listing.name,
                "mpn": locked_listing.mpn,
                "previous_quantity": previous_quantity,
                "delta": delta,
                "resulting_quantity": resulting_quantity,
                "reason": reason,
                "note": note,
            },
        )

        return movement
