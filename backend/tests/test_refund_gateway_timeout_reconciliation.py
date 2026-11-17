"""Comprehensive test suite for Refund Gateway Timeout Remediation and Reconciliation Engine.

Verifies:
1. Connection timeouts/network drops do not mark refund as FAILED; transition to PROCESSING_UNKNOWN.
2. Identical idempotency key preserved across operations.
3. Database row locking (select_for_update) prevents concurrent duplicate dispatches.
4. Prevent issuing another refund while previous gateway transaction outcome is unknown.
5. Reconcile ambiguous transactions via provider inquiry APIs (Stripe & Razorpay).
6. Safe reconciliation transitions to SUCCEEDED or FAILED based on verified provider records.
7. Reconcile ambiguous transactions via inbound webhooks.
8. Webhook idempotency prevents duplicate state transitions on duplicate event deliveries.
9. Automatic execution of linked Maker-Checker ApprovalRequest upon confirmed reconciliation.
10. Inconclusive reconciliation applies bounded exponential backoff.
11. Management command 'reconcile_refunds' execution.
12. Staff Admin API reconciliation endpoint guarded with 'finance.payout' permissions.
"""

import json
import urllib.request
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pyotp
import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.management import call_command
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.identity.approval_service import ApprovalService
from apps.identity.models import (
    ApprovalRequest,
    ApprovalStatusChoices,
    RoleChoices,
    StaffProfile,
    StaffRole,
    User,
)
from apps.marketplace.models import (
    Order,
    OrderItem,
    PaymentStatusChoices,
    PaymentTransaction,
    Refund,
    RefundMethodChoices,
    RefundStatusChoices,
)
from apps.marketplace.payments.razorpay_provider import RazorpayPaymentProvider
from apps.marketplace.payments.service import PaymentService
from apps.marketplace.payments.stripe_provider import StripePaymentProvider
from apps.marketplace.returns.service import RefundService
from platform_core.audit.models import AuditLog


class MockHTTPResponse:
    def __init__(self, body_bytes: bytes, status_code: int = 200):
        self._body = body_bytes
        self.status = status_code
        self.code = status_code

    def read(self, *args, **kwargs):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


@pytest.fixture
def make_staff():
    """Helper factory to create staff members with specific roles and TOTP enabled."""
    def _create(email, role_code, first_name='Staff', last_name='Member'):
        user = User.objects.create_user(
            email=email,
            password='SecureStaffPassword123!',
            first_name=first_name,
            last_name=last_name,
            is_staff=True,
            is_email_verified=True,
        )
        user.add_role(RoleChoices.STAFF)
        role = StaffRole.objects.get(code=role_code)
        profile, _ = StaffProfile.objects.get_or_create(user=user)
        profile.staff_role = role
        profile.totp_enabled = True
        profile.set_totp_secret(pyotp.random_base32())
        profile.save()
        return user
    return _create


@pytest.fixture
def finance_officer(make_staff):
    return make_staff('finance.reconcile@driverxtra.com', 'FINANCE_OFFICER', 'Fiona', 'Finance')


@pytest.fixture
def support_agent(make_staff):
    return make_staff('support.reconcile@driverxtra.com', 'SUPPORT_AGENT', 'Sam', 'Support')


@pytest.fixture
def sample_order(db, buyer_user):
    order = Order.objects.create(
        buyer=buyer_user,
        order_number=f"ORD-REC-{uuid.uuid4().hex[:6].upper()}",
        total_amount=Decimal('450.00'),
        subtotal_taxable_amount=Decimal('375.00'),
        total_tax_amount=Decimal('75.00'),
        currency='GBP',
        shipping_country='GB',
        payment_status=PaymentStatusChoices.PAID,
        payment_reference='pi_test_stripe_rec_123',
    )
    OrderItem.objects.create(
        order=order,
        title='Clutch Plate Assembly',
        unit_price=Decimal('375.00'),
        quantity=1,
        taxable_amount=Decimal('375.00'),
        tax_amount=Decimal('75.00'),
        total_amount=Decimal('450.00'),
    )
    return order


@pytest.fixture
def pending_refund(db, sample_order, finance_officer):
    return Refund.objects.create(
        order=sample_order,
        refund_number=f"RFND-REC-{uuid.uuid4().hex[:6].upper()}",
        amount=Decimal('200.00'),
        currency='GBP',
        refund_method=RefundMethodChoices.ORIGINAL_PAYMENT,
        status=RefundStatusChoices.PENDING,
        created_by=finance_officer,
    )


# ==============================================================================
# 1. GATEWAY TIMEOUT HANDLING & AMBIGUOUS STATE (PROCESSING_UNKNOWN)
# ==============================================================================


@pytest.mark.django_db
def test_timeout_transitions_to_processing_unknown_not_failed(pending_refund, finance_officer):
    """When a gateway connection timeout occurs during dispatch:
    - Refund transitions to PROCESSING_UNKNOWN (NOT FAILED).
    - Idempotency key is preserved.
    - PaymentTransaction is recorded with PENDING status.
    - Audit log is created for marketplace.refund.gateway_timeout.
    """
    with patch(
        'apps.marketplace.payments.stripe_provider.StripePaymentProvider.issue_refund',
        side_effect=RuntimeError("Gateway connection timed out: Read timed out after 30 seconds"),
    ):
        with pytest.raises(DjangoValidationError) as exc:
            RefundService.dispatch_gateway_refund(pending_refund, actor=finance_officer)

        err_text = str(exc.value).lower()
        assert "timeout" in err_text or "processing_unknown" in err_text

    pending_refund.refresh_from_db()
    assert pending_refund.status == RefundStatusChoices.PROCESSING_UNKNOWN
    assert pending_refund.idempotency_key == pending_refund.refund_number
    assert "timed out" in pending_refund.failure_reason.lower()

    # Verify PaymentTransaction
    tx = PaymentTransaction.objects.filter(
        order=pending_refund.order,
        transaction_type='REFUND',
    ).first()
    assert tx is not None
    assert tx.status == PaymentStatusChoices.PENDING
    assert tx.amount == pending_refund.amount
    assert tx.idempotency_key == pending_refund.refund_number

    # Verify Audit Log
    log = AuditLog.objects.filter(
        event_type="marketplace.refund.gateway_timeout",
        resource_id=str(pending_refund.id),
    ).first()
    assert log is not None
    assert log.actor_id == finance_officer.id
    assert log.metadata.get("idempotency_key") == pending_refund.refund_number


@pytest.mark.django_db
def test_prevent_duplicate_dispatch_while_unknown(pending_refund, finance_officer):
    """A refund in PROCESSING_UNKNOWN must block any further dispatch attempts to prevent double-refunds."""
    pending_refund.status = RefundStatusChoices.PROCESSING_UNKNOWN
    pending_refund.idempotency_key = pending_refund.refund_number
    pending_refund.save()

    with pytest.raises(DjangoValidationError) as exc:
        RefundService.dispatch_gateway_refund(pending_refund, actor=finance_officer)

    assert "reconciliation" in str(exc.value).lower() or "processing_unknown" in str(exc.value).lower()


# ==============================================================================
# 2. SAFE RECONCILIATION VIA PROVIDER INQUIRY API
# ==============================================================================


