"""
Unit & Integration tests for Phase 7.2 Celery tasks and management commands.
Covers:
- activate_scheduled_campaigns_task: Transitions eligible SCHEDULED campaigns to ACTIVE.
- expire_completed_campaigns_task: Transitions expired ACTIVE campaigns to COMPLETED.
- aggregate_campaign_daily_metrics_task: Aggregates metrics and spend for active campaigns.
- process_advertising_campaigns management command: CLI execution with options.
"""

import datetime
import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.marketplace.models import (
    AdvertisingCampaign,
    CampaignTypeChoices,
    CampaignStatusChoices,
    CampaignPaymentStatusChoices,
    VehicleListing,
    VehicleMake,
    VehicleModel,
    ListingStatusChoices,
)
from apps.marketplace.advertising_service import AdvertisingCampaignService
from apps.marketplace.tasks import (
    activate_scheduled_campaigns_task,
    expire_completed_campaigns_task,
    aggregate_campaign_daily_metrics_task,
)


@pytest.fixture
def sample_vehicle(seller_user, db):
    make = VehicleMake.objects.create(name="Ford")
    model = VehicleModel.objects.create(make=make, name="Focus", year_start=2018)
    return VehicleListing.objects.create(
        seller=seller_user,
        title="2020 Ford Focus Titanium",
        make=make,
        model=model,
        year=2020,
        vin="WF000000000000099",
        price=14500,
        currency="GBP",
        status=ListingStatusChoices.APPROVED,
    )


