import logging
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction, IntegrityError, models
from django.core.exceptions import ValidationError as DjangoValidationError, PermissionDenied
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
    DepositStatusChoices,
    LineItemTypeChoices,
    WorkOrder,
    WorkOrderTask,
    WorkOrderPartUsage,
    WorkOrderStatusChoices,
    WorkOrderTaskStatusChoices,
    ChangeOrder,
    ChangeOrderLineItem,
    ChangeOrderStatusChoices,
    WorkshopReview,
    ReviewStatusChoices,
    WorkshopDepositWebhookEvent,
)
from apps.garage.models import GarageVehicle
from apps.catalogue.models import Part
from apps.identity.models import User
from platform_core.audit.writer import record_audit_entry
from apps.notifications.services import create_notification
from apps.workshops.deposit_service import WorkshopDepositPaymentService

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
                status__in=[BookingStatusChoices.ACCEPTED, BookingStatusChoices.CONFIRMED, BookingStatusChoices.QUOTED],
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
        workshop_currency = booking.workshop.currency
        client_currency = data.get('currency')
        if client_currency and client_currency.strip().upper() != workshop_currency.upper():
            raise DjangoValidationError(
                f"Conflicting quotation currency '{client_currency}' rejected. "
                f"Quotation must use workshop currency '{workshop_currency}'."
            )

        line_items_data = data.get('line_items', [])
        discount_amount = data.get('discount_amount', Decimal('0.00'))
        tax_rate_percent = data.get('tax_rate_percent')
        valid_until = data.get('valid_until')
        workshop_notes = data.get('workshop_notes', '')
        terms_and_conditions = data.get('terms_and_conditions', '')
        requires_deposit = data.get('requires_deposit')
        deposit_percentage = data.get('deposit_percentage')
        deposit_amount = data.get('deposit_amount')

        with transaction.atomic():
            # Lock booking row to prevent concurrent version assignment races
            booking = WorkshopBooking.objects.select_for_update().get(id=booking.id)

            if requires_deposit is None and getattr(booking.workshop, 'requires_deposit', False):
                requires_deposit = True
                if deposit_percentage is None:
                    deposit_percentage = getattr(booking.workshop, 'default_deposit_percentage', Decimal('0.00'))

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
                if requires_deposit:
                    quotation.requires_deposit = True
                    if deposit_percentage is not None:
                        quotation.deposit_percentage = Decimal(str(deposit_percentage))
                    if deposit_amount is not None:
                        quotation.deposit_amount = Decimal(str(deposit_amount))
                    quotation.deposit_status = DepositStatusChoices.NOT_REQUIRED
                elif requires_deposit is False:
                    quotation.requires_deposit = False
                    quotation.deposit_percentage = Decimal('0.00')
                    quotation.deposit_amount = Decimal('0.00')
                    quotation.deposit_status = DepositStatusChoices.NOT_REQUIRED
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
                    currency=workshop_currency,
                )
                if tax_rate_percent is not None:
                    quotation.tax_rate_percent = tax_rate_percent
                if requires_deposit:
                    quotation.requires_deposit = True
                    if deposit_percentage is not None:
                        quotation.deposit_percentage = Decimal(str(deposit_percentage))
                    if deposit_amount is not None:
                        quotation.deposit_amount = Decimal(str(deposit_amount))
                    quotation.deposit_status = DepositStatusChoices.NOT_REQUIRED
                elif requires_deposit is False:
                    quotation.requires_deposit = False
                    quotation.deposit_percentage = Decimal('0.00')
                    quotation.deposit_amount = Decimal('0.00')
                    quotation.deposit_status = DepositStatusChoices.NOT_REQUIRED
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
            if quotation.requires_deposit and quotation.deposit_status == DepositStatusChoices.NOT_REQUIRED:
                quotation.deposit_status = DepositStatusChoices.PENDING
            quotation.save(update_fields=['status', 'issued_at', 'deposit_status', 'updated_at'])

            # Update booking status to QUOTED if still pending or confirmed without an active work order
            if booking.status in (
                BookingStatusChoices.REQUESTED,
                BookingStatusChoices.UNDER_REVIEW,
                BookingStatusChoices.ACCEPTED,
                BookingStatusChoices.CONFIRMED,
            ):
                from apps.workshops.models import WorkOrder
                if not WorkOrder.objects.filter(booking=booking).exists():
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

            if quotation.requires_deposit and quotation.deposit_status != DepositStatusChoices.PAID:
                raise DjangoValidationError(
                    f"Quotation #{quotation.quotation_number} requires an upfront deposit payment of "
                    f"{quotation.currency} {quotation.deposit_amount} before it can be accepted."
                )

            # Mark quotation as ACCEPTED
            quotation.status = QuotationStatusChoices.ACCEPTED
            quotation.accepted_at = timezone.now()
            quotation.save(update_fields=['status', 'accepted_at', 'updated_at'])

            # Update booking status
            if booking.status != BookingStatusChoices.CONFIRMED:
                booking.status = BookingStatusChoices.CONFIRMED
                booking.save(update_fields=['status', 'updated_at'])

            # Automatically create Work Order upon quotation acceptance
            WorkOrderService.create_work_order_for_booking(
                booking=booking,
                quotation=quotation,
                actor=buyer,
            )

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



