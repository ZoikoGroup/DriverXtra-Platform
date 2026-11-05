import uuid
from datetime import date, timedelta
from decimal import Decimal
import pytest
from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework import status
from rest_framework.test import APIClient

from apps.identity.models import User, RoleChoices
from apps.organisations.models import Organisation, OrganisationMembership, OrganisationRoleChoices, OrganisationTypeChoices
from apps.garage.models import GarageVehicle
from apps.notifications.models import Notification
from platform_core.audit.models import AuditLog
from apps.workshops.models import (
    WorkshopProfile,
    WorkshopBooking,
    WorkshopQuotation,
    QuotationLineItem,
    WorkOrder,
    WorkOrderTask,
    BookingStatusChoices,
    QuotationStatusChoices,
    WorkOrderStatusChoices,
    WorkOrderTaskStatusChoices,
    LineItemTypeChoices,
    WorkshopReview,
    ReviewStatusChoices,
)
from apps.workshops.services import WorkshopReviewService, QuotationService


@pytest.fixture
def workshop_owner(db):
    user = User.objects.create_user(
        email='apex_owner@apexmotors.co.uk',
        password='SecurePassword123!',
        first_name='Arthur',
        last_name='Apex',
        phone_number='+447111000111',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.WORKSHOP)
    return user


@pytest.fixture
def workshop_tech(db):
    user = User.objects.create_user(
        email='apex_tech@apexmotors.co.uk',
        password='SecurePassword123!',
        first_name='Timothy',
        last_name='Torque',
        phone_number='+447111000222',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.WORKSHOP)
    return user


@pytest.fixture
def other_workshop_user(db):
    user = User.objects.create_user(
        email='other_ws@external.com',
        password='SecurePassword123!',
        first_name='Oscar',
        last_name='Other',
        phone_number='+447111000333',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.WORKSHOP)
    return user


