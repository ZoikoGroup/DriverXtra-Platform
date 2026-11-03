from datetime import date, timedelta
from decimal import Decimal

import pytest
from rest_framework import status
from rest_framework.test import APIClient
from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError

from apps.identity.models import User, RoleChoices
from apps.organisations.models import Organisation, OrganisationRoleChoices, OrganisationTypeChoices
from apps.garage.models import GarageVehicle, VehicleServiceRecord
from apps.notifications.models import Notification
from apps.workshops.models import (
    WorkshopProfile,
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
    ChangeOrder,
    ChangeOrderLineItem,
    ChangeOrderStatusChoices,
)
from apps.workshops.services import QuotationService, WorkOrderService, ChangeOrderService
from apps.garage.services import VehicleServiceHistoryService
from platform_core.audit.models import AuditLog


@pytest.fixture
def owner_user(db):
    user = User.objects.create_user(
        email='owner@apexchange.com',
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
        email='tech@apexchange.com',
        password='Password123!',
        first_name='Tom',
        last_name='Tech',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.WORKSHOP)
    return user


@pytest.fixture
def external_user(db):
    user = User.objects.create_user(
        email='external@random.com',
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
def other_buyer_user(db):
    user = User.objects.create_user(
        email='otherbuyer@driverxtra.com',
        password='Password123!',
        first_name='Alice',
        last_name='AnotherBuyer',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.fixture
def workshop_org(db, owner_user, tech_user):
    org = Organisation.objects.create(
        name="Apex Change Workshop",
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
        business_name="Apex Change Motors",
        slug="apex-change-motors",
        city="Manchester",
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
        make="Audi",
        model="A4 Avant",
        year=2022,
        registration_plate="DX22 AUD",
        vin="WAUZZZ8W123456789",
        current_odometer=24000,
        odometer_unit="mi",
    )


@pytest.fixture
def work_order_fixture(db, workshop_profile, buyer_user, garage_vehicle, owner_user, tech_user):
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
        status=BookingStatusChoices.CONFIRMED,
        assigned_technician=tech_user,
    )

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
        description="Standard Brake Inspection",
        quantity=Decimal('1.00'),
        unit_price=Decimal('50.00'),
        line_total=Decimal('50.00'),
    )
    QuotationLineItem.objects.create(
        quotation=quote,
        item_type=LineItemTypeChoices.PART,
        description="Standard Brake Fluid DOT4",
        quantity=Decimal('1.00'),
        unit_price=Decimal('15.00'),
        line_total=Decimal('15.00'),
    )
    quote.recalculate_totals(commit=True)
    # net = 65, tax 20% = 13.00, total = 78.00

    quote = QuotationService.accept_quotation(quote, buyer=buyer_user)
    wo = WorkOrder.objects.get(booking=booking)
    wo.status = WorkOrderStatusChoices.IN_PROGRESS
    wo.save(update_fields=['status'])
    return wo


