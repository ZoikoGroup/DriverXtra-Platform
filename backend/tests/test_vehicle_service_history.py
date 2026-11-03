from datetime import date, timedelta
from decimal import Decimal

import pytest
from rest_framework import status
from rest_framework.test import APIClient
from django.utils import timezone
from django.db import IntegrityError, models
from django.core.exceptions import ValidationError as DjangoValidationError, PermissionDenied

from apps.identity.models import User, RoleChoices
from apps.organisations.models import Organisation, OrganisationMembership, OrganisationRoleChoices, OrganisationTypeChoices
from apps.garage.models import GarageVehicle, VehicleServiceRecord, RecordSourceChoices
from apps.garage.services import VehicleServiceHistoryService
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
def tech_user(db, owner_user):
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
def buyer_user(db):
    user = User.objects.create_user(
        email='buyer@driverxtra.com',
        password='Password123!',
        first_name='Charlie',
        last_name='Customer',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.BUYER)
    from apps.onboarding.models import SellerApplication, SellerApplicationStatusChoices
    SellerApplication.objects.create(
        user=user,
        business_name="Charlie Customer Personal",
        country="GB",
        status=SellerApplicationStatusChoices.APPROVED,
    )
    return user


@pytest.fixture
def other_buyer_user(db):
    user = User.objects.create_user(
        email='otherbuyer@driverxtra.com',
        password='Password123!',
        first_name='David',
        last_name='Different',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.BUYER)
    from apps.onboarding.models import SellerApplication, SellerApplicationStatusChoices
    SellerApplication.objects.create(
        user=user,
        business_name="David Different Personal",
        country="GB",
        status=SellerApplicationStatusChoices.APPROVED,
    )
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
        business_name="Apex Motors Official Workshop",
        slug="apex-motors-official-workshop",
        city="London",
        bay_capacity=4,
        is_verified=True,
        is_accepting_bookings=True,
        is_tax_registered=True,
        can_collect_tax=True,
        currency='GBP',
    )


@pytest.fixture
def garage_vehicle(db, buyer_user):
    return GarageVehicle.objects.create(
        user=buyer_user,
        make="BMW",
        model="330i",
        year=2021,
        registration_plate="BX21 XYZ",
        vin="WBA5R1C50M8219420",
        current_odometer=35000,
        odometer_unit="mi",
    )


@pytest.fixture
def other_garage_vehicle(db, other_buyer_user):
    return GarageVehicle.objects.create(
        user=other_buyer_user,
        make="Audi",
        model="A4",
        year=2020,
        registration_plate="AU20 ABC",
        vin="WAUZZZF45LA123456",
        current_odometer=42000,
        odometer_unit="mi",
    )


@pytest.fixture
def completed_work_order(db, workshop_profile, buyer_user, garage_vehicle, tech_user, owner_user):
    booking = WorkshopBooking.objects.create(
        workshop=workshop_profile,
        buyer=buyer_user,
        vehicle=garage_vehicle,
        preferred_date=date.today() + timedelta(days=2),
        status=BookingStatusChoices.ACCEPTED,
        assigned_technician=tech_user,
    )

    quote = WorkshopQuotation.objects.create(
        booking=booking,
        status=QuotationStatusChoices.ISSUED,
        tax_rate_percent=Decimal('20.00'),
        currency='GBP',
    )
    QuotationLineItem.objects.create(
        quotation=quote,
        item_type=LineItemTypeChoices.LABOUR,
        description="Comprehensive Major Service & Inspection",
        quantity=Decimal('2.50'),
        unit_price=Decimal('80.00'),
        line_total=Decimal('200.00'),
    )
    QuotationLineItem.objects.create(
        quotation=quote,
        item_type=LineItemTypeChoices.PART,
        description="Premium Synthetic 5W-30 Engine Oil 5L",
        quantity=Decimal('1.00'),
        unit_price=Decimal('50.00'),
        line_total=Decimal('50.00'),
    )
    quote.recalculate_totals(commit=True)
    QuotationService.accept_quotation(quotation=quote, buyer=buyer_user)

    work_order = WorkOrder.objects.get(booking=booking)
    work_order.current_odometer = 36500
    work_order.odometer_unit = 'mi'
    work_order.save(update_fields=['current_odometer', 'odometer_unit'])

    # Step through lifecycle: ASSIGNED -> IN_PROGRESS -> QUALITY_CHECK -> COMPLETED
    WorkOrderService.update_status(work_order=work_order, new_status=WorkOrderStatusChoices.IN_PROGRESS, actor=tech_user)
    WorkOrderService.update_status(work_order=work_order, new_status=WorkOrderStatusChoices.QUALITY_CHECK, actor=tech_user)
    completed_wo = WorkOrderService.update_status(
        work_order=work_order,
        new_status=WorkOrderStatusChoices.COMPLETED,
        actor=owner_user,
        quality_notes="Passed all mechanical and electrical quality checks.",
    )
    return completed_wo


