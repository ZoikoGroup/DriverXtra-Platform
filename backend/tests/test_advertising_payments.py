"""
Unit & Integration tests for Phase 7.2 Advertising Payments & Webhooks.
Covers:
- Authoritative Stripe (GBP) and Razorpay (INR) payment recording.
- Multi-currency validation and underpayment detection.
- Idempotent webhook event and gateway payment processing.
- Transition to ACTIVE (start_date <= today) vs SCHEDULED (start_date > today).
- Payment session generation for APPROVED campaigns only.
- Webhook signature validation and rejection.
"""

import datetime
import json
import uuid
from decimal import Decimal
from unittest.mock import patch, MagicMock
import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.identity.models import User
from apps.marketplace.models import (
    AdvertisingCampaign,
    CampaignPayment,
    CampaignRefundOperation,
    CampaignRefundStatusChoices,
    CampaignTypeChoices,
    CampaignStatusChoices,
    CampaignPaymentStatusChoices,
    PaymentWebhookEvent,
    VehicleListing,
    VehicleMake,
    VehicleModel,
    ListingStatusChoices,
)
from apps.marketplace.advertising_service import AdvertisingCampaignService


@pytest.fixture
def vehicle_make(db):
    return VehicleMake.objects.create(name="BMW")


@pytest.fixture
def vehicle_model(db, vehicle_make):
    return VehicleModel.objects.create(make=vehicle_make, name="3 Series", year_start=2019)


@pytest.fixture
def sample_vehicle(seller_user, vehicle_make, vehicle_model):
    return VehicleListing.objects.create(
        seller=seller_user,
        title="2022 BMW 330e M-Sport",
        make=vehicle_make,
        model=vehicle_model,
        year=2022,
        vin="WBA00000000000001",
        price=32000,
        currency="GBP",
        status=ListingStatusChoices.APPROVED,
    )


@pytest.fixture
def gbp_approved_campaign(seller_user, sample_vehicle):
    today = timezone.localdate()
    campaign = AdvertisingCampaignService.create_campaign(
        seller=seller_user,
        title="BMW Fleet Promotion",
        campaign_type=CampaignTypeChoices.VEHICLES,
        currency="GBP",
        target_country="GB",
        package_code="7_DAYS",
        start_date=today,
    )
    AdvertisingCampaignService.attach_listings(campaign, [sample_vehicle.id], seller_user)
    campaign.status = CampaignStatusChoices.APPROVED
    campaign.save(update_fields=['status'])
    return campaign


@pytest.fixture
def inr_approved_campaign(seller_user, sample_vehicle):
    today = timezone.localdate()
    campaign = AdvertisingCampaignService.create_campaign(
        seller=seller_user,
        title="India Parts Festive Campaign",
        campaign_type=CampaignTypeChoices.VEHICLES,
        currency="INR",
        target_country="IN",
        package_code="14_DAYS",
        start_date=today,
    )
    AdvertisingCampaignService.attach_listings(campaign, [sample_vehicle.id], seller_user)
    campaign.status = CampaignStatusChoices.APPROVED
    campaign.save(update_fields=['status'])
    return campaign