@pytest.mark.django_db
class TestChangeOrderCreationAndCalculations:
    """Verifies change order creation, validation rules, and financial calculations."""

    def test_create_draft_change_order_calculates_correct_totals(self, work_order_fixture, owner_user):
        wo = work_order_fixture
        initial_quote_total = wo.quotation.total_amount  # 78.00

        data = {
            'reason': 'Front brake pads worn below 1.5mm; front discs heavily scored.',
            'discount_amount': Decimal('10.00'),
            'tax_rate_percent': Decimal('20.00'),
            'workshop_notes': 'Observed severe disc grooving on driver side wheel.',
            'line_items': [
                {
                    'item_type': LineItemTypeChoices.LABOUR,
                    'description': 'Replace Front Brake Discs & Pads',
                    'quantity': Decimal('1.50'),
                    'unit_price': Decimal('80.00'),
                    'estimated_labour_minutes': 90,
                },
                {
                    'item_type': LineItemTypeChoices.PART,
                    'description': 'Brembo Front Brake Discs (Pair)',
                    'part_number': 'BRM-09.B337.21',
                    'quantity': Decimal('1.00'),
                    'unit_price': Decimal('120.00'),
                },
                {
                    'item_type': LineItemTypeChoices.PART,
                    'description': 'Brembo Front Brake Pads Set',
                    'part_number': 'BRM-P85.126',
                    'quantity': Decimal('1.00'),
                    'unit_price': Decimal('50.00'),
                },
            ],
        }

        co = ChangeOrderService.create_change_order(work_order=wo, data=data, actor=owner_user)

        assert co.status == ChangeOrderStatusChoices.DRAFT
        assert co.version == 1
        assert co.work_order == wo
        assert co.change_order_number.startswith('CO-')

        # Financial checks:
        # Labour: 1.5 * 80 = 120.00
        # Parts: 120 + 50 = 170.00
        # Gross = 290.00
        # Discount = 10.00 -> Net = 280.00
        # Tax 20% = 56.00
        # Additional Amount = 336.00
        # Revised Authorized Total = 78.00 + 336.00 = 414.00
        assert co.subtotal_labour == Decimal('120.00')
        assert co.subtotal_parts == Decimal('170.00')
        assert co.discount_amount == Decimal('10.00')
        assert co.tax_amount == Decimal('56.00')
        assert co.additional_amount == Decimal('336.00')
        assert co.revised_authorized_total == Decimal('414.00')
        assert co.currency == 'GBP'

    def test_create_and_submit_change_order_immediately(self, work_order_fixture, owner_user, buyer_user):
        wo = work_order_fixture
        data = {
            'reason': 'Damaged suspension coil spring detected.',
            'submit_for_approval': True,
            'line_items': [
                {
                    'item_type': LineItemTypeChoices.PART,
                    'description': 'Front Left Coil Spring',
                    'quantity': Decimal('1.00'),
                    'unit_price': Decimal('75.00'),
                },
                {
                    'item_type': LineItemTypeChoices.LABOUR,
                    'description': 'Fit Coil Spring',
                    'quantity': Decimal('1.00'),
                    'unit_price': Decimal('60.00'),
                },
            ],
        }

        co = ChangeOrderService.create_change_order(work_order=wo, data=data, actor=owner_user)
        assert co.status == ChangeOrderStatusChoices.SUBMITTED
        assert co.submitted_at is not None

        # Verify buyer received notification
        notif = Notification.objects.filter(recipient=buyer_user).first()
        assert notif is not None
        assert co.change_order_number in notif.title

    def test_empty_reason_or_empty_line_items_rejected(self, work_order_fixture, owner_user):
        wo = work_order_fixture

        with pytest.raises(DjangoValidationError, match="reason for additional work is required"):
            ChangeOrderService.create_change_order(
                work_order=wo,
                data={'reason': '', 'line_items': [{'description': 'Part', 'unit_price': 10}]},
                actor=owner_user,
            )

        with pytest.raises(DjangoValidationError, match="At least one line item is required"):
            ChangeOrderService.create_change_order(
                work_order=wo,
                data={'reason': 'Valid reason', 'line_items': []},
                actor=owner_user,
            )

    def test_cannot_raise_change_order_on_completed_or_cancelled_work_order(self, work_order_fixture, owner_user):
        wo = work_order_fixture
        wo.status = WorkOrderStatusChoices.CANCELLED
        wo.save(update_fields=['status'])

        with pytest.raises(DjangoValidationError, match="Cannot raise a change order for a cancelled work order"):
            ChangeOrderService.create_change_order(
                work_order=wo,
                data={'reason': 'Too late', 'line_items': [{'description': 'Part', 'unit_price': 10}]},
                actor=owner_user,
            )


@pytest.mark.django_db
class TestChangeOrderAuthorizationAndAccessControl:
    """Verifies strict role and identity boundaries on change order actions."""

    def test_external_user_cannot_create_change_order(self, work_order_fixture, external_user):
        wo = work_order_fixture
        with pytest.raises(DjangoValidationError, match="permission to manage change orders for this workshop"):
            ChangeOrderService.create_change_order(
                work_order=wo,
                data={'reason': 'Hacker attempt', 'line_items': [{'description': 'Part', 'unit_price': 10}]},
                actor=external_user,
            )

    def test_other_buyer_cannot_approve_or_reject_change_order(self, work_order_fixture, owner_user, other_buyer_user):
        wo = work_order_fixture
        co = ChangeOrderService.create_change_order(
            work_order=wo,
            data={'reason': 'Extra work', 'submit_for_approval': True, 'line_items': [{'description': 'Labour', 'unit_price': 50}]},
            actor=owner_user,
        )

        with pytest.raises(DjangoValidationError, match="Only the vehicle owner who placed this booking can authorize"):
            ChangeOrderService.approve_change_order(change_order=co, buyer=other_buyer_user)

        with pytest.raises(DjangoValidationError, match="Only the vehicle owner who placed this booking can reject"):
            ChangeOrderService.reject_change_order(change_order=co, buyer=other_buyer_user, reason="Not mine")