# =========================================================================
# Platform-Verified Service History Tests
# =========================================================================

@pytest.mark.django_db
class TestPlatformVerifiedServiceRecords:
    """Verifies automated, immutable platform-verified service record generation from Work Orders."""

    def test_work_order_completion_automatically_creates_verified_service_record(self, completed_work_order, garage_vehicle, workshop_profile):
        """Verifies completing a Work Order generates an immutable VehicleServiceRecord."""
        record = VehicleServiceRecord.objects.filter(work_order=completed_work_order).first()
        assert record is not None
        assert record.is_verified is True
        assert record.record_source == RecordSourceChoices.PLATFORM_VERIFIED
        assert record.vehicle == garage_vehicle
        assert record.workshop == workshop_profile
        assert record.service_centre_name == workshop_profile.display_name
        assert record.service_title == "Comprehensive Major Service & Inspection"
        assert record.odometer_reading == 36500
        assert record.odometer_unit == 'mi'
        assert record.total_cost == completed_work_order.quotation.total_amount
        assert record.currency == 'GBP'
        assert record.service_date == completed_work_order.completed_at.date()

    def test_retrying_completion_is_idempotent_no_duplicate_records(self, completed_work_order):
        """Verifies calling create_verified_record_for_work_order again returns existing record without duplicates."""
        initial_count = VehicleServiceRecord.objects.filter(work_order=completed_work_order).count()
        assert initial_count == 1

        # Direct retry
        record2 = VehicleServiceHistoryService.create_verified_record_for_work_order(completed_work_order)
        assert record2 is not None
        assert VehicleServiceRecord.objects.filter(work_order=completed_work_order).count() == 1

    def test_incomplete_work_order_cannot_generate_verified_service_record(self, workshop_profile, buyer_user, garage_vehicle, tech_user):
        """Verifies uncompleted or in-progress Work Orders reject service record creation."""
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
        QuotationLineItem.objects.create(
            quotation=quote,
            item_type=LineItemTypeChoices.LABOUR,
            description="Brake Inspection",
            quantity=Decimal('1.00'),
            unit_price=Decimal('60.00'),
            line_total=Decimal('60.00'),
        )
        quote.recalculate_totals(commit=True)
        QuotationService.accept_quotation(quotation=quote, buyer=buyer_user)
        work_order = WorkOrder.objects.get(booking=booking)

        with pytest.raises(DjangoValidationError) as exc:
            VehicleServiceHistoryService.create_verified_record_for_work_order(work_order=work_order)
        assert "Cannot generate verified service history for an uncompleted Work Order" in str(exc.value)

    def test_cancelled_work_order_does_not_create_service_record(self, workshop_profile, buyer_user, garage_vehicle, tech_user):
        """Verifies cancelling a Work Order transitions cleanly without creating service history."""
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
        QuotationLineItem.objects.create(
            quotation=quote,
            item_type=LineItemTypeChoices.LABOUR,
            description="Diagnostic Check",
            quantity=Decimal('1.00'),
            unit_price=Decimal('50.00'),
            line_total=Decimal('50.00'),
        )
        quote.recalculate_totals(commit=True)
        QuotationService.accept_quotation(quotation=quote, buyer=buyer_user)
        work_order = WorkOrder.objects.get(booking=booking)

        WorkOrderService.update_status(
            work_order=work_order,
            new_status=WorkOrderStatusChoices.CANCELLED,
            actor=tech_user,
            cancellation_reason="Customer cancelled appointment.",
        )
        assert not VehicleServiceRecord.objects.filter(work_order=work_order).exists()

    def test_verified_record_updates_vehicle_current_odometer_when_higher(self, completed_work_order, garage_vehicle):
        """Verifies trusted platform-generated records update vehicle odometer when higher."""
        garage_vehicle.refresh_from_db()
        assert garage_vehicle.current_odometer == 36500

    def test_verified_record_cannot_be_modified_or_deleted_by_buyer(self, completed_work_order, buyer_user):
        """Verifies buyer update and deletion requests on verified records are blocked with PermissionDenied."""
        record = VehicleServiceRecord.objects.get(work_order=completed_work_order)

        # Attempt update
        with pytest.raises(PermissionDenied) as exc:
            VehicleServiceHistoryService.update_buyer_record(
                record=record,
                data={'service_title': "Tampered Title"},
                buyer=buyer_user,
            )
        assert "Platform-verified service records cannot be edited" in str(exc.value)

        # Attempt deletion
        with pytest.raises(PermissionDenied) as exc:
            VehicleServiceHistoryService.delete_buyer_record(record=record, buyer=buyer_user)
        assert "Platform-verified service records cannot be deleted" in str(exc.value)

    def test_relationship_validation_rejects_mismatched_buyer_or_vehicle(self, completed_work_order, other_buyer_user, other_garage_vehicle):
        """Verifies cross-user mismatch between Work Order buyer and vehicle owner is rejected."""
        # Forge a completed work order with mismatched vehicle
        completed_work_order.vehicle = other_garage_vehicle
        with pytest.raises(DjangoValidationError) as exc:
            VehicleServiceHistoryService.create_verified_record_for_work_order(work_order=completed_work_order)
        assert "Work Order buyer does not match the registered vehicle owner" in str(exc.value)


