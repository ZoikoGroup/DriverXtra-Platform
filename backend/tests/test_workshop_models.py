from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from apps.identity.models import User, RoleChoices
from apps.organisations.models import Organisation, OrganisationTypeChoices
from apps.garage.models import GarageVehicle
from apps.catalogue.models import Part, PartCategory
from apps.workshops.models import (
    WorkshopProfile,
    WorkshopOperatingHours,
    WorkshopServiceCategory,
    WorkshopService,
    WorkshopBooking,
    BookingServiceItem,
    WorkshopQuotation,
    QuotationLineItem,
    DayOfWeekChoices,
    BookingStatusChoices,
    QuotationStatusChoices,
    LineItemTypeChoices,
)


@pytest.fixture
def workshop_org(db, workshop_user):
    return Organisation.objects.create(
        name="AutoTech Precision Workshop",
        type=OrganisationTypeChoices.WORKSHOP,
        created_by=workshop_user,
    )


@pytest.fixture
def dealer_org(db, seller_user):
    return Organisation.objects.create(
        name="Apex Motors Dealership",
        type=OrganisationTypeChoices.DEALER_GROUP,
        created_by=seller_user,
    )


@pytest.fixture
def workshop_profile(db, workshop_org):
    return WorkshopProfile.objects.create(
        organisation=workshop_org,
        business_name="AutoTech Precision",
        contact_email="service@autotech.co.uk",
        contact_phone="+442080000000",
        address_line1="12 High Street",
        city="London",
        postal_code="SW1A 1AA",
        country="GB",
        bay_capacity=4,
        is_tax_registered=True,
        default_tax_rate_percent=Decimal("20.00"),
    )


@pytest.fixture
def buyer_vehicle(db, buyer_user):
    return GarageVehicle.objects.create(
        user=buyer_user,
        make="BMW",
        model="3 Series 320d",
        year=2021,
        registration_plate="AB21 CDE",
        vin="WBA1234567890ABCD",
        current_odometer=35000,
        odometer_unit="mi",
    )


@pytest.fixture
def catalogue_part(db):
    cat = PartCategory.objects.create(name="Braking Systems")
    return Part.objects.create(
        name="Front Brake Disc Set",
        brand="Brembo",
        mpn="09.C398.13",
        category=cat,
    )


@pytest.mark.django_db
class TestWorkshopProfileModel:

    def test_workshop_profile_creation_success(self, workshop_profile, workshop_org):
        assert workshop_profile.id is not None
        assert workshop_profile.organisation == workshop_org
        assert workshop_profile.slug == "autotech-precision"
        assert workshop_profile.bay_capacity == 4
        assert workshop_profile.is_accepting_bookings is True
        assert workshop_profile.is_tax_registered is True
        assert workshop_profile.default_tax_rate_percent == Decimal("20.00")
        assert workshop_profile.display_name == "AutoTech Precision"
        assert str(workshop_profile) == f"AutoTech Precision ({workshop_org.slug})"

    def test_workshop_profile_rejects_non_workshop_org(self, dealer_org):
        profile = WorkshopProfile(
            organisation=dealer_org,
            business_name="Apex Motors Services",
        )
        with pytest.raises(ValidationError) as exc_info:
            profile.save()
        assert "organisation" in exc_info.value.message_dict

    def test_workshop_profile_inherits_organisation_slug_and_name_if_blank(self, workshop_user):
        org = Organisation.objects.create(
            name="Euro Garage Services Ltd",
            type=OrganisationTypeChoices.WORKSHOP,
            created_by=workshop_user,
        )
        profile = WorkshopProfile.objects.create(organisation=org)
        assert profile.business_name == "Euro Garage Services Ltd"
        assert profile.slug == org.slug
        assert profile.display_name == "Euro Garage Services Ltd"
        assert profile.default_tax_rate_percent == Decimal("0.00")

    def test_workshop_profile_tax_configuration(self, workshop_user):
        org = Organisation.objects.create(
            name="Delhi Tech Garage",
            type=OrganisationTypeChoices.WORKSHOP,
            created_by=workshop_user,
        )
        # Workshop in India with 18% GST and INR currency
        profile = WorkshopProfile.objects.create(
            organisation=org,
            currency="INR",
            default_tax_rate_percent=Decimal("18.00"),
        )
        assert profile.currency == "INR"
        assert profile.default_tax_rate_percent == Decimal("18.00")


