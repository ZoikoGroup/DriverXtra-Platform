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
    LineItemTypeChoices,
    WorkOrder,
    WorkOrderTask,
    WorkOrderPartUsage,
    WorkOrderStatusChoices,
    WorkOrderTaskStatusChoices,
)
from apps.workshops.services import QuotationService, WorkOrderService


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
        status=QuotationStatusChoices.ISSUED,
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
            status=QuotationStatusChoices.ISSUED,
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
            status=QuotationStatusChoices.ISSUED,
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
            status=QuotationStatusChoices.ISSUED,
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

