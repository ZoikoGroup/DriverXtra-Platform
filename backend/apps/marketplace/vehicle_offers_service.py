"""
Vehicle Purchase Offers and Order Placement Service Layer.

Provides business logic for:
1. Vehicle purchase offer negotiation (submission, counteroffers, rejection, withdrawal).
2. Atomic vehicle reservation with row-level locks (select_for_update).
3. Dedicated VehicleOrder creation with initial PAYMENT_PENDING status.
4. Statutory 5-business-day payment deadline calculation using dealership jurisdiction & holiday calendar.
5. Idempotent background expiration and release of unfulfilled reservations.
"""

import uuid
import logging
from datetime import datetime, date, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
from typing import Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError, PermissionDenied

from apps.identity.models import User
from apps.organisations.models import Organisation
from apps.marketplace.models import (
    VehicleListing,
    ListingStatusChoices,
    VehicleListingAvailabilityChoices,
    VehiclePurchaseOffer,
    VehicleOfferStatusChoices,
    VehicleOfferProposal,
    VehicleOfferAction,
    VehicleOfferActionTypeChoices,
    VehicleHandoverTypeChoices,
    VehicleOrder,
    VehicleOrderStatusChoices,
    VehiclePaymentReport,
    VehiclePaymentReportStatusChoices,
    VehiclePaymentEscalationLevelChoices,
    VehiclePaymentVerificationEvent,
    VehiclePaymentVerificationEventTypeChoices,
)
from platform_core.audit.writer import record_audit_entry

logger = logging.getLogger(__name__)


class VehicleAlreadyReservedError(ValidationError):
    """Raised when an attempt is made to reserve an already reserved vehicle listing."""
    pass


# =============================================================================
# 1. Jurisdiction Calendars and Business Day Calculation
# =============================================================================

def get_jurisdiction_holidays(market_tz_name: str, year: int) -> set[date]:
    """
    Returns statutory bank/public holidays for the given market jurisdiction and year.
    Strictly isolated from support-ticket SLA calendars.
    """
    holidays = set()

    # Allow environment/settings override for marketplace vehicle holidays
    configured = getattr(settings, 'MARKETPLACE_VEHICLE_HOLIDAYS', [])
    for item in configured:
        if isinstance(item, date):
            holidays.add(item)
        elif isinstance(item, str):
            try:
                holidays.add(datetime.strptime(item.strip(), "%Y-%m-%d").date())
            except ValueError:
                pass

    if 'Kolkata' in market_tz_name or 'India' in market_tz_name or 'Asia' in market_tz_name:
        # India Statutory National Holidays
        holidays.add(date(year, 1, 26))   # Republic Day
        holidays.add(date(year, 5, 1))    # May Day / Labor Day
        holidays.add(date(year, 8, 15))   # Independence Day
        holidays.add(date(year, 10, 2))   # Gandhi Jayanti
        holidays.add(date(year, 12, 25))  # Christmas Day
    else:
        # UK Statutory Bank Holidays (default market: Europe/London)
        holidays.add(date(year, 1, 1))    # New Year's Day
        holidays.add(date(year, 12, 25))  # Christmas Day
        holidays.add(date(year, 12, 26))  # Boxing Day

        # Approximate / well-known moveable UK bank holidays for 2026/2027
        if year == 2026:
            holidays.add(date(2026, 4, 3))   # Good Friday
            holidays.add(date(2026, 4, 6))   # Easter Monday
            holidays.add(date(2026, 5, 4))   # Early May Bank Holiday
            holidays.add(date(2026, 5, 25))  # Spring Bank Holiday
            holidays.add(date(2026, 8, 31))  # Summer Bank Holiday
            holidays.add(date(2026, 12, 28)) # Boxing Day Substitute
        elif year == 2027:
            holidays.add(date(2027, 3, 26))  # Good Friday
            holidays.add(date(2027, 3, 29))  # Easter Monday
            holidays.add(date(2027, 5, 3))   # Early May Bank Holiday
            holidays.add(date(2027, 5, 31))  # Spring Bank Holiday
            holidays.add(date(2027, 8, 30))  # Summer Bank Holiday

    return holidays


def calculate_payment_deadline(
    start_dt: datetime,
    market_tz_name: str = "Europe/London",
    business_days: int = 5,
) -> datetime:
    """
    Calculates the exact deadline 5 statutory business days after start_dt in the
    selling dealership's jurisdiction, excluding weekends and official bank holidays.
    """
    try:
        tz = ZoneInfo(market_tz_name)
    except Exception:
        tz = ZoneInfo("Europe/London")

    if timezone.is_naive(start_dt):
        local_dt = start_dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
    else:
        local_dt = start_dt.astimezone(tz)

    current_date = local_dt.date()
    added_days = 0

    while added_days < business_days:
        current_date += timedelta(days=1)
        # 0 = Monday, 4 = Friday, 5 = Saturday, 6 = Sunday
        if current_date.weekday() < 5:
            year_holidays = get_jurisdiction_holidays(market_tz_name, current_date.year)
            if current_date not in year_holidays:
                added_days += 1

    # Deadline is at the same time of day on the 5th business day
    deadline_local = datetime.combine(current_date, local_dt.time(), tzinfo=tz)
    return deadline_local.astimezone(ZoneInfo("UTC"))


def serialize_listing_snapshot(listing: VehicleListing) -> dict:
    """Creates an immutable JSON snapshot of vehicle listing specifications at purchase time."""
    return {
        "listing_id": str(listing.id),
        "title": listing.title,
        "make": listing.make.name if listing.make else "",
        "model": listing.model.name if listing.model else "",
        "variant": listing.variant.name if listing.variant else "",
        "year": listing.year,
        "vin": listing.vin,
        "masked_vin": listing.masked_vin,
        "registration_number": listing.registration_number,
        "masked_registration": listing.masked_registration,
        "mileage": listing.mileage,
        "fuel_type": listing.fuel_type,
        "transmission": listing.transmission,
        "body_type": listing.body_type,
        "price": str(listing.price),
        "currency": listing.currency,
        "condition": listing.condition,
        "location_city": listing.location_city,
        "primary_image_url": listing.primary_image_url,
        "seller_name": listing.seller.full_name,
        "seller_email": listing.seller.email,
        "organisation_name": listing.organisation.name if listing.organisation else "",
        "snapshot_created_at": timezone.now().isoformat(),
    }


# =============================================================================
# 2. Offer Submission and Negotiation Workflow
# =============================================================================

