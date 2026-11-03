import logging
from decimal import Decimal
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError as DjangoValidationError, PermissionDenied
from django.utils import timezone

from apps.garage.models import GarageVehicle, VehicleServiceRecord, RecordSourceChoices
from apps.identity.models import User
from apps.workshops.models import WorkOrder, WorkOrderStatusChoices
from platform_core.audit.writer import record_audit_entry

logger = logging.getLogger(__name__)


class VehicleServiceHistoryService:
    """
    Business logic and lifecycle operations for Vehicle Service History records.
    Manages both Platform-Verified records (generated from completed Work Orders)
    and Buyer-Entered historical records (external/historical repairs).
    """

    @classmethod
    def create_verified_record_for_work_order(
        cls,
        work_order: WorkOrder,
        actor: User | None = None,
    ) -> VehicleServiceRecord:
        """
        Generates a Platform-Verified VehicleServiceRecord upon successful Work Order completion.
        Atomic and idempotent: returns existing record if already created for this Work Order.
        Strictly validates relationships:
        - Work Order must be in COMPLETED status.
        - Work Order must reference a registered GarageVehicle.
        - Work Order buyer must match the vehicle owner.
        - Work Order must reference a valid WorkshopProfile.
        """
        # Validate completion status
        if work_order.status != WorkOrderStatusChoices.COMPLETED:
            raise DjangoValidationError("Cannot generate verified service history for an uncompleted Work Order.")

        # Validate vehicle association
        vehicle = work_order.vehicle
        if not vehicle:
            raise DjangoValidationError("Work Order does not reference a registered garage vehicle.")

        # Validate ownership consistency
        if work_order.buyer_id != vehicle.user_id:
            raise DjangoValidationError("Work Order buyer does not match the registered vehicle owner.")

        # Validate workshop presence
        workshop = work_order.workshop
        if not workshop:
            raise DjangoValidationError("Work Order does not reference a workshop profile.")

        # Idempotency check: if record already exists, return it cleanly
        existing = VehicleServiceRecord.objects.filter(work_order=work_order).first()
        if existing:
            return existing

        # Determine primary service title
        first_task = work_order.tasks.order_by('order_index').first()
        if first_task and first_task.description:
            service_title = first_task.description[:200]
        else:
            service_title = f"Workshop Repair #{work_order.work_order_number}"

        # Compile task descriptions into a readable service summary
        tasks = list(work_order.tasks.order_by('order_index'))
        if tasks:
            task_descriptions = [t.description for t in tasks if t.description]
            description = "; ".join(task_descriptions)
        else:
            description = f"Completed service order #{work_order.work_order_number} at {workshop.display_name}."

        # Service date from completed_at timestamp
        service_date = work_order.completed_at.date() if work_order.completed_at else timezone.now().date()

        # Odometer and units
        odometer_reading = work_order.current_odometer
        odometer_unit = work_order.odometer_unit or vehicle.odometer_unit or 'mi'

        # Financials from quotation and approved change orders
        quotation = work_order.quotation
        total_cost = work_order.authorized_total_amount if hasattr(work_order, 'authorized_total_amount') else (quotation.total_amount if quotation else None)
        currency = quotation.currency.upper() if quotation and quotation.currency else (workshop.currency.upper() if workshop.currency else 'GBP')

        # Document approved change orders in service description
        approved_cos = list(work_order.change_orders.filter(status='APPROVED')) if hasattr(work_order, 'change_orders') else []
        if approved_cos:
            co_summaries = [f"{co.change_order_number}: {co.reason}" for co in approved_cos]
            description += f" [Approved change orders: {'; '.join(co_summaries)}]"

        try:
            with transaction.atomic():
                record = VehicleServiceRecord.objects.create(
                    vehicle=vehicle,
                    work_order=work_order,
                    workshop=workshop,
                    service_centre_name=workshop.display_name,
                    service_title=service_title,
                    service_type='SERVICE',
                    description=description,
                    service_date=service_date,
                    odometer_reading=odometer_reading,
                    odometer_unit=odometer_unit,
                    total_cost=total_cost,
                    currency=currency,
                    record_source=RecordSourceChoices.PLATFORM_VERIFIED,
                    is_verified=True,
                    created_by=actor or work_order.buyer,
                )

                # Safely update vehicle odometer only from platform-verified orders when greater.
                # Handles current_odometer=None safely without TypeError.
                # Initializes current_odometer when None or updates when greater, strictly when units match.
                # Unit mismatches never cause silent conversion or overwrite vehicle current odometer.
                units_match = (
                    not vehicle.odometer_unit
                    or (odometer_unit and vehicle.odometer_unit.lower() == odometer_unit.lower())
                )
                if odometer_reading is not None and units_match:
                    if vehicle.current_odometer is None or vehicle.current_odometer == 0 or odometer_reading > vehicle.current_odometer:
                        vehicle.current_odometer = odometer_reading
                        update_fields = ['current_odometer', 'updated_at']
                        if not vehicle.odometer_unit and odometer_unit:
                            vehicle.odometer_unit = odometer_unit
                            update_fields.append('odometer_unit')
                        vehicle.save(update_fields=update_fields)

        except IntegrityError:
            # Handle potential concurrent creation race condition
            return VehicleServiceRecord.objects.get(work_order=work_order)

        # Audit logging
        audit_meta = {
            "vehicle_id": str(vehicle.id),
            "work_order_number": work_order.work_order_number,
            "workshop_id": str(workshop.id),
            "total_cost": str(total_cost) if total_cost is not None else None,
            "odometer_reading": odometer_reading,
            "odometer_unit": odometer_unit,
            "vehicle_odometer_unit": getattr(vehicle, 'odometer_unit', None),
            "units_matched": units_match,
        }
        if not units_match:
            audit_meta["odometer_unit_mismatch"] = True
            audit_meta["unit_mismatch_warning"] = (
                f"Vehicle odometer not updated: vehicle is in '{vehicle.odometer_unit}', "
                f"service recorded in '{odometer_unit}'."
            )

        record_audit_entry(
            event_type="garage.service_record.verified_created",
            action="garage:service_record.create_verified",
            resource_type="VehicleServiceRecord",
            resource_id=str(record.id),
            actor_id=actor.id if actor else None,
            metadata=audit_meta,
        )
        return record

    @classmethod
    def create_buyer_record(
        cls,
        vehicle: GarageVehicle,
        data: dict,
        buyer: User,
    ) -> VehicleServiceRecord:
        """
        Creates a manual, unverified historical service record submitted by the vehicle owner.
        Enforces vehicle ownership and strictly forces record_source=BUYER_ENTERED,
        is_verified=False, and work_order=None regardless of input payload.
        Does NOT update vehicle current_odometer (unverified telemetry).
        """
        # Strict vehicle ownership check
        if vehicle.user_id != buyer.id:
            raise DjangoValidationError("You can only add service records for vehicles in your personal garage.")

        if vehicle.is_archived:
            raise DjangoValidationError("Cannot add service records to an archived vehicle.")

        service_date = data.get('service_date')
        if service_date and service_date > timezone.now().date():
            raise DjangoValidationError("Service date cannot be in the future.")

        odometer_reading = data.get('odometer_reading')
        if odometer_reading is not None and odometer_reading < 0:
            raise DjangoValidationError("Odometer reading cannot be negative.")

        total_cost = data.get('total_cost')
        if total_cost is not None and Decimal(str(total_cost)) < Decimal('0.00'):
            raise DjangoValidationError("Total cost cannot be negative.")

        from platform_core.regional import derive_regional_context_for_vehicle_and_buyer
        reg_ctx = derive_regional_context_for_vehicle_and_buyer(vehicle=vehicle, buyer=buyer)

        odometer_unit = data.get('odometer_unit') or getattr(vehicle, 'odometer_unit', None) or reg_ctx.get('odometer_unit')
        if not odometer_unit:
            raise DjangoValidationError("Odometer unit could not be reliably determined. Please specify an explicit unit ('km' or 'mi').")

        currency = data.get('currency')
        if currency and str(currency).strip():
            currency = str(currency).strip().upper()
        else:
            currency = reg_ctx.get('currency')
            if not currency:
                raise DjangoValidationError("Currency could not be reliably determined from your regional profile. Please provide an explicit currency code (e.g. INR, GBP).")

        record = VehicleServiceRecord(
            vehicle=vehicle,
            work_order=None,        # Strictly forbidden for buyer records
            workshop=None,          # Strictly forbidden for buyer records
            service_centre_name=data.get('service_centre_name', '').strip(),
            service_title=data['service_title'].strip(),
            service_type=data.get('service_type', 'SERVICE').strip().upper() or 'SERVICE',
            description=data.get('description', '').strip(),
            service_date=service_date,
            odometer_reading=odometer_reading,
            odometer_unit=odometer_unit,
            total_cost=total_cost,
            currency=currency,
            record_source=RecordSourceChoices.BUYER_ENTERED,
            is_verified=False,      # Always unverified
            created_by=buyer,
            notes=data.get('notes', '').strip(),
        )
        record.full_clean()
        record.save()

        # Audit logging
        record_audit_entry(
            event_type="garage.service_record.buyer_created",
            action="garage:service_record.create_buyer",
            resource_type="VehicleServiceRecord",
            resource_id=str(record.id),
            actor_id=buyer.id,
            metadata={
                "vehicle_id": str(vehicle.id),
                "service_title": record.service_title,
                "service_date": str(record.service_date),
            },
        )
        return record

    @classmethod
    def update_buyer_record(
        cls,
        record: VehicleServiceRecord,
        data: dict,
        buyer: User,
    ) -> VehicleServiceRecord:
        """
        Updates an existing buyer-entered service record.
        Rejects modifications to platform-verified records with PermissionDenied.
        Restricts updates to permitted user-editable fields.
        """
        # Block edits to verified records
        if record.is_verified or record.record_source != RecordSourceChoices.BUYER_ENTERED:
            raise PermissionDenied("Platform-verified service records cannot be edited.")

        # Enforce vehicle ownership
        if record.vehicle.user_id != buyer.id:
            raise PermissionDenied("You can only modify service records for vehicles you own.")

        update_fields = ['updated_at']

        if 'service_title' in data:
            record.service_title = data['service_title'].strip()
            update_fields.append('service_title')

        if 'service_date' in data:
            if data['service_date'] > timezone.now().date():
                raise DjangoValidationError("Service date cannot be in the future.")
            record.service_date = data['service_date']
            update_fields.append('service_date')

        if 'service_type' in data:
            record.service_type = data['service_type'].strip().upper() or 'SERVICE'
            update_fields.append('service_type')

        if 'service_centre_name' in data:
            record.service_centre_name = data['service_centre_name'].strip()
            update_fields.append('service_centre_name')

        if 'odometer_reading' in data:
            val = data['odometer_reading']
            if val is not None and val < 0:
                raise DjangoValidationError("Odometer reading cannot be negative.")
            record.odometer_reading = val
            update_fields.append('odometer_reading')

        if 'odometer_unit' in data:
            record.odometer_unit = data['odometer_unit'] or record.vehicle.odometer_unit or 'mi'
            update_fields.append('odometer_unit')

        if 'total_cost' in data:
            val = data['total_cost']
            if val is not None and Decimal(str(val)) < Decimal('0.00'):
                raise DjangoValidationError("Total cost cannot be negative.")
            record.total_cost = val
            update_fields.append('total_cost')

        if 'currency' in data:
            record.currency = (data['currency'] or 'GBP').upper()
            update_fields.append('currency')

        if 'description' in data:
            record.description = data['description'].strip()
            update_fields.append('description')

        if 'notes' in data:
            record.notes = data['notes'].strip()
            update_fields.append('notes')

        record.full_clean()
        record.save(update_fields=update_fields)

        record_audit_entry(
            event_type="garage.service_record.buyer_updated",
            action="garage:service_record.update_buyer",
            resource_type="VehicleServiceRecord",
            resource_id=str(record.id),
            actor_id=buyer.id,
            metadata={
                "vehicle_id": str(record.vehicle_id),
                "service_title": record.service_title,
            },
        )
        return record

    @classmethod
    def delete_buyer_record(
        cls,
        record: VehicleServiceRecord,
        buyer: User,
    ) -> None:
        """
        Deletes a buyer-entered service record.
        Rejects deletions of platform-verified records with PermissionDenied.
        """
        if record.is_verified or record.record_source != RecordSourceChoices.BUYER_ENTERED:
            raise PermissionDenied("Platform-verified service records cannot be deleted.")

        if record.vehicle.user_id != buyer.id:
            raise PermissionDenied("You can only delete service records for vehicles you own.")

        record_id = str(record.id)
        vehicle_id = str(record.vehicle_id)
        title = record.service_title

        record.delete()

        record_audit_entry(
            event_type="garage.service_record.buyer_deleted",
            action="garage:service_record.delete_buyer",
            resource_type="VehicleServiceRecord",
            resource_id=record_id,
            actor_id=buyer.id,
            metadata={
                "vehicle_id": vehicle_id,
                "service_title": title,
            },
        )

