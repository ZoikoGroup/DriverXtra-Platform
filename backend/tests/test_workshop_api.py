from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from rest_framework import status
from rest_framework.test import APIClient
from django.utils import timezone

from apps.identity.models import User, RoleChoices
from apps.organisations.models import Organisation, OrganisationMembership, OrganisationRoleChoices, OrganisationTypeChoices
from apps.garage.models import GarageVehicle
from apps.catalogue.models import Part, PartCategory
from apps.workshops.models import (
    WorkshopProfile,
    WorkshopOperatingHours,
    WorkshopServiceCategory,
    WorkshopService,
    WorkshopBooking,
    WorkshopQuotation,
    QuotationLineItem,
    DayOfWeekChoices,
    BookingStatusChoices,
    QuotationStatusChoices,
    LineItemTypeChoices,
)


@pytest.fixture
def workshop_owner_user(db):
    user = User.objects.create_user(
        email='owner@prestigegarage.co.uk',
        password='SecurePassword123!',
        first_name='Arthur',
        last_name='Pendleton',
        phone_number='+447000111222',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.WORKSHOP)
    return user


@pytest.fixture
def workshop_tech_user(db):
    user = User.objects.create_user(
        email='tech@prestigegarage.co.uk',
        password='SecurePassword123!',
        first_name='Bob',
        last_name='Spanner',
        phone_number='+447000333444',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.WORKSHOP)
    return user


@pytest.fixture
def workshop_org(db, workshop_owner_user):
    org = Organisation.objects.create(
        name="Prestige Auto Care Ltd",
        type=OrganisationTypeChoices.WORKSHOP,
        created_by=workshop_owner_user,
    )
    # Add owner membership
    org.add_member(workshop_owner_user, role=OrganisationRoleChoices.OWNER)
    return org


@pytest.fixture
def workshop_profile(db, workshop_org):
    return WorkshopProfile.objects.create(
        organisation=workshop_org,
        business_name="Prestige Auto Care",
        contact_email="service@prestige.co.uk",
        contact_phone="+442079460991",
        address_line1="45 Industrial Park",
        city="Manchester",
        postal_code="M1 2AB",
        country="GB",
        bay_capacity=2,
        is_accepting_bookings=True,
        is_verified=True,
        is_tax_registered=True,
        default_tax_rate_percent=Decimal("20.00"),
    )


@pytest.fixture
def workshop_service(db, workshop_profile):
    cat = WorkshopServiceCategory.objects.create(name="Servicing & Diagnostics", slug="servicing-diagnostics")
    return WorkshopService.objects.create(
        workshop=workshop_profile,
        category=cat,
        name="Comprehensive Major Service",
        estimated_duration_minutes=120,
        base_price=Decimal("180.00"),
        currency="GBP",
    )


@pytest.fixture
def buyer_vehicle(db, buyer_user):
    return GarageVehicle.objects.create(
        user=buyer_user,
        make="Volkswagen",
        model="Golf GTD",
        year=2020,
        registration_plate="VK20 XYZ",
        vin="WVWZZZAUZLW123456",
        current_odometer=42000,
        odometer_unit="mi",
    )


@pytest.fixture
def buyer_client(buyer_user):
    client = APIClient()
    client.force_authenticate(user=buyer_user)
    return client


@pytest.fixture
def owner_client(workshop_owner_user):
    client = APIClient()
    client.force_authenticate(user=workshop_owner_user)
    return client


@pytest.fixture
def tech_client(workshop_tech_user, workshop_org):
    workshop_org.add_member(workshop_tech_user, role=OrganisationRoleChoices.TECHNICIAN)
    client = APIClient()
    client.force_authenticate(user=workshop_tech_user)
    return client


@pytest.fixture
def admin_client(staff_user):
    client = APIClient()
    client.force_authenticate(user=staff_user)
    return client