@pytest.mark.django_db
class TestChangeOrderApprovalWorkflow:
    """Verifies buyer authorization execution, task spawning, and financial updating."""

    def test_buyer_approval_spawns_tasks_without_consuming_parts(self, work_order_fixture, owner_user, buyer_user):
        wo = work_order_fixture
        initial_task_count = wo.tasks.count()  # Initial inspection task from quote

        data = {
            'reason': 'Found worn rear auxiliary belt and tensioner pulley.',
            'submit_for_approval': True,
            'line_items': [
                {
                    'item_type': LineItemTypeChoices.LABOUR,
                    'description': 'Replace Auxiliary Drive Belt & Tensioner',
                    'quantity': Decimal('1.00'),
                    'unit_price': Decimal('70.00'),
                    'estimated_labour_minutes': 60,
                },
                {
                    'item_type': LineItemTypeChoices.PART,
                    'description': 'Drive Belt Kit',
                    'part_number': 'CONT-6PK1870K1',
                    'quantity': Decimal('1.00'),
                    'unit_price': Decimal('65.00'),
                },
            ],
        }
        co = ChangeOrderService.create_change_order(work_order=wo, data=data, actor=owner_user)

        # Buyer approves
        approved_co = ChangeOrderService.approve_change_order(
            change_order=co,
            buyer=buyer_user,
            notes="Authorized - please proceed with belt replacement.",
        )

        assert approved_co.status == ChangeOrderStatusChoices.APPROVED
        assert approved_co.reviewed_by == buyer_user
        assert approved_co.buyer_notes == "Authorized - please proceed with belt replacement."
        assert approved_co.reviewed_at is not None

        # Verify task was spawned for the labour line item
        wo.refresh_from_db()
        assert wo.tasks.count() == initial_task_count + 1
        spawned_task = wo.tasks.filter(description__icontains="Replace Auxiliary Drive Belt").first()
        assert spawned_task is not None
        assert spawned_task.estimated_labour_minutes == 60
        assert spawned_task.assigned_technician == wo.lead_technician
        assert spawned_task.status == WorkOrderTaskStatusChoices.PENDING

        # CRITICAL: Verify parts are NOT automatically marked as consumed
        assert WorkOrderPartUsage.objects.filter(work_order=wo).count() == 0

        # Verify authorized total on WorkOrder
        # Original: 78.00. Added: (70 + 65) = 135 + 20% tax = 162.00. Revised = 240.00
        assert wo.approved_change_orders_amount == approved_co.additional_amount
        assert wo.authorized_total_amount == Decimal('240.00')

    def test_duplicate_approval_prevention(self, work_order_fixture, owner_user, buyer_user):
        wo = work_order_fixture
        co = ChangeOrderService.create_change_order(
            work_order=wo,
            data={'reason': 'Extra work', 'submit_for_approval': True, 'line_items': [{'description': 'Extra part', 'unit_price': 50}]},
            actor=owner_user,
        )

        ChangeOrderService.approve_change_order(change_order=co, buyer=buyer_user)

        # Second approval must fail
        with pytest.raises(DjangoValidationError, match="must be SUBMITTED"):
            ChangeOrderService.approve_change_order(change_order=co, buyer=buyer_user)

        # Attempt to reject an approved change order must fail
        with pytest.raises(DjangoValidationError, match="must be SUBMITTED"):
            ChangeOrderService.reject_change_order(change_order=co, buyer=buyer_user, reason="Changed mind")

    def test_cannot_approve_draft_change_order(self, work_order_fixture, owner_user, buyer_user):
        wo = work_order_fixture
        co = ChangeOrderService.create_change_order(
            work_order=wo,
            data={'reason': 'Draft work', 'submit_for_approval': False, 'line_items': [{'description': 'Part', 'unit_price': 20}]},
            actor=owner_user,
        )
        assert co.status == ChangeOrderStatusChoices.DRAFT

        with pytest.raises(DjangoValidationError, match="must be SUBMITTED"):
            ChangeOrderService.approve_change_order(change_order=co, buyer=buyer_user)


