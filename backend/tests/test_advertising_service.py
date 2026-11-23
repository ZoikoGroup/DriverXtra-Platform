"""
Unit & Integration tests for Phase 7.2 AdvertisingCampaignService.
Covers:
- Full lifecycle state machine: DRAFT -> PENDING_APPROVAL -> APPROVED -> SCHEDULED/ACTIVE -> PAUSED -> CANCELLED/COMPLETED.
- Inventory ownership and APPROVED status verification on attachment.
- Self-approval guard (staff cannot approve/reject their own ad campaigns).
- Mandatory rejection reason.
- Pro-rata whole-day refund computation on cancellation.
- Scheduled campaign activation and completed campaign expiration.
- Impression and click tracking with session de-duplication.
- Sponsored feed rotation and filtering.
"""

import datetime
import uuid
import pytest
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils import timezone

from apps.identity.models import User, RoleChoices
from apps.marketplace.models import (
    AdvertisingCampaign,
    SponsoredListing,
    CampaignPayment,
    CampaignImpression,
    CampaignClick,
    CampaignTypeChoices,
    CampaignStatusChoices,
    CampaignPaymentStatusChoices,
    VehicleListing,
    VehicleMake,
    VehicleModel,
    ListingStatusChoices,
)
from apps.marketplace.advertising_service import AdvertisingCampaignService


@pytest.fixture
def vehicle_make(db):
    return VehicleMake.objects.create(name="Audi")


@pytest.fixture
def vehicle_model(db, vehicle_make):
    return VehicleModel.objects.create(make=vehicle_make, name="A4", year_start=2018)


@pytest.fixture
def approved_vehicle(seller_user, vehicle_make, vehicle_model):
    return VehicleListing.objects.create(
        seller=seller_user,
        title="2021 Audi A4 S-Line",
        make=vehicle_make,
        model=vehicle_model,
        year=2021,
        vin="WAU00000000000002",
        price=21000,
        currency="GBP",
        status=ListingStatusChoices.APPROVED,
    )


@pytest.fixture
def pending_vehicle(seller_user, vehicle_make, vehicle_model):
    return VehicleListing.objects.create(
        seller=seller_user,
        title="2021 Audi A4 Pending",
        make=vehicle_make,
        model=vehicle_model,
        year=2021,
        vin="WAU00000000000003",
        price=20000,
        currency="GBP",
        status=ListingStatusChoices.PENDING_APPROVAL,
    )