class WorkOrderService:
    """
    Business logic and lifecycle state transitions for Workshop Work Orders.
    """

    @classmethod
    def create_work_order_for_booking(
        cls,
        booking: WorkshopBooking,
        quotation: WorkshopQuotation,
        actor: User,
    ) -> WorkOrder:
        """
        Creates a new WorkOrder upon buyer acceptance of a WorkshopQuotation.
        Pre-populates tasks from quotation labour items and parts usage from quotation part items.
        Idempotent: if a work order already exists for this booking, returns it.
        """
        existing = WorkOrder.objects.filter(booking=booking).first()
        if existing:
            return existing

        if quotation.status != QuotationStatusChoices.ACCEPTED:
            raise DjangoValidationError("Work orders can only be created for accepted quotations.")

        if quotation.booking_id != booking.id:
            raise DjangoValidationError("The accepted quotation does not belong to the specified booking.")

        if quotation.booking.workshop_id != booking.workshop_id:
            raise DjangoValidationError("The quotation and booking must belong to the same workshop.")

        try:
            with transaction.atomic():
                work_order = WorkOrder(
                    booking=booking,
                    quotation=quotation,
                    workshop=booking.workshop,
                    buyer=booking.buyer,
                    vehicle=booking.vehicle,
                    vehicle_make=booking.vehicle_make,
                    vehicle_model=booking.vehicle_model,
                    vehicle_year=booking.vehicle_year,
                    vehicle_registration_plate=booking.vehicle_registration_plate,
                    vehicle_vin=booking.vehicle_vin,
                    current_odometer=booking.current_odometer,
                    odometer_unit=booking.odometer_unit or (booking.vehicle.odometer_unit if booking.vehicle_id else 'mi'),
                    lead_technician=booking.assigned_technician,
                    assigned_by=actor if booking.assigned_technician else None,
                    assigned_at=timezone.now() if booking.assigned_technician else None,
                    status=WorkOrderStatusChoices.ASSIGNED,
                )
                work_order.full_clean()
                work_order.save()

                # Pre-populate tasks from quotation labour and diagnostic items.
                # Conversion: multiply the original decimal quantity by 60 before rounding:
                # (quantity * Decimal('60')).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
                tasks_to_create = []
                order_idx = 0
                for item in quotation.line_items.all():
                    if item.item_type in (LineItemTypeChoices.LABOUR, LineItemTypeChoices.DIAGNOSTIC):
                        quantity = item.quantity if item.quantity is not None else Decimal('1.00')
                        est_minutes = int((quantity * Decimal('60')).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

                        tasks_to_create.append(
                            WorkOrderTask(
                                work_order=work_order,
                                description=item.description,
                                assigned_technician=work_order.lead_technician,
                                estimated_labour_minutes=est_minutes,
                                status=WorkOrderTaskStatusChoices.PENDING,
                                order_index=order_idx,
                            )
                        )
                        order_idx += 1

                if tasks_to_create:
                    WorkOrderTask.objects.bulk_create(tasks_to_create)

                # NOTE: Quotation PART line items represent planned/estimated parts quoted to the customer.
                # They are accessible via work_order.quotation.line_items.
                # WorkOrderPartUsage strictly tracks actual floor parts consumption recorded during repair,
                # avoiding premature assumption of inventory consumption before work commences.

                # Record audit entry
                audit = record_audit_entry(
                    event_type="workshop.workorder.created",
                    action="workshop:workorder.create",
                    resource_type="WorkOrder",
                    resource_id=str(work_order.id),
                    actor_id=actor.id,
                    metadata={
                        "work_order_number": work_order.work_order_number,
                        "booking_number": booking.booking_number,
                        "quotation_number": quotation.quotation_number,
                        "vehicle_plate": work_order.vehicle_registration_plate,
                        "status": work_order.status,
                    },
                )

                # Notify workshop owner
                try:
                    org_owner = booking.workshop.organisation.created_by
                    if org_owner and audit:
                        create_notification(
                            recipient=org_owner,
                            audit_entry=audit,
                            title=f"Work Order Created #{work_order.work_order_number}",
                            message=f"Work Order #{work_order.work_order_number} has been generated for {work_order.vehicle_make} {work_order.vehicle_model} ({work_order.vehicle_registration_plate}).",
                            link="/platform?tab=workshop_landing",
                            resource_type="WorkOrder",
                            resource_id=str(work_order.id),
                            event_type="workshop.workorder.created",
                        )
                except Exception as e:
                    logger.warning("Failed to dispatch work order created notification: %s", e)

                return work_order
        except IntegrityError:
            existing = WorkOrder.objects.filter(booking=booking).first()
            if existing:
                return existing
            raise

    @classmethod
    def assign_technician(
        cls,
        work_order: WorkOrder,
        technician: User,
        actor: User,
    ) -> WorkOrder:
        """
        Assigns or reassigns lead technician to a WorkOrder.
        Validates technician is an active member of the workshop organisation.
        """
        with transaction.atomic():
            work_order = WorkOrder.objects.select_for_update().get(id=work_order.id)

            # Validate technician is active member of this workshop organisation
            org = work_order.workshop.organisation
            is_member = org.memberships.filter(user=technician, is_active=True).exists()
            if not is_member and not (technician.is_staff or technician.is_superuser):
                raise DjangoValidationError("Selected technician must be an active member of this workshop organisation.")

            work_order.lead_technician = technician
            work_order.assigned_by = actor
            work_order.assigned_at = timezone.now()
            work_order.save(update_fields=['lead_technician', 'assigned_by', 'assigned_at', 'updated_at'])

            # Also sync to booking if not already set
            if work_order.booking.assigned_technician_id != technician.id:
                work_order.booking.assigned_technician = technician
                work_order.booking.save(update_fields=['assigned_technician', 'updated_at'])

            audit = record_audit_entry(
                event_type="workshop.workorder.assigned",
                action="workshop:workorder.assign",
                resource_type="WorkOrder",
                resource_id=str(work_order.id),
                actor_id=actor.id,
                metadata={
                    "work_order_number": work_order.work_order_number,
                    "technician_id": str(technician.id),
                    "technician_name": technician.full_name or technician.email,
                },
            )

            # Notify the assigned technician
            try:
                if audit and technician.id != actor.id:
                    create_notification(
                        recipient=technician,
                        audit_entry=audit,
                        title=f"Work Order Assigned #{work_order.work_order_number}",
                        message=f"You have been assigned as lead technician on Work Order #{work_order.work_order_number} ({work_order.vehicle_make} {work_order.vehicle_model}).",
                        link="/platform?tab=workshop_landing",
                        resource_type="WorkOrder",
                        resource_id=str(work_order.id),
                        event_type="workshop.workorder.assigned",
                    )
            except Exception as e:
                logger.warning("Failed to dispatch technician assigned notification: %s", e)

            return work_order

    @classmethod
    def update_status(
        cls,
        work_order: WorkOrder,
        new_status: str,
        actor: User,
        internal_notes: str = '',
        quality_notes: str = '',
        cancellation_reason: str = '',
    ) -> WorkOrder:
        """
        Executes a validated status transition for a WorkOrder:
        - ASSIGNED -> IN_PROGRESS
        - IN_PROGRESS -> AWAITING_PARTS
        - AWAITING_PARTS -> IN_PROGRESS
        - IN_PROGRESS -> QUALITY_CHECK
        - QUALITY_CHECK -> IN_PROGRESS (inspection failed, returned for rework)
        - QUALITY_CHECK -> COMPLETED (inspection passed, repair completed)
        - CANCELLED (from any non-completed state)
        """
        valid_transitions = {
            WorkOrderStatusChoices.ASSIGNED: [
                WorkOrderStatusChoices.IN_PROGRESS,
                WorkOrderStatusChoices.CANCELLED,
            ],
            WorkOrderStatusChoices.IN_PROGRESS: [
                WorkOrderStatusChoices.AWAITING_PARTS,
                WorkOrderStatusChoices.QUALITY_CHECK,
                WorkOrderStatusChoices.CANCELLED,
            ],
            WorkOrderStatusChoices.AWAITING_PARTS: [
                WorkOrderStatusChoices.IN_PROGRESS,
                WorkOrderStatusChoices.CANCELLED,
            ],
            WorkOrderStatusChoices.QUALITY_CHECK: [
                WorkOrderStatusChoices.IN_PROGRESS,  # Inspection failed
                WorkOrderStatusChoices.COMPLETED,    # Inspection passed
                WorkOrderStatusChoices.CANCELLED,
            ],
            WorkOrderStatusChoices.COMPLETED: [],  # Terminal
            WorkOrderStatusChoices.CANCELLED: [],  # Terminal
        }

        with transaction.atomic():
            work_order = WorkOrder.objects.select_for_update().get(id=work_order.id)
            current_status = work_order.status

            if new_status == current_status:
                return work_order

            allowed = valid_transitions.get(current_status, [])
            if new_status not in allowed:
                raise DjangoValidationError(
                    f"Cannot transition Work Order from '{current_status}' to '{new_status}'."
                )

            # Apply state updates
            work_order.status = new_status
            update_fields = ['status', 'updated_at']

            if internal_notes:
                work_order.internal_notes = internal_notes
                update_fields.append('internal_notes')

            if new_status == WorkOrderStatusChoices.IN_PROGRESS:
                if not work_order.started_at:
                    work_order.started_at = timezone.now()
                    update_fields.append('started_at')

            elif new_status == WorkOrderStatusChoices.QUALITY_CHECK:
                work_order.quality_inspected_at = timezone.now()
                work_order.quality_inspected_by = actor
                if quality_notes:
                    work_order.quality_notes = quality_notes
                    update_fields.append('quality_notes')
                update_fields.extend(['quality_inspected_at', 'quality_inspected_by'])

            elif new_status == WorkOrderStatusChoices.COMPLETED:
                # Must be coming from QUALITY_CHECK
                if current_status != WorkOrderStatusChoices.QUALITY_CHECK:
                    raise DjangoValidationError("Work order must pass Quality Check before being marked completed.")
                # Prevent completion while unresolved change orders exist
                if work_order.change_orders.filter(status=ChangeOrderStatusChoices.SUBMITTED).exists():
                    raise DjangoValidationError("Cannot complete Work Order while unresolved Change Orders are pending buyer approval.")
                work_order.completed_at = timezone.now()
                if quality_notes:
                    work_order.quality_notes = quality_notes
                    update_fields.append('quality_notes')
                update_fields.append('completed_at')

            elif new_status == WorkOrderStatusChoices.CANCELLED:
                work_order.cancellation_reason = cancellation_reason or 'Work order cancelled by workshop.'
                update_fields.append('cancellation_reason')

                # Automatically restock any parts consumed on this work order
                import math
                from apps.marketplace.models import SparePartListing, StockMovement, StockMovementReasonChoices

                for pu in work_order.parts_used.filter(is_stock_deducted=True, inventory_item__isnull=False).select_related('inventory_item'):
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
                            note=f"Restocked upon cancellation of Work Order {work_order.work_order_number}",
                        )
                        pu.is_stock_deducted = False
                        pu.save(update_fields=['is_stock_deducted', 'updated_at'])

            work_order.save(update_fields=update_fields)

            # Generate platform-verified vehicle service history record upon successful completion
            status_warnings = []
            if new_status == WorkOrderStatusChoices.COMPLETED:
                from apps.garage.services import VehicleServiceHistoryService
                VehicleServiceHistoryService.create_verified_record_for_work_order(
                    work_order=work_order,
                    actor=actor,
                )
                # Check for odometer unit mismatch between vehicle and work order
                vehicle = work_order.vehicle
                if vehicle and getattr(vehicle, 'odometer_unit', None) and work_order.odometer_unit:
                    veh_unit = str(vehicle.odometer_unit).strip().lower()
                    wo_unit = str(work_order.odometer_unit).strip().lower()
                    if veh_unit != wo_unit:
                        status_warnings.append({
                            "code": "ODOMETER_UNIT_MISMATCH",
                            "message": f"Vehicle odometer not updated due to unit mismatch (vehicle: {veh_unit}, work order: {wo_unit}).",
                            "vehicle_odometer_unit": veh_unit,
                            "work_order_odometer_unit": wo_unit,
                            "vehicle_current_odometer": vehicle.current_odometer,
                            "work_order_odometer_reading": work_order.current_odometer,
                        })

            work_order._status_update_warnings = status_warnings

            # Record audit event
            event_type = f"workshop.workorder.{new_status.lower()}"
            audit_metadata = {
                "work_order_number": work_order.work_order_number,
                "previous_status": current_status,
                "new_status": new_status,
            }
            if status_warnings:
                audit_metadata["warnings"] = status_warnings
                for w in status_warnings:
                    if w.get("code") == "ODOMETER_UNIT_MISMATCH":
                        audit_metadata["odometer_unit_mismatch"] = True
                        audit_metadata["vehicle_odometer_unit"] = w["vehicle_odometer_unit"]
                        audit_metadata["work_order_odometer_unit"] = w["work_order_odometer_unit"]

            audit = record_audit_entry(
                event_type=event_type,
                action="workshop:workorder.status_update",
                resource_type="WorkOrder",
                resource_id=str(work_order.id),
                actor_id=actor.id,
                metadata=audit_metadata,
            )

            # Send notifications
            try:
                if new_status == WorkOrderStatusChoices.IN_PROGRESS:
                    create_notification(
                        recipient=work_order.buyer,
                        audit_entry=audit,
                        title=f"Repair Work Commenced #{work_order.work_order_number}",
                        message=f"Work has started on your {work_order.vehicle_make} {work_order.vehicle_model} at {work_order.workshop.display_name}.",
                        link="/platform?tab=workshops_browse",
                        resource_type="WorkOrder",
                        resource_id=str(work_order.id),
                        event_type="workshop.workorder.in_progress",
                    )
                elif new_status == WorkOrderStatusChoices.QUALITY_CHECK:
                    org_owner = work_order.workshop.organisation.created_by
                    if org_owner:
                        create_notification(
                            recipient=org_owner,
                            audit_entry=audit,
                            title=f"Quality Check Required #{work_order.work_order_number}",
                            message=f"Work Order #{work_order.work_order_number} is ready for quality inspection.",
                            link="/platform?tab=workshop_landing",
                            resource_type="WorkOrder",
                            resource_id=str(work_order.id),
                            event_type="workshop.workorder.quality_check",
                        )
                elif new_status == WorkOrderStatusChoices.COMPLETED:
                    completed_msg = f"Repairs and quality inspection on your {work_order.vehicle_make} {work_order.vehicle_model} have been successfully completed."
                    if status_warnings:
                        for w in status_warnings:
                            if w.get("code") == "ODOMETER_UNIT_MISMATCH":
                                completed_msg += f" Note: Vehicle odometer was not updated due to unit difference ({w['vehicle_odometer_unit']} vs {w['work_order_odometer_unit']})."
                    create_notification(
                        recipient=work_order.buyer,
                        audit_entry=audit,
                        title=f"Service Completed #{work_order.work_order_number}",
                        message=completed_msg,
                        link="/platform?tab=workshops_browse",
                        resource_type="WorkOrder",
                        resource_id=str(work_order.id),
                        event_type="workshop.workorder.completed",
                    )
            except Exception as e:
                logger.warning("Failed to dispatch work order status notification: %s", e)

            return work_order

    @classmethod
    def add_task(
        cls,
        work_order: WorkOrder,
        description: str,
        assigned_technician: User | None = None,
        estimated_labour_minutes: int = 60,
        notes: str = '',
        actor: User | None = None,
    ) -> WorkOrderTask:
        """Adds a new task to a work order."""
        if work_order.status in (WorkOrderStatusChoices.COMPLETED, WorkOrderStatusChoices.CANCELLED):
            raise DjangoValidationError("Cannot add tasks to a completed or cancelled work order.")

        if assigned_technician:
            org = work_order.workshop.organisation
            is_member = org.memberships.filter(user=assigned_technician, is_active=True).exists()
            if not is_member and not (assigned_technician.is_staff or assigned_technician.is_superuser):
                raise DjangoValidationError("Assigned technician must belong to this workshop organisation.")

        task = WorkOrderTask.objects.create(
            work_order=work_order,
            description=description,
            assigned_technician=assigned_technician or work_order.lead_technician,
            estimated_labour_minutes=estimated_labour_minutes,
            notes=notes,
            order_index=work_order.tasks.count(),
        )
        return task

    @classmethod
    def update_task(
        cls,
        task: WorkOrderTask,
        status: str | None = None,
        actual_labour_minutes: int | None = None,
        notes: str | None = None,
        assigned_technician: User | None = None,
        actor: User | None = None,
    ) -> WorkOrderTask:
        """Updates task progress, actual labour time, and status."""
        update_fields = ['updated_at']

        if status:
            task.status = status
            update_fields.append('status')
            if status == WorkOrderTaskStatusChoices.IN_PROGRESS and not task.started_at:
                task.started_at = timezone.now()
                update_fields.append('started_at')
            elif status == WorkOrderTaskStatusChoices.COMPLETED:
                task.completed_at = timezone.now()
                update_fields.append('completed_at')

        if actual_labour_minutes is not None:
            task.actual_labour_minutes = actual_labour_minutes
            update_fields.append('actual_labour_minutes')

        if notes is not None:
            task.notes = notes
            update_fields.append('notes')

        if assigned_technician is not None:
            org = task.work_order.workshop.organisation
            is_member = org.memberships.filter(user=assigned_technician, is_active=True).exists()
            if not is_member and not (assigned_technician.is_staff or assigned_technician.is_superuser):
                raise DjangoValidationError("Assigned technician must belong to this workshop organisation.")
            task.assigned_technician = assigned_technician
            update_fields.append('assigned_technician')

        task.save(update_fields=update_fields)
        return task

    @classmethod
    def record_part_usage(
        cls,
        work_order: WorkOrder,
        part_name: str,
        quantity: Decimal,
        unit_cost: Decimal,
        part_number: str = '',
        description: str = '',
        catalogue_part=None,
        inventory_item=None,
        actor: User | None = None,
    ) -> WorkOrderPartUsage:
        """
        Records physical spare part usage on a work order.
        If linked to workshop inventory (SparePartListing), atomically validates
        and decrements stock, creating a StockMovement ledger audit entry.
        """
        import math
        from apps.marketplace.models import SparePartListing, StockMovement, StockMovementReasonChoices

        if work_order.status in (WorkOrderStatusChoices.COMPLETED, WorkOrderStatusChoices.CANCELLED):
            raise DjangoValidationError("Cannot add parts to a completed or cancelled work order.")

        org = getattr(work_order.workshop, 'organisation', None)
        if not inventory_item and org:
            if part_number:
                inventory_item = SparePartListing.objects.filter(
                    organisation=org,
                    mpn__iexact=part_number,
                ).first()
            if not inventory_item and catalogue_part:
                inventory_item = SparePartListing.objects.filter(
                    organisation=org,
                    catalogue_part=catalogue_part,
                ).first()

        with transaction.atomic():
            is_deducted = False
            qty_units = max(1, int(math.ceil(quantity)))

            if inventory_item:
                listing = SparePartListing.objects.select_for_update().filter(id=inventory_item.id).first()
                if listing:
                    if listing.stock_quantity < qty_units:
                        raise DjangoValidationError(
                            f"Insufficient inventory stock for '{listing.name}'. Available: {listing.stock_quantity}, requested: {qty_units}."
                        )
                    listing.stock_quantity -= qty_units
                    listing.save(update_fields=['stock_quantity', 'updated_at'])

                    StockMovement.objects.create(
                        listing=listing,
                        delta=-qty_units,
                        resulting_quantity=listing.stock_quantity,
                        reason=StockMovementReasonChoices.WORK_ORDER,
                        actor=actor,
                        note=f"Consumed in Work Order {work_order.work_order_number}",
                    )
                    is_deducted = True
                    inventory_item = listing

            part_usage = WorkOrderPartUsage.objects.create(
                work_order=work_order,
                part_name=part_name,
                part_number=part_number,
                description=description,
                catalogue_part=catalogue_part,
                inventory_item=inventory_item,
                is_stock_deducted=is_deducted,
                quantity=quantity,
                unit_cost=unit_cost,
                added_by=actor,
            )

        record_audit_entry(
            event_type="workshop.workorder.part_recorded",
            action="workshop:workorder.part.record",
            resource_type="WorkOrderPartUsage",
            resource_id=str(part_usage.id),
            actor_id=actor.id if actor else None,
            metadata={
                "work_order_number": work_order.work_order_number,
                "part_name": part_name,
                "quantity": str(quantity),
                "total_cost": str(part_usage.total_cost),
                "stock_deducted": is_deducted,
            },
        )
        return part_usage

    @classmethod
    def delete_task(cls, task: WorkOrderTask, actor: User) -> None:
        """Removes a task from an active work order with audit logging."""
        work_order = task.work_order
        if work_order.status in (WorkOrderStatusChoices.COMPLETED, WorkOrderStatusChoices.CANCELLED):
            raise DjangoValidationError("Cannot delete tasks on a completed or cancelled work order.")

        task_id = str(task.id)
        desc = task.description
        labour = task.actual_labour_minutes
        task.delete()

        record_audit_entry(
            event_type="workshop.workorder.task_deleted",
            action="workshop:workorder.task.delete",
            resource_type="WorkOrderTask",
            resource_id=task_id,
            actor_id=actor.id,
            metadata={
                "work_order_number": work_order.work_order_number,
                "description": desc,
                "actual_labour_minutes": labour,
            },
        )

    @classmethod
    def delete_part_usage(cls, part_usage: WorkOrderPartUsage, actor: User) -> None:
        """Removes a recorded part usage entry from an active work order with audit logging and stock restoration."""
        import math
        from apps.marketplace.models import SparePartListing, StockMovement, StockMovementReasonChoices

        work_order = part_usage.work_order
        if work_order.status in (WorkOrderStatusChoices.COMPLETED, WorkOrderStatusChoices.CANCELLED):
            raise DjangoValidationError("Cannot delete parts on a completed or cancelled work order.")

        with transaction.atomic():
            if part_usage.is_stock_deducted and part_usage.inventory_item_id:
                listing = SparePartListing.objects.select_for_update().filter(id=part_usage.inventory_item_id).first()
                if listing:
                    qty_restore = max(1, int(math.ceil(part_usage.quantity)))
                    listing.stock_quantity += qty_restore
                    listing.save(update_fields=['stock_quantity', 'updated_at'])

                    StockMovement.objects.create(
                        listing=listing,
                        delta=qty_restore,
                        resulting_quantity=listing.stock_quantity,
                        reason=StockMovementReasonChoices.WORK_ORDER_RESTOCK,
                        actor=actor,
                        note=f"Restocked from deleted part usage on Work Order {work_order.work_order_number}",
                    )
                    part_usage.is_stock_deducted = False

            part_id = str(part_usage.id)
            part_name = part_usage.part_name
            quantity = str(part_usage.quantity)
            total_cost = str(part_usage.total_cost)
            part_usage.delete()

        record_audit_entry(
            event_type="workshop.workorder.part_deleted",
            action="workshop:workorder.part.delete",
            resource_type="WorkOrderPartUsage",
            resource_id=part_id,
            actor_id=actor.id,
            metadata={
                "work_order_number": work_order.work_order_number,
                "part_name": part_name,
                "quantity": quantity,
                "total_cost": total_cost,
            },
        )

