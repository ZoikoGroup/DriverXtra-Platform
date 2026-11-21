"""
Integration tests for Phase 7.2 Advertising REST APIs.
Covers:
- Dynamic pricing quotes with UK VAT and Indian GST breakdown.
- Seller campaign lifecycle: creation, listing isolation, submission, pausing, resuming, cancelling.
- Platform staff moderation: review queue, approve, reject with mandatory reason, self-approval guard.
- Admin oversight: overview KPIs, force pause, administrative termination.
- Public marketplace feed: sponsored inventory rotation, ACTIVE-only filtering.
- Public impression & click tracking with de-duplication.
"""

import datetime
import uuid
import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.identity.models import User, RoleChoices
from apps.marketplace.models import (
    AdvertisingCampaign,
    SponsoredListing,
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
    return VehicleMake.objects.create(name="Mercedes-Benz")


@pytest.fixture
def vehicle_model(db, vehicle_make):
    return VehicleModel.objects.create(make=vehicle_make, name="C-Class", year_start=2020)


@pytest.fixture
def seller_vehicle(seller_user, vehicle_make, vehicle_model):
    return VehicleListing.objects.create(
        seller=seller_user,
        title="2022 Mercedes-Benz C220d AMG Line",
        make=vehicle_make,
        model=vehicle_model,
        year=2022,
        vin="WDD00000000000009",
        price=34500,
        currency="GBP",
        status=ListingStatusChoices.APPROVED,
    )


@pytest.fixture
def other_seller(db):
    user = User.objects.create_user(
        email="other_seller@driverxtra.local",
        password="TestPassword123!",
        is_active=True,
    )
    user.add_role(RoleChoices.SELLER)
    return user


@pytest.fixture
def active_sponsored_vehicle(seller_user, seller_vehicle):
    today = timezone.localdate()
    campaign = AdvertisingCampaignService.create_campaign(
        seller=seller_user,
        title="Active Sponsored Vehicle Campaign",
        campaign_type=CampaignTypeChoices.VEHICLES,
        currency="GBP",
        target_country="GB",
        package_code="7_DAYS",
        start_date=today,
    )
    AdvertisingCampaignService.attach_listings(campaign, [seller_vehicle.id], seller_user)
    campaign.status = CampaignStatusChoices.APPROVED
    campaign.save(update_fields=['status'])

    AdvertisingCampaignService.record_successful_payment(
        campaign_id=campaign.id,
        provider="STRIPE",
        gateway_reference="pi_active_feed_1",
        gateway_payment_id="ch_active_feed_1",
        amount_minor=campaign.total_budget_minor,
        currency="GBP",
    )
    campaign.refresh_from_db()
    return campaign


@pytest.mark.django_db
class TestAdvertisingPricingQuoteApi:
    """Verifies the public pricing quote calculation endpoint."""

    def test_quote_uk_7_days(self):
        client = APIClient()
        response = client.post(
            '/api/v1/marketplace/advertising/pricing-quote/',
            data={
                "currency": "GBP",
                "package_code": "7_DAYS",
                "target_country": "GB",
            },
            format='json',
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert data['package_code'] == '7_DAYS'
        assert data['currency'] == 'GBP'
        assert data['net_amount_minor'] == 3500
        assert data['tax_amount_minor'] == 700
        assert data['total_amount_minor'] == 4200
        assert data['tax_regime'] == 'UK VAT'

    def test_quote_india_14_days(self):
        client = APIClient()
        response = client.post(
            '/api/v1/marketplace/advertising/pricing-quote/',
            data={
                "currency": "INR",
                "package_code": "14_DAYS",
                "target_country": "IN",
            },
            format='json',
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert data['currency'] == 'INR'
        assert data['net_amount_minor'] == 600000
        assert data['tax_amount_minor'] == 108000
        assert data['total_amount_minor'] == 708000
        assert data['sac_code'] == '998365'

    def test_quote_invalid_currency_rejected(self):
        client = APIClient()
        response = client.post(
            '/api/v1/marketplace/advertising/pricing-quote/',
            data={
                "currency": "USD",
                "package_code": "7_DAYS",
                "target_country": "US",
            },
            format='json',
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestSellerCampaignApi:
    """Verifies seller actions: CRUD, submit, pause, resume, cancel."""

    def test_create_campaign_draft(self, seller_user, seller_vehicle):
        client = APIClient()
        client.force_authenticate(user=seller_user)

        payload = {
            "title": "Summer C-Class Promotion",
            "campaign_type": CampaignTypeChoices.VEHICLES,
            "target_country": "GB",
            "currency": "GBP",
            "package_code": "7_DAYS",
            "listing_ids": [str(seller_vehicle.id)],
        }
        response = client.post('/api/v1/marketplace/advertising/campaigns/', data=payload, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['title'] == "Summer C-Class Promotion"
        assert response.data['status'] == CampaignStatusChoices.DRAFT
        assert response.data['total_budget_minor'] == 4200
        assert len(response.data['sponsored_listings']) == 1

    def test_list_campaigns_isolation(self, seller_user, other_seller, seller_vehicle):
        """Sellers can only see their own campaigns."""
        today = timezone.localdate()
        c1 = AdvertisingCampaignService.create_campaign(
            seller=seller_user,
            title="Seller 1 Campaign",
            campaign_type=CampaignTypeChoices.VEHICLES,
            currency="GBP",
            start_date=today,
        )
        c2 = AdvertisingCampaignService.create_campaign(
            seller=other_seller,
            title="Seller 2 Campaign",
            campaign_type=CampaignTypeChoices.VEHICLES,
            currency="GBP",
            start_date=today,
        )

        client = APIClient()
        client.force_authenticate(user=seller_user)

        response = client.get('/api/v1/marketplace/advertising/campaigns/')
        assert response.status_code == status.HTTP_200_OK
        ids = [item['id'] for item in response.data]
        assert str(c1.id) in ids
        assert str(c2.id) not in ids

    def test_submit_campaign_for_review(self, seller_user, seller_vehicle):
        today = timezone.localdate()
        campaign = AdvertisingCampaignService.create_campaign(
            seller=seller_user,
            title="Submit Test Campaign",
            campaign_type=CampaignTypeChoices.VEHICLES,
            currency="GBP",
            start_date=today,
        )
        AdvertisingCampaignService.attach_listings(campaign, [seller_vehicle.id], seller_user)

        client = APIClient()
        client.force_authenticate(user=seller_user)

        response = client.post(f'/api/v1/marketplace/advertising/campaigns/{campaign.id}/submit/')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['campaign']['status'] == CampaignStatusChoices.PENDING_APPROVAL

    def test_pause_resume_cancel_campaign(self, seller_user, active_sponsored_vehicle):
        client = APIClient()
        client.force_authenticate(user=seller_user)

        # 1. Pause
        resp_pause = client.post(f'/api/v1/marketplace/advertising/campaigns/{active_sponsored_vehicle.id}/pause/')
        assert resp_pause.status_code == status.HTTP_200_OK
        assert resp_pause.data['status'] == CampaignStatusChoices.PAUSED

        # 2. Resume
        resp_resume = client.post(f'/api/v1/marketplace/advertising/campaigns/{active_sponsored_vehicle.id}/resume/')
        assert resp_resume.status_code == status.HTTP_200_OK
        assert resp_resume.data['status'] == CampaignStatusChoices.ACTIVE

        # 3. Cancel with pro-rata refund
        resp_cancel = client.post(
            f'/api/v1/marketplace/advertising/campaigns/{active_sponsored_vehicle.id}/cancel/',
            data={"reason": "Customer request"},
            format='json',
        )
        assert resp_cancel.status_code == status.HTTP_200_OK
        assert resp_cancel.data['campaign']['status'] == CampaignStatusChoices.CANCELLED
        assert 'refund_amount_minor' in resp_cancel.data

    def test_unauthenticated_forbidden(self):
        client = APIClient()
        response = client.get('/api/v1/marketplace/advertising/campaigns/')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestAdminAdvertisingApi:
    """Verifies platform staff review and administration endpoints."""

    def test_admin_approve_campaign(self, staff_user, seller_user, seller_vehicle):
        today = timezone.localdate()
        campaign = AdvertisingCampaignService.create_campaign(
            seller=seller_user,
            title="Moderation Test Campaign",
            campaign_type=CampaignTypeChoices.VEHICLES,
            currency="GBP",
            start_date=today,
        )
        AdvertisingCampaignService.attach_listings(campaign, [seller_vehicle.id], seller_user)
        AdvertisingCampaignService.submit_campaign(campaign, seller_user)

        client = APIClient()
        client.force_authenticate(user=staff_user)

        response = client.post(
            f'/api/v1/marketplace/advertising/admin/campaigns/{campaign.id}/review/',
            data={"action": "APPROVE", "notes": "Approved by staff."},
            format='json',
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data['campaign']['status'] == CampaignStatusChoices.APPROVED

    def test_admin_reject_campaign_with_mandatory_reason(self, staff_user, seller_user, seller_vehicle):
        today = timezone.localdate()
        campaign = AdvertisingCampaignService.create_campaign(
            seller=seller_user,
            title="Rejection Test Campaign",
            campaign_type=CampaignTypeChoices.VEHICLES,
            currency="GBP",
            start_date=today,
        )
        AdvertisingCampaignService.attach_listings(campaign, [seller_vehicle.id], seller_user)
        AdvertisingCampaignService.submit_campaign(campaign, seller_user)

        client = APIClient()
        client.force_authenticate(user=staff_user)

        # Rejection without reason fails
        resp_fail = client.post(
            f'/api/v1/marketplace/advertising/admin/campaigns/{campaign.id}/review/',
            data={"action": "REJECT", "rejection_reason": ""},
            format='json',
        )
        assert resp_fail.status_code == status.HTTP_400_BAD_REQUEST

        # Rejection with reason succeeds
        resp_ok = client.post(
            f'/api/v1/marketplace/advertising/admin/campaigns/{campaign.id}/review/',
            data={"action": "REJECT", "rejection_reason": "Low quality imagery."},
            format='json',
        )
        assert resp_ok.status_code == status.HTTP_200_OK
        assert resp_ok.data['campaign']['status'] == CampaignStatusChoices.REJECTED
        assert resp_ok.data['campaign']['rejection_reason'] == "Low quality imagery."

    def test_admin_self_approval_guard(self, staff_user, seller_vehicle):
        """Staff user cannot approve their own campaign."""
        today = timezone.localdate()
        campaign = AdvertisingCampaignService.create_campaign(
            seller=staff_user,
            title="Staff Self Campaign",
            campaign_type=CampaignTypeChoices.VEHICLES,
            currency="GBP",
            start_date=today,
        )
        AdvertisingCampaignService.attach_listings(campaign, [seller_vehicle.id], staff_user)
        AdvertisingCampaignService.submit_campaign(campaign, staff_user)

        client = APIClient()
        client.force_authenticate(user=staff_user)

        response = client.post(
            f'/api/v1/marketplace/advertising/admin/campaigns/{campaign.id}/review/',
            data={"action": "APPROVE"},
            format='json',
        )
        assert response.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN)

    def test_admin_overview_metrics(self, staff_user, active_sponsored_vehicle):
        client = APIClient()
        client.force_authenticate(user=staff_user)

        response = client.get('/api/v1/marketplace/advertising/admin/overview/')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['total_campaigns'] >= 1
        assert response.data['active_campaigns'] >= 1
        assert response.data['total_revenue_minor'] >= active_sponsored_vehicle.total_budget_minor

    def test_non_staff_forbidden_from_admin_endpoints(self, seller_user):
        client = APIClient()
        client.force_authenticate(user=seller_user)

        response = client.get('/api/v1/marketplace/advertising/admin/campaigns/')
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestSponsoredFeedAndTrackingApi:
    """Verifies public sponsored feed and impression/click tracking."""

    def test_public_sponsored_feed_returns_active(self, active_sponsored_vehicle):
        client = APIClient()
        response = client.get('/api/v1/marketplace/advertising/sponsored-feed/?type=VEHICLES&country=GB&limit=5')
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1
        item = response.data[0]
        assert item['is_sponsored'] is True
        assert 'sponsored_listing_id' in item

    def test_impression_and_click_tracking_endpoints(self, active_sponsored_vehicle):
        client = APIClient()
        sponsored = active_sponsored_vehicle.sponsored_listings.first()
        session_id = f"sess_{uuid.uuid4().hex[:10]}"

        # 1. First impression
        imp_resp = client.post(
            '/api/v1/marketplace/advertising/track-impression/',
            data={
                "sponsored_listing_id": str(sponsored.id),
                "session_id": session_id,
                "referrer": "https://driverxtra.com/browse/vehicles",
            },
            format='json',
        )
        assert imp_resp.status_code == status.HTTP_200_OK
        assert imp_resp.data['recorded'] is True
        assert imp_resp.data['duplicate'] is False

        # 2. Duplicate impression (same session, same day)
        dup_imp_resp = client.post(
            '/api/v1/marketplace/advertising/track-impression/',
            data={
                "sponsored_listing_id": str(sponsored.id),
                "session_id": session_id,
            },
            format='json',
        )
        assert dup_imp_resp.status_code == status.HTTP_200_OK
        assert dup_imp_resp.data['duplicate'] is True

        # 3. First click
        clk_resp = client.post(
            '/api/v1/marketplace/advertising/track-click/',
            data={
                "sponsored_listing_id": str(sponsored.id),
                "session_id": session_id,
                "destination_url": f"/vehicles/{sponsored.vehicle_listing_id}",
            },
            format='json',
        )
        assert clk_resp.status_code == status.HTTP_200_OK
        assert clk_resp.data['recorded'] is True
        assert clk_resp.data['duplicate'] is False

        # 4. Duplicate click (same session, same hour)
        dup_clk_resp = client.post(
            '/api/v1/marketplace/advertising/track-click/',
            data={
                "sponsored_listing_id": str(sponsored.id),
                "session_id": session_id,
            },
            format='json',
        )
        assert dup_clk_resp.status_code == status.HTTP_200_OK
        assert dup_clk_resp.data['duplicate'] is True
