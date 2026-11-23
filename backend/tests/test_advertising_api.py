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
import hashlib
import hmac
import uuid
import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.identity.models import User, RoleChoices
from apps.catalogue.models import PartCategory
from apps.marketplace.models import (
    AdvertisingCampaign,
    SponsoredListing,
    CampaignDailyMetric,
    CampaignTypeChoices,
    CampaignStatusChoices,
    CampaignPaymentStatusChoices,
    VehicleListing,
    VehicleMake,
    VehicleModel,
    SparePartListing,
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
def approved_vehicle_campaign(seller_user, seller_vehicle):
    today = timezone.localdate()
    campaign = AdvertisingCampaignService.create_campaign(
        seller=seller_user,
        title="Approved Vehicle Campaign",
        campaign_type=CampaignTypeChoices.VEHICLES,
        currency="GBP",
        target_country="GB",
        package_code="7_DAYS",
        start_date=today + datetime.timedelta(days=1),
    )
    AdvertisingCampaignService.attach_listings(campaign, [seller_vehicle.id], seller_user)
    campaign.status = CampaignStatusChoices.APPROVED
    campaign.save(update_fields=['status'])
    return campaign


@pytest.fixture
def approved_inr_vehicle_campaign(seller_user, seller_vehicle):
    today = timezone.localdate()
    campaign = AdvertisingCampaignService.create_campaign(
        seller=seller_user,
        title="Approved INR Vehicle Campaign",
        campaign_type=CampaignTypeChoices.VEHICLES,
        currency="INR",
        target_country="IN",
        package_code="7_DAYS",
        start_date=today + datetime.timedelta(days=1),
    )
    AdvertisingCampaignService.attach_listings(campaign, [seller_vehicle.id], seller_user)
    campaign.status = CampaignStatusChoices.APPROVED
    campaign.save(update_fields=['status'])
    return campaign


@pytest.fixture
def draft_campaign(seller_user, seller_vehicle):
    campaign = AdvertisingCampaignService.create_campaign(
        seller=seller_user,
        title="Draft Campaign",
        campaign_type=CampaignTypeChoices.VEHICLES,
        currency="GBP",
        target_country="GB",
        package_code="7_DAYS",
        start_date=timezone.localdate(),
    )
    return campaign


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


@pytest.mark.django_db
class TestAdvertisingCampaignAnalyticsApi:
    """Verifies campaign performance analytics calculations and security."""

    def test_analytics_zero_metrics_returns_safe_defaults(self, seller_user, active_sponsored_vehicle, seller_vehicle):
        client = APIClient()
        client.force_authenticate(user=seller_user)

        response = client.get(f'/api/v1/marketplace/advertising/campaigns/{active_sponsored_vehicle.id}/analytics/')
        assert response.status_code == status.HTTP_200_OK
        data = response.data

        assert data['campaign_id'] == str(active_sponsored_vehicle.id)
        assert data['title'] == active_sponsored_vehicle.title
        assert data['currency'] == 'GBP'
        assert data['total_impressions'] == 0
        assert data['total_clicks'] == 0
        assert data['click_through_rate_pct'] == 0.0
        assert data['total_budget_minor'] == 4200
        assert data['spent_amount_minor'] == 0
        assert data['daily_metrics'] == []

        assert len(data['listings_metrics']) == 1
        lm = data['listings_metrics'][0]
        assert lm['listing_id'] == str(seller_vehicle.id)
        assert lm['title'] == seller_vehicle.title
        assert lm['target_type'] == CampaignTypeChoices.VEHICLES
        assert lm['impressions'] == 0
        assert lm['clicks'] == 0
        assert lm['ctr_pct'] == 0.0
        assert lm['is_active'] is True

    def test_analytics_with_impressions_clicks_and_daily_metrics(self, seller_user, active_sponsored_vehicle):
        client = APIClient()
        client.force_authenticate(user=seller_user)
        sponsored = active_sponsored_vehicle.sponsored_listings.first()

        # Record real impression and click
        session_id = f"sess_{uuid.uuid4().hex[:10]}"
        AdvertisingCampaignService.record_impression(
            sponsored_listing_id=sponsored.id,
            session_id=session_id,
        )
        AdvertisingCampaignService.record_click(
            sponsored_listing_id=sponsored.id,
            session_id=session_id,
        )

        # Update daily metric created by tracking to test metric fields
        today = timezone.localdate()
        CampaignDailyMetric.objects.filter(
            campaign=active_sponsored_vehicle,
            date=today,
        ).update(
            impressions=100,
            clicks=10,
            spend_minor=600,
        )

        response = client.get(f'/api/v1/marketplace/advertising/campaigns/{active_sponsored_vehicle.id}/analytics/')
        assert response.status_code == status.HTTP_200_OK
        data = response.data

        assert data['total_impressions'] >= 1
        assert data['total_clicks'] >= 1
        assert data['click_through_rate_pct'] == 100.0

        assert len(data['daily_metrics']) == 1
        dm = data['daily_metrics'][0]
        assert dm['date'] == str(today)
        assert dm['impressions'] == 100
        assert dm['clicks'] == 10
        assert dm['ctr_pct'] == 10.0
        assert dm['spend_minor'] == 600

        lm = data['listings_metrics'][0]
        assert lm['impressions'] >= 1
        assert lm['clicks'] >= 1
        assert lm['ctr_pct'] == 100.0

    def test_analytics_spare_part_listing_resolves_title(self, seller_user):
        category = PartCategory.objects.create(name="Braking", slug=f"braking-{uuid.uuid4().hex[:6]}")
        part = SparePartListing.objects.create(
            seller=seller_user,
            name="Front Ceramic Brake Pad Set",
            category=category,
            brand="Brembo",
            mpn="P85020",
            price=85,
            currency="GBP",
            status=ListingStatusChoices.APPROVED,
        )

        campaign = AdvertisingCampaignService.create_campaign(
            seller=seller_user,
            title="Brembo Brake Promo",
            campaign_type=CampaignTypeChoices.SPARE_PARTS,
            currency="GBP",
            target_country="GB",
            package_code="7_DAYS",
            start_date=timezone.localdate(),
        )
        AdvertisingCampaignService.attach_listings(campaign, [part.id], seller_user)

        client = APIClient()
        client.force_authenticate(user=seller_user)
        response = client.get(f'/api/v1/marketplace/advertising/campaigns/{campaign.id}/analytics/')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['listings_metrics'][0]['title'] == "Front Ceramic Brake Pad Set"

    def test_analytics_permission_and_isolation(self, active_sponsored_vehicle, other_seller):
        anon_client = APIClient()
        response = anon_client.get(f'/api/v1/marketplace/advertising/campaigns/{active_sponsored_vehicle.id}/analytics/')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        other_client = APIClient()
        other_client.force_authenticate(user=other_seller)
        forbidden_response = other_client.get(f'/api/v1/marketplace/advertising/campaigns/{active_sponsored_vehicle.id}/analytics/')
        assert forbidden_response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestAdvertisingCampaignPaymentSessionApi:
    """Tests for resuming, retrieving, and confirming advertising campaign payment sessions."""

    def test_payment_session_post_creates_and_saves_reference(self, approved_vehicle_campaign, seller_user):
        client = APIClient()
        client.force_authenticate(user=seller_user)

        response = client.post(
            f'/api/v1/marketplace/advertising/campaigns/{approved_vehicle_campaign.id}/payment-session/',
            data={"return_url": "https://example.com/return"},
            format='json',
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert data['currency'] == "GBP"
        assert 'session_data' in data
        assert data['session_data']['provider_order_id'].startswith("pi_test_")

        approved_vehicle_campaign.refresh_from_db()
        assert approved_vehicle_campaign.status == CampaignStatusChoices.PAYMENT_PENDING
        assert approved_vehicle_campaign.payment_status == CampaignPaymentStatusChoices.PENDING
        assert approved_vehicle_campaign.payment_reference == data['session_data']['provider_order_id']

    def test_payment_session_get_resumes_existing_session(self, approved_vehicle_campaign, seller_user):
        approved_vehicle_campaign.status = CampaignStatusChoices.PAYMENT_PENDING
        approved_vehicle_campaign.payment_status = CampaignPaymentStatusChoices.PENDING
        approved_vehicle_campaign.payment_reference = "pi_test_resume_9876543210"
        approved_vehicle_campaign.save()

        client = APIClient()
        client.force_authenticate(user=seller_user)

        response = client.get(
            f'/api/v1/marketplace/advertising/campaigns/{approved_vehicle_campaign.id}/payment-session/'
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert data['session_data']['provider_order_id'] == "pi_test_resume_9876543210"

    def test_payment_session_confirm_action(self, approved_vehicle_campaign, seller_user):
        approved_vehicle_campaign.status = CampaignStatusChoices.PAYMENT_PENDING
        approved_vehicle_campaign.payment_status = CampaignPaymentStatusChoices.PENDING
        approved_vehicle_campaign.payment_reference = "pi_test_confirm_112233"
        # Start date tomorrow ensures transition to SCHEDULED
        approved_vehicle_campaign.start_date = timezone.localdate() + datetime.timedelta(days=1)
        approved_vehicle_campaign.end_date = timezone.localdate() + datetime.timedelta(days=7)
        approved_vehicle_campaign.save()

        client = APIClient()
        client.force_authenticate(user=seller_user)

        response = client.post(
            f'/api/v1/marketplace/advertising/campaigns/{approved_vehicle_campaign.id}/payment-session/',
            data={
                "action": "confirm",
                "payload": {
                    "payment_intent_id": "pi_test_confirm_112233",
                    "client_secret": "pi_test_confirm_112233_secret_12345",
                },
            },
            format='json',
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data['detail'] == "Payment confirmed successfully."

        approved_vehicle_campaign.refresh_from_db()
        assert approved_vehicle_campaign.payment_status == CampaignPaymentStatusChoices.PAID
        assert approved_vehicle_campaign.status == CampaignStatusChoices.SCHEDULED

    def test_payment_session_hidden_for_non_payable_campaigns(self, draft_campaign, seller_user):
        client = APIClient()
        client.force_authenticate(user=seller_user)

        # DRAFT cannot retrieve payment session
        response = client.get(
            f'/api/v1/marketplace/advertising/campaigns/{draft_campaign.id}/payment-session/'
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_payment_session_cross_seller_isolation(self, approved_vehicle_campaign, other_seller):
        client = APIClient()
        client.force_authenticate(user=other_seller)

        response = client.get(
            f'/api/v1/marketplace/advertising/campaigns/{approved_vehicle_campaign.id}/payment-session/'
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_razorpay_payment_session_get_resumes_inr_order(self, approved_inr_vehicle_campaign, seller_user):
        approved_inr_vehicle_campaign.status = CampaignStatusChoices.PAYMENT_PENDING
        approved_inr_vehicle_campaign.payment_status = CampaignPaymentStatusChoices.PENDING
        approved_inr_vehicle_campaign.payment_reference = "order_rzp_resume_554433"
        approved_inr_vehicle_campaign.save()

        client = APIClient()
        client.force_authenticate(user=seller_user)

        response = client.get(
            f'/api/v1/marketplace/advertising/campaigns/{approved_inr_vehicle_campaign.id}/payment-session/'
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert data['currency'] == "INR"
        assert data['provider'] == "RAZORPAY"
        assert data['session_data']['provider_order_id'] == "order_rzp_resume_554433"
        assert data['session_data']['order_id'] == "order_rzp_resume_554433"

    def test_razorpay_payment_session_confirm_valid_signature(self, approved_inr_vehicle_campaign, seller_user):
        from django.conf import settings

        order_id = "order_rzp_api_confirm_001"
        payment_id = "pay_rzp_api_confirm_001"
        key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', 'rzp_test_placeholder_secret')

        approved_inr_vehicle_campaign.status = CampaignStatusChoices.PAYMENT_PENDING
        approved_inr_vehicle_campaign.payment_status = CampaignPaymentStatusChoices.PENDING
        approved_inr_vehicle_campaign.payment_reference = order_id
        approved_inr_vehicle_campaign.save()

        msg = f"{order_id}|{payment_id}".encode('utf-8')
        valid_signature = hmac.new(key_secret.encode('utf-8'), msg, hashlib.sha256).hexdigest()

        client = APIClient()
        client.force_authenticate(user=seller_user)

        response = client.post(
            f'/api/v1/marketplace/advertising/campaigns/{approved_inr_vehicle_campaign.id}/payment-session/',
            data={
                "action": "confirm",
                "payload": {
                    "razorpay_order_id": order_id,
                    "razorpay_payment_id": payment_id,
                    "razorpay_signature": valid_signature,
                },
            },
            format='json',
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data['detail'] == "Payment confirmed successfully."

        approved_inr_vehicle_campaign.refresh_from_db()
        assert approved_inr_vehicle_campaign.payment_status == CampaignPaymentStatusChoices.PAID
        assert approved_inr_vehicle_campaign.status == CampaignStatusChoices.SCHEDULED

    def test_razorpay_payment_session_confirm_invalid_signature(self, approved_inr_vehicle_campaign, seller_user):
        order_id = "order_rzp_api_confirm_002"
        payment_id = "pay_rzp_api_confirm_002"

        approved_inr_vehicle_campaign.status = CampaignStatusChoices.PAYMENT_PENDING
        approved_inr_vehicle_campaign.payment_status = CampaignPaymentStatusChoices.PENDING
        approved_inr_vehicle_campaign.payment_reference = order_id
        approved_inr_vehicle_campaign.save()

        client = APIClient()
        client.force_authenticate(user=seller_user)

        response = client.post(
            f'/api/v1/marketplace/advertising/campaigns/{approved_inr_vehicle_campaign.id}/payment-session/',
            data={
                "action": "confirm",
                "payload": {
                    "razorpay_order_id": order_id,
                    "razorpay_payment_id": payment_id,
                    "razorpay_signature": "invalid_tampered_signature_hex",
                },
            },
            format='json',
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid Razorpay payment signature." in str(response.data)

        approved_inr_vehicle_campaign.refresh_from_db()
        assert approved_inr_vehicle_campaign.payment_status == CampaignPaymentStatusChoices.PENDING

    def test_razorpay_payment_session_confirm_mismatched_order_id(self, approved_inr_vehicle_campaign, seller_user):
        from django.conf import settings

        correct_order_id = "order_rzp_api_confirm_003"
        tampered_order_id = "order_rzp_api_tampered_999"
        payment_id = "pay_rzp_api_confirm_003"
        key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', 'rzp_test_placeholder_secret')

        approved_inr_vehicle_campaign.status = CampaignStatusChoices.PAYMENT_PENDING
        approved_inr_vehicle_campaign.payment_status = CampaignPaymentStatusChoices.PENDING
        approved_inr_vehicle_campaign.payment_reference = correct_order_id
        approved_inr_vehicle_campaign.save()

        msg = f"{tampered_order_id}|{payment_id}".encode('utf-8')
        tampered_sig = hmac.new(key_secret.encode('utf-8'), msg, hashlib.sha256).hexdigest()

        client = APIClient()
        client.force_authenticate(user=seller_user)

        response = client.post(
            f'/api/v1/marketplace/advertising/campaigns/{approved_inr_vehicle_campaign.id}/payment-session/',
            data={
                "action": "confirm",
                "payload": {
                    "razorpay_order_id": tampered_order_id,
                    "razorpay_payment_id": payment_id,
                    "razorpay_signature": tampered_sig,
                },
            },
            format='json',
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "does not match the active session" in str(response.data)

        approved_inr_vehicle_campaign.refresh_from_db()
        assert approved_inr_vehicle_campaign.payment_status == CampaignPaymentStatusChoices.PENDING

    def test_razorpay_payment_session_confirm_missing_fields(self, approved_inr_vehicle_campaign, seller_user):
        order_id = "order_rzp_api_confirm_004"
        approved_inr_vehicle_campaign.status = CampaignStatusChoices.PAYMENT_PENDING
        approved_inr_vehicle_campaign.payment_status = CampaignPaymentStatusChoices.PENDING
        approved_inr_vehicle_campaign.payment_reference = order_id
        approved_inr_vehicle_campaign.save()

        client = APIClient()
        client.force_authenticate(user=seller_user)

        # Missing signature
        response = client.post(
            f'/api/v1/marketplace/advertising/campaigns/{approved_inr_vehicle_campaign.id}/payment-session/',
            data={
                "action": "confirm",
                "payload": {
                    "razorpay_order_id": order_id,
                    "razorpay_payment_id": "pay_rzp_123",
                },
            },
            format='json',
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Missing razorpay_signature" in str(response.data)