@pytest.mark.django_db
class TestWorkshopPublicAndBuyerFlows:

    def test_list_and_search_workshops_public(self, api_client, workshop_profile):
        resp = api_client.get('/api/v1/workshops/')
        assert resp.status_code == status.HTTP_200_OK
        results = resp.json()['results']
        assert len(results) >= 1
        assert results[0]['business_name'] == "Prestige Auto Care"
        assert results[0]['city'] == "Manchester"

        # Search by city
        city_resp = api_client.get('/api/v1/workshops/?city=Manchester')
        assert len(city_resp.json()['results']) >= 1

        # Search non-matching city
        none_resp = api_client.get('/api/v1/workshops/?city=Edinburgh')
        assert len(none_resp.json()['results']) == 0

    def test_get_workshop_detail_by_slug_and_id(self, api_client, workshop_profile, workshop_service):
        # By ID
        id_resp = api_client.get(f'/api/v1/workshops/{workshop_profile.id}/')
        assert id_resp.status_code == status.HTTP_200_OK
        assert id_resp.json()['display_name'] == "Prestige Auto Care"
        assert len(id_resp.json()['services']) == 1

        # By Slug
        slug_resp = api_client.get(f'/api/v1/workshops/{workshop_profile.slug}/')
        assert slug_resp.status_code == status.HTTP_200_OK
        assert slug_resp.json()['id'] == str(workshop_profile.id)

    def test_buyer_creates_booking_request(self, buyer_client, workshop_profile, workshop_service, buyer_vehicle):
        payload = {
            'workshop_id': str(workshop_profile.id),
            'vehicle_id': str(buyer_vehicle.id),
            'service_ids': [str(workshop_service.id)],
            'preferred_date': str(date.today() + timedelta(days=5)),
            'preferred_time_slot': '09:00 - 11:00',
            'customer_notes': 'Oil pressure warning flashed twice yesterday.',
            'reported_faults': 'Engine noise at cold start.',
        }
        resp = buyer_client.post('/api/v1/workshops/bookings/', payload, format='json')
        assert resp.status_code == status.HTTP_201_CREATED
        data = resp.json()
        assert data['booking_number'].startswith('BK-')
        assert data['status'] == 'REQUESTED'
        assert data['vehicle_make'] == 'Volkswagen'
        assert data['vehicle_registration_plate'] == 'VK20 XYZ'
        assert len(data['service_items']) == 1
        assert data['service_items'][0]['service_name'] == 'Comprehensive Major Service'

    def test_buyer_views_booking_history(self, buyer_client, workshop_profile, buyer_vehicle):
        # Create a booking directly
        booking = WorkshopBooking.objects.create(
            workshop=workshop_profile,
            buyer=buyer_vehicle.user,
            vehicle=buyer_vehicle,
            preferred_date=date.today() + timedelta(days=4),
        )

        resp = buyer_client.get('/api/v1/workshops/bookings/my/')
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()['count'] >= 1

        detail_resp = buyer_client.get(f'/api/v1/workshops/bookings/my/{booking.id}/')
        assert detail_resp.status_code == status.HTTP_200_OK
        assert detail_resp.json()['id'] == str(booking.id)

    def test_buyer_cancels_booking(self, buyer_client, workshop_profile, buyer_vehicle):
        booking = WorkshopBooking.objects.create(
            workshop=workshop_profile,
            buyer=buyer_vehicle.user,
            vehicle=buyer_vehicle,
            preferred_date=date.today() + timedelta(days=4),
        )

        cancel_resp = buyer_client.post(
            f'/api/v1/workshops/bookings/my/{booking.id}/cancel/',
            {'reason': 'Work schedule clash, will rebook next week.'},
            format='json',
        )
        assert cancel_resp.status_code == status.HTTP_200_OK
        assert cancel_resp.json()['status'] == 'CANCELLED'
        assert cancel_resp.json()['cancellation_reason'] == 'Work schedule clash, will rebook next week.'