@pytest.mark.django_db
class TestAdvertisingCeleryTasks:
    """Verifies Celery background tasks for advertising lifecycle."""

    def test_activate_scheduled_campaigns_task(self, seller_user, sample_vehicle):
        """Campaigns in SCHEDULED state whose start_date has arrived are transitioned to ACTIVE."""
        today = timezone.localdate()
        campaign = AdvertisingCampaignService.create_campaign(
            seller=seller_user,
            title="Scheduled to Active Test",
            campaign_type=CampaignTypeChoices.VEHICLES,
            currency="GBP",
            target_country="GB",
            package_code="7_DAYS",
            start_date=today,
        )
        AdvertisingCampaignService.attach_listings(campaign, [sample_vehicle.id], seller_user)
        campaign.status = CampaignStatusChoices.SCHEDULED
        campaign.payment_status = CampaignPaymentStatusChoices.PAID
        campaign.save(update_fields=['status', 'payment_status'])

        result = activate_scheduled_campaigns_task()
        assert result['activated_count'] >= 1

        campaign.refresh_from_db()
        assert campaign.status == CampaignStatusChoices.ACTIVE

    def test_expire_completed_campaigns_task(self, seller_user, sample_vehicle):
        """Active campaigns whose end_date has passed are transitioned to COMPLETED."""
        past_start = timezone.localdate() - datetime.timedelta(days=10)
        past_end = timezone.localdate() - datetime.timedelta(days=2)

        campaign = AdvertisingCampaign.objects.create(
            seller=seller_user,
            title="Expired Campaign Test",
            campaign_type=CampaignTypeChoices.VEHICLES,
            currency="GBP",
            package_code="7_DAYS",
            start_date=past_start,
            end_date=past_end,
            total_budget_minor=4200,
            daily_rate_minor=600,
            status=CampaignStatusChoices.ACTIVE,
            payment_status=CampaignPaymentStatusChoices.PAID,
        )

        result = expire_completed_campaigns_task()
        assert result['completed_count'] >= 1

        campaign.refresh_from_db()
        assert campaign.status == CampaignStatusChoices.COMPLETED
        assert campaign.completed_at is not None

    def test_aggregate_campaign_daily_metrics_task(self, seller_user, sample_vehicle):
        """Aggregates daily performance metrics for campaigns."""
        today = timezone.localdate()
        campaign = AdvertisingCampaignService.create_campaign(
            seller=seller_user,
            title="Metrics Aggregation Test",
            campaign_type=CampaignTypeChoices.VEHICLES,
            currency="GBP",
            target_country="GB",
            package_code="7_DAYS",
            start_date=today,
        )
        AdvertisingCampaignService.attach_listings(campaign, [sample_vehicle.id], seller_user)
        campaign.status = CampaignStatusChoices.ACTIVE
        campaign.payment_status = CampaignPaymentStatusChoices.PAID
        campaign.save(update_fields=['status', 'payment_status'])

        result = aggregate_campaign_daily_metrics_task()
        assert 'status' in result
        assert result['status'] == 'completed'

    def test_process_advertising_campaigns_command(self, seller_user, sample_vehicle):
        """CLI management command runs without errors."""
        call_command('process_advertising_campaigns', activate=True, expire=True, aggregate=True, recover=True)

    def test_recover_held_paid_campaigns_date_transitions(self, seller_user, sample_vehicle):
        """
        Held paid campaigns transition safely based on start and end dates:
        - start_date <= today <= end_date -> ACTIVE
        - start_date > today -> SCHEDULED
        - today > end_date -> COMPLETED (never activated)
        """
        from django.test import override_settings
        today = timezone.localdate()

        # 1. Currently running campaign
        c_active = AdvertisingCampaign.objects.create(
            seller=seller_user,
            title="Held Current Campaign",
            campaign_type=CampaignTypeChoices.VEHICLES,
            currency="GBP",
            package_code="7_DAYS",
            start_date=today,
            end_date=today + datetime.timedelta(days=6),
            total_budget_minor=4200,
            daily_rate_minor=600,
            status=CampaignStatusChoices.PAYMENT_PENDING,
            payment_status=CampaignPaymentStatusChoices.PAID,
        )

        # 2. Future-start campaign
        c_future = AdvertisingCampaign.objects.create(
            seller=seller_user,
            title="Held Future Campaign",
            campaign_type=CampaignTypeChoices.VEHICLES,
            currency="GBP",
            package_code="7_DAYS",
            start_date=today + datetime.timedelta(days=3),
            end_date=today + datetime.timedelta(days=9),
            total_budget_minor=4200,
            daily_rate_minor=600,
            status=CampaignStatusChoices.PAYMENT_PENDING,
            payment_status=CampaignPaymentStatusChoices.PAID,
        )

        # 3. Expired campaign
        c_expired = AdvertisingCampaign.objects.create(
            seller=seller_user,
            title="Held Expired Campaign",
            campaign_type=CampaignTypeChoices.VEHICLES,
            currency="GBP",
            package_code="7_DAYS",
            start_date=today - datetime.timedelta(days=10),
            end_date=today - datetime.timedelta(days=3),
            total_budget_minor=4200,
            daily_rate_minor=600,
            status=CampaignStatusChoices.PAYMENT_PENDING,
            payment_status=CampaignPaymentStatusChoices.PAID,
        )

        with override_settings(LIVE_ADVERTISING_CHARGES_ENABLED=True):
            recovered = AdvertisingCampaignService.recover_held_paid_campaigns()
            assert recovered == 3

        c_active.refresh_from_db()
        assert c_active.status == CampaignStatusChoices.ACTIVE

        c_future.refresh_from_db()
        assert c_future.status == CampaignStatusChoices.SCHEDULED

        c_expired.refresh_from_db()
        assert c_expired.status == CampaignStatusChoices.COMPLETED
        assert c_expired.completed_at is not None

    def test_recover_held_paid_campaigns_ineligible_safety(self, seller_user, sample_vehicle):
        """
        Cancelled, rejected, partially refunded, and unpaid campaigns are never overwritten.
        """
        from apps.marketplace.models import CampaignPayment
        from django.test import override_settings
        today = timezone.localdate()

        # Cancelled campaign with payment_status=PAID
        c_cancelled = AdvertisingCampaign.objects.create(
            seller=seller_user,
            title="Cancelled Campaign",
            campaign_type=CampaignTypeChoices.VEHICLES,
            currency="GBP",
            package_code="7_DAYS",
            start_date=today,
            end_date=today + datetime.timedelta(days=6),
            total_budget_minor=4200,
            daily_rate_minor=600,
            status=CampaignStatusChoices.CANCELLED,
            payment_status=CampaignPaymentStatusChoices.PAID,
        )

        # Rejected campaign
        c_rejected = AdvertisingCampaign.objects.create(
            seller=seller_user,
            title="Rejected Campaign",
            campaign_type=CampaignTypeChoices.VEHICLES,
            currency="GBP",
            package_code="7_DAYS",
            start_date=today,
            end_date=today + datetime.timedelta(days=6),
            total_budget_minor=4200,
            daily_rate_minor=600,
            status=CampaignStatusChoices.REJECTED,
            payment_status=CampaignPaymentStatusChoices.PAID,
        )

        # Partially refunded campaign
        c_partially_refunded = AdvertisingCampaign.objects.create(
            seller=seller_user,
            title="Partially Refunded Campaign",
            campaign_type=CampaignTypeChoices.VEHICLES,
            currency="GBP",
            package_code="7_DAYS",
            start_date=today,
            end_date=today + datetime.timedelta(days=6),
            total_budget_minor=4200,
            daily_rate_minor=600,
            status=CampaignStatusChoices.PAYMENT_PENDING,
            payment_status=CampaignPaymentStatusChoices.PAID,
        )
        CampaignPayment.objects.create(
            campaign=c_partially_refunded,
            provider="STRIPE",
            gateway_reference="cs_part_rfnd",
            amount_minor=5000,
            currency="GBP",
            payment_status=CampaignPaymentStatusChoices.PARTIALLY_REFUNDED,
            refund_amount_minor=2000,
        )

        with override_settings(LIVE_ADVERTISING_CHARGES_ENABLED=True):
            recovered = AdvertisingCampaignService.recover_held_paid_campaigns()
            assert recovered == 0

        c_cancelled.refresh_from_db()
        assert c_cancelled.status == CampaignStatusChoices.CANCELLED

        c_rejected.refresh_from_db()
        assert c_rejected.status == CampaignStatusChoices.REJECTED

        c_partially_refunded.refresh_from_db()
        assert c_partially_refunded.status == CampaignStatusChoices.PAYMENT_PENDING

    def test_recover_held_paid_campaigns_live_gate_and_idempotency(self, seller_user, sample_vehicle):
        """
        Live campaigns remain held when LIVE_ADVERTISING_CHARGES_ENABLED=False.
        When True, they recover, and repeated recovery is completely idempotent.
        """
        from apps.marketplace.models import CampaignPayment
        from platform_core.audit.models import AuditLog
        from django.test import override_settings
        today = timezone.localdate()

        c_live = AdvertisingCampaign.objects.create(
            seller=seller_user,
            title="Live Held Campaign",
            campaign_type=CampaignTypeChoices.VEHICLES,
            currency="GBP",
            package_code="7_DAYS",
            start_date=today,
            end_date=today + datetime.timedelta(days=6),
            total_budget_minor=4200,
            daily_rate_minor=600,
            status=CampaignStatusChoices.PAYMENT_PENDING,
            payment_status=CampaignPaymentStatusChoices.PAID,
        )
        CampaignPayment.objects.create(
            campaign=c_live,
            provider="STRIPE",
            gateway_reference="cs_live_held_1",
            amount_minor=5000,
            currency="GBP",
            payment_status=CampaignPaymentStatusChoices.PAID,
            raw_response={"livemode": True},
        )

        # 1. Recovery disabled while live authorization is False
        with override_settings(LIVE_ADVERTISING_CHARGES_ENABLED=False, LIVE_ADVERTISING_PAYMENTS_ENABLED=False):
            rec_count = AdvertisingCampaignService.recover_held_paid_campaigns()
            assert rec_count == 0
            c_live.refresh_from_db()
            assert c_live.status == CampaignStatusChoices.PAYMENT_PENDING

        # 2. When authorized, recovery succeeds
        with override_settings(LIVE_ADVERTISING_CHARGES_ENABLED=True):
            rec_count = AdvertisingCampaignService.recover_held_paid_campaigns()
            assert rec_count == 1
            c_live.refresh_from_db()
            assert c_live.status == CampaignStatusChoices.ACTIVE

            audit_count_before = AuditLog.objects.filter(
                event_type="advertising.campaign.recovered",
                resource_id=str(c_live.id),
            ).count()
            assert audit_count_before == 1

            # 3. Repeated run is completely idempotent (no re-activation, no duplicate audit)
            rec_count_repeat = AdvertisingCampaignService.recover_held_paid_campaigns()
            assert rec_count_repeat == 0

            audit_count_after = AuditLog.objects.filter(
                event_type="advertising.campaign.recovered",
                resource_id=str(c_live.id),
            ).count()
            assert audit_count_after == 1