@pytest.mark.django_db
class TestWorkshopOperatingHoursModel:

    def test_operating_hours_valid(self, workshop_profile):
        hours = WorkshopOperatingHours.objects.create(
            workshop=workshop_profile,
            day_of_week=DayOfWeekChoices.MONDAY,
            is_closed=False,
            open_time=time(8, 30),
            close_time=time(17, 30),
            slot_duration_minutes=60,
        )
        assert hours.id is not None
        assert "Monday" in str(hours)

    def test_operating_hours_closed_day(self, workshop_profile):
        sunday = WorkshopOperatingHours.objects.create(
            workshop=workshop_profile,
            day_of_week=DayOfWeekChoices.SUNDAY,
            is_closed=True,
        )
        assert sunday.id is not None
        assert "Closed" in str(sunday)

    def test_operating_hours_invalid_times(self, workshop_profile):
        hours = WorkshopOperatingHours(
            workshop=workshop_profile,
            day_of_week=DayOfWeekChoices.TUESDAY,
            is_closed=False,
            open_time=time(18, 0),
            close_time=time(9, 0),
        )
        with pytest.raises(ValidationError):
            hours.clean()

    def test_operating_hours_unique_per_day(self, workshop_profile):
        WorkshopOperatingHours.objects.create(
            workshop=workshop_profile,
            day_of_week=DayOfWeekChoices.WEDNESDAY,
            is_closed=False,
            open_time=time(9, 0),
            close_time=time(17, 0),
        )
        duplicate = WorkshopOperatingHours(
            workshop=workshop_profile,
            day_of_week=DayOfWeekChoices.WEDNESDAY,
            is_closed=False,
            open_time=time(8, 0),
            close_time=time(16, 0),
        )
        with pytest.raises(IntegrityError):
            duplicate.save()


@pytest.mark.django_db
class TestWorkshopServiceModels:

    def test_service_category_and_service(self, workshop_profile):
        category = WorkshopServiceCategory.objects.create(
            name="MOT & Inspection",
            description="Official annual Ministry of Transport roadworthiness testing",
        )
        assert category.slug == "mot-inspection"

        service = WorkshopService.objects.create(
            workshop=workshop_profile,
            category=category,
            name="Class 4 MOT Test",
            estimated_duration_minutes=45,
            base_price=Decimal("54.85"),
            currency="GBP",
        )
        assert service.id is not None
        assert service.base_price == Decimal("54.85")
        assert service.is_active is True


