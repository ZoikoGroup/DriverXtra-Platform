import pytest
from decimal import Decimal
from datetime import date
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.test import APIClient

from apps.identity.models import User, RoleChoices
from apps.onboarding.models import (
    SellerApplication,
    SellerApplicationStatusChoices,
    BusinessTypeChoices,
)
from apps.onboarding.services import provision_workshop_organisation
from apps.organisations.models import (
    Organisation,
    OrganisationMembership,
    OrganisationTypeChoices,
    OrganisationRoleChoices,
)
from apps.workshops.models import (
    WorkshopProfile,
    WorkshopService,
    WorkshopBooking,
    WorkshopQuotation,
    WorkOrder,
    WorkOrderStatusChoices,
    ChangeOrder,
    ChangeOrderStatusChoices,
)
from apps.workshops.services import (
    QuotationService,
    WorkOrderService,
    ChangeOrderService,
)
from apps.garage.models import GarageVehicle, VehicleServiceRecord


@pytest.fixture
def admin_user(db):
    user = User.objects.create_user(
        email='platform.admin@driverxtra.com',
        password='AdminPassword123!',
        first_name='Admin',
        last_name='User',
        is_staff=True,
        is_superuser=True,
    )
    user.add_role(RoleChoices.ADMIN)
    return user


@pytest.fixture
def admin_client(admin_user):
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