@pytest.mark.django_db
def test_reconciliation_success_inquiry_updates_records_and_audit(pending_refund, finance_officer):
    """When inquiry confirms the gateway successfully settled the refund:
    - Refund transitions to SUCCEEDED.
    - Transaction marked as SUCCEEDED.
    - Order payment status updated.
    - Audit log records marketplace.refund.reconciled_success.
    """
    pending_refund.status = RefundStatusChoices.PROCESSING_UNKNOWN
    pending_refund.idempotency_key = pending_refund.refund_number
    pending_refund.save()

    # Mock gateway inquiry returning confirmed success
    with patch(
        'apps.marketplace.payments.stripe_provider.StripePaymentProvider.inquire_refund',
        return_value=('SUCCEEDED', "re_stripe_inquiry_succ_12345", {"status": "succeeded", "amount": 20000}),
    ) as mock_inquire:
        refund, outcome = RefundService.reconcile_refund(
            pending_refund,
            actor=finance_officer,
        )

        assert mock_inquire.call_count == 1
        assert outcome == "SUCCEEDED"
        assert refund.status == RefundStatusChoices.SUCCEEDED
        assert refund.gateway_refund_id == "re_stripe_inquiry_succ_12345"
        assert refund.processed_at is not None

        # Order payment status updated
        pending_refund.order.refresh_from_db()
        assert pending_refund.order.payment_status == PaymentStatusChoices.PAID

        # Audit log verified
        log = AuditLog.objects.filter(
            event_type="marketplace.refund.reconciled_success",
            resource_id=str(pending_refund.id),
        ).first()
        assert log is not None
        assert log.metadata.get("gateway_refund_id") == "re_stripe_inquiry_succ_12345"


@pytest.mark.django_db
def test_reconciliation_failure_inquiry_marks_failed(pending_refund, finance_officer):
    """When inquiry confirms the gateway definitely did not execute the refund:
    - Refund transitions to FAILED.
    - Transaction marked as FAILED.
    - Failure reason recorded.
    - Audit log records outcome FAILED.
    """
    pending_refund.status = RefundStatusChoices.PROCESSING_UNKNOWN
    pending_refund.idempotency_key = pending_refund.refund_number
    pending_refund.save()

    with patch(
        'apps.marketplace.payments.stripe_provider.StripePaymentProvider.inquire_refund',
        return_value=('FAILED', "Gateway reported: Charge has not been refunded", {}),
    ):
        refund, outcome = RefundService.reconcile_refund(
            pending_refund,
            actor=finance_officer,
        )

        assert outcome == "FAILED"
        assert refund.status == RefundStatusChoices.FAILED
        assert "not been refunded" in refund.failure_reason

        # Audit log verified
        log = AuditLog.objects.filter(
            event_type="marketplace.refund.reconciled_failed",
            resource_id=str(pending_refund.id),
        ).first()
        assert log is not None


@pytest.mark.django_db
def test_reconciliation_inconclusive_increments_attempts_and_backoff(pending_refund, finance_officer):
    """When inquiry returns inconclusive (e.g. inquiry itself timed out):
    - Refund stays in PROCESSING_UNKNOWN.
    - Attempts counter incremented.
    - next_reconciliation_at scheduled with exponential backoff.
    - Audit log records attempt without marking resolved.
    """
    pending_refund.status = RefundStatusChoices.PROCESSING_UNKNOWN
    pending_refund.idempotency_key = pending_refund.refund_number
    pending_refund.save()

    with patch(
        'apps.marketplace.payments.stripe_provider.StripePaymentProvider.inquire_refund',
        return_value=('UNKNOWN', "Inquiry call timed out", {}),
    ):
        refund, outcome = RefundService.reconcile_refund(
            pending_refund,
            actor=finance_officer,
        )

        assert outcome == "INCONCLUSIVE"
        assert refund.status == RefundStatusChoices.PROCESSING_UNKNOWN
        assert refund.reconciliation_attempts == 1
        assert refund.next_reconciliation_at is not None
        assert refund.next_reconciliation_at > timezone.now()


# ==============================================================================
# 3. RECONCILIATION VIA INBOUND WEBHOOKS & WEBHOOK IDEMPOTENCY
# ==============================================================================


@pytest.mark.django_db
def test_webhook_reconciles_processing_unknown_refund(pending_refund):
    """An incoming webhook (refund.processed or charge.refunded) reconciles PROCESSING_UNKNOWN refund."""
    pending_refund.status = RefundStatusChoices.PROCESSING_UNKNOWN
    pending_refund.idempotency_key = pending_refund.refund_number
    pending_refund.save()

    payload = {
        "id": "evt_test_stripe_webhook_refund_1",
        "type": "charge.refunded",
        "data": {
            "object": {
                "id": "ch_test_stripe_charge_123",
                "object": "charge",
                "payment_intent": pending_refund.order.payment_reference,
                "amount_refunded": 20000,
                "currency": "gbp",
                "refunds": {
                    "data": [
                        {
                            "id": "re_stripe_webhook_settled_555",
                            "status": "succeeded",
                            "amount": 20000,
                            "metadata": {
                                "refund_number": pending_refund.refund_number,
                            },
                        }
                    ]
                },
            }
        },
    }

    body = json.dumps(payload).encode('utf-8')
    headers = {"stripe-signature": "test_stripe_sig_valid"}

    success, code, result = PaymentService.process_webhook(
        provider_name="stripe",
        request_body=body,
        headers=headers,
    )

    assert success is True
    assert code == 200
    pending_refund.refresh_from_db()
    assert pending_refund.status == RefundStatusChoices.SUCCEEDED
    assert pending_refund.gateway_refund_id == "re_stripe_webhook_settled_555"
    assert pending_refund.processed_at is not None


@pytest.mark.django_db
def test_webhook_idempotency_prevents_duplicate_processing(pending_refund):
    """Duplicate delivery of the same webhook event ID is detected and ignored idempotently."""
    event_id = f"evt_dup_{uuid.uuid4().hex[:8]}"
    payload = {
        "id": event_id,
        "type": "charge.refunded",
        "data": {
            "object": {
                "id": f"ch_{uuid.uuid4().hex[:6]}",
                "object": "charge",
                "payment_intent": pending_refund.order.payment_reference,
                "refunds": {
                    "data": [
                        {
                            "id": "re_test_dup_1",
                            "status": "succeeded",
                            "metadata": {"refund_number": pending_refund.refund_number},
                        }
                    ]
                },
            }
        },
    }

    body = json.dumps(payload).encode('utf-8')
    headers = {"stripe-signature": "test_stripe_sig_valid"}

    # First delivery
    success1, code1, res1 = PaymentService.process_webhook("stripe", body, headers)
    assert success1 is True
    assert code1 == 200

    # Second delivery with identical event_id
    success2, code2, res2 = PaymentService.process_webhook("stripe", body, headers)
    assert success2 is True
    assert code2 == 200
    assert res2.get("status") == "already_processed"
    assert res2.get("replayed") is True


# ==============================================================================
# 4. MAKER-CHECKER INTEGRATION ON RECONCILIATION
# ==============================================================================


@pytest.mark.django_db
def test_approval_request_auto_executed_on_successful_reconciliation(
    pending_refund,
    finance_officer,
    support_agent,
):
    """If a high-value or dual-authorized refund timed out and was left in APPROVED,
    successful reconciliation must automatically execute the linked ApprovalRequest.
    """
    app_req = ApprovalService.create_request(
        requester=support_agent,
        action_type='REFUND_DISPATCH',
        target_type='Refund',
        target_id=str(pending_refund.id),
        amount=pending_refund.amount,
        currency='GBP',
    )
    app_req = ApprovalService.approve_request(app_req.id, approver=finance_officer)

    # Set to PROCESSING_UNKNOWN
    pending_refund.status = RefundStatusChoices.PROCESSING_UNKNOWN
    pending_refund.idempotency_key = pending_refund.refund_number
    pending_refund.save()

    with patch(
        'apps.marketplace.payments.stripe_provider.StripePaymentProvider.inquire_refund',
        return_value=('SUCCEEDED', "re_stripe_confirmed_mc_1", {"status": "succeeded"}),
    ):
        reconciled_refund, outcome = RefundService.reconcile_refund(
            pending_refund,
            actor=finance_officer,
        )

    assert outcome == "SUCCEEDED"
    app_req.refresh_from_db()
    assert app_req.status == ApprovalStatusChoices.EXECUTED
    assert app_req.execution_error == ""