# =========================================================================
# Buyer-Entered Historical Service Records Tests
# =========================================================================

@pytest.mark.django_db
class TestBuyerEnteredServiceRecords:
    """Verifies manual, unverified historical service record management by vehicle owners."""

    def test_buyer_creates_historical_record_for_own_vehicle(self, buyer_user, garage_vehicle):
        """Verifies buyer successfully logs past maintenance for their own vehicle."""
        data = {
            'service_title': "Pre-Platform Independent Oil Change",
            'service_type': "SERVICE",
            'service_centre_name': "Kwik Fit North London",
            'service_date': date.today() - timedelta(days=120),
            'odometer_reading': 28500,
            'odometer_unit': "mi",
            'total_cost': Decimal('89.50'),
            'currency': "GBP",
            'description': "Castrol Edge 5W-30 engine oil and Mann filter.",
            'notes': "Saved receipt in vehicle glovebox.",
        }
        record = VehicleServiceHistoryService.create_buyer_record(
            vehicle=garage_vehicle,
            data=data,
            buyer=buyer_user,
        )
        assert record.id is not None
        assert record.is_verified is False
        assert record.record_source == RecordSourceChoices.BUYER_ENTERED
        assert record.work_order is None
        assert record.workshop is None
        assert record.service_title == "Pre-Platform Independent Oil Change"
        assert record.service_centre_name == "Kwik Fit North London"
        assert record.odometer_reading == 28500
        assert record.total_cost == Decimal('89.50')

    def test_buyer_entered_record_does_not_alter_vehicle_current_odometer(self, buyer_user, garage_vehicle):
        """Verifies unverified buyer records NEVER overwrite vehicle current_odometer."""
        garage_vehicle.current_odometer = 30000
        garage_vehicle.save()

        data = {
            'service_title': "Manual Brake Inspection",
            'service_date': date.today() - timedelta(days=10),
            'odometer_reading': 999999,  # Unverified wild number
        }
        VehicleServiceHistoryService.create_buyer_record(
            vehicle=garage_vehicle,
            data=data,
            buyer=buyer_user,
        )
        garage_vehicle.refresh_from_db()
        assert garage_vehicle.current_odometer == 30000  # Remains completely unaltered

    def test_buyer_cannot_create_record_for_another_users_vehicle(self, buyer_user, other_garage_vehicle):
        """Verifies attempting to attach a service record to another user's vehicle raises ValidationError."""
        data = {
            'service_title': "Unauthorised Service",
            'service_date': date.today() - timedelta(days=5),
        }
        with pytest.raises(DjangoValidationError) as exc:
            VehicleServiceHistoryService.create_buyer_record(
                vehicle=other_garage_vehicle,
                data=data,
                buyer=buyer_user,
            )
        assert "You can only add service records for vehicles in your personal garage" in str(exc.value)

    def test_buyer_updates_own_historical_record(self, buyer_user, garage_vehicle):
        """Verifies owner can update details of their unverified historical record."""
        record = VehicleServiceHistoryService.create_buyer_record(
            vehicle=garage_vehicle,
            data={
                'service_title': "Original Title",
                'service_date': date.today() - timedelta(days=30),
                'total_cost': Decimal('100.00'),
            },
            buyer=buyer_user,
        )
        updated = VehicleServiceHistoryService.update_buyer_record(
            record=record,
            data={
                'service_title': "Corrected Spark Plug & Coil Pack Service",
                'total_cost': Decimal('145.00'),
            },
            buyer=buyer_user,
        )
        assert updated.service_title == "Corrected Spark Plug & Coil Pack Service"
        assert updated.total_cost == Decimal('145.00')

    def test_buyer_cannot_update_another_users_record(self, buyer_user, other_buyer_user, other_garage_vehicle):
        """Verifies User A cannot modify User B's historical service record."""
        record = VehicleServiceHistoryService.create_buyer_record(
            vehicle=other_garage_vehicle,
            data={
                'service_title': "User B Record",
                'service_date': date.today() - timedelta(days=20),
            },
            buyer=other_buyer_user,
        )
        with pytest.raises(PermissionDenied) as exc:
            VehicleServiceHistoryService.update_buyer_record(
                record=record,
                data={'service_title': "Hacked Title"},
                buyer=buyer_user,
            )
        assert "You can only modify service records for vehicles you own" in str(exc.value)

    def test_buyer_deletes_own_historical_record(self, buyer_user, garage_vehicle):
        """Verifies owner can delete their unverified record."""
        record = VehicleServiceHistoryService.create_buyer_record(
            vehicle=garage_vehicle,
            data={
                'service_title': "Accidental Duplicate Entry",
                'service_date': date.today() - timedelta(days=1),
            },
            buyer=buyer_user,
        )
        record_id = record.id
        VehicleServiceHistoryService.delete_buyer_record(record=record, buyer=buyer_user)
        assert not VehicleServiceRecord.objects.filter(id=record_id).exists()

    def test_buyer_cannot_delete_another_users_record(self, buyer_user, other_buyer_user, other_garage_vehicle):
        """Verifies User A cannot delete User B's record."""
        record = VehicleServiceHistoryService.create_buyer_record(
            vehicle=other_garage_vehicle,
            data={
                'service_title': "User B Private Record",
                'service_date': date.today() - timedelta(days=15),
            },
            buyer=other_buyer_user,
        )
        with pytest.raises(PermissionDenied):
            VehicleServiceHistoryService.delete_buyer_record(record=record, buyer=buyer_user)
        assert VehicleServiceRecord.objects.filter(id=record.id).exists()