class ChangeOrderService:
    """
    Business logic, authorization workflows and state management for Workshop Change Orders.
    Enforces strict buyer approval before additional repairs or parts are executed.
    """

    @classmethod
    def _validate_workshop_actor(cls, work_order: WorkOrder, actor: User):
        if actor.is_staff or actor.is_superuser:
            return
        org = work_order.workshop.organisation
        is_member = org.memberships.filter(user=actor, is_active=True).exists()
        if not is_member:
            raise DjangoValidationError("You do not have permission to manage change orders for this workshop.")

    @classmethod
    def create_change_order(cls, work_order: WorkOrder, data: dict, actor: User) -> ChangeOrder:
        """
        Creates a new Change Order requesting additional work/parts authorization.
        Validates work order eligibility and actor permissions.
        """
        cls._validate_workshop_actor(work_order, actor)

        if work_order.status in (WorkOrderStatusChoices.COMPLETED, WorkOrderStatusChoices.CANCELLED):
            raise DjangoValidationError(f"Cannot raise a change order for a {work_order.get_status_display().lower()} work order.")

        reason = data.get('reason', '').strip()
        if not reason:
            raise DjangoValidationError("A clear reason for additional work is required.")

        line_items_data = data.get('line_items', [])
        if not line_items_data:
            raise DjangoValidationError("At least one line item is required for a change order.")

        discount_amount = data.get('discount_amount', Decimal('0.00'))
        tax_rate_percent = data.get('tax_rate_percent')
        workshop_notes = data.get('workshop_notes', '')
        submit_for_approval = data.get('submit_for_approval', False) or data.get('status') == ChangeOrderStatusChoices.SUBMITTED

        with transaction.atomic():
            work_order = WorkOrder.objects.select_for_update().get(id=work_order.id)
            if work_order.status in (WorkOrderStatusChoices.COMPLETED, WorkOrderStatusChoices.CANCELLED):
                raise DjangoValidationError(f"Cannot raise a change order for a {work_order.get_status_display().lower()} work order.")

            # Inherit tax rate and currency from workshop if not specified
            workshop = work_order.workshop
            expected_currency = work_order.quotation.currency if work_order.quotation else workshop.currency
            client_currency = data.get('currency')
            if client_currency and client_currency.strip().upper() != expected_currency.upper():
                raise DjangoValidationError(
                    f"Conflicting change order currency '{client_currency}' rejected. "
                    f"Change order must use work order currency '{expected_currency}'."
                )

            can_collect = getattr(workshop, 'can_collect_tax', False) and workshop.is_tax_registered
            if tax_rate_percent is None:
                tax_rate_percent = workshop.default_tax_rate_percent if can_collect else Decimal('0.00')
            elif tax_rate_percent > Decimal('0.00') and not getattr(workshop, 'can_collect_tax', False):
                raise DjangoValidationError(
                    f"Workshop '{workshop.display_name}' is not authorized to collect tax. Change order tax rate must be 0.00%."
                )

            change_order = ChangeOrder(
                work_order=work_order,
                reason=reason,
                discount_amount=discount_amount,
                tax_rate_percent=tax_rate_percent,
                currency=work_order.quotation.currency if work_order.quotation else workshop.currency,
                workshop_notes=workshop_notes,
                created_by=actor,
                status=ChangeOrderStatusChoices.DRAFT,
            )
            change_order.save()

            for item_data in line_items_data:
                catalogue_part = None
                if item_data.get('catalogue_part_id'):
                    catalogue_part = Part.objects.filter(id=item_data['catalogue_part_id']).first()

                qty = Decimal(str(item_data.get('quantity', '1.00')))
                price = Decimal(str(item_data.get('unit_price', '0.00')))
                ChangeOrderLineItem.objects.create(
                    change_order=change_order,
                    item_type=item_data.get('item_type', LineItemTypeChoices.LABOUR),
                    description=item_data.get('description', ''),
                    part_number=item_data.get('part_number', ''),
                    catalogue_part=catalogue_part,
                    quantity=qty,
                    unit_price=price,
                    estimated_labour_minutes=item_data.get('estimated_labour_minutes'),
                )

            change_order.recalculate_totals(commit=True)

            if submit_for_approval:
                cls._submit_change_order_internal(change_order, actor)

            return change_order

    @classmethod
    def _submit_change_order_internal(cls, change_order: ChangeOrder, actor: User) -> ChangeOrder:
        """Internal helper to submit a change order to the buyer and trigger audit and notifications."""
        work_order = change_order.work_order
        change_order.status = ChangeOrderStatusChoices.SUBMITTED
        change_order.submitted_at = timezone.now()
        change_order.save(update_fields=['status', 'submitted_at', 'updated_at'])

        audit = record_audit_entry(
            event_type="workshop.changeorder.submitted",
            action="workshop:changeorder.submit",
            resource_type="ChangeOrder",
            resource_id=str(change_order.id),
            actor_id=actor.id,
            metadata={
                "change_order_number": change_order.change_order_number,
                "work_order_number": work_order.work_order_number,
                "version": change_order.version,
                "additional_amount": str(change_order.additional_amount),
                "revised_authorized_total": str(change_order.revised_authorized_total),
                "currency": change_order.currency,
            },
        )

        try:
            if audit:
                create_notification(
                    recipient=work_order.buyer,
                    audit_entry=audit,
                    title=f"Additional Authorization Required #{change_order.change_order_number}",
                    message=f"{work_order.workshop.display_name} requested authorization for additional work ({change_order.currency} {change_order.additional_amount}) on {work_order.vehicle_registration_plate}. Reason: {change_order.reason[:100]}",
                    link="/platform?tab=my_orders",
                    resource_type="ChangeOrder",
                    resource_id=str(change_order.id),
                    event_type="workshop.changeorder.submitted",
                )
        except Exception as e:
            logger.warning("Failed to dispatch change order submitted notification: %s", e)

        return change_order

    @classmethod
    def submit_change_order(cls, change_order: ChangeOrder, actor: User) -> ChangeOrder:
        """Submits a draft change order for buyer approval."""
        with transaction.atomic():
            change_order = ChangeOrder.objects.select_for_update().get(id=change_order.id)
            work_order = WorkOrder.objects.select_for_update().get(id=change_order.work_order_id)
            cls._validate_workshop_actor(work_order, actor)

            if change_order.status != ChangeOrderStatusChoices.DRAFT:
                raise DjangoValidationError(f"Only draft change orders can be submitted (current status: {change_order.status}).")

            if work_order.status in (WorkOrderStatusChoices.COMPLETED, WorkOrderStatusChoices.CANCELLED):
                raise DjangoValidationError(f"Cannot submit a change order for a {work_order.get_status_display().lower()} work order.")

            if change_order.line_items.count() == 0:
                raise DjangoValidationError("Cannot submit an empty change order with no line items.")

            change_order.recalculate_totals(commit=True)
            return cls._submit_change_order_internal(change_order, actor)

    @classmethod
    def approve_change_order(cls, change_order: ChangeOrder, buyer: User, notes: str = '') -> ChangeOrder:
        """
        Buyer authorizes the additional work and costs described in the change order.
        - Atomically locks WorkOrder and ChangeOrder.
        - Validates buyer ownership and status.
        - Transitions to APPROVED.
        - Spawns WorkOrderTask records for labour items (does NOT consume parts).
        - Dispatches audit logging and notifications.
        """
        with transaction.atomic():
            work_order = WorkOrder.objects.select_for_update().get(id=change_order.work_order_id)
            change_order = ChangeOrder.objects.select_for_update().get(id=change_order.id)

            if work_order.buyer_id != buyer.id and not (buyer.is_staff or buyer.is_superuser):
                raise DjangoValidationError("Only the vehicle owner who placed this booking can authorize additional work.")

            if change_order.status != ChangeOrderStatusChoices.SUBMITTED:
                raise DjangoValidationError(
                    f"Cannot approve Change Order #{change_order.change_order_number} in status '{change_order.status}' (must be SUBMITTED)."
                )

            if work_order.status in (WorkOrderStatusChoices.COMPLETED, WorkOrderStatusChoices.CANCELLED):
                raise DjangoValidationError(f"Cannot approve a change order for a {work_order.get_status_display().lower()} work order.")

            change_order.status = ChangeOrderStatusChoices.APPROVED
            change_order.reviewed_by = buyer
            change_order.reviewed_at = timezone.now()
            change_order.buyer_notes = notes.strip() if notes else ''
            change_order.recalculate_totals(commit=False)
            change_order.save(update_fields=[
                'status', 'reviewed_by', 'reviewed_at', 'buyer_notes',
                'revised_authorized_total', 'updated_at'
            ])

            # Pre-populate tasks from change order labour and diagnostic line items
            max_order_idx = work_order.tasks.aggregate(models.Max('order_index'))['order_index__max'] or 0
            tasks_to_create = []
            for idx, item in enumerate(change_order.line_items.all()):
                if item.item_type in (LineItemTypeChoices.LABOUR, LineItemTypeChoices.DIAGNOSTIC):
                    est_minutes = item.estimated_labour_minutes or 60
                    tasks_to_create.append(
                        WorkOrderTask(
                            work_order=work_order,
                            description=f"[{change_order.change_order_number}] {item.description}",
                            assigned_technician=work_order.lead_technician,
                            estimated_labour_minutes=est_minutes,
                            status=WorkOrderTaskStatusChoices.PENDING,
                            notes=f"Approved under Change Order #{change_order.change_order_number}",
                            order_index=max_order_idx + idx + 1,
                        )
                    )

            if tasks_to_create:
                WorkOrderTask.objects.bulk_create(tasks_to_create)

            # NOTE: Parts in change order represent approved scope.
            # They are NOT automatically marked as consumed until technicians physically install them.

            audit = record_audit_entry(
                event_type="workshop.changeorder.approved",
                action="workshop:changeorder.approve",
                resource_type="ChangeOrder",
                resource_id=str(change_order.id),
                actor_id=buyer.id,
                metadata={
                    "change_order_number": change_order.change_order_number,
                    "work_order_number": work_order.work_order_number,
                    "additional_amount": str(change_order.additional_amount),
                    "revised_authorized_total": str(change_order.revised_authorized_total),
                    "currency": change_order.currency,
                },
            )

            try:
                org_owner = work_order.workshop.organisation.created_by
                if org_owner and audit:
                    create_notification(
                        recipient=org_owner,
                        audit_entry=audit,
                        title=f"Change Order Approved #{change_order.change_order_number}",
                        message=f"Customer {buyer.full_name or buyer.email} approved Change Order #{change_order.change_order_number} (+{change_order.currency} {change_order.additional_amount}) for {work_order.vehicle_registration_plate}.",
                        link="/platform?tab=workshop_landing",
                        resource_type="ChangeOrder",
                        resource_id=str(change_order.id),
                        event_type="workshop.changeorder.approved",
                    )
            except Exception as e:
                logger.warning("Failed to dispatch change order approved notification: %s", e)

            return change_order

    @classmethod
    def reject_change_order(cls, change_order: ChangeOrder, buyer: User, reason: str = '') -> ChangeOrder:
        """
        Buyer declines the additional work or parts request.
        - Atomically locks WorkOrder and ChangeOrder.
        - Validates buyer ownership and status.
        - Transitions to REJECTED.
        - Records buyer rejection reason.
        - Dispatches audit logging and notifications.
        """
        with transaction.atomic():
            work_order = WorkOrder.objects.select_for_update().get(id=change_order.work_order_id)
            change_order = ChangeOrder.objects.select_for_update().get(id=change_order.id)

            if work_order.buyer_id != buyer.id and not (buyer.is_staff or buyer.is_superuser):
                raise DjangoValidationError("Only the vehicle owner who placed this booking can reject this change order.")

            if change_order.status != ChangeOrderStatusChoices.SUBMITTED:
                raise DjangoValidationError(
                    f"Cannot reject Change Order #{change_order.change_order_number} in status '{change_order.status}' (must be SUBMITTED)."
                )

            change_order.status = ChangeOrderStatusChoices.REJECTED
            change_order.reviewed_by = buyer
            change_order.reviewed_at = timezone.now()
            change_order.buyer_notes = reason.strip() if reason else ''
            change_order.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'buyer_notes', 'updated_at'])

            audit = record_audit_entry(
                event_type="workshop.changeorder.rejected",
                action="workshop:changeorder.reject",
                resource_type="ChangeOrder",
                resource_id=str(change_order.id),
                actor_id=buyer.id,
                metadata={
                    "change_order_number": change_order.change_order_number,
                    "work_order_number": work_order.work_order_number,
                    "rejection_reason": change_order.buyer_notes,
                },
            )

            try:
                org_owner = work_order.workshop.organisation.created_by
                if org_owner and audit:
                    create_notification(
                        recipient=org_owner,
                        audit_entry=audit,
                        title=f"Change Order Declined #{change_order.change_order_number}",
                        message=f"Customer declined Change Order #{change_order.change_order_number} for {work_order.vehicle_registration_plate}. Reason: {reason or 'No reason provided'}",
                        link="/platform?tab=workshop_landing",
                        resource_type="ChangeOrder",
                        resource_id=str(change_order.id),
                        event_type="workshop.changeorder.rejected",
                    )
            except Exception as e:
                logger.warning("Failed to dispatch change order rejected notification: %s", e)

            return change_order

    @classmethod
    def cancel_change_order(cls, change_order: ChangeOrder, actor: User, reason: str = '') -> ChangeOrder:
        """Workshop cancels a draft or submitted change order before buyer decision."""
        with transaction.atomic():
            work_order = WorkOrder.objects.select_for_update().get(id=change_order.work_order_id)
            change_order = ChangeOrder.objects.select_for_update().get(id=change_order.id)
            cls._validate_workshop_actor(work_order, actor)

            if change_order.status in (ChangeOrderStatusChoices.APPROVED, ChangeOrderStatusChoices.REJECTED):
                raise DjangoValidationError(f"Cannot cancel a {change_order.status.lower()} change order.")

            change_order.status = ChangeOrderStatusChoices.CANCELLED
            if reason:
                change_order.workshop_notes = (change_order.workshop_notes + f"\nCancelled: {reason}").strip()
            change_order.save(update_fields=['status', 'workshop_notes', 'updated_at'])

            record_audit_entry(
                event_type="workshop.changeorder.cancelled",
                action="workshop:changeorder.cancel",
                resource_type="ChangeOrder",
                resource_id=str(change_order.id),
                actor_id=actor.id,
                metadata={
                    "change_order_number": change_order.change_order_number,
                    "work_order_number": work_order.work_order_number,
                    "reason": reason,
                },
            )

            return change_order