@pytest.fixture
def buyer(db):
    user = User.objects.create_user(
        email='customer_charlie@driverxtra.com',
        password='SecurePassword123!',
        first_name='Charlie',
        last_name='Customer',
        phone_number='+447222000111',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.fixture
def other_buyer(db):
    user = User.objects.create_user(
        email='intruder_ian@driverxtra.com',
        password='SecurePassword123!',
        first_name='Ian',
        last_name='Intruder',
        phone_number='+447222000222',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.fixture
def staff_admin(db):
    user = User.objects.create_user(
        email='admin_staff@driverxtra.com',
        password='SecurePassword123!',
        first_name='Sarah',
        last_name='Staff',
        is_staff=True,
        is_email_verified=True,
    )
    user.add_role(RoleChoices.STAFF)
    return user


@pytest.fixture
def workshop_org(db, workshop_owner, workshop_tech):
    org = Organisation.objects.create(
        name="Apex Motors Group Ltd",
        type=OrganisationTypeChoices.WORKSHOP,
        created_by=workshop_owner,
    )
    org.add_member(workshop_owner, role=OrganisationRoleChoices.OWNER)
    org.add_member(workshop_tech, role=OrganisationRoleChoices.TECHNICIAN)
    return org


@pytest.fixture
def workshop(db, workshop_org):
    return WorkshopProfile.objects.create(
        organisation=workshop_org,
        business_name="Apex Auto Services Ltd",
        slug="apex-auto-services",
        city="Manchester",
        postal_code="M1 1AA",
        address_line1="10 Industrial Park",
        contact_email="service@apexmotors.co.uk",
        contact_phone="+441619998888",
        bay_capacity=4,
        is_tax_registered=True,
        can_collect_tax=True,
        default_tax_rate_percent=Decimal('20.00'),
        is_accepting_bookings=True,
        is_verified=True,
    )


@pytest.fixture
def vehicle(db, buyer):
    return GarageVehicle.objects.create(
        user=buyer,
        make="Audi",
        model="A4",
        year=2021,
        registration_plate="GF21 XTR",
        vin="WAUZZZF41MA012345",
        current_odometer=45000,
        odometer_unit="mi",
    )


@pytest.fixture
def completed_service(db, workshop, buyer, vehicle):
    """
    Creates an end-to-end completed service with a confirmed booking and completed work order.
    """
    booking = WorkshopBooking.objects.create(
        workshop=workshop,
        buyer=buyer,
        vehicle=vehicle,
        vehicle_make=vehicle.make,
        vehicle_model=vehicle.model,
        vehicle_year=vehicle.year,
        vehicle_registration_plate=vehicle.registration_plate,
        vehicle_vin=vehicle.vin,
        current_odometer=vehicle.current_odometer,
        odometer_unit=vehicle.odometer_unit,
        preferred_date=date.today() + timedelta(days=2),
        preferred_time_slot="Morning (08:30 - 12:00)",
        status=BookingStatusChoices.CONFIRMED,
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
        description="Class 4 MOT Test & Health Check",
        quantity=Decimal('1.00'),
        unit_price=Decimal('54.17'),
        line_total=Decimal('54.17'),
    )
    quote.recalculate_totals(commit=True)
    quote.status = QuotationStatusChoices.ACCEPTED
    quote.save(update_fields=['status'])

    completed_time = timezone.now() - timedelta(hours=3)
    work_order = WorkOrder.objects.create(
        booking=booking,
        quotation=quote,
        workshop=workshop,
        buyer=buyer,
        vehicle=vehicle,
        vehicle_registration_plate=vehicle.registration_plate,
        vehicle_vin=vehicle.vin,
        status=WorkOrderStatusChoices.COMPLETED,
        started_at=completed_time - timedelta(hours=2),
        completed_at=completed_time,
        quality_inspected_at=completed_time,
    )

    return booking, work_order


# =============================================================================
# 1. MODEL & INTEGRITY TESTS
# =============================================================================

@pytest.mark.django_db
class TestWorkshopReviewModel:
    def test_review_creation_and_fields(self, completed_service, buyer):
        booking, work_order = completed_service
        review = WorkshopReview.objects.create(
            workshop=booking.workshop,
            booking=booking,
            work_order=work_order,
            buyer=buyer,
            rating=5,
            communication_rating=5,
            workmanship_rating=4,
            pricing_transparency_rating=5,
            title="Exceptional Service",
            comment="The MOT was conducted thoroughly and vehicle was returned spotless.",
            status=ReviewStatusChoices.APPROVED,
            is_verified_service=True,
        )
        assert review.id is not None
        assert review.rating == 5
        assert review.is_verified_service is True
        assert review.status == ReviewStatusChoices.APPROVED
        assert "5★" in str(review)

    def test_booking_unique_constraint(self, completed_service, buyer):
        booking, work_order = completed_service
        WorkshopReview.objects.create(
            workshop=booking.workshop,
            booking=booking,
            work_order=work_order,
            buyer=buyer,
            rating=5,
            comment="Great work done.",
        )
        # Attempt duplicate creation for the same booking
        with pytest.raises(IntegrityError):
            WorkshopReview.objects.create(
                workshop=booking.workshop,
                booking=booking,
                work_order=work_order,
                buyer=buyer,
                rating=4,
                comment="Another review for the same booking.",
            )

    def test_clean_validation_workshop_mismatch(self, completed_service, buyer):
        booking, work_order = completed_service
        # Create a second workshop
        other_org = Organisation.objects.create(name="Other WS", type=OrganisationTypeChoices.WORKSHOP)
        other_ws = WorkshopProfile.objects.create(organisation=other_org, business_name="Other Motors", slug="other-motors")

        review = WorkshopReview(
            workshop=other_ws,  # Mismatch with booking.workshop
            booking=booking,
            work_order=work_order,
            buyer=buyer,
            rating=5,
            comment="Mismatch test.",
        )
        with pytest.raises(DjangoValidationError) as exc:
            review.clean()
        assert "Booking does not belong to this workshop" in str(exc.value)

    def test_clean_validation_work_order_mismatch(self, completed_service, buyer, workshop, vehicle):
        booking, work_order = completed_service
        # Create another booking and work order
        booking2 = WorkshopBooking.objects.create(
            workshop=workshop,
            buyer=buyer,
            vehicle=vehicle,
            preferred_date=date.today() + timedelta(days=2),
            status=BookingStatusChoices.CONFIRMED,
        )
        q2 = WorkshopQuotation.objects.create(
            booking=booking2,
            version=1,
            status=QuotationStatusChoices.ISSUED,
            tax_rate_percent=Decimal('20.00'),
            valid_until=date.today() + timedelta(days=14),
        )
        q2.status = QuotationStatusChoices.ACCEPTED
        q2.save(update_fields=['status'])
        wo2 = WorkOrder.objects.create(
            booking=booking2,
            quotation=q2,
            workshop=workshop,
            buyer=buyer,
            vehicle=vehicle,
            status=WorkOrderStatusChoices.COMPLETED,
            completed_at=timezone.now(),
        )

        review = WorkshopReview(
            workshop=workshop,
            booking=booking,
            work_order=wo2,  # Belongs to booking2, not booking
            buyer=buyer,
            rating=5,
            comment="Work order mismatch test.",
        )
        with pytest.raises(DjangoValidationError) as exc:
            review.clean()
        assert "Work order does not belong to this booking" in str(exc.value)


# =============================================================================
# 2. ELIGIBILITY SERVICE TESTS
# =============================================================================

@pytest.mark.django_db
class TestWorkshopReviewEligibility:
    def test_eligible_completed_service(self, completed_service, buyer):
        booking, work_order = completed_service
        is_eligible, reason, wo = WorkshopReviewService.check_review_eligibility(booking, buyer)
        assert is_eligible is True
        assert "Eligible" in reason
        assert wo.id == work_order.id

    def test_wrong_buyer_ineligible(self, completed_service, other_buyer):
        booking, _ = completed_service
        is_eligible, reason, _ = WorkshopReviewService.check_review_eligibility(booking, other_buyer)
        assert is_eligible is False
        assert "only review bookings placed by your account" in reason

    def test_cancelled_booking_ineligible(self, completed_service, buyer):
        booking, _ = completed_service
        booking.status = BookingStatusChoices.CANCELLED
        booking.save()
        is_eligible, reason, _ = WorkshopReviewService.check_review_eligibility(booking, buyer)
        assert is_eligible is False
        assert "cancelled" in reason.lower()

    def test_missing_work_order_ineligible(self, workshop, buyer, vehicle):
        booking = WorkshopBooking.objects.create(
            workshop=workshop,
            buyer=buyer,
            vehicle=vehicle,
            preferred_date=date.today() + timedelta(days=2),
            status=BookingStatusChoices.CONFIRMED,
        )
        is_eligible, reason, _ = WorkshopReviewService.check_review_eligibility(booking, buyer)
        assert is_eligible is False
        assert "No work order found" in reason

    def test_incomplete_work_order_ineligible(self, completed_service, buyer):
        booking, work_order = completed_service
        work_order.status = WorkOrderStatusChoices.IN_PROGRESS
        work_order.save()
        is_eligible, reason, _ = WorkshopReviewService.check_review_eligibility(booking, buyer)
        assert is_eligible is False
        assert "COMPLETED" in reason

    def test_missing_completed_at_ineligible(self, completed_service, buyer):
        booking, work_order = completed_service
        work_order.completed_at = None
        work_order.save()
        is_eligible, reason, _ = WorkshopReviewService.check_review_eligibility(booking, buyer)
        assert is_eligible is False
        assert "no recorded completion date" in reason

    def test_already_reviewed_ineligible(self, completed_service, buyer):
        booking, work_order = completed_service
        WorkshopReview.objects.create(
            workshop=booking.workshop,
            booking=booking,
            work_order=work_order,
            buyer=buyer,
            rating=5,
            comment="First review.",
        )
        is_eligible, reason, _ = WorkshopReviewService.check_review_eligibility(booking, buyer)
        assert is_eligible is False
        assert "already been submitted" in reason


# =============================================================================
# 3. CREATION SERVICE, AUDIT & NOTIFICATION TESTS
# =============================================================================

@pytest.mark.django_db
class TestWorkshopReviewCreationService:
    def test_create_review_success_with_audit_and_notification(self, completed_service, buyer, workshop_owner):
        booking, work_order = completed_service
        review = WorkshopReviewService.create_review(
            booking=booking,
            buyer=buyer,
            data={
                "rating": 5,
                "title": "Superb MOT",
                "comment": "Quick turnaround and transparent advisories.",
                "communication_rating": 5,
                "workmanship_rating": 5,
                "pricing_transparency_rating": 4,
            },
        )
        assert review.id is not None
        assert review.status == ReviewStatusChoices.APPROVED
        assert review.is_verified_service is True
        assert review.communication_rating == 5
        assert review.pricing_transparency_rating == 4

        # Check audit entry
        audit = AuditLog.objects.filter(event_type="workshop.review.created", resource_id=str(review.id)).first()
        assert audit is not None
        assert audit.action == "workshop:review.create"
        assert audit.actor_id == buyer.id
        assert audit.metadata["rating"] == 5

        # Check notification dispatched to workshop owner
        notif = Notification.objects.filter(recipient=workshop_owner, event_type="workshop.review.created").first()
        assert notif is not None
        assert "New Customer Review" in notif.title
        assert "5★ review" in notif.message

    def test_invalid_rating_rejection(self, completed_service, buyer):
        booking, _ = completed_service
        # Rating 0
        with pytest.raises(DjangoValidationError) as exc:
            WorkshopReviewService.create_review(
                booking=booking,
                buyer=buyer,
                data={"rating": 0, "comment": "Valid comment here."},
            )
        assert "between 1 and 5" in str(exc.value)

        # Rating 6
        with pytest.raises(DjangoValidationError) as exc:
            WorkshopReviewService.create_review(
                booking=booking,
                buyer=buyer,
                data={"rating": 6, "comment": "Valid comment here."},
            )
        assert "between 1 and 5" in str(exc.value)

    def test_short_comment_rejection(self, completed_service, buyer):
        booking, _ = completed_service
        with pytest.raises(DjangoValidationError) as exc:
            WorkshopReviewService.create_review(
                booking=booking,
                buyer=buyer,
                data={"rating": 5, "comment": "Bad"},
            )
        assert "at least 5 characters" in str(exc.value)

    def test_duplicate_review_service_rejection(self, completed_service, buyer):
        booking, _ = completed_service
        WorkshopReviewService.create_review(
            booking=booking,
            buyer=buyer,
            data={"rating": 5, "comment": "Original review."},
        )
        with pytest.raises(DjangoValidationError) as exc:
            WorkshopReviewService.create_review(
                booking=booking,
                buyer=buyer,
                data={"rating": 4, "comment": "Attempting second review."},
            )
        assert "already been submitted" in str(exc.value)


# =============================================================================
# 4. WORKSHOP REPLY & MODERATION TESTS
# =============================================================================

@pytest.mark.django_db
class TestWorkshopReviewReplyAndModeration:
    @pytest.fixture
    def active_review(self, completed_service, buyer):
        booking, work_order = completed_service
        return WorkshopReviewService.create_review(
            booking=booking,
            buyer=buyer,
            data={"rating": 5, "comment": "Very satisfied with the workmanship."},
        )

    def test_workshop_owner_reply_success(self, active_review, workshop_owner, buyer):
        reply_text = "Thank you Charlie! It was a pleasure servicing your Audi A4."
        updated = WorkshopReviewService.reply_to_review(active_review, workshop_owner, reply_text)
        assert updated.workshop_reply == reply_text
        assert updated.workshop_reply_at is not None
        assert updated.workshop_replied_by == workshop_owner

        # Check audit entry
        audit = AuditLog.objects.filter(event_type="workshop.review.replied", resource_id=str(active_review.id)).first()
        assert audit is not None
        assert audit.action == "workshop:review.reply"

        # Check notification dispatched to buyer
        notif = Notification.objects.filter(recipient=buyer, event_type="workshop.review.replied").first()
        assert notif is not None
        assert "replied to your review" in notif.title

    def test_workshop_tech_reply_success(self, active_review, workshop_tech):
        reply_text = "Glad to help get your vehicle in top condition!"
        updated = WorkshopReviewService.reply_to_review(active_review, workshop_tech, reply_text)
        assert updated.workshop_reply == reply_text
        assert updated.workshop_replied_by == workshop_tech

    def test_unauthorized_user_reply_rejection(self, active_review, other_workshop_user):
        from django.core.exceptions import PermissionDenied
        with pytest.raises(PermissionDenied):
            WorkshopReviewService.reply_to_review(active_review, other_workshop_user, "Unauthorized reply.")

    def test_duplicate_reply_rejection(self, active_review, workshop_owner):
        WorkshopReviewService.reply_to_review(active_review, workshop_owner, "First reply.")
        with pytest.raises(DjangoValidationError) as exc:
            WorkshopReviewService.reply_to_review(active_review, workshop_owner, "Second reply.")
        assert "already been posted" in str(exc.value)

    def test_admin_moderation(self, active_review, staff_admin):
        # Admin flags review
        moderated = WorkshopReviewService.moderate_review(
            active_review,
            staff_admin,
            ReviewStatusChoices.FLAGGED,
            reason="Review under investigation for disputed charges",
        )
        assert moderated.status == ReviewStatusChoices.FLAGGED

        # Check audit entry
        audit = AuditLog.objects.filter(event_type="workshop.review.moderated", resource_id=str(active_review.id)).first()
        assert audit is not None
        assert audit.metadata["new_status"] == ReviewStatusChoices.FLAGGED

    def test_non_staff_cannot_moderate(self, active_review, buyer):
        from django.core.exceptions import PermissionDenied
        with pytest.raises(PermissionDenied):
            WorkshopReviewService.moderate_review(active_review, buyer, ReviewStatusChoices.REJECTED)


# =============================================================================
# 5. REPUTATION SUMMARY & AGGREGATION TESTS
# =============================================================================

@pytest.mark.django_db
class TestWorkshopReputationSummary:
    def test_summary_with_multiple_reviews(self, workshop, buyer, other_buyer, vehicle):
        # Create vehicle for other buyer
        other_vehicle = GarageVehicle.objects.create(
            user=other_buyer,
            make="BMW",
            model="118i",
            year=2020,
            registration_plate="AB20 XYZ",
            vin="WBA118I2020XYZ111",
            current_odometer=30000,
            odometer_unit="mi",
        )

        # Helper to create a completed booking
        def create_service(customer, veh):
            b = WorkshopBooking.objects.create(
                workshop=workshop,
                buyer=customer,
                vehicle=veh,
                vehicle_registration_plate=veh.registration_plate,
                preferred_date=date.today() + timedelta(days=2),
                status=BookingStatusChoices.CONFIRMED,
            )
            q = WorkshopQuotation.objects.create(
                booking=b,
                version=1,
                status=QuotationStatusChoices.ISSUED,
                tax_rate_percent=Decimal('20.00'),
                valid_until=date.today() + timedelta(days=14),
            )
            q.status = QuotationStatusChoices.ACCEPTED
            q.save(update_fields=['status'])
            wo = WorkOrder.objects.create(
                booking=b,
                quotation=q,
                workshop=workshop,
                buyer=customer,
                vehicle=veh,
                status=WorkOrderStatusChoices.COMPLETED,
                completed_at=timezone.now(),
            )
            return b, wo

        b1, wo1 = create_service(buyer, vehicle)
        b2, wo2 = create_service(other_buyer, other_vehicle)

        # Review 1: 5 stars
        WorkshopReviewService.create_review(
            b1, buyer,
            {"rating": 5, "comment": "Perfect service 5/5.", "communication_rating": 5, "workmanship_rating": 5, "pricing_transparency_rating": 4},
        )
        # Review 2: 4 stars
        WorkshopReviewService.create_review(
            b2, other_buyer,
            {"rating": 4, "comment": "Good job overall 4/5.", "communication_rating": 4, "workmanship_rating": 4, "pricing_transparency_rating": 4},
        )

        summary = WorkshopReviewService.get_workshop_reputation_summary(workshop)
        assert summary["total_reviews"] == 2
        assert summary["average_rating"] == 4.5
        assert summary["distribution"]["5"] == 1
        assert summary["distribution"]["4"] == 1
        assert summary["distribution"]["3"] == 0
        assert summary["sub_ratings"]["communication"] == 4.5
        assert summary["sub_ratings"]["workmanship"] == 4.5
        assert summary["sub_ratings"]["pricing_transparency"] == 4.0

    def test_empty_workshop_summary(self, workshop):
        summary = WorkshopReviewService.get_workshop_reputation_summary(workshop)
        assert summary["total_reviews"] == 0
        assert summary["average_rating"] == 0.0
        assert summary["distribution"]["5"] == 0


# =============================================================================
# 6. REST API ENDPOINT TESTS
# =============================================================================

@pytest.mark.django_db
class TestWorkshopReviewAPIEndpoints:
    def test_buyer_check_eligibility_endpoint(self, completed_service, buyer):
        booking, _ = completed_service
        client = APIClient()
        client.force_authenticate(user=buyer)

        url = f"/api/v1/workshops/bookings/{booking.id}/review-eligibility/"
        resp = client.get(url)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["is_eligible"] is True
        assert data["booking_number"] == booking.booking_number
        assert data["workshop_name"] == booking.workshop.business_name

    def test_other_buyer_eligibility_forbidden(self, completed_service, other_buyer):
        booking, _ = completed_service
        client = APIClient()
        client.force_authenticate(user=other_buyer)

        url = f"/api/v1/workshops/bookings/{booking.id}/review-eligibility/"
        resp = client.get(url)
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_buyer_submit_review_api_success(self, completed_service, buyer):
        booking, _ = completed_service
        client = APIClient()
        client.force_authenticate(user=buyer)

        url = f"/api/v1/workshops/bookings/{booking.id}/review/"
        payload = {
            "rating": 5,
            "title": "Great turnaround time",
            "comment": "Diagnosed and repaired smoothly within the day.",
            "communication_rating": 5,
            "workmanship_rating": 5,
            "pricing_transparency_rating": 4,
        }
        resp = client.post(url, data=payload, format='json')
        assert resp.status_code == status.HTTP_201_CREATED
        data = resp.json()
        assert data["rating"] == 5
        assert data["title"] == "Great turnaround time"
        assert data["is_verified_service"] is True
        assert data["buyer_name"] == "Charlie C."
        assert "Audi" in data["vehicle_display"]

    def test_buyer_submit_duplicate_review_api_fails(self, completed_service, buyer):
        booking, _ = completed_service
        client = APIClient()
        client.force_authenticate(user=buyer)

        url = f"/api/v1/workshops/bookings/{booking.id}/review/"
        payload = {"rating": 5, "comment": "First review."}
        resp1 = client.post(url, data=payload, format='json')
        assert resp1.status_code == status.HTTP_201_CREATED

        # Second attempt
        resp2 = client.post(url, data={"rating": 4, "comment": "Second review attempt."}, format='json')
        assert resp2.status_code == status.HTTP_400_BAD_REQUEST

    def test_public_reviews_list_shows_only_approved(self, completed_service, buyer, workshop):
        booking, work_order = completed_service
        # Create approved review
        WorkshopReview.objects.create(
            workshop=workshop,
            booking=booking,
            work_order=work_order,
            buyer=buyer,
            rating=5,
            comment="Approved review.",
            status=ReviewStatusChoices.APPROVED,
        )

        client = APIClient()
        url = f"/api/v1/workshops/{workshop.slug}/reviews/"
        resp = client.get(url)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["count"] == 1
        assert len(data["results"]) == 1
        assert data["results"][0]["rating"] == 5
        assert "reputation" in data
        assert data["reputation"]["average_rating"] == 5.0

    def test_public_reviews_list_excludes_flagged_or_rejected(self, completed_service, buyer, workshop):
        booking, work_order = completed_service
        WorkshopReview.objects.create(
            workshop=workshop,
            booking=booking,
            work_order=work_order,
            buyer=buyer,
            rating=1,
            comment="Under dispute.",
            status=ReviewStatusChoices.FLAGGED,
        )

        client = APIClient()
        url = f"/api/v1/workshops/{workshop.slug}/reviews/"
        resp = client.get(url)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["count"] == 0
        assert len(data["results"]) == 0

    def test_workshop_reply_api(self, completed_service, buyer, workshop, workshop_owner):
        booking, work_order = completed_service
        review = WorkshopReview.objects.create(
            workshop=workshop,
            booking=booking,
            work_order=work_order,
            buyer=buyer,
            rating=5,
            comment="Great team and excellent diagnostics.",
            status=ReviewStatusChoices.APPROVED,
        )

        client = APIClient()
        client.force_authenticate(user=workshop_owner)

        url = f"/api/v1/workshops/manage/reviews/{review.id}/reply/"
        resp = client.post(url, data={"reply": "Thank you for trusting Apex Auto Services!"}, format='json')
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["workshop_reply"] == "Thank you for trusting Apex Auto Services!"
        assert data["workshop_reply_at"] is not None

    def test_admin_review_moderation_api(self, completed_service, buyer, workshop, staff_admin):
        booking, work_order = completed_service
        review = WorkshopReview.objects.create(
            workshop=workshop,
            booking=booking,
            work_order=work_order,
            buyer=buyer,
            rating=5,
            comment="Test review for moderation.",
            status=ReviewStatusChoices.APPROVED,
        )

        client = APIClient()
        client.force_authenticate(user=staff_admin)

        # List all admin reviews
        list_resp = client.get("/api/v1/workshops/admin/reviews/")
        assert list_resp.status_code == status.HTTP_200_OK
        assert list_resp.json()["count"] >= 1

        # Moderate review
        mod_url = f"/api/v1/workshops/admin/reviews/{review.id}/moderate/"
        mod_resp = client.post(
            mod_url,
            data={"status": "FLAGGED", "moderation_reason": "Contains sensitive customer plate data"},
            format='json',
        )
        assert mod_resp.status_code == status.HTTP_200_OK
        assert mod_resp.json()["status"] == "FLAGGED"

    def test_workshop_public_list_annotated_rating(self, completed_service, buyer, workshop):
        booking, work_order = completed_service
        WorkshopReview.objects.create(
            workshop=workshop,
            booking=booking,
            work_order=work_order,
            buyer=buyer,
            rating=5,
            comment="5-star rating test.",
            status=ReviewStatusChoices.APPROVED,
        )

        client = APIClient()
        resp = client.get("/api/v1/workshops/")
        assert resp.status_code == status.HTTP_200_OK
        ws_list = resp.json()["results"]
        matching = next((w for w in ws_list if str(w["id"]) == str(workshop.id)), None)
        assert matching is not None
        assert matching["average_rating"] == 5.0
        assert matching["review_count"] == 1