def submit_vehicle_offer(
    *,
    buyer: User,
    listing: VehicleListing,
    offered_price: Decimal,
    handover_preference: str = VehicleHandoverTypeChoices.COLLECTION,
    notes: str = "",
    metadata: Optional[dict] = None,
) -> VehiclePurchaseOffer:
    """
    Submits a formal buyer purchase offer on an active and available vehicle listing.
    Initializes round 1 with an immutable VehicleOfferProposal and VehicleOfferAction.
    """
    if listing.status != ListingStatusChoices.APPROVED or not listing.is_active:
        raise ValidationError("Purchase offers can only be submitted for active, approved vehicle listings.")

    if listing.availability_status != VehicleListingAvailabilityChoices.AVAILABLE:
        raise ValidationError(f"This vehicle is currently {listing.availability_status.lower()} and not accepting new purchase offers.")

    if listing.seller_id == buyer.id:
        raise ValidationError("You cannot submit a purchase offer on your own vehicle listing.")

    if listing.organisation and listing.organisation.is_member(buyer):
        raise ValidationError("You cannot submit a purchase offer on a vehicle owned by your organisation.")

    if offered_price <= Decimal("0"):
        raise ValidationError("Offered purchase price must be greater than zero.")

    # Check for existing active offer by this buyer on this vehicle
    active_existing = VehiclePurchaseOffer.objects.filter(
        listing=listing,
        buyer=buyer,
        status__in=[
            VehicleOfferStatusChoices.PENDING_DEALER,
            VehicleOfferStatusChoices.PENDING_BUYER,
        ],
    ).exists()
    if active_existing:
        raise ValidationError("You already have an active negotiation on this vehicle. Please view your existing offer.")

    with transaction.atomic():
        # Default offer expiry: 72 hours for dealer to review
        expires_at = timezone.now() + timedelta(hours=72)

        offer = VehiclePurchaseOffer.objects.create(
            listing=listing,
            buyer=buyer,
            seller=listing.seller,
            organisation=listing.organisation,
            status=VehicleOfferStatusChoices.PENDING_DEALER,
            current_round=1,
            currency=listing.currency,
            expires_at=expires_at,
        )

        proposal = VehicleOfferProposal.objects.create(
            offer=offer,
            revision_number=1,
            proposed_by=buyer,
            proposed_by_role="BUYER",
            offered_price=offered_price,
            currency=listing.currency,
            handover_preference=handover_preference,
            notes=notes,
        )

        VehicleOfferAction.objects.create(
            offer=offer,
            proposal=proposal,
            actor=buyer,
            action_type=VehicleOfferActionTypeChoices.SUBMITTED,
            notes=notes,
            metadata=metadata or {},
        )

        record_audit_entry(
            event_type="marketplace.vehicle_offer.submitted",
            action="marketplace:vehicle_offer.submit",
            resource_type="VehiclePurchaseOffer",
            resource_id=str(offer.id),
            actor_id=buyer.id,
            operating_org_id=listing.organisation_id,
            metadata={
                "offer_id": str(offer.id),
                "listing_id": str(listing.id),
                "offered_price": str(offered_price),
                "currency": listing.currency,
                "round": 1,
            },
        )

    return offer


def counter_vehicle_offer(
    *,
    actor: User,
    offer: VehiclePurchaseOffer,
    counter_price: Decimal,
    handover_preference: Optional[str] = None,
    notes: str = "",
    metadata: Optional[dict] = None,
) -> VehiclePurchaseOffer:
    """
    Submits a counteroffer in an active negotiation round.
    If dealer counters, offer moves to PENDING_BUYER.
    If buyer counters, offer moves to PENDING_DEALER.
    Creates a new immutable proposal revision and audit action.
    """
    if counter_price <= Decimal("0"):
        raise ValidationError("Counteroffer price must be greater than zero.")

    if not offer.is_active:
        raise ValidationError(f"Cannot counter an offer that is currently {offer.status}.")

    if offer.expires_at <= timezone.now():
        offer.status = VehicleOfferStatusChoices.EXPIRED
        offer.save(update_fields=['status', 'updated_at'])
        raise ValidationError("This offer has expired.")

    with transaction.atomic():
        # Re-fetch under lock
        locked_offer = VehiclePurchaseOffer.objects.select_for_update().get(pk=offer.pk)
        if not locked_offer.is_active:
            raise ValidationError("This offer is no longer active for negotiation.")

        is_seller_side = (
            locked_offer.seller_id == actor.id or
            (locked_offer.organisation and locked_offer.organisation.is_member(actor))
        )
        is_buyer_side = (locked_offer.buyer_id == actor.id)

        if not is_seller_side and not is_buyer_side:
            raise PermissionDenied("You are not a participant in this vehicle offer.")

        if is_seller_side:
            if locked_offer.status != VehicleOfferStatusChoices.PENDING_DEALER:
                raise ValidationError("It is not your turn to counter. Awaiting buyer response.")
            next_status = VehicleOfferStatusChoices.PENDING_BUYER
            proposer_role = "DEALER"
            # Buyer has 48 hours to respond to dealer counteroffer
            new_expiry = timezone.now() + timedelta(hours=48)
        else:
            if locked_offer.status != VehicleOfferStatusChoices.PENDING_BUYER:
                raise ValidationError("It is not your turn to counter. Awaiting dealer response.")
            next_status = VehicleOfferStatusChoices.PENDING_DEALER
            proposer_role = "BUYER"
            # Dealer has 72 hours to respond
            new_expiry = timezone.now() + timedelta(hours=72)

        locked_offer.current_round += 1
        locked_offer.status = next_status
        locked_offer.expires_at = new_expiry
        locked_offer.save(update_fields=['current_round', 'status', 'expires_at', 'updated_at'])

        latest_prop = locked_offer.latest_proposal
        chosen_handover = handover_preference or (latest_prop.handover_preference if latest_prop else VehicleHandoverTypeChoices.COLLECTION)

        proposal = VehicleOfferProposal.objects.create(
            offer=locked_offer,
            revision_number=locked_offer.current_round,
            proposed_by=actor,
            proposed_by_role=proposer_role,
            offered_price=counter_price,
            currency=locked_offer.currency,
            handover_preference=chosen_handover,
            notes=notes,
        )

        VehicleOfferAction.objects.create(
            offer=locked_offer,
            proposal=proposal,
            actor=actor,
            action_type=VehicleOfferActionTypeChoices.COUNTERED,
            notes=notes,
            metadata=metadata or {},
        )

        record_audit_entry(
            event_type="marketplace.vehicle_offer.countered",
            action="marketplace:vehicle_offer.counter",
            resource_type="VehiclePurchaseOffer",
            resource_id=str(locked_offer.id),
            actor_id=actor.id,
            operating_org_id=locked_offer.organisation_id,
            metadata={
                "offer_id": str(locked_offer.id),
                "round": locked_offer.current_round,
                "counter_price": str(counter_price),
                "proposer_role": proposer_role,
            },
        )

    return locked_offer


