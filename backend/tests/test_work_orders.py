from datetime import date, timedelta
from decimal import Decimal

import pytest
from rest_framework import status
from rest_framework.test import APIClient
from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError

from apps.identity.models import User, RoleChoices
from apps.organisations.models import Organisation, OrganisationMembership, OrganisationRoleChoices, OrganisationTypeChoices
from apps.garage.models import GarageVehicle
from apps.notifications.models import Notification
from apps.workshops.models import (
    WorkshopProfile,
    WorkshopOperatingHours,
    WorkshopServiceCategory,
    WorkshopService,
    WorkshopBooking,
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
)
from apps.workshops.services import QuotationService, WorkOrderService
from tests.quotation_states import make_quotation, advance_quotation


@pytest.fixture
def owner_user(db):
    user = User.objects.create_user(
        email='owner@apexmotors.com',
        password='Password123!',
        first_name='Oliver',
        last_name='Owner',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.WORKSHOP)
    return user


@pytest.fixture
def tech_user(db):
    user = User.objects.create_user(
        email='tech@apexmotors.com',
        password='Password123!',
        first_name='Tom',
        last_name='Tech',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.WORKSHOP)
    return user


@pytest.fixture
def other_user(db):
    user = User.objects.create_user(
        email='other@external.com',
        password='Password123!',
        first_name='Eve',
        last_name='External',
        is_email_verified=True,
    )
    return user