class WorkshopTaxAuthorizationService:
    """
    Administrative service for platform staff to explicitly grant or revoke
    tax collection authorization for a WorkshopProfile.

    Enforces prerequisite tax registration and emits immutable audit logs.
    """

    @classmethod
    def set_tax_collection_authorization(
        cls,
        workshop: WorkshopProfile,
        authorized: bool,
        actor: User,
        reason: str = "",
    ) -> WorkshopProfile:
        from apps.workshops.permissions import is_platform_admin_or_staff

        if not (actor and is_platform_admin_or_staff(actor)):
            raise PermissionDenied("Only authorized platform administrators and staff can modify workshop tax collection permissions.")

        if authorized and not workshop.is_tax_registered:
            raise DjangoValidationError("Cannot authorize tax collection for a workshop that is not tax registered.")

        with transaction.atomic():
            workshop = WorkshopProfile.objects.select_for_update().get(id=workshop.id)
            previous_state = workshop.can_collect_tax
            workshop.can_collect_tax = authorized
            workshop.save(update_fields=['can_collect_tax', 'updated_at'])

            event_type = "workshop.tax_authorization.granted" if authorized else "workshop.tax_authorization.revoked"
            action = "workshop:tax_authorization.grant" if authorized else "workshop:tax_authorization.revoke"

            record_audit_entry(
                event_type=event_type,
                action=action,
                resource_type="WorkshopProfile",
                resource_id=str(workshop.id),
                actor_id=actor.id,
                actor_kind="STAFF" if getattr(actor, 'is_staff', False) else "ADMIN",
                operating_org_id=workshop.organisation_id,
                reason_code=reason or ("TAX_AUTHORIZED" if authorized else "TAX_REVOKED"),
                metadata={
                    "workshop_id": str(workshop.id),
                    "business_name": workshop.business_name,
                    "organisation_id": str(workshop.organisation_id) if workshop.organisation_id else None,
                    "previous_state": previous_state,
                    "new_state": authorized,
                    "is_tax_registered": workshop.is_tax_registered,
                    "reason": reason,
                },
            )

        return workshop