def reject_vehicle_offer(
    *,
    actor: User,
    offer: VehiclePurchaseOffer,
    reason: str = "",
) -> VehiclePurchaseOffer:
    """Explicitly rejects an active vehicle purchase offer or counteroffer."""
    if not offer.is_active:
        raise ValidationError(f"Cannot reject an offer that is currently {offer.status}.")

    with transaction.atomic():
        locked_offer = VehiclePurchaseOffer.objects.select_for_update().get(pk=offer.pk)
        if not locked_offer.is_active:
            raise ValidationError("This offer is no longer active.")

        is_seller_side = (
            locked_offer.seller_id == actor.id or
            (locked_offer.organisation and locked_offer.organisation.is_member(actor))
        )
        is_buyer_side = (locked_offer.buyer_id == actor.id)

        if not is_seller_side and not is_buyer_side:
            raise PermissionDenied("You are not a participant in this vehicle offer.")

        locked_offer.status = VehicleOfferStatusChoices.REJECTED
        locked_offer.rejected_at = timezone.now()
        locked_offer.save(update_fields=['status', 'rejected_at', 'updated_at'])

        VehicleOfferAction.objects.create(
            offer=locked_offer,
            proposal=locked_offer.latest_proposal,
            actor=actor,
            action_type=VehicleOfferActionTypeChoices.REJECTED,
            notes=reason,
        )

        record_audit_entry(
            event_type="marketplace.vehicle_offer.rejected",
            action="marketplace:vehicle_offer.reject",
            resource_type="VehiclePurchaseOffer",
            resource_id=str(locked_offer.id),
            actor_id=actor.id,
            operating_org_id=locked_offer.organisation_id,
            metadata={"offer_id": str(locked_offer.id), "reason": reason},
        )

    return locked_offer


def withdraw_vehicle_offer(
    *,
    actor: User,
    offer: VehiclePurchaseOffer,
    reason: str = "",
) -> VehiclePurchaseOffer:
    """Allows the party whose turn it is to withdraw their offer prior to acceptance."""
    if not offer.is_active:
        raise ValidationError(f"Cannot withdraw an offer that is currently {offer.status}.")

    with transaction.atomic():
        locked_offer = VehiclePurchaseOffer.objects.select_for_update().get(pk=offer.pk)
        if not locked_offer.is_active:
            raise ValidationError("This offer is no longer active.")

        is_buyer_side = (locked_offer.buyer_id == actor.id)
        is_seller_side = (
            locked_offer.seller_id == actor.id or
            (locked_offer.organisation and locked_offer.organisation.is_member(actor))
        )

        # Proposer can withdraw: Buyer if PENDING_DEALER, Dealer if PENDING_BUYER
        if is_buyer_side and locked_offer.status != VehicleOfferStatusChoices.PENDING_DEALER:
            raise ValidationError("You can only withdraw an offer while awaiting dealer review.")
        if is_seller_side and locked_offer.status != VehicleOfferStatusChoices.PENDING_BUYER:
            raise ValidationError("You can only withdraw a counteroffer while awaiting buyer review.")
        if not is_buyer_side and not is_seller_side:
            raise PermissionDenied("You are not a participant in this vehicle offer.")

        locked_offer.status = VehicleOfferStatusChoices.WITHDRAWN
        locked_offer.withdrawn_at = timezone.now()
        locked_offer.save(update_fields=['status', 'withdrawn_at', 'updated_at'])

        VehicleOfferAction.objects.create(
            offer=locked_offer,
            proposal=locked_offer.latest_proposal,
            actor=actor,
            action_type=VehicleOfferActionTypeChoices.WITHDRAWN,
            notes=reason,
        )

        record_audit_entry(
            event_type="marketplace.vehicle_offer.withdrawn",
            action="marketplace:vehicle_offer.withdraw",
            resource_type="VehiclePurchaseOffer",
            resource_id=str(locked_offer.id),
            actor_id=actor.id,
            operating_org_id=locked_offer.organisation_id,
            metadata={"offer_id": str(locked_offer.id), "reason": reason},
        )

    return locked_offer


# =============================================================================
# 3. Atomic Vehicle Reservation & Dedicated VehicleOrder Creation
# =============================================================================