@pytest.fixture
def buyer_user(db):
    user = User.objects.create_user(
        email='buyer@driverxtra.com',
        password='Password123!',
        first_name='Charlie',
        last_name='Customer',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.fixture
def workshop_org(db, owner_user, tech_user):
    org = Organisation.objects.create(
        name="Apex Motors Workshop",
        type=OrganisationTypeChoices.WORKSHOP,
        created_by=owner_user,
    )
    org.add_member(owner_user, role=OrganisationRoleChoices.OWNER)
    org.add_member(tech_user, role=OrganisationRoleChoices.TECHNICIAN)
    return org


@pytest.fixture
def workshop_profile(db, workshop_org):
    return WorkshopProfile.objects.create(
        organisation=workshop_org,
        business_name="Apex Motors",
        slug="apex-motors",
        city="London",
        bay_capacity=3,
        is_tax_registered=True,
        can_collect_tax=True,
        default_tax_rate_percent=Decimal('20.00'),
        is_accepting_bookings=True,
        is_verified=True,
    )


@pytest.fixture
def garage_vehicle(db, buyer_user):
    return GarageVehicle.objects.create(
        user=buyer_user,
        make="BMW",
        model="330e M Sport",
        year=2021,
        registration_plate="DX21 BMW",
        vin="WBA330E2021XYZ999",
        current_odometer=32000,
        odometer_unit="mi",
    )


@pytest.fixture
def booking_with_quotation(db, workshop_profile, buyer_user, garage_vehicle, owner_user):
    booking = WorkshopBooking.objects.create(
        workshop=workshop_profile,
        buyer=buyer_user,
        vehicle=garage_vehicle,
        vehicle_make=garage_vehicle.make,
        vehicle_model=garage_vehicle.model,
        vehicle_year=garage_vehicle.year,
        vehicle_registration_plate=garage_vehicle.registration_plate,
        vehicle_vin=garage_vehicle.vin,
        current_odometer=garage_vehicle.current_odometer,
        odometer_unit=garage_vehicle.odometer_unit,
        preferred_date=date.today() + timedelta(days=2),
        preferred_time_slot="Morning (09:00 - 12:00)",
        status=BookingStatusChoices.ACCEPTED,
    )

    # Create quotation with labour and parts
    quote = WorkshopQuotation.objects.create(
        booking=booking,
        version=1,
        status=QuotationStatusChoices.DRAFT,
        tax_rate_percent=Decimal('20.00'),
        valid_until=date.today() + timedelta(days=14),
    )
    QuotationLineItem.objects.create(
        quotation=quote,
        item_type=LineItemTypeChoices.LABOUR,
        description="Major Service Inspection & Diagnostic",
        quantity=Decimal('2.00'),
        unit_price=Decimal('60.00'),
        line_total=Decimal('120.00'),
    )
    QuotationLineItem.objects.create(
        quotation=quote,
        item_type=LineItemTypeChoices.PART,
        description="OEM Synthetic Oil & Filter Kit",
        part_number="OEM-OIL-FIL-99",
        quantity=Decimal('1.00'),
        unit_price=Decimal('45.00'),
        line_total=Decimal('45.00'),
    )
    quote.recalculate_totals(commit=True)
    # Issue only after scope is final: issued quotations are write-once (AUT-01)
    advance_quotation(quote, QuotationStatusChoices.ISSUED)
    return booking, quote


@pytest.mark.django_db
class TestWorkOrderCreationAndQuotationIntegration:
    """Verifies that Work Orders are created only upon quotation acceptance."""

    def test_no_work_order_before_quotation_acceptance(self, booking_with_quotation):
        booking, quote = booking_with_quotation
        assert not hasattr(booking, 'work_order') or booking.work_order is None
        assert WorkOrder.objects.filter(booking=booking).count() == 0

    def test_work_order_created_automatically_on_quotation_acceptance(self, booking_with_quotation, buyer_user):
        booking, quote = booking_with_quotation

        # Buyer accepts quotation
        accepted_quote = QuotationService.accept_quotation(quotation=quote, buyer=buyer_user)
        assert accepted_quote.status == QuotationStatusChoices.ACCEPTED

        # Work order must now exist
        work_order = WorkOrder.objects.get(booking=booking)
        assert work_order.quotation == accepted_quote
        assert work_order.workshop == booking.workshop
        assert work_order.buyer == buyer_user
        assert work_order.vehicle_registration_plate == "DX21 BMW"
        assert work_order.status == WorkOrderStatusChoices.ASSIGNED
        assert work_order.work_order_number.startswith("WO-")

        # Tasks must be pre-populated from quotation labour line items
        tasks = work_order.tasks.all()
        assert tasks.count() == 1
        assert tasks[0].description == "Major Service Inspection & Diagnostic"
        assert tasks[0].status == WorkOrderTaskStatusChoices.PENDING

        # Quotation parts are planned parts on the quotation and must not be marked as prematurely consumed
        planned_parts = work_order.quotation.line_items.filter(item_type=LineItemTypeChoices.PART)
        assert planned_parts.count() == 1
        assert planned_parts[0].description == "OEM Synthetic Oil & Filter Kit"
        assert planned_parts[0].quantity == Decimal('1.00')

        # Floor parts consumption starts at 0 until technician logs usage during repair
        assert work_order.parts_used.count() == 0

    def test_no_duplicate_work_orders(self, booking_with_quotation, buyer_user):
        booking, quote = booking_with_quotation
        QuotationService.accept_quotation(quotation=quote, buyer=buyer_user)

        # Attempt to call create_work_order_for_booking a second time
        wo1 = WorkOrder.objects.get(booking=booking)
        wo2 = WorkOrderService.create_work_order_for_booking(booking=booking, quotation=quote, actor=buyer_user)

        assert wo1.id == wo2.id
        assert WorkOrder.objects.filter(booking=booking).count() == 1

    def test_rejects_quotation_from_different_booking(self, booking_with_quotation, buyer_user, workshop_profile, garage_vehicle):
        booking1, quote1 = booking_with_quotation
        accepted_quote1 = QuotationService.accept_quotation(quotation=quote1, buyer=buyer_user)
        quote1.refresh_from_db()

        # Create a second booking
        booking2 = WorkshopBooking.objects.create(
            workshop=workshop_profile,
            buyer=buyer_user,
            vehicle=garage_vehicle,
            preferred_date=date.today() + timedelta(days=5),
            preferred_time_slot="Morning",
            status=BookingStatusChoices.ACCEPTED,
        )

        # Attempting to create work order for booking2 using quote1 from booking1 must be rejected
        with pytest.raises(DjangoValidationError, match="does not belong to the specified booking"):
            WorkOrderService.create_work_order_for_booking(booking=booking2, quotation=quote1, actor=buyer_user)

    def test_labour_duration_conversion_expected_examples(self, workshop_profile, buyer_user, garage_vehicle):
        """
        Verifies exact required labour-duration conversions:
        - 1 hour = 60 minutes
        - 1.5 hours = 90 minutes
        - 2.25 hours = 135 minutes
        """
        booking = WorkshopBooking.objects.create(
            workshop=workshop_profile,
            buyer=buyer_user,
            vehicle=garage_vehicle,
            preferred_date=date.today() + timedelta(days=3),
            status=BookingStatusChoices.ACCEPTED,
        )

        quote = WorkshopQuotation.objects.create(
            booking=booking,
            status=QuotationStatusChoices.DRAFT,
            tax_rate_percent=Decimal('20.00'),
        )

        # 1 hour = 60 minutes
        QuotationLineItem.objects.create(
            quotation=quote,
            item_type=LineItemTypeChoices.LABOUR,
            description="Standard 1 Hour Inspection",
            quantity=Decimal('1.00'),
            unit_price=Decimal('50.00'),
            line_total=Decimal('50.00'),
        )

        # 1.5 hours = 90 minutes
        QuotationLineItem.objects.create(
            quotation=quote,
            item_type=LineItemTypeChoices.LABOUR,
            description="Brake Pad and Rotor Replacement",
            quantity=Decimal('1.50'),
            unit_price=Decimal('80.00'),
            line_total=Decimal('120.00'),
        )

        # 2.25 hours = 135 minutes
        QuotationLineItem.objects.create(
            quotation=quote,
            item_type=LineItemTypeChoices.DIAGNOSTIC,
            description="Electrical System Diagnostic",
            quantity=Decimal('2.25'),
            unit_price=Decimal('90.00'),
            line_total=Decimal('202.50'),
        )

        quote.recalculate_totals(commit=True)
        # Issue only after scope is final: issued quotations are write-once (AUT-01)
        advance_quotation(quote, QuotationStatusChoices.ISSUED)
        accepted_quote = QuotationService.accept_quotation(quotation=quote, buyer=buyer_user)
        work_order = WorkOrder.objects.get(booking=booking)

        tasks = list(work_order.tasks.order_by('order_index'))
        assert len(tasks) == 3

        # 1.0 hour -> 60 minutes
        assert tasks[0].description == "Standard 1 Hour Inspection"
        assert tasks[0].estimated_labour_minutes == 60

        # 1.5 hours -> 90 minutes
        assert tasks[1].description == "Brake Pad and Rotor Replacement"
        assert tasks[1].estimated_labour_minutes == 90

        # 2.25 hours -> 135 minutes
        assert tasks[2].description == "Electrical System Diagnostic"
        assert tasks[2].estimated_labour_minutes == 135

    def test_labour_duration_whole_and_fractional_hours(self, workshop_profile, buyer_user, garage_vehicle):
        """
        Tests whole and fractional hour conversions:
        - 0.25 hours = 15 minutes
        - 0.50 hours = 30 minutes
        - 0.75 hours = 45 minutes
        - 2.00 hours = 120 minutes
        - 3.00 hours = 180 minutes
        """
        booking = WorkshopBooking.objects.create(
            workshop=workshop_profile,
            buyer=buyer_user,
            vehicle=garage_vehicle,
            preferred_date=date.today() + timedelta(days=2),
            status=BookingStatusChoices.ACCEPTED,
        )
        quote = WorkshopQuotation.objects.create(
            booking=booking,
            status=QuotationStatusChoices.DRAFT,
            tax_rate_percent=Decimal('20.00'),
        )

        items_data = [
            (Decimal('0.25'), 15, "Quarter hour check"),
            (Decimal('0.50'), 30, "Half hour adjustment"),
            (Decimal('0.75'), 45, "45-minute service"),
            (Decimal('2.00'), 120, "Two hour overhaul"),
            (Decimal('3.00'), 180, "Three hour major service"),
        ]
        for qty, _, desc in items_data:
            QuotationLineItem.objects.create(
                quotation=quote,
                item_type=LineItemTypeChoices.LABOUR,
                description=desc,
                quantity=qty,
                unit_price=Decimal('60.00'),
                line_total=qty * Decimal('60.00'),
            )
        quote.recalculate_totals(commit=True)
        # Issue only after scope is final: issued quotations are write-once (AUT-01)
        advance_quotation(quote, QuotationStatusChoices.ISSUED)
        QuotationService.accept_quotation(quotation=quote, buyer=buyer_user)

        work_order = WorkOrder.objects.get(booking=booking)
        tasks = list(work_order.tasks.order_by('order_index'))
        assert len(tasks) == len(items_data)

        for task, (qty, expected_mins, desc) in zip(tasks, items_data):
            assert task.description == desc
            assert task.estimated_labour_minutes == expected_mins

    def test_labour_duration_rounding_behaviour(self, workshop_profile, buyer_user, garage_vehicle):
        """
        Tests exact rounding with ROUND_HALF_UP on (quantity * Decimal('60')).quantize(Decimal('1'), rounding=ROUND_HALF_UP):
        - 0.33 hours * 60 = 19.80 -> 20 minutes (rounds up)
        - 0.17 hours * 60 = 10.20 -> 10 minutes (rounds down)
        - 0.42 hours * 60 = 25.20 -> 25 minutes (rounds down)
        - 0.58 hours * 60 = 34.80 -> 35 minutes (rounds up)
        - 1.33 hours * 60 = 79.80 -> 80 minutes (rounds up)
        - 1.67 hours * 60 = 100.20 -> 100 minutes (rounds down)
        """
        booking = WorkshopBooking.objects.create(
            workshop=workshop_profile,
            buyer=buyer_user,
            vehicle=garage_vehicle,
            preferred_date=date.today() + timedelta(days=4),
            status=BookingStatusChoices.ACCEPTED,
        )
        quote = WorkshopQuotation.objects.create(
            booking=booking,
            status=QuotationStatusChoices.DRAFT,
            tax_rate_percent=Decimal('20.00'),
        )

        rounding_data = [
            (Decimal('0.33'), 20, "0.33 hours -> 19.8 -> 20 min"),
            (Decimal('0.17'), 10, "0.17 hours -> 10.2 -> 10 min"),
            (Decimal('0.42'), 25, "0.42 hours -> 25.2 -> 25 min"),
            (Decimal('0.58'), 35, "0.58 hours -> 34.8 -> 35 min"),
            (Decimal('1.33'), 80, "1.33 hours -> 79.8 -> 80 min"),
            (Decimal('1.67'), 100, "1.67 hours -> 100.2 -> 100 min"),
        ]
        for qty, _, desc in rounding_data:
            QuotationLineItem.objects.create(
                quotation=quote,
                item_type=LineItemTypeChoices.LABOUR,
                description=desc,
                quantity=qty,
                unit_price=Decimal('100.00'),
                line_total=qty * Decimal('100.00'),
            )
        quote.recalculate_totals(commit=True)
        # Issue only after scope is final: issued quotations are write-once (AUT-01)
        advance_quotation(quote, QuotationStatusChoices.ISSUED)
        QuotationService.accept_quotation(quotation=quote, buyer=buyer_user)

        work_order = WorkOrder.objects.get(booking=booking)
        tasks = list(work_order.tasks.order_by('order_index'))
        assert len(tasks) == len(rounding_data)

        for task, (qty, expected_mins, desc) in zip(tasks, rounding_data):
            assert task.description == desc
            assert task.estimated_labour_minutes == expected_mins

    def test_direct_formula_multiplication_before_rounding(self):
        """
        Direct test of: (quantity * Decimal('60')).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        verifying that multiplication precedes rounding, avoiding premature integer truncation.
        """
        from decimal import Decimal, ROUND_HALF_UP

        def calc(quantity: Decimal) -> int:
            return int((quantity * Decimal('60')).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

        # Expected conversions
        assert calc(Decimal('1')) == 60
        assert calc(Decimal('1.00')) == 60
        assert calc(Decimal('1.5')) == 90
        assert calc(Decimal('1.50')) == 90
        assert calc(Decimal('2.25')) == 135

        # Whole hours
        assert calc(Decimal('2')) == 120
        assert calc(Decimal('3')) == 180
        assert calc(Decimal('4')) == 240

        # Fractional hours
        assert calc(Decimal('0.25')) == 15
        assert calc(Decimal('0.5')) == 30
        assert calc(Decimal('0.75')) == 45
        assert calc(Decimal('0.1')) == 6

        # Rounding edge cases (including half-up)
        # 0.125 * 60 = 7.50 -> 8
        assert calc(Decimal('0.125')) == 8
        # 0.124 * 60 = 7.44 -> 7
        assert calc(Decimal('0.124')) == 7
        # 0.33 * 60 = 19.80 -> 20
        assert calc(Decimal('0.33')) == 20
        # 0.17 * 60 = 10.20 -> 10
        assert calc(Decimal('0.17')) == 10

@pytest.mark.django_db
class TestWorkOrderTechnicianAssignmentAndPermissions:
    """Verifies technician assignment validation and cross-workshop access boundaries."""

    def test_technician_assignment_success(self, booking_with_quotation, buyer_user, tech_user, owner_user):
        booking, quote = booking_with_quotation
        QuotationService.accept_quotation(quotation=quote, buyer=buyer_user)
        work_order = WorkOrder.objects.get(booking=booking)

        updated = WorkOrderService.assign_technician(work_order=work_order, technician=tech_user, actor=owner_user)
        assert updated.lead_technician == tech_user
        assert updated.assigned_by == owner_user
        assert updated.assigned_at is not None

    def test_technician_assignment_rejects_external_user(self, booking_with_quotation, buyer_user, other_user, owner_user):
        booking, quote = booking_with_quotation
        QuotationService.accept_quotation(quotation=quote, buyer=buyer_user)
        work_order = WorkOrder.objects.get(booking=booking)

        with pytest.raises(DjangoValidationError) as excinfo:
            WorkOrderService.assign_technician(work_order=work_order, technician=other_user, actor=owner_user)
        assert "must be an active member of this workshop" in str(excinfo.value)

    def test_cross_workshop_access_isolated(self, booking_with_quotation, buyer_user, other_user):
        booking, quote = booking_with_quotation
        QuotationService.accept_quotation(quotation=quote, buyer=buyer_user)
        work_order = WorkOrder.objects.get(booking=booking)

        # Other user has a different workshop organisation
        other_org = Organisation.objects.create(name="Other Workshop", type=OrganisationTypeChoices.WORKSHOP, created_by=other_user)
        other_org.add_member(other_user, role=OrganisationRoleChoices.OWNER)
        WorkshopProfile.objects.create(organisation=other_org, business_name="Other Workshop", slug="other-ws")

        client = APIClient()
        client.force_authenticate(user=other_user)

        # Trying to access work_order of apex motors
        resp = client.get(f"/api/v1/workshops/manage/work-orders/{work_order.id}/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestWorkOrderStatusTransitions:
    """Verifies strict status transition logic and timestamps."""

    def test_valid_lifecycle_status_transitions(self, booking_with_quotation, buyer_user, owner_user):
        booking, quote = booking_with_quotation
        QuotationService.accept_quotation(quotation=quote, buyer=buyer_user)
        work_order = WorkOrder.objects.get(booking=booking)

        # 1. ASSIGNED -> IN_PROGRESS
        wo = WorkOrderService.update_status(work_order, WorkOrderStatusChoices.IN_PROGRESS, actor=owner_user)
        assert wo.status == WorkOrderStatusChoices.IN_PROGRESS
        assert wo.started_at is not None

        # 2. IN_PROGRESS -> AWAITING_PARTS
        wo = WorkOrderService.update_status(wo, WorkOrderStatusChoices.AWAITING_PARTS, actor=owner_user)
        assert wo.status == WorkOrderStatusChoices.AWAITING_PARTS

        # 3. AWAITING_PARTS -> IN_PROGRESS
        wo = WorkOrderService.update_status(wo, WorkOrderStatusChoices.IN_PROGRESS, actor=owner_user)
        assert wo.status == WorkOrderStatusChoices.IN_PROGRESS

        # 4. IN_PROGRESS -> QUALITY_CHECK
        wo = WorkOrderService.update_status(wo, WorkOrderStatusChoices.QUALITY_CHECK, actor=owner_user, quality_notes="Initial checks")
        assert wo.status == WorkOrderStatusChoices.QUALITY_CHECK
        assert wo.quality_inspected_at is not None

        # 5. QUALITY_CHECK -> IN_PROGRESS (inspection failure rework)
        wo = WorkOrderService.update_status(wo, WorkOrderStatusChoices.IN_PROGRESS, actor=owner_user, internal_notes="Brake pads need alignment")
        assert wo.status == WorkOrderStatusChoices.IN_PROGRESS

        # 6. Re-send to QUALITY_CHECK
        wo = WorkOrderService.update_status(wo, WorkOrderStatusChoices.QUALITY_CHECK, actor=owner_user, quality_notes="Re-inspected, all clear")
        assert wo.status == WorkOrderStatusChoices.QUALITY_CHECK

        # 7. QUALITY_CHECK -> COMPLETED
        wo = WorkOrderService.update_status(wo, WorkOrderStatusChoices.COMPLETED, actor=owner_user, quality_notes="Passed all road tests")
        assert wo.status == WorkOrderStatusChoices.COMPLETED
        assert wo.completed_at is not None

    def test_cannot_jump_directly_from_in_progress_to_completed(self, booking_with_quotation, buyer_user, owner_user):
        booking, quote = booking_with_quotation
        QuotationService.accept_quotation(quotation=quote, buyer=buyer_user)
        work_order = WorkOrder.objects.get(booking=booking)

        WorkOrderService.update_status(work_order, WorkOrderStatusChoices.IN_PROGRESS, actor=owner_user)

        # Attempt to complete without quality inspection
        with pytest.raises(DjangoValidationError) as excinfo:
            WorkOrderService.update_status(work_order, WorkOrderStatusChoices.COMPLETED, actor=owner_user)
        assert "Cannot transition Work Order" in str(excinfo.value)

    def test_cancellation_from_assigned_state(self, booking_with_quotation, buyer_user, owner_user):
        booking, quote = booking_with_quotation
        QuotationService.accept_quotation(quotation=quote, buyer=buyer_user)
        work_order = WorkOrder.objects.get(booking=booking)

        wo = WorkOrderService.update_status(work_order, WorkOrderStatusChoices.CANCELLED, actor=owner_user, cancellation_reason="Customer vehicle written off")
        assert wo.status == WorkOrderStatusChoices.CANCELLED
        assert "written off" in wo.cancellation_reason


@pytest.mark.django_db
class TestWorkOrderTasksAndPartsUsage:
    """Verifies task management and spare parts decimal calculations."""

    def test_add_and_update_tasks(self, booking_with_quotation, buyer_user, tech_user, owner_user):
        booking, quote = booking_with_quotation
        QuotationService.accept_quotation(quotation=quote, buyer=buyer_user)
        work_order = WorkOrder.objects.get(booking=booking)

        task = WorkOrderService.add_task(
            work_order=work_order,
            description="Replace front brake pads and flush fluid",
            assigned_technician=tech_user,
            estimated_labour_minutes=90,
            actor=owner_user,
        )
        assert task.assigned_technician == tech_user
        assert task.estimated_labour_minutes == 90
        assert task.status == WorkOrderTaskStatusChoices.PENDING

        # Technician starts task and logs labour
        updated_task = WorkOrderService.update_task(
            task=task,
            status=WorkOrderTaskStatusChoices.COMPLETED,
            actual_labour_minutes=85,
            notes="Completed without incident. Fluid bleed test OK.",
            actor=tech_user,
        )
        assert updated_task.status == WorkOrderTaskStatusChoices.COMPLETED
        assert updated_task.actual_labour_minutes == 85
        assert updated_task.completed_at is not None

        # Verify property on work_order
        work_order.refresh_from_db()
        assert work_order.total_actual_labour_minutes == 85

    def test_parts_usage_decimal_calculation(self, booking_with_quotation, buyer_user, owner_user):
        booking, quote = booking_with_quotation
        QuotationService.accept_quotation(quotation=quote, buyer=buyer_user)
        work_order = WorkOrder.objects.get(booking=booking)

        # Clear pre-populated parts for clear calculation
        work_order.parts_used.all().delete()

        part1 = WorkOrderService.record_part_usage(
            work_order=work_order,
            part_name="Castrol Edge 5W-30 (1L)",
            quantity=Decimal('4.50'),
            unit_cost=Decimal('12.50'),
            actor=owner_user,
        )
        # 4.5 * 12.50 = 56.25
        assert part1.total_cost == Decimal('56.25')

        part2 = WorkOrderService.record_part_usage(
            work_order=work_order,
            part_name="Sump Washer Gasket",
            quantity=Decimal('2.00'),
            unit_cost=Decimal('1.85'),
            actor=owner_user,
        )
        # 2.0 * 1.85 = 3.70
        assert part2.total_cost == Decimal('3.70')

        work_order.refresh_from_db()
        assert work_order.total_parts_cost == Decimal('59.95')

    def test_invalid_part_quantity_and_cost_rejected(self, booking_with_quotation, buyer_user, owner_user):
        booking, quote = booking_with_quotation
        QuotationService.accept_quotation(quotation=quote, buyer=buyer_user)
        work_order = WorkOrder.objects.get(booking=booking)

        with pytest.raises(DjangoValidationError):
            WorkOrderService.record_part_usage(
                work_order=work_order,
                part_name="Invalid Quantity",
                quantity=Decimal('-1.00'),
                unit_cost=Decimal('10.00'),
                actor=owner_user,
            )

        with pytest.raises(DjangoValidationError):
            WorkOrderService.record_part_usage(
                work_order=work_order,
                part_name="Invalid Cost",
                quantity=Decimal('1.00'),
                unit_cost=Decimal('-5.00'),
                actor=owner_user,
            )


@pytest.mark.django_db
class TestWorkOrderAPIEndpoints:
    """End-to-end REST API verification for work orders management."""

    def test_list_and_retrieve_work_orders(self, booking_with_quotation, buyer_user, owner_user):
        booking, quote = booking_with_quotation
        QuotationService.accept_quotation(quotation=quote, buyer=buyer_user)
        work_order = WorkOrder.objects.get(booking=booking)

        client = APIClient()
        client.force_authenticate(user=owner_user)

        # List
        resp = client.get("/api/v1/workshops/manage/work-orders/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data['count'] == 1
        assert resp.data['results'][0]['work_order_number'] == work_order.work_order_number

        # Detail
        detail_resp = client.get(f"/api/v1/workshops/manage/work-orders/{work_order.id}/")
        assert detail_resp.status_code == status.HTTP_200_OK
        assert detail_resp.data['vehicle_registration_plate'] == "DX21 BMW"
        assert len(detail_resp.data['tasks']) == 1
        assert len(detail_resp.data['planned_parts']) == 1
        assert len(detail_resp.data['parts_used']) == 0

    def test_assign_technician_api(self, booking_with_quotation, buyer_user, tech_user, owner_user):
        booking, quote = booking_with_quotation
        QuotationService.accept_quotation(quotation=quote, buyer=buyer_user)
        work_order = WorkOrder.objects.get(booking=booking)

        client = APIClient()
        client.force_authenticate(user=owner_user)

        resp = client.post(
            f"/api/v1/workshops/manage/work-orders/{work_order.id}/assign-technician/",
            data={'technician_id': str(tech_user.id)},
            format='json',
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data['status'] == 'success'
        assert str(resp.data['work_order']['lead_technician']) == str(tech_user.id)

    def test_status_update_api(self, booking_with_quotation, buyer_user, owner_user):
        booking, quote = booking_with_quotation
        QuotationService.accept_quotation(quotation=quote, buyer=buyer_user)
        work_order = WorkOrder.objects.get(booking=booking)

        client = APIClient()
        client.force_authenticate(user=owner_user)

        resp = client.post(
            f"/api/v1/workshops/manage/work-orders/{work_order.id}/status/",
            data={'status': 'IN_PROGRESS', 'internal_notes': 'Vehicle pulled onto Bay 2'},
            format='json',
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data['work_order']['status'] == 'IN_PROGRESS'

    def test_status_update_completion_returns_odometer_unit_mismatch_warning(
        self, booking_with_quotation, buyer_user, owner_user
    ):
        """Transitioning to COMPLETED returns structured warning if vehicle odometer unit mismatches work order."""
        booking, quote = booking_with_quotation
        QuotationService.accept_quotation(quotation=quote, buyer=buyer_user)
        work_order = WorkOrder.objects.get(booking=booking)

        # Vehicle is in km, work order is in mi
        vehicle = work_order.vehicle
        vehicle.odometer_unit = 'km'
        vehicle.current_odometer = 50000
        vehicle.save(update_fields=['odometer_unit', 'current_odometer'])

        work_order.odometer_unit = 'mi'
        work_order.current_odometer = 52000
        work_order.status = WorkOrderStatusChoices.QUALITY_CHECK
        work_order.save(update_fields=['odometer_unit', 'current_odometer', 'status'])

        client = APIClient()
        client.force_authenticate(user=owner_user)

        resp = client.post(
            f"/api/v1/workshops/manage/work-orders/{work_order.id}/status/",
            data={'status': 'COMPLETED'},
            format='json',
        )
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data['work_order']['status'] == 'COMPLETED'
        assert data['work_order']['odometer_unit_mismatch'] is True
        assert data['work_order']['vehicle_odometer_unit'] == 'km'

        # Check top-level warnings
        assert 'warnings' in data
        assert len(data['warnings']) == 1
        warn = data['warnings'][0]
        assert warn['code'] == 'ODOMETER_UNIT_MISMATCH'
        assert warn['vehicle_odometer_unit'] == 'km'
        assert warn['work_order_odometer_unit'] == 'mi'
        assert 'unit mismatch' in warn['message'].lower()

        # Verify vehicle odometer was NOT updated
        vehicle.refresh_from_db()
        assert vehicle.current_odometer == 50000
        assert vehicle.odometer_unit == 'km'

    def test_technicians_list_api(self, workshop_profile, owner_user, tech_user):
        client = APIClient()
        client.force_authenticate(user=owner_user)

        resp = client.get("/api/v1/workshops/manage/technicians/")
        assert resp.status_code == status.HTTP_200_OK
        results = resp.data['results']
        emails = [r['email'] for r in results]
        assert 'owner@apexmotors.com' in emails
        assert 'tech@apexmotors.com' in emails

    def test_buyer_inspects_work_order_and_privacy_boundaries(self, booking_with_quotation, buyer_user, tech_user, owner_user):
        booking, quote = booking_with_quotation
        QuotationService.accept_quotation(quotation=quote, buyer=buyer_user)
        work_order = WorkOrder.objects.get(booking=booking)

        # Set lead tech and internal operational notes
        work_order.lead_technician = tech_user
        work_order.internal_notes = "CONFIDENTIAL: Customer reported slight vibration, tech should check CV joints."
        work_order.quality_notes = "INTERNAL QC: Torque wrench calibration pending next week."
        work_order.save(update_fields=['lead_technician', 'internal_notes', 'quality_notes'])

        client = APIClient()
        client.force_authenticate(user=buyer_user)

        resp = client.get(f"/api/v1/workshops/bookings/my/{booking.id}/work-order/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data['work_order_number'] == work_order.work_order_number

        # Verify privacy: internal workshop notes and private technician emails must NOT be exposed
        assert 'internal_notes' not in resp.data
        assert 'quality_notes' not in resp.data
        assert 'lead_technician_email' not in resp.data
        assert 'assigned_by' not in resp.data
        assert 'quality_inspected_by' not in resp.data
        assert resp.data['lead_technician_name'] == (tech_user.full_name or tech_user.email)

    def test_task_and_part_deletion_audit_logging(self, booking_with_quotation, buyer_user, owner_user):
        booking, quote = booking_with_quotation
        QuotationService.accept_quotation(quotation=quote, buyer=buyer_user)
        work_order = WorkOrder.objects.get(booking=booking)

        # Add a task and record a part
        task = WorkOrderService.add_task(work_order=work_order, description="Temporary inspection task", actor=owner_user)
        part = WorkOrderService.record_part_usage(work_order=work_order, part_name="Sample Gasket", quantity=Decimal('1.00'), unit_cost=Decimal('5.50'), actor=owner_user)

        client = APIClient()
        client.force_authenticate(user=owner_user)

        # Delete task via API
        del_task_resp = client.delete(f"/api/v1/workshops/manage/work-orders/{work_order.id}/tasks/{task.id}/")
        assert del_task_resp.status_code == status.HTTP_204_NO_CONTENT
        assert not WorkOrderTask.objects.filter(id=task.id).exists()

        # Delete part via API
        del_part_resp = client.delete(f"/api/v1/workshops/manage/work-orders/{work_order.id}/parts/{part.id}/")
        assert del_part_resp.status_code == status.HTTP_204_NO_CONTENT
        assert not WorkOrderPartUsage.objects.filter(id=part.id).exists()



@pytest.mark.django_db
class TestWorkOrderAssignTechnicianContract:
    """
    G22 regression: the frontend client must call the backend assign-technician route.
    Previously the client posted to .../assign/, which has no backend route.
    """

    def test_frontend_assign_technician_call_resolves_to_backend_view(self):
        import re
        import uuid
        from pathlib import Path
        from django.urls import resolve
        from apps.workshops.views import WorkOrderAssignTechnicianView

        client_ts = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "api" / "client.ts"
        if not client_ts.exists():
            pytest.skip(f"Frontend client not present at {client_ts}")
        source = client_ts.read_text(encoding="utf-8")

        start = source.find("async assignTechnician(")
        assert start != -1, "api.workshops.manageWorkOrders.assignTechnician not found in client.ts"
        end = source.find("\n      async ", start + 1)
        block = source[start:end if end != -1 else None]

        path_match = re.search(r"`(/workshops/manage/work-orders/\$\{id\}/[^`]*)`", block)
        assert path_match, "assignTechnician path template not found"
        path = path_match.group(1).replace("${id}", str(uuid.uuid4()))

        match = resolve(f"/api/v1{path}")
        assert match.func.view_class is WorkOrderAssignTechnicianView
        assert 'method: "POST"' in block
        assert "technician_id" in block
        # Backend responds { status, message, work_order }; the client must return the work order.
        assert ".work_order" in block

    def test_assign_technician_api_rejects_non_member(self, booking_with_quotation, buyer_user, other_user, owner_user):
        booking, quote = booking_with_quotation
        QuotationService.accept_quotation(quotation=quote, buyer=buyer_user)
        work_order = WorkOrder.objects.get(booking=booking)
        before = work_order.lead_technician_id

        client = APIClient()
        client.force_authenticate(user=owner_user)
        resp = client.post(
            f"/api/v1/workshops/manage/work-orders/{work_order.id}/assign-technician/",
            data={'technician_id': str(other_user.id)},
            format='json',
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert resp.data['status'] == 'error'
        work_order.refresh_from_db()
        assert work_order.lead_technician_id == before

    def test_assign_technician_api_denies_other_workshop(self, booking_with_quotation, buyer_user, tech_user, other_user):
        booking, quote = booking_with_quotation
        QuotationService.accept_quotation(quotation=quote, buyer=buyer_user)
        work_order = WorkOrder.objects.get(booking=booking)
        before = work_order.lead_technician_id

        other_org = Organisation.objects.create(name="Other Workshop", type=OrganisationTypeChoices.WORKSHOP, created_by=other_user)
        other_org.add_member(other_user, role=OrganisationRoleChoices.OWNER)
        WorkshopProfile.objects.create(organisation=other_org, business_name="Other Workshop", slug="other-ws")

        client = APIClient()
        client.force_authenticate(user=other_user)
        resp = client.post(
            f"/api/v1/workshops/manage/work-orders/{work_order.id}/assign-technician/",
            data={'technician_id': str(tech_user.id)},
            format='json',
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        work_order.refresh_from_db()
        assert work_order.lead_technician_id == before

@pytest.mark.django_db
class TestIssuedQuotationIsWriteOnce:
    """
    G23 / DX-GC-06 AUT-01: a quotation is write-once after it is sent (ISSUED).
    New scope requires a new quotation version; lifecycle and deposit state may still change.
    """

    def test_issued_quotation_content_fields_cannot_change(self, booking_with_quotation):
        _, quote = booking_with_quotation
        for field, value in (
            ('total_amount', quote.total_amount + Decimal('10.00')),
            ('discount_amount', Decimal('5.00')),
            ('terms_and_conditions', 'Changed after sending'),
            ('valid_until', date.today() + timedelta(days=60)),
        ):
            fresh = WorkshopQuotation.objects.get(pk=quote.pk)
            setattr(fresh, field, value)
            with pytest.raises(DjangoValidationError) as exc:
                fresh.save()
            assert "is issued and immutable" in str(exc.value)
            assert field in str(exc.value)
        quote.refresh_from_db()
        assert quote.terms_and_conditions == ''

    def test_issued_quotation_line_items_cannot_be_added_changed_or_deleted(self, booking_with_quotation):
        _, quote = booking_with_quotation
        before_total = quote.total_amount
        with pytest.raises(DjangoValidationError):
            QuotationLineItem.objects.create(
                quotation=quote,
                item_type=LineItemTypeChoices.LABOUR,
                description="Extra work added after sending",
                quantity=Decimal('1.00'),
                unit_price=Decimal('99.00'),
            )
        item = quote.line_items.first()
        item.unit_price = Decimal('1.00')
        with pytest.raises(DjangoValidationError):
            item.save()
        with pytest.raises(DjangoValidationError):
            quote.line_items.first().delete()
        quote.refresh_from_db()
        assert quote.line_items.count() == 2
        assert quote.total_amount == before_total

    def test_issued_quotation_totals_cannot_be_recalculated(self, booking_with_quotation):
        _, quote = booking_with_quotation
        with pytest.raises(DjangoValidationError):
            quote.recalculate_totals(commit=True)

    def test_issued_quotation_cannot_be_deleted(self, booking_with_quotation):
        _, quote = booking_with_quotation
        with pytest.raises(DjangoValidationError):
            quote.delete()
        assert WorkshopQuotation.objects.filter(pk=quote.pk).exists()

    def test_stale_in_memory_parent_cannot_bypass_line_item_lock(self, booking_with_quotation):
        _, quote = booking_with_quotation
        stale = WorkshopQuotation.objects.get(pk=quote.pk)
        stale.status = QuotationStatusChoices.DRAFT  # in memory only
        with pytest.raises(DjangoValidationError):
            QuotationLineItem.objects.create(
                quotation=stale,
                item_type=LineItemTypeChoices.LABOUR,
                description="Bypass attempt",
                quantity=Decimal('1.00'),
                unit_price=Decimal('10.00'),
            )

    def test_deposit_payment_state_can_still_change_on_issued_quotation(self, booking_with_quotation, owner_user):
        booking, _ = booking_with_quotation
        # Deposit-bearing quotation built through the real service path
        quote = QuotationService.create_or_revise_quotation(
            booking=booking,
            data={
                'requires_deposit': True,
                'deposit_percentage': '20.00',
                'line_items': [{
                    'item_type': LineItemTypeChoices.LABOUR,
                    'description': 'Clutch replacement',
                    'quantity': '1.00',
                    'unit_price': '300.00',
                }],
            },
            actor=owner_user,
        )
        quote = QuotationService.issue_quotation(quote, actor=owner_user)
        assert quote.deposit_status == DepositStatusChoices.PENDING
        total_before = quote.total_amount

        quote.deposit_status = DepositStatusChoices.PROCESSING
        quote.deposit_order_id = 'order_test_123'
        quote.save(update_fields=['deposit_status', 'deposit_order_id', 'updated_at'])

        quote.refresh_from_db()
        assert quote.deposit_status == DepositStatusChoices.PROCESSING
        assert quote.deposit_order_id == 'order_test_123'
        assert quote.total_amount == total_before

    def test_revision_creates_new_version_and_preserves_sent_version(self, booking_with_quotation, owner_user):
        booking, v1 = booking_with_quotation
        v1_total = v1.total_amount
        v1_items = sorted(v1.line_items.values_list('description', flat=True))

        v2 = QuotationService.create_or_revise_quotation(
            booking=booking,
            data={'line_items': [{
                'item_type': LineItemTypeChoices.LABOUR,
                'description': 'Revised scope: brake inspection',
                'quantity': '1.00',
                'unit_price': '80.00',
            }]},
            actor=owner_user,
        )
        assert v2.pk != v1.pk
        assert v2.version == v1.version + 1
        assert v2.status == QuotationStatusChoices.DRAFT

        QuotationService.issue_quotation(v2, actor=owner_user)
        v1.refresh_from_db()
        assert v1.status == QuotationStatusChoices.SUPERSEDED
        assert v1.total_amount == v1_total
        assert sorted(v1.line_items.values_list('description', flat=True)) == v1_items

        # A superseded version stays frozen as well
        v1.total_amount = Decimal('1.00')
        with pytest.raises(DjangoValidationError):
            v1.save()

    def test_rejected_quotation_content_is_frozen(self, booking_with_quotation, buyer_user):
        _, quote = booking_with_quotation
        QuotationService.reject_quotation(quote, buyer=buyer_user, reason='Too expensive')
        quote.refresh_from_db()
        quote.discount_amount = Decimal('20.00')
        with pytest.raises(DjangoValidationError):
            quote.save()

def _move_quotation_to(quote, target, buyer_user, owner_user):
    """Drive an ISSUED quotation into `target` through its legitimate path."""
    if target == QuotationStatusChoices.ACCEPTED:
        QuotationService.accept_quotation(quote, buyer=buyer_user)
    elif target == QuotationStatusChoices.REJECTED:
        QuotationService.reject_quotation(quote, buyer=buyer_user, reason='Declined')
    elif target == QuotationStatusChoices.SUPERSEDED:
        v2 = QuotationService.create_or_revise_quotation(
            booking=quote.booking,
            data={'line_items': [{'item_type': LineItemTypeChoices.LABOUR, 'description': 'Revised', 'quantity': '1.00', 'unit_price': '10.00'}]},
            actor=owner_user,
        )
        QuotationService.issue_quotation(v2, actor=owner_user)
    quote.refresh_from_db()
    assert quote.status == target
    return quote


# EXPIRED has no owning service workflow, so it is unreachable (see test_expired_is_unreachable).
LOCKED_STATES = [
    QuotationStatusChoices.ISSUED,
    QuotationStatusChoices.ACCEPTED,
    QuotationStatusChoices.REJECTED,
    QuotationStatusChoices.SUPERSEDED,
]


@pytest.mark.django_db
class TestQuotationWriteOnceReviewCorrections:
    """
    G23 / DX-GC-06 AUT-01 corrections after independent review:
    no reopening to DRAFT, workshop_notes frozen, bulk ORM paths guarded, admin guarded, row locking.
    """

    # --- 1. Reopening a locked quotation -------------------------------------------------

    @pytest.mark.parametrize('state', LOCKED_STATES)
    def test_locked_quotation_cannot_return_to_draft_via_save(self, state, booking_with_quotation, buyer_user, owner_user):
        _, quote = booking_with_quotation
        quote = _move_quotation_to(quote, state, buyer_user, owner_user)
        quote.status = QuotationStatusChoices.DRAFT
        with pytest.raises(DjangoValidationError):
            quote.save()
        assert WorkshopQuotation.objects.get(pk=quote.pk).status == state

    @pytest.mark.parametrize('state', LOCKED_STATES)
    def test_locked_quotation_cannot_return_to_draft_via_queryset_update(self, state, booking_with_quotation, buyer_user, owner_user):
        _, quote = booking_with_quotation
        quote = _move_quotation_to(quote, state, buyer_user, owner_user)
        with pytest.raises(DjangoValidationError):
            WorkshopQuotation.objects.filter(pk=quote.pk).update(status=QuotationStatusChoices.DRAFT)
        assert WorkshopQuotation.objects.get(pk=quote.pk).status == state

    @pytest.mark.parametrize('state', LOCKED_STATES)
    def test_locked_quotation_cannot_return_to_draft_via_bulk_update(self, state, booking_with_quotation, buyer_user, owner_user):
        _, quote = booking_with_quotation
        quote = _move_quotation_to(quote, state, buyer_user, owner_user)
        quote.status = QuotationStatusChoices.DRAFT
        with pytest.raises(DjangoValidationError):
            WorkshopQuotation.objects.bulk_update([quote], ['status'])
        assert WorkshopQuotation.objects.get(pk=quote.pk).status == state

    def test_terminal_states_cannot_move_to_other_states(self, booking_with_quotation, buyer_user, owner_user):
        _, quote = booking_with_quotation
        quote = _move_quotation_to(quote, QuotationStatusChoices.REJECTED, buyer_user, owner_user)
        for target in (QuotationStatusChoices.ISSUED, QuotationStatusChoices.ACCEPTED):
            with pytest.raises(DjangoValidationError):
                WorkshopQuotation.objects.filter(pk=quote.pk).update(status=target)
        assert WorkshopQuotation.objects.get(pk=quote.pk).status == QuotationStatusChoices.REJECTED

    # --- 2. Customer-visible content -----------------------------------------------------

    def test_workshop_notes_frozen_after_issue(self, booking_with_quotation):
        _, quote = booking_with_quotation
        quote.workshop_notes = 'Changed after sending'
        with pytest.raises(DjangoValidationError) as exc:
            quote.save()
        assert 'workshop_notes' in str(exc.value)
        with pytest.raises(DjangoValidationError):
            WorkshopQuotation.objects.filter(pk=quote.pk).update(workshop_notes='Changed in bulk')
        assert WorkshopQuotation.objects.get(pk=quote.pk).workshop_notes == ''

    def test_recorded_rejection_reason_cannot_be_rewritten(self, booking_with_quotation, buyer_user, owner_user):
        _, quote = booking_with_quotation
        quote = _move_quotation_to(quote, QuotationStatusChoices.REJECTED, buyer_user, owner_user)
        quote.customer_rejection_reason = 'Rewritten'
        with pytest.raises(DjangoValidationError):
            quote.save()
        assert WorkshopQuotation.objects.get(pk=quote.pk).customer_rejection_reason == 'Declined'

    # --- 3. Bulk ORM bypasses ------------------------------------------------------------

    def test_queryset_update_of_content_rejected(self, booking_with_quotation):
        from django.db.models import F
        booking, quote = booking_with_quotation
        total = quote.total_amount
        with pytest.raises(DjangoValidationError):
            WorkshopQuotation.objects.filter(pk=quote.pk).update(total_amount=Decimal('1.00'))
        with pytest.raises(DjangoValidationError):
            WorkshopQuotation.objects.filter(pk=quote.pk).update(total_amount=F('total_amount') + 1)
        with pytest.raises(DjangoValidationError):
            booking.quotations.all().update(terms_and_conditions='Bulk terms')
        assert WorkshopQuotation.objects.get(pk=quote.pk).total_amount == total

    def test_queryset_update_of_payment_state_allowed_but_not_status(self, booking_with_quotation):
        _, quote = booking_with_quotation
        assert WorkshopQuotation.objects.filter(pk=quote.pk).update(deposit_status=DepositStatusChoices.PROCESSING) == 1
        # Superseding is owned by QuotationService.issue_quotation, never a direct update
        with pytest.raises(DjangoValidationError):
            WorkshopQuotation.objects.filter(pk=quote.pk).update(status=QuotationStatusChoices.SUPERSEDED)
        assert WorkshopQuotation.objects.get(pk=quote.pk).status == QuotationStatusChoices.ISSUED

    def test_bulk_update_of_content_rejected_but_payment_state_allowed(self, booking_with_quotation):
        _, quote = booking_with_quotation
        quote.discount_amount = Decimal('5.00')
        with pytest.raises(DjangoValidationError):
            WorkshopQuotation.objects.bulk_update([quote], ['discount_amount'])
        quote.refresh_from_db()
        quote.deposit_order_id = 'order_bulk_1'
        WorkshopQuotation.objects.bulk_update([quote], ['deposit_order_id'])
        assert WorkshopQuotation.objects.get(pk=quote.pk).deposit_order_id == 'order_bulk_1'

    def test_bulk_create_upsert_rejected(self, booking_with_quotation):
        _, quote = booking_with_quotation
        quote.total_amount = Decimal('1.00')
        with pytest.raises(DjangoValidationError):
            WorkshopQuotation.objects.bulk_create(
                [quote], update_conflicts=True, unique_fields=['id'], update_fields=['total_amount']
            )
        assert WorkshopQuotation.objects.get(pk=quote.pk).total_amount != Decimal('1.00')

    def test_queryset_delete_of_issued_quotation_rejected(self, booking_with_quotation):
        booking, quote = booking_with_quotation
        with pytest.raises(DjangoValidationError):
            WorkshopQuotation.objects.filter(pk=quote.pk).delete()
        with pytest.raises(DjangoValidationError):
            booking.quotations.all().delete()
        assert WorkshopQuotation.objects.filter(pk=quote.pk).exists()
        assert quote.line_items.count() == 2

    def test_draft_quotation_bulk_operations_still_allowed(self, booking_with_quotation, owner_user):
        booking, _ = booking_with_quotation
        draft = QuotationService.create_or_revise_quotation(
            booking=booking,
            data={'line_items': [{'item_type': LineItemTypeChoices.LABOUR, 'description': 'Draft work', 'quantity': '1.00', 'unit_price': '20.00'}]},
            actor=owner_user,
        )
        assert WorkshopQuotation.objects.filter(pk=draft.pk).update(workshop_notes='Draft note') == 1
        assert QuotationLineItem.objects.filter(quotation=draft).update(description='Draft work v2') == 1
        # Revising an existing draft (draft locked before the booking) replaces its items in place
        again = QuotationService.create_or_revise_quotation(
            booking=booking,
            data={'line_items': [{'item_type': LineItemTypeChoices.PART, 'description': 'Draft part', 'quantity': '2.00', 'unit_price': '5.00'}]},
            actor=owner_user,
        )
        assert again.pk == draft.pk
        assert list(again.line_items.values_list('description', flat=True)) == ['Draft part']
        WorkshopQuotation.objects.filter(pk=draft.pk).delete()
        assert not WorkshopQuotation.objects.filter(pk=draft.pk).exists()

    # --- 4. Line-item bulk operations ----------------------------------------------------

    def test_line_item_bulk_operations_on_issued_quotation_rejected(self, booking_with_quotation):
        _, quote = booking_with_quotation
        items = list(quote.line_items.all())
        with pytest.raises(DjangoValidationError):
            QuotationLineItem.objects.filter(quotation=quote).update(unit_price=Decimal('1.00'))
        with pytest.raises(DjangoValidationError):
            quote.line_items.all().delete()
        items[0].unit_price = Decimal('1.00')
        with pytest.raises(DjangoValidationError):
            QuotationLineItem.objects.bulk_update(items, ['unit_price'])
        with pytest.raises(DjangoValidationError):
            QuotationLineItem.objects.bulk_create([QuotationLineItem(
                quotation=quote, item_type=LineItemTypeChoices.LABOUR, description='Bulk extra',
                quantity=Decimal('1.00'), unit_price=Decimal('9.00'), line_total=Decimal('9.00'),
            )])
        assert sorted(quote.line_items.values_list('unit_price', flat=True)) == [Decimal('45.00'), Decimal('60.00')]
        assert quote.line_items.count() == 2

    def test_line_item_cannot_be_moved_out_of_issued_quotation(self, booking_with_quotation, owner_user):
        booking, quote = booking_with_quotation
        draft = QuotationService.create_or_revise_quotation(
            booking=booking,
            data={'line_items': [{'item_type': LineItemTypeChoices.LABOUR, 'description': 'Draft', 'quantity': '1.00', 'unit_price': '1.00'}]},
            actor=owner_user,
        )
        item = quote.line_items.first()
        item.quotation = draft
        with pytest.raises(DjangoValidationError):
            item.save()
        with pytest.raises(DjangoValidationError):
            QuotationLineItem.objects.filter(pk=item.pk).update(quotation=draft)
        assert QuotationLineItem.objects.get(pk=item.pk).quotation_id == quote.pk

    # --- 5. Admin ------------------------------------------------------------------------

    def test_admin_bulk_delete_does_not_delete_issued_quotation(self, booking_with_quotation):
        from django.test import Client
        from django.urls import reverse
        _, quote = booking_with_quotation
        admin_user = User.objects.create_superuser(email='admin-g23@driverxtra.com', password='Password123!')
        client = Client()
        client.force_login(admin_user)
        resp = client.post(
            reverse('admin:workshops_workshopquotation_changelist'),
            {'action': 'delete_selected', '_selected_action': [str(quote.pk)], 'post': 'yes'},
        )
        assert resp.status_code in (200, 302, 403)
        assert WorkshopQuotation.objects.filter(pk=quote.pk).exists()
        assert quote.line_items.count() == 2

    def test_admin_permissions_lock_issued_quotation_and_inline_items(self, booking_with_quotation, owner_user):
        from django.contrib import admin as django_admin
        from django.test import RequestFactory
        from apps.workshops.admin import QuotationLineItemInline, QuotationLineItemAdmin
        booking, quote = booking_with_quotation
        admin_user = User.objects.create_superuser(email='admin-g23b@driverxtra.com', password='Password123!')
        request = RequestFactory().get('/admin/')
        request.user = admin_user

        q_admin = django_admin.site._registry[WorkshopQuotation]
        inline = QuotationLineItemInline(WorkshopQuotation, django_admin.site)
        item_admin = QuotationLineItemAdmin(QuotationLineItem, django_admin.site)
        assert q_admin.has_change_permission(request, quote) is False
        assert q_admin.has_delete_permission(request, quote) is False
        assert inline.has_add_permission(request, quote) is False
        assert inline.has_change_permission(request, quote) is False
        assert inline.has_delete_permission(request, quote) is False
        item = quote.line_items.first()
        assert item_admin.has_change_permission(request, item) is False
        assert item_admin.has_delete_permission(request, item) is False

        draft = QuotationService.create_or_revise_quotation(
            booking=booking,
            data={'line_items': [{'item_type': LineItemTypeChoices.LABOUR, 'description': 'Draft', 'quantity': '1.00', 'unit_price': '1.00'}]},
            actor=owner_user,
        )
        assert q_admin.has_change_permission(request, draft) is True
        assert inline.has_add_permission(request, draft) is True

    # --- 6. Concurrency (structural) -----------------------------------------------------

    def test_writes_lock_the_quotation_row_before_checking(self, booking_with_quotation):
        """
        The status check and the write run under SELECT ... FOR UPDATE on the quotation row.
        In-memory SQLite ignores FOR UPDATE, so this asserts the lock is requested; it does not
        exercise real concurrent transactions (that needs PostgreSQL).
        """
        from unittest import mock
        from django.db.models import QuerySet
        _, quote = booking_with_quotation
        original = QuerySet.select_for_update
        locked_models = []

        def spy(qs, *args, **kwargs):
            locked_models.append(qs.model)
            return original(qs, *args, **kwargs)

        with mock.patch.object(QuerySet, 'select_for_update', spy):
            quote.deposit_order_id = 'order_lock_check'
            quote.save(update_fields=['deposit_order_id', 'updated_at'])
            assert WorkshopQuotation in locked_models
            locked_models.clear()
            with pytest.raises(DjangoValidationError):
                QuotationLineItem.objects.create(
                    quotation=quote, item_type=LineItemTypeChoices.LABOUR, description='x',
                    quantity=Decimal('1.00'), unit_price=Decimal('1.00'),
                )
            assert WorkshopQuotation in locked_models
            locked_models.clear()
            WorkshopQuotation.objects.filter(pk=quote.pk).update(deposit_status=DepositStatusChoices.PROCESSING)
            # Unguarded fields need no lock; guarded ones do
            assert WorkshopQuotation not in locked_models
            with pytest.raises(DjangoValidationError):
                WorkshopQuotation.objects.filter(pk=quote.pk).update(status=QuotationStatusChoices.SUPERSEDED)
            assert WorkshopQuotation in locked_models

def _new_draft(booking, owner_user, description='Draft scope'):
    return QuotationService.create_or_revise_quotation(
        booking=booking,
        data={'line_items': [{'item_type': LineItemTypeChoices.LABOUR, 'description': description, 'quantity': '1.00', 'unit_price': '25.00'}]},
        actor=owner_user,
    )


def _select_for_update_order(callable_):
    """Run callable_ and return the models locked with select_for_update, in call order."""
    from unittest import mock
    from django.db.models import QuerySet
    original = QuerySet.select_for_update
    order = []

    def spy(qs, *args, **kwargs):
        order.append(qs.model.__name__)
        return original(qs, *args, **kwargs)

    with mock.patch.object(QuerySet, 'select_for_update', spy):
        callable_()
    return order


TERMINAL_TARGETS = [
    QuotationStatusChoices.ACCEPTED,
    QuotationStatusChoices.REJECTED,
    QuotationStatusChoices.SUPERSEDED,
    QuotationStatusChoices.EXPIRED,
]


@pytest.mark.django_db
class TestQuotationServiceOwnedTransitions:
    """
    G23 / DX-GC-06 AUT-01 third pass: status changes only through the owning QuotationService
    workflow; lifecycle facts only with their transition; no line-item upserts; one lock order.
    """

    # --- Finding 1: service-bypassing status transitions ---------------------------------

    @pytest.mark.parametrize('target', TERMINAL_TARGETS)
    def test_draft_cannot_jump_to_terminal_state(self, target, booking_with_quotation, owner_user):
        booking, _ = booking_with_quotation
        draft = _new_draft(booking, owner_user)
        draft.status = target
        with pytest.raises(DjangoValidationError):
            draft.save()
        with pytest.raises(DjangoValidationError):
            WorkshopQuotation.objects.filter(pk=draft.pk).update(status=target)
        with pytest.raises(DjangoValidationError):
            WorkshopQuotation.objects.bulk_update([draft], ['status'])
        assert WorkshopQuotation.objects.get(pk=draft.pk).status == QuotationStatusChoices.DRAFT

    def test_draft_cannot_be_issued_outside_issue_service(self, booking_with_quotation, owner_user):
        booking, _ = booking_with_quotation
        draft = _new_draft(booking, owner_user)
        draft.status = QuotationStatusChoices.ISSUED
        with pytest.raises(DjangoValidationError) as exc:
            draft.save()
        assert 'issue_quotation' in str(exc.value)
        with pytest.raises(DjangoValidationError):
            WorkshopQuotation.objects.filter(pk=draft.pk).update(status=QuotationStatusChoices.ISSUED)
        # The owning service still issues it
        issued = QuotationService.issue_quotation(draft, actor=owner_user)
        assert issued.status == QuotationStatusChoices.ISSUED
        assert issued.issued_at is not None

    @pytest.mark.parametrize('target,owner', [
        (QuotationStatusChoices.ACCEPTED, 'accept_quotation'),
        (QuotationStatusChoices.REJECTED, 'reject_quotation'),
    ])
    def test_issued_cannot_be_accepted_or_rejected_outside_service(self, target, owner, booking_with_quotation):
        _, quote = booking_with_quotation
        quote.status = target
        with pytest.raises(DjangoValidationError) as exc:
            quote.save()
        assert owner in str(exc.value)
        with pytest.raises(DjangoValidationError):
            WorkshopQuotation.objects.filter(pk=quote.pk).update(status=target)
        quote.refresh_from_db()
        with pytest.raises(DjangoValidationError):
            quote.status = target
            WorkshopQuotation.objects.bulk_update([quote], ['status'])
        quote.refresh_from_db()
        assert quote.status == QuotationStatusChoices.ISSUED
        assert not WorkOrder.objects.filter(booking=quote.booking).exists()

    def test_expired_is_unreachable_without_an_owning_workflow(self, booking_with_quotation):
        _, quote = booking_with_quotation
        quote.status = QuotationStatusChoices.EXPIRED
        with pytest.raises(DjangoValidationError):
            quote.save()
        with pytest.raises(DjangoValidationError):
            WorkshopQuotation.objects.filter(pk=quote.pk).update(status=QuotationStatusChoices.EXPIRED)
        with pytest.raises(ValueError):
            from apps.workshops.models import _quotation_transition
            with _quotation_transition([quote.pk], QuotationStatusChoices.ISSUED, QuotationStatusChoices.EXPIRED):
                pass

    def test_quotation_cannot_be_created_in_non_draft_state(self, booking_with_quotation):
        booking, _ = booking_with_quotation
        for status_value in (QuotationStatusChoices.ISSUED, QuotationStatusChoices.ACCEPTED, QuotationStatusChoices.REJECTED):
            with pytest.raises(DjangoValidationError):
                WorkshopQuotation.objects.create(booking=booking, version=50, status=status_value)
            with pytest.raises(DjangoValidationError):
                WorkshopQuotation.objects.bulk_create([WorkshopQuotation(booking=booking, version=51, status=status_value)])
        assert booking.quotations.count() == 1

    def test_admin_cannot_set_status_or_lifecycle_fields(self, booking_with_quotation):
        from django.contrib import admin as django_admin
        from django.test import RequestFactory
        admin_user = User.objects.create_superuser(email='admin-g23c@driverxtra.com', password='Password123!')
        request = RequestFactory().get('/admin/')
        request.user = admin_user
        q_admin = django_admin.site._registry[WorkshopQuotation]
        readonly = set(q_admin.get_readonly_fields(request, None))
        assert {'status', 'issued_at', 'accepted_at', 'rejected_at', 'customer_rejection_reason'} <= readonly
        add_form_fields = set(q_admin.get_form(request, None).base_fields)
        assert 'status' not in add_form_fields
        assert not ({'issued_at', 'accepted_at', 'rejected_at', 'customer_rejection_reason'} & add_form_fields)

    # --- Finding 2: lifecycle fields bound to their transitions ---------------------------

    def test_premature_acceptance_timestamp_refused_then_service_records_it(self, booking_with_quotation, buyer_user):
        _, quote = booking_with_quotation
        early = timezone.now() - timedelta(days=3)
        quote.accepted_at = early
        with pytest.raises(DjangoValidationError):
            quote.save()
        with pytest.raises(DjangoValidationError):
            WorkshopQuotation.objects.filter(pk=quote.pk).update(accepted_at=early)
        fresh = WorkshopQuotation.objects.get(pk=quote.pk)
        fresh.accepted_at = early
        with pytest.raises(DjangoValidationError):
            WorkshopQuotation.objects.bulk_update([fresh], ['accepted_at'])
        assert WorkshopQuotation.objects.get(pk=quote.pk).accepted_at is None

        accepted = QuotationService.accept_quotation(WorkshopQuotation.objects.get(pk=quote.pk), buyer=buyer_user)
        assert accepted.status == QuotationStatusChoices.ACCEPTED
        assert accepted.accepted_at is not None and accepted.accepted_at > early

    def test_premature_rejection_fields_refused_then_service_records_them(self, booking_with_quotation, buyer_user):
        _, quote = booking_with_quotation
        quote.rejected_at = timezone.now()
        with pytest.raises(DjangoValidationError):
            quote.save()
        quote.refresh_from_db()
        quote.customer_rejection_reason = 'Pre-filled reason'
        with pytest.raises(DjangoValidationError):
            quote.save()
        with pytest.raises(DjangoValidationError):
            WorkshopQuotation.objects.filter(pk=quote.pk).update(customer_rejection_reason='Pre-filled')
        stored = WorkshopQuotation.objects.get(pk=quote.pk)
        assert stored.rejected_at is None and stored.customer_rejection_reason == ''

        rejected = QuotationService.reject_quotation(stored, buyer=buyer_user, reason='Too expensive')
        assert rejected.status == QuotationStatusChoices.REJECTED
        assert rejected.customer_rejection_reason == 'Too expensive'
        assert rejected.rejected_at is not None

    def test_issue_timestamp_bound_to_issue_transition(self, booking_with_quotation, owner_user):
        booking, quote = booking_with_quotation
        # Issued quotation: issued_at can be neither cleared nor rewritten
        for value in (None, timezone.now() + timedelta(days=1)):
            quote.refresh_from_db()
            quote.issued_at = value
            with pytest.raises(DjangoValidationError):
                quote.save()
        # Draft: issued_at cannot be recorded before the issue transition
        draft = _new_draft(booking, owner_user)
        draft.issued_at = timezone.now()
        with pytest.raises(DjangoValidationError):
            draft.save()
        with pytest.raises(DjangoValidationError):
            WorkshopQuotation.objects.create(booking=booking, version=60, issued_at=timezone.now())
        issued = QuotationService.issue_quotation(WorkshopQuotation.objects.get(pk=draft.pk), actor=owner_user)
        assert issued.issued_at is not None

    def test_lifecycle_fields_of_other_transitions_cannot_ride_along(self, booking_with_quotation, buyer_user):
        """Accepting must not also record rejection facts (each transition owns only its own fields)."""
        _, quote = booking_with_quotation
        quote.status = QuotationStatusChoices.ACCEPTED
        quote.accepted_at = timezone.now()
        quote.customer_rejection_reason = 'smuggled'
        from apps.workshops.models import _quotation_transition
        with _quotation_transition([quote.pk], QuotationStatusChoices.ISSUED, QuotationStatusChoices.ACCEPTED):
            with pytest.raises(DjangoValidationError):
                quote.save()
        assert WorkshopQuotation.objects.get(pk=quote.pk).status == QuotationStatusChoices.ISSUED

    # --- Legitimate workflows ---------------------------------------------------------------

    def test_issue_accept_and_revision_workflows_still_work(self, booking_with_quotation, buyer_user, owner_user):
        booking, v1 = booking_with_quotation
        v2 = _new_draft(booking, owner_user, description='Revision scope')
        v2 = QuotationService.issue_quotation(v2, actor=owner_user)
        v1.refresh_from_db()
        assert v1.status == QuotationStatusChoices.SUPERSEDED
        assert v2.status == QuotationStatusChoices.ISSUED and v2.issued_at is not None
        accepted = QuotationService.accept_quotation(v2, buyer=buyer_user)
        assert accepted.status == QuotationStatusChoices.ACCEPTED and accepted.accepted_at is not None
        assert WorkOrder.objects.filter(booking=booking, quotation=accepted).exists()

    # --- Finding 3: line-item conflict upsert ----------------------------------------------

    def test_line_item_upsert_against_issued_parent_refused(self, booking_with_quotation, owner_user):
        booking, issued = booking_with_quotation
        draft = _new_draft(booking, owner_user)
        existing = issued.line_items.first()
        original_price = existing.unit_price
        incoming = QuotationLineItem(
            id=existing.id,  # conflicts with the issued quotation's line item
            quotation=draft,  # but targets an unlocked draft
            item_type=LineItemTypeChoices.LABOUR,
            description='Upsert takeover',
            quantity=Decimal('1.00'),
            unit_price=Decimal('1.00'),
            line_total=Decimal('1.00'),
        )
        with pytest.raises(DjangoValidationError):
            QuotationLineItem.objects.bulk_create(
                [incoming], update_conflicts=True, unique_fields=['id'],
                update_fields=['quotation', 'unit_price', 'description'],
            )
        existing.refresh_from_db()
        assert existing.quotation_id == issued.pk
        assert existing.unit_price == original_price

    # --- Finding 4: lock ordering -----------------------------------------------------------

    def test_line_item_writes_lock_parent_quotation_before_line_items(self, booking_with_quotation, owner_user):
        booking, _ = booking_with_quotation
        draft = _new_draft(booking, owner_user)
        item = draft.line_items.first()

        def assert_parent_first(order):
            assert 'WorkshopQuotation' in order and 'QuotationLineItem' in order, order
            assert order.index('WorkshopQuotation') < order.index('QuotationLineItem'), order

        assert_parent_first(_select_for_update_order(
            lambda: QuotationLineItem.objects.filter(pk=item.pk).update(description='qs update')))
        item.refresh_from_db()
        item.description = 'instance update'
        assert_parent_first(_select_for_update_order(lambda: item.save()))
        item.refresh_from_db()
        item.description = 'bulk update'
        assert_parent_first(_select_for_update_order(
            lambda: QuotationLineItem.objects.bulk_update([item], ['description'])))
        extra = QuotationLineItem.objects.create(
            quotation=draft, item_type=LineItemTypeChoices.PART, description='to delete',
            quantity=Decimal('1.00'), unit_price=Decimal('2.00'),
        )
        assert_parent_first(_select_for_update_order(lambda: extra.delete()))
        assert_parent_first(_select_for_update_order(
            lambda: QuotationLineItem.objects.filter(pk=item.pk).delete()))
        assert not QuotationLineItem.objects.filter(pk__in=[item.pk, extra.pk]).exists()

    def test_quotation_services_lock_quotations_before_booking(self, booking_with_quotation, buyer_user, owner_user):
        booking, _ = booking_with_quotation
        draft = _new_draft(booking, owner_user)
        # Quotation rows are locked first; later quotation entries after the booking are re-locks of
        # rows this transaction already holds (they cannot wait), not new acquisitions.
        order = _select_for_update_order(lambda: QuotationService.issue_quotation(draft, actor=owner_user))
        assert order[0] == 'WorkshopQuotation', order
        assert order.index('WorkshopQuotation') < order.index('WorkshopBooking'), order
        order = _select_for_update_order(lambda: _new_draft(booking, owner_user, description='Another revision'))
        assert order[0] == 'WorkshopQuotation', order
        assert order.index('WorkshopQuotation') < order.index('WorkshopBooking'), order

    def test_accept_and_reject_lock_quotation_before_booking(self, booking_with_quotation, buyer_user, owner_user):
        booking, quote = booking_with_quotation
        order = _select_for_update_order(lambda: QuotationService.reject_quotation(quote, buyer=buyer_user, reason='No'))
        assert order[0] == 'WorkshopQuotation', order
        assert order.index('WorkshopQuotation') < order.index('WorkshopBooking'), order

        v2 = QuotationService.issue_quotation(_new_draft(booking, owner_user, description='After rejection'), actor=owner_user)
        order = _select_for_update_order(lambda: QuotationService.accept_quotation(v2, buyer=buyer_user))
        assert order[0] == 'WorkshopQuotation', order
        assert order.index('WorkshopQuotation') < order.index('WorkshopBooking'), order

    def test_multi_row_quotation_locks_use_primary_key_order(self, booking_with_quotation, owner_user):
        """Revision and issue lock their quotation rows ORDER BY primary key, not Meta.ordering (-version)."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        booking, _ = booking_with_quotation
        table = WorkshopQuotation._meta.db_table
        pk_order = f'ORDER BY "{table}"."id" ASC'

        def lock_queries(ctx):
            # The quotation lock queries select only the id column (FOR UPDATE is omitted on SQLite).
            return [q['sql'] for q in ctx.captured_queries
                    if q['sql'].startswith(f'SELECT "{table}"."id" FROM "{table}"') and 'ORDER BY' in q['sql']]

        with CaptureQueriesContext(connection) as ctx:
            draft = _new_draft(booking, owner_user)
        revision_locks = [q for q in lock_queries(ctx) if "'DRAFT'" in q]
        assert revision_locks, ctx.captured_queries
        assert all(pk_order in q for q in revision_locks), revision_locks

        with CaptureQueriesContext(connection) as ctx:
            QuotationService.issue_quotation(draft, actor=owner_user)
        issue_locks = [q for q in lock_queries(ctx) if "'ISSUED'" in q and ' OR ' in q]
        assert issue_locks, ctx.captured_queries
        assert all(pk_order in q for q in issue_locks), issue_locks

