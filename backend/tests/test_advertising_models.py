"""
Unit tests for Phase 7.2 Sponsored Listings & Advertising database models.
Covers:
- AdvertisingCampaign model constraints, properties, status transitions.
- SponsoredListing model XOR constraint (vehicle XOR part) and CTR property.
- CampaignPayment model and gateway references.
- CampaignImpression and CampaignClick session de-duplication constraints.
- CampaignDailyMetric aggregates.
"""

import uuid
import datetime
import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.identity.models import User, RoleChoices
from apps.marketplace.models import (
    AdvertisingCampaign,
    SponsoredListing,
    CampaignPayment,
    CampaignImpression,
    CampaignClick,
    CampaignDailyMetric,
    CampaignTypeChoices,
    CampaignStatusChoices,
    CampaignPaymentStatusChoices,
    VehicleListing,
    VehicleMake,
    VehicleModel,
    SparePartListing,
    PartCategory,
    ListingStatusChoices,
)


@pytest.fixture
def vehicle_make(db):
    return VehicleMake.objects.create(name="BMW")


@pytest.fixture
def vehicle_model(db, vehicle_make):
    return VehicleModel.objects.create(make=vehicle_make, name="3 Series", year_start=2019)


@pytest.fixture
def part_category(db):
    return PartCategory.objects.create(name="Braking Systems")


@pytest.fixture
def sample_vehicle_listing(seller_user, vehicle_make, vehicle_model):
    return VehicleListing.objects.create(
        seller=seller_user,
        title="2022 BMW 320i M Sport",
        make=vehicle_make,
        model=vehicle_model,
        year=2022,
        vin="WBA00000000000001",
        price=24500,
        currency="GBP",
        status=ListingStatusChoices.APPROVED,
    )


@pytest.fixture
def sample_part_listing(seller_user, part_category):
    return SparePartListing.objects.create(
        seller=seller_user,
        name="Brembo Front Brake Pads Set",
        brand="Brembo",
        mpn="BRK-00123",
        category=part_category,
        price=85,
        currency="GBP",
        stock_quantity=10,
        status=ListingStatusChoices.APPROVED,
    )


@pytest.mark.django_db
class TestAdvertisingCampaignModel:
    """Tests for AdvertisingCampaign model attributes, properties and constraints."""

    def test_campaign_creation_with_defaults(self, seller_user):
        """Creates campaign with default draft state and valid properties."""
        today = timezone.localdate()
        campaign = AdvertisingCampaign.objects.create(
            seller=seller_user,
            title="Spring 2026 Vehicle Spotlight",
            campaign_type=CampaignTypeChoices.VEHICLES,
            currency="GBP",
            package_code="7_DAYS",
            start_date=today,
            end_date=today + datetime.timedelta(days=6),
            total_budget_minor=4200,
            daily_rate_minor=600,
        )

        assert isinstance(campaign.id, uuid.UUID)
        assert campaign.status == CampaignStatusChoices.DRAFT
        assert campaign.payment_status == CampaignPaymentStatusChoices.UNPAID
        assert campaign.is_eligible_for_serving is False
        assert campaign.click_through_rate == 0.0
        assert campaign.remaining_budget_minor == 4200
        assert campaign.duration_days == 7

    def test_campaign_ctr_property(self, seller_user):
        """Verify CTR property computes accurate percentage with 2 decimal places."""
        today = timezone.localdate()
        campaign = AdvertisingCampaign.objects.create(
            seller=seller_user,
            title="CTR Test Campaign",
            campaign_type=CampaignTypeChoices.VEHICLES,
            currency="GBP",
            start_date=today,
            end_date=today + datetime.timedelta(days=7),
            total_budget_minor=4200,
            impressions_count=1000,
            clicks_count=25,
        )

        assert campaign.click_through_rate == 2.5