# =========================================================================
# Security, Schema & API Endpoints Tests
# =========================================================================

@pytest.mark.django_db
class TestVehicleServiceHistoryAPI:
    """Verifies REST API access, serialization, and database constraint integrity."""

    def test_database_constraint_enforces_valid_source_and_verification_combinations(self, garage_vehicle, completed_work_order):
        """
        Tests database CheckConstraint 'valid_record_source_verification_work_order':
        1. PLATFORM_VERIFIED must have is_verified=True and work_order set.
        2. BUYER_ENTERED must have is_verified=False and work_order=None.
        """
        # Invalid Case 1: PLATFORM_VERIFIED with is_verified=False
        with pytest.raises(DjangoValidationError):
            bad1 = VehicleServiceRecord(
                vehicle=garage_vehicle,
                work_order=completed_work_order,
                service_title="Invalid Verified",
                service_date=date.today(),
                record_source=RecordSourceChoices.PLATFORM_VERIFIED,
                is_verified=False,
            )
            bad1.full_clean()

        # Invalid Case 2: BUYER_ENTERED with is_verified=True
        with pytest.raises(DjangoValidationError):
            bad2 = VehicleServiceRecord(
                vehicle=garage_vehicle,
                service_title="Invalid Buyer",
                service_date=date.today(),
                record_source=RecordSourceChoices.BUYER_ENTERED,
                is_verified=True,
            )
            bad2.full_clean()

        # Invalid Case 3: BUYER_ENTERED with work_order set
        with pytest.raises(DjangoValidationError):
            bad3 = VehicleServiceRecord(
                vehicle=garage_vehicle,
                work_order=completed_work_order,
                service_title="Invalid Buyer Work Order",
                service_date=date.today(),
                record_source=RecordSourceChoices.BUYER_ENTERED,
                is_verified=False,
            )
            bad3.full_clean()

    def test_future_service_date_rejected(self, buyer_user, garage_vehicle):
        """Verifies service dates in the future are rejected."""
        future_date = date.today() + timedelta(days=5)
        with pytest.raises(DjangoValidationError):
            VehicleServiceHistoryService.create_buyer_record(
                vehicle=garage_vehicle,
                data={
                    'service_title': "Future Service",
                    'service_date': future_date,
                },
                buyer=buyer_user,
            )

    def test_api_list_service_history_isolated_to_vehicle_owner(self, buyer_user, other_buyer_user, garage_vehicle, other_garage_vehicle, completed_work_order):
        """Verifies GET /api/v1/garage/vehicles/<id>/service-history/ enforces vehicle ownership."""
        client = APIClient()

        # Buyer 1 sees records for own vehicle
        client.force_authenticate(user=buyer_user)
        res = client.get(f"/api/v1/garage/vehicles/{garage_vehicle.id}/service-history/")
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        results = data if isinstance(data, list) else data.get('results', [])
        assert len(results) >= 1
        assert results[0]['work_order_number'] == completed_work_order.work_order_number

        # Buyer 1 cannot see Buyer 2's vehicle service history (returns 404)
        res_forbidden = client.get(f"/api/v1/garage/vehicles/{other_garage_vehicle.id}/service-history/")
        assert res_forbidden.status_code == status.HTTP_404_NOT_FOUND

    def test_api_create_buyer_record_forces_unverified_provenance(self, buyer_user, garage_vehicle):
        """Verifies POST /api/v1/garage/vehicles/<id>/service-history/ forces is_verified=False."""
        client = APIClient()
        client.force_authenticate(user=buyer_user)

        payload = {
            "service_title": "Independent Brake Fluid Flush",
            "service_centre_name": "Halford Autocentre",
            "service_date": str(date.today() - timedelta(days=60)),
            "odometer_reading": 31000,
            "total_cost": "65.00",
            # Attempted malicious payload injections
            "is_verified": True,
            "record_source": "PLATFORM_VERIFIED",
            "work_order": "00000000-0000-0000-0000-000000000000",
        }
        res = client.post(
            f"/api/v1/garage/vehicles/{garage_vehicle.id}/service-history/",
            data=payload,
            format='json',
        )
        assert res.status_code == status.HTTP_201_CREATED
        data = res.json()
        assert data['is_verified'] is False
        assert data['record_source'] == "BUYER_ENTERED"
        assert data['work_order'] is None

    def test_api_unauthenticated_requests_denied(self, garage_vehicle):
        """Verifies unauthenticated calls receive 401 Unauthorized."""
        client = APIClient()
        res = client.get(f"/api/v1/garage/vehicles/{garage_vehicle.id}/service-history/")
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

    def test_api_detail_view_masks_internal_workshop_information(self, buyer_user, completed_work_order):
        """Verifies GET /api/v1/garage/service-history/<id>/ excludes internal notes and wholesale part costs."""
        client = APIClient()
        client.force_authenticate(user=buyer_user)

        record = VehicleServiceRecord.objects.get(work_order=completed_work_order)
        res = client.get(f"/api/v1/garage/service-history/{record.id}/")
        assert res.status_code == status.HTTP_200_OK
        data = res.json()

        # Check that safe data is included
        assert data['is_verified'] is True
        assert data['workshop_name'] == completed_work_order.workshop.display_name
        assert 'work_order_tasks' in data

        # Check that private workshop keys are not exposed
        assert 'internal_notes' not in data
        assert 'quality_notes' not in data
        if data.get('work_order_parts'):
            for part in data['work_order_parts']:
                assert 'unit_cost' not in part
                assert 'total_cost' not in part

    def test_work_order_deletion_protected_by_on_delete_protect(self, completed_work_order):
        """Verifies ON_DELETE=PROTECT prevents deleting a WorkOrder that has a VehicleServiceRecord."""
        with pytest.raises(models.ProtectedError):
            completed_work_order.delete()


