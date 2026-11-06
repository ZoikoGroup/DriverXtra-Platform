from datetime import date, timedelta
from decimal import Decimal

import pytest
from rest_framework import status
from rest_framework.test import APIClient
from django.utils import timezone

from apps.identity.models import User, RoleChoices
from apps.organisations.models import Organisation, OrganisationRoleChoices, OrganisationTypeChoices
from apps.garage.models import GarageVehicle
from apps.workshops.models import (
    WorkshopProfile,
    WorkshopBooking,
    WorkshopQuotation,
    QuotationLineItem,
    LineItemTypeChoices,
    WorkOrder,
    WorkOrderStatusChoices,
    WorkOrderTask,
    WorkOrderTaskStatusChoices,
)
from apps.catalogue.models import PartCategory
from apps.marketplace.models import (
    SparePartListing,
    ListingStatusChoices,
)


@pytest.fixture
def workshop_owner(db):
    user = User.objects.create_user(
        email='owner.techflow@apexmotors.co.uk',
        password='Password123!',
        first_name='Oliver',
        last_name='Owner',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.WORKSHOP)
    return user


@pytest.fixture
def lead_technician(db):
    user = User.objects.create_user(
        email='lead.tech@apexmotors.co.uk',
        password='Password123!',
        first_name='Terry',
        last_name='Technician',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.WORKSHOP)
    return user


@pytest.fixture
def unrelated_technician(db):
    user = User.objects.create_user(
        email='other.tech@othergarage.co.uk',
        password='Password123!',
        first_name='Oscar',
        last_name='Other',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.WORKSHOP)
    return user