@pytest.mark.django_db
class TestSponsoredListingModel:
    """Tests for SponsoredListing model targets and XOR constraints."""

    def test_attach_vehicle_listing_success(self, seller_user, sample_vehicle_listing):
        """Attaching a single vehicle listing succeeds."""
        today = timezone.localdate()
        campaign = AdvertisingCampaign.objects.create(
            seller=seller_user,
            title="Vehicle Ad Campaign",
            campaign_type=CampaignTypeChoices.VEHICLES,
            currency="GBP",
            start_date=today,
            end_date=today + datetime.timedelta(days=7),
            total_budget_minor=4200,
        )

        sponsored = SponsoredListing.objects.create(
            campaign=campaign,
            vehicle_listing=sample_vehicle_listing,
        )

        assert sponsored.vehicle_listing == sample_vehicle_listing
        assert sponsored.part_listing is None
        assert sponsored.target_type == CampaignTypeChoices.VEHICLES

    def test_attach_part_listing_success(self, seller_user, sample_part_listing):
        """Attaching a single spare-part listing succeeds."""
        today = timezone.localdate()
        campaign = AdvertisingCampaign.objects.create(
            seller=seller_user,
            title="Parts Ad Campaign",
            campaign_type=CampaignTypeChoices.SPARE_PARTS,
            currency="GBP",
            start_date=today,
            end_date=today + datetime.timedelta(days=7),
            total_budget_minor=4200,
        )

        sponsored = SponsoredListing.objects.create(
            campaign=campaign,
            part_listing=sample_part_listing,
        )

        assert sponsored.part_listing == sample_part_listing
        assert sponsored.vehicle_listing is None
        assert sponsored.target_type == CampaignTypeChoices.SPARE_PARTS

    def test_xor_constraint_both_listings_fails(self, seller_user, sample_vehicle_listing, sample_part_listing):
        """Attaching both vehicle and spare-part to a single sponsored listing violates XOR check."""
        today = timezone.localdate()
        campaign = AdvertisingCampaign.objects.create(
            seller=seller_user,
            title="Invalid XOR Campaign",
            campaign_type=CampaignTypeChoices.VEHICLES,
            currency="GBP",
            start_date=today,
            end_date=today + datetime.timedelta(days=7),
            total_budget_minor=4200,
        )

        with pytest.raises(IntegrityError):
            SponsoredListing.objects.create(
                campaign=campaign,
                vehicle_listing=sample_vehicle_listing,
                part_listing=sample_part_listing,
            )

    def test_unique_constraint_listing_per_campaign(self, seller_user, sample_vehicle_listing):
        """Attaching the same vehicle twice to the same campaign violates unique constraint."""
        today = timezone.localdate()
        campaign = AdvertisingCampaign.objects.create(
            seller=seller_user,
            title="Duplicate Listing Campaign",
            campaign_type=CampaignTypeChoices.VEHICLES,
            currency="GBP",
            start_date=today,
            end_date=today + datetime.timedelta(days=7),
            total_budget_minor=4200,
        )

        SponsoredListing.objects.create(
            campaign=campaign,
            vehicle_listing=sample_vehicle_listing,
        )

        with pytest.raises(IntegrityError):
            SponsoredListing.objects.create(
                campaign=campaign,
                vehicle_listing=sample_vehicle_listing,
            )


@pytest.mark.django_db
class TestCampaignAnalyticsModels:
    """Tests for impressions, clicks and session de-duplication."""

    def test_impression_session_hash_deduplication(self, seller_user, sample_vehicle_listing):
        """Duplicate session hash on the same date is blocked by unique constraint."""
        today = timezone.localdate()
        campaign = AdvertisingCampaign.objects.create(
            seller=seller_user,
            title="Impression Test",
            campaign_type=CampaignTypeChoices.VEHICLES,
            currency="GBP",
            start_date=today,
            end_date=today + datetime.timedelta(days=7),
            total_budget_minor=4200,
        )
        sponsored = SponsoredListing.objects.create(
            campaign=campaign,
            vehicle_listing=sample_vehicle_listing,
        )

        test_hash = "abc123sessionhash456"

        # First impression succeeds
        imp1 = CampaignImpression.objects.create(
            campaign=campaign,
            sponsored_listing=sponsored,
            session_hash=test_hash,
            date=today,
        )
        assert imp1.session_hash == test_hash
        assert CampaignImpression.objects.filter(session_hash=test_hash, sponsored_listing=sponsored).exists() is True
