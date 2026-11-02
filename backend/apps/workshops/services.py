import logging
from decimal import Decimal
from django.db import transaction, models
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone

from apps.workshops.models import (
    WorkshopProfile,
    WorkshopBooking,
    BookingServiceItem,
    WorkshopService,
    WorkshopQuotation,
    QuotationLineItem,
    BookingStatusChoices,
    QuotationStatusChoices,
    LineItemTypeChoices,
)
from apps.garage.models import GarageVehicle
from apps.catalogue.models import Part
from apps.identity.models import User
from platform_core.audit.writer import record_audit_entry
from apps.notifications.services import create_notification

logger = logging.getLogger(__name__)


class CapacityExceededError(DjangoValidationError):
    """Raised when an appointment exceeds the workshop's simultaneous bay capacity."""
    pass


class BookingService:

    @classmethod
    def create_booking(cls, buyer: User, data: dict) -> WorkshopBooking:
        """
        Creates a new customer booking request with vehicle snapshot and service items.
        """
        workshop_id = data['workshop_id']
        vehicle_id = data['vehicle_id']
        service_ids = data.get('service_ids', [])
        preferred_date = data['preferred_date']
        preferred_time_slot = data.get('preferred_time_slot', '')
        customer_notes = data.get('customer_notes', '')
        reported_faults = data.get('reported_faults', '')

        with transaction.atomic():
            workshop = WorkshopProfile.objects.select_related('organisation').get(id=workshop_id)
            if not workshop.is_accepting_bookings:
                raise DjangoValidationError("This workshop is currently not accepting new bookings.")

            vehicle = GarageVehicle.objects.get(id=vehicle_id, user=buyer)
            if vehicle.is_archived:
                raise DjangoValidationError("Cannot book an appointment for an archived vehicle.")

            booking = WorkshopBooking(
                workshop=workshop,
                buyer=buyer,
                vehicle=vehicle,
                preferred_date=preferred_date,
                preferred_time_slot=preferred_time_slot,
                customer_notes=customer_notes,
                reported_faults=reported_faults,
                status=BookingStatusChoices.REQUESTED,
            )
            booking.save()

            # Attach requested services
            if service_ids:
                services = WorkshopService.objects.filter(id__in=service_ids, workshop=workshop, is_active=True)
                for service in services:
                    BookingServiceItem.objects.create(
                        booking=booking,
                        service=service,
                        service_name=service.name,
                        service_price=service.base_price,
                        currency=service.currency,
                    )

            # Record audit entry
            audit = record_audit_entry(
                event_type="workshop.booking.created",
                action="workshop:booking.create",
                resource_type="WorkshopBooking",
                resource_id=str(booking.id),
                actor_id=buyer.id,
                metadata={
                    "booking_number": booking.booking_number,
                    "workshop_id": str(workshop.id),
                    "workshop_name": workshop.display_name,
                    "preferred_date": str(preferred_date),
                    "vehicle_plate": booking.vehicle_registration_plate,
                },
            )

            # Send notification to workshop owner/admin
            try:
                org_owner = workshop.organisation.created_by
                if org_owner and audit:
                    create_notification(
                        recipient=org_owner,
                        audit_entry=audit,
                        title=f"New Booking Request #{booking.booking_number}",
                        message=f"{buyer.full_name or buyer.email} requested a booking for {booking.vehicle_make} {booking.vehicle_model} on {preferred_date}.",
                        link="/platform?tab=workshop_landing",
                        resource_type="WorkshopBooking",
                        resource_id=str(booking.id),
                        event_type="workshop.booking.created",
                    )
            except Exception as e:
                logger.warning("Failed to dispatch booking notification: %s", e)

            return booking

    @classmethod
    def accept_booking(cls, booking: WorkshopBooking, actor: User, internal_notes: str = '') -> WorkshopBooking:
        with transaction.atomic():
            booking = WorkshopBooking.objects.select_for_update().get(id=booking.id)
            if booking.status not in (BookingStatusChoices.REQUESTED, BookingStatusChoices.UNDER_REVIEW):
                raise DjangoValidationError(f"Cannot accept booking in current status: {booking.status}")

            booking.status = BookingStatusChoices.ACCEPTED
            if internal_notes:
                booking.internal_notes = internal_notes
            booking.save(update_fields=['status', 'internal_notes', 'updated_at'])

            audit = record_audit_entry(
                event_type="workshop.booking.accepted",
                action="workshop:booking.accept",
                resource_type="WorkshopBooking",
                resource_id=str(booking.id),
                actor_id=actor.id,
                metadata={"booking_number": booking.booking_number, "status": booking.status},
            )

            try:
                if audit:
                    create_notification(
                        recipient=booking.buyer,
                        audit_entry=audit,
                        title=f"Booking Accepted #{booking.booking_number}",
                        message=f"{booking.workshop.display_name} has accepted your booking request.",
                        link="/platform?tab=my_orders",
                        resource_type="WorkshopBooking",
                        resource_id=str(booking.id),
                        event_type="workshop.booking.accepted",
                    )
            except Exception as e:
                logger.warning("Failed to dispatch accept notification: %s", e)

            return booking

    @classmethod
    def reject_booking(cls, booking: WorkshopBooking, reason: str, actor: User) -> WorkshopBooking:
        if not reason or not reason.strip():
            raise DjangoValidationError("A rejection reason is mandatory.")

        with transaction.atomic():
            booking = WorkshopBooking.objects.select_for_update().get(id=booking.id)
            if booking.status in (BookingStatusChoices.CONFIRMED, BookingStatusChoices.CANCELLED, BookingStatusChoices.REJECTED):
                raise DjangoValidationError(f"Cannot reject booking in current status: {booking.status}")

            booking.status = BookingStatusChoices.REJECTED
            booking.rejection_reason = reason.strip()
            booking.save(update_fields=['status', 'rejection_reason', 'updated_at'])

            audit = record_audit_entry(
                event_type="workshop.booking.rejected",
                action="workshop:booking.reject",
                resource_type="WorkshopBooking",
                resource_id=str(booking.id),
                actor_id=actor.id,
                metadata={"booking_number": booking.booking_number, "reason": reason},
            )

            try:
                if audit:
                    create_notification(
                        recipient=booking.buyer,
                        audit_entry=audit,
                        title=f"Booking Update #{booking.booking_number}",
                        message=f"{booking.workshop.display_name} could not accept your booking: {reason}",
                        link="/platform?tab=my_orders",
                        resource_type="WorkshopBooking",
                        resource_id=str(booking.id),
                        event_type="workshop.booking.rejected",
                    )
            except Exception as e:
                logger.warning("Failed to dispatch rejection notification: %s", e)

            return booking

    @classmethod
    def schedule_appointment(
        cls,
        booking: WorkshopBooking,
        start_time,
        end_time,
        technician_id=None,
        internal_notes: str = '',
        actor: User = None,
    ) -> WorkshopBooking:
        """
        Transaction-safe appointment slot allocation checking workshop simultaneous bay capacity.
        """
        if end_time <= start_time:
            raise DjangoValidationError("Scheduled appointment end time must be after start time.")

        with transaction.atomic():
            # Lock the workshop profile row to serialize concurrent scheduling
            workshop = WorkshopProfile.objects.select_for_update().get(id=booking.workshop_id)
            booking = WorkshopBooking.objects.select_for_update().get(id=booking.id)

            if booking.status in (BookingStatusChoices.CANCELLED, BookingStatusChoices.REJECTED):
                raise DjangoValidationError(f"Cannot schedule an appointment for a {booking.status} booking.")

            # Count overlapping confirmed / scheduled appointments
            overlapping_count = WorkshopBooking.objects.filter(
                workshop=workshop,
                status__in=[BookingStatusChoices.ACCEPTED, BookingStatusChoices.CONFIRMED],
                scheduled_appointment_start__lt=end_time,
                scheduled_appointment_end__gt=start_time,
            ).exclude(id=booking.id).count()

            if overlapping_count >= workshop.bay_capacity:
                raise CapacityExceededError(
                    f"Workshop bay capacity ({workshop.bay_capacity}) is fully booked during this time window ({overlapping_count} active bookings)."
                )

            booking.scheduled_appointment_start = start_time
            booking.scheduled_appointment_end = end_time
            booking.status = BookingStatusChoices.CONFIRMED

            if technician_id:
                tech = User.objects.get(id=technician_id)
                booking.assigned_technician = tech
            if internal_notes:
                booking.internal_notes = internal_notes

            booking.save()

            audit = record_audit_entry(
                event_type="workshop.booking.scheduled",
                action="workshop:booking.schedule",
                resource_type="WorkshopBooking",
                resource_id=str(booking.id),
                actor_id=(actor.id if actor else booking.workshop.organisation.created_by.id),
                metadata={
                    "booking_number": booking.booking_number,
                    "scheduled_start": start_time.isoformat(),
                    "scheduled_end": end_time.isoformat(),
                },
            )

            try:
                if audit:
                    create_notification(
                        recipient=booking.buyer,
                        audit_entry=audit,
                        title=f"Appointment Confirmed #{booking.booking_number}",
                        message=f"Your appointment at {workshop.display_name} has been scheduled for {start_time.strftime('%d %b %Y at %H:%M')}.",
                        link="/platform?tab=my_orders",
                        resource_type="WorkshopBooking",
                        resource_id=str(booking.id),
                        event_type="workshop.booking.scheduled",
                    )
            except Exception as e:
                logger.warning("Failed to dispatch schedule notification: %s", e)

            return booking

    @classmethod
    def cancel_booking(cls, booking: WorkshopBooking, reason: str, actor: User) -> WorkshopBooking:
        if not reason or not reason.strip():
            raise DjangoValidationError("A cancellation reason is required.")

        with transaction.atomic():
            booking = WorkshopBooking.objects.select_for_update().get(id=booking.id)
            if booking.status == BookingStatusChoices.CANCELLED:
                raise DjangoValidationError("Booking is already cancelled.")

            booking.status = BookingStatusChoices.CANCELLED
            booking.cancellation_reason = reason.strip()
            booking.cancelled_by = actor
            booking.cancelled_at = timezone.now()
            booking.save(update_fields=['status', 'cancellation_reason', 'cancelled_by', 'cancelled_at', 'updated_at'])

            audit = record_audit_entry(
                event_type="workshop.booking.cancelled",
                action="workshop:booking.cancel",
                resource_type="WorkshopBooking",
                resource_id=str(booking.id),
                actor_id=actor.id,
                metadata={"booking_number": booking.booking_number, "reason": reason},
            )

            # Notify the opposite party
            try:
                recipient = booking.workshop.organisation.created_by if actor == booking.buyer else booking.buyer
                if recipient and audit:
                    create_notification(
                        recipient=recipient,
                        audit_entry=audit,
                        title=f"Booking Cancelled #{booking.booking_number}",
                        message=f"Booking #{booking.booking_number} was cancelled by {actor.full_name or actor.email}. Reason: {reason}",
                        link="/platform",
                        resource_type="WorkshopBooking",
                        resource_id=str(booking.id),
                        event_type="workshop.booking.cancelled",
                    )
            except Exception as e:
                logger.warning("Failed to dispatch cancellation notification: %s", e)

            return booking


