from decimal import Decimal
from typing import Optional
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError
from platform_core.audit.writer import record_audit_entry
from common.middleware import get_current_correlation_id
from .models import (
    SparePartListing,
    StockMovement,
    StockMovementReasonChoices,
    PriceChange,
    ListingStatusChoices,
)


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


_UNSET = object()


def change_price(
    listing: SparePartListing,
    new_price,
    new_compare_at_price=_UNSET,
    actor=None,
    note: str = "",
) -> Optional[PriceChange]:
    """Changes price and/or compare_at_price for a SparePartListing under a row-level lock.

    - Uses transaction.atomic and select_for_update
    - Validates price > 0 and price <= MAX_LISTING_PRICE
    - Validates compare_at_price > 0 and compare_at_price > price (if set)
    - If no actual change to price or compare_at_price, does nothing and returns None (no-op)
    - On an APPROVED listing, changing price or compare_at_price returns listing to PENDING_APPROVAL
    - Appends one immutable PriceChange record and records an audit log
    """
    max_price = getattr(settings, 'MAX_LISTING_PRICE', Decimal('100000'))
    if not isinstance(max_price, Decimal):
        max_price = Decimal(str(max_price))

    with transaction.atomic():
        locked_listing = SparePartListing.objects.select_for_update().get(pk=listing.pk)

        # Determine target price
        if new_price is not None:
            target_price = Decimal(str(new_price))
        else:
            target_price = locked_listing.price

        # Determine target compare_at_price
        if new_compare_at_price is not _UNSET:
            if new_compare_at_price is not None:
                target_compare_at = Decimal(str(new_compare_at_price))
            else:
                target_compare_at = None
        else:
            target_compare_at = locked_listing.compare_at_price

        # Validate target_price
        if target_price <= Decimal('0'):
            raise ValidationError("Price must be greater than zero.")
        if target_price > max_price:
            raise ValidationError(f"Price cannot exceed maximum allowable listing price of £{max_price}.")

        # Validate target_compare_at
        if target_compare_at is not None:
            if target_compare_at <= Decimal('0'):
                raise ValidationError("Compare-at price must be greater than zero.")
            if target_compare_at <= target_price:
                raise ValidationError("Compare-at price must be strictly greater than retail price.")

        # Check for actual change
        old_price = locked_listing.price
        old_compare_at = locked_listing.compare_at_price

        price_changed = (old_price != target_price)
        compare_at_changed = (old_compare_at != target_compare_at)

        if not price_changed and not compare_at_changed:
            return None  # No-op save: write nothing, do not demote

        # Update listing fields
        locked_listing.price = target_price
        locked_listing.compare_at_price = target_compare_at

        # On APPROVED listing, demote to PENDING_APPROVAL
        demoted = False
        if locked_listing.status == ListingStatusChoices.APPROVED:
            locked_listing.status = ListingStatusChoices.PENDING_APPROVAL
            locked_listing.rejection_reason = ""
            locked_listing.submitted_at = timezone.now()
            demoted = True

        update_fields = ['price', 'compare_at_price', 'updated_at']
        if demoted:
            update_fields.extend(['status', 'rejection_reason', 'submitted_at'])
        locked_listing.save(update_fields=update_fields)

        # Synchronize in-memory listing object
        listing.price = locked_listing.price
        listing.compare_at_price = locked_listing.compare_at_price
        listing.status = locked_listing.status
        listing.rejection_reason = locked_listing.rejection_reason
        listing.submitted_at = locked_listing.submitted_at
        listing.updated_at = locked_listing.updated_at

        # Append immutable PriceChange record
        price_change = PriceChange(
            listing=locked_listing,
            old_price=old_price,
            new_price=target_price,
            old_compare_at_price=old_compare_at,
            new_compare_at_price=target_compare_at,
            actor=actor,
            note=note or "",
        )
        price_change._state.adding = True
        price_change.save(force_insert=True)

        # Write audit ledger entry
        actor_id = getattr(actor, 'id', None)
        record_audit_entry(
            event_type="inventory.price.changed",
            action="marketplace:price.change",
            resource_type="SparePartListing",
            resource_id=str(locked_listing.id),
            actor_id=actor_id,
            operating_org_id=locked_listing.organisation_id,
            correlation_id=get_current_correlation_id(),
            metadata={
                "listing_id": str(locked_listing.id),
                "part_name": locked_listing.name,
                "mpn": locked_listing.mpn,
                "old_price": str(old_price),
                "new_price": str(target_price),
                "old_compare_at_price": str(old_compare_at) if old_compare_at is not None else None,
                "new_compare_at_price": str(target_compare_at) if target_compare_at is not None else None,
                "note": note or "",
            },
        )

        return price_change