def accept_vehicle_offer_and_reserve(
    *,
    actor: User,
    offer_id: str | uuid.UUID,
    handover_address: Optional[dict] = None,
) -> VehicleOrder:
    """
    Formally accepts a vehicle purchase offer, acquires an exclusive row lock
    on the VehicleListing, verifies availability, and atomically creates the
    dedicated VehicleOrder in PAYMENT_PENDING status.

    - Locks listing row with select_for_update().
    - Sets listing availability_status to RESERVED.
    - Sets accepted offer status to ACCEPTED.
    - Transitions all competing offers on this listing to SUPERSEDED.
    - Calculates 5-business-day payment deadline starting from order creation.
    - Returns the created VehicleOrder.
    """
    with transaction.atomic():
        try:
            offer = VehiclePurchaseOffer.objects.get(pk=offer_id)
        except VehiclePurchaseOffer.DoesNotExist:
            raise ValidationError("Vehicle purchase offer not found.")

        # 1. Lock the vehicle listing to prevent concurrent reservations
        try:
            listing = (
                VehicleListing.objects.select_for_update(of=('self',))
                .select_related('make', 'model', 'variant', 'seller', 'organisation')
                .get(pk=offer.listing_id)
            )
        except VehicleListing.DoesNotExist:
            raise ValidationError("Associated vehicle listing no longer exists.")

        # 2. Check listing availability & status under lock
        if listing.status != ListingStatusChoices.APPROVED or not listing.is_active:
            raise ValidationError("This vehicle listing is not active and approved for purchase.")

        if listing.availability_status != VehicleListingAvailabilityChoices.AVAILABLE:
            raise VehicleAlreadyReservedError(
                f"Vehicle reservation failed: This vehicle is currently {listing.availability_status.lower()} by another buyer."
            )

        # 3. Check existing active orders on listing
        active_order_exists = VehicleOrder.objects.filter(
            listing=listing,
            status__in=[
                VehicleOrderStatusChoices.PAYMENT_PENDING,
                VehicleOrderStatusChoices.PAYMENT_SUBMITTED,
                VehicleOrderStatusChoices.PAYMENT_CONFIRMED,
                VehicleOrderStatusChoices.DOCUMENTS_PENDING,
                VehicleOrderStatusChoices.READY_FOR_HANDOVER,
            ],
        ).exists()
        if active_order_exists:
            raise VehicleAlreadyReservedError("Vehicle reservation failed: An active order already exists for this vehicle.")

        # 4. Lock and verify the offer
        locked_offer = VehiclePurchaseOffer.objects.select_for_update().get(pk=offer.pk)
        if not locked_offer.is_active:
            raise ValidationError(f"This offer is not eligible for acceptance (status: {locked_offer.status}).")

        if locked_offer.expires_at <= timezone.now():
            locked_offer.status = VehicleOfferStatusChoices.EXPIRED
            locked_offer.save(update_fields=['status', 'updated_at'])
            raise ValidationError("This offer has expired and can no longer be accepted.")

        is_seller_side = (
            locked_offer.seller_id == actor.id or
            (locked_offer.organisation and locked_offer.organisation.is_member(actor))
        )
        is_buyer_side = (locked_offer.buyer_id == actor.id)

        # Validate turn-based acceptance
        if locked_offer.status == VehicleOfferStatusChoices.PENDING_DEALER:
            if not is_seller_side:
                raise PermissionDenied("Only the seller or authorized dealer can accept this offer.")
        elif locked_offer.status == VehicleOfferStatusChoices.PENDING_BUYER:
            if not is_buyer_side:
                raise PermissionDenied("Only the buyer can accept this counteroffer.")
        else:
            raise ValidationError("This offer is not in a state that can be accepted.")

        latest_proposal = locked_offer.latest_proposal
        if not latest_proposal:
            raise ValidationError("Cannot accept an offer with no proposed terms.")

        # 5. Transition Offer to ACCEPTED
        locked_offer.status = VehicleOfferStatusChoices.ACCEPTED
        locked_offer.agreed_price = latest_proposal.offered_price
        locked_offer.accepted_at = timezone.now()
        locked_offer.save(update_fields=['status', 'agreed_price', 'accepted_at', 'updated_at'])

        VehicleOfferAction.objects.create(
            offer=locked_offer,
            proposal=latest_proposal,
            actor=actor,
            action_type=VehicleOfferActionTypeChoices.ACCEPTED,
            notes=f"Offer accepted by {actor.email}. Vehicle reserved.",
        )

        record_audit_entry(
            event_type="marketplace.vehicle_offer.accepted",
            action="marketplace:vehicle_offer.accept",
            resource_type="VehiclePurchaseOffer",
            resource_id=str(locked_offer.id),
            actor_id=actor.id,
            operating_org_id=locked_offer.organisation_id,
            metadata={
                "offer_id": str(locked_offer.id),
                "listing_id": str(listing.id),
                "agreed_price": str(locked_offer.agreed_price),
            },
        )

        # 6. Set Listing availability to RESERVED
        listing.availability_status = VehicleListingAvailabilityChoices.RESERVED
        listing.save(update_fields=['availability_status', 'updated_at'])

        # 7. Determine market timezone and calculate 5-business-day payment deadline
        market_tz = "Asia/Kolkata" if listing.currency == "INR" else "Europe/London"
        now = timezone.now()
        payment_deadline = calculate_payment_deadline(
            start_dt=now,
            market_tz_name=market_tz,
            business_days=5,
        )

        # 8. Create dedicated VehicleOrder
        order_number = f"VO-{now.strftime('%Y%m')}-{uuid.uuid4().hex[:8].upper()}"
        snapshot = serialize_listing_snapshot(listing)

        order = VehicleOrder.objects.create(
            order_number=order_number,
            listing=listing,
            accepted_offer=locked_offer,
            buyer=locked_offer.buyer,
            seller=locked_offer.seller,
            organisation=locked_offer.organisation,
            status=VehicleOrderStatusChoices.PAYMENT_PENDING,
            agreed_price=locked_offer.agreed_price,
            currency=locked_offer.currency,
            handover_type=latest_proposal.handover_preference,
            handover_address=handover_address or {},
            payment_deadline=payment_deadline,
            market_timezone=market_tz,
            listing_snapshot=snapshot,
        )

        # 9. Mark all competing offers on this listing as SUPERSEDED
        competing_offers = VehiclePurchaseOffer.objects.filter(
            listing=listing,
            status__in=[
                VehicleOfferStatusChoices.PENDING_DEALER,
                VehicleOfferStatusChoices.PENDING_BUYER,
            ],
        ).exclude(pk=locked_offer.pk)

        for comp_offer in competing_offers:
            comp_offer.status = VehicleOfferStatusChoices.SUPERSEDED
            comp_offer.save(update_fields=['status', 'updated_at'])
            VehicleOfferAction.objects.create(
                offer=comp_offer,
                actor=actor,
                action_type=VehicleOfferActionTypeChoices.SUPERSEDED,
                notes=f"Vehicle was reserved by another accepted offer (Order {order.order_number}).",
            )
            record_audit_entry(
                event_type="marketplace.vehicle_offer.superseded",
                action="marketplace:vehicle_offer.supersede",
                resource_type="VehiclePurchaseOffer",
                resource_id=str(comp_offer.id),
                actor_id=actor.id,
                operating_org_id=comp_offer.organisation_id,
                metadata={
                    "offer_id": str(comp_offer.id),
                    "listing_id": str(listing.id),
                    "winning_order_number": order.order_number,
                },
            )

        # 10. Audit Logging
        record_audit_entry(
            event_type="marketplace.vehicle_order.created",
            action="marketplace:vehicle_order.create",
            resource_type="VehicleOrder",
            resource_id=str(order.id),
            actor_id=actor.id,
            operating_org_id=order.organisation_id,
            metadata={
                "order_id": str(order.id),
                "order_number": order.order_number,
                "listing_id": str(listing.id),
                "accepted_offer_id": str(locked_offer.id),
                "agreed_price": str(order.agreed_price),
                "currency": order.currency,
                "payment_deadline": payment_deadline.isoformat(),
                "market_timezone": market_tz,
            },
        )

        logger.info(
            "Created VehicleOrder %s for listing %s, agreed price %s %s, deadline %s",
            order.order_number,
            listing.id,
            order.currency,
            order.agreed_price,
            payment_deadline,
        )

    return order


# =============================================================================
# 4. Payment Deadline Expiration and Reservation Release
# =============================================================================