@pytest.mark.django_db
class TestWorkshopBookingModel:

    def test_booking_creation_and_snapshot_population(self, workshop_profile, buyer_user, buyer_vehicle):
        booking = WorkshopBooking.objects.create(
            workshop=workshop_profile,
            buyer=buyer_user,
            vehicle=buyer_vehicle,
            preferred_date=date.today() + timedelta(days=2),
            preferred_time_slot="09:00 - 10:00",
            customer_notes="Brake warning light illuminated on dashboard.",
            reported_faults="Squealing sound during moderate deceleration.",
        )

        assert booking.booking_number.startswith("BK-")
        assert booking.status == BookingStatusChoices.REQUESTED
        # Verify vehicle snapshot populated
        assert booking.vehicle_make == "BMW"
        assert booking.vehicle_model == "3 Series 320d"
        assert booking.vehicle_year == 2021
        assert booking.vehicle_registration_plate == "AB21 CDE"
        assert booking.vehicle_vin == "WBA1234567890ABCD"
        assert booking.current_odometer == 35000
        assert booking.odometer_unit == "mi"

    def test_booking_rejects_vehicle_belonging_to_other_buyer(self, workshop_profile, buyer_user, seller_user):
        other_vehicle = GarageVehicle.objects.create(
            user=seller_user,
            make="Audi",
            model="A4",
            year=2020,
            registration_plate="XY20 ZZZ",
        )
        booking = WorkshopBooking(
            workshop=workshop_profile,
            buyer=buyer_user,
            vehicle=other_vehicle,
            preferred_date=date.today() + timedelta(days=1),
        )
        with pytest.raises(ValidationError) as exc_info:
            booking.save()
        assert "vehicle" in exc_info.value.message_dict

    def test_booking_rejects_archived_vehicle(self, workshop_profile, buyer_user, buyer_vehicle):
        buyer_vehicle.is_archived = True
        buyer_vehicle.archived_at = timezone.now()
        buyer_vehicle.save()

        booking = WorkshopBooking(
            workshop=workshop_profile,
            buyer=buyer_user,
            vehicle=buyer_vehicle,
            preferred_date=date.today() + timedelta(days=1),
        )
        with pytest.raises(ValidationError) as exc_info:
            booking.save()
        assert "vehicle" in exc_info.value.message_dict

    def test_booking_rejects_past_preferred_date(self, workshop_profile, buyer_user, buyer_vehicle):
        booking = WorkshopBooking(
            workshop=workshop_profile,
            buyer=buyer_user,
            vehicle=buyer_vehicle,
            preferred_date=date.today() - timedelta(days=1),
        )
        with pytest.raises(ValidationError) as exc_info:
            booking.save()
        assert "preferred_date" in exc_info.value.message_dict

    def test_booking_rejects_invalid_appointment_time_range(self, workshop_profile, buyer_user, buyer_vehicle):
        start = timezone.now() + timedelta(days=2, hours=10)
        end = start - timedelta(hours=1)
        booking = WorkshopBooking(
            workshop=workshop_profile,
            buyer=buyer_user,
            vehicle=buyer_vehicle,
            preferred_date=date.today() + timedelta(days=2),
            scheduled_appointment_start=start,
            scheduled_appointment_end=end,
        )
        with pytest.raises(ValidationError) as exc_info:
            booking.save()
        assert "scheduled_appointment_end" in exc_info.value.message_dict

    def test_booking_rejects_buyer_mutation_on_update(self, workshop_profile, buyer_user, seller_user, buyer_vehicle):
        booking = WorkshopBooking.objects.create(
            workshop=workshop_profile,
            buyer=buyer_user,
            vehicle=buyer_vehicle,
            preferred_date=date.today() + timedelta(days=3),
        )
        booking.buyer = seller_user
        with pytest.raises(ValidationError) as exc_info:
            booking.save()
        assert "buyer" in exc_info.value.message_dict

    def test_booking_cannot_be_deleted_if_has_accepted_quotation(self, workshop_profile, buyer_user, buyer_vehicle):
        booking = WorkshopBooking.objects.create(
            workshop=workshop_profile,
            buyer=buyer_user,
            vehicle=buyer_vehicle,
            preferred_date=date.today() + timedelta(days=3),
        )
        WorkshopQuotation.objects.create(
            booking=booking,
            status=QuotationStatusChoices.ACCEPTED,
            accepted_at=timezone.now(),
        )
        with pytest.raises(ValidationError) as exc_info:
            booking.delete()
        assert "accepted quotation" in str(exc_info.value)