@pytest.mark.django_db
class TestAdvertisingPaymentService:
    """Verifies core payment orchestration in AdvertisingCampaignService."""

    def test_stripe_payment_recording_success(self, gbp_approved_campaign):
        """Valid Stripe payment marks campaign PAID and ACTIVE."""
        payment = AdvertisingCampaignService.record_successful_payment(
            campaign_id=gbp_approved_campaign.id,
            provider="STRIPE",
            gateway_reference="pi_test_stripe_123",
            gateway_payment_id="ch_test_stripe_123",
            amount_minor=gbp_approved_campaign.total_budget_minor,
            currency="GBP",
            raw_response={"status": "succeeded"},
        )
        assert payment.payment_status == CampaignPaymentStatusChoices.PAID
        assert payment.amount_minor == gbp_approved_campaign.total_budget_minor

        gbp_approved_campaign.refresh_from_db()
        assert gbp_approved_campaign.payment_status == CampaignPaymentStatusChoices.PAID
        assert gbp_approved_campaign.status == CampaignStatusChoices.ACTIVE

    def test_razorpay_payment_recording_success(self, inr_approved_campaign):
        """Valid Razorpay payment marks campaign PAID and ACTIVE."""
        payment = AdvertisingCampaignService.record_successful_payment(
            campaign_id=inr_approved_campaign.id,
            provider="RAZORPAY",
            gateway_reference="order_test_rzp_456",
            gateway_payment_id="pay_test_rzp_456",
            amount_minor=inr_approved_campaign.total_budget_minor,
            currency="INR",
            raw_response={"status": "captured"},
        )
        assert payment.payment_status == CampaignPaymentStatusChoices.PAID
        assert payment.amount_minor == inr_approved_campaign.total_budget_minor

        inr_approved_campaign.refresh_from_db()
        assert inr_approved_campaign.payment_status == CampaignPaymentStatusChoices.PAID
        assert inr_approved_campaign.status == CampaignStatusChoices.ACTIVE

    def test_payment_idempotency_skip_duplicate(self, gbp_approved_campaign):
        """Recording identical gateway payment ID is idempotent and returns existing record."""
        pay1 = AdvertisingCampaignService.record_successful_payment(
            campaign_id=gbp_approved_campaign.id,
            provider="STRIPE",
            gateway_reference="pi_idem_1",
            gateway_payment_id="ch_idem_1",
            amount_minor=gbp_approved_campaign.total_budget_minor,
            currency="GBP",
        )
        pay2 = AdvertisingCampaignService.record_successful_payment(
            campaign_id=gbp_approved_campaign.id,
            provider="STRIPE",
            gateway_reference="pi_idem_1",
            gateway_payment_id="ch_idem_1",
            amount_minor=gbp_approved_campaign.total_budget_minor,
            currency="GBP",
        )
        assert pay1.id == pay2.id
        assert CampaignPayment.objects.filter(gateway_payment_id="ch_idem_1").count() == 1

    def test_underpayment_rejected(self, gbp_approved_campaign):
        """Paying less than the total required budget raises ValidationError."""
        underpaid_amount = gbp_approved_campaign.total_budget_minor - 100
        with pytest.raises(ValidationError, match="Underpayment detected"):
            AdvertisingCampaignService.record_successful_payment(
                campaign_id=gbp_approved_campaign.id,
                provider="STRIPE",
                gateway_reference="pi_under_1",
                gateway_payment_id="ch_under_1",
                amount_minor=underpaid_amount,
                currency="GBP",
            )

    def test_currency_mismatch_rejected(self, gbp_approved_campaign):
        """Submitting payment in INR for a GBP campaign raises ValidationError."""
        with pytest.raises(ValidationError, match="currency mismatch"):
            AdvertisingCampaignService.record_successful_payment(
                campaign_id=gbp_approved_campaign.id,
                provider="STRIPE",
                gateway_reference="pi_curr_1",
                gateway_payment_id="ch_curr_1",
                amount_minor=gbp_approved_campaign.total_budget_minor,
                currency="INR",
            )

    def test_future_start_date_transitions_to_scheduled(self, seller_user, sample_vehicle):
        """Paid campaigns starting tomorrow enter SCHEDULED status, not ACTIVE."""
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        campaign = AdvertisingCampaignService.create_campaign(
            seller=seller_user,
            title="Future Promotion",
            campaign_type=CampaignTypeChoices.VEHICLES,
            currency="GBP",
            target_country="GB",
            package_code="7_DAYS",
            start_date=tomorrow,
        )
        AdvertisingCampaignService.attach_listings(campaign, [sample_vehicle.id], seller_user)
        campaign.status = CampaignStatusChoices.APPROVED
        campaign.save(update_fields=['status'])

        AdvertisingCampaignService.record_successful_payment(
            campaign_id=campaign.id,
            provider="STRIPE",
            gateway_reference="pi_future_1",
            gateway_payment_id="ch_future_1",
            amount_minor=campaign.total_budget_minor,
            currency="GBP",
        )
        campaign.refresh_from_db()
        assert campaign.payment_status == CampaignPaymentStatusChoices.PAID
        assert campaign.status == CampaignStatusChoices.SCHEDULED

    def test_create_payment_session_gbp(self, gbp_approved_campaign):
        """Creating payment session for GBP uses Stripe provider."""
        mock_session = {"provider": "STRIPE", "session_id": "cs_test_mock", "checkout_url": "https://stripe.com/pay"}
        with patch('apps.marketplace.payments.stripe_provider.StripePaymentProvider.create_payment_session', return_value=mock_session):
            res = AdvertisingCampaignService.create_payment_session(gbp_approved_campaign)
            assert res['provider'] == 'STRIPE'
            assert res['amount_minor'] == gbp_approved_campaign.total_budget_minor

    def test_create_payment_session_inr(self, inr_approved_campaign):
        """Creating payment session for INR uses Razorpay provider."""
        mock_session = {"provider": "RAZORPAY", "order_id": "order_mock", "razorpay_order_id": "order_mock"}
        with patch('apps.marketplace.payments.razorpay_provider.RazorpayPaymentProvider.create_payment_session', return_value=mock_session):
            res = AdvertisingCampaignService.create_payment_session(inr_approved_campaign)
            assert res['provider'] == 'RAZORPAY'
            assert res['amount_minor'] == inr_approved_campaign.total_budget_minor

    def test_create_payment_session_unapproved_rejected(self, seller_user, sample_vehicle):
        """Cannot create payment session for DRAFT campaign."""
        today = timezone.localdate()
        draft_campaign = AdvertisingCampaignService.create_campaign(
            seller=seller_user,
            title="Draft Campaign",
            campaign_type=CampaignTypeChoices.VEHICLES,
            currency="GBP",
            start_date=today,
        )
        with pytest.raises(ValidationError, match="APPROVED"):
            AdvertisingCampaignService.create_payment_session(draft_campaign)