def cancel_expired_payment_orders() -> int:
    """
    Background maintenance task:
    Cancels eligible PAYMENT_PENDING orders where payment_deadline has passed.
    Releases vehicle availability back to AVAILABLE only after the cancellation
    is safely committed. Idempotent and concurrency-safe.
    """
    now = timezone.now()
    expired_order_ids = list(
        VehicleOrder.objects.filter(
            status=VehicleOrderStatusChoices.PAYMENT_PENDING,
            payment_deadline__lt=now,
        ).values_list('id', flat=True)
    )

    cancelled_count = 0

    for order_id in expired_order_ids:
        try:
            with transaction.atomic():
                order = (
                    VehicleOrder.objects.select_for_update(of=('self',))
                    .select_related('listing')
                    .get(pk=order_id)
                )

                if order.status != VehicleOrderStatusChoices.PAYMENT_PENDING or order.payment_deadline >= now:
                    continue  # State changed or extended

                order.status = VehicleOrderStatusChoices.CANCELLED
                order.cancelled_at = now
                order.cancellation_reason = "Payment deadline of 5 business days expired without confirmed buyer payment."
                order.save(update_fields=['status', 'cancelled_at', 'cancellation_reason', 'updated_at'])

                # Release the listing back to AVAILABLE
                listing = VehicleListing.objects.select_for_update().get(pk=order.listing_id)
                if listing.availability_status == VehicleListingAvailabilityChoices.RESERVED:
                    listing.availability_status = VehicleListingAvailabilityChoices.AVAILABLE
                    listing.save(update_fields=['availability_status', 'updated_at'])

                record_audit_entry(
                    event_type="marketplace.vehicle_order.expired_cancelled",
                    action="marketplace:vehicle_order.expire",
                    resource_type="VehicleOrder",
                    resource_id=str(order.id),
                    actor_id=None,
                    operating_org_id=order.organisation_id,
                    metadata={
                        "order_id": str(order.id),
                        "order_number": order.order_number,
                        "listing_id": str(listing.id),
                        "reason": order.cancellation_reason,
                    },
                )
                cancelled_count += 1
                logger.info("Cancelled expired VehicleOrder %s and relisted %s", order.order_number, listing.id)
        except Exception as exc:
            logger.error("Failed to cancel expired order %s: %s", order_id, exc, exc_info=True)

    return cancelled_count


def expire_pending_vehicle_offers() -> int:
    """
    Background maintenance task:
    Finds and expires active VehiclePurchaseOffer records where expires_at has passed.
    Eligible statuses: PENDING_DEALER, PENDING_BUYER.
    Does NOT expire ACCEPTED, REJECTED, WITHDRAWN, SUPERSEDED, or already EXPIRED offers.
    Records an immutable VehicleOfferAction (action_type=EXPIRED).
    Records an audit entry triggering notification dispatch to both buyer and seller.
    Concurrency safe: uses select_for_update(of=('self',)) inside transaction.atomic().
    """
    now = timezone.now()
    eligible_offer_ids = list(
        VehiclePurchaseOffer.objects.filter(
            status__in=[
                VehicleOfferStatusChoices.PENDING_DEALER,
                VehicleOfferStatusChoices.PENDING_BUYER,
            ],
            expires_at__lt=now,
        ).values_list('id', flat=True)
    )

    expired_count = 0
    for offer_id in eligible_offer_ids:
        try:
            with transaction.atomic():
                offer = (
                    VehiclePurchaseOffer.objects.select_for_update(of=('self',))
                    .select_related('listing')
                    .get(pk=offer_id)
                )

                if offer.status not in (VehicleOfferStatusChoices.PENDING_DEALER, VehicleOfferStatusChoices.PENDING_BUYER):
                    continue
                if offer.expires_at >= now:
                    continue

                offer.status = VehicleOfferStatusChoices.EXPIRED
                offer.save(update_fields=['status', 'updated_at'])

                expiring_actor = offer.seller if offer.status == VehicleOfferStatusChoices.PENDING_DEALER else offer.buyer

                VehicleOfferAction.objects.create(
                    offer=offer,
                    proposal=offer.latest_proposal,
                    actor=expiring_actor,
                    action_type=VehicleOfferActionTypeChoices.EXPIRED,
                    notes=f"Offer expired automatically after negotiation deadline passed at {offer.expires_at.isoformat()}.",
                )

                record_audit_entry(
                    event_type="marketplace.vehicle_offer.expired",
                    action="marketplace:vehicle_offer.expire",
                    resource_type="VehiclePurchaseOffer",
                    resource_id=str(offer.id),
                    actor_id=expiring_actor.id,
                    operating_org_id=offer.organisation_id,
                    metadata={
                        "offer_id": str(offer.id),
                        "listing_id": str(offer.listing_id),
                        "expired_at": now.isoformat(),
                    },
                )
                expired_count += 1
                logger.info("Auto-expired VehiclePurchaseOffer %s on listing %s", offer.id, offer.listing_id)
        except Exception as exc:
            logger.error("Failed to expire vehicle offer %s: %s", offer_id, exc, exc_info=True)

    return expired_count


def send_vehicle_payment_reminders(hours_before_deadline: int = 24) -> int:
    """
    Background maintenance task:
    Finds PAYMENT_PENDING orders whose payment_deadline is within `hours_before_deadline`
    and sends an idempotent payment reminder notification to the buyer.
    Uses AuditLog with unique source_audit_id to prevent duplicate reminders.
    """
    now = timezone.now()
    threshold = now + timedelta(hours=hours_before_deadline)

    pending_orders = list(
        VehicleOrder.objects.filter(
            status=VehicleOrderStatusChoices.PAYMENT_PENDING,
            payment_deadline__gt=now,
            payment_deadline__lte=threshold,
        ).values_list('id', flat=True)
    )

    reminded_count = 0
    for order_id in pending_orders:
        try:
            with transaction.atomic():
                order = VehicleOrder.objects.select_for_update(of=('self',)).get(pk=order_id)
                if order.status != VehicleOrderStatusChoices.PAYMENT_PENDING:
                    continue

                from platform_core.audit.models import AuditLog
                already_reminded = AuditLog.objects.filter(
                    event_type="marketplace.vehicle_order.payment_reminder",
                    resource_type="VehicleOrder",
                    resource_id=str(order.id),
                ).exists()

                if already_reminded:
                    continue

                record_audit_entry(
                    event_type="marketplace.vehicle_order.payment_reminder",
                    action="marketplace:vehicle_order.payment_reminder",
                    resource_type="VehicleOrder",
                    resource_id=str(order.id),
                    actor_id=None,
                    operating_org_id=order.organisation_id,
                    metadata={
                        "order_id": str(order.id),
                        "order_number": order.order_number,
                        "payment_deadline": order.payment_deadline.isoformat(),
                    },
                )
                reminded_count += 1
                logger.info("Sent payment deadline reminder for VehicleOrder %s", order.order_number)
        except Exception as exc:
            logger.error("Failed to send payment reminder for order %s: %s", order_id, exc, exc_info=True)

    return reminded_count


# =============================================================================
# 5. Phase 2: Offline Payment Reporting and Dealer Verification
# =============================================================================