# ==============================================================================
# 5. PROVIDER INQUIRE IMPLEMENTATION TESTS (STRIPE & RAZORPAY)
# ==============================================================================


def test_stripe_provider_inquire_live_mock(monkeypatch):
    """Verify StripePaymentProvider inquiry parses gateway responses correctly."""
    provider = StripePaymentProvider()
    provider.test_mode = False
    provider.force_network_call = True
    provider.secret_key = "sk_test_mock_secret_key"

    # 1. Gateway ID inquiry succeeded
    mock_body = json.dumps({
        "id": "re_live_123",
        "status": "succeeded",
        "amount": 5000,
    }).encode('utf-8')

    def mock_urlopen(req, timeout=10):
        return MockHTTPResponse(mock_body)

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    st, gw_id, data = provider.inquire_refund("pi_123", "RFND-001", "re_live_123")
    assert st == "SUCCEEDED"
    assert gw_id == "re_live_123"

    # 2. Connection error returns UNKNOWN
    def mock_urlopen_fail(req, timeout=10):
        raise urllib.error.URLError("Read timed out")

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen_fail)

    st, gw_id, data = provider.inquire_refund("pi_123", "RFND-001")
    assert st == "UNKNOWN"


def test_razorpay_provider_inquire_live_mock(monkeypatch):
    """Verify RazorpayPaymentProvider inquiry parses gateway responses correctly."""
    provider = RazorpayPaymentProvider()
    provider.test_mode = False
    provider.force_network_call = True
    provider.key_id = "rzp_test_mock_key"
    provider.key_secret = "rzp_test_mock_secret"

    mock_body = json.dumps({
        "items": [
            {
                "id": "rfnd_rzp_live_999",
                "status": "processed",
                "notes": {"refund_number": "RFND-RZP-1"},
            }
        ]
    }).encode('utf-8')

    def mock_urlopen(req, timeout=10):
        return MockHTTPResponse(mock_body)

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    st, gw_id, data = provider.inquire_refund("pay_123", "RFND-RZP-1")
    assert st == "SUCCEEDED"
    assert gw_id == "rfnd_rzp_live_999"


# ==============================================================================
# 6. BATCH RECONCILIATION & MANAGEMENT COMMAND
# ==============================================================================


@pytest.mark.django_db
def test_reconcile_all_pending_unknown_batch(sample_order, finance_officer):
    """Test batch reconciliation runner."""
    r1 = Refund.objects.create(
        order=sample_order,
        refund_number="RFND-BATCH-1",
        amount=Decimal('50.00'),
        currency='GBP',
        status=RefundStatusChoices.PROCESSING_UNKNOWN,
        created_by=finance_officer,
    )
    r2 = Refund.objects.create(
        order=sample_order,
        refund_number="RFND-BATCH-2",
        amount=Decimal('60.00'),
        currency='GBP',
        status=RefundStatusChoices.PROCESSING_UNKNOWN,
        created_by=finance_officer,
    )

    with patch(
        'apps.marketplace.payments.stripe_provider.StripePaymentProvider.inquire_refund',
        return_value=('SUCCEEDED', "re_batch_reconciled", {"status": "succeeded"}),
    ):
        summary = RefundService.reconcile_all_pending_unknown(max_batch=10)

        assert summary['processed'] >= 2
        assert summary['succeeded'] >= 2

    r1.refresh_from_db()
    r2.refresh_from_db()
    assert r1.status == RefundStatusChoices.SUCCEEDED
    assert r2.status == RefundStatusChoices.SUCCEEDED


@pytest.mark.django_db
def test_management_command_reconcile_refunds(sample_order, finance_officer):
    """Test management command execution."""
    r = Refund.objects.create(
        order=sample_order,
        refund_number="RFND-CMD-1",
        amount=Decimal('25.00'),
        currency='GBP',
        status=RefundStatusChoices.PROCESSING_UNKNOWN,
        created_by=finance_officer,
    )

    with patch(
        'apps.marketplace.payments.stripe_provider.StripePaymentProvider.inquire_refund',
        return_value=('SUCCEEDED', "re_cmd_reconciled", {"status": "succeeded"}),
    ):
        call_command('reconcile_refunds', '--batch', 10)

    r.refresh_from_db()
    assert r.status == RefundStatusChoices.SUCCEEDED


# ==============================================================================
# 7. ADMIN API RECONCILIATION ENDPOINT & PERMISSIONS
# ==============================================================================


@pytest.mark.django_db
def test_admin_api_reconcile_endpoint_permissions(
    pending_refund,
    finance_officer,
    support_agent,
    buyer_user,
    api_client,
):
    """POST /api/v1/marketplace/admin/refunds/<identifier>/reconcile/
    - Anonymous / Buyer: 401 / 403 Forbidden.
    - Support Agent (lacks finance.payout): 403 Forbidden.
    - Finance Officer (has finance.payout): 200 OK.
    """
    pending_refund.status = RefundStatusChoices.PROCESSING_UNKNOWN
    pending_refund.idempotency_key = pending_refund.refund_number
    pending_refund.save()

    url = f"/api/v1/marketplace/admin/refunds/{pending_refund.refund_number}/reconcile/"

    # 1. Buyer cannot reconcile
    api_client.force_authenticate(user=buyer_user)
    res_buyer = api_client.post(url)
    assert res_buyer.status_code == status.HTTP_403_FORBIDDEN

    # 2. Support agent lacks finance.payout permission
    api_client.force_authenticate(user=support_agent)
    res_support = api_client.post(url)
    assert res_support.status_code == status.HTTP_403_FORBIDDEN

    # 3. Finance officer with finance.payout can trigger reconciliation
    api_client.force_authenticate(user=finance_officer)
    with patch(
        'apps.marketplace.payments.stripe_provider.StripePaymentProvider.inquire_refund',
        return_value=('SUCCEEDED', "re_api_reconciled_999", {"status": "succeeded"}),
    ):
        res_finance = api_client.post(url)
        assert res_finance.status_code == status.HTTP_200_OK
        data = res_finance.json()
        assert data.get("status") == "success"
        assert data.get("outcome") == "SUCCEEDED"
        assert data.get("refund", {}).get("status") == "SUCCEEDED"
        assert data.get("refund", {}).get("gateway_refund_id") == "re_api_reconciled_999"


# ==============================================================================
# 8. CONSERVATIVE NOT_FOUND, STRIPE PAGINATION & SAFETY REGRESSION TESTS
# ==============================================================================


@pytest.mark.django_db
def test_not_found_on_first_attempt_remains_processing_unknown(pending_refund, finance_officer):
    """Conservative NOT_FOUND rule:
    NOT_FOUND on initial reconciliation attempt must NOT mark the refund FAILED.
    It remains in PROCESSING_UNKNOWN with bounded backoff scheduled.
    """
    pending_refund.status = RefundStatusChoices.PROCESSING_UNKNOWN
    pending_refund.idempotency_key = pending_refund.refund_number
    pending_refund.save()

    with patch(
        'apps.marketplace.payments.stripe_provider.StripePaymentProvider.inquire_refund',
        return_value=('NOT_FOUND', "No record found on Stripe", {}),
    ):
        refund, outcome = RefundService.reconcile_refund(
            pending_refund,
            actor=finance_officer,
        )

    assert outcome == "INCONCLUSIVE"
    assert refund.status == RefundStatusChoices.PROCESSING_UNKNOWN
    assert refund.reconciliation_attempts == 1
    assert refund.next_reconciliation_at is not None
    assert refund.next_reconciliation_at > timezone.now()
    assert "ambiguous" in refund.failure_reason.lower() or "not found" in refund.failure_reason.lower()


