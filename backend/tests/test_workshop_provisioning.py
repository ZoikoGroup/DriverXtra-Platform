import pytest
from unittest.mock import patch
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
from apps.workshops.models import WorkshopProfile, WorkshopBooking
from apps.workshops.services import BookingService
from apps.garage.models import GarageVehicle


@pytest.fixture
def applicant_user(db):
    user = User.objects.create_user(
        email='mechanic@apexgarage.co.uk',
        password='SecurePassword123!',
        first_name='Marcus',
        last_name='Spanner',
        phone_number='+447000123456',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.fixture
def admin_user(db):
    user = User.objects.create_user(
        email='admin@driverxtra.com',
        password='AdminPassword123!',
        first_name='Platform',
        last_name='Admin',
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
def applicant_client(applicant_user):
    client = APIClient()
    client.force_authenticate(user=applicant_user)
    return client


@pytest.fixture
def buyer_vehicle(db, applicant_user):
    return GarageVehicle.objects.create(
        user=applicant_user,
        make="BMW",
        model="M3",
        year=2021,
        registration_plate="BM21 APX",
        vin="WBA1234567890ABCD",
        current_odometer=15000,
        odometer_unit="mi",
    )


@pytest.mark.django_db
class TestWorkshopOrganisationProvisioning:

    def test_successful_workshop_application_approval_and_provisioning(
        self, admin_client, applicant_user, applicant_client
    ):
        """1. Successful workshop application approval provisions org, membership, and profile."""
        app = SellerApplication.objects.create(
            user=applicant_user,
            business_name="Apex Performance Workshop Ltd",
            business_type=BusinessTypeChoices.WORKSHOP,
            requested_roles=["WORKSHOP"],
            contact_email="service@apexgarage.co.uk",
            contact_phone="+447000123456",
            address_line1="12 Silverstone Circuit",
            city="Towcester",
            postal_code="NN12 8TN",
            country="United Kingdom",
            status=SellerApplicationStatusChoices.PENDING,
        )

        res = admin_client.post(
            f"/api/v1/admin/seller-applications/{app.id}/review/",
            {"action": "APPROVE", "admin_notes": "All workshop facilities verified."},
            format="json",
        )
        assert res.status_code == status.HTTP_200_OK

        app.refresh_from_db()
        assert app.status == SellerApplicationStatusChoices.APPROVED
        assert app.organisation is not None
        assert app.organisation.type == OrganisationTypeChoices.WORKSHOP
        assert app.organisation.name == "Apex Performance Workshop Ltd"

        # Verify applicant is OWNER of the newly created workshop organisation
        membership = OrganisationMembership.objects.filter(
            organisation=app.organisation,
            user=applicant_user,
        ).first()
        assert membership is not None
        assert membership.role == OrganisationRoleChoices.OWNER
        assert membership.is_active is True

        # Verify WorkshopProfile created
        profile = WorkshopProfile.objects.filter(organisation=app.organisation).first()
        assert profile is not None
        assert profile.business_name == "Apex Performance Workshop Ltd"
        assert profile.city == "Towcester"
        assert profile.postal_code == "NN12 8TN"
        # Unconfigured workshop must NOT accept bookings initially
        assert profile.is_accepting_bookings is False

        # Verify applicant user holds WORKSHOP platform role
        applicant_user.refresh_from_db()
        assert applicant_user.has_role(RoleChoices.WORKSHOP)

        # Verify applicant can now access workshop profile API without 403
        get_res = applicant_client.get("/api/v1/workshops/manage/profile/")
        assert get_res.status_code == status.HTTP_200_OK
        assert get_res.json()["business_name"] == "Apex Performance Workshop Ltd"

        # Verify applicant can update profile
        patch_res = applicant_client.patch(
            "/api/v1/workshops/manage/profile/",
            {"bay_capacity": 4, "is_accepting_bookings": True},
            format="json",
        )
        assert patch_res.status_code == status.HTTP_200_OK
        assert patch_res.json()["bay_capacity"] == 4
        assert patch_res.json()["is_accepting_bookings"] is True

    def test_idempotent_approval_and_provisioning(self, applicant_user, admin_client):
        """2. Repeated provisioning or approval does not duplicate records."""
        app = SellerApplication.objects.create(
            user=applicant_user,
            business_name="Precision Spanners Ltd",
            business_type=BusinessTypeChoices.WORKSHOP,
            requested_roles=["WORKSHOP"],
            contact_email="info@precisionspanners.co.uk",
            contact_phone="+447000999888",
            status=SellerApplicationStatusChoices.PENDING,
        )

        # First run: direct service call
        org1, prof1 = provision_workshop_organisation(app)
        assert Organisation.objects.filter(type=OrganisationTypeChoices.WORKSHOP).count() == 1
        assert WorkshopProfile.objects.count() == 1

        # Second run: identical service call
        org2, prof2 = provision_workshop_organisation(app)
        assert org1.id == org2.id
        assert prof1.id == prof2.id
        assert Organisation.objects.filter(type=OrganisationTypeChoices.WORKSHOP).count() == 1
        assert WorkshopProfile.objects.count() == 1
        assert OrganisationMembership.objects.filter(user=applicant_user).count() == 1

        # Third run: verify API re-approval returns 400 Bad Request
        app.status = SellerApplicationStatusChoices.APPROVED
        app.save()
        res = admin_client.post(
            f"/api/v1/admin/seller-applications/{app.id}/review/",
            {"action": "APPROVE"},
            format="json",
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "pending status can be approved" in str(res.json()).lower()

    def test_existing_membership_preservation(self, applicant_user):
        """3. Preserves existing organisation and membership records."""
        existing_org = Organisation.objects.create(
            name="Heritage Bavarian Garage",
            type=OrganisationTypeChoices.WORKSHOP,
            created_by=applicant_user,
        )
        existing_org.add_member(applicant_user, role=OrganisationRoleChoices.OWNER)

        app = SellerApplication.objects.create(
            user=applicant_user,
            organisation=existing_org,
            business_name="Heritage Bavarian Garage",
            business_type=BusinessTypeChoices.WORKSHOP,
            requested_roles=["WORKSHOP"],
            contact_email="heritage@bavarian.co.uk",
            contact_phone="+447000444555",
            status=SellerApplicationStatusChoices.PENDING,
        )

        org, profile = provision_workshop_organisation(app)
        assert org.id == existing_org.id
        assert Organisation.objects.filter(type=OrganisationTypeChoices.WORKSHOP).count() == 1
        assert OrganisationMembership.objects.filter(user=applicant_user).count() == 1

    def test_admin_not_automatically_promoted_to_owner(self, applicant_user, admin_client):
        """4. An existing ADMIN membership must NOT be automatically promoted to OWNER."""
        creator = User.objects.create_user(email="owner@dealers.com", password="Password123!")
        existing_org = Organisation.objects.create(
            name="Apex Motors Workshop",
            type=OrganisationTypeChoices.WORKSHOP,
            created_by=creator,
        )
        existing_org.add_member(creator, role=OrganisationRoleChoices.OWNER)
        # Add applicant as ADMIN (not OWNER)
        membership = existing_org.add_member(applicant_user, role=OrganisationRoleChoices.ADMIN)
        assert membership.role == OrganisationRoleChoices.ADMIN

        app = SellerApplication.objects.create(
            user=applicant_user,
            organisation=existing_org,
            business_name="Apex Motors Workshop",
            business_type=BusinessTypeChoices.WORKSHOP,
            requested_roles=["WORKSHOP"],
            contact_email="admin.applicant@apex.com",
            contact_phone="+447000777888",
            status=SellerApplicationStatusChoices.PENDING,
        )

        res = admin_client.post(
            f"/api/v1/admin/seller-applications/{app.id}/review/",
            {"action": "APPROVE"},
            format="json",
        )
        assert res.status_code == status.HTTP_200_OK

        membership.refresh_from_db()
        # Verify role was preserved as ADMIN, NOT promoted to OWNER
        assert membership.role == OrganisationRoleChoices.ADMIN

    def test_multiple_workshop_organisations_detected(self, applicant_user, applicant_client):
        """5. Detects ambiguous multiple workshop organisations instead of selecting one arbitrarily."""
        org1 = Organisation.objects.create(
            name="Workshop Branch North",
            type=OrganisationTypeChoices.WORKSHOP,
            created_by=applicant_user,
        )
        org1.add_member(applicant_user, role=OrganisationRoleChoices.OWNER)
        prof1 = WorkshopProfile.objects.create(organisation=org1, business_name="Workshop Branch North")

        org2 = Organisation.objects.create(
            name="Workshop Branch South",
            type=OrganisationTypeChoices.WORKSHOP,
            created_by=applicant_user,
        )
        org2.add_member(applicant_user, role=OrganisationRoleChoices.OWNER)
        prof2 = WorkshopProfile.objects.create(organisation=org2, business_name="Workshop Branch South")

        applicant_user.add_role(RoleChoices.WORKSHOP)

        # Ambiguous request without organisation context
        res = applicant_client.get("/api/v1/workshops/manage/profile/")
        assert res.status_code == status.HTTP_403_FORBIDDEN
        assert "multiple active workshop organisations found" in str(res.json()).lower()

        # Disambiguated request using X-Organisation-ID header
        res_north = applicant_client.get(
            "/api/v1/workshops/manage/profile/",
            HTTP_X_ORGANISATION_ID=str(org1.id),
        )
        assert res_north.status_code == status.HTTP_200_OK
        assert res_north.json()["business_name"] == "Workshop Branch North"

        # Disambiguated request using query param
        res_south = applicant_client.get(f"/api/v1/workshops/manage/profile/?organisation_id={org2.id}")
        assert res_south.status_code == status.HTTP_200_OK
        assert res_south.json()["business_name"] == "Workshop Branch South"

    def test_existing_dealer_organisation_association_preservation(
        self, applicant_user, admin_client
    ):
        """6. Does not overwrite an existing dealership organisation association on SellerApplication."""
        dealer_org = Organisation.objects.create(
            name="Prestige Dealer Group PLC",
            type=OrganisationTypeChoices.DEALER_GROUP,
            created_by=applicant_user,
        )
        dealer_org.add_member(applicant_user, role=OrganisationRoleChoices.OWNER)

        app = SellerApplication.objects.create(
            user=applicant_user,
            organisation=dealer_org,
            business_name="Prestige Auto Care Workshop",
            business_type=BusinessTypeChoices.WORKSHOP,
            requested_roles=["SELLER", "WORKSHOP"],
            contact_email="service@prestigeplc.com",
            contact_phone="+447000555666",
            status=SellerApplicationStatusChoices.PENDING,
        )

        res = admin_client.post(
            f"/api/v1/admin/seller-applications/{app.id}/review/",
            {"action": "APPROVE"},
            format="json",
        )
        assert res.status_code == status.HTTP_200_OK

        app.refresh_from_db()
        # Verify dealership organisation association is strictly preserved on application
        assert app.organisation == dealer_org
        assert app.organisation.type == OrganisationTypeChoices.DEALER_GROUP

        # Verify a new workshop organisation was created for workshop operations
        workshop_org = Organisation.objects.filter(
            type=OrganisationTypeChoices.WORKSHOP,
            created_by=applicant_user,
        ).first()
        assert workshop_org is not None
        assert WorkshopProfile.objects.filter(organisation=workshop_org).exists()

        # Verify applicant is member of both organisations
        assert dealer_org.is_member(applicant_user)
        assert workshop_org.is_member(applicant_user)

    def test_transaction_rollback_on_provisioning_failure(
        self, applicant_user, admin_client
    ):
        """7. Ensure failures roll back provisioning safely."""
        app = SellerApplication.objects.create(
            user=applicant_user,
            business_name="Fragile Workshop Ltd",
            business_type=BusinessTypeChoices.WORKSHOP,
            requested_roles=["WORKSHOP"],
            contact_email="fragile@workshop.com",
            contact_phone="+447000111222",
            status=SellerApplicationStatusChoices.PENDING,
        )

        # Mock WorkshopProfile.objects.get_or_create to simulate an unexpected database validation error
        with patch(
            "apps.workshops.models.WorkshopProfile.objects.get_or_create",
            side_effect=DjangoValidationError("Database constraint violation"),
        ):
            res = admin_client.post(
                f"/api/v1/admin/seller-applications/{app.id}/review/",
                {"action": "APPROVE"},
                format="json",
            )
            assert res.status_code == status.HTTP_400_BAD_REQUEST

        app.refresh_from_db()
        # Verify application status was NOT updated to APPROVED
        assert app.status == SellerApplicationStatusChoices.PENDING
        # Verify role was NOT granted
        applicant_user.refresh_from_db()
        assert not applicant_user.has_role(RoleChoices.WORKSHOP)
        # Verify no orphaned workshop organisation was committed
        assert Organisation.objects.filter(name="Fragile Workshop Ltd").count() == 0

    def test_notification_failure_after_commit(self, applicant_user, admin_client):
        """8. If notification fails after commit, the committed transaction remains valid."""
        app = SellerApplication.objects.create(
            user=applicant_user,
            business_name="Reliable Workshop Ltd",
            business_type=BusinessTypeChoices.WORKSHOP,
            requested_roles=["WORKSHOP"],
            contact_email="reliable@workshop.com",
            contact_phone="+447000333444",
            status=SellerApplicationStatusChoices.PENDING,
        )

        with patch(
            "apps.notifications.services.create_notification",
            side_effect=RuntimeError("Push notification gateway timeout"),
        ):
            res = admin_client.post(
                f"/api/v1/admin/seller-applications/{app.id}/review/",
                {"action": "APPROVE"},
                format="json",
            )
            assert res.status_code == status.HTTP_200_OK

        app.refresh_from_db()
        # Application approval and tenant provisioning succeeded despite post-commit notification failure
        assert app.status == SellerApplicationStatusChoices.APPROVED
        assert app.organisation is not None
        assert WorkshopProfile.objects.filter(organisation=app.organisation).exists()

    def test_profile_get_remains_read_only(self, applicant_user, applicant_client):
        """9. Profile GET remains strictly read-only and does not create missing records."""
        org = Organisation.objects.create(
            name="Empty Workshop Org",
            type=OrganisationTypeChoices.WORKSHOP,
            created_by=applicant_user,
        )
        org.add_member(applicant_user, role=OrganisationRoleChoices.OWNER)
        applicant_user.add_role(RoleChoices.WORKSHOP)

        # GET request when WorkshopProfile does not exist
        res = applicant_client.get("/api/v1/workshops/manage/profile/")
        assert res.status_code == status.HTTP_403_FORBIDDEN
        assert "no workshop profile exists" in str(res.json()).lower()

        # Crucial check: zero WorkshopProfile records were created by the GET endpoint
        assert WorkshopProfile.objects.filter(organisation=org).count() == 0

    def test_unconfigured_workshop_cannot_accept_bookings(
        self, applicant_user, admin_client, buyer_vehicle
    ):
        """10. Unconfigured workshop cannot accept bookings until owner enables booking availability."""
        app = SellerApplication.objects.create(
            user=applicant_user,
            business_name="Unconfigured Garage Ltd",
            business_type=BusinessTypeChoices.WORKSHOP,
            requested_roles=["WORKSHOP"],
            contact_email="unconfigured@garage.com",
            contact_phone="+447000888999",
            status=SellerApplicationStatusChoices.PENDING,
        )

        res = admin_client.post(
            f"/api/v1/admin/seller-applications/{app.id}/review/",
            {"action": "APPROVE"},
            format="json",
        )
        assert res.status_code == status.HTTP_200_OK

        app.refresh_from_db()
        profile = app.organisation.workshop_profile
        assert profile.is_accepting_bookings is False

        # Create a separate buyer user
        buyer = User.objects.create_user(
            email="customer@example.co.uk",
            password="Password123!",
            first_name="Jane",
            last_name="Customer",
        )

        booking_payload = {
            "workshop_id": str(profile.id),
            "vehicle_id": str(buyer_vehicle.id),
            "preferred_date": "2026-12-01",
        }

        # Attempt to book unconfigured workshop -> must raise validation error
        with pytest.raises(DjangoValidationError) as exc:
            BookingService.create_booking(buyer=buyer, data=booking_payload)
        assert "not accepting new bookings" in str(exc.value).lower()

        # Owner configures workshop profile and enables bookings
        profile.is_accepting_bookings = True
        profile.save(update_fields=["is_accepting_bookings"])

        # Now booking succeeds
        buyer_vehicle.user = buyer
        buyer_vehicle.save(update_fields=["user"])

        booking = BookingService.create_booking(buyer=buyer, data=booking_payload)
        assert booking is not None
        assert booking.workshop == profile