@pytest.mark.django_db
class TestChangeOrderRejectionWorkflow:
    """Verifies buyer rejection behavior and restrictions on rejected scope."""

    def test_buyer_rejection_records_reason_and_excludes_from_authorized_scope(self, work_order_fixture, owner_user, buyer_user):
        wo = work_order_fixture
        initial_tasks = wo.tasks.count()
        initial_authorized = wo.authorized_total_amount

        co = ChangeOrderService.create_change_order(
            work_order=wo,
            data={
                'reason': 'Optional cabin air purification filter.',
                'submit_for_approval': True,
                'line_items': [{'item_type': LineItemTypeChoices.PART, 'description': 'HEPA Cabin Filter', 'unit_price': 45.00}],
            },
            actor=owner_user,
        )

        rejected_co = ChangeOrderService.reject_change_order(
            change_order=co,
            buyer=buyer_user,
            reason="Decline filter upgrade; please stick to mechanical inspection.",
        )

        assert rejected_co.status == ChangeOrderStatusChoices.REJECTED
        assert rejected_co.buyer_notes == "Decline filter upgrade; please stick to mechanical inspection."
        assert rejected_co.reviewed_by == buyer_user

        # No tasks spawned
        wo.refresh_from_db()
        assert wo.tasks.count() == initial_tasks
        assert wo.authorized_total_amount == initial_authorized
        assert wo.approved_change_orders_amount == Decimal('0.00')


@pytest.mark.django_db
class TestChangeOrderWorkOrderCompletionBlocking:
    """Verifies that pending change orders strictly block work order completion."""

    def test_pending_change_order_blocks_work_order_completion(self, work_order_fixture, owner_user, tech_user, buyer_user):
        wo = work_order_fixture

        # Raise change order and leave in SUBMITTED
        co = ChangeOrderService.create_change_order(
            work_order=wo,
            data={'reason': 'Pending oil cooler leak check', 'submit_for_approval': True, 'line_items': [{'description': 'Cooler', 'unit_price': 100}]},
            actor=owner_user,
        )
        assert wo.has_pending_change_orders is True

        # Advance work order to QUALITY_CHECK
        wo.status = WorkOrderStatusChoices.QUALITY_CHECK
        wo.save(update_fields=['status'])

        # Attempt to mark COMPLETED while change order is SUBMITTED
        with pytest.raises(DjangoValidationError, match="Cannot complete Work Order while unresolved Change Orders are pending"):
            WorkOrderService.update_status(
                work_order=wo,
                new_status=WorkOrderStatusChoices.COMPLETED,
                actor=tech_user,
                quality_notes="Tested fine",
            )

        # Resolve change order (reject it)
        ChangeOrderService.reject_change_order(change_order=co, buyer=buyer_user, reason="Do not replace")
        wo.refresh_from_db()
        assert wo.has_pending_change_orders is False

        # Now completion succeeds!
        completed_wo = WorkOrderService.update_status(
            work_order=wo,
            new_status=WorkOrderStatusChoices.COMPLETED,
            actor=tech_user,
            quality_notes="All verified",
        )
        assert completed_wo.status == WorkOrderStatusChoices.COMPLETED


@pytest.mark.django_db
class TestChangeOrderVehicleServiceHistoryIntegration:
    """Verifies that verified vehicle service records inherit approved change orders."""

    def test_completed_work_order_service_record_reflects_revised_authorized_total(self, work_order_fixture, owner_user, tech_user, buyer_user):
        wo = work_order_fixture

        # Add and approve change order
        co = ChangeOrderService.create_change_order(
            work_order=wo,
            data={
                'reason': 'New spark plugs required.',
                'submit_for_approval': True,
                'tax_rate_percent': Decimal('20.00'),
                'line_items': [
                    {'item_type': LineItemTypeChoices.PART, 'description': 'NGK Iridium Plugs x4', 'unit_price': Decimal('40.00')},
                    {'item_type': LineItemTypeChoices.LABOUR, 'description': 'Install Spark Plugs', 'unit_price': Decimal('30.00')},
                ],
            },
            actor=owner_user,
        )
        ChangeOrderService.approve_change_order(change_order=co, buyer=buyer_user)
        # Net = 70.00, Tax = 14.00, Addl = 84.00. Revised = 78.00 + 84.00 = 162.00
        wo.refresh_from_db()
        assert wo.authorized_total_amount == Decimal('162.00')

        # Advance to QUALITY_CHECK then COMPLETED
        wo.status = WorkOrderStatusChoices.QUALITY_CHECK
        wo.save(update_fields=['status'])
        WorkOrderService.update_status(work_order=wo, new_status=WorkOrderStatusChoices.COMPLETED, actor=tech_user)

        # Inspect generated VehicleServiceRecord
        record = VehicleServiceRecord.objects.get(work_order=wo)
        assert record.is_verified is True
        assert record.total_cost == Decimal('162.00')
        assert co.change_order_number in record.description