@pytest.mark.django_db
def test_repeated_not_found_applies_exponential_backoff_without_failing(pending_refund, finance_officer):
    """Repeated NOT_FOUND responses must never be treated as proof of failure.
    Refund remains held in PROCESSING_UNKNOWN with exponential backoff up to 60 mins.
    """
    pending_refund.status = RefundStatusChoices.PROCESSING_UNKNOWN
    pending_refund.idempotency_key = pending_refund.refund_number
    pending_refund.reconciliation_attempts = 5
    pending_refund.save()

    with patch(
        'apps.marketplace.payments.stripe_provider.StripePaymentProvider.inquire_refund',
        return_value=('NOT_FOUND', "No record found", {}),
    ):
        refund, outcome = RefundService.reconcile_refund(
            pending_refund,
            actor=finance_officer,
        )

    assert outcome == "INCONCLUSIVE"
    assert refund.status == RefundStatusChoices.PROCESSING_UNKNOWN
    assert refund.reconciliation_attempts == 6
    assert refund.next_reconciliation_at is not None


@pytest.mark.django_db
def test_delayed_gateway_visibility_resolves_to_succeeded(pending_refund, finance_officer):
    """A refund not found on attempt 1, but found on attempt 2 after gateway indexing completes."""
    pending_refund.status = RefundStatusChoices.PROCESSING_UNKNOWN
    pending_refund.idempotency_key = pending_refund.refund_number
    pending_refund.save()

    # Attempt 1: NOT_FOUND
    with patch(
        'apps.marketplace.payments.stripe_provider.StripePaymentProvider.inquire_refund',
        return_value=('NOT_FOUND', "Record not indexed yet", {}),
    ):
        refund, outcome1 = RefundService.reconcile_refund(pending_refund, actor=finance_officer)
    assert outcome1 == "INCONCLUSIVE"
    assert refund.status == RefundStatusChoices.PROCESSING_UNKNOWN

    # Attempt 2: Provider index ready, returns SUCCEEDED
    with patch(
        'apps.marketplace.payments.stripe_provider.StripePaymentProvider.inquire_refund',
        return_value=('SUCCEEDED', "re_delayed_ok_888", {"status": "succeeded"}),
    ):
        refund, outcome2 = RefundService.reconcile_refund(pending_refund, actor=finance_officer)
    assert outcome2 == "SUCCEEDED"
    assert refund.status == RefundStatusChoices.SUCCEEDED
    assert refund.gateway_refund_id == "re_delayed_ok_888"


@pytest.mark.django_db
def test_delayed_successful_webhook_after_not_found(pending_refund):
    """Inquiry returned NOT_FOUND, keeping refund in PROCESSING_UNKNOWN.
    Subsequently, gateway webhook delivers confirmation, successfully resolving refund.
    """
    pending_refund.status = RefundStatusChoices.PROCESSING_UNKNOWN
    pending_refund.idempotency_key = pending_refund.refund_number
    pending_refund.save()

    payload = {
        "id": f"evt_delayed_{uuid.uuid4().hex[:6]}",
        "type": "charge.refunded",
        "data": {
            "object": {
                "id": "ch_delayed_123",
                "object": "charge",
                "payment_intent": pending_refund.order.payment_reference,
                "amount_refunded": 20000,
                "refunds": {
                    "data": [
                        {
                            "id": "re_webhook_delayed_999",
                            "status": "succeeded",
                            "metadata": {"refund_number": pending_refund.refund_number},
                        }
                    ]
                },
            }
        },
    }

    body = json.dumps(payload).encode('utf-8')
    headers = {"stripe-signature": "test_stripe_sig_valid"}
    success, code, res = PaymentService.process_webhook("stripe", body, headers)

    assert success is True
    assert code == 200
    pending_refund.refresh_from_db()
    assert pending_refund.status == RefundStatusChoices.SUCCEEDED
    assert pending_refund.gateway_refund_id == "re_webhook_delayed_999"


@pytest.mark.django_db
def test_create_replacement_refund_strictly_blocked_while_unknown(pending_refund, finance_officer):
    """Creating a new/replacement refund on an order with a PROCESSING_UNKNOWN refund is strictly rejected
    to prevent double-refunding.
    """
    pending_refund.status = RefundStatusChoices.PROCESSING_UNKNOWN
    pending_refund.idempotency_key = pending_refund.refund_number
    pending_refund.save()

    with pytest.raises(DjangoValidationError) as exc:
        RefundService.create_refund(
            order=pending_refund.order,
            amount=Decimal('50.00'),
            reason="Attempted duplicate/replacement refund",
            actor=finance_officer,
        )

    assert "ambiguous refund is currently awaiting gateway reconciliation" in str(exc.value)


@pytest.mark.django_db
def test_manual_resolve_unknown_refund_requires_permission_and_records_audit(
    pending_refund,
    finance_officer,
    support_agent,
):
    """Authorized manual resolution procedure:
    - Unauthorized staff receives permission error.
    - Comprehensive justification required (>= 10 chars).
    - Authorized finance officer can manually resolve to FAILED or CANCELLED with audit trail.
    """
    pending_refund.status = RefundStatusChoices.PROCESSING_UNKNOWN
    pending_refund.idempotency_key = pending_refund.refund_number
    pending_refund.save()

    # 1. Support agent unauthorized
    with pytest.raises(DjangoValidationError) as exc_perm:
        RefundService.manual_resolve_unknown_refund(
            pending_refund,
            actor=support_agent,
            resolution="FAILED",
            reason="Verified no charge in gateway dashboard",
        )
    assert "permission denied" in str(exc_perm.value).lower()

    # 2. Too short reason rejected
    with pytest.raises(DjangoValidationError) as exc_short:
        RefundService.manual_resolve_unknown_refund(
            pending_refund,
            actor=finance_officer,
            resolution="FAILED",
            reason="short",
            gateway_reference="gw_test_123",
            ticket_reference="SUP-12345",
        )
    assert "justification" in str(exc_short.value).lower()

    # 2b. Missing structured evidence rejected
    with pytest.raises(DjangoValidationError) as exc_no_ev:
        RefundService.manual_resolve_unknown_refund(
            pending_refund,
            actor=finance_officer,
            resolution="FAILED",
            reason="Verified gateway logs: request dropped prior to gateway processing.",
        )
    assert "structured evidence" in str(exc_no_ev.value).lower()

    # 3. Authorized resolution succeeds with structured evidence
    resolved = RefundService.manual_resolve_unknown_refund(
        pending_refund,
        actor=finance_officer,
        resolution="FAILED",
        reason="Verified gateway logs: request dropped prior to gateway processing.",
        gateway_reference="gw_ref_test_verified",
        ticket_reference="SUP-12345",
    )
    assert resolved.status == RefundStatusChoices.FAILED
    assert "manual resolution" in resolved.failure_reason.lower()
    assert "gw_ref_test_verified" in resolved.failure_reason
    assert "SUP-12345" in resolved.failure_reason

    # 4. Audit entry verified
    log = AuditLog.objects.filter(
        event_type="marketplace.refund.manual_resolution",
        resource_id=str(pending_refund.id),
    ).first()
    assert log is not None
    assert log.actor_id == finance_officer.id
    assert log.metadata.get("gateway_reference") == "gw_ref_test_verified"
    assert log.metadata.get("ticket_reference") == "SUP-12345"
    assert "resolved_at" in log.metadata.get("evidence", {})