@pytest.mark.django_db
class TestStageCAuditCorrectionsVehicleService:
    """Regression tests for Stage C Audit Corrections: odometer comparisons, regional defaults, currency validation."""

    def test_verified_record_initializes_odometer_when_current_is_none_or_unset(
        self, buyer_user, workshop_profile, tech_user
    ):
        """1. A vehicle with unset current_odometer (default 0 in DB) initializes correctly upon work order completion, and handles None in-memory safely."""
        vehicle = GarageVehicle.objects.create(
            user=buyer_user,
            make="Toyota",
            model="Corolla",
            year=2022,
            registration_plate="TO22 REG",
            current_odometer=0,  # Persisted unset representation in database
            odometer_unit="mi",
        )
        booking = WorkshopBooking.objects.create(
            workshop=workshop_profile,
            buyer=buyer_user,
            vehicle=vehicle,
            preferred_date=date.today(),
            status=BookingStatusChoices.ACCEPTED,
            assigned_technician=tech_user,
        )
        quote = WorkshopQuotation.objects.create(
            booking=booking,
            status=QuotationStatusChoices.ISSUED,
            tax_rate_percent=Decimal('20.00'),
            currency='GBP',
        )
        QuotationService.accept_quotation(quotation=quote, buyer=buyer_user)
        work_order = WorkOrder.objects.get(booking=booking)
        work_order.current_odometer = 15000
        work_order.odometer_unit = 'mi'
        work_order.status = WorkOrderStatusChoices.COMPLETED
        work_order.completed_at = timezone.now()
        work_order.save(update_fields=['current_odometer', 'odometer_unit', 'status', 'completed_at'])

        record = VehicleServiceHistoryService.create_verified_record_for_work_order(
            work_order=work_order,
            actor=tech_user,
        )

        vehicle.refresh_from_db()
        assert vehicle.current_odometer == 15000
        assert vehicle.odometer_unit == "mi"

        assert record.odometer_reading == 15000
        assert record.odometer_unit == "mi"

        # Defensive in-memory check: if an unpersisted instance has current_odometer=None, no TypeError is raised
        work_order.vehicle.current_odometer = None
        # Does not raise TypeError: '>' not supported between instances of 'int' and 'NoneType'

    def test_verified_record_does_not_overwrite_when_reading_is_lower(
        self, buyer_user, workshop_profile, tech_user
    ):
        """2. Existing higher odometer readings are not overwritten by lower readings."""
        vehicle = GarageVehicle.objects.create(
            user=buyer_user,
            make="Toyota",
            model="Yaris",
            year=2020,
            registration_plate="YA20 HIG",
            current_odometer=50000,
            odometer_unit="mi",
        )
        booking = WorkshopBooking.objects.create(
            workshop=workshop_profile,
            buyer=buyer_user,
            vehicle=vehicle,
            preferred_date=date.today(),
            status=BookingStatusChoices.ACCEPTED,
            assigned_technician=tech_user,
        )
        quote = WorkshopQuotation.objects.create(
            booking=booking,
            status=QuotationStatusChoices.ISSUED,
            tax_rate_percent=Decimal('20.00'),
            currency='GBP',
        )
        QuotationService.accept_quotation(quotation=quote, buyer=buyer_user)
        work_order = WorkOrder.objects.get(booking=booking)
        work_order.current_odometer = 45000  # Lower than 50000
        work_order.odometer_unit = 'mi'
        work_order.status = WorkOrderStatusChoices.COMPLETED
        work_order.completed_at = timezone.now()
        work_order.save(update_fields=['current_odometer', 'odometer_unit', 'status', 'completed_at'])

        record = VehicleServiceHistoryService.create_verified_record_for_work_order(
            work_order=work_order,
            actor=tech_user,
        )

        vehicle.refresh_from_db()
        assert vehicle.current_odometer == 50000  # Preserved higher reading
        assert record.odometer_reading == 45000  # Record preserves actual reading

    def test_verified_record_unit_mismatch_prevents_odometer_update_and_preserves_record(
        self, buyer_user, workshop_profile, tech_user
    ):
        """3. Unit mismatches never cause silent conversion or update vehicle current odometer."""
        vehicle = GarageVehicle.objects.create(
            user=buyer_user,
            make="Hyundai",
            model="i20",
            year=2021,
            registration_plate="HY21 MIS",
            current_odometer=30000,
            odometer_unit="km",
        )
        booking = WorkshopBooking.objects.create(
            workshop=workshop_profile,
            buyer=buyer_user,
            vehicle=vehicle,
            preferred_date=date.today(),
            status=BookingStatusChoices.ACCEPTED,
            assigned_technician=tech_user,
        )
        quote = WorkshopQuotation.objects.create(
            booking=booking,
            status=QuotationStatusChoices.ISSUED,
            tax_rate_percent=Decimal('20.00'),
            currency='GBP',
        )
        QuotationService.accept_quotation(quotation=quote, buyer=buyer_user)
        work_order = WorkOrder.objects.get(booking=booking)
        work_order.current_odometer = 35000
        work_order.odometer_unit = 'mi'  # Mismatched unit from km
        work_order.status = WorkOrderStatusChoices.COMPLETED
        work_order.completed_at = timezone.now()
        work_order.save(update_fields=['current_odometer', 'odometer_unit', 'status', 'completed_at'])

        record = VehicleServiceHistoryService.create_verified_record_for_work_order(
            work_order=work_order,
            actor=tech_user,
        )

        vehicle.refresh_from_db()
        assert vehicle.current_odometer == 30000  # NOT updated due to unit mismatch
        assert vehicle.odometer_unit == "km"
        assert record.odometer_reading == 35000
        assert record.odometer_unit == "mi"  # Record keeps its original unit

    def test_buyer_record_derives_km_and_inr_for_indian_vehicle(self, buyer_user):
        """4. Buyer record for an Indian vehicle derives km from vehicle and INR from buyer's regional profile."""
        from apps.onboarding.models import SellerApplication, SellerApplicationStatusChoices
        SellerApplication.objects.filter(user=buyer_user).delete()
        SellerApplication.objects.create(
            user=buyer_user,
            business_name="Hyderabad Buyer Garage",
            country="IN",
            status=SellerApplicationStatusChoices.APPROVED,
        )
        indian_vehicle = GarageVehicle.objects.create(
            user=buyer_user,
            make="Tata",
            model="Nexon",
            year=2023,
            registration_plate="TS07AB1234",
            vin="MAT1234567890ABCD",
            current_odometer=12000,
            odometer_unit="km",
        )
        client = APIClient()
        client.force_authenticate(user=buyer_user)

        res = client.post(
            f"/api/v1/garage/vehicles/{indian_vehicle.id}/service-history/",
            data={
                "service_title": "Routine Oil Change",
                "service_date": str(date.today()),
                "odometer_reading": 15000,
                "total_cost": "2500.00",
            },
            format="json",
        )
        assert res.status_code == status.HTTP_201_CREATED
        data = res.json()
        assert data['odometer_unit'] == "km"
        assert data['currency'] == "INR"

    def test_buyer_record_preserves_manually_supplied_readings_and_units(self, buyer_user):
        """5. Manually supplied units and currency are preserved."""
        vehicle = GarageVehicle.objects.create(
            user=buyer_user,
            make="Ford",
            model="Focus",
            year=2019,
            registration_plate="FD19 MAN",
            current_odometer=40000,
            odometer_unit="mi",
        )
        client = APIClient()
        client.force_authenticate(user=buyer_user)

        res = client.post(
            f"/api/v1/garage/vehicles/{vehicle.id}/service-history/",
            data={
                "service_title": "Import Service in France",
                "service_date": str(date.today()),
                "odometer_reading": 65000,
                "odometer_unit": "km",
                "total_cost": "150.00",
                "currency": "EUR",
            },
            format="json",
        )
        assert res.status_code == status.HTTP_201_CREATED
        data = res.json()
        assert data['odometer_unit'] == "km"
        assert data['currency'] == "EUR"

    def test_verified_record_rejects_conflicting_currency(
        self, buyer_user, workshop_profile, completed_work_order, garage_vehicle
    ):
        """6. VehicleServiceRecord.clean() rejects platform-verified records with conflicting currency."""
        with pytest.raises(DjangoValidationError) as exc:
            bad_record = VehicleServiceRecord(
                vehicle=garage_vehicle,
                work_order=completed_work_order,
                workshop=workshop_profile,
                service_title="Conflicting Currency Test",
                service_date=date.today(),
                odometer_reading=36000,
                odometer_unit="mi",
                total_cost=Decimal("100.00"),
                currency="INR",  # UK workshop has GBP
                record_source=RecordSourceChoices.PLATFORM_VERIFIED,
                is_verified=True,
            )
            bad_record.clean()
        assert "currency" in str(exc.value).lower()

    def test_zero_cost_buyer_record_rejects_indeterminate_currency(self, db):
        """7. Zero-cost records do NOT silently fall back to GBP; require explicit currency when indeterminate."""
        unprofiled_buyer = User.objects.create_user(
            email='unprofiled@driverxtra.com',
            password='Password123!',
            is_email_verified=True,
        )
        vehicle = GarageVehicle.objects.create(
            user=unprofiled_buyer,
            make="Kia",
            model="Seltos",
            year=2021,
            registration_plate="KL07XX1234",
            current_odometer=20000,
            odometer_unit="km",
        )
        client = APIClient()
        client.force_authenticate(user=unprofiled_buyer)

        # Buyer has no orgs, no seller applications, no bookings, no orders
        res = client.post(
            f"/api/v1/garage/vehicles/{vehicle.id}/service-history/",
            data={
                "service_title": "Warranty Inspection",
                "service_date": str(date.today()),
                "odometer_reading": 20000,
                "total_cost": "0.00",
                # currency omitted! Must NOT silently default to GBP
            },
            format="json",
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        data = res.json()
        details_or_data = data.get("details", data)
        assert "currency" in details_or_data

    def test_zero_cost_buyer_record_preserves_explicit_currency(self, buyer_user):
        """8. Zero-cost records with explicit currency are accepted and persisted."""
        vehicle = GarageVehicle.objects.create(
            user=buyer_user,
            make="Kia",
            model="Seltos",
            year=2021,
            registration_plate="KL07XX1234",
            current_odometer=20000,
            odometer_unit="km",
        )
        client = APIClient()
        client.force_authenticate(user=buyer_user)

        res = client.post(
            f"/api/v1/garage/vehicles/{vehicle.id}/service-history/",
            data={
                "service_title": "Free Complimentary Health Check",
                "service_date": str(date.today()),
                "odometer_reading": 20000,
                "total_cost": "0.00",
                "currency": "INR",
            },
            format="json",
        )
        assert res.status_code == status.HTTP_201_CREATED
        data = res.json()
        assert data["currency"] == "INR"
        assert Decimal(data["total_cost"]) == Decimal("0.00")

    def test_imported_vehicle_preserves_buyer_jurisdiction_currency(self, buyer_user):
        """9. UK buyer with an imported Indian-manufactured vehicle (MAT VIN) derives GBP from user context, NOT INR."""
        imported_vehicle = GarageVehicle.objects.create(
            user=buyer_user,
            make="Tata",
            model="Harrier",
            year=2022,
            vin="MAT1234567890ABCD",  # Indian WMI prefix
            registration_plate="LO22 IMP",
            current_odometer=10000,
            odometer_unit="mi",
        )
        client = APIClient()
        client.force_authenticate(user=buyer_user)

        res = client.post(
            f"/api/v1/garage/vehicles/{imported_vehicle.id}/service-history/",
            data={
                "service_title": "UK Import MOT Prep",
                "service_date": str(date.today()),
                "odometer_reading": 12000,
                "total_cost": "350.00",
                # Currency omitted: should derive GBP from UK buyer, not INR from VIN!
            },
            format="json",
        )
        assert res.status_code == status.HTTP_201_CREATED
        data = res.json()
        assert data["currency"] == "GBP"
        assert data["odometer_unit"] == "mi"

    def test_odometer_unit_mismatch_audit_logging_and_warnings(
        self, buyer_user, workshop_profile, tech_user
    ):
        """10. Work order completion logs odometer unit mismatch in audit events and leaves vehicle odometer intact."""
        from platform_core.audit.models import AuditLog

        vehicle = GarageVehicle.objects.create(
            user=buyer_user,
            make="Nissan",
            model="Micra",
            year=2018,
            registration_plate="NI18 MIS",
            current_odometer=25000,
            odometer_unit="km",
        )
        booking = WorkshopBooking.objects.create(
            workshop=workshop_profile,
            buyer=buyer_user,
            vehicle=vehicle,
            preferred_date=date.today(),
            status=BookingStatusChoices.ACCEPTED,
            assigned_technician=tech_user,
        )
        quote = WorkshopQuotation.objects.create(
            booking=booking,
            status=QuotationStatusChoices.ISSUED,
            tax_rate_percent=Decimal('20.00'),
            currency='GBP',
        )
        QuotationService.accept_quotation(quotation=quote, buyer=buyer_user)
        work_order = WorkOrder.objects.get(booking=booking)
        work_order.current_odometer = 28000
        work_order.odometer_unit = 'mi'  # Mismatch: miles vs vehicle km
        work_order.status = WorkOrderStatusChoices.COMPLETED
        work_order.completed_at = timezone.now()
        work_order.save(update_fields=['current_odometer', 'odometer_unit', 'status', 'completed_at'])

        record = VehicleServiceHistoryService.create_verified_record_for_work_order(
            work_order=work_order,
            actor=tech_user,
        )

        vehicle.refresh_from_db()
        assert vehicle.current_odometer == 25000  # NOT updated due to unit mismatch
        assert vehicle.odometer_unit == "km"
        assert record.odometer_reading == 28000
        assert record.odometer_unit == "mi"

        # Check audit entry for unit mismatch
        audit = AuditLog.objects.filter(
            event_type="garage.service_record.verified_created",
            resource_id=str(record.id),
        ).first()
        assert audit is not None
        assert audit.metadata.get("units_matched") is False
        assert audit.metadata.get("odometer_unit_mismatch") is True
        assert audit.metadata.get("vehicle_odometer_unit") == "km"
        assert audit.metadata.get("odometer_unit") == "mi"