@pytest.mark.django_db
class TestAdvertisingPaymentWebhookView:
    """Verifies Stripe and Razorpay webhook HTTP handlers."""

    def test_stripe_webhook_payment_intent_succeeded(self, gbp_approved_campaign):
        client = APIClient()
        payload = {
            "id": "evt_stripe_test_1",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "ch_webhook_stripe_1",
                    "amount": gbp_approved_campaign.total_budget_minor,
                    "currency": "gbp",
                    "metadata": {
                        "campaign_id": str(gbp_approved_campaign.id),
                    },
                }
            }
        }
        body_bytes = json.dumps(payload).encode('utf-8')

        with patch('apps.marketplace.payments.stripe_provider.StripePaymentProvider.verify_webhook', return_value=(True, "evt_stripe_test_1", "payment_intent.succeeded", payload)):
            response = client.post(
                '/api/v1/marketplace/advertising/webhook/stripe/',
                data=body_bytes,
                content_type='application/json',
                HTTP_STRIPE_SIGNATURE='t=123,v1=mock_sig',
            )
            assert response.status_code == 200
            assert response.data['status'] == 'success'
            assert response.data['campaign_id'] == str(gbp_approved_campaign.id)

            gbp_approved_campaign.refresh_from_db()
            assert gbp_approved_campaign.payment_status == CampaignPaymentStatusChoices.PAID

    def test_stripe_webhook_invalid_signature_rejected(self):
        client = APIClient()
        with patch('apps.marketplace.payments.stripe_provider.StripePaymentProvider.verify_webhook', return_value=(False, None, None, {"error": "Invalid signature"})):
            response = client.post(
                '/api/v1/marketplace/advertising/webhook/stripe/',
                data=b'{"fake": "data"}',
                content_type='application/json',
            )
            assert response.status_code == 400

    def test_razorpay_webhook_payment_captured(self, inr_approved_campaign):
        client = APIClient()
        payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_webhook_rzp_1",
                        "order_id": "order_webhook_rzp_1",
                        "amount": inr_approved_campaign.total_budget_minor,
                        "currency": "INR",
                        "notes": {
                            "campaign_id": str(inr_approved_campaign.id),
                        },
                    }
                }
            }
        }
        body_bytes = json.dumps(payload).encode('utf-8')

        with patch('apps.marketplace.payments.razorpay_provider.RazorpayPaymentProvider.verify_webhook', return_value=(True, "evt_rzp_test_1", "payment.captured", payload)):
            response = client.post(
                '/api/v1/marketplace/advertising/webhook/razorpay/',
                data=body_bytes,
                content_type='application/json',
                HTTP_X_RAZORPAY_SIGNATURE='mock_rzp_sig',
            )
            assert response.status_code == 200
            assert response.data['status'] == 'success'

            inr_approved_campaign.refresh_from_db()
            assert inr_approved_campaign.payment_status == CampaignPaymentStatusChoices.PAID

    def test_webhook_idempotency_duplicate_event(self, gbp_approved_campaign):
        """Duplicate webhook event is acknowledged with already_processed without re-executing."""
        PaymentWebhookEvent.objects.create(
            provider="STRIPE",
            event_id="evt_duplicate_test",
            event_type="payment_intent.succeeded",
            processed=True,
            payload={},
        )
        client = APIClient()
        with patch('apps.marketplace.payments.stripe_provider.StripePaymentProvider.verify_webhook', return_value=(True, "evt_duplicate_test", "payment_intent.succeeded", {})):
            response = client.post(
                '/api/v1/marketplace/advertising/webhook/stripe/',
                data=b'{}',
                content_type='application/json',
            )
            assert response.status_code == 200
            assert response.data['status'] == 'already_processed'

    def test_gateway_refund_dispatch_stripe_success(self, gbp_approved_campaign):
        """Refund dispatch calls Stripe issue_refund with Decimal amount and updates payment record."""
        # Setup paid campaign
        payment = AdvertisingCampaignService.record_successful_payment(
            campaign_id=gbp_approved_campaign.id,
            provider="STRIPE",
            gateway_reference="pi_rfnd_stripe_1",
            gateway_payment_id="ch_rfnd_stripe_1",
            amount_minor=gbp_approved_campaign.total_budget_minor,
            currency="GBP",
        )
        assert payment.payment_status == CampaignPaymentStatusChoices.PAID

        with patch('apps.marketplace.payments.stripe_provider.StripePaymentProvider.issue_refund') as mock_refund:
            mock_refund.return_value = (True, "re_stripe_test_123", {"status": "succeeded"})

            refunded_payment = AdvertisingCampaignService.refund_campaign(
                campaign=gbp_approved_campaign,
                refund_minor=gbp_approved_campaign.total_budget_minor,
                reason="Policy cancellation",
            )

            assert refunded_payment is not None
            assert refunded_payment.payment_status == CampaignPaymentStatusChoices.REFUNDED
            assert refunded_payment.refund_amount_minor == gbp_approved_campaign.total_budget_minor
            assert refunded_payment.raw_response.get('gateway_refund_id') == "re_stripe_test_123"

            # Verify mock called with Decimal amount in major units
            mock_refund.assert_called_once()
            call_kwargs = mock_refund.call_args[1]
            assert call_kwargs['payment_reference'] == "ch_rfnd_stripe_1"
            assert call_kwargs['currency'] == "GBP"
            assert call_kwargs['amount'] == Decimal(gbp_approved_campaign.total_budget_minor) / Decimal(100)

    def test_gateway_refund_dispatch_razorpay_success(self, inr_approved_campaign):
        """Refund dispatch calls Razorpay issue_refund for INR campaigns."""
        payment = AdvertisingCampaignService.record_successful_payment(
            campaign_id=inr_approved_campaign.id,
            provider="RAZORPAY",
            gateway_reference="order_rfnd_rzp_1",
            gateway_payment_id="pay_rfnd_rzp_1",
            amount_minor=inr_approved_campaign.total_budget_minor,
            currency="INR",
        )
        with patch('apps.marketplace.payments.razorpay_provider.RazorpayPaymentProvider.issue_refund') as mock_refund:
            mock_refund.return_value = (True, "rfnd_rzp_test_456", {"status": "processed"})

            refunded_payment = AdvertisingCampaignService.refund_campaign(
                campaign=inr_approved_campaign,
                refund_minor=inr_approved_campaign.total_budget_minor,
                reason="Dealer cancellation",
            )
            assert refunded_payment.payment_status == CampaignPaymentStatusChoices.REFUNDED
            assert refunded_payment.raw_response.get('gateway_refund_id') == "rfnd_rzp_test_456"
            mock_refund.assert_called_once()
            assert mock_refund.call_args[1]['payment_reference'] == "pay_rfnd_rzp_1"

    def test_gateway_refund_dispatch_failure_handling(self, gbp_approved_campaign):
        """Gateway rejection raises ValidationError and records error in raw_response."""
        payment = AdvertisingCampaignService.record_successful_payment(
            campaign_id=gbp_approved_campaign.id,
            provider="STRIPE",
            gateway_reference="pi_fail_rfnd",
            gateway_payment_id="ch_fail_rfnd",
            amount_minor=gbp_approved_campaign.total_budget_minor,
            currency="GBP",
        )
        with patch('apps.marketplace.payments.stripe_provider.StripePaymentProvider.issue_refund') as mock_refund:
            mock_refund.return_value = (False, "charge_already_refunded", {"code": "err"})

            with pytest.raises(ValidationError, match="Payment gateway refund dispatch failed"):
                AdvertisingCampaignService.refund_campaign(
                    campaign=gbp_approved_campaign,
                    refund_minor=gbp_approved_campaign.total_budget_minor,
                    reason="Cancellation attempt",
                )

            payment.refresh_from_db()
            assert "refund_dispatch_error" in payment.raw_response

    def test_gateway_refund_idempotency_skip_duplicate(self, gbp_approved_campaign):
        """Subsequent refund call with identical amount does not re-invoke gateway API."""
        payment = AdvertisingCampaignService.record_successful_payment(
            campaign_id=gbp_approved_campaign.id,
            provider="STRIPE",
            gateway_reference="pi_idem_rfnd",
            gateway_payment_id="ch_idem_rfnd",
            amount_minor=gbp_approved_campaign.total_budget_minor,
            currency="GBP",
        )
        with patch('apps.marketplace.payments.stripe_provider.StripePaymentProvider.issue_refund') as mock_refund:
            mock_refund.return_value = (True, "re_idem_1", {})
            AdvertisingCampaignService.refund_campaign(
                campaign=gbp_approved_campaign,
                refund_minor=gbp_approved_campaign.total_budget_minor,
            )
            assert mock_refund.call_count == 1

            # Second call
            AdvertisingCampaignService.refund_campaign(
                campaign=gbp_approved_campaign,
                refund_minor=gbp_approved_campaign.total_budget_minor,
            )
            assert mock_refund.call_count == 1  # Not called again

    def test_webhook_charge_refunded_reconciliation(self, gbp_approved_campaign):
        """Webhook event charge.refunded updates payment status to REFUNDED."""
        payment = AdvertisingCampaignService.record_successful_payment(
            campaign_id=gbp_approved_campaign.id,
            provider="STRIPE",
            gateway_reference="pi_wb_rfnd",
            gateway_payment_id="ch_wb_rfnd",
            amount_minor=gbp_approved_campaign.total_budget_minor,
            currency="GBP",
        )
        client = APIClient()
        payload = {
            "type": "charge.refunded",
            "data": {
                "object": {
                    "id": "ch_wb_rfnd",
                    "amount_refunded": gbp_approved_campaign.total_budget_minor,
                    "currency": "gbp",
                    "metadata": {
                        "campaign_id": str(gbp_approved_campaign.id),
                    },
                }
            }
        }
        body_bytes = json.dumps(payload).encode('utf-8')
        with patch('apps.marketplace.payments.stripe_provider.StripePaymentProvider.verify_webhook', return_value=(True, "evt_stripe_rfnd_1", "charge.refunded", payload)):
            response = client.post(
                '/api/v1/marketplace/advertising/webhook/stripe/',
                data=body_bytes,
                content_type='application/json',
                HTTP_STRIPE_SIGNATURE='mock_sig',
            )
            assert response.status_code == 200
            assert response.data['status'] == 'refund_reconciled'

            payment.refresh_from_db()
            assert payment.payment_status == CampaignPaymentStatusChoices.REFUNDED

    def test_multiple_partial_refunds_and_exact_same_amount(self, gbp_approved_campaign):
        """Supports multiple legitimate partial refunds against one payment, including equal amounts."""
        total_amount = 6000  # 60.00 GBP
        gbp_approved_campaign.total_budget_minor = total_amount
        gbp_approved_campaign.save()

        payment = AdvertisingCampaignService.record_successful_payment(
            campaign_id=gbp_approved_campaign.id,
            provider="STRIPE",
            gateway_reference="pi_multi_rfnd",
            gateway_payment_id="ch_multi_rfnd",
            amount_minor=total_amount,
            currency="GBP",
        )

        with patch('apps.marketplace.payments.stripe_provider.StripePaymentProvider.issue_refund') as mock_refund:
            mock_refund.return_value = (True, "re_partial_1", {})
            # First refund: 1500 minor
            p1 = AdvertisingCampaignService.refund_campaign(
                campaign=gbp_approved_campaign,
                refund_minor=1500,
                reason="First partial refund",
            )
            assert p1.payment_status == CampaignPaymentStatusChoices.PARTIALLY_REFUNDED
            assert p1.refund_amount_minor == 1500
            assert mock_refund.call_count == 1

            # Second refund of EXACT SAME AMOUNT (1500 minor)
            mock_refund.return_value = (True, "re_partial_2", {})
            p2 = AdvertisingCampaignService.refund_campaign(
                campaign=gbp_approved_campaign,
                refund_minor=1500,
                reason="Second partial refund of equal amount",
            )
            assert p2.payment_status == CampaignPaymentStatusChoices.PARTIALLY_REFUNDED
            assert p2.refund_amount_minor == 3000
            assert mock_refund.call_count == 2

            # Verify CampaignRefundOperation records
            ops = payment.refund_operations.order_by('created_at')
            assert ops.count() == 2
            assert ops[0].amount_minor == 1500
            assert ops[0].status == CampaignRefundStatusChoices.SUCCEEDED
            assert ops[1].amount_minor == 1500
            assert ops[1].status == CampaignRefundStatusChoices.SUCCEEDED
            assert ops[0].operation_id != ops[1].operation_id

            # Third refund: exceeding remaining balance (remaining = 3000, attempt 3500)
            with pytest.raises(ValidationError) as exc_info:
                AdvertisingCampaignService.refund_campaign(
                    campaign=gbp_approved_campaign,
                    refund_minor=3500,
                    reason="Excessive refund",
                )
            assert "exceeds remaining refundable amount" in str(exc_info.value)

            # Fourth refund: exact remaining balance (3000 minor)
            mock_refund.return_value = (True, "re_partial_3", {})
            p3 = AdvertisingCampaignService.refund_campaign(
                campaign=gbp_approved_campaign,
                refund_minor=3000,
                reason="Final partial refund",
            )
            assert p3.payment_status == CampaignPaymentStatusChoices.REFUNDED
            assert p3.refund_amount_minor == 6000
            assert ops.filter(status=CampaignRefundStatusChoices.SUCCEEDED).count() == 3

    def test_refund_operation_id_idempotency_retry(self, gbp_approved_campaign):
        """Reusing the exact same operation_id returns existing payment without re-calling gateway."""
        payment = AdvertisingCampaignService.record_successful_payment(
            campaign_id=gbp_approved_campaign.id,
            provider="STRIPE",
            gateway_reference="pi_op_idem",
            gateway_payment_id="ch_op_idem",
            amount_minor=5000,
            currency="GBP",
        )
        custom_op_id = "custom_op_abc123"

        with patch('apps.marketplace.payments.stripe_provider.StripePaymentProvider.issue_refund') as mock_refund:
            mock_refund.return_value = (True, "re_stripe_op_1", {})
            p1 = AdvertisingCampaignService.refund_campaign(
                campaign=gbp_approved_campaign,
                refund_minor=2000,
                reason="Initial refund call",
                operation_id=custom_op_id,
            )
            assert p1.refund_amount_minor == 2000
            assert mock_refund.call_count == 1

            # Retry with exact same operation_id
            p2 = AdvertisingCampaignService.refund_campaign(
                campaign=gbp_approved_campaign,
                refund_minor=2000,
                reason="Retried refund call",
                operation_id=custom_op_id,
            )
            assert p2.refund_amount_minor == 2000
            assert mock_refund.call_count == 1  # Not called again!

            op = payment.refund_operations.get(operation_id=custom_op_id)
            assert op.status == CampaignRefundStatusChoices.SUCCEEDED
            assert op.gateway_refund_id == "re_stripe_op_1"

    def test_live_advertising_payment_safety_gate(self, gbp_approved_campaign):
        """Enforces LIVE_ADVERTISING_PAYMENTS_ENABLED = False server-side across payments, refunds, and webhooks."""
        from django.conf import settings

        # 1. Payment session in live mode is blocked when LIVE_ADVERTISING_PAYMENTS_ENABLED=False
        with patch.object(settings, 'LIVE_ADVERTISING_PAYMENTS_ENABLED', False):
            with patch('apps.marketplace.payments.stripe_provider.StripePaymentProvider._is_test_mode_allowed', return_value=False):
                with pytest.raises(ValidationError) as exc:
                    AdvertisingCampaignService.create_payment_session(gbp_approved_campaign)
                assert "Live commercial advertising payments are disabled" in str(exc.value)

        # 2. Live refund dispatch is blocked when LIVE_ADVERTISING_PAYMENTS_ENABLED=False
        payment = AdvertisingCampaignService.record_successful_payment(
            campaign_id=gbp_approved_campaign.id,
            provider="STRIPE",
            gateway_reference="pi_live_gate",
            gateway_payment_id="ch_live_gate",
            amount_minor=gbp_approved_campaign.total_budget_minor,
            currency="GBP",
        )
        with patch.object(settings, 'LIVE_ADVERTISING_PAYMENTS_ENABLED', False):
            with patch('apps.marketplace.payments.stripe_provider.StripePaymentProvider._is_test_mode_allowed', return_value=False):
                with pytest.raises(ValidationError) as exc:
                    AdvertisingCampaignService.refund_campaign(
                        campaign=gbp_approved_campaign,
                        refund_minor=1000,
                        reason="Live refund attempt",
                    )
                assert "Live gateway advertising refunds are disabled" in str(exc.value)

        # 3. Live webhook when LIVE_ADVERTISING_PAYMENTS_ENABLED=False:
        # Acknowledges webhook, persists event, records payment, but withholds activation
        gbp_approved_campaign.status = CampaignStatusChoices.PAYMENT_PENDING
        gbp_approved_campaign.payment_status = CampaignPaymentStatusChoices.PENDING
        gbp_approved_campaign.save()

        client = APIClient()
        live_payload = {
            "type": "payment_intent.succeeded",
            "livemode": True,  # Claims to be live
            "data": {
                "object": {
                    "id": "pi_live_wb_gate",
                    "livemode": True,
                    "amount": gbp_approved_campaign.total_budget_minor,
                    "currency": "gbp",
                    "metadata": {
                        "campaign_id": str(gbp_approved_campaign.id),
                    },
                }
            }
        }
        body_bytes = json.dumps(live_payload).encode('utf-8')
        with patch.object(settings, 'LIVE_ADVERTISING_PAYMENTS_ENABLED', False):
            with patch('apps.marketplace.payments.stripe_provider.StripePaymentProvider.verify_webhook', return_value=(True, "evt_live_1", "payment_intent.succeeded", live_payload)):
                response = client.post(
                    '/api/v1/marketplace/advertising/webhook/stripe/',
                    data=body_bytes,
                    content_type='application/json',
                    HTTP_STRIPE_SIGNATURE='sig_live',
                )
                # Successfully acknowledged (200), not rejected with 403
                assert response.status_code == 200
                assert response.data['status'] == 'payment_recorded_activation_held'

                # Payment ledger updated
                gbp_approved_campaign.refresh_from_db()
                assert gbp_approved_campaign.payment_status == CampaignPaymentStatusChoices.PAID
                # Campaign remains unactivated (not ACTIVE or SCHEDULED)
                assert gbp_approved_campaign.status == CampaignStatusChoices.PAYMENT_PENDING

                # Event persisted idempotently
                event = PaymentWebhookEvent.objects.get(provider="STRIPE", event_id="evt_live_1")
                assert event.processed is True

        # 4. Live refund webhook when LIVE_ADVERTISING_PAYMENTS_ENABLED=False reconciles passively
        live_refund_payload = {
            "type": "charge.refunded",
            "livemode": True,
            "data": {
                "object": {
                    "id": "ch_live_wb_gate",
                    "livemode": True,
                    "amount_refunded": gbp_approved_campaign.total_budget_minor,
                    "currency": "gbp",
                    "metadata": {
                        "campaign_id": str(gbp_approved_campaign.id),
                    },
                }
            }
        }
        rfnd_body_bytes = json.dumps(live_refund_payload).encode('utf-8')
        with patch.object(settings, 'LIVE_ADVERTISING_PAYMENTS_ENABLED', False):
            with patch('apps.marketplace.payments.stripe_provider.StripePaymentProvider.verify_webhook', return_value=(True, "evt_live_rfnd_1", "charge.refunded", live_refund_payload)):
                rfnd_resp = client.post(
                    '/api/v1/marketplace/advertising/webhook/stripe/',
                    data=rfnd_body_bytes,
                    content_type='application/json',
                    HTTP_STRIPE_SIGNATURE='sig_live_rfnd',
                )
                assert rfnd_resp.status_code == 200
                assert rfnd_resp.data['status'] == 'refund_reconciled'

                gbp_approved_campaign.refresh_from_db()
                assert gbp_approved_campaign.payment_status == CampaignPaymentStatusChoices.REFUNDED

    def test_webhook_never_dispatches_outbound_refund(self, gbp_approved_campaign):
        """Regression test: Incoming refund webhooks perform passive reconciliation and NEVER dispatch outbound refunds."""
        payment = AdvertisingCampaignService.record_successful_payment(
            campaign_id=gbp_approved_campaign.id,
            provider="STRIPE",
            gateway_reference="pi_no_outbound",
            gateway_payment_id="ch_no_outbound",
            amount_minor=gbp_approved_campaign.total_budget_minor,
            currency="GBP",
        )
        client = APIClient()
        payload = {
            "type": "charge.refunded",
            "data": {
                "object": {
                    "id": "ch_no_outbound",
                    "amount_refunded": 2500,
                    "currency": "gbp",
                    "refunds": {
                        "data": [
                            {
                                "id": "re_passive_sync_1",
                                "amount": 2500,
                                "metadata": {
                                    "campaign_id": str(gbp_approved_campaign.id),
                                    "operation_id": "ref_passive_test",
                                }
                            }
                        ]
                    },
                    "metadata": {
                        "campaign_id": str(gbp_approved_campaign.id),
                    },
                }
            }
        }
        body_bytes = json.dumps(payload).encode('utf-8')

        with patch('apps.marketplace.payments.stripe_provider.StripePaymentProvider.issue_refund') as mock_stripe_refund:
            with patch('apps.marketplace.payments.razorpay_provider.RazorpayPaymentProvider.issue_refund') as mock_rzp_refund:
                with patch('apps.marketplace.payments.stripe_provider.StripePaymentProvider.verify_webhook', return_value=(True, "evt_no_outbound_1", "charge.refunded", payload)):
                    response = client.post(
                        '/api/v1/marketplace/advertising/webhook/stripe/',
                        data=body_bytes,
                        content_type='application/json',
                        HTTP_STRIPE_SIGNATURE='sig_test',
                    )
                    assert response.status_code == 200
                    assert response.data['status'] == 'refund_reconciled'

                    # PROVE outbound refund dispatch was NEVER called
                    assert mock_stripe_refund.call_count == 0
                    assert mock_rzp_refund.call_count == 0

                    payment.refresh_from_db()
                    assert payment.payment_status == CampaignPaymentStatusChoices.PARTIALLY_REFUNDED
                    assert payment.refund_amount_minor == 2500
                    op = payment.refund_operations.get(gateway_refund_id="re_passive_sync_1")
                    assert op.status == CampaignRefundStatusChoices.SUCCEEDED
                    assert op.amount_minor == 2500

    def test_stripe_webhook_cumulative_amount_refunded_incremental_handling(self, gbp_approved_campaign):
        """Stripe cumulative amount_refunded is reconciled incrementally without double-counting."""
        total_minor = 10000  # 100.00 GBP
        gbp_approved_campaign.total_budget_minor = total_minor
        gbp_approved_campaign.save()

        payment = AdvertisingCampaignService.record_successful_payment(
            campaign_id=gbp_approved_campaign.id,
            provider="STRIPE",
            gateway_reference="pi_cumul_test",
            gateway_payment_id="ch_cumul_test",
            amount_minor=total_minor,
            currency="GBP",
        )
        client = APIClient()

        # First refund: cumulative 3000 minor (£30)
        p1_payload = {
            "type": "charge.refunded",
            "data": {
                "object": {
                    "id": "ch_cumul_test",
                    "amount_refunded": 3000,
                    "currency": "gbp",
                    "metadata": {"campaign_id": str(gbp_approved_campaign.id)},
                }
            }
        }
        with patch('apps.marketplace.payments.stripe_provider.StripePaymentProvider.verify_webhook', return_value=(True, "evt_cumul_1", "charge.refunded", p1_payload)):
            r1 = client.post(
                '/api/v1/marketplace/advertising/webhook/stripe/',
                data=json.dumps(p1_payload).encode('utf-8'),
                content_type='application/json',
            )
            assert r1.status_code == 200

            payment.refresh_from_db()
            assert payment.refund_amount_minor == 3000
            assert payment.refund_operations.count() == 1

        # Second refund: Stripe sends cumulative amount_refunded = 5000 minor (£50 total, +£20 incremental)
        p2_payload = {
            "type": "charge.refunded",
            "data": {
                "object": {
                    "id": "ch_cumul_test",
                    "amount_refunded": 5000,
                    "currency": "gbp",
                    "metadata": {"campaign_id": str(gbp_approved_campaign.id)},
                }
            }
        }
        with patch('apps.marketplace.payments.stripe_provider.StripePaymentProvider.verify_webhook', return_value=(True, "evt_cumul_2", "charge.refunded", p2_payload)):
            r2 = client.post(
                '/api/v1/marketplace/advertising/webhook/stripe/',
                data=json.dumps(p2_payload).encode('utf-8'),
                content_type='application/json',
            )
            assert r2.status_code == 200

            payment.refresh_from_db()
            # Must be 5000, NOT 3000 + 5000 = 8000!
            assert payment.refund_amount_minor == 5000
            assert payment.refund_operations.count() == 2
            ops = payment.refund_operations.order_by('created_at')
            assert ops[0].amount_minor == 3000
            assert ops[1].amount_minor == 2000

        # Duplicate replay of cumulative amount 5000: does not add any extra refund
        with patch('apps.marketplace.payments.stripe_provider.StripePaymentProvider.verify_webhook', return_value=(True, "evt_cumul_3", "charge.refunded", p2_payload)):
            r3 = client.post(
                '/api/v1/marketplace/advertising/webhook/stripe/',
                data=json.dumps(p2_payload).encode('utf-8'),
                content_type='application/json',
            )
            assert r3.status_code == 200

            payment.refresh_from_db()
            assert payment.refund_amount_minor == 5000
            assert payment.refund_operations.count() == 2

    def test_unmatched_refund_webhook_recorded_safely(self):
        """Unmatched webhook events are safely recorded into PaymentWebhookEvent for reconciliation without errors."""
        client = APIClient()
        payload = {
            "type": "charge.refunded",
            "data": {
                "object": {
                    "id": "ch_unknown_999",
                    "amount_refunded": 1000,
                    "metadata": {"campaign_id": str(uuid.uuid4())},
                }
            }
        }
        with patch('apps.marketplace.payments.stripe_provider.StripePaymentProvider.verify_webhook', return_value=(True, "evt_unmatched_1", "charge.refunded", payload)):
            response = client.post(
                '/api/v1/marketplace/advertising/webhook/stripe/',
                data=json.dumps(payload).encode('utf-8'),
                content_type='application/json',
            )
            assert response.status_code == 200
            assert response.data['status'] == 'unmatched_recorded'

            event = PaymentWebhookEvent.objects.get(provider="STRIPE", event_id="evt_unmatched_1")
            assert event.processed is True

    def test_deterministic_collision_resistant_gateway_idempotency_key(self):
        """Gateway idempotency key derives deterministically from full operation_id and resists prefix collisions."""
        from apps.marketplace.advertising_service import generate_campaign_refund_gateway_key

        test_pid = uuid.uuid4()

        # 1. Stability across retries
        op_1 = "ref_a1b2c3d4e5f67890"
        key_1a = generate_campaign_refund_gateway_key(test_pid, op_1)
        key_1b = generate_campaign_refund_gateway_key(test_pid, op_1)
        assert key_1a == key_1b
        assert key_1a.startswith("ADV-REF-")

        # 2. Collision resistance for IDs sharing 8-char prefixes like 'ref_'
        op_2a = "ref_common_prefix_0001"
        op_2b = "ref_common_prefix_0002"
        key_2a = generate_campaign_refund_gateway_key(test_pid, op_2a)
        key_2b = generate_campaign_refund_gateway_key(test_pid, op_2b)
        assert key_2a != key_2b  # Slicing [:8] would have collided on 'REF_COMM'!

        # 3. Collision resistance for webhook IDs sharing 'wh_' prefix
        op_wh1 = "wh_evt_stripe_charge_refunded_1001"
        op_wh2 = "wh_evt_stripe_charge_refunded_1002"
        key_wh1 = generate_campaign_refund_gateway_key(test_pid, op_wh1)
        key_wh2 = generate_campaign_refund_gateway_key(test_pid, op_wh2)
        assert key_wh1 != key_wh2

        # 4. Respects gateway length constraints (Razorpay max 40 characters)
        assert len(key_1a) <= 40
        assert len(key_2a) <= 40
        assert len(key_wh1) <= 40
        assert len(key_1a) >= 10

    def test_separate_charge_and_refund_controls(self, seller_user, gbp_approved_campaign):
        """
        Verifies separation of live charge and refund controls:
        - When LIVE_ADVERTISING_CHARGES_ENABLED=False, live payment sessions are blocked.
        - When LIVE_ADVERTISING_REFUNDS_ENABLED=True, refunds can proceed even with charges disabled.
        - When LIVE_ADVERTISING_REFUNDS_ENABLED=False, live refunds are blocked.
        """
        from django.test import override_settings
        from apps.marketplace.payments.stripe_provider import StripePaymentProvider

        # 1. LIVE_ADVERTISING_CHARGES_ENABLED=False blocks live payment session creation
        with override_settings(LIVE_ADVERTISING_CHARGES_ENABLED=False, LIVE_ADVERTISING_PAYMENTS_ENABLED=False):
            with patch.object(StripePaymentProvider, '_is_test_mode_allowed', return_value=False):
                with pytest.raises(ValidationError, match="Live commercial advertising payments are disabled"):
                    AdvertisingCampaignService.create_payment_session(
                        campaign=gbp_approved_campaign,
                    )

        # 2. Record a live payment
        payment = CampaignPayment.objects.create(
            campaign=gbp_approved_campaign,
            provider="STRIPE",
            gateway_reference="cs_live_test_123",
            gateway_payment_id="pi_live_test_123",
            amount_minor=5000,
            currency="GBP",
            payment_status=CampaignPaymentStatusChoices.PAID,
            raw_response={"livemode": True},
        )
        gbp_approved_campaign.payment_status = CampaignPaymentStatusChoices.PAID
        gbp_approved_campaign.status = CampaignStatusChoices.ACTIVE
        gbp_approved_campaign.save()

        # 3. LIVE_ADVERTISING_REFUNDS_ENABLED=False blocks live gateway refund dispatch
        with override_settings(LIVE_ADVERTISING_REFUNDS_ENABLED=False):
            with patch.object(StripePaymentProvider, '_is_test_mode_allowed', return_value=False):
                with pytest.raises(ValidationError, match="Live gateway advertising refunds are disabled"):
                    AdvertisingCampaignService.refund_campaign(
                        campaign=gbp_approved_campaign,
                        refund_minor=2000,
                        reason="Test blocked live refund",
                    )
            failed_op = CampaignRefundOperation.objects.filter(payment=payment, status=CampaignRefundStatusChoices.FAILED).first()
            assert failed_op is not None
            assert failed_op.amount_minor == 2000

        # 4. LIVE_ADVERTISING_CHARGES_ENABLED=False but LIVE_ADVERTISING_REFUNDS_ENABLED=True allows live refund!
        with override_settings(LIVE_ADVERTISING_CHARGES_ENABLED=False, LIVE_ADVERTISING_REFUNDS_ENABLED=True):
            with patch.object(StripePaymentProvider, '_is_test_mode_allowed', return_value=False), \
                 patch.object(StripePaymentProvider, 'issue_refund', return_value=(True, "re_live_success_999", {})):
                refunded_payment = AdvertisingCampaignService.refund_campaign(
                    campaign=gbp_approved_campaign,
                    refund_minor=2000,
                    reason="Authorized live refund while charges disabled",
                    operation_id="ref_authorized_live_01",
                )
                assert refunded_payment is not None
                assert refunded_payment.payment_status == CampaignPaymentStatusChoices.PARTIALLY_REFUNDED
                succeeded_op = CampaignRefundOperation.objects.get(operation_id="ref_authorized_live_01")
                assert succeeded_op.status == CampaignRefundStatusChoices.SUCCEEDED
                assert succeeded_op.gateway_refund_id == "re_live_success_999"