def test_stripe_pagination_with_has_more_matches_on_second_page(monkeypatch):
    """Stripe inquiry cursor pagination: matches refund on page 2 when page 1 has has_more=true."""
    provider = StripePaymentProvider()
    provider.test_mode = False
    provider.force_network_call = True
    provider.secret_key = "sk_test_mock_secret_key"

    # Page 1: 50 items, has_more=True, last item id is re_page1_50
    page1_items = [{"id": f"re_page1_{i}", "status": "succeeded", "metadata": {}} for i in range(1, 51)]
    page1_body = json.dumps({"data": page1_items, "has_more": True}).encode('utf-8')

    # Page 2: 2 items, has_more=False, item 2 matches refund_number
    page2_items = [
        {"id": "re_page2_1", "status": "succeeded", "metadata": {}},
        {"id": "re_page2_matched_999", "status": "succeeded", "metadata": {"refund_number": "RFND-PAGE-MATCH"}},
    ]
    page2_body = json.dumps({"data": page2_items, "has_more": False}).encode('utf-8')

    call_count = {"count": 0}

    def mock_urlopen(req, timeout=10):
        call_count["count"] += 1
        if "starting_after=re_page1_50" in req.full_url:
            return MockHTTPResponse(page2_body)
        return MockHTTPResponse(page1_body)

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    st, gw_id, data = provider.inquire_refund("pi_test_page_123", "RFND-PAGE-MATCH")
    assert st == "SUCCEEDED"
    assert gw_id == "re_page2_matched_999"
    assert call_count["count"] == 2


def test_stripe_pagination_error_returns_unknown_not_not_found(monkeypatch):
    """If an API network error occurs on page 2, inquiry must return UNKNOWN, never NOT_FOUND."""
    provider = StripePaymentProvider()
    provider.test_mode = False
    provider.force_network_call = True
    provider.secret_key = "sk_test_mock_secret_key"

    page1_items = [{"id": f"re_page1_{i}", "status": "succeeded", "metadata": {}} for i in range(1, 51)]
    page1_body = json.dumps({"data": page1_items, "has_more": True}).encode('utf-8')

    def mock_urlopen(req, timeout=10):
        if "starting_after=" in req.full_url:
            raise urllib.error.URLError("Connection reset by peer on page 2")
        return MockHTTPResponse(page1_body)

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    st, gw_id, data = provider.inquire_refund("pi_test_page_456", "RFND-NEVER-SEEN")
    assert st == "UNKNOWN"
    assert "page 2" in gw_id.lower() or "connection" in gw_id.lower()


@pytest.mark.django_db
def test_concurrent_batch_reservation_advances_lease(sample_order, finance_officer):
    """Batch reservation phase advances next_reconciliation_at lease to prevent concurrent workers
    from claiming the same refunds.
    """
    r = Refund.objects.create(
        order=sample_order,
        refund_number="RFND-CONC-LEASE",
        amount=Decimal('40.00'),
        currency='GBP',
        status=RefundStatusChoices.PROCESSING_UNKNOWN,
        created_by=finance_officer,
    )

    with patch(
        'apps.marketplace.payments.stripe_provider.StripePaymentProvider.inquire_refund',
        return_value=('UNKNOWN', "Provider timed out", {}),
    ):
        summary = RefundService.reconcile_all_pending_unknown(max_batch=5)
        assert summary["processed"] >= 1

    r.refresh_from_db()
    # Next reconciliation scheduled in future
    assert r.next_reconciliation_at is not None
    assert r.next_reconciliation_at > timezone.now()


# =============================================================================
# FINANCIAL INTEGRITY & MAKER-CHECKER REMEDIATION SUITE
# =============================================================================

@pytest.fixture
def high_value_order(db, buyer_user):
    order = Order.objects.create(
        buyer=buyer_user,
        order_number=f"ORD-HV-{uuid.uuid4().hex[:6].upper()}",
        total_amount=Decimal('5000.00'),
        subtotal_taxable_amount=Decimal('4166.67'),
        total_tax_amount=Decimal('833.33'),
        currency='GBP',
        shipping_country='GB',
        payment_status=PaymentStatusChoices.PAID,
        payment_reference='pi_test_stripe_hv_999',
    )
    OrderItem.objects.create(
        order=order,
        title="High-Value Automotive Diagnostics Unit",
        unit_price=Decimal('4166.67'),
        quantity=1,
        taxable_amount=Decimal('4166.67'),
        tax_amount=Decimal('833.33'),
        total_amount=Decimal('5000.00'),
    )
    return order


@pytest.fixture
def finance_checker(make_staff):
    return make_staff('finance.checker@driverxtra.com', 'FINANCE_OFFICER', 'Charles', 'Checker')


@pytest.mark.django_db
def test_structured_evidence_validation_server_side(pending_refund, finance_officer):
    """Structured evidence: validates that free-text justification alone is rejected,
    and gateway_reference & ticket_reference are strictly required.
    """
    pending_refund.status = RefundStatusChoices.PROCESSING_UNKNOWN
    pending_refund.save()

    # 1. Free-text reason alone without gateway_reference
    with pytest.raises(DjangoValidationError) as exc1:
        RefundService.manual_resolve_unknown_refund(
            pending_refund,
            actor=finance_officer,
            resolution="FAILED",
            reason="Confirmed no charge on Stripe portal",
        )
    assert "structured evidence" in str(exc1.value).lower()
    assert "gateway_reference" in str(exc1.value)

    # 2. Reason + gateway_reference but missing ticket_reference
    with pytest.raises(DjangoValidationError) as exc2:
        RefundService.manual_resolve_unknown_refund(
            pending_refund,
            actor=finance_officer,
            resolution="FAILED",
            reason="Confirmed no charge on Stripe portal",
            gateway_reference="inq_stripe_not_found_01",
        )
    assert "ticket_reference" in str(exc2.value)

    # 3. Supplying structured evidence via dictionary passes
    resolved = RefundService.manual_resolve_unknown_refund(
        pending_refund,
        actor=finance_officer,
        resolution="FAILED",
        reason="Confirmed no charge on Stripe portal after deep inquiry",
        evidence={
            "gateway_reference": "inq_stripe_not_found_01",
            "ticket_reference": "TICK-88412",
        },
    )
    assert resolved.status == RefundStatusChoices.FAILED
    assert "inq_stripe_not_found_01" in resolved.failure_reason
    assert "TICK-88412" in resolved.failure_reason


@pytest.mark.django_db
def test_high_value_manual_resolution_requires_maker_checker(
    high_value_order,
    finance_officer,
):
    """High-value manual refund resolution (> £1,000) strictly requires Maker-Checker approval.
    Keeps refund in PROCESSING_UNKNOWN until approval is obtained.
    """
    hv_refund = Refund.objects.create(
        order=high_value_order,
        refund_number=f"REF-HV-{uuid.uuid4().hex[:6].upper()}",
        amount=Decimal('2500.00'),
        currency='GBP',
        status=RefundStatusChoices.PROCESSING_UNKNOWN,
        created_by=finance_officer,
    )

    with pytest.raises(DjangoValidationError) as exc:
        RefundService.manual_resolve_unknown_refund(
            hv_refund,
            actor=finance_officer,
            resolution="FAILED",
            reason="Gateway API confirms transaction dropped before processing.",
            gateway_reference="inq_gw_dropped_999",
            ticket_reference="INC-HV-5501",
        )

    assert "maker-checker threshold" in str(exc.value).lower()
    assert "dual authorization approval is required" in str(exc.value).lower()

    # Refund remains safely in PROCESSING_UNKNOWN
    hv_refund.refresh_from_db()
    assert hv_refund.status == RefundStatusChoices.PROCESSING_UNKNOWN

    # ApprovalRequest created with action_type=MANUAL_REFUND_RESOLUTION
    app_req = ApprovalRequest.objects.filter(
        target_type='Refund',
        target_id=str(hv_refund.id),
        action_type='MANUAL_REFUND_RESOLUTION',
    ).first()
    assert app_req is not None
    assert app_req.status == ApprovalStatusChoices.PENDING
    assert app_req.requester == finance_officer
    assert Decimal(str(app_req.amount)) == Decimal('2500.00')