def report_vehicle_order_payment(
    *,
    actor: User,
    order_id: str,
    amount_paid: Decimal,
    currency: str,
    payment_reference: str,
    paid_at: datetime,
    payment_notes: str = "",
) -> VehiclePaymentReport:
    """
    Buyer reports that they have transferred offline payment directly to the dealer.
    Enforces strict ownership, status validation, exact amount and currency matching,
    duplicate prevention, and row-level locking.
    Transitions order to PAYMENT_SUBMITTED while keeping vehicle reserved.
    """
    ref_clean = payment_reference.strip()
    if not ref_clean or len(ref_clean) < 3:
        raise ValidationError("A valid bank transfer or transaction reference (minimum 3 characters) is required.")

    now = timezone.now()
    if paid_at > now + timedelta(minutes=5):
        raise ValidationError("Payment date/time cannot be in the future.")

    with transaction.atomic():
        try:
            order = VehicleOrder.objects.select_for_update(of=('self',)).get(pk=order_id)
        except VehicleOrder.DoesNotExist:
            raise ValidationError("Vehicle order not found.")

        # 1. Authorization: Only the purchasing buyer can report payment
        if order.buyer_id != actor.id:
            raise PermissionDenied("Only the purchasing buyer can report payment for this vehicle order.")

        # 2. State Validation: Order must be in PAYMENT_PENDING
        if order.status != VehicleOrderStatusChoices.PAYMENT_PENDING:
            raise ValidationError(
                f"Cannot report payment on an order in '{order.status}' status. Payment can only be reported for orders in PAYMENT_PENDING."
            )

        # 2b. Deadline Validation: Cannot submit payment on an expired order
        if order.payment_deadline <= now:
            raise ValidationError(
                f"The payment deadline for this vehicle order expired at {order.payment_deadline.isoformat()} ({order.market_timezone}). New payment reports cannot be submitted for expired orders."
            )

        # 3. Currency Validation
        if currency.strip().upper() != order.currency.upper():
            raise ValidationError(
                f"Payment currency '{currency}' does not match agreed order currency '{order.currency}'."
            )

        # 4. Amount Validation (Exact match to agreed purchase price)
        if amount_paid != order.agreed_price:
            raise ValidationError(
                f"Amount paid ({currency} {amount_paid}) does not match agreed order price ({order.currency} {order.agreed_price}). Arbitrary or partial amounts are not permitted."
            )

        # 5. Prevent duplicate pending reports
        has_pending_report = order.payment_reports.filter(
            status=VehiclePaymentReportStatusChoices.PENDING_VERIFICATION,
        ).exists()
        if has_pending_report:
            raise ValidationError(
                "A payment report is already pending dealer verification for this vehicle order. Please wait for the dealer to verify."
            )

        # 6. Create auditable VehiclePaymentReport
        report = VehiclePaymentReport.objects.create(
            order=order,
            submitted_by=actor,
            amount_paid=amount_paid,
            currency=currency.strip().upper(),
            payment_reference=ref_clean,
            paid_at=paid_at,
            payment_notes=payment_notes.strip(),
            status=VehiclePaymentReportStatusChoices.PENDING_VERIFICATION,
        )

        # 7. Record immutable verification event
        VehiclePaymentVerificationEvent.objects.create(
            report=report,
            order=order,
            actor=actor,
            event_type=VehiclePaymentVerificationEventTypeChoices.PAYMENT_REPORTED,
            notes=f"Buyer reported direct bank transfer {ref_clean} of {currency} {amount_paid}.",
            metadata={
                "payment_reference": ref_clean,
                "amount_paid": str(amount_paid),
                "currency": currency,
                "paid_at": paid_at.isoformat(),
            },
        )

        # 8. Transition order to PAYMENT_SUBMITTED
        order.status = VehicleOrderStatusChoices.PAYMENT_SUBMITTED
        order.payment_submitted_at = now
        order.save(update_fields=['status', 'payment_submitted_at', 'updated_at'])

        # 9. Audit log entry (triggers dealer notification)
        record_audit_entry(
            event_type="marketplace.vehicle_order.payment_reported",
            action="marketplace:vehicle_order.report_payment",
            resource_type="VehicleOrder",
            resource_id=str(order.id),
            actor_id=actor.id,
            operating_org_id=order.organisation_id,
            metadata={
                "report_id": str(report.id),
                "order_id": str(order.id),
                "order_number": order.order_number,
                "amount_paid": str(amount_paid),
                "currency": currency,
                "payment_reference": ref_clean,
                "paid_at": paid_at.isoformat(),
            },
        )

        logger.info(
            "Buyer %s reported payment for VehicleOrder %s (Report %s, %s %s)",
            actor.email,
            order.order_number,
            report.id,
            currency,
            amount_paid,
        )

    return report


def confirm_vehicle_order_payment(
    *,
    actor: User,
    order_id: str,
    notes: str = "",
) -> VehiclePaymentReport:
    """
    Dealer confirms that buyer's offline payment has arrived in their bank account.
    Validates dealer organisation ownership, order state, and report state.
    Transitions order to PAYMENT_CONFIRMED and records verified_by and verified_at.
    """
    now = timezone.now()

    with transaction.atomic():
        try:
            order = VehicleOrder.objects.select_for_update(of=('self',)).get(pk=order_id)
        except VehicleOrder.DoesNotExist:
            raise ValidationError("Vehicle order not found.")

        # 1. Authorization: Only seller or dealer org member can verify
        is_seller = (order.seller_id == actor.id)
        is_org_member = bool(order.organisation and order.organisation.is_member(actor))
        if not (is_seller or is_org_member):
            raise PermissionDenied("You do not have permission to verify payments for this dealer order.")

        # Buyer cannot verify
        if order.buyer_id == actor.id:
            raise PermissionDenied("Buyers cannot verify their own payment.")

        # 2. State Validation
        if order.status != VehicleOrderStatusChoices.PAYMENT_SUBMITTED:
            raise ValidationError(
                f"Cannot confirm payment on an order in '{order.status}' status. Only orders in PAYMENT_SUBMITTED can be confirmed."
            )

        # 3. Fetch active pending or flagged report under lock
        report = (
            order.payment_reports.select_for_update(of=('self',))
            .filter(
                status__in=[
                    VehiclePaymentReportStatusChoices.PENDING_VERIFICATION,
                    VehiclePaymentReportStatusChoices.FLAGGED,
                ]
            )
            .first()
        )
        if not report:
            raise ValidationError("No pending or flagged payment report found awaiting verification for this order.")

        # 4. Transition report to CONFIRMED
        report.status = VehiclePaymentReportStatusChoices.CONFIRMED
        report.verified_by = actor
        report.verified_at = now
        report.verification_notes = notes.strip()
        report.save(update_fields=['status', 'verified_by', 'verified_at', 'verification_notes', 'updated_at'])

        # 5. Transition order to PAYMENT_CONFIRMED
        order.status = VehicleOrderStatusChoices.PAYMENT_CONFIRMED
        order.payment_confirmed_at = now
        order.confirmed_by = actor
        order.save(update_fields=['status', 'payment_confirmed_at', 'confirmed_by', 'updated_at'])

        # 6. Record immutable verification event
        VehiclePaymentVerificationEvent.objects.create(
            report=report,
            order=order,
            actor=actor,
            event_type=VehiclePaymentVerificationEventTypeChoices.VERIFICATION_CONFIRMED,
            notes=notes.strip() or "Dealer confirmed offline funds received in bank account.",
            metadata={
                "report_id": str(report.id),
                "verified_by": actor.email,
                "verified_at": now.isoformat(),
            },
        )

        # 7. Audit log (triggers buyer notification)
        record_audit_entry(
            event_type="marketplace.vehicle_order.payment_confirmed",
            action="marketplace:vehicle_order.confirm_payment",
            resource_type="VehicleOrder",
            resource_id=str(order.id),
            actor_id=actor.id,
            operating_org_id=order.organisation_id,
            metadata={
                "order_id": str(order.id),
                "order_number": order.order_number,
                "report_id": str(report.id),
                "verified_by_id": str(actor.id),
                "notes": notes.strip(),
            },
        )

        logger.info(
            "Dealer %s confirmed payment for VehicleOrder %s (Report %s)",
            actor.email,
            order.order_number,
            report.id,
        )

    return report