@pytest.mark.django_db
class TestChangeOrderAPIEndpoints:
    """Tests the REST API views for workshop and buyer interactions."""

    def test_workshop_change_order_api_lifecycle(self, work_order_fixture, owner_user):
        client = APIClient()
        client.force_authenticate(user=owner_user)

        wo = work_order_fixture
        url = f"/api/v1/workshops/manage/work-orders/{wo.id}/change-orders/"

        # 1. Create Change Order via POST
        payload = {
            'reason': 'Front tyre sidewall bulged and unsafe.',
            'discount_amount': '0.00',
            'tax_rate_percent': '20.00',
            'workshop_notes': 'MOT safety critical failure risk.',
            'submit_for_approval': False,
            'line_items': [
                {
                    'item_type': 'PART',
                    'description': 'Michelin Pilot Sport 5 225/45 R18',
                    'part_number': 'MICH-PS5-18',
                    'quantity': '1.00',
                    'unit_price': '135.00',
                },
                {
                    'item_type': 'LABOUR',
                    'description': 'Tyre Fitting & High Speed Balancing',
                    'quantity': '1.00',
                    'unit_price': '25.00',
                    'estimated_labour_minutes': 30,
                },
            ],
        }

        resp = client.post(url, payload, format='json')
        assert resp.status_code == status.HTTP_201_CREATED
        co_id = resp.data['id']
        assert resp.data['status'] == 'DRAFT'
        assert resp.data['subtotal_parts'] == '135.00'
        assert resp.data['subtotal_labour'] == '25.00'
        # Net = 160.00 + 20% = 192.00
        assert resp.data['additional_amount'] == '192.00'

        # 2. List change orders
        list_resp = client.get(url)
        assert list_resp.status_code == status.HTTP_200_OK
        assert len(list_resp.data['results']) == 1

        # 3. Submit change order
        submit_url = f"/api/v1/workshops/manage/change-orders/{co_id}/submit/"
        submit_resp = client.post(submit_url)
        assert submit_resp.status_code == status.HTTP_200_OK
        assert submit_resp.data['status'] == 'SUBMITTED'

    def test_buyer_change_order_api_review_and_decision(self, work_order_fixture, owner_user, buyer_user):
        wo = work_order_fixture

        # Create submitted change order
        co = ChangeOrderService.create_change_order(
            work_order=wo,
            data={
                'reason': 'Rear brake pad replacement required.',
                'submit_for_approval': True,
                'workshop_notes': 'CONFIDENTIAL_WORKSHOP_INTERNAL_PROFIT_NOTE',
                'line_items': [{'item_type': 'PART', 'description': 'Rear Pads', 'unit_price': 40}],
            },
            actor=owner_user,
        )

        # Buyer client
        client = APIClient()
        client.force_authenticate(user=buyer_user)

        # 1. Buyer lists change orders for booking
        list_url = f"/api/v1/workshops/bookings/my/{wo.booking.id}/change-orders/"
        resp = client.get(list_url)
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data['results']) == 1
        item = resp.data['results'][0]
        assert item['id'] == str(co.id)
        # Verify privacy: internal workshop notes MUST NOT be exposed to buyer
        assert 'workshop_notes' not in item

        # 2. Buyer approves change order
        approve_url = f"/api/v1/workshops/change-orders/{co.id}/approve/"
        app_resp = client.post(approve_url, {'notes': 'Looks good to me.'}, format='json')
        assert app_resp.status_code == status.HTTP_200_OK
        assert app_resp.data['status'] == 'APPROVED'
        assert app_resp.data['buyer_notes'] == 'Looks good to me.'

        co.refresh_from_db()
        assert co.status == ChangeOrderStatusChoices.APPROVED