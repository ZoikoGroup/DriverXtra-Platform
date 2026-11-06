from datetime import date, timedelta
from decimal import Decimal

import pytest
from rest_framework import status
from rest_framework.test import APIClient
from django.utils import timezone

from apps.identity.models import User, RoleChoices
from apps.organisations.models import Organisation, OrganisationRoleChoices, OrganisationTypeChoices
from apps.garage.models import GarageVehicle, VehicleServiceRecord, RecordSourceChoices
from apps.workshops.models import (
    WorkshopProfile,
    WorkshopBooking,
    WorkshopQuotation,
    WorkOrder,
    WorkOrderStatusChoices,
    WorkOrderTask,
    WorkOrderTaskStatusChoices,
    WorkOrderPartUsage,
)
from apps.garage.services import VehicleServiceHistoryService
from apps.garage.passport_service import VehiclePassportPdfService


@pytest.fixture
def owner_user(db):
    user = User.objects.create_user(
        email='car.owner@driverxtra.co.uk',
        password='Password123!',
        first_name='Oliver',
        last_name='Owner',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.fixture
def other_buyer(db):
    user = User.objects.create_user(
        email='other.buyer@driverxtra.co.uk',
        password='Password123!',
        first_name='Eve',
        last_name='Eavesdropper',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.fixture
def workshop_user(db):
    user = User.objects.create_user(
        email='workshop.lead@apexmotors.co.uk',
        password='Password123!',
        first_name='Walter',
        last_name='Workshop',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.WORKSHOP)
    return user


@pytest.fixture
def workshop_org(db, workshop_user):
    org = Organisation.objects.create(
        name="Apex Motors Workshop",
        type=OrganisationTypeChoices.WORKSHOP,
        created_by=workshop_user,
    )
    org.add_member(workshop_user, role=OrganisationRoleChoices.OWNER)
    return org


@pytest.fixture
def workshop_profile(db, workshop_org):
    return WorkshopProfile.objects.create(
        organisation=workshop_org,
        business_name="Apex Auto Services Ltd",
        slug="apex-auto-services-pdf",
        address_line1="12 High Street",
        city="London",
        postal_code="SW1A 1AA",
        contact_phone="+442079460123",
        currency="GBP",
        is_tax_registered=True,
        can_collect_tax=True,
        default_tax_rate_percent=Decimal('20.00'),
        is_accepting_bookings=True,
        is_verified=True,
    )


@pytest.fixture
def garage_vehicle(db, owner_user):
    return GarageVehicle.objects.create(
        user=owner_user,
        make="Audi",
        model="A4 2.0 TDI S Line",
        year=2021,
        trim="S Line",
        registration_plate="GF21 XTR",
        vin="WAUZZZF41MA000123",
        engine_code="DETA",
        fuel_type="Diesel",
        transmission="Automatic (S-Tronic)",
        color="Daytona Grey",
        current_odometer=32450,
        odometer_unit="mi",
    )


@pytest.fixture
def completed_work_order(db, workshop_profile, owner_user, garage_vehicle, workshop_user):
    booking = WorkshopBooking.objects.create(
        workshop=workshop_profile,
        buyer=owner_user,
        vehicle=garage_vehicle,
        vehicle_make=garage_vehicle.make,
        vehicle_model=garage_vehicle.model,
        vehicle_year=garage_vehicle.year,
        vehicle_registration_plate=garage_vehicle.registration_plate,
        vehicle_vin=garage_vehicle.vin,
        current_odometer=32450,
        odometer_unit="mi",
        preferred_date=date.today() + timedelta(days=2),
        status="CONFIRMED",
    )
    quotation = WorkshopQuotation.objects.create(
        booking=booking,
        status="ACCEPTED",
        subtotal_labour=Decimal('150.00'),
        subtotal_parts=Decimal('120.00'),
        tax_rate_percent=Decimal('20.00'),
        tax_amount=Decimal('54.00'),
        total_amount=Decimal('324.00'),
        currency='GBP',
        created_by=workshop_user,
    )
    wo = WorkOrder.objects.create(
        workshop=workshop_profile,
        booking=booking,
        quotation=quotation,
        buyer=owner_user,
        vehicle=garage_vehicle,
        vehicle_make=garage_vehicle.make,
        vehicle_model=garage_vehicle.model,
        vehicle_year=garage_vehicle.year,
        vehicle_registration_plate=garage_vehicle.registration_plate,
        vehicle_vin=garage_vehicle.vin,
        current_odometer=32450,
        odometer_unit="mi",
        lead_technician=workshop_user,
        status=WorkOrderStatusChoices.COMPLETED,
        completed_at=timezone.now(),
    )
    WorkOrderTask.objects.create(
        work_order=wo,
        description="Replace engine oil and OEM filter cartridge",
        status=WorkOrderTaskStatusChoices.COMPLETED,
        actual_labour_minutes=45,
        order_index=1,
    )
    WorkOrderPartUsage.objects.create(
        work_order=wo,
        part_name="Castrol Edge Professional 5W-30 (5L)",
        part_number="OIL-5W30-01",
        quantity=Decimal('1.00'),
        unit_cost=Decimal('45.00'),
        total_cost=Decimal('45.00'),
        added_by=workshop_user,
    )
    return wo


@pytest.mark.django_db
def test_vehicle_passport_pdf_service_generates_valid_pdf(garage_vehicle, completed_work_order, workshop_user):
    """VehiclePassportPdfService directly renders valid PDF bytes with header, tables, and records."""
    VehicleServiceHistoryService.create_verified_record_for_work_order(
        work_order=completed_work_order,
        actor=workshop_user,
    )

    pdf_bytes = VehiclePassportPdfService.generate_passport_pdf(garage_vehicle)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b'%PDF-')
    assert b'%%EOF' in pdf_bytes


@pytest.mark.django_db
def test_owner_can_download_passport_pdf_endpoint(garage_vehicle, completed_work_order, owner_user, workshop_user):
    """Vehicle owner can download the official service passport via GET API."""
    VehicleServiceHistoryService.create_verified_record_for_work_order(
        work_order=completed_work_order,
        actor=workshop_user,
    )

    client = APIClient()
    client.force_authenticate(user=owner_user)

    url = f"/api/v1/garage/vehicles/{garage_vehicle.id}/passport/pdf/"
    response = client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert response['Content-Type'] == 'application/pdf'
    assert 'attachment;' in response['Content-Disposition']
    assert 'GF21_XTR.pdf' in response['Content-Disposition']
    assert response.content.startswith(b'%PDF-')


@pytest.mark.django_db
def test_unauthorized_user_cannot_download_passport_pdf(garage_vehicle, other_buyer):
    """Unrelated user cannot download another user's vehicle service passport."""
    client = APIClient()
    client.force_authenticate(user=other_buyer)

    url = f"/api/v1/garage/vehicles/{garage_vehicle.id}/passport/pdf/"
    response = client.get(url)

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_servicing_workshop_can_download_serviced_vehicle_passport(garage_vehicle, completed_work_order, workshop_user):
    """Workshop profile that serviced the vehicle has permission to download its passport."""
    VehicleServiceHistoryService.create_verified_record_for_work_order(
        work_order=completed_work_order,
        actor=workshop_user,
    )

    client = APIClient()
    client.force_authenticate(user=workshop_user)

    url = f"/api/v1/garage/vehicles/{garage_vehicle.id}/passport/pdf/"
    response = client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert response['Content-Type'] == 'application/pdf'


@pytest.mark.django_db
def test_archived_vehicle_passport_returns_404(garage_vehicle, owner_user):
    """Archived vehicles return 404 Not Found for passport PDF requests."""
    garage_vehicle.archive()

    client = APIClient()
    client.force_authenticate(user=owner_user)

    url = f"/api/v1/garage/vehicles/{garage_vehicle.id}/passport/pdf/"
    response = client.get(url)

    assert response.status_code == status.HTTP_404_NOT_FOUND