def reject_vehicle_order_payment(
    *,
    actor: User,
    order_id: str,
    reason: str,
) -> VehiclePaymentReport:
    """
    Dealer rejects payment report because funds were not received or details mismatched.
    Requires a non-empty reason.
    Preserves report and action history.
    Reverts order to PAYMENT_PENDING so buyer can re-submit, keeping vehicle RESERVED.
    """
    reason_clean = reason.strip()
    if not reason_clean or len(reason_clean) < 5:
        raise ValidationError("A clear explanation (minimum 5 characters) is required when rejecting a payment report.")

    now = timezone.now()

    with transaction.atomic():
        try:
            order = VehicleOrder.objects.select_for_update(of=('self',)).get(pk=order_id)
        except VehicleOrder.DoesNotExist:
            raise ValidationError("Vehicle order not found.")

        # 1. Authorization
        is_seller = (order.seller_id == actor.id)
        is_org_member = bool(order.organisation and order.organisation.is_member(actor))
        if not (is_seller or is_org_member):
            raise PermissionDenied("You do not have permission to reject payments for this dealer order.")

        if order.buyer_id == actor.id:
            raise PermissionDenied("Buyers cannot reject payment.")

        # 2. State Validation
        if order.status != VehicleOrderStatusChoices.PAYMENT_SUBMITTED:
            raise ValidationError(
                f"Cannot reject payment on an order in '{order.status}' status. Only orders in PAYMENT_SUBMITTED can be rejected."
            )

        # 3. Fetch active pending or flagged report under lock
        report = (
            order.payment_reports.select_for_update(of=('self',))
            .filter(
                status__in=[
                    VehiclePaymentReportStatusChoices.PENDING_VERIFICATION,
                    VehiclePaymentReportStatusChoices.FLAGGED,
                ]
            )
            .first()
        )
        if not report:
            raise ValidationError("No pending or flagged payment report found to reject for this order.")

        # 4. Transition report to REJECTED
        report.status = VehiclePaymentReportStatusChoices.REJECTED
        report.verified_by = actor
        report.verified_at = now
        report.verification_notes = reason_clean
        report.save(update_fields=['status', 'verified_by', 'verified_at', 'verification_notes', 'updated_at'])

        # 5. Keep order & vehicle RESERVED, set order status back to PAYMENT_PENDING so buyer can re-submit
        order.status = VehicleOrderStatusChoices.PAYMENT_PENDING
        order.save(update_fields=['status', 'updated_at'])

        # 6. Record immutable verification event
        VehiclePaymentVerificationEvent.objects.create(
            report=report,
            order=order,
            actor=actor,
            event_type=VehiclePaymentVerificationEventTypeChoices.VERIFICATION_REJECTED,
            notes=reason_clean,
            metadata={
                "report_id": str(report.id),
                "reason": reason_clean,
                "rejected_by": actor.email,
            },
        )

        # 7. Audit log (triggers buyer notification)
        record_audit_entry(
            event_type="marketplace.vehicle_order.payment_rejected",
            action="marketplace:vehicle_order.reject_payment",
            resource_type="VehicleOrder",
            resource_id=str(order.id),
            actor_id=actor.id,
            operating_org_id=order.organisation_id,
            metadata={
                "order_id": str(order.id),
                "order_number": order.order_number,
                "report_id": str(report.id),
                "reason": reason_clean,
            },
        )

        logger.info(
            "Dealer %s rejected payment report %s for VehicleOrder %s: %s",
            actor.email,
            report.id,
            order.order_number,
            reason_clean,
        )

    return report


def flag_vehicle_order_payment(
    *,
    actor: User,
    order_id: str,
    reason: str,
) -> VehiclePaymentReport:
    """
    Dealer flags a payment report with a discrepancy (e.g. transfer reference unclear).
    Requires a non-empty reason.
    Preserves report and records FLAGGED event while keeping order in PAYMENT_SUBMITTED.
    """
    reason_clean = reason.strip()
    if not reason_clean or len(reason_clean) < 5:
        raise ValidationError("A clear explanation (minimum 5 characters) is required when flagging a payment discrepancy.")

    now = timezone.now()

    with transaction.atomic():
        try:
            order = VehicleOrder.objects.select_for_update(of=('self',)).get(pk=order_id)
        except VehicleOrder.DoesNotExist:
            raise ValidationError("Vehicle order not found.")

        # 1. Authorization
        is_seller = (order.seller_id == actor.id)
        is_org_member = bool(order.organisation and order.organisation.is_member(actor))
        if not (is_seller or is_org_member):
            raise PermissionDenied("You do not have permission to flag payments for this dealer order.")

        if order.status != VehicleOrderStatusChoices.PAYMENT_SUBMITTED:
            raise ValidationError(
                f"Cannot flag payment on an order in '{order.status}' status. Only orders in PAYMENT_SUBMITTED can be flagged."
            )

        report = (
            order.payment_reports.select_for_update(of=('self',))
            .filter(status=VehiclePaymentReportStatusChoices.PENDING_VERIFICATION)
            .first()
        )
        if not report:
            raise ValidationError("No pending payment report found to flag for this order.")

        report.status = VehiclePaymentReportStatusChoices.FLAGGED
        report.verified_by = actor
        report.verified_at = now
        report.verification_notes = reason_clean
        report.save(update_fields=['status', 'verified_by', 'verified_at', 'verification_notes', 'updated_at'])

        VehiclePaymentVerificationEvent.objects.create(
            report=report,
            order=order,
            actor=actor,
            event_type=VehiclePaymentVerificationEventTypeChoices.VERIFICATION_FLAGGED,
            notes=reason_clean,
            metadata={
                "report_id": str(report.id),
                "reason": reason_clean,
                "flagged_by": actor.email,
            },
        )

        record_audit_entry(
            event_type="marketplace.vehicle_order.payment_flagged",
            action="marketplace:vehicle_order.flag_payment",
            resource_type="VehicleOrder",
            resource_id=str(order.id),
            actor_id=actor.id,
            operating_org_id=order.organisation_id,
            metadata={
                "order_id": str(order.id),
                "order_number": order.order_number,
                "report_id": str(report.id),
                "reason": reason_clean,
            },
        )

        logger.info(
            "Dealer %s flagged payment report %s for VehicleOrder %s: %s",
            actor.email,
            report.id,
            order.order_number,
            reason_clean,
        )

    return report