class WorkshopReviewService:
    """
    Orchestrates review eligibility checks, verified review submissions,
    workshop public responses, and reputation metrics calculation.
    """

    @classmethod
    def check_review_eligibility(cls, booking: WorkshopBooking, user: User) -> tuple[bool, str, WorkOrder | None]:
        """
        Validates whether user is eligible to submit a review for the booking.
        Eligibility rules:
        1. User must be authenticated.
        2. Authenticated user must be the actual booking buyer (booking.buyer_id == user.id).
        3. Booking must not be cancelled.
        4. WorkOrder must exist and belong to this booking and workshop.
        5. WorkOrder status must be COMPLETED.
        6. WorkOrder completed_at must be populated.
        7. Booking must not already have a review submitted.
        """
        if not user or not user.is_authenticated:
            return False, "Authentication required to review workshop services.", None

        if booking.buyer_id != user.id:
            from apps.workshops.permissions import is_platform_admin_or_staff
            if not is_platform_admin_or_staff(user):
                return False, "You can only review bookings placed by your account.", None

        if booking.status == BookingStatusChoices.CANCELLED:
            return False, f"Booking {booking.booking_number} is cancelled. Cancelled bookings cannot be reviewed.", None

        if not hasattr(booking, 'work_order') or not booking.work_order:
            return False, f"No work order found for booking {booking.booking_number}. Services must have an operational work order to be reviewed.", None

        work_order = booking.work_order
        if work_order.workshop_id != booking.workshop_id:
            return False, "Work order does not match the booking workshop.", None

        if work_order.status != WorkOrderStatusChoices.COMPLETED:
            return False, f"Work order {work_order.work_order_number} is currently '{work_order.get_status_display()}'. Reviews can only be submitted after work is marked COMPLETED.", work_order

        if not work_order.completed_at:
            return False, f"Work order {work_order.work_order_number} has no recorded completion date.", work_order

        if hasattr(booking, 'review') and booking.review:
            return False, "A review has already been submitted for this service booking.", work_order

        if WorkshopReview.objects.filter(booking=booking).exists():
            return False, "A review has already been submitted for this service booking.", work_order

        return True, "Eligible to review.", work_order

    @classmethod
    def create_review(
        cls,
        booking: WorkshopBooking,
        buyer: User,
        data: dict,
        actor: User | None = None,
    ) -> WorkshopReview:
        """
        Creates a verified workshop review.
        Enforces eligibility, database transactions, locking, and audit/notification dispatch.
        """
        is_eligible, err_msg, work_order = cls.check_review_eligibility(booking, buyer)
        if not is_eligible:
            raise DjangoValidationError(err_msg)

        # Validate rating
        raw_rating = data.get('rating')
        if raw_rating is None:
            raise DjangoValidationError("Overall rating is required.")
        try:
            rating = int(raw_rating)
        except (ValueError, TypeError):
            raise DjangoValidationError("Rating must be an integer between 1 and 5.")

        if not (1 <= rating <= 5):
            raise DjangoValidationError("Rating must be between 1 and 5 stars.")

        # Validate dimensional ratings if provided
        dimensional = {}
        for field in ('communication_rating', 'workmanship_rating', 'pricing_transparency_rating'):
            val = data.get(field)
            if val is not None and str(val).strip() != '':
                try:
                    int_val = int(val)
                    if not (1 <= int_val <= 5):
                        raise DjangoValidationError(f"{field.replace('_', ' ').capitalize()} must be between 1 and 5.")
                    dimensional[field] = int_val
                except (ValueError, TypeError):
                    raise DjangoValidationError(f"{field.replace('_', ' ').capitalize()} must be an integer between 1 and 5.")

        # Validate comment
        comment = (data.get('comment') or '').strip()
        if len(comment) < 5:
            raise DjangoValidationError("Review comment must be at least 5 characters long.")

        title = (data.get('title') or '').strip()

        with transaction.atomic():
            # Lock booking to prevent race conditions
            locked_booking = WorkshopBooking.objects.select_for_update().get(id=booking.id)
            if hasattr(locked_booking, 'review') or WorkshopReview.objects.filter(booking=locked_booking).exists():
                raise DjangoValidationError("A review has already been submitted for this booking.")

            workshop = locked_booking.workshop
            actual_work_order = locked_booking.work_order

            try:
                review = WorkshopReview.objects.create(
                    workshop=workshop,
                    booking=locked_booking,
                    work_order=actual_work_order,
                    buyer=buyer,
                    rating=rating,
                    title=title,
                    comment=comment,
                    status=ReviewStatusChoices.APPROVED,
                    is_verified_service=True,
                    **dimensional,
                )
            except IntegrityError:
                raise DjangoValidationError("A review has already been submitted for this booking.")

            # Record audit entry
            audit = record_audit_entry(
                event_type="workshop.review.created",
                action="workshop:review.create",
                resource_type="WorkshopReview",
                resource_id=str(review.id),
                actor_id=buyer.id,
                operating_org_id=workshop.organisation_id,
                metadata={
                    "review_id": str(review.id),
                    "workshop_id": str(workshop.id),
                    "workshop_name": workshop.business_name,
                    "booking_id": str(locked_booking.id),
                    "booking_number": locked_booking.booking_number,
                    "work_order_id": str(actual_work_order.id),
                    "work_order_number": actual_work_order.work_order_number,
                    "rating": rating,
                    "buyer_id": str(buyer.id),
                },
            )

            # Send in-app notification to workshop owner/admin
            try:
                org_owner = workshop.organisation.created_by if workshop.organisation else None
                if org_owner and audit:
                    create_notification(
                        recipient=org_owner,
                        audit_entry=audit,
                        title=f"New Customer Review for {workshop.display_name}",
                        message=f"{buyer.full_name or buyer.email} left a {rating}★ review for service on {locked_booking.vehicle_make} {locked_booking.vehicle_model}.",
                        link="/platform?tab=workshop_landing",
                        resource_type="WorkshopReview",
                        resource_id=str(review.id),
                        event_type="workshop.review.created",
                    )
            except Exception as e:
                logger.warning("Failed to dispatch workshop review notification: %s", e)

        return review

    @classmethod
    def reply_to_review(cls, review: WorkshopReview, user: User, reply_text: str) -> WorkshopReview:
        """
        Allows authorized workshop staff or organisation members to post a public response.
        """
        from apps.workshops.permissions import is_platform_admin_or_staff
        from apps.organisations.models import OrganisationMembership
        workshop = review.workshop
        is_org_member = False
        if workshop.organisation_id:
            is_org_member = OrganisationMembership.objects.filter(
                organisation_id=workshop.organisation_id,
                user=user,
                is_active=True,
            ).exists()
        if not is_org_member and workshop.organisation and workshop.organisation.created_by_id == user.id:
            is_org_member = True

        if not (is_org_member or is_platform_admin_or_staff(user)):
            raise PermissionDenied("You do not have permission to reply on behalf of this workshop.")

        text = (reply_text or '').strip()
        if len(text) < 2:
            raise DjangoValidationError("Reply message cannot be empty.")

        with transaction.atomic():
            locked_review = WorkshopReview.objects.select_for_update().get(id=review.id)
            if locked_review.workshop_reply:
                raise DjangoValidationError("A reply has already been posted for this review.")

            locked_review.workshop_reply = text
            locked_review.workshop_reply_at = timezone.now()
            locked_review.workshop_replied_by = user
            locked_review.save(update_fields=['workshop_reply', 'workshop_reply_at', 'workshop_replied_by', 'updated_at'])
            review = locked_review

            audit = record_audit_entry(
                event_type="workshop.review.replied",
                action="workshop:review.reply",
                resource_type="WorkshopReview",
                resource_id=str(review.id),
                actor_id=user.id,
                operating_org_id=workshop.organisation_id,
                metadata={
                    "review_id": str(review.id),
                    "workshop_id": str(workshop.id),
                    "reply_preview": text[:100],
                },
            )

            # Notify the customer
            try:
                if review.buyer and audit:
                    create_notification(
                        recipient=review.buyer,
                        audit_entry=audit,
                        title=f"{workshop.display_name} replied to your review",
                        message=f"{workshop.display_name} has posted an official response to your service review.",
                        link="/platform?tab=workshops",
                        resource_type="WorkshopReview",
                        resource_id=str(review.id),
                        event_type="workshop.review.replied",
                    )
            except Exception as e:
                logger.warning("Failed to dispatch review reply notification: %s", e)

        return review

    @classmethod
    def moderate_review(cls, review: WorkshopReview, user: User, status: str, reason: str = "") -> WorkshopReview:
        """
        Allows platform staff/admin to moderate review status (APPROVED, REJECTED, FLAGGED).
        """
        from apps.workshops.permissions import is_platform_admin_or_staff
        if not is_platform_admin_or_staff(user):
            raise PermissionDenied("Only authorized platform administrators and staff can moderate reviews.")

        target_status = status.strip().upper()
        if target_status not in ReviewStatusChoices.values:
            raise DjangoValidationError(f"Invalid moderation status '{target_status}'. Must be one of {ReviewStatusChoices.values}.")

        with transaction.atomic():
            review = WorkshopReview.objects.select_for_update().get(id=review.id)
            previous_status = review.status
            review.status = target_status
            review.save(update_fields=['status', 'updated_at'])

            record_audit_entry(
                event_type="workshop.review.moderated",
                action="workshop:review.moderate",
                resource_type="WorkshopReview",
                resource_id=str(review.id),
                actor_id=user.id,
                metadata={
                    "review_id": str(review.id),
                    "workshop_id": str(review.workshop_id),
                    "previous_status": previous_status,
                    "new_status": target_status,
                    "reason": reason,
                },
            )

        return review

    @classmethod
    def get_workshop_reputation_summary(cls, workshop: WorkshopProfile) -> dict:
        """
        Computes average rating, count, star distribution, and sub-ratings for approved reviews.
        """
        approved_qs = workshop.reviews.filter(status=ReviewStatusChoices.APPROVED)
        total_reviews = approved_qs.count()

        if total_reviews == 0:
            return {
                "average_rating": 0.0,
                "total_reviews": 0,
                "verified_reviews_count": 0,
                "distribution": {"5": 0, "4": 0, "3": 0, "2": 0, "1": 0},
                "sub_ratings": {
                    "communication": 0.0,
                    "workmanship": 0.0,
                    "pricing_transparency": 0.0,
                },
            }

        agg = approved_qs.aggregate(
            avg_rating=models.Avg('rating'),
            avg_comm=models.Avg('communication_rating'),
            avg_work=models.Avg('workmanship_rating'),
            avg_price=models.Avg('pricing_transparency_rating'),
        )

        avg_rating = round(float(agg['avg_rating'] or 0.0), 2)
        avg_comm = round(float(agg['avg_comm'] or 0.0), 1) if agg['avg_comm'] is not None else None
        avg_work = round(float(agg['avg_work'] or 0.0), 1) if agg['avg_work'] is not None else None
        avg_price = round(float(agg['avg_price'] or 0.0), 1) if agg['avg_price'] is not None else None

        distribution = {
            "5": approved_qs.filter(rating=5).count(),
            "4": approved_qs.filter(rating=4).count(),
            "3": approved_qs.filter(rating=3).count(),
            "2": approved_qs.filter(rating=2).count(),
            "1": approved_qs.filter(rating=1).count(),
        }

        sub_ratings = {}
        if avg_comm is not None:
            sub_ratings["communication"] = avg_comm
        if avg_work is not None:
            sub_ratings["workmanship"] = avg_work
        if avg_price is not None:
            sub_ratings["pricing_transparency"] = avg_price

        return {
            "average_rating": avg_rating,
            "total_reviews": total_reviews,
            "verified_reviews_count": approved_qs.filter(is_verified_service=True).count(),
            "distribution": distribution,
            "sub_ratings": sub_ratings,
        }


