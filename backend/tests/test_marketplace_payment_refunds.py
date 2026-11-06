import uuid
import json
from decimal import Decimal
import pytest
from django.utils import timezone
from django.conf import settings
from rest_framework import status
from rest_framework.test import APIClient
from django.core.exceptions import ValidationError as DjangoValidationError

from apps.identity.models import User, RoleChoices
from apps.marketplace.models import (
    Order,
    OrderStatusChoices,
    PaymentMethodChoices,
    PaymentStatusChoices,
    PaymentTransaction,
    PaymentWebhookEvent,
    Refund,
    RefundStatusChoices,
    RefundMethodChoices,
)
from apps.marketplace.payments.razorpay_provider import RazorpayPaymentProvider
from apps.marketplace.payments.stripe_provider import StripePaymentProvider
from apps.marketplace.payments.service import PaymentService
from apps.marketplace.returns.service import RefundService


@pytest.fixture
def buyer_user(db):
    user = User.objects.create_user(
        email='refund_buyer@driverxtra.com',
        password='SecurePassword123!',
        first_name='Alice',
        last_name='Buyer',
        phone_number='+919876543210',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.fixture
def buyer_client(buyer_user):
    client = APIClient()
    client.force_authenticate(user=buyer_user)
    return client


@pytest.fixture
def admin_user(db):
    user = User.objects.create_user(
        email='refund_admin@driverxtra.com',
        password='SecurePassword123!',
        first_name='Admin',
        last_name='Ops',
        is_staff=True,
        is_superuser=True,
        is_email_verified=True,
    )
    user.add_role(RoleChoices.ADMIN)
    return user


@pytest.fixture
def admin_client(admin_user):
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


@pytest.fixture
def unauthorized_user(db):
    user = User.objects.create_user(
        email='unauth_user@driverxtra.com',
        password='SecurePassword123!',
        first_name='Bob',
        last_name='Guest',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.fixture
def unauthorized_client(unauthorized_user):
    client = APIClient()
    client.force_authenticate(user=unauthorized_user)
    return client


@pytest.fixture
def inr_paid_order(db, buyer_user):
    order = Order.objects.create(
        order_number=f"ORD-INR-{uuid.uuid4().hex[:6].upper()}",
        buyer=buyer_user,
        subtotal_taxable_amount=Decimal('1500.00'),
        cgst_amount=Decimal('0.00'),
        sgst_amount=Decimal('0.00'),
        igst_amount=Decimal('0.00'),
        total_tax_amount=Decimal('0.00'),
        total_amount=Decimal('1500.00'),
        currency='INR',
        shipping_country='IN',
        shipping_name='Alice Buyer',
        shipping_address_line1='123 Main Road',
        shipping_city='Bangalore',
        shipping_state='KA',
        shipping_postal_code='560001',
        status=OrderStatusChoices.CONFIRMED,
        payment_method=PaymentMethodChoices.ONLINE,
        payment_status=PaymentStatusChoices.PAID,
        payment_reference='pay_test_inr_123456',
        paid_at=timezone.now(),
    )
    PaymentTransaction.objects.create(
        order=order,
        transaction_type=PaymentTransaction.TransactionTypeChoices.PAYMENT,
        provider='RAZORPAY',
        amount=order.total_amount,
        currency='INR',
        status=PaymentTransaction.StatusChoices.SUCCESS,
        provider_transaction_id='pay_test_inr_123456',
        provider_order_id='order_rzp_mock_123',
    )
    return order


@pytest.fixture
def gbp_paid_order(db, buyer_user):
    order = Order.objects.create(
        order_number=f"ORD-GBP-{uuid.uuid4().hex[:6].upper()}",
        buyer=buyer_user,
        subtotal_taxable_amount=Decimal('250.00'),
        total_tax_amount=Decimal('0.00'),
        total_amount=Decimal('250.00'),
        currency='GBP',
        shipping_country='GB',
        shipping_name='Alice UK',
        shipping_address_line1='45 London Road',
        shipping_city='London',
        shipping_postal_code='SW1A 1AA',
        status=OrderStatusChoices.CONFIRMED,
        payment_method=PaymentMethodChoices.ONLINE,
        payment_status=PaymentStatusChoices.PAID,
        payment_reference='pi_test_gbp_789012',
        paid_at=timezone.now(),
    )
    PaymentTransaction.objects.create(
        order=order,
        transaction_type=PaymentTransaction.TransactionTypeChoices.PAYMENT,
        provider='STRIPE',
        amount=order.total_amount,
        currency='GBP',
        status=PaymentTransaction.StatusChoices.SUCCESS,
        provider_transaction_id='pi_test_gbp_789012',
        provider_order_id='pi_test_gbp_789012',
    )
    return order


# =============================================================================
# 1. Direct Payment Provider Unit Tests
# =============================================================================

@pytest.mark.django_db
def test_razorpay_provider_issue_refund():
    provider = RazorpayPaymentProvider()
    assert provider.test_mode is True

    # Valid INR refund
    success, ref_id, extra = provider.issue_refund(
        payment_reference='pay_mock_123',
        amount=Decimal('500.00'),
        currency='INR',
        reason='Customer requested cancellation',
        refund_number='REF-20261104-001',
    )
    assert success is True
    assert ref_id.startswith('rfnd_test_')
    assert extra.get('amount') == 50000
    assert extra.get('currency') == 'INR'
    assert extra.get('status') == 'processed'

    # Currency mismatch
    success, err_msg, _ = provider.issue_refund(
        payment_reference='pay_mock_123',
        amount=Decimal('500.00'),
        currency='GBP',
    )
    assert success is False
    assert "only supports INR" in err_msg


@pytest.mark.django_db
def test_stripe_provider_issue_refund():
    provider = StripePaymentProvider()
    assert provider.test_mode is True

    # Valid GBP refund
    success, ref_id, extra = provider.issue_refund(
        payment_reference='pi_mock_456',
        amount=Decimal('75.50'),
        currency='GBP',
        reason='Defective product returned',
        refund_number='REF-20261104-002',
    )
    assert success is True
    assert ref_id.startswith('re_test_')
    assert extra.get('amount') == 7550
    assert extra.get('currency') == 'gbp'
    assert extra.get('status') == 'succeeded'

    # Currency mismatch
    success, err_msg, _ = provider.issue_refund(
        payment_reference='pi_mock_456',
        amount=Decimal('75.50'),
        currency='INR',
    )
    assert success is False
    assert "only supports GBP" in err_msg


# =============================================================================
# 2. Refund Service & Gateway Dispatch Tests
# =============================================================================

@pytest.mark.django_db
def test_full_refund_dispatch_razorpay(inr_paid_order, admin_user):
    refund = RefundService.create_refund(
        order=inr_paid_order,
        amount=Decimal('1500.00'),
        reason='Buyer cancelled order before dispatch',
        actor=admin_user,
        auto_process=True,
    )
    assert refund.status == RefundStatusChoices.SUCCEEDED
    assert refund.gateway_refund_id.startswith('rfnd_test_')
    assert refund.processed_at is not None

    inr_paid_order.refresh_from_db()
    assert inr_paid_order.payment_status == PaymentStatusChoices.REFUNDED

    # Immutable ledger check
    refund_tx = PaymentTransaction.objects.filter(
        order=inr_paid_order,
        transaction_type=PaymentTransaction.TransactionTypeChoices.REFUND,
        status=PaymentTransaction.StatusChoices.SUCCESS,
    ).first()
    assert refund_tx is not None
    assert refund_tx.amount == Decimal('1500.00')
    assert refund_tx.provider == 'RAZORPAY'


@pytest.mark.django_db
def test_partial_refund_dispatch_razorpay(inr_paid_order, admin_user):
    # First partial refund: ₹600 of ₹1500
    ref1 = RefundService.create_refund(
        order=inr_paid_order,
        amount=Decimal('600.00'),
        reason='Partial refund for out-of-stock item',
        actor=admin_user,
        auto_process=True,
    )
    assert ref1.status == RefundStatusChoices.SUCCEEDED
    inr_paid_order.refresh_from_db()
    assert inr_paid_order.payment_status == PaymentStatusChoices.PAID  # Still PAID, not fully refunded

    summary = RefundService.get_order_refund_summary(inr_paid_order)
    assert summary['paid_amount'] == Decimal('1500.00')
    assert summary['total_refunded'] == Decimal('600.00')
    assert summary['available_refundable'] == Decimal('900.00')
    assert summary['can_refund'] is True

    # Second partial refund: remaining ₹900
    ref2 = RefundService.create_refund(
        order=inr_paid_order,
        amount=Decimal('900.00'),
        reason='Remaining balance refunded',
        actor=admin_user,
        auto_process=True,
    )
    assert ref2.status == RefundStatusChoices.SUCCEEDED
    inr_paid_order.refresh_from_db()
    assert inr_paid_order.payment_status == PaymentStatusChoices.REFUNDED

    summary_final = RefundService.get_order_refund_summary(inr_paid_order)
    assert summary_final['available_refundable'] == Decimal('0.00')
    assert summary_final['can_refund'] is False


@pytest.mark.django_db
def test_stripe_gbp_refund_dispatch(gbp_paid_order, admin_user):
    refund = RefundService.create_refund(
        order=gbp_paid_order,
        amount=Decimal('250.00'),
        reason='Full return accepted in UK warehouse',
        actor=admin_user,
        auto_process=True,
    )
    assert refund.status == RefundStatusChoices.SUCCEEDED
    assert refund.gateway_refund_id.startswith('re_test_')
    assert refund.currency == 'GBP'

    gbp_paid_order.refresh_from_db()
    assert gbp_paid_order.payment_status == PaymentStatusChoices.REFUNDED


@pytest.mark.django_db
def test_insufficient_refundable_balance_rejected(inr_paid_order, admin_user):
    with pytest.raises(DjangoValidationError) as exc:
        RefundService.create_refund(
            order=inr_paid_order,
            amount=Decimal('1500.01'),
            reason='Over-refunding',
            actor=admin_user,
        )
    assert "exceeds maximum available refundable balance" in str(exc.value)


@pytest.mark.django_db
def test_unpaid_order_refund_rejected(db, buyer_user, admin_user):
    unpaid_order = Order.objects.create(
        order_number=f"ORD-UNPAID-{uuid.uuid4().hex[:6].upper()}",
        buyer=buyer_user,
        subtotal_taxable_amount=Decimal('800.00'),
        cgst_amount=Decimal('0.00'),
        sgst_amount=Decimal('0.00'),
        igst_amount=Decimal('0.00'),
        total_tax_amount=Decimal('0.00'),
        total_amount=Decimal('800.00'),
        currency='INR',
        shipping_country='IN',
        status=OrderStatusChoices.PENDING_CONFIRMATION,
        payment_status=PaymentStatusChoices.PENDING,
    )
    with pytest.raises(DjangoValidationError) as exc:
        RefundService.create_refund(
            order=unpaid_order,
            amount=Decimal('800.00'),
            reason='Cannot refund unpaid order',
            actor=admin_user,
        )
    assert "Order must be PAID" in str(exc.value)


@pytest.mark.django_db
def test_permission_enforcement(inr_paid_order, unauthorized_user):
    with pytest.raises(DjangoValidationError) as exc:
        RefundService.create_refund(
            order=inr_paid_order,
            amount=Decimal('100.00'),
            reason='Unauthorized buyer cannot issue refund directly',
            actor=unauthorized_user,
        )
    assert "Permission denied" in str(exc.value)


@pytest.mark.django_db
def test_admin_approval_workflow(inr_paid_order, admin_user):
    # Create pending refund
    refund = RefundService.create_refund(
        order=inr_paid_order,
        amount=Decimal('500.00'),
        reason='Pending operations review',
        actor=admin_user,
        auto_process=False,
    )
    assert refund.status == RefundStatusChoices.PENDING
    assert refund.gateway_refund_id == ''

    # Approve and dispatch
    approved = RefundService.approve_refund(
        refund=refund,
        actor=admin_user,
        notes='Approved by finance manager',
    )
    assert approved.status == RefundStatusChoices.SUCCEEDED
    assert approved.gateway_refund_id.startswith('rfnd_test_')
    assert approved.approved_by == admin_user
    assert '[Approved]: Approved by finance manager' in approved.notes


@pytest.mark.django_db
def test_admin_rejection_workflow(inr_paid_order, admin_user):
    refund = RefundService.create_refund(
        order=inr_paid_order,
        amount=Decimal('300.00'),
        reason='Customer requested claim',
        actor=admin_user,
        auto_process=False,
    )
    assert refund.status == RefundStatusChoices.PENDING

    rejected = RefundService.reject_refund(
        refund=refund,
        actor=admin_user,
        reason='Items were installed and damaged by buyer',
    )
    assert rejected.status == RefundStatusChoices.CANCELLED
    assert rejected.failure_reason == 'Items were installed and damaged by buyer'
    assert rejected.approved_by == admin_user


@pytest.mark.django_db
def test_gateway_failure_handling(inr_paid_order, admin_user, monkeypatch):
    provider = PaymentService.get_provider_for_order(inr_paid_order)

    # Simulate gateway rejection
    def mock_issue_refund(*args, **kwargs):
        return False, "Gateway declined refund: insufficient merchant account balance", {}

    monkeypatch.setattr(provider, 'issue_refund', mock_issue_refund)
    monkeypatch.setattr(PaymentService, 'get_provider_for_order', lambda o: provider)

    refund = RefundService.create_refund(
        order=inr_paid_order,
        amount=Decimal('400.00'),
        reason='Attempting refund with failing gateway',
        actor=admin_user,
        auto_process=False,
    )

    with pytest.raises(DjangoValidationError) as exc:
        RefundService.dispatch_gateway_refund(refund, admin_user)

    assert "Payment gateway refund failed" in str(exc.value)

    refund.refresh_from_db()
    assert refund.status == RefundStatusChoices.FAILED
    assert "insufficient merchant account balance" in refund.failure_reason

    # Ledger record
    failed_tx = PaymentTransaction.objects.filter(
        order=inr_paid_order,
        transaction_type=PaymentTransaction.TransactionTypeChoices.REFUND,
        status=PaymentTransaction.StatusChoices.FAILED,
    ).first()
    assert failed_tx is not None
    assert "insufficient merchant account balance" in failed_tx.error_message


@pytest.mark.django_db
def test_idempotent_duplicate_dispatch(inr_paid_order, admin_user):
    refund = RefundService.create_refund(
        order=inr_paid_order,
        amount=Decimal('1500.00'),
        reason='Full refund',
        actor=admin_user,
        auto_process=True,
    )
    assert refund.status == RefundStatusChoices.SUCCEEDED
    first_gateway_id = refund.gateway_refund_id

    # Second dispatch call should be a no-op
    second_call = RefundService.dispatch_gateway_refund(refund, admin_user)
    assert second_call.status == RefundStatusChoices.SUCCEEDED
    assert second_call.gateway_refund_id == first_gateway_id

    # Transactions count should remain 1
    tx_count = PaymentTransaction.objects.filter(
        order=inr_paid_order,
        transaction_type=PaymentTransaction.TransactionTypeChoices.REFUND,
    ).count()
    assert tx_count == 1


# =============================================================================
# 3. Webhook Integration Tests
# =============================================================================

@pytest.mark.django_db
def test_webhook_razorpay_refund_processed(inr_paid_order, admin_user, client):
    # Pending refund awaiting webhook settlement
    refund = RefundService.create_refund(
        order=inr_paid_order,
        amount=Decimal('1500.00'),
        reason='Return processed',
        actor=admin_user,
        auto_process=False,
    )
    assert refund.status == RefundStatusChoices.PENDING

    payload = {
        "entity": "event",
        "account_id": "acc_mock_123",
        "event": "refund.processed",
        "contains": ["refund"],
        "payload": {
            "refund": {
                "entity": {
                    "id": "rfnd_webhook_12345",
                    "amount": 150000,
                    "currency": "INR",
                    "payment_id": "pay_test_inr_123456",
                    "notes": {
                        "order_number": inr_paid_order.order_number,
                        "refund_number": refund.refund_number,
                    },
                    "status": "processed",
                }
            }
        }
    }
    body_bytes = json.dumps(payload).encode('utf-8')

    response = client.post(
        '/api/v1/marketplace/payments/webhook/razorpay/',
        data=body_bytes,
        content_type='application/json',
        HTTP_X_RAZORPAY_SIGNATURE='test_webhook_sig_valid',
    )
    assert response.status_code == status.HTTP_200_OK

    refund.refresh_from_db()
    assert refund.status == RefundStatusChoices.SUCCEEDED
    assert refund.gateway_refund_id == 'rfnd_webhook_12345'

    inr_paid_order.refresh_from_db()
    assert inr_paid_order.payment_status == PaymentStatusChoices.REFUNDED


@pytest.mark.django_db
def test_webhook_replay_defense(inr_paid_order, client):
    payload = {
        "entity": "event",
        "event_id": "evt_replay_test_999",
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_replay_test",
                    "amount": 150000,
                    "currency": "INR",
                    "order_id": "order_rzp_mock_123",
                    "notes": {"order_number": inr_paid_order.order_number},
                    "status": "captured",
                }
            }
        }
    }
    body_bytes = json.dumps(payload).encode('utf-8')

    # First call
    resp1 = client.post(
        '/api/v1/marketplace/payments/webhook/razorpay/',
        data=body_bytes,
        content_type='application/json',
        HTTP_X_RAZORPAY_SIGNATURE='test_webhook_sig_valid',
    )
    assert resp1.status_code == status.HTTP_200_OK

    # Replay call
    resp2 = client.post(
        '/api/v1/marketplace/payments/webhook/razorpay/',
        data=body_bytes,
        content_type='application/json',
        HTTP_X_RAZORPAY_SIGNATURE='test_webhook_sig_valid',
    )
    assert resp2.status_code == status.HTTP_200_OK
    assert resp2.data.get('replayed') is True