def process_vehicle_payment_verification_escalations() -> dict[str, int]:
    """
    Background maintenance task:
    Evaluates orders in PAYMENT_SUBMITTED with reports in PENDING_VERIFICATION (or FLAGGED)
    against the 48h warning, 72h overdue, and 120h operations escalation milestones.
    Monotonically transitions escalation_level to prevent duplicate alerts.
    Idempotent and safe to run on recurring schedules.
    """
    now = timezone.now()
    results = {"warnings_48h": 0, "overdue_72h": 0, "escalated_120h": 0}

    # Find pending reports on PAYMENT_SUBMITTED orders
    eligible_reports = list(
        VehiclePaymentReport.objects.filter(
            order__status=VehicleOrderStatusChoices.PAYMENT_SUBMITTED,
            status__in=[
                VehiclePaymentReportStatusChoices.PENDING_VERIFICATION,
                VehiclePaymentReportStatusChoices.FLAGGED,
            ],
        )
        .exclude(escalation_level=VehiclePaymentEscalationLevelChoices.ESCALATED_120H)
        .values_list('id', flat=True)
    )

    for report_id in eligible_reports:
        try:
            with transaction.atomic():
                report = (
                    VehiclePaymentReport.objects.select_for_update(of=('self',))
                    .select_related('order')
                    .get(pk=report_id)
                )

                order = report.order
                if order.status != VehicleOrderStatusChoices.PAYMENT_SUBMITTED:
                    continue

                submitted_at = order.payment_submitted_at or report.created_at
                elapsed = now - submitted_at

                # Milestone 3: 120 hours (72h + 48h operations grace period)
                if elapsed >= timedelta(hours=120):
                    if report.escalation_level != VehiclePaymentEscalationLevelChoices.ESCALATED_120H:
                        report.escalation_level = VehiclePaymentEscalationLevelChoices.ESCALATED_120H
                        report.escalated_at = now
                        report.save(update_fields=['escalation_level', 'escalated_at', 'updated_at'])

                        VehiclePaymentVerificationEvent.objects.create(
                            report=report,
                            order=order,
                            actor=None,
                            event_type=VehiclePaymentVerificationEventTypeChoices.OPERATIONS_ESCALATED,
                            notes="Verification unfulfilled after 120 hours (72h + 48h operations grace period). Escalated to operations queue.",
                            metadata={"elapsed_hours": elapsed.total_seconds() / 3600},
                        )

                        record_audit_entry(
                            event_type="marketplace.vehicle_order.verification_escalated_120h",
                            action="marketplace:vehicle_order.escalate",
                            resource_type="VehicleOrder",
                            resource_id=str(order.id),
                            actor_id=None,
                            operating_org_id=order.organisation_id,
                            metadata={
                                "order_id": str(order.id),
                                "order_number": order.order_number,
                                "report_id": str(report.id),
                                "elapsed_hours": round(elapsed.total_seconds() / 3600, 1),
                            },
                        )
                        results["escalated_120h"] += 1
                        logger.warning("VehicleOrder %s escalated to operations after 120h", order.order_number)

                # Milestone 2: 72 hours (Verification overdue)
                elif elapsed >= timedelta(hours=72):
                    if report.escalation_level in (VehiclePaymentEscalationLevelChoices.NONE, VehiclePaymentEscalationLevelChoices.WARNING_48H):
                        report.escalation_level = VehiclePaymentEscalationLevelChoices.OVERDUE_72H
                        report.escalated_at = now
                        report.save(update_fields=['escalation_level', 'escalated_at', 'updated_at'])

                        VehiclePaymentVerificationEvent.objects.create(
                            report=report,
                            order=order,
                            actor=None,
                            event_type=VehiclePaymentVerificationEventTypeChoices.OVERDUE_72H_TRIGGERED,
                            notes="Dealer payment verification is overdue (exceeded 72 hours).",
                            metadata={"elapsed_hours": elapsed.total_seconds() / 3600},
                        )

                        record_audit_entry(
                            event_type="marketplace.vehicle_order.verification_overdue_72h",
                            action="marketplace:vehicle_order.overdue_warning",
                            resource_type="VehicleOrder",
                            resource_id=str(order.id),
                            actor_id=None,
                            operating_org_id=order.organisation_id,
                            metadata={
                                "order_id": str(order.id),
                                "order_number": order.order_number,
                                "report_id": str(report.id),
                                "elapsed_hours": round(elapsed.total_seconds() / 3600, 1),
                            },
                        )
                        results["overdue_72h"] += 1
                        logger.info("VehicleOrder %s marked 72h overdue for payment verification", order.order_number)

                # Milestone 1: 48 hours (Verification warning)
                elif elapsed >= timedelta(hours=48):
                    if report.escalation_level == VehiclePaymentEscalationLevelChoices.NONE:
                        report.escalation_level = VehiclePaymentEscalationLevelChoices.WARNING_48H
                        report.escalated_at = now
                        report.save(update_fields=['escalation_level', 'escalated_at', 'updated_at'])

                        VehiclePaymentVerificationEvent.objects.create(
                            report=report,
                            order=order,
                            actor=None,
                            event_type=VehiclePaymentVerificationEventTypeChoices.WARNING_48H_TRIGGERED,
                            notes="Payment verification pending for 48 hours. Warning sent to dealer.",
                            metadata={"elapsed_hours": elapsed.total_seconds() / 3600},
                        )

                        record_audit_entry(
                            event_type="marketplace.vehicle_order.verification_warning_48h",
                            action="marketplace:vehicle_order.verification_warning",
                            resource_type="VehicleOrder",
                            resource_id=str(order.id),
                            actor_id=None,
                            operating_org_id=order.organisation_id,
                            metadata={
                                "order_id": str(order.id),
                                "order_number": order.order_number,
                                "report_id": str(report.id),
                                "elapsed_hours": round(elapsed.total_seconds() / 3600, 1),
                            },
                        )
                        results["warnings_48h"] += 1
                        logger.info("VehicleOrder %s sent 48h payment verification warning", order.order_number)

        except Exception as exc:
            logger.error("Failed to process payment verification escalation for report %s: %s", report_id, exc, exc_info=True)

    return results