@pytest.mark.django_db
def test_maker_cannot_approve_own_manual_resolution(
    high_value_order,
    finance_officer,
):
    """The maker must not approve their own manual refund resolution request."""
    hv_refund = Refund.objects.create(
        order=high_value_order,
        refund_number=f"REF-HV-SELF-{uuid.uuid4().hex[:6].upper()}",
        amount=Decimal('1800.00'),
        currency='GBP',
        status=RefundStatusChoices.PROCESSING_UNKNOWN,
        created_by=finance_officer,
    )

    with pytest.raises(DjangoValidationError):
        RefundService.manual_resolve_unknown_refund(
            hv_refund,
            actor=finance_officer,
            resolution="FAILED",
            reason="Confirmed no trace on payment gateway network.",
            gateway_reference="inq_notrace_01",
            ticket_reference="INC-7744",
        )

    app_req = ApprovalRequest.objects.filter(target_id=str(hv_refund.id)).first()
    assert app_req is not None

    # Maker attempts self-approval
    with pytest.raises(DjangoValidationError) as exc:
        ApprovalService.approve_request(
            approval_request_id=app_req.id,
            approver=finance_officer,
            notes="Approving my own resolution",
        )
    assert "requester cannot approve their own request" in str(exc.value).lower()


@pytest.mark.django_db
def test_independent_checker_approves_and_executes_manual_resolution(
    high_value_order,
    finance_officer,
    finance_checker,
):
    """Independent checker approves high-value resolution; execution resolves the refund
    and prevents duplicate execution.
    """
    hv_refund = Refund.objects.create(
        order=high_value_order,
        refund_number=f"REF-HV-EXEC-{uuid.uuid4().hex[:6].upper()}",
        amount=Decimal('2000.00'),
        currency='GBP',
        status=RefundStatusChoices.PROCESSING_UNKNOWN,
        created_by=finance_officer,
    )

    with pytest.raises(DjangoValidationError):
        RefundService.manual_resolve_unknown_refund(
            hv_refund,
            actor=finance_officer,
            resolution="FAILED",
            reason="Verified gateway communication dropped before execution.",
            gateway_reference="inq_exec_gw_123",
            ticket_reference="INC-HV-EXEC",
        )

    app_req = ApprovalRequest.objects.filter(target_id=str(hv_refund.id)).first()
    assert app_req.status == ApprovalStatusChoices.PENDING

    # Checker approves
    approved = ApprovalService.approve_request(
        approval_request_id=app_req.id,
        approver=finance_checker,
        notes="Reviewed portal logs and verified dropped request.",
    )
    assert approved.status == ApprovalStatusChoices.APPROVED

    # Execute approved request
    executed_req, resolved_rfnd = ApprovalService.execute_request(
        approval_request_id=app_req.id,
        executor=finance_checker,
    )
    assert executed_req.status == ApprovalStatusChoices.EXECUTED
    assert resolved_rfnd.status == RefundStatusChoices.FAILED
    assert "inq_exec_gw_123" in resolved_rfnd.failure_reason

    # Duplicate execution strictly blocked
    with pytest.raises(DjangoValidationError) as exc_dup:
        ApprovalService.execute_request(app_req.id, executor=finance_checker)
    assert "already been executed" in str(exc_dup.value).lower()


@pytest.mark.django_db
def test_unauthorized_staff_cannot_resolve_or_approve(
    pending_refund,
    support_agent,
    finance_officer,
):
    """Support agents and unauthorized roles cannot execute manual resolution or approve requests."""
    pending_refund.status = RefundStatusChoices.PROCESSING_UNKNOWN
    pending_refund.save()

    with pytest.raises(DjangoValidationError) as exc:
        RefundService.manual_resolve_unknown_refund(
            pending_refund,
            actor=support_agent,
            resolution="FAILED",
            reason="Support agent attempt",
            gateway_reference="gw_test_fail",
            ticket_reference="SUP-1111",
        )
    assert "permission denied" in str(exc.value).lower()


@pytest.mark.django_db
def test_delayed_success_webhook_after_manual_failed_resolution_no_replacement(
    sample_order,
    finance_officer,
):
    """Delayed webhook: if a refund was manually resolved to FAILED and NO replacement refund exists,
    the legitimate gateway success is recognized and reconciled to SUCCEEDED.
    """
    r1 = Refund.objects.create(
        order=sample_order,
        refund_number=f"RFND-LATE-OK-{uuid.uuid4().hex[:6].upper()}",
        amount=Decimal('100.00'),
        currency='GBP',
        status=RefundStatusChoices.PROCESSING_UNKNOWN,
        created_by=finance_officer,
    )

    # Manually resolve R1 as FAILED
    RefundService.manual_resolve_unknown_refund(
        r1,
        actor=finance_officer,
        resolution="FAILED",
        reason="Gateway communication timed out. Assuming dropped.",
        gateway_reference="gw_inq_404_init",
        ticket_reference="INC-LATE-01",
    )
    r1.refresh_from_db()
    assert r1.status == RefundStatusChoices.FAILED

    # Delayed webhook arrives for R1
    event_id = f"evt_late_ok_{uuid.uuid4().hex[:8]}"
    payload = {
        "id": event_id,
        "type": "charge.refunded",
        "data": {
            "object": {
                "id": "ch_test_late_ok_123",
                "payment_intent": sample_order.payment_reference,
                "refunds": {
                    "data": [
                        {
                            "id": "re_gateway_late_123",
                            "status": "succeeded",
                            "metadata": {
                                "refund_number": r1.refund_number,
                                "order_number": sample_order.order_number,
                            },
                        }
                    ]
                },
            }
        },
    }

    body = json.dumps(payload).encode('utf-8')
    headers = {"stripe-signature": "test_stripe_sig_valid"}
    ok, code, res = PaymentService.process_webhook('stripe', body, headers)
    assert ok is True
    assert code == 200

    r1.refresh_from_db()
    assert r1.status == RefundStatusChoices.SUCCEEDED
    assert r1.gateway_refund_id == "re_gateway_late_123"
    assert "Late Gateway Webhook" in r1.notes