@pytest.mark.django_db
class TestWorkshopManagementAndQuotationFlow:

    @pytest.fixture
    def booking(self, workshop_profile, buyer_user, buyer_vehicle):
        return WorkshopBooking.objects.create(
            workshop=workshop_profile,
            buyer=buyer_user,
            vehicle=buyer_vehicle,
            preferred_date=date.today() + timedelta(days=3),
        )

    def test_owner_manages_profile(self, owner_client, workshop_profile):
        resp = owner_client.get('/api/v1/workshops/manage/profile/')
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()['business_name'] == "Prestige Auto Care"

        update_resp = owner_client.patch(
            '/api/v1/workshops/manage/profile/',
            {'bay_capacity': 5, 'description': 'Upgraded service bays with Hunter alignment.'},
            format='json',
        )
        assert update_resp.status_code == status.HTTP_200_OK
        assert update_resp.json()['bay_capacity'] == 5

    def test_owner_configures_operating_hours(self, owner_client, workshop_profile):
        hours_data = [
            {'day_of_week': 0, 'is_closed': False, 'open_time': '08:00', 'close_time': '17:30', 'slot_duration_minutes': 60},
            {'day_of_week': 1, 'is_closed': False, 'open_time': '08:00', 'close_time': '17:30', 'slot_duration_minutes': 60},
            {'day_of_week': 6, 'is_closed': True},
        ]
        resp = owner_client.put('/api/v1/workshops/manage/operating-hours/', hours_data, format='json')
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.json()) == 3

    def test_workshop_accepts_and_schedules_appointment_with_capacity_check(self, owner_client, booking, workshop_profile):
        # 1. Accept
        accept_resp = owner_client.post(
            f'/api/v1/workshops/manage/bookings/{booking.id}/status/',
            {'action': 'ACCEPT', 'internal_notes': 'Assigned to diagnostic bay.'},
            format='json',
        )
        assert accept_resp.status_code == status.HTTP_200_OK
        assert accept_resp.json()['status'] == 'ACCEPTED'

        # 2. Schedule
        start = timezone.now() + timedelta(days=3, hours=9)
        end = start + timedelta(hours=2)
        schedule_resp = owner_client.post(
            f'/api/v1/workshops/manage/bookings/{booking.id}/status/',
            {
                'action': 'SCHEDULE',
                'scheduled_appointment_start': start.isoformat(),
                'scheduled_appointment_end': end.isoformat(),
                'internal_notes': 'Confirmed with customer by phone.',
            },
            format='json',
        )
        assert schedule_resp.status_code == status.HTTP_200_OK
        assert schedule_resp.json()['status'] == 'CONFIRMED'

    def test_capacity_exceeded_prevents_overbooking(self, owner_client, workshop_profile, buyer_user, buyer_vehicle):
        # Workshop bay_capacity is 2
        workshop_profile.bay_capacity = 1
        workshop_profile.save()

        start = timezone.now() + timedelta(days=2, hours=10)
        end = start + timedelta(hours=2)

        # Booking 1 scheduled in that slot
        b1 = WorkshopBooking.objects.create(
            workshop=workshop_profile,
            buyer=buyer_user,
            vehicle=buyer_vehicle,
            preferred_date=start.date(),
            scheduled_appointment_start=start,
            scheduled_appointment_end=end,
            status=BookingStatusChoices.CONFIRMED,
        )

        # Booking 2 tries to book same slot
        b2 = WorkshopBooking.objects.create(
            workshop=workshop_profile,
            buyer=buyer_user,
            vehicle=buyer_vehicle,
            preferred_date=start.date(),
        )

        overbook_resp = owner_client.post(
            f'/api/v1/workshops/manage/bookings/{b2.id}/status/',
            {
                'action': 'SCHEDULE',
                'scheduled_appointment_start': start.isoformat(),
                'scheduled_appointment_end': end.isoformat(),
            },
            format='json',
        )
        assert overbook_resp.status_code == status.HTTP_409_CONFLICT
        assert overbook_resp.json()['code'] == 'CAPACITY_EXCEEDED'

    def test_full_quotation_lifecycle(self, owner_client, buyer_client, booking):
        # 1. Workshop creates draft quotation
        quote_payload = {
            'discount_amount': '20.00',
            'tax_rate_percent': '20.00',
            'valid_until': str(date.today() + timedelta(days=14)),
            'workshop_notes': 'Estimate includes genuine OEM filters and Shell Helix Ultra oil.',
            'line_items': [
                {
                    'item_type': 'LABOUR',
                    'description': 'Diagnostic fault-finding & oil service labour',
                    'quantity': '2.00',
                    'unit_price': '80.00',
                },
                {
                    'item_type': 'PART',
                    'description': 'OEM Oil Filter & Gasket',
                    'quantity': '1.00',
                    'unit_price': '25.00',
                },
                {
                    'item_type': 'DISPOSAL',
                    'description': 'Environmental hazardous oil disposal fee',
                    'quantity': '1.00',
                    'unit_price': '5.00',
                },
            ],
        }
        create_resp = owner_client.post(
            f'/api/v1/workshops/manage/bookings/{booking.id}/quotations/',
            quote_payload,
            format='json',
        )
        assert create_resp.status_code == status.HTTP_201_CREATED
        quote_data = create_resp.json()
        assert quote_data['status'] == 'DRAFT'
        # Labour: 160, Parts: 25, Other: 5 -> Gross: 190, Discount: 20 -> Net: 170. Tax (20%): 34. Total: 204.00
        assert quote_data['subtotal_labour'] == '160.00'
        assert quote_data['subtotal_parts'] == '25.00'
        assert quote_data['tax_amount'] == '34.00'
        assert quote_data['total_amount'] == '204.00'
        quote_id = quote_data['id']

        # 2. Workshop issues quotation
        issue_resp = owner_client.post(f'/api/v1/workshops/manage/quotations/{quote_id}/issue/')
        assert issue_resp.status_code == status.HTTP_200_OK
        assert issue_resp.json()['status'] == 'ISSUED'

        # Verify booking is now QUOTED
        booking.refresh_from_db()
        assert booking.status == BookingStatusChoices.QUOTED

        # 3. Buyer accepts quotation
        accept_resp = buyer_client.post(f'/api/v1/workshops/quotations/{quote_id}/accept/')
        assert accept_resp.status_code == status.HTTP_200_OK
        assert accept_resp.json()['status'] == 'ACCEPTED'

        # Verify booking status transitioned to CONFIRMED
        booking.refresh_from_db()
        assert booking.status == BookingStatusChoices.CONFIRMED

    def test_tech_permissions_boundary(self, tech_client, workshop_profile):
        # Technician can view bookings
        view_resp = tech_client.get('/api/v1/workshops/manage/bookings/')
        assert view_resp.status_code == status.HTTP_200_OK

        # Technician CANNOT update workshop profile
        patch_resp = tech_client.patch('/api/v1/workshops/manage/profile/', {'bay_capacity': 99}, format='json')
        assert patch_resp.status_code == status.HTTP_403_FORBIDDEN

        # Technician CANNOT delete services
        service = WorkshopService.objects.create(
            workshop=workshop_profile,
            name="Tyre Fitting",
            base_price=Decimal("15.00"),
        )
        del_resp = tech_client.delete(f'/api/v1/workshops/manage/services/{service.id}/')
        assert del_resp.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_oversight_view(self, admin_client, booking):
        admin_resp = admin_client.get('/api/v1/workshops/admin/bookings/')
        assert admin_resp.status_code == status.HTTP_200_OK
        results = admin_resp.json()['results']
        assert any(b['id'] == str(booking.id) for b in results)