# =============================================================================
# 4. API Endpoints Tests
# =============================================================================

@pytest.mark.django_db
def test_api_order_refund_summary(inr_paid_order, buyer_client):
    resp = buyer_client.get(f"/api/v1/marketplace/orders/{inr_paid_order.order_number}/refund-summary/")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.data
    assert data['order_number'] == inr_paid_order.order_number
    assert data['currency'] == 'INR'
    assert Decimal(str(data['available_refundable'])) == Decimal('1500.00')
    assert data['can_refund'] is True
    assert 'refunds' in data


@pytest.mark.django_db
def test_api_admin_order_refund_create(inr_paid_order, admin_client):
    payload = {
        "amount": "500.00",
        "reason": "Return accepted via customer service",
        "refund_method": "ORIGINAL_PAYMENT",
        "auto_process": True,
    }
    resp = admin_client.post(
        f"/api/v1/marketplace/admin/orders/{inr_paid_order.order_number}/refund/",
        data=payload,
        format='json',
    )
    assert resp.status_code == status.HTTP_201_CREATED
    assert resp.data['refund']['status'] == RefundStatusChoices.SUCCEEDED
    assert resp.data['refund']['gateway_refund_id'].startswith('rfnd_test_')


@pytest.mark.django_db
def test_api_admin_refund_approve(inr_paid_order, admin_user, admin_client):
    refund = RefundService.create_refund(
        order=inr_paid_order,
        amount=Decimal('400.00'),
        reason='Awaiting admin click to approve',
        actor=admin_user,
        auto_process=False,
    )
    assert refund.status == RefundStatusChoices.PENDING

    resp = admin_client.post(
        f"/api/v1/marketplace/admin/refunds/{refund.refund_number}/approve/",
        data={"notes": "Approved via admin console"},
        format='json',
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data['refund']['status'] == RefundStatusChoices.SUCCEEDED
    assert resp.data['refund']['gateway_refund_id'].startswith('rfnd_test_')


@pytest.mark.django_db
def test_api_admin_refund_reject(inr_paid_order, admin_user, admin_client):
    refund = RefundService.create_refund(
        order=inr_paid_order,
        amount=Decimal('400.00'),
        reason='Suspicious claim',
        actor=admin_user,
        auto_process=False,
    )
    assert refund.status == RefundStatusChoices.PENDING

    resp = admin_client.post(
        f"/api/v1/marketplace/admin/refunds/{refund.refund_number}/reject/",
        data={"reason": "Dispute rejected - part was tampered with"},
        format='json',
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data['refund']['status'] == RefundStatusChoices.CANCELLED
    assert resp.data['refund']['failure_reason'] == "Dispute rejected - part was tampered with"


@pytest.mark.django_db
def test_api_buyer_refunds_list(inr_paid_order, buyer_user, admin_user, buyer_client):
    ref = RefundService.create_refund(
        order=inr_paid_order,
        amount=Decimal('200.00'),
        reason='Small partial refund',
        actor=admin_user,
        auto_process=True,
    )
    resp = buyer_client.get("/api/v1/marketplace/buyer/refunds/")
    assert resp.status_code == status.HTTP_200_OK
    results = resp.data if isinstance(resp.data, list) else resp.data.get('results', [])
    assert any(r['refund_number'] == ref.refund_number for r in results)
