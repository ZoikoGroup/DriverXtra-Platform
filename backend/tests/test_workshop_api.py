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
    WorkOrder,
    WorkOrderTask,
    DayOfWeekChoices,
    BookingStatusChoices,
    QuotationStatusChoices,
    WorkOrderStatusChoices,
    WorkOrderTaskStatusChoices,
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
        can_collect_tax=True,
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
        assert create_resp.status_code == status.HTTP_201_CREATED, create_resp.json()
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

    def test_unauthorized_workshop_quotation_submission_with_tax_fails(self, owner_client, booking, workshop_profile):
        """Unauthorized workshop cannot submit a quotation with tax rate > 0%."""
        workshop_profile.can_collect_tax = False
        workshop_profile.save(update_fields=['can_collect_tax'])

        quote_payload = {
            'discount_amount': '0.00',
            'tax_rate_percent': '20.00',
            'line_items': [
                {
                    'item_type': 'LABOUR',
                    'description': 'Suspension inspection',
                    'quantity': '1.00',
                    'unit_price': '80.00',
                },
            ],
        }
        resp = owner_client.post(
            f'/api/v1/workshops/manage/bookings/{booking.id}/quotations/',
            quote_payload,
            format='json',
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        data = resp.json()
        assert "not authorized to collect tax" in str(data).lower()

    def test_unauthorized_workshop_zero_tax_quotation_lifecycle(self, owner_client, buyer_client, booking, workshop_profile):
        """Unauthorized workshop can create, issue and have accepted a quotation with 0% tax."""
        workshop_profile.can_collect_tax = False
        workshop_profile.save(update_fields=['can_collect_tax'])

        quote_payload = {
            'discount_amount': '15.00',
            'tax_rate_percent': '0.00',
            'line_items': [
                {
                    'item_type': 'LABOUR',
                    'description': 'Brake pad replacement',
                    'quantity': '1.00',
                    'unit_price': '100.00',
                },
            ],
        }
        create_resp = owner_client.post(
            f'/api/v1/workshops/manage/bookings/{booking.id}/quotations/',
            quote_payload,
            format='json',
        )
        assert create_resp.status_code == status.HTTP_201_CREATED, create_resp.json()
        quote_data = create_resp.json()
        assert quote_data['status'] == 'DRAFT'
        assert quote_data['tax_amount'] == '0.00'
        assert quote_data['tax_rate_percent'] == '0.00'
        # Subtotal: 100.00 - Discount: 15.00 + Tax: 0.00 = 85.00
        assert quote_data['total_amount'] == '85.00'

        # Workshop issues quotation
        quote_id = quote_data['id']
        issue_resp = owner_client.post(f'/api/v1/workshops/manage/quotations/{quote_id}/issue/')
        assert issue_resp.status_code == status.HTTP_200_OK
        assert issue_resp.json()['status'] == 'ISSUED'

        # Buyer accepts quotation
        accept_resp = buyer_client.post(f'/api/v1/workshops/quotations/{quote_id}/accept/')
        assert accept_resp.status_code == status.HTTP_200_OK
        assert accept_resp.json()['status'] == 'ACCEPTED'

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

    def test_quotation_issued_after_scheduling_transitions_to_quoted_and_visible_to_buyer(
        self, owner_client, buyer_client, booking, workshop_owner_user
    ):
        """
        Verify that scheduling a booking (CONFIRMED) followed by issuing a quotation:
        1. Correctly transitions booking.status to QUOTED.
        2. Allows the buyer to see the booking when filtering by ?status=QUOTED.
        3. Allows the buyer to accept the quotation, transitioning booking to CONFIRMED with a work order.
        """
        from apps.workshops.services import BookingService
        start = timezone.now() + timedelta(days=2)
        end = start + timedelta(hours=2)

        # 1. Workshop schedules the appointment -> booking becomes CONFIRMED
        BookingService.schedule_appointment(
            booking=booking,
            start_time=start,
            end_time=end,
            actor=workshop_owner_user,
        )
        booking.refresh_from_db()
        assert booking.status == BookingStatusChoices.CONFIRMED

        # 2. Workshop creates and issues a quotation
        quote_payload = {
            'discount_amount': '0.00',
            'tax_rate_percent': '20.00',
            'valid_until': str(date.today() + timedelta(days=7)),
            'workshop_notes': 'MOT and brake inspection estimate',
            'line_items': [
                {
                    'item_type': 'LABOUR',
                    'description': 'Brake inspection and fluid service',
                    'quantity': '1.00',
                    'unit_price': '60.00',
                },
            ],
        }
        create_resp = owner_client.post(
            f'/api/v1/workshops/manage/bookings/{booking.id}/quotations/',
            quote_payload,
            format='json',
        )
        assert create_resp.status_code == status.HTTP_201_CREATED
        quote_id = create_resp.json()['id']

        issue_resp = owner_client.post(f'/api/v1/workshops/manage/quotations/{quote_id}/issue/')
        assert issue_resp.status_code == status.HTTP_200_OK

        # 3. Booking must now have status QUOTED (not stranded in CONFIRMED)
        booking.refresh_from_db()
        assert booking.status == BookingStatusChoices.QUOTED

        # 4. Buyer queries ?status=QUOTED and sees the booking with active_quotation
        buyer_list_resp = buyer_client.get('/api/v1/workshops/bookings/my/?status=QUOTED')
        assert buyer_list_resp.status_code == status.HTTP_200_OK
        results = buyer_list_resp.json()['results']
        assert len(results) == 1
        assert results[0]['id'] == str(booking.id)
        assert results[0]['active_quotation']['id'] == quote_id
        assert results[0]['active_quotation']['status'] == 'ISSUED'

        # 5. Buyer accepts the quotation -> status becomes CONFIRMED with WorkOrder
        accept_resp = buyer_client.post(f'/api/v1/workshops/quotations/{quote_id}/accept/')
        assert accept_resp.status_code == status.HTTP_200_OK
        assert accept_resp.json()['status'] == 'ACCEPTED'

        booking.refresh_from_db()
        assert booking.status == BookingStatusChoices.CONFIRMED
        assert hasattr(booking, 'work_order')
        assert booking.work_order is not None

    def test_buyer_quoted_filter_includes_confirmed_booking_with_issued_quotation(
        self, buyer_client, booking, workshop_owner_user
    ):
        """
        Verify that even if a legacy booking has status CONFIRMED in the database,
        the buyer query ?status=QUOTED retrieves it if an ISSUED quotation exists.
        """
        from apps.workshops.models import WorkshopQuotation, QuotationStatusChoices, QuotationLineItem, LineItemTypeChoices

        # Create issued quotation directly while keeping booking.status as CONFIRMED
        booking.status = BookingStatusChoices.CONFIRMED
        booking.save(update_fields=['status'])

        quote = WorkshopQuotation.objects.create(
            booking=booking,
            version=1,
            currency='GBP',
            tax_rate_percent=Decimal('0.00'),
            total_amount=Decimal('50.00'),
            status=QuotationStatusChoices.ISSUED,
            issued_at=timezone.now(),
        )
        QuotationLineItem.objects.create(
            quotation=quote,
            item_type=LineItemTypeChoices.LABOUR,
            description='Test diagnostic',
            quantity=Decimal('1.00'),
            unit_price=Decimal('50.00'),
            line_total=Decimal('50.00'),
        )

        resp = buyer_client.get('/api/v1/workshops/bookings/my/?status=QUOTED')
        assert resp.status_code == status.HTTP_200_OK
        found_ids = [b['id'] for b in resp.json()['results']]
        assert str(booking.id) in found_ids
        booking_data = next(b for b in resp.json()['results'] if b['id'] == str(booking.id))
        assert booking_data['active_quotation']['id'] == str(quote.id)
        assert booking_data['active_quotation']['status'] == 'ISSUED'


@pytest.mark.django_db
class TestAdminWorkshopOversight:
    """
    Comprehensive test suite for the Admin Workshop Operations Oversight endpoint:
    GET /api/v1/workshops/admin/bookings/

    Validates all 15 operational scenarios required by Section 9:
    1. All bookings list (?status=ALL or no status param).
    2. Requested booking filter (?status=REQUESTED).
    3. Accepted booking filter (?status=ACCEPTED).
    4. Confirmed booking filter (?status=CONFIRMED).
    5. Quoted booking filter (?status=QUOTED).
    6. Issued quotation visibility under quoted filter.
    7. Accepted quotation with confirmed booking visible under confirmed and all.
    8. Rejected (?status=REJECTED) and cancelled (?status=CANCELLED) filters.
    9. Work order serialization (number, status, technician, task count, nested object).
    10. Search by booking reference (?q=BK-...).
    11. Search by quotation reference (?q=QT-...).
    12. Search by work order reference (?q=WO-...).
    13. Duplicate prevention (.distinct()).
    14. Platform staff and superuser access (HTTP 200).
    15. Unauthorized user receives HTTP 403 Forbidden / 401 Unauthorized.
    """

    @pytest.fixture
    def oversight_data(self, workshop_profile, buyer_user, buyer_vehicle, workshop_tech_user):
        """
        Populate an explicit, realistic booking lifecycle dataset across all states.
        """
        from apps.workshops.services import WorkOrderService

        workshop_profile.organisation.add_member(workshop_tech_user, role=OrganisationRoleChoices.TECHNICIAN)

        # 1. REQUESTED
        b_req = WorkshopBooking.objects.create(
            workshop=workshop_profile,
            buyer=buyer_user,
            vehicle=buyer_vehicle,
            preferred_date=date.today() + timedelta(days=5),
            status=BookingStatusChoices.REQUESTED,
        )

        # 2. ACCEPTED (workshop accepted customer request)
        b_acc = WorkshopBooking.objects.create(
            workshop=workshop_profile,
            buyer=buyer_user,
            vehicle=buyer_vehicle,
            preferred_date=date.today() + timedelta(days=6),
            status=BookingStatusChoices.ACCEPTED,
        )

        # 3. CONFIRMED (scheduled appointment without quotation)
        b_conf = WorkshopBooking.objects.create(
            workshop=workshop_profile,
            buyer=buyer_user,
            vehicle=buyer_vehicle,
            preferred_date=date.today() + timedelta(days=7),
            status=BookingStatusChoices.CONFIRMED,
        )

        # 4. QUOTED (with an ISSUED quotation awaiting customer decision)
        b_quoted = WorkshopBooking.objects.create(
            workshop=workshop_profile,
            buyer=buyer_user,
            vehicle=buyer_vehicle,
            preferred_date=date.today() + timedelta(days=8),
            status=BookingStatusChoices.QUOTED,
        )
        quote_issued = WorkshopQuotation.objects.create(
            booking=b_quoted,
            version=1,
            currency='GBP',
            tax_rate_percent=Decimal('0.00'),
            total_amount=Decimal('120.00'),
            status=QuotationStatusChoices.ISSUED,
            issued_at=timezone.now(),
        )
        QuotationLineItem.objects.create(
            quotation=quote_issued,
            item_type=LineItemTypeChoices.LABOUR,
            description='Diagnostic and health check labour',
            quantity=Decimal('2.00'),
            unit_price=Decimal('60.00'),
            line_total=Decimal('120.00'),
        )

        # 5. CONFIRMED with an ACCEPTED quotation and generated WorkOrder
        b_wo = WorkshopBooking.objects.create(
            workshop=workshop_profile,
            buyer=buyer_user,
            vehicle=buyer_vehicle,
            preferred_date=date.today() + timedelta(days=9),
            status=BookingStatusChoices.CONFIRMED,
            assigned_technician=workshop_tech_user,
        )
        quote_accepted = WorkshopQuotation.objects.create(
            booking=b_wo,
            version=1,
            currency='GBP',
            tax_rate_percent=Decimal('0.00'),
            total_amount=Decimal('250.00'),
            status=QuotationStatusChoices.ISSUED,
            issued_at=timezone.now(),
        )
        QuotationLineItem.objects.create(
            quotation=quote_accepted,
            item_type=LineItemTypeChoices.LABOUR,
            description='Timing belt replacement',
            quantity=Decimal('3.00'),
            unit_price=Decimal('70.00'),
            line_total=Decimal('210.00'),
        )
        QuotationLineItem.objects.create(
            quotation=quote_accepted,
            item_type=LineItemTypeChoices.PART,
            description='Timing belt kit',
            quantity=Decimal('1.00'),
            unit_price=Decimal('40.00'),
            line_total=Decimal('40.00'),
        )
        quote_accepted.status = QuotationStatusChoices.ACCEPTED
        quote_accepted.accepted_at = timezone.now()
        quote_accepted.save(update_fields=['status', 'accepted_at'])
        work_order = WorkOrderService.create_work_order_for_booking(
            booking=b_wo,
            quotation=quote_accepted,
            actor=buyer_user,
        )

        # 6. REJECTED
        b_rej = WorkshopBooking.objects.create(
            workshop=workshop_profile,
            buyer=buyer_user,
            vehicle=buyer_vehicle,
            preferred_date=date.today() + timedelta(days=10),
            status=BookingStatusChoices.REJECTED,
            rejection_reason='No technician availability for commercial vans.',
        )

        # 7. CANCELLED
        b_canc = WorkshopBooking.objects.create(
            workshop=workshop_profile,
            buyer=buyer_user,
            vehicle=buyer_vehicle,
            preferred_date=date.today() + timedelta(days=11),
            status=BookingStatusChoices.CANCELLED,
            cancellation_reason='Customer cancelled appointment.',
        )

        return {
            'b_req': b_req,
            'b_acc': b_acc,
            'b_conf': b_conf,
            'b_quoted': b_quoted,
            'quote_issued': quote_issued,
            'b_wo': b_wo,
            'quote_accepted': quote_accepted,
            'work_order': work_order,
            'b_rej': b_rej,
            'b_canc': b_canc,
        }

    def test_admin_list_all_bookings_unfiltered(self, admin_client, oversight_data):
        resp = admin_client.get('/api/v1/workshops/admin/bookings/')
        assert resp.status_code == status.HTTP_200_OK
        results = resp.json()['results']
        retrieved_ids = {b['id'] for b in results}
        for key in ('b_req', 'b_acc', 'b_conf', 'b_quoted', 'b_wo', 'b_rej', 'b_canc'):
            assert str(oversight_data[key].id) in retrieved_ids

    def test_admin_list_all_bookings_explicit_status_all(self, admin_client, oversight_data):
        resp = admin_client.get('/api/v1/workshops/admin/bookings/?status=ALL')
        assert resp.status_code == status.HTTP_200_OK
        results = resp.json()['results']
        retrieved_ids = {b['id'] for b in results}
        for key in ('b_req', 'b_acc', 'b_conf', 'b_quoted', 'b_wo', 'b_rej', 'b_canc'):
            assert str(oversight_data[key].id) in retrieved_ids

    def test_admin_filter_requested_bookings(self, admin_client, oversight_data):
        resp = admin_client.get('/api/v1/workshops/admin/bookings/?status=REQUESTED')
        assert resp.status_code == status.HTTP_200_OK
        results = resp.json()['results']
        retrieved_ids = {b['id'] for b in results}
        assert str(oversight_data['b_req'].id) in retrieved_ids
        for b in results:
            assert b['status'] == 'REQUESTED'

    def test_admin_filter_accepted_bookings(self, admin_client, oversight_data):
        resp = admin_client.get('/api/v1/workshops/admin/bookings/?status=ACCEPTED')
        assert resp.status_code == status.HTTP_200_OK
        results = resp.json()['results']
        retrieved_ids = {b['id'] for b in results}
        assert str(oversight_data['b_acc'].id) in retrieved_ids
        assert str(oversight_data['b_wo'].id) not in retrieved_ids
        for b in results:
            assert b['status'] == 'ACCEPTED'

    def test_admin_filter_confirmed_bookings(self, admin_client, oversight_data):
        resp = admin_client.get('/api/v1/workshops/admin/bookings/?status=CONFIRMED')
        assert resp.status_code == status.HTTP_200_OK
        results = resp.json()['results']
        retrieved_ids = {b['id'] for b in results}
        assert str(oversight_data['b_conf'].id) in retrieved_ids
        assert str(oversight_data['b_wo'].id) in retrieved_ids
        for b in results:
            assert b['status'] == 'CONFIRMED'

    def test_admin_filter_quoted_bookings_includes_quoted_and_issued(self, admin_client, oversight_data):
        resp = admin_client.get('/api/v1/workshops/admin/bookings/?status=QUOTED')
        assert resp.status_code == status.HTTP_200_OK
        results = resp.json()['results']
        retrieved_ids = {b['id'] for b in results}
        assert str(oversight_data['b_quoted'].id) in retrieved_ids

    def test_admin_issued_quotation_visible_under_quoted_filter(self, admin_client, oversight_data):
        resp = admin_client.get('/api/v1/workshops/admin/bookings/?status=QUOTED')
        assert resp.status_code == status.HTTP_200_OK
        results = resp.json()['results']
        quoted_booking = next(b for b in results if b['id'] == str(oversight_data['b_quoted'].id))
        assert quoted_booking['active_quotation'] is not None
        assert quoted_booking['active_quotation']['quotation_number'] == oversight_data['quote_issued'].quotation_number
        assert quoted_booking['active_quotation']['status'] == 'ISSUED'

    def test_admin_accepted_quote_confirmed_booking_visibility(self, admin_client, oversight_data):
        # 1. Visible under CONFIRMED
        conf_resp = admin_client.get('/api/v1/workshops/admin/bookings/?status=CONFIRMED')
        conf_ids = {b['id'] for b in conf_resp.json()['results']}
        assert str(oversight_data['b_wo'].id) in conf_ids

        # 2. Visible under ALL
        all_resp = admin_client.get('/api/v1/workshops/admin/bookings/?status=ALL')
        all_ids = {b['id'] for b in all_resp.json()['results']}
        assert str(oversight_data['b_wo'].id) in all_ids

        # 3. NOT under ACCEPTED (booking acceptance is distinct from quotation acceptance)
        acc_resp = admin_client.get('/api/v1/workshops/admin/bookings/?status=ACCEPTED')
        acc_ids = {b['id'] for b in acc_resp.json()['results']}
        assert str(oversight_data['b_wo'].id) not in acc_ids

        # 4. NOT under QUOTED (it has already been accepted)
        quoted_resp = admin_client.get('/api/v1/workshops/admin/bookings/?status=QUOTED')
        quoted_ids = {b['id'] for b in quoted_resp.json()['results']}
        assert str(oversight_data['b_wo'].id) not in quoted_ids

    def test_admin_filter_rejected_and_cancelled_bookings(self, admin_client, oversight_data):
        rej_resp = admin_client.get('/api/v1/workshops/admin/bookings/?status=REJECTED')
        assert rej_resp.status_code == status.HTTP_200_OK
        rej_ids = {b['id'] for b in rej_resp.json()['results']}
        assert str(oversight_data['b_rej'].id) in rej_ids
        for b in rej_resp.json()['results']:
            assert b['status'] == 'REJECTED'

        canc_resp = admin_client.get('/api/v1/workshops/admin/bookings/?status=CANCELLED')
        assert canc_resp.status_code == status.HTTP_200_OK
        canc_ids = {b['id'] for b in canc_resp.json()['results']}
        assert str(oversight_data['b_canc'].id) in canc_ids
        for b in canc_resp.json()['results']:
            assert b['status'] == 'CANCELLED'

    def test_admin_work_order_serialization(self, admin_client, oversight_data):
        resp = admin_client.get('/api/v1/workshops/admin/bookings/?status=CONFIRMED')
        assert resp.status_code == status.HTTP_200_OK
        wo_booking = next(b for b in resp.json()['results'] if b['id'] == str(oversight_data['b_wo'].id))

        assert wo_booking['work_order_number'] == oversight_data['work_order'].work_order_number
        assert wo_booking['work_order_status'] == 'ASSIGNED'
        assert wo_booking['work_order_technician'] == 'Bob Spanner'
        assert wo_booking['work_order_tasks_count'] == 1
        assert wo_booking['work_order'] is not None
        assert wo_booking['work_order']['work_order_number'] == oversight_data['work_order'].work_order_number
        assert len(wo_booking['work_order']['tasks']) == 1
        assert wo_booking['work_order']['tasks'][0]['description'] == 'Timing belt replacement'

    def test_admin_search_by_booking_reference(self, admin_client, oversight_data):
        b_num = oversight_data['b_wo'].booking_number
        resp = admin_client.get(f'/api/v1/workshops/admin/bookings/?q={b_num}')
        assert resp.status_code == status.HTTP_200_OK
        results = resp.json()['results']
        assert len(results) == 1
        assert results[0]['id'] == str(oversight_data['b_wo'].id)
        assert results[0]['booking_number'] == b_num

    def test_admin_search_by_quotation_reference(self, admin_client, oversight_data):
        q_num = oversight_data['quote_accepted'].quotation_number
        resp = admin_client.get(f'/api/v1/workshops/admin/bookings/?q={q_num}')
        assert resp.status_code == status.HTTP_200_OK
        results = resp.json()['results']
        assert len(results) == 1
        assert results[0]['id'] == str(oversight_data['b_wo'].id)

    def test_admin_search_by_work_order_reference(self, admin_client, oversight_data):
        wo_num = oversight_data['work_order'].work_order_number
        resp = admin_client.get(f'/api/v1/workshops/admin/bookings/?q={wo_num}')
        assert resp.status_code == status.HTTP_200_OK
        results = resp.json()['results']
        assert len(results) == 1
        assert results[0]['id'] == str(oversight_data['b_wo'].id)

    def test_admin_search_distinct_prevents_duplicate_rows(self, admin_client, oversight_data):
        # Create additional quotation revision and work order task on b_wo
        WorkshopQuotation.objects.create(
            booking=oversight_data['b_wo'],
            version=2,
            currency='GBP',
            tax_rate_percent=Decimal('0.00'),
            total_amount=Decimal('300.00'),
            status=QuotationStatusChoices.SUPERSEDED,
        )
        WorkOrderTask.objects.create(
            work_order=oversight_data['work_order'],
            description='Additional coolant flush',
            estimated_labour_minutes=30,
            status=WorkOrderTaskStatusChoices.PENDING,
            order_index=1,
        )

        reg_plate = oversight_data['b_wo'].vehicle_registration_plate
        resp = admin_client.get(f'/api/v1/workshops/admin/bookings/?q={reg_plate}')
        assert resp.status_code == status.HTTP_200_OK
        results = resp.json()['results']
        matching_ids = [b['id'] for b in results if b['id'] == str(oversight_data['b_wo'].id)]
        assert len(matching_ids) == 1

    def test_admin_staff_and_superuser_access(self, admin_client, admin_auth_client, oversight_data):
        # Staff user access
        staff_resp = admin_client.get('/api/v1/workshops/admin/bookings/')
        assert staff_resp.status_code == status.HTTP_200_OK

        # Superuser access
        super_resp = admin_auth_client.get('/api/v1/workshops/admin/bookings/')
        assert super_resp.status_code == status.HTTP_200_OK

    def test_admin_unauthorized_user_forbidden(self, buyer_client, owner_client, api_client, oversight_data):
        # Buyer user forbidden
        buyer_resp = buyer_client.get('/api/v1/workshops/admin/bookings/')
        assert buyer_resp.status_code == status.HTTP_403_FORBIDDEN

        # Workshop owner user forbidden
        owner_resp = owner_client.get('/api/v1/workshops/admin/bookings/')
        assert owner_resp.status_code == status.HTTP_403_FORBIDDEN

        # Unauthenticated user unauthorized
        anon_resp = api_client.get('/api/v1/workshops/admin/bookings/')
        assert anon_resp.status_code == status.HTTP_401_UNAUTHORIZED