@pytest.fixture
def indian_applicant(db):
    user = User.objects.create_user(
        email='rajesh@hyderabadmotors.in',
        password='Password123!',
        first_name='Rajesh',
        last_name='Kumar',
        phone_number='+919876543210',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.fixture
def uk_applicant(db):
    user = User.objects.create_user(
        email='george@oxfordmotors.co.uk',
        password='Password123!',
        first_name='George',
        last_name='Smith',
        phone_number='+447123456789',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.fixture
def buyer_user(db):
    user = User.objects.create_user(
        email='customer@example.com',
        password='Password123!',
        first_name='Jane',
        last_name='Customer',
        phone_number='+447000111222',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.mark.django_db
class TestWorkshopRegionalProvisioning:
    """Tests for Indian and UK workshop onboarding, approval, and regional profile provisioning."""

    def test_indian_workshop_onboarding_and_approval_flow(
        self, admin_client, indian_applicant
    ):
        """1. Indian workshop application provisions org with IN/IN-TG, profile with INR and GST."""
        app = SellerApplication.objects.create(
            user=indian_applicant,
            business_name="Hyderabad Precision Auto Care",
            business_type=BusinessTypeChoices.WORKSHOP,
            requested_roles=["WORKSHOP"],
            contact_email="service@hyderabadautocare.in",
            contact_phone="+919876543210",
            address_line1="Road No 36, Jubilee Hills",
            city="Hyderabad",
            postal_code="500033",
            country="IN",
            jurisdiction="IN-TG",
            tax_id="36AABCS1429B1Z5",
            status=SellerApplicationStatusChoices.PENDING,
        )

        res = admin_client.post(
            f"/api/v1/admin/seller-applications/{app.id}/review/",
            {"action": "APPROVE"},
            format="json",
        )
        assert res.status_code == status.HTTP_200_OK

        app.refresh_from_db()
        assert app.status == SellerApplicationStatusChoices.APPROVED
        assert app.organisation is not None

        org = app.organisation
        assert org.country == "IN"
        assert org.jurisdiction == "IN-TG"
        assert org.type == OrganisationTypeChoices.WORKSHOP

        # Check membership
        assert org.is_member(indian_applicant)
        membership = OrganisationMembership.objects.get(organisation=org, user=indian_applicant)
        assert membership.role == OrganisationRoleChoices.OWNER
        assert membership.is_active is True

        # Check workshop profile
        profile = org.workshop_profile
        assert profile is not None
        assert profile.country == "IN"
        assert profile.currency == "INR"
        assert profile.is_tax_registered is True
        assert profile.can_collect_tax is False
        assert profile.default_tax_rate_percent == Decimal("18.00")

    def test_indian_workshop_jurisdiction_derived_from_gstin(
        self, admin_client, indian_applicant
    ):
        """2. When jurisdiction is omitted, Indian workshop derives jurisdiction from GSTIN state code."""
        # GSTIN starting with 27 is Maharashtra (IN-MH)
        app = SellerApplication.objects.create(
            user=indian_applicant,
            business_name="Mumbai Speed Works",
            business_type=BusinessTypeChoices.WORKSHOP,
            requested_roles=["WORKSHOP"],
            contact_email="speed@mumbaiworks.in",
            contact_phone="+919876543211",
            address_line1="Andheri East",
            city="Mumbai",
            postal_code="400069",
            country="IN",
            tax_id="27AAAAA0000A1Z5",
            status=SellerApplicationStatusChoices.PENDING,
        )

        org, profile = provision_workshop_organisation(app)
        assert org.country == "IN"
        assert org.jurisdiction == "IN-MH"
        assert profile.currency == "INR"
        assert profile.default_tax_rate_percent == Decimal("18.00")

    def test_uk_workshop_onboarding_and_approval_flow(
        self, admin_client, uk_applicant
    ):
        """3. UK workshop application provisions org with GB/GB-ENG, profile with GBP and VAT."""
        app = SellerApplication.objects.create(
            user=uk_applicant,
            business_name="Cotswolds Classic Tuning Ltd",
            business_type=BusinessTypeChoices.WORKSHOP,
            requested_roles=["WORKSHOP"],
            contact_email="service@cotswoldstuning.co.uk",
            contact_phone="+447123456789",
            address_line1="14 High Street",
            city="Chipping Norton",
            postal_code="OX7 5AD",
            country="GB",
            jurisdiction="GB-ENG",
            tax_id="GB987654321",
            status=SellerApplicationStatusChoices.PENDING,
        )

        res = admin_client.post(
            f"/api/v1/admin/seller-applications/{app.id}/review/",
            {"action": "APPROVE"},
            format="json",
        )
        assert res.status_code == status.HTTP_200_OK

        app.refresh_from_db()
        org = app.organisation
        assert org.country == "GB"
        assert org.jurisdiction == "GB-ENG"

        profile = org.workshop_profile
        assert profile.country == "GB"
        assert profile.currency == "GBP"
        assert profile.is_tax_registered is True
        assert profile.can_collect_tax is False
        assert profile.default_tax_rate_percent == Decimal("20.00")

    def test_country_and_jurisdiction_validation_and_mismatch_rejection(
        self, indian_applicant
    ):
        """4. Reject invalid country code and mismatched country/jurisdiction."""
        # Invalid country code
        app_bad_country = SellerApplication(
            user=indian_applicant,
            business_name="Mars Rover Repair",
            business_type=BusinessTypeChoices.WORKSHOP,
            requested_roles=["WORKSHOP"],
            contact_email="mars@repair.com",
            contact_phone="+123456789",
            country="XX",
            jurisdiction="IN-TG",
        )
        with pytest.raises(DjangoValidationError) as exc:
            app_bad_country.clean()
        assert "country" in exc.value.message_dict

        # Mismatched country and jurisdiction: country IN, jurisdiction GB-ENG
        app_mismatched = SellerApplication(
            user=indian_applicant,
            business_name="Mismatched Garage",
            business_type=BusinessTypeChoices.WORKSHOP,
            requested_roles=["WORKSHOP"],
            contact_email="mismatch@garage.com",
            contact_phone="+919876543210",
            country="IN",
            jurisdiction="GB-ENG",
        )
        with pytest.raises(DjangoValidationError) as exc:
            app_mismatched.clean()
        assert "jurisdiction" in exc.value.message_dict

    def test_idempotency_and_repeated_approval_safety(
        self, indian_applicant
    ):
        """5. Provisioning is strictly idempotent; repeated calls return the same org and profile."""
        app = SellerApplication.objects.create(
            user=indian_applicant,
            business_name="Bangalore Auto Works",
            business_type=BusinessTypeChoices.WORKSHOP,
            requested_roles=["WORKSHOP"],
            contact_email="blr@autoworks.in",
            contact_phone="+919876543299",
            country="IN",
            jurisdiction="IN-KA",
            status=SellerApplicationStatusChoices.PENDING,
        )

        org1, profile1 = provision_workshop_organisation(app)
        assert Organisation.objects.filter(name="Bangalore Auto Works").count() == 1
        assert WorkshopProfile.objects.filter(organisation=org1).count() == 1

        # Second call
        org2, profile2 = provision_workshop_organisation(app)
        assert org1.id == org2.id
        assert profile1.id == profile2.id
        assert Organisation.objects.filter(name="Bangalore Auto Works").count() == 1
        assert WorkshopProfile.objects.filter(organisation=org1).count() == 1

    def test_multiple_workshop_memberships_safe_resolution_and_conflict_prevention(
        self, indian_applicant
    ):
        """6. Multiple active memberships: resolve by name match, raise ValidationError if ambiguous."""
        # Create 2 distinct workshop orgs owned by applicant
        org1 = Organisation.objects.create(
            name="Alpha Speed Shop",
            type=OrganisationTypeChoices.WORKSHOP,
            country="IN",
            jurisdiction="IN-TG",
            created_by=indian_applicant,
        )
        org1.add_member(indian_applicant, role=OrganisationRoleChoices.OWNER)
        WorkshopProfile.objects.create(organisation=org1, business_name="Alpha Speed Shop", country="IN", currency="INR")

        org2 = Organisation.objects.create(
            name="Beta Turbo Lab",
            type=OrganisationTypeChoices.WORKSHOP,
            country="IN",
            jurisdiction="IN-KA",
            created_by=indian_applicant,
        )
        org2.add_member(indian_applicant, role=OrganisationRoleChoices.OWNER)
        WorkshopProfile.objects.create(organisation=org2, business_name="Beta Turbo Lab", country="IN", currency="INR")

        # Application matching org1 by name -> associates safely without error
        app_matching = SellerApplication.objects.create(
            user=indian_applicant,
            business_name="Alpha Speed Shop",
            business_type=BusinessTypeChoices.WORKSHOP,
            requested_roles=["WORKSHOP"],
            contact_email="alpha@speed.in",
            contact_phone="+919876543201",
            country="IN",
            jurisdiction="IN-TG",
            status=SellerApplicationStatusChoices.PENDING,
        )
        res_org, res_prof = provision_workshop_organisation(app_matching)
        assert res_org.id == org1.id

        # Application with a third name -> cannot resolve arbitrarily -> raises DjangoValidationError
        app_ambiguous = SellerApplication.objects.create(
            user=indian_applicant,
            business_name="Gamma Tuning Works",
            business_type=BusinessTypeChoices.WORKSHOP,
            requested_roles=["WORKSHOP"],
            contact_email="gamma@tuning.in",
            contact_phone="+919876543202",
            country="IN",
            jurisdiction="IN-MH",
            status=SellerApplicationStatusChoices.PENDING,
        )
        with pytest.raises(DjangoValidationError) as exc:
            provision_workshop_organisation(app_ambiguous)
        assert "multiple active workshop organisations" in str(exc.value).lower()


@pytest.mark.django_db
class TestWorkshopRegionalCurrencyAndOperations:
    """Tests for currency consistency and operations across workshop services, quotes, and change orders."""

    @pytest.fixture
    def indian_workshop(self, db, indian_applicant):
        org = Organisation.objects.create(
            name="Deccan Auto Engineering",
            type=OrganisationTypeChoices.WORKSHOP,
            country="IN",
            jurisdiction="IN-TG",
            created_by=indian_applicant,
        )
        org.add_member(indian_applicant, role=OrganisationRoleChoices.OWNER)
        indian_applicant.add_role(RoleChoices.WORKSHOP)
        return WorkshopProfile.objects.create(
            organisation=org,
            business_name="Deccan Auto Engineering",
            country="IN",
            currency="INR",
            default_tax_rate_percent=Decimal("18.00"),
            is_tax_registered=True,
            can_collect_tax=True,
            is_accepting_bookings=True,
        )

    @pytest.fixture
    def uk_workshop(self, db, uk_applicant):
        org = Organisation.objects.create(
            name="London Supercar Clinic",
            type=OrganisationTypeChoices.WORKSHOP,
            country="GB",
            jurisdiction="GB-ENG",
            created_by=uk_applicant,
        )
        org.add_member(uk_applicant, role=OrganisationRoleChoices.OWNER)
        uk_applicant.add_role(RoleChoices.WORKSHOP)
        return WorkshopProfile.objects.create(
            organisation=org,
            business_name="London Supercar Clinic",
            country="GB",
            currency="GBP",
            default_tax_rate_percent=Decimal("20.00"),
            is_tax_registered=True,
            can_collect_tax=True,
            is_accepting_bookings=True,
        )

    @pytest.fixture
    def indian_vehicle(self, db, buyer_user):
        return GarageVehicle.objects.create(
            user=buyer_user,
            make="Tata",
            model="Harrier",
            year=2023,
            registration_plate="TS09FA1234",
            vin="MAT1234567890ABCD",
            current_odometer=25000,
            odometer_unit="km",
        )

    @pytest.fixture
    def uk_vehicle(self, db, buyer_user):
        return GarageVehicle.objects.create(
            user=buyer_user,
            make="Land Rover",
            model="Defender",
            year=2022,
            registration_plate="LD22 GBR",
            vin="SAL1234567890ABCD",
            current_odometer=18500,
            odometer_unit="mi",
        )

    def test_workshop_service_currency_consistency_and_conflict_rejection(
        self, indian_workshop, uk_workshop
    ):
        """1. Services derive currency from workshop and reject conflicting currencies."""
        # Indian workshop service defaults to INR
        in_service = WorkshopService(
            workshop=indian_workshop,
            name="Brake Pad Replacement",
            estimated_duration_minutes=60,
            base_price=Decimal("3500.00"),
        )
        in_service.clean()
        assert in_service.currency == "INR"

        # Indian workshop service with explicit conflicting currency (GBP) is rejected
        in_service_bad = WorkshopService(
            workshop=indian_workshop,
            name="Transmission Flush",
            estimated_duration_minutes=90,
            base_price=Decimal("5000.00"),
            currency="GBP",
        )
        with pytest.raises(DjangoValidationError) as exc:
            in_service_bad.clean()
        assert "currency" in exc.value.message_dict

        # UK workshop service defaults to GBP
        uk_service = WorkshopService(
            workshop=uk_workshop,
            name="Full Service & MOT",
            estimated_duration_minutes=120,
            base_price=Decimal("250.00"),
        )
        uk_service.clean()
        assert uk_service.currency == "GBP"

        # UK workshop service with explicit conflicting currency (INR) is rejected
        uk_service_bad = WorkshopService(
            workshop=uk_workshop,
            name="Full Service & MOT",
            estimated_duration_minutes=120,
            base_price=Decimal("250.00"),
            currency="INR",
        )
        with pytest.raises(DjangoValidationError) as exc:
            uk_service_bad.clean()
        assert "currency" in exc.value.message_dict

    def test_quotation_and_change_order_currency_enforcement(
        self, indian_workshop, indian_vehicle, buyer_user
    ):
        """2. Quotations and Change Orders enforce workshop currency and reject conflicts."""
        booking = WorkshopBooking.objects.create(
            workshop=indian_workshop,
            buyer=buyer_user,
            vehicle=indian_vehicle,
            preferred_date=date.today(),
            customer_notes="Clutch overhaul and flywheel check",
        )

        creator = indian_workshop.organisation.created_by

        # Service creates quotation -> gets workshop currency INR
        quote = QuotationService.create_or_revise_quotation(
            booking=booking,
            data={
                "line_items": [
                    {"description": "Clutch kit", "item_type": "PART", "quantity": 1, "unit_price": "12000.00"},
                    {"description": "Clutch replacement labour", "item_type": "LABOUR", "quantity": 4, "unit_price": "1000.00"},
                ],
                "tax_rate_percent": Decimal("18.00"),
            },
            actor=creator,
        )
        assert quote.currency == "INR"
        assert quote.total_amount == Decimal("18880.00")  # (12000 + 4000) * 1.18

        # Quotation rejection if client tries to pass conflicting currency
        with pytest.raises(DjangoValidationError) as exc:
            QuotationService.create_or_revise_quotation(
                booking=booking,
                data={
                    "line_items": [{"description": "Labour", "item_type": "LABOUR", "quantity": 1, "unit_price": "1000.00"}],
                    "currency": "GBP",
                },
                actor=creator,
            )
        assert "currency" in str(exc.value).lower()

        # Issue quote and accept to spawn work order
        QuotationService.issue_quotation(quote, actor=creator)
        QuotationService.accept_quotation(quote, buyer=buyer_user)
        booking.refresh_from_db()
        work_order = booking.work_order
        assert work_order is not None

        # Change order with matching currency (or omitted) succeeds
        co = ChangeOrderService.create_change_order(
            work_order=work_order,
            data={
                "reason": "Found worn release bearing during clutch removal",
                "line_items": [
                    {"description": "Bearing replacement", "item_type": "LABOUR", "quantity": 1, "unit_price": "1500.00"},
                    {"description": "Heavy duty bearing", "item_type": "PART", "quantity": 1, "unit_price": "2500.00"},
                ],
                "tax_rate_percent": Decimal("18.00"),
            },
            actor=creator,
        )
        assert co.currency == "INR"

        # Change order with conflicting currency is rejected
        with pytest.raises(DjangoValidationError) as exc:
            ChangeOrderService.create_change_order(
                work_order=work_order,
                data={
                    "reason": "Additional exhaust leak fix",
                    "line_items": [{"description": "Welding", "item_type": "LABOUR", "quantity": 1, "unit_price": "50.00"}],
                    "currency": "GBP",
                },
                actor=creator,
            )
        assert "currency" in str(exc.value).lower()

    def test_odometer_unit_and_reading_preservation(
        self, indian_workshop, uk_workshop, indian_vehicle, uk_vehicle, buyer_user
    ):
        """3. Odometer units (km vs mi) and historical readings are strictly preserved upon completion."""
        # --- Indian vehicle flow (km) ---
        creator_in = indian_workshop.organisation.created_by
        booking_in = WorkshopBooking.objects.create(
            workshop=indian_workshop,
            buyer=buyer_user,
            vehicle=indian_vehicle,
            preferred_date=date.today(),
            customer_notes="Regular service",
        )
        quote_in = QuotationService.create_or_revise_quotation(
            booking=booking_in,
            data={
                "line_items": [{"description": "Service labour", "item_type": "LABOUR", "quantity": 2, "unit_price": "1500.00"}],
            },
            actor=creator_in,
        )
        QuotationService.issue_quotation(quote_in, actor=creator_in)
        QuotationService.accept_quotation(quote_in, buyer=buyer_user)
        booking_in.refresh_from_db()
        wo_in = booking_in.work_order

        # Progress work order to COMPLETED with higher odometer in km
        WorkOrderService.assign_technician(wo_in, technician=creator_in, actor=creator_in)
        WorkOrderService.update_status(wo_in, WorkOrderStatusChoices.IN_PROGRESS, actor=creator_in)
        WorkOrderService.update_status(wo_in, WorkOrderStatusChoices.QUALITY_CHECK, actor=creator_in)
        wo_in.current_odometer = 28500
        wo_in.save(update_fields=['current_odometer'])
        WorkOrderService.update_status(
            wo_in,
            WorkOrderStatusChoices.COMPLETED,
            actor=creator_in,
        )

        indian_vehicle.refresh_from_db()
        assert indian_vehicle.current_odometer == 28500
        assert indian_vehicle.odometer_unit == "km"

        # Check generated VehicleServiceRecord
        record_in = VehicleServiceRecord.objects.get(work_order=wo_in)
        assert record_in.odometer_reading == 28500
        assert record_in.odometer_unit == "km"
        assert record_in.currency == "INR"

        # --- UK vehicle flow (mi) ---
        creator_uk = uk_workshop.organisation.created_by
        booking_uk = WorkshopBooking.objects.create(
            workshop=uk_workshop,
            buyer=buyer_user,
            vehicle=uk_vehicle,
            preferred_date=date.today(),
            customer_notes="MOT inspection",
        )
        quote_uk = QuotationService.create_or_revise_quotation(
            booking=booking_uk,
            data={
                "line_items": [{"description": "MOT test", "item_type": "LABOUR", "quantity": 1, "unit_price": "54.85"}],
            },
            actor=creator_uk,
        )
        QuotationService.issue_quotation(quote_uk, actor=creator_uk)
        QuotationService.accept_quotation(quote_uk, buyer=buyer_user)
        booking_uk.refresh_from_db()
        wo_uk = booking_uk.work_order

        WorkOrderService.assign_technician(wo_uk, technician=creator_uk, actor=creator_uk)
        WorkOrderService.update_status(wo_uk, WorkOrderStatusChoices.IN_PROGRESS, actor=creator_uk)
        WorkOrderService.update_status(wo_uk, WorkOrderStatusChoices.QUALITY_CHECK, actor=creator_uk)
        wo_uk.current_odometer = 19200
        wo_uk.save(update_fields=['current_odometer'])
        WorkOrderService.update_status(
            wo_uk,
            WorkOrderStatusChoices.COMPLETED,
            actor=creator_uk,
        )

        uk_vehicle.refresh_from_db()
        assert uk_vehicle.current_odometer == 19200
        assert uk_vehicle.odometer_unit == "mi"

        record_uk = VehicleServiceRecord.objects.get(work_order=wo_uk)
        assert record_uk.odometer_reading == 19200
        assert record_uk.odometer_unit == "mi"
        assert record_uk.currency == "GBP"

    def test_api_rejection_of_conflicting_currency(
        self, indian_workshop, buyer_user
    ):
        """4. Workshop Service and Quotation APIs reject conflicting currencies."""
        client = APIClient()
        client.force_authenticate(user=indian_workshop.organisation.created_by)

        # Service creation with invalid currency
        res = client.post(
            "/api/v1/workshops/manage/services/",
            {
                "name": "Alignment Service",
                "duration_minutes": 45,
                "base_price": "1200.00",
                "currency": "GBP",  # Conflicting with INR
            },
            format="json",
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "currency" in str(res.json()).lower()

        # Service creation with matching currency succeeds
        res_ok = client.post(
            "/api/v1/workshops/manage/services/",
            {
                "name": "Alignment Service",
                "duration_minutes": 45,
                "base_price": "1200.00",
                "currency": "INR",
            },
            format="json",
        )
        assert res_ok.status_code == status.HTTP_201_CREATED
        assert res_ok.json()["currency"] == "INR"


@pytest.mark.django_db
class TestStageCAuditCorrectionsRegionalFoundation:
    """Regression tests for Stage C Audit Corrections: GSTIN validation, cross-validation, and tax safety."""

    def test_gstin_structural_validation_and_jurisdiction_derivation(self):
        """1. derive_jurisdiction_from_tax_id enforces full 15-char format and valid state code."""
        from platform_core.regional import derive_jurisdiction_from_tax_id

        # Valid statutory GSTINs
        assert derive_jurisdiction_from_tax_id("36AAAAA0000A1Z5", "IN") == "IN-TG"
        assert derive_jurisdiction_from_tax_id("27AAAAA0000A1Z5", "IN") == "IN-MH"
        assert derive_jurisdiction_from_tax_id("07AAAAA0000A1Z5", "IN") == "IN-DL"
        # Case insensitive
        assert derive_jurisdiction_from_tax_id("36aaaaa0000a1z5", "IN") == "IN-TG"

        # Truncated GSTINs (must NOT derive jurisdiction from only 2 digits)
        assert derive_jurisdiction_from_tax_id("36", "IN") is None
        assert derive_jurisdiction_from_tax_id("36AAAAA", "IN") is None
        assert derive_jurisdiction_from_tax_id("36AAAAA0000A1Z", "IN") is None

        # Malformed GSTINs
        assert derive_jurisdiction_from_tax_id("36INVALID123456", "IN") is None
        assert derive_jurisdiction_from_tax_id("36AAAAA0000A1!5", "IN") is None
        assert derive_jurisdiction_from_tax_id("36AAAAA0000A1ZZZ", "IN") is None

        # Invalid / unsupported state code
        assert derive_jurisdiction_from_tax_id("99AAAAA0000A1Z5", "IN") is None
        assert derive_jurisdiction_from_tax_id("00AAAAA0000A1Z5", "IN") is None

        # Unsupported / None inputs
        assert derive_jurisdiction_from_tax_id(None, "IN") is None
        assert derive_jurisdiction_from_tax_id("", "IN") is None
        assert derive_jurisdiction_from_tax_id("GB987654321", "GB") is None

    def test_gstin_cross_validation_with_explicit_jurisdiction(self, indian_applicant):
        """2. Cross-validate Indian GSTIN against explicitly submitted jurisdiction."""
        from apps.onboarding.serializers import SellerApplicationCreateUpdateSerializer
        from rest_framework.test import APIRequestFactory
        from rest_framework.exceptions import ValidationError as DRFValidationError

        factory = APIRequestFactory()
        request = factory.post("/api/v1/seller-applications/")
        request.user = indian_applicant

        # 2a. Telangana GSTIN + Telangana jurisdiction (MATCH -> Accepted)
        valid_data = {
            "business_name": "Telangana Precision Motors",
            "business_type": "WORKSHOP",
            "country": "IN",
            "jurisdiction": "IN-TG",
            "tax_id": "36AAAAA0000A1Z5",
            "contact_email": "tg@motors.in",
            "contact_phone": "+919876543210",
            "address_line1": "Road 36",
            "city": "Hyderabad",
            "postal_code": "500033",
        }
        serializer = SellerApplicationCreateUpdateSerializer(data=valid_data, context={"request": request})
        assert serializer.is_valid(), serializer.errors
        assert serializer.validated_data["jurisdiction"] == "IN-TG"

        # 2b. Telangana GSTIN + Maharashtra jurisdiction (MISMATCH -> Rejected)
        mismatch_data = {
            "business_name": "Mismatch Motors",
            "business_type": "WORKSHOP",
            "country": "IN",
            "jurisdiction": "IN-MH",
            "tax_id": "36AAAAA0000A1Z5",  # 36 is Telangana, not Maharashtra
            "contact_email": "mismatch@motors.in",
            "contact_phone": "+919876543210",
            "address_line1": "Andheri West",
            "city": "Mumbai",
            "postal_code": "400053",
        }
        serializer_bad = SellerApplicationCreateUpdateSerializer(data=mismatch_data, context={"request": request})
        assert not serializer_bad.is_valid()
        assert "jurisdiction" in serializer_bad.errors
        err_msg = str(serializer_bad.errors["jurisdiction"])
        assert "mismatch" in err_msg.lower()

    def test_tax_registration_safety_in_provisioning(self, indian_applicant):
        """3. Do not mark workshop as tax registered solely because tax_id contains text."""
        # 3a. Arbitrary non-GSTIN text does NOT set is_tax_registered=True
        app_text_tax = SellerApplication.objects.create(
            user=indian_applicant,
            business_name="Unregistered Auto Care",
            business_type=BusinessTypeChoices.WORKSHOP,
            requested_roles=["WORKSHOP"],
            contact_email="unregistered@autocare.in",
            address_line1="Banjara Hills",
            city="Hyderabad",
            postal_code="500034",
            country="IN",
            jurisdiction="IN-TG",
            tax_id="APPLIED_FOR",  # Text, not valid GSTIN format
            status=SellerApplicationStatusChoices.APPROVED,
        )

        org1, profile1 = provision_workshop_organisation(app_text_tax)
        assert profile1.is_tax_registered is False
        assert profile1.default_tax_rate_percent == Decimal("0.00")

        # 3b. Missing tax_id leaves workshop profile unregistered
        user2 = User.objects.create_user(
            email="notax@hyderabadmotors.in",
            password="Password123!",
            is_email_verified=True,
        )
        app_no_tax = SellerApplication.objects.create(
            user=user2,
            business_name="No Tax Workshop",
            business_type=BusinessTypeChoices.WORKSHOP,
            requested_roles=["WORKSHOP"],
            contact_email="notax@workshop.in",
            address_line1="Madhapur",
            city="Hyderabad",
            postal_code="500081",
            country="IN",
            jurisdiction="IN-TG",
            tax_id="",
            status=SellerApplicationStatusChoices.APPROVED,
        )

        org2, profile2 = provision_workshop_organisation(app_no_tax)
        assert profile2.is_tax_registered is False
        assert profile2.default_tax_rate_percent == Decimal("0.00")

        # 3c. Valid statutory GSTIN format marks profile as candidate tax registered
        user3 = User.objects.create_user(
            email="validtax@hyderabadmotors.in",
            password="Password123!",
            is_email_verified=True,
        )
        app_valid_tax = SellerApplication.objects.create(
            user=user3,
            business_name="Valid Tax Workshop",
            business_type=BusinessTypeChoices.WORKSHOP,
            requested_roles=["WORKSHOP"],
            contact_email="validtax@workshop.in",
            address_line1="Gachibowli",
            city="Hyderabad",
            postal_code="500032",
            country="IN",
            jurisdiction="IN-TG",
            tax_id="36AAAAA0000A1Z5",
            status=SellerApplicationStatusChoices.APPROVED,
        )

        org3, profile3 = provision_workshop_organisation(app_valid_tax)
        assert profile3.is_tax_registered is True
        assert profile3.can_collect_tax is False  # Structural format validation does NOT authorize tax collection
        assert profile3.default_tax_rate_percent == Decimal("18.00")

    def test_tax_collection_authorization_and_prevention_of_unauthorized_tax(
        self, indian_applicant, buyer_user
    ):
        """4. Separate registration from collection authorization; prevent unauthorized tax on quotes."""
        from django.core.exceptions import ValidationError as DjangoValidationError
        from apps.workshops.models import WorkshopBooking, WorkshopQuotation

        user = User.objects.create_user(
            email="candidate.tax@hyderabadmotors.in",
            password="Password123!",
            is_email_verified=True,
        )
        app = SellerApplication.objects.create(
            user=user,
            business_name="Candidate Tax Workshop",
            business_type=BusinessTypeChoices.WORKSHOP,
            requested_roles=["WORKSHOP"],
            contact_email="cand@workshop.in",
            address_line1="Jubilee Hills",
            city="Hyderabad",
            postal_code="500033",
            country="IN",
            jurisdiction="IN-TG",
            tax_id="36AAAAA0000A1Z5",  # Valid GSTIN syntax
            status=SellerApplicationStatusChoices.APPROVED,
        )
        org, profile = provision_workshop_organisation(app)
        assert profile.is_tax_registered is True
        assert profile.can_collect_tax is False  # Not authorized solely by regex!

        vehicle = GarageVehicle.objects.create(
            user=buyer_user,
            make="Maruti",
            model="Swift",
            year=2020,
            registration_plate="TS09AB9999",
            odometer_unit="km",
        )
        booking = WorkshopBooking.objects.create(
            workshop=profile,
            buyer=buyer_user,
            vehicle=vehicle,
            preferred_date=date.today(),
        )

        # 4a. Creating a quotation for unauthorized workshop does NOT auto-inject tax
        quote = WorkshopQuotation(
            booking=booking,
            currency="INR",
            tax_rate_percent=Decimal("0.00"),
        )
        quote.clean()
        assert quote.tax_rate_percent == Decimal("0.00")  # Remains 0.00%, NOT auto-bumped to 18.00%

        # 4b. Attempting to charge positive tax when unauthorized raises ValidationError
        unauthorized_quote = WorkshopQuotation(
            booking=booking,
            currency="INR",
            tax_rate_percent=Decimal("18.00"),
        )
        with pytest.raises(DjangoValidationError) as exc:
            unauthorized_quote.clean()
        assert "not authorized to collect tax" in str(exc.value).lower()

        # 4c. Authorizing workshop allows tax configuration and collection
        profile.can_collect_tax = True
        profile.save(update_fields=['can_collect_tax'])

        authorized_quote = WorkshopQuotation(
            booking=booking,
            currency="INR",
            tax_rate_percent=Decimal("18.00"),
        )
        authorized_quote.clean()  # Passes cleanly!
        assert authorized_quote.tax_rate_percent == Decimal("18.00")

        # 4d. Unregistered workshop cannot have can_collect_tax=True
        profile.is_tax_registered = False
        with pytest.raises(DjangoValidationError) as exc:
            profile.clean()
        assert "cannot authorize tax collection" in str(exc.value).lower()


@pytest.mark.django_db
class TestStageCFinalTaxAuthorizationEnforcement:
    """
    Exhaustive regression test suite verifying the strict separation of:
    - Tax ID presence
    - Structural format validity
    - Tax registration status
    - Explicit administrative tax collection authorization
    """

    def test_new_workshop_profiles_default_to_unauthorized(self, db, admin_user):
        """1. New workshop profiles must default to can_collect_tax=False and is_tax_registered=False."""
        org = Organisation.objects.create(
            name="New Default Motors",
            slug="new-default-motors",
            type=OrganisationTypeChoices.WORKSHOP,
            country="GB",
            jurisdiction="GB-ENG",
            created_by=admin_user,
        )
        profile = WorkshopProfile.objects.create(
            organisation=org,
            business_name="New Default Motors",
            city="Birmingham",
        )
        assert profile.can_collect_tax is False
        assert profile.is_tax_registered is False

    def test_existing_workshops_remain_unauthorized_migration_default(self):
        """2. Field definition defaults must be False so migrations default existing rows to False."""
        can_collect_field = WorkshopProfile._meta.get_field('can_collect_tax')
        assert can_collect_field.default is False

        is_registered_field = WorkshopProfile._meta.get_field('is_tax_registered')
        assert is_registered_field.default is False

    def test_existing_workshop_profiles_remain_unauthorized_without_explicit_grant(self, db, admin_user):
        """2b. Existing workshop created prior to tax collection verification remains can_collect_tax=False."""
        org = Organisation.objects.create(
            name="Legacy Pre-Existing Motors",
            slug="legacy-pre-existing-motors",
            type=OrganisationTypeChoices.WORKSHOP,
            country="GB",
            jurisdiction="GB-ENG",
            created_by=admin_user,
        )
        # Workshop profile exists with tax registration but without explicit can_collect_tax
        profile = WorkshopProfile.objects.create(
            organisation=org,
            business_name="Legacy Pre-Existing Motors",
            city="Manchester",
            is_tax_registered=True,
            default_tax_rate_percent=Decimal("20.00"),
        )
        profile.refresh_from_db()
        assert profile.can_collect_tax is False
        assert profile.default_tax_rate_percent == Decimal("20.00")

    def test_structurally_valid_tax_id_does_not_grant_collection_authorization(
        self, admin_user, indian_applicant, uk_applicant
    ):
        """3. Structurally valid tax IDs (GSTIN / VAT) set format-validated candidate registration, but strictly can_collect_tax=False."""
        # Indian workshop with valid GSTIN
        in_app = SellerApplication.objects.create(
            user=indian_applicant,
            business_name="Deccan Auto Solutions",
            business_type=BusinessTypeChoices.WORKSHOP,
            requested_roles=["WORKSHOP"],
            contact_email="service@deccanauto.in",
            contact_phone="+919876543210",
            address_line1="Banjara Hills",
            city="Hyderabad",
            postal_code="500034",
            country="IN",
            jurisdiction="IN-TG",
            tax_id="36AAACB1234F1Z5",  # Structurally valid Indian GSTIN
            status=SellerApplicationStatusChoices.PENDING,
        )
        _, in_profile = provision_workshop_organisation(in_app)
        assert in_profile.is_tax_registered is True
        assert in_profile.can_collect_tax is False  # Explicitly unauthorized!

        # UK workshop with valid VAT
        uk_app = SellerApplication.objects.create(
            user=uk_applicant,
            business_name="Thames Auto Tech",
            business_type=BusinessTypeChoices.WORKSHOP,
            requested_roles=["WORKSHOP"],
            contact_email="service@thamesautotech.co.uk",
            contact_phone="+447123456789",
            address_line1="Oxford Road",
            city="Oxford",
            postal_code="OX1 1AA",
            country="GB",
            jurisdiction="GB-ENG",
            tax_id="GB123456789",  # Structurally valid UK VAT
            status=SellerApplicationStatusChoices.PENDING,
        )
        _, uk_profile = provision_workshop_organisation(uk_app)
        assert uk_profile.is_tax_registered is True
        assert uk_profile.can_collect_tax is False  # Explicitly unauthorized!

    def test_workshop_users_cannot_grant_themselves_authorization_through_profile_apis(
        self, db, indian_applicant
    ):
        """4. Workshop owners cannot grant themselves tax collection authorization via manage profile API."""
        org = Organisation.objects.create(
            name="Hyderabad Speedworks",
            slug="hyderabad-speedworks",
            type=OrganisationTypeChoices.WORKSHOP,
            country="IN",
            jurisdiction="IN-TG",
            created_by=indian_applicant,
        )
        org.add_member(indian_applicant, role=OrganisationRoleChoices.OWNER)
        profile = WorkshopProfile.objects.create(
            organisation=org,
            business_name="Hyderabad Speedworks",
            city="Hyderabad",
            country="IN",
            currency="INR",
            is_tax_registered=True,
            can_collect_tax=False,
            is_verified=True,
        )

        client = APIClient()
        client.force_authenticate(user=indian_applicant)

        # Workshop owner attempts to set can_collect_tax=True
        resp = client.patch(
            '/api/v1/workshops/manage/profile/',
            {'can_collect_tax': True},
            format='json',
            HTTP_X_ORGANISATION_ID=str(org.id),
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        assert "cannot modify tax collection authorization" in str(resp.data).lower()

        # Database state remains unchanged
        profile.refresh_from_db()
        assert profile.can_collect_tax is False

    def test_unauthorized_workshops_cannot_apply_positive_tax_rates_to_quotations_or_change_orders(
        self, db, admin_user, buyer_user
    ):
        """5. Quotations and change orders reject positive tax rates when workshop is unauthorized."""
        from apps.workshops.serializers import QuotationCreateUpdateSerializer, ChangeOrderCreateSerializer

        org = Organisation.objects.create(
            name="Alpha Garage Ltd",
            slug="alpha-garage-ltd",
            type=OrganisationTypeChoices.WORKSHOP,
            country="GB",
            jurisdiction="GB-ENG",
            created_by=admin_user,
        )
        profile = WorkshopProfile.objects.create(
            organisation=org,
            business_name="Alpha Garage",
            city="London",
            country="GB",
            currency="GBP",
            is_tax_registered=True,
            can_collect_tax=False,  # Unauthorized!
            is_verified=True,
        )
        vehicle = GarageVehicle.objects.create(
            user=buyer_user,
            make="Ford",
            model="Focus",
            year=2019,
            registration_plate="LO19 FFD",
            odometer_unit="mi",
        )
        booking = WorkshopBooking.objects.create(
            workshop=profile,
            buyer=buyer_user,
            vehicle=vehicle,
            preferred_date=date.today(),
        )

        # 5a. QuotationCreateUpdateSerializer rejects positive tax rate
        q_serializer = QuotationCreateUpdateSerializer(
            data={
                'tax_rate_percent': '20.00',
                'line_items': [{'item_type': 'LABOUR', 'description': 'Oil change', 'unit_price': '100.00', 'quantity': '1.00'}],
            },
            context={'booking': booking},
        )
        assert q_serializer.is_valid() is False
        assert 'tax_rate_percent' in q_serializer.errors
        assert "not authorized to collect tax" in str(q_serializer.errors['tax_rate_percent']).lower()

        # 5b. WorkshopQuotation.clean() rejects positive tax rate
        unauth_quote = WorkshopQuotation(
            booking=booking,
            currency="GBP",
            tax_rate_percent=Decimal("20.00"),
        )
        with pytest.raises(DjangoValidationError) as exc:
            unauth_quote.clean()
        assert "not authorized to collect tax" in str(exc.value).lower()

        # Create valid 0% quotation to test change order
        quote = WorkshopQuotation.objects.create(
            booking=booking,
            currency="GBP",
            tax_rate_percent=Decimal("0.00"),
        )
        work_order = WorkOrder.objects.create(
            workshop=profile,
            booking=booking,
            buyer=buyer_user,
            vehicle=vehicle,
            quotation=quote,
            odometer_unit="mi",
        )

        # 5c. ChangeOrderCreateSerializer rejects positive tax rate
        co_serializer = ChangeOrderCreateSerializer(
            data={
                'reason': 'Discovered worn brake pads during inspection',
                'tax_rate_percent': '20.00',
                'line_items': [{'item_type': 'PART', 'description': 'Brake pads', 'unit_price': '80.00', 'quantity': '1.00'}],
            },
            context={'work_order': work_order},
        )
        assert co_serializer.is_valid() is False
        assert 'tax_rate_percent' in co_serializer.errors
        assert "not authorized to collect tax" in str(co_serializer.errors['tax_rate_percent']).lower()

        # 5d. ChangeOrderService.create_change_order rejects positive tax rate
        with pytest.raises(DjangoValidationError) as exc:
            ChangeOrderService.create_change_order(
                work_order=work_order,
                data={
                    'reason': 'Worn auxiliary belt',
                    'tax_rate_percent': Decimal('20.00'),
                    'line_items': [{'item_type': 'PART', 'description': 'Aux belt', 'unit_price': Decimal('40.00'), 'quantity': Decimal('1.00')}],
                },
                actor=admin_user,
            )
        assert "not authorized to collect tax" in str(exc.value).lower()

    def test_authorized_staff_can_grant_and_revoke_tax_collection_with_audit_events(
        self, db, admin_user, admin_client
    ):
        """6. Platform staff can grant and revoke authorization via service and admin API, with audit trails."""
        from apps.workshops.services import WorkshopTaxAuthorizationService
        from platform_core.audit.models import AuditLog

        org = Organisation.objects.create(
            name="Staff Verified Motors",
            slug="staff-verified-motors",
            type=OrganisationTypeChoices.WORKSHOP,
            country="GB",
            jurisdiction="GB-ENG",
            created_by=admin_user,
        )
        profile = WorkshopProfile.objects.create(
            organisation=org,
            business_name="Staff Verified Motors",
            city="Leeds",
            country="GB",
            currency="GBP",
            is_tax_registered=True,
            can_collect_tax=False,
            is_verified=True,
        )

        # 6a. Grant tax collection authorization via service
        updated = WorkshopTaxAuthorizationService.set_tax_collection_authorization(
            workshop=profile,
            authorized=True,
            actor=admin_user,
            reason="HMRC VAT certificate inspected and verified",
        )
        assert updated.can_collect_tax is True

        # Verify audit event for grant
        grant_audit = AuditLog.objects.filter(
            resource_type="WorkshopProfile",
            resource_id=str(profile.id),
            event_type="workshop.tax_authorization.granted",
        ).order_by('-created_at').first()
        assert grant_audit is not None
        assert grant_audit.actor_id == admin_user.id
        assert grant_audit.metadata.get('new_state') is True
        assert "hmrc vat certificate" in grant_audit.metadata.get('reason', '').lower()

        # 6b. Revoke tax collection authorization via platform admin API
        resp = admin_client.post(
            f'/api/v1/workshops/admin/{profile.id}/tax-authorization/',
            {'can_collect_tax': False, 'reason': 'VAT deregistration confirmation received'},
            format='json',
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data.get('can_collect_tax') is False

        profile.refresh_from_db()
        assert profile.can_collect_tax is False

        # Verify audit event for revoke
        revoke_audit = AuditLog.objects.filter(
            resource_type="WorkshopProfile",
            resource_id=str(profile.id),
            event_type="workshop.tax_authorization.revoked",
        ).order_by('-created_at').first()
        assert revoke_audit is not None
        assert revoke_audit.actor_id == admin_user.id
        assert revoke_audit.metadata.get('new_state') is False

    def test_staff_cannot_authorize_tax_collection_for_unregistered_workshop(
        self, db, admin_user, admin_client
    ):
        """7. Platform staff cannot authorize tax collection for a workshop that is not tax registered."""
        from apps.workshops.services import WorkshopTaxAuthorizationService

        org = Organisation.objects.create(
            name="Unregistered Motors",
            slug="unregistered-motors",
            type=OrganisationTypeChoices.WORKSHOP,
            country="GB",
            jurisdiction="GB-ENG",
            created_by=admin_user,
        )
        profile = WorkshopProfile.objects.create(
            organisation=org,
            business_name="Unregistered Motors",
            city="Bristol",
            country="GB",
            currency="GBP",
            is_tax_registered=False,  # NOT tax registered!
            can_collect_tax=False,
            is_verified=True,
        )

        # 7a. Service rejects authorization
        with pytest.raises(DjangoValidationError) as exc:
            WorkshopTaxAuthorizationService.set_tax_collection_authorization(
                workshop=profile,
                authorized=True,
                actor=admin_user,
                reason="Attempted premature authorization",
            )
        assert "not tax registered" in str(exc.value).lower()

        # 7b. Admin API rejects authorization
        resp = admin_client.post(
            f'/api/v1/workshops/admin/{profile.id}/tax-authorization/',
            {'can_collect_tax': True, 'reason': 'Attempted premature authorization'},
            format='json',
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "not tax registered" in str(resp.data.get('message', '')).lower()