@pytest.fixture
def buyer_user(db):
    user = User.objects.create_user(
        email='car.client@driverxtra.co.uk',
        password='Password123!',
        first_name='Catherine',
        last_name='Client',
        phone_number="+447700900123",
        is_email_verified=True,
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.fixture
def workshop_org(db, workshop_owner, lead_technician):
    org = Organisation.objects.create(
        name="Apex Motors Workshop Tech",
        type=OrganisationTypeChoices.WORKSHOP,
        created_by=workshop_owner,
    )
    org.add_member(workshop_owner, role=OrganisationRoleChoices.OWNER)
    org.add_member(lead_technician, role=OrganisationRoleChoices.TECHNICIAN)
    return org


@pytest.fixture
def workshop_profile(db, workshop_org):
    return WorkshopProfile.objects.create(
        organisation=workshop_org,
        business_name="Apex Motors Tech Division",
        slug="apex-motors-tech-division",
        city="London",
        currency="GBP",
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
        make="Volkswagen",
        model="Golf R",
        year=2022,
        registration_plate="GL22 VWX",
        vin="WVWZZZCDZPW000999",
        current_odometer=15000,
        odometer_unit="mi",
    )


@pytest.fixture
def assigned_work_order(db, workshop_profile, buyer_user, garage_vehicle, workshop_owner, lead_technician):
    booking = WorkshopBooking.objects.create(
        workshop=workshop_profile,
        buyer=buyer_user,
        vehicle=garage_vehicle,
        vehicle_make=garage_vehicle.make,
        vehicle_model=garage_vehicle.model,
        vehicle_year=garage_vehicle.year,
        vehicle_registration_plate=garage_vehicle.registration_plate,
        vehicle_vin=garage_vehicle.vin,
        current_odometer=15000,
        odometer_unit="mi",
        preferred_date=date.today() + timedelta(days=1),
        reported_faults="Slight squeal when braking at low speed.",
        customer_notes="Please test fluid boiling point.",
        status="CONFIRMED",
    )
    quotation = WorkshopQuotation.objects.create(
        booking=booking,
        status="DRAFT",
        subtotal_labour=Decimal('120.00'),
        subtotal_parts=Decimal('80.00'),
        tax_rate_percent=Decimal('20.00'),
        tax_amount=Decimal('40.00'),
        total_amount=Decimal('240.00'),
        currency='GBP',
        created_by=workshop_owner,
    )
    QuotationLineItem.objects.create(
        quotation=quotation,
        item_type=LineItemTypeChoices.PART,
        description="High Performance Front Brake Pads",
        part_number="GOLF-R-PADS",
        quantity=Decimal('1.00'),
        unit_price=Decimal('80.00'),
        line_total=Decimal('80.00'),
    )
    quotation.status = "ACCEPTED"
    quotation.save(update_fields=['status'])
    wo = WorkOrder.objects.create(
        workshop=workshop_profile,
        booking=booking,
        quotation=quotation,
        buyer=buyer_user,
        vehicle=garage_vehicle,
        vehicle_make=garage_vehicle.make,
        vehicle_model=garage_vehicle.model,
        vehicle_year=garage_vehicle.year,
        vehicle_registration_plate=garage_vehicle.registration_plate,
        vehicle_vin=garage_vehicle.vin,
        current_odometer=15000,
        odometer_unit="mi",
        lead_technician=lead_technician,
        status=WorkOrderStatusChoices.ASSIGNED,
    )
    WorkOrderTask.objects.create(
        work_order=wo,
        description="Remove old front pads and clean calliper slides",
        assigned_technician=lead_technician,
        estimated_labour_minutes=45,
        status=WorkOrderTaskStatusChoices.PENDING,
        order_index=1,
    )
    return wo


@pytest.fixture
def brake_category(db):
    cat, _ = PartCategory.objects.get_or_create(slug="brakes-tech-test", defaults={"name": "Brakes"})
    return cat


@pytest.fixture
def workshop_part_inventory(db, workshop_org, workshop_owner, brake_category):
    return SparePartListing.objects.create(
        organisation=workshop_org,
        seller=workshop_owner,
        category=brake_category,
        name="High Performance Front Brake Pads",
        brand="Brembo",
        mpn="GOLF-R-PADS",
        price=Decimal('80.00'),
        currency='GBP',
        stock_quantity=8,
        status=ListingStatusChoices.APPROVED,
    )


@pytest.mark.django_db
def test_technician_lists_assigned_work_orders(assigned_work_order, lead_technician):
    """Technician can list work orders assigned to them."""
    client = APIClient()
    client.force_authenticate(user=lead_technician)

    url = "/api/v1/workshops/technician/work-orders/"
    response = client.get(url)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data['status'] == 'success'
    assert data['count'] >= 1
    wo_numbers = [item['work_order_number'] for item in data['results']]
    assert assigned_work_order.work_order_number in wo_numbers


@pytest.mark.django_db
def test_technician_gets_work_order_detail(assigned_work_order, lead_technician):
    """Technician gets full mobile payload including vehicle, customer notes, tasks, and planned scope."""
    client = APIClient()
    client.force_authenticate(user=lead_technician)

    url = f"/api/v1/workshops/technician/work-orders/{assigned_work_order.id}/"
    response = client.get(url)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data['work_order_number'] == assigned_work_order.work_order_number
    assert data['vehicle_make'] == "Volkswagen"
    assert data['vehicle_model'] == "Golf R"
    assert data['buyer_name'] == "Catherine Client"
    assert data['buyer_phone'] == "+447700900123"
    assert "Slight squeal" in data['reported_faults']
    assert "fluid boiling point" in data['customer_notes']
    assert len(data['tasks']) == 1
    assert "IN_PROGRESS" in data['available_transitions']


@pytest.mark.django_db
def test_technician_updates_task_progress(assigned_work_order, lead_technician):
    """Technician updates a task's status, notes, and actual labour minutes."""
    task = assigned_work_order.tasks.first()
    client = APIClient()
    client.force_authenticate(user=lead_technician)

    url = f"/api/v1/workshops/technician/work-orders/{assigned_work_order.id}/tasks/{task.id}/"
    payload = {
        "status": "COMPLETED",
        "actual_labour_minutes": 50,
        "notes": "Calliper slides cleaned and lubricated with silicone grease.",
    }
    response = client.patch(url, payload, format='json')

    assert response.status_code == status.HTTP_200_OK
    task.refresh_from_db()
    assert task.status == WorkOrderTaskStatusChoices.COMPLETED
    assert task.actual_labour_minutes == 50
    assert "lubricated with silicone grease" in task.notes


@pytest.mark.django_db
def test_technician_status_transitions_workflow(assigned_work_order, lead_technician):
    """Technician advances work order from ASSIGNED -> IN_PROGRESS -> QUALITY_CHECK -> COMPLETED."""
    client = APIClient()
    client.force_authenticate(user=lead_technician)
    url = f"/api/v1/workshops/technician/work-orders/{assigned_work_order.id}/status/"

    # Step 1: Start job (ASSIGNED -> IN_PROGRESS)
    resp1 = client.post(url, {"status": "IN_PROGRESS", "internal_notes": "Started diagnostics"}, format='json')
    assert resp1.status_code == status.HTTP_200_OK
    assigned_work_order.refresh_from_db()
    assert assigned_work_order.status == WorkOrderStatusChoices.IN_PROGRESS

    # Step 2: Submit for Quality Check (IN_PROGRESS -> QUALITY_CHECK)
    resp2 = client.post(url, {"status": "QUALITY_CHECK", "quality_notes": "All bolts torqued to 120Nm"}, format='json')
    assert resp2.status_code == status.HTTP_200_OK
    assigned_work_order.refresh_from_db()
    assert assigned_work_order.status == WorkOrderStatusChoices.QUALITY_CHECK

    # Step 3: Complete job (QUALITY_CHECK -> COMPLETED)
    resp3 = client.post(url, {"status": "COMPLETED", "quality_notes": "Final road test passed OK"}, format='json')
    assert resp3.status_code == status.HTTP_200_OK
    assigned_work_order.refresh_from_db()
    assert assigned_work_order.status == WorkOrderStatusChoices.COMPLETED


@pytest.mark.django_db
def test_technician_records_part_consumption_with_stock_decrement(
    assigned_work_order,
    workshop_part_inventory,
    lead_technician,
):
    """Technician records part consumption, automatically decrementing workshop inventory."""
    initial_stock = workshop_part_inventory.stock_quantity
    assert initial_stock == 8

    client = APIClient()
    client.force_authenticate(user=lead_technician)

    url = f"/api/v1/workshops/technician/work-orders/{assigned_work_order.id}/parts/"
    payload = {
        "part_name": "High Performance Front Brake Pads",
        "part_number": "GOLF-R-PADS",
        "quantity": "1.00",
        "unit_cost": "80.00",
        "inventory_item_id": str(workshop_part_inventory.id),
    }
    response = client.post(url, payload, format='json')

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data['is_stock_deducted'] is True

    workshop_part_inventory.refresh_from_db()
    assert workshop_part_inventory.stock_quantity == 7


@pytest.mark.django_db
def test_unrelated_technician_blocked_from_work_order(assigned_work_order, unrelated_technician):
    """Unrelated technician cannot access or modify work orders from another workshop."""
    client = APIClient()
    client.force_authenticate(user=unrelated_technician)

    url = f"/api/v1/workshops/technician/work-orders/{assigned_work_order.id}/"
    response = client.get(url)

    assert response.status_code == status.HTTP_403_FORBIDDEN
