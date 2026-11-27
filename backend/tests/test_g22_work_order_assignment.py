"""Focused regression coverage for the G22 work-order assignment contract."""

from datetime import date

import pytest
from rest_framework.test import APIClient

from apps.garage.models import GarageVehicle
from apps.identity.models import RoleChoices, User
from apps.organisations.models import (
    Organisation,
    OrganisationRoleChoices,
    OrganisationTypeChoices,
)
from apps.workshops.models import (
    WorkOrder,
    WorkshopBooking,
    WorkshopProfile,
    WorkshopQuotation,
)


@pytest.fixture
def assignment_records(db):
    owner = User.objects.create_user(
        email="g22-owner@example.test", password="Password123!", first_name="Garage", last_name="Owner"
    )
    owner.add_role(RoleChoices.WORKSHOP)
    technician = User.objects.create_user(
        email="g22-tech@example.test", password="Password123!", first_name="Taylor", last_name="Tech"
    )
    technician.add_role(RoleChoices.WORKSHOP)
    buyer = User.objects.create_user(
        email="g22-buyer@example.test", password="Password123!", first_name="Casey", last_name="Buyer"
    )
    organisation = Organisation.objects.create(
        name="G22 Test Workshop", type=OrganisationTypeChoices.WORKSHOP, created_by=owner
    )
    organisation.add_member(owner, role=OrganisationRoleChoices.OWNER)
    organisation.add_member(technician, role=OrganisationRoleChoices.TECHNICIAN)
    workshop = WorkshopProfile.objects.create(
        organisation=organisation, business_name="G22 Test Workshop", slug="g22-test-workshop"
    )
    vehicle = GarageVehicle.objects.create(
        user=buyer, make="Test", model="Vehicle", year=2022, registration_plate="G22 TEST"
    )
    booking = WorkshopBooking.objects.create(
        workshop=workshop,
        buyer=buyer,
        vehicle=vehicle,
        preferred_date=date.today(),
    )
    quotation = WorkshopQuotation.objects.create(booking=booking, version=1)
    work_order = WorkOrder.objects.create(
        booking=booking,
        quotation=quotation,
        workshop=workshop,
        buyer=buyer,
        vehicle=vehicle,
    )
    return owner, technician, workshop, booking, work_order


@pytest.mark.django_db
def test_assignment_persists_and_is_returned_by_subsequent_reads(assignment_records):
    owner, technician, _, booking, work_order = assignment_records
    client = APIClient()
    client.force_authenticate(user=owner)

    response = client.post(
        f"/api/v1/workshops/manage/work-orders/{work_order.id}/assign-technician/",
        {"technician_id": str(technician.id)},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["status"] == "success"
    assert str(response.data["work_order"]["lead_technician"]) == str(technician.id)
    work_order.refresh_from_db()
    booking.refresh_from_db()
    assert work_order.lead_technician_id == technician.id
    assert work_order.assigned_by_id == owner.id
    assert work_order.assigned_at is not None
    assert booking.assigned_technician_id == technician.id

    detail = client.get(f"/api/v1/workshops/manage/work-orders/{work_order.id}/")
    listing = client.get("/api/v1/workshops/manage/work-orders/")
    assert detail.status_code == 200
    assert str(detail.data["lead_technician"]) == str(technician.id)
    assert detail.data["lead_technician_name"] == technician.full_name
    assert listing.status_code == 200
    listed = next(row for row in listing.data["results"] if row["id"] == str(work_order.id))
    assert str(listed["lead_technician"]) == str(technician.id)
    assert listed["lead_technician_name"] == technician.full_name


@pytest.mark.django_db
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"technician_id": "not-a-uuid"},
    ],
)
def test_assignment_rejects_invalid_request_without_mutating_work_order(assignment_records, payload):
    owner, _, _, booking, work_order = assignment_records
    client = APIClient()
    client.force_authenticate(user=owner)

    response = client.post(
        f"/api/v1/workshops/manage/work-orders/{work_order.id}/assign-technician/",
        payload,
        format="json",
    )

    assert response.status_code == 400
    work_order.refresh_from_db()
    booking.refresh_from_db()
    assert work_order.lead_technician_id is None
    assert work_order.assigned_by_id is None
    assert work_order.assigned_at is None
    assert booking.assigned_technician_id is None