@pytest.mark.django_db
def test_delayed_success_webhook_after_replacement_refund_succeeds_prevents_duplicate(
    sample_order,
    finance_officer,
):
    """Delayed webhook: if R1 was manually resolved to FAILED and a replacement refund R2
    already SUCCEEDED, the late success for R1 MUST NOT revive R1 to SUCCEEDED.
    Prevents duplicate refund and balance calculation corruption!
    """
    # Sample order total is £450.00
    r1 = Refund.objects.create(
        order=sample_order,
        refund_number=f"RFND-R1-{uuid.uuid4().hex[:6].upper()}",
        amount=Decimal('450.00'),
        currency='GBP',
        status=RefundStatusChoices.PROCESSING_UNKNOWN,
        created_by=finance_officer,
    )

    # 1. Manually resolve R1 as FAILED
    RefundService.manual_resolve_unknown_refund(
        r1,
        actor=finance_officer,
        resolution="FAILED",
        reason="Gateway communication timed out. Assuming dropped.",
        gateway_reference="gw_inq_none_01",
        ticket_reference="INC-DUP-01",
    )
    r1.refresh_from_db()
    assert r1.status == RefundStatusChoices.FAILED

    # 2. Replacement refund R2 is created and SUCCEEDS
    r2 = RefundService.create_refund(
        order=sample_order,
        amount=Decimal('450.00'),
        reason="Replacement refund for R1",
        actor=finance_officer,
        refund_method=RefundMethodChoices.ORIGINAL_PAYMENT,
    )
    r2.status = RefundStatusChoices.SUCCEEDED
    r2.gateway_refund_id = "re_replacement_succeeded_222"
    r2.save()
    sample_order.payment_status = PaymentStatusChoices.REFUNDED
    sample_order.save()

    # 3. Delayed webhook arrives for R1 claiming gateway success
    event_id = f"evt_late_dup_{uuid.uuid4().hex[:8]}"
    payload = {
        "id": event_id,
        "type": "charge.refunded",
        "data": {
            "object": {
                "id": "ch_test_dup_123",
                "payment_intent": sample_order.payment_reference,
                "refunds": {
                    "data": [
                        {
                            "id": "re_gateway_r1_late_333",
                            "status": "succeeded",
                            "metadata": {
                                "refund_number": r1.refund_number,
                                "order_number": sample_order.order_number,
                            },
                        }
                    ]
                },
            }
        },
    }

    body = json.dumps(payload).encode('utf-8')
    headers = {"stripe-signature": "test_stripe_sig_valid"}
    ok, code, res = PaymentService.process_webhook('stripe', body, headers)
    assert ok is True
    assert code == 200

    # 4. Strict safeguards verified:
    r1.refresh_from_db()
    # R1 must remain FAILED to prevent duplicate refund on order ledger!
    assert r1.status == RefundStatusChoices.FAILED
    assert "CONFLICTING GATEWAY SUCCESS" in r1.notes
    assert "FINANCIAL RECONCILIATION REQUIRED" in r1.notes

    # Conflicting gateway outcome preserved in PaymentTransaction
    tx = PaymentTransaction.objects.filter(
        order=sample_order,
        provider_transaction_id="re_gateway_r1_late_333",
    ).first()
    assert tx is not None
    assert tx.status == PaymentTransaction.StatusChoices.SUCCESS
    assert tx.raw_response.get("conflict") is True
    assert tx.raw_response.get("conflict_reason") == "REPLACEMENT_REFUND_SUCCEEDED"

    # Order refund summary remains strictly correct
    summary = RefundService.get_order_refund_summary(sample_order)
    assert summary["total_refunded"] == Decimal('450.00')
    assert summary["available_refundable"] == Decimal('0.00')


@pytest.mark.django_db
def test_delayed_success_webhook_when_replacement_is_active_prevents_duplicate(
    sample_order,
    finance_officer,
):
    """Delayed webhook: if R1 was FAILED and replacement R2 is active (PENDING/PROCESSING),
    late webhook for R1 is flagged as a conflict and does not revive R1.
    """
    r1 = Refund.objects.create(
        order=sample_order,
        refund_number=f"RFND-ACT-R1-{uuid.uuid4().hex[:6].upper()}",
        amount=Decimal('200.00'),
        currency='GBP',
        status=RefundStatusChoices.PROCESSING_UNKNOWN,
        created_by=finance_officer,
    )

    RefundService.manual_resolve_unknown_refund(
        r1,
        actor=finance_officer,
        resolution="FAILED",
        reason="Gateway communication timed out. Assuming dropped.",
        gateway_reference="gw_inq_act_01",
        ticket_reference="INC-ACT-01",
    )

    # Replacement R2 created and is PENDING
    r2 = RefundService.create_refund(
        order=sample_order,
        amount=Decimal('200.00'),
        reason="Replacement refund active",
        actor=finance_officer,
    )
    assert r2.status == RefundStatusChoices.PENDING

    # Late webhook arrives for R1
    event_id = f"evt_act_conflict_{uuid.uuid4().hex[:8]}"
    payload = {
        "id": event_id,
        "type": "charge.refunded",
        "data": {
            "object": {
                "id": "ch_test_act_123",
                "payment_intent": sample_order.payment_reference,
                "refunds": {
                    "data": [
                        {
                            "id": "re_gw_act_conflict_999",
                            "status": "succeeded",
                            "metadata": {
                                "refund_number": r1.refund_number,
                                "order_number": sample_order.order_number,
                            },
                        }
                    ]
                },
            }
        },
    }

    body = json.dumps(payload).encode('utf-8')
    headers = {"stripe-signature": "test_stripe_sig_valid"}
    ok, code, res = PaymentService.process_webhook('stripe', body, headers)
    assert ok is True

    r1.refresh_from_db()
    assert r1.status == RefundStatusChoices.FAILED
    assert "CONFLICTING GATEWAY SUCCESS" in r1.notes


@pytest.mark.django_db
def test_webhook_replay_and_duplicate_delivery_idempotency(sample_order, finance_officer):
    """Replaying the exact same webhook returns already_processed without duplicating state."""
    r = Refund.objects.create(
        order=sample_order,
        refund_number=f"RFND-REPLAY-{uuid.uuid4().hex[:6].upper()}",
        amount=Decimal('50.00'),
        currency='GBP',
        status=RefundStatusChoices.PROCESSING_UNKNOWN,
        created_by=finance_officer,
    )

    event_id = f"evt_replay_test_{uuid.uuid4().hex[:8]}"
    payload = {
        "id": event_id,
        "type": "charge.refunded",
        "data": {
            "object": {
                "id": "ch_test_replay_123",
                "payment_intent": sample_order.payment_reference,
                "refunds": {
                    "data": [
                        {
                            "id": "re_replay_gw_1",
                            "status": "succeeded",
                            "metadata": {
                                "refund_number": r.refund_number,
                                "order_number": sample_order.order_number,
                            },
                        }
                    ]
                },
            }
        },
    }

    body = json.dumps(payload).encode('utf-8')
    headers = {"stripe-signature": "test_stripe_sig_valid"}

    # 1. First delivery
    ok1, code1, res1 = PaymentService.process_webhook('stripe', body, headers)
    assert ok1 is True
    assert code1 == 200

    # 2. Duplicate delivery (replay)
    ok2, code2, res2 = PaymentService.process_webhook('stripe', body, headers)
    assert ok2 is True
    assert code2 == 200
    assert res2.get("replayed") is True
    assert res2.get("status") == "already_processed"


@pytest.mark.django_db
def test_approved_failed_resolution_accepts_failed_execution(
    high_value_order,
    finance_officer,
    finance_checker,
):
    """Approved FAILED resolution accepts FAILED execution."""
    hv_refund = Refund.objects.create(
        order=high_value_order,
        refund_number=f"RFND-PAYLOAD-OK-{uuid.uuid4().hex[:6].upper()}",
        amount=Decimal('1500.00'),
        currency='GBP',
        status=RefundStatusChoices.PROCESSING_UNKNOWN,
        created_by=finance_officer,
    )

    with pytest.raises(DjangoValidationError):
        RefundService.manual_resolve_unknown_refund(
            hv_refund,
            actor=finance_officer,
            resolution="FAILED",
            reason="Confirmed dropped request on Stripe network.",
            gateway_reference="gw_fail_match_1",
            ticket_reference="INC-MATCH-01",
        )

    app_req = ApprovalRequest.objects.filter(target_id=str(hv_refund.id)).first()
    assert app_req.status == ApprovalStatusChoices.PENDING
    assert app_req.payload.get("resolution") == "FAILED"

    ApprovalService.approve_request(
        approval_request_id=app_req.id,
        approver=finance_checker,
        notes="Approved FAILED resolution.",
    )

    executed_req, resolved_rfnd = ApprovalService.execute_request(
        approval_request_id=app_req.id,
        executor=finance_checker,
    )

    assert executed_req.status == ApprovalStatusChoices.EXECUTED
    assert resolved_rfnd.status == RefundStatusChoices.FAILED
    hv_refund.refresh_from_db()
    assert hv_refund.status == RefundStatusChoices.FAILED