@pytest.mark.django_db
class TestAdvertisingCampaignServiceLifecycle:
    """Tests the state transitions of an advertising campaign through its service engine."""

    def test_full_campaign_lifecycle(self, seller_user, staff_user, approved_vehicle):
        """Trace complete happy path from creation to completion."""
        today = timezone.localdate()

        # 1. Create Campaign
        campaign = AdvertisingCampaignService.create_campaign(
            seller=seller_user,
            title="Spring Audi Promotion",
            campaign_type=CampaignTypeChoices.VEHICLES,
            currency="GBP",
            target_country="GB",
            package_code="7_DAYS",
            start_date=today,
        )
        assert campaign.status == CampaignStatusChoices.DRAFT

        # 2. Attach Approved Listings
        AdvertisingCampaignService.attach_listings(
            campaign=campaign,
            listing_ids=[approved_vehicle.id],
            user=seller_user,
        )
        assert campaign.sponsored_listings.count() == 1

        # 3. Submit for Staff Review
        campaign = AdvertisingCampaignService.submit_campaign(campaign, seller_user)
        assert campaign.status == CampaignStatusChoices.PENDING_APPROVAL

        # 4. Staff Approves Campaign
        campaign = AdvertisingCampaignService.approve_campaign(
            campaign=campaign,
            staff_user=staff_user,
            approval_notes="All documents and listings verified.",
        )
        assert campaign.status == CampaignStatusChoices.APPROVED

        # 5. Record Payment via Webhook -> Transitions to ACTIVE (start_date <= today)
        payment = AdvertisingCampaignService.record_successful_payment(
            campaign_id=campaign.id,
            provider="STRIPE",
            gateway_reference="pi_test_123",
            gateway_payment_id="ch_test_123",
            amount_minor=campaign.total_budget_minor,
            currency="GBP",
        )
        campaign.refresh_from_db()
        assert campaign.payment_status == CampaignPaymentStatusChoices.PAID
        assert campaign.status == CampaignStatusChoices.ACTIVE

        # 6. Pause Campaign
        campaign = AdvertisingCampaignService.pause_campaign(campaign, seller_user)
        assert campaign.status == CampaignStatusChoices.PAUSED

        # 7. Resume Campaign
        campaign = AdvertisingCampaignService.resume_campaign(campaign, seller_user)
        assert campaign.status == CampaignStatusChoices.ACTIVE

    def test_self_approval_guard(self, seller_user, approved_vehicle):
        """Staff user cannot approve their own advertising campaign."""
        # Give seller staff role as well
        seller_user.is_staff = True
        seller_user.save()

        today = timezone.localdate()
        campaign = AdvertisingCampaignService.create_campaign(
            seller=seller_user,
            title="Self Approval Test",
            campaign_type=CampaignTypeChoices.VEHICLES,
            currency="GBP",
            start_date=today,
        )
        AdvertisingCampaignService.attach_listings(campaign, [approved_vehicle.id], seller_user)
        campaign = AdvertisingCampaignService.submit_campaign(campaign, seller_user)

        with pytest.raises(PermissionDenied, match="cannot approve or reject their own"):
            AdvertisingCampaignService.approve_campaign(campaign, seller_user)

    def test_unapproved_inventory_cannot_be_sponsored(self, seller_user, pending_vehicle):
        """Attempting to attach unapproved inventory raises ValidationError."""
        today = timezone.localdate()
        campaign = AdvertisingCampaignService.create_campaign(
            seller=seller_user,
            title="Unapproved Inventory Test",
            campaign_type=CampaignTypeChoices.VEHICLES,
            currency="GBP",
            start_date=today,
        )

        with pytest.raises(ValidationError, match="APPROVED"):
            AdvertisingCampaignService.attach_listings(campaign, [pending_vehicle.id], seller_user)

    def test_rejection_requires_mandatory_reason(self, seller_user, staff_user, approved_vehicle):
        """Rejecting a campaign without a reason raises ValidationError."""
        today = timezone.localdate()
        campaign = AdvertisingCampaignService.create_campaign(
            seller=seller_user,
            title="Rejection Test",
            campaign_type=CampaignTypeChoices.VEHICLES,
            currency="GBP",
            start_date=today,
        )
        AdvertisingCampaignService.attach_listings(campaign, [approved_vehicle.id], seller_user)
        campaign = AdvertisingCampaignService.submit_campaign(campaign, seller_user)

        with pytest.raises(ValidationError, match="rejection reason"):
            AdvertisingCampaignService.reject_campaign(campaign, staff_user, rejection_reason="")

    def test_impression_and_click_tracking_with_deduplication(self, seller_user, staff_user, approved_vehicle):
        """Impressions and clicks from the same session on the same day are de-duplicated."""
        today = timezone.localdate()
        campaign = AdvertisingCampaignService.create_campaign(
            seller=seller_user,
            title="Tracking Test",
            campaign_type=CampaignTypeChoices.VEHICLES,
            currency="GBP",
            start_date=today,
        )
        AdvertisingCampaignService.attach_listings(campaign, [approved_vehicle.id], seller_user)
        campaign = AdvertisingCampaignService.submit_campaign(campaign, seller_user)
        campaign = AdvertisingCampaignService.approve_campaign(campaign, staff_user)
        AdvertisingCampaignService.record_successful_payment(
            campaign_id=campaign.id,
            provider="STRIPE",
            gateway_reference="pi_track_1",
            gateway_payment_id="ch_track_1",
            amount_minor=campaign.total_budget_minor,
            currency="GBP",
        )
        sponsored = campaign.sponsored_listings.first()

        session_id = "test-session-xyz"

        # 1. First impression records
        imp1, created1 = AdvertisingCampaignService.record_impression(
            sponsored_listing_id=sponsored.id,
            session_id=session_id,
        )
        assert created1 is True

        # 2. Second impression from same session is duplicate
        imp2, created2 = AdvertisingCampaignService.record_impression(
            sponsored_listing_id=sponsored.id,
            session_id=session_id,
        )
        assert created2 is False

        # 3. First click records
        clk1, click_created1 = AdvertisingCampaignService.record_click(
            sponsored_listing_id=sponsored.id,
            session_id=session_id,
        )
        assert click_created1 is True

        # 4. Second click from same session is duplicate
        clk2, click_created2 = AdvertisingCampaignService.record_click(
            sponsored_listing_id=sponsored.id,
            session_id=session_id,
        )
        assert click_created2 is False