@pytest.mark.django_db
class TestWorkshopQuotationModel:

    @pytest.fixture
    def booking(self, workshop_profile, buyer_user, buyer_vehicle):
        return WorkshopBooking.objects.create(
            workshop=workshop_profile,
            buyer=buyer_user,
            vehicle=buyer_vehicle,
            preferred_date=date.today() + timedelta(days=3),
        )

    def test_quotation_versioning(self, booking):
        quote_v1 = WorkshopQuotation.objects.create(
            booking=booking,
            version=1,
            workshop_notes="Initial quotation for front brake discs and pads.",
        )
        assert quote_v1.version == 1
        assert quote_v1.quotation_number.startswith("QT-")

        # Create v2 for same booking
        quote_v2 = WorkshopQuotation.objects.create(
            booking=booking,
            workshop_notes="Updated quotation including sensor replacement.",
        )
        assert quote_v2.version == 2
        assert quote_v2.quotation_number.startswith("QT-")
        assert quote_v2.quotation_number != quote_v1.quotation_number

    def test_quotation_inherits_workshop_tax_rate(self, booking):
        # Workshop profile has default_tax_rate_percent = 20.00
        quote = WorkshopQuotation.objects.create(
            booking=booking,
        )
        # Should inherit workshop default tax rate
        assert quote.tax_rate_percent == Decimal("20.00")

    def test_quotation_recalculate_totals_with_decimal_precision(self, booking, catalogue_part):
        quotation = WorkshopQuotation.objects.create(
            booking=booking,
            tax_rate_percent=Decimal("20.00"),
            discount_amount=Decimal("15.00"),
        )

        # Labour: 2 hours at 85.00 = 170.00
        QuotationLineItem.objects.create(
            quotation=quotation,
            item_type=LineItemTypeChoices.LABOUR,
            description="Front brake disc and pad replacement labour",
            quantity=Decimal("2.00"),
            unit_price=Decimal("85.00"),
        )

        # Spare Part: 1 Brembo disc set at 120.50 = 120.50
        QuotationLineItem.objects.create(
            quotation=quotation,
            item_type=LineItemTypeChoices.PART,
            catalogue_part=catalogue_part,
            quantity=Decimal("1.00"),
            unit_price=Decimal("120.50"),
        )

        # Diagnostics: 45.00
        QuotationLineItem.objects.create(
            quotation=quotation,
            item_type=LineItemTypeChoices.DIAGNOSTIC,
            description="OBD-II Fault code diagnostic readout",
            quantity=Decimal("1.00"),
            unit_price=Decimal("45.00"),
        )

        # Environmental Disposal Fee: 5.00
        QuotationLineItem.objects.create(
            quotation=quotation,
            item_type=LineItemTypeChoices.DISPOSAL,
            description="Worn parts eco-disposal fee",
            quantity=Decimal("1.00"),
            unit_price=Decimal("5.00"),
        )

        quotation.recalculate_totals(commit=True)
        quotation.refresh_from_db()

        assert quotation.subtotal_labour == Decimal("170.00")
        assert quotation.subtotal_parts == Decimal("120.50")
        assert quotation.subtotal_other == Decimal("50.00")  # 45 + 5
        # Net = 170 + 120.50 + 50 - 15 = 325.50
        # Tax = 325.50 * 0.20 = 65.10
        # Total = 325.50 + 65.10 = 390.60
        assert quotation.tax_amount == Decimal("65.10")
        assert quotation.total_amount == Decimal("390.60")

    def test_accepted_quotation_immutability(self, booking):
        quotation = WorkshopQuotation.objects.create(
            booking=booking,
            subtotal_labour=Decimal("100.00"),
            tax_rate_percent=Decimal("20.00"),
            tax_amount=Decimal("20.00"),
            total_amount=Decimal("120.00"),
            status=QuotationStatusChoices.ACCEPTED,
            accepted_at=timezone.now(),
        )

        # Attempt to modify total_amount
        quotation.total_amount = Decimal("200.00")
        with pytest.raises(ValidationError) as exc_info:
            quotation.save()
        assert "immutable" in str(exc_info.value)

        # Attempt to revert status away from ACCEPTED
        quotation.refresh_from_db()
        quotation.status = QuotationStatusChoices.DRAFT
        with pytest.raises(ValidationError) as exc_info_revert:
            quotation.save()
        assert "cannot be changed" in str(exc_info_revert.value)

        # Attempt to add line item to accepted quote
        quotation.refresh_from_db()
        new_item = QuotationLineItem(
            quotation=quotation,
            item_type=LineItemTypeChoices.LABOUR,
            description="Extra unauthorised charge",
            quantity=Decimal("1.00"),
            unit_price=Decimal("50.00"),
        )
        with pytest.raises(ValidationError) as exc_info_item:
            new_item.save()
        assert "accepted quotation" in str(exc_info_item.value)

        # Attempt to delete accepted quotation
        with pytest.raises(ValidationError) as exc_info_del:
            quotation.delete()
        assert "cannot be deleted" in str(exc_info_del.value)

    def test_unique_accepted_quotation_per_booking_constraint(self, booking):
        # First accepted quotation
        WorkshopQuotation.objects.create(
            booking=booking,
            version=1,
            status=QuotationStatusChoices.ACCEPTED,
            accepted_at=timezone.now(),
        )
        # Attempt to create second quotation with status ACCEPTED for same booking
        with pytest.raises((IntegrityError, ValidationError)):
            WorkshopQuotation.objects.create(
                booking=booking,
                version=2,
                status=QuotationStatusChoices.ACCEPTED,
                accepted_at=timezone.now(),
            )

    def test_booking_deletion_protected_when_quotations_exist(self, booking):
        quote = WorkshopQuotation.objects.create(
            booking=booking,
            version=1,
            status=QuotationStatusChoices.DRAFT,
        )
        # Deleting booking when quotation is attached raises ProtectedError
        with pytest.raises(ProtectedError):
            booking.delete()