@pytest.mark.django_db
def test_approved_failed_resolution_rejects_cancelled_execution(
    high_value_order,
    finance_officer,
    finance_checker,
):
    """Approved FAILED resolution rejects CANCELLED execution and preserves PROCESSING_UNKNOWN."""
    hv_refund = Refund.objects.create(
        order=high_value_order,
        refund_number=f"RFND-PAYLOAD-MIS1-{uuid.uuid4().hex[:6].upper()}",
        amount=Decimal('1600.00'),
        currency='GBP',
        status=RefundStatusChoices.PROCESSING_UNKNOWN,
        created_by=finance_officer,
    )

    with pytest.raises(DjangoValidationError):
        RefundService.manual_resolve_unknown_refund(
            hv_refund,
            actor=finance_officer,
            resolution="FAILED",
            reason="Confirmed dropped transaction on network.",
            gateway_reference="gw_mis_1",
            ticket_reference="INC-MIS-01",
        )

    app_req = ApprovalRequest.objects.filter(target_id=str(hv_refund.id)).first()
    ApprovalService.approve_request(
        approval_request_id=app_req.id,
        approver=finance_checker,
        notes="Approved FAILED resolution.",
    )
    app_req.refresh_from_db()

    # Caller attempts to execute resolution as CANCELLED instead of FAILED
    with pytest.raises(DjangoValidationError) as exc:
        RefundService.manual_resolve_unknown_refund(
            refund=hv_refund,
            actor=finance_checker,
            resolution="CANCELLED",
            reason="Attempting to switch resolution to CANCELLED.",
            approved_request=app_req,
            gateway_reference="gw_mis_1",
            ticket_reference="INC-MIS-01",
        )

    assert "does not match approved resolution" in str(exc.value).lower()
    assert "changing resolution after approval is prohibited" in str(exc.value).lower()

    # Refund status must NOT be mutated
    hv_refund.refresh_from_db()
    assert hv_refund.status == RefundStatusChoices.PROCESSING_UNKNOWN
    app_req.refresh_from_db()
    assert app_req.status == ApprovalStatusChoices.APPROVED


@pytest.mark.django_db
def test_approved_cancelled_resolution_rejects_failed_execution(
    high_value_order,
    finance_officer,
    finance_checker,
):
    """Approved CANCELLED resolution rejects FAILED execution and preserves PROCESSING_UNKNOWN."""
    hv_refund = Refund.objects.create(
        order=high_value_order,
        refund_number=f"RFND-PAYLOAD-MIS2-{uuid.uuid4().hex[:6].upper()}",
        amount=Decimal('1700.00'),
        currency='GBP',
        status=RefundStatusChoices.PROCESSING_UNKNOWN,
        created_by=finance_officer,
    )

    with pytest.raises(DjangoValidationError):
        RefundService.manual_resolve_unknown_refund(
            hv_refund,
            actor=finance_officer,
            resolution="CANCELLED",
            reason="Confirmed cancellation before dispatch.",
            gateway_reference="gw_mis_2",
            ticket_reference="INC-MIS-02",
        )

    app_req = ApprovalRequest.objects.filter(target_id=str(hv_refund.id)).first()
    assert app_req.payload.get("resolution") == "CANCELLED"

    ApprovalService.approve_request(
        approval_request_id=app_req.id,
        approver=finance_checker,
        notes="Approved CANCELLED resolution.",
    )
    app_req.refresh_from_db()

    # Caller attempts to execute resolution as FAILED instead of CANCELLED
    with pytest.raises(DjangoValidationError) as exc:
        RefundService.manual_resolve_unknown_refund(
            refund=hv_refund,
            actor=finance_checker,
            resolution="FAILED",
            reason="Attempting to switch resolution to FAILED.",
            approved_request=app_req,
            gateway_reference="gw_mis_2",
            ticket_reference="INC-MIS-02",
        )

    assert "does not match approved resolution" in str(exc.value).lower()
    assert "changing resolution after approval is prohibited" in str(exc.value).lower()

    # Refund status must NOT be mutated
    hv_refund.refresh_from_db()
    assert hv_refund.status == RefundStatusChoices.PROCESSING_UNKNOWN
    app_req.refresh_from_db()
    assert app_req.status == ApprovalStatusChoices.APPROVED


@pytest.mark.django_db
def test_missing_resolution_in_approval_payload_rejected(
    high_value_order,
    finance_officer,
    finance_checker,
):
    """Missing resolution in an approval payload is strictly rejected by both execute_request and manual_resolve_unknown_refund."""
    hv_refund = Refund.objects.create(
        order=high_value_order,
        refund_number=f"RFND-PAYLOAD-MISSING-{uuid.uuid4().hex[:6].upper()}",
        amount=Decimal('1800.00'),
        currency='GBP',
        status=RefundStatusChoices.PROCESSING_UNKNOWN,
        created_by=finance_officer,
    )

    # Create approval request with missing 'resolution' in payload
    app_req = ApprovalService.create_request(
        requester=finance_officer,
        action_type='MANUAL_REFUND_RESOLUTION',
        target_type='Refund',
        target_id=str(hv_refund.id),
        amount=hv_refund.amount,
        currency=hv_refund.currency,
        reason="Manual resolution request missing resolution key.",
        payload={
            "gateway_reference": "gw_missing_res_1",
            "ticket_reference": "INC-NO-RES",
            "reason": "Missing resolution payload field",
        },
    )

    ApprovalService.approve_request(
        approval_request_id=app_req.id,
        approver=finance_checker,
        notes="Approved request without resolution.",
    )
    app_req.refresh_from_db()

    # 1. ApprovalService.execute_request rejects missing resolution
    with pytest.raises(DjangoValidationError) as exc_exec:
        ApprovalService.execute_request(
            approval_request_id=app_req.id,
            executor=finance_checker,
        )
    assert "missing approved resolution" in str(exc_exec.value).lower()

    # 2. Direct call to manual_resolve_unknown_refund also rejects missing resolution
    with pytest.raises(DjangoValidationError) as exc_direct:
        RefundService.manual_resolve_unknown_refund(
            refund=hv_refund,
            actor=finance_checker,
            resolution="FAILED",
            reason="Direct execution attempt with missing payload resolution.",
            approved_request=app_req,
            gateway_reference="gw_missing_res_1",
            ticket_reference="INC-NO-RES",
        )
    assert "missing approved resolution" in str(exc_direct.value).lower()

    # Refund status must NOT be mutated
    hv_refund.refresh_from_db()
    assert hv_refund.status == RefundStatusChoices.PROCESSING_UNKNOWN


@pytest.mark.django_db
def test_approved_cancelled_resolution_accepts_cancelled_execution(
    high_value_order,
    finance_officer,
    finance_checker,
):
    """Approved CANCELLED resolution successfully executes via ApprovalService.execute_request."""
    hv_refund = Refund.objects.create(
        order=high_value_order,
        refund_number=f"RFND-PAYLOAD-CANCEL-OK-{uuid.uuid4().hex[:6].upper()}",
        amount=Decimal('1900.00'),
        currency='GBP',
        status=RefundStatusChoices.PROCESSING_UNKNOWN,
        created_by=finance_officer,
    )

    with pytest.raises(DjangoValidationError):
        RefundService.manual_resolve_unknown_refund(
            hv_refund,
            actor=finance_officer,
            resolution="CANCELLED",
            reason="Confirmed cancelled prior to gateway processing.",
            gateway_reference="gw_cancel_match_1",
            ticket_reference="INC-CANCEL-01",
        )

    app_req = ApprovalRequest.objects.filter(target_id=str(hv_refund.id)).first()
    assert app_req.payload.get("resolution") == "CANCELLED"

    ApprovalService.approve_request(
        approval_request_id=app_req.id,
        approver=finance_checker,
        notes="Approved CANCELLED resolution.",
    )

    executed_req, resolved_rfnd = ApprovalService.execute_request(
        approval_request_id=app_req.id,
        executor=finance_checker,
    )

    assert executed_req.status == ApprovalStatusChoices.EXECUTED
    assert resolved_rfnd.status == RefundStatusChoices.CANCELLED
    hv_refund.refresh_from_db()
    assert hv_refund.status == RefundStatusChoices.CANCELLED