class QuotationService:

    @classmethod
    def create_or_revise_quotation(cls, booking: WorkshopBooking, data: dict, actor: User) -> WorkshopQuotation:
        """
        Creates a new draft quotation, or increments version if a previous quote was issued/rejected.
        """
        line_items_data = data.get('line_items', [])
        discount_amount = data.get('discount_amount', Decimal('0.00'))
        tax_rate_percent = data.get('tax_rate_percent')
        valid_until = data.get('valid_until')
        workshop_notes = data.get('workshop_notes', '')
        terms_and_conditions = data.get('terms_and_conditions', '')

        with transaction.atomic():
            # Lock booking row to prevent concurrent version assignment races
            booking = WorkshopBooking.objects.select_for_update().get(id=booking.id)

            # Check if an existing unissued DRAFT quotation exists for this booking
            draft_quotation = WorkshopQuotation.objects.filter(
                booking=booking,
                status=QuotationStatusChoices.DRAFT,
            ).order_by('-version').first()

            if draft_quotation:
                quotation = draft_quotation
                # Clear existing draft line items to replace with revised items
                quotation.line_items.all().delete()
                quotation.discount_amount = discount_amount
                if tax_rate_percent is not None:
                    quotation.tax_rate_percent = tax_rate_percent
                quotation.valid_until = valid_until
                quotation.workshop_notes = workshop_notes
                quotation.terms_and_conditions = terms_and_conditions
                quotation.save()
            else:
                # Create next version
                latest_version = WorkshopQuotation.objects.filter(booking=booking).aggregate(
                    models_max=models.Max('version')
                )['models_max'] or 0

                quotation = WorkshopQuotation(
                    booking=booking,
                    version=latest_version + 1,
                    status=QuotationStatusChoices.DRAFT,
                    discount_amount=discount_amount,
                    valid_until=valid_until,
                    workshop_notes=workshop_notes,
                    terms_and_conditions=terms_and_conditions,
                    created_by=actor,
                )
                if tax_rate_percent is not None:
                    quotation.tax_rate_percent = tax_rate_percent
                quotation.save()

            # Insert line items
            for item in line_items_data:
                catalogue_part = None
                part_id = item.get('catalogue_part_id')
                if part_id:
                    catalogue_part = Part.objects.filter(id=part_id).first()

                QuotationLineItem.objects.create(
                    quotation=quotation,
                    item_type=item.get('item_type', LineItemTypeChoices.LABOUR),
                    description=item['description'],
                    part_number=item.get('part_number', ''),
                    catalogue_part=catalogue_part,
                    quantity=Decimal(str(item.get('quantity', '1.00'))),
                    unit_price=Decimal(str(item.get('unit_price', '0.00'))),
                )

            # Recalculate totals with Decimal precision and commit
            quotation.recalculate_totals(commit=True)

            record_audit_entry(
                event_type="workshop.quotation.drafted",
                action="workshop:quotation.draft",
                resource_type="WorkshopQuotation",
                resource_id=str(quotation.id),
                actor_id=actor.id,
                metadata={
                    "quotation_number": quotation.quotation_number,
                    "booking_number": booking.booking_number,
                    "version": quotation.version,
                    "total_amount": str(quotation.total_amount),
                },
            )

            return quotation

    @classmethod
    def issue_quotation(cls, quotation: WorkshopQuotation, actor: User) -> WorkshopQuotation:
        with transaction.atomic():
            quotation = WorkshopQuotation.objects.select_for_update().get(id=quotation.id)
            booking = WorkshopBooking.objects.select_for_update().get(id=quotation.booking_id)

            if quotation.status != QuotationStatusChoices.DRAFT:
                raise DjangoValidationError(f"Only draft quotations can be issued (current: {quotation.status}).")
            if quotation.line_items.count() == 0:
                raise DjangoValidationError("Cannot issue an empty quotation with no line items.")

            # Supersede any previously ISSUED quotation for this booking
            WorkshopQuotation.objects.filter(
                booking=booking,
                status=QuotationStatusChoices.ISSUED,
            ).exclude(id=quotation.id).update(status=QuotationStatusChoices.SUPERSEDED)

            quotation.status = QuotationStatusChoices.ISSUED
            quotation.issued_at = timezone.now()
            quotation.save(update_fields=['status', 'issued_at', 'updated_at'])

            # Update booking status to QUOTED if still pending
            if booking.status in (BookingStatusChoices.REQUESTED, BookingStatusChoices.UNDER_REVIEW, BookingStatusChoices.ACCEPTED):
                booking.status = BookingStatusChoices.QUOTED
                booking.save(update_fields=['status', 'updated_at'])

            audit = record_audit_entry(
                event_type="workshop.quotation.issued",
                action="workshop:quotation.issue",
                resource_type="WorkshopQuotation",
                resource_id=str(quotation.id),
                actor_id=actor.id,
                metadata={
                    "quotation_number": quotation.quotation_number,
                    "booking_number": booking.booking_number,
                    "version": quotation.version,
                    "total_amount": str(quotation.total_amount),
                    "currency": quotation.currency,
                },
            )

            try:
                if audit:
                    create_notification(
                        recipient=booking.buyer,
                        audit_entry=audit,
                        title=f"Quotation Ready #{quotation.quotation_number}",
                        message=f"{booking.workshop.display_name} has prepared an estimate of {quotation.currency} {quotation.total_amount} for your review.",
                        link="/platform?tab=my_orders",
                        resource_type="WorkshopQuotation",
                        resource_id=str(quotation.id),
                        event_type="workshop.quotation.issued",
                    )
            except Exception as e:
                logger.warning("Failed to dispatch quote issue notification: %s", e)

            return quotation

    @classmethod
    def accept_quotation(cls, quotation: WorkshopQuotation, buyer: User) -> WorkshopQuotation:
        with transaction.atomic():
            quotation = WorkshopQuotation.objects.select_for_update().get(id=quotation.id)
            booking = WorkshopBooking.objects.select_for_update().get(id=quotation.booking_id)

            if booking.buyer_id != buyer.id:
                raise DjangoValidationError("Only the customer who placed this booking can accept this quotation.")
            if quotation.status != QuotationStatusChoices.ISSUED:
                raise DjangoValidationError(f"Cannot accept quotation in '{quotation.status}' status (must be ISSUED).")

            # Mark quotation as ACCEPTED
            quotation.status = QuotationStatusChoices.ACCEPTED
            quotation.accepted_at = timezone.now()
            quotation.save(update_fields=['status', 'accepted_at', 'updated_at'])

            # Update booking status
            if booking.status != BookingStatusChoices.CONFIRMED:
                booking.status = BookingStatusChoices.CONFIRMED
                booking.save(update_fields=['status', 'updated_at'])

            audit = record_audit_entry(
                event_type="workshop.quotation.accepted",
                action="workshop:quotation.accept",
                resource_type="WorkshopQuotation",
                resource_id=str(quotation.id),
                actor_id=buyer.id,
                metadata={
                    "quotation_number": quotation.quotation_number,
                    "booking_number": booking.booking_number,
                    "version": quotation.version,
                    "total_amount": str(quotation.total_amount),
                },
            )

            try:
                org_owner = booking.workshop.organisation.created_by
                if org_owner and audit:
                    create_notification(
                        recipient=org_owner,
                        audit_entry=audit,
                        title=f"Quotation Accepted #{quotation.quotation_number}",
                        message=f"Customer {buyer.full_name or buyer.email} has accepted quotation #{quotation.quotation_number} ({quotation.currency} {quotation.total_amount}).",
                        link="/platform?tab=workshop_landing",
                        resource_type="WorkshopQuotation",
                        resource_id=str(quotation.id),
                        event_type="workshop.quotation.accepted",
                    )
            except Exception as e:
                logger.warning("Failed to dispatch quotation accepted notification: %s", e)

            return quotation

    @classmethod
    def reject_quotation(cls, quotation: WorkshopQuotation, buyer: User, reason: str = '') -> WorkshopQuotation:
        with transaction.atomic():
            quotation = WorkshopQuotation.objects.select_for_update().get(id=quotation.id)
            booking = WorkshopBooking.objects.select_for_update().get(id=quotation.booking_id)

            if booking.buyer_id != buyer.id:
                raise DjangoValidationError("Only the customer who placed this booking can reject this quotation.")
            if quotation.status != QuotationStatusChoices.ISSUED:
                raise DjangoValidationError(f"Cannot reject quotation in '{quotation.status}' status (must be ISSUED).")

            quotation.status = QuotationStatusChoices.REJECTED
            quotation.customer_rejection_reason = reason.strip() if reason else ''
            quotation.rejected_at = timezone.now()
            quotation.save(update_fields=['status', 'customer_rejection_reason', 'rejected_at', 'updated_at'])

            audit = record_audit_entry(
                event_type="workshop.quotation.rejected",
                action="workshop:quotation.reject",
                resource_type="WorkshopQuotation",
                resource_id=str(quotation.id),
                actor_id=buyer.id,
                metadata={
                    "quotation_number": quotation.quotation_number,
                    "booking_number": booking.booking_number,
                    "reason": reason,
                },
            )

            try:
                org_owner = booking.workshop.organisation.created_by
                if org_owner and audit:
                    create_notification(
                        recipient=org_owner,
                        audit_entry=audit,
                        title=f"Quotation Declined #{quotation.quotation_number}",
                        message=f"Customer declined quotation #{quotation.quotation_number}. Reason: {reason or 'No reason provided'}",
                        link="/platform?tab=workshop_landing",
                        resource_type="WorkshopQuotation",
                        resource_id=str(quotation.id),
                        event_type="workshop.quotation.rejected",
                    )
            except Exception as e:
                logger.warning("Failed to dispatch quotation rejected notification: %s", e)

            return quotation
