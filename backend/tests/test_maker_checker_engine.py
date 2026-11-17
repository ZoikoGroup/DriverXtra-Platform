"""Comprehensive test suite for Phase 2: Maker-Checker Approval Engine.

Verifies:
1. Dual-authorization lifecycle (PENDING, APPROVED, REJECTED, CANCELLED, EXECUTED).
2. Maker cannot approve or review own request (ValueError / 400 Bad Request).
3. Checker must hold required permission ('finance.payout' or Platform Administrator).
4. Checker lacking permission receives 403 Forbidden.
5. Rejected/cancelled requests cannot be executed.
6. Already approved requests cannot be re-approved.
7. Duplicate gateway execution is prevented.
8. Baseline threshold rules (£500.00 GBP and ₹50,000.00 INR) with boundary checks.
9. Integration with RefundService: high-value refunds require approval prior to gateway dispatch.
10. Low-value refunds (< threshold) dispatch directly without dual-authorization.
11. Non-staff (e.g. buyers) receive 403 Forbidden on all approval endpoints.
12. Audit logging trails for all approval lifecycle transitions.
"""

import uuid
from decimal import Decimal
from unittest.mock import patch

import pyotp
import pytest
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
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
    Refund,
    RefundMethodChoices,
    RefundStatusChoices,
)
from apps.marketplace.returns.service import RefundService
from platform_core.audit.models import AuditLog


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
def finance_officer_maker(make_staff):
    return make_staff('finance.maker@driverxtra.com', 'FINANCE_OFFICER', 'Alice', 'Maker')


@pytest.fixture
def finance_officer_checker(make_staff):
    return make_staff('finance.checker@driverxtra.com', 'FINANCE_OFFICER', 'Bob', 'Checker')


@pytest.fixture
def verification_officer(make_staff):
    return make_staff('verif.officer@driverxtra.com', 'VERIFICATION_OFFICER', 'Victor', 'Officer')


@pytest.fixture
def support_agent(make_staff):
    return make_staff('support.agent@driverxtra.com', 'SUPPORT_AGENT', 'Sam', 'Agent')


@pytest.fixture
def high_value_order(db, buyer_user):
    order = Order.objects.create(
        buyer=buyer_user,
        order_number=f"ORD-HV-{uuid.uuid4().hex[:6].upper()}",
        total_amount=Decimal('1200.00'),
        subtotal_taxable_amount=Decimal('1000.00'),
        total_tax_amount=Decimal('200.00'),
        currency='GBP',
        shipping_country='GB',
        payment_status=PaymentStatusChoices.PAID,
        payment_reference='pi_test_high_value_123',
    )
    OrderItem.objects.create(
        order=order,
        title='Engine Assembly',
        unit_price=Decimal('1000.00'),
        quantity=1,
        taxable_amount=Decimal('1000.00'),
        tax_amount=Decimal('200.00'),
        total_amount=Decimal('1200.00'),
    )
    return order


@pytest.fixture
def high_value_refund(db, high_value_order, finance_officer_maker):
    return Refund.objects.create(
        order=high_value_order,
        refund_number=f"RFND-HV-{uuid.uuid4().hex[:6].upper()}",
        amount=Decimal('750.00'),
        currency='GBP',
        refund_method=RefundMethodChoices.ORIGINAL_PAYMENT,
        status=RefundStatusChoices.PENDING,
        created_by=finance_officer_maker,
    )


@pytest.fixture
def low_value_refund(db, high_value_order, finance_officer_maker):
    return Refund.objects.create(
        order=high_value_order,
        refund_number=f"RFND-LV-{uuid.uuid4().hex[:6].upper()}",
        amount=Decimal('350.00'),
        currency='GBP',
        refund_method=RefundMethodChoices.ORIGINAL_PAYMENT,
        status=RefundStatusChoices.PENDING,
        created_by=finance_officer_maker,
    )


# =============================================================================
# 1. Dual-Authorization Threshold Tests
# =============================================================================

@pytest.mark.django_db
def test_threshold_rules_gbp_boundary():
    """Baseline GBP threshold is £500.00."""
    assert ApprovalService.is_approval_required('REFUND_DISPATCH', Decimal('500.00'), 'GBP') is False
    assert ApprovalService.is_approval_required('REFUND_DISPATCH', Decimal('499.99'), 'GBP') is False
    assert ApprovalService.is_approval_required('REFUND_DISPATCH', Decimal('500.01'), 'GBP') is True
    assert ApprovalService.is_approval_required('REFUND_DISPATCH', Decimal('1500.00'), 'GBP') is True


@pytest.mark.django_db
def test_threshold_rules_inr_boundary():
    """Baseline INR threshold is ₹50,000.00."""
    assert ApprovalService.is_approval_required('REFUND_DISPATCH', Decimal('50000.00'), 'INR') is False
    assert ApprovalService.is_approval_required('REFUND_DISPATCH', Decimal('49999.00'), 'INR') is False
    assert ApprovalService.is_approval_required('REFUND_DISPATCH', Decimal('50000.01'), 'INR') is True
    assert ApprovalService.is_approval_required('REFUND_DISPATCH', Decimal('75000.00'), 'INR') is True


# =============================================================================
# 2. Maker Cannot Approve Own Request (Maker-Checker Rule 1)
# =============================================================================

@pytest.mark.django_db
def test_maker_cannot_approve_own_request_service(finance_officer_maker):
    """Service layer strictly prevents requester from approving their own request."""
    req = ApprovalService.create_request(
        requester=finance_officer_maker,
        action_type='REFUND_DISPATCH',
        target_type='Refund',
        target_id='test-uuid-123',
        amount=Decimal('800.00'),
        currency='GBP',
        reason='Test high-value refund',
    )
    assert req.status == ApprovalStatusChoices.PENDING

    with pytest.raises(DjangoValidationError) as exc:
        ApprovalService.approve_request(
            approval_request_id=req.id,
            approver=finance_officer_maker,
            notes='Self-approval attempt',
        )
    assert "maker-checker violation" in str(exc.value).lower()

    req.refresh_from_db()
    assert req.status == ApprovalStatusChoices.PENDING
    assert req.approver is None


@pytest.mark.django_db
def test_maker_cannot_approve_own_request_api(finance_officer_maker):
    """API endpoint returns 400 Bad Request when maker attempts to approve own request."""
    req = ApprovalService.create_request(
        requester=finance_officer_maker,
        action_type='REFUND_DISPATCH',
        target_type='Refund',
        target_id='test-uuid-456',
        amount=Decimal('800.00'),
        currency='GBP',
    )
    client = APIClient()
    client.force_authenticate(user=finance_officer_maker)

    response = client.post(f"/api/v1/admin/approvals/{req.id}/approve/", {"notes": "Self approval"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "maker-checker violation" in response.data.get("error", "").lower()


# =============================================================================
# 3. Independent Checker Can Approve / Reject
# =============================================================================

@pytest.mark.django_db
def test_independent_checker_with_finance_payout_can_approve(finance_officer_maker, finance_officer_checker):
    """Authorized independent finance checker successfully approves pending request."""
    req = ApprovalService.create_request(
        requester=finance_officer_maker,
        action_type='REFUND_DISPATCH',
        target_type='Refund',
        target_id='test-uuid-789',
        amount=Decimal('900.00'),
        currency='GBP',
    )
    client = APIClient()
    client.force_authenticate(user=finance_officer_checker)

    response = client.post(f"/api/v1/admin/approvals/{req.id}/approve/", {"notes": "Approved by Bob"})
    assert response.status_code == status.HTTP_200_OK
    assert response.data["status"] == "success"

    req.refresh_from_db()
    assert req.status == ApprovalStatusChoices.APPROVED
    assert req.approver == finance_officer_checker
    assert req.reviewed_at is not None
    assert req.notes == "Approved by Bob"


@pytest.mark.django_db
def test_checker_without_finance_payout_cannot_approve(finance_officer_maker, verification_officer, support_agent):
    """Staff members lacking 'finance.payout' are denied approval authority (403 Forbidden)."""
    req = ApprovalService.create_request(
        requester=finance_officer_maker,
        action_type='REFUND_DISPATCH',
        target_type='Refund',
        target_id='test-uuid-999',
        amount=Decimal('900.00'),
        currency='GBP',
    )

    client = APIClient()

    # Verification Officer (lacks finance.payout)
    client.force_authenticate(user=verification_officer)
    resp_vo = client.post(f"/api/v1/admin/approvals/{req.id}/approve/", {"notes": "VO approve"})
    assert resp_vo.status_code == status.HTTP_403_FORBIDDEN

    # Support Agent (lacks finance.payout)
    client.force_authenticate(user=support_agent)
    resp_sa = client.post(f"/api/v1/admin/approvals/{req.id}/approve/", {"notes": "SA approve"})
    assert resp_sa.status_code == status.HTTP_403_FORBIDDEN

    req.refresh_from_db()
    assert req.status == ApprovalStatusChoices.PENDING


@pytest.mark.django_db
def test_platform_admin_can_approve_requests(finance_officer_maker, admin_user):
    """Platform superusers bypass checker permission checks to authorize requests."""
    req = ApprovalService.create_request(
        requester=finance_officer_maker,
        action_type='REFUND_DISPATCH',
        target_type='Refund',
        target_id='test-uuid-admin',
        amount=Decimal('1500.00'),
        currency='GBP',
    )
    client = APIClient()
    client.force_authenticate(user=admin_user)

    response = client.post(f"/api/v1/admin/approvals/{req.id}/approve/", {"notes": "Admin approval"})
    assert response.status_code == status.HTTP_200_OK

    req.refresh_from_db()
    assert req.status == ApprovalStatusChoices.APPROVED
    assert req.approver == admin_user


# =============================================================================
# 4. Lifecycle Invariants: No Re-Approval & Rejected Cannot Execute
# =============================================================================

@pytest.mark.django_db
def test_cannot_reapprove_already_approved_request(finance_officer_maker, finance_officer_checker, admin_user):
    """Already approved request cannot be approved again."""
    req = ApprovalService.create_request(
        requester=finance_officer_maker,
        action_type='REFUND_DISPATCH',
        target_type='Refund',
        target_id='test-uuid-reapprove',
        amount=Decimal('700.00'),
        currency='GBP',
    )
    ApprovalService.approve_request(req.id, approver=finance_officer_checker)
    req.refresh_from_db()
    assert req.status == ApprovalStatusChoices.APPROVED

    with pytest.raises(DjangoValidationError) as exc:
        ApprovalService.approve_request(req.id, approver=admin_user)
    assert "cannot approve request with status 'approved'" in str(exc.value).lower()


@pytest.mark.django_db
def test_rejected_request_cannot_execute(finance_officer_maker, finance_officer_checker):
    """Rejected approval request cannot be executed."""
    req = ApprovalService.create_request(
        requester=finance_officer_maker,
        action_type='REFUND_DISPATCH',
        target_type='Refund',
        target_id='test-uuid-reject-exec',
        amount=Decimal('700.00'),
        currency='GBP',
    )
    ApprovalService.reject_request(
        req.id,
        approver=finance_officer_checker,
        reason="Suspicious high amount without customer receipts.",
    )
    req.refresh_from_db()
    assert req.status == ApprovalStatusChoices.REJECTED

    with pytest.raises(DjangoValidationError) as exc:
        ApprovalService.execute_request(req.id, executor=finance_officer_checker)
    assert "cannot execute a rejected approval request" in str(exc.value).lower()


@pytest.mark.django_db
def test_cancelled_request_cannot_execute(finance_officer_maker, finance_officer_checker):
    """Cancelled approval request cannot be executed."""
    req = ApprovalService.create_request(
        requester=finance_officer_maker,
        action_type='REFUND_DISPATCH',
        target_type='Refund',
        target_id='test-uuid-cancel-exec',
        amount=Decimal('700.00'),
        currency='GBP',
    )
    ApprovalService.cancel_request(req.id, actor=finance_officer_maker, notes="Mistake in refund amount")
    req.refresh_from_db()
    assert req.status == ApprovalStatusChoices.CANCELLED

    with pytest.raises(DjangoValidationError) as exc:
        ApprovalService.execute_request(req.id, executor=finance_officer_checker)
    assert "cannot execute a cancelled approval request" in str(exc.value).lower()


# =============================================================================
# 5. Financial Workflow Integration (RefundService & Gateway Dispatch)
# =============================================================================

@pytest.mark.django_db
def test_high_value_refund_blocks_gateway_dispatch_until_approved(
    high_value_refund,
    finance_officer_maker,
    finance_officer_checker,
):
    """A refund > £500 requires Maker-Checker dual authorization before gateway dispatch."""
    # Attempting direct dispatch by maker fails with validation error and creates pending ApprovalRequest
    with pytest.raises(DjangoValidationError) as exc:
        RefundService.dispatch_gateway_refund(
            refund=high_value_refund,
            actor=finance_officer_maker,
        )
    assert "maker-checker threshold" in str(exc.value).lower()

    # Pending ApprovalRequest was automatically created
    app_req = ApprovalRequest.objects.filter(
        target_type='Refund',
        target_id=str(high_value_refund.id),
        status=ApprovalStatusChoices.PENDING,
    ).first()
    assert app_req is not None
    assert app_req.amount == Decimal('750.00')
    assert app_req.requester == finance_officer_maker

    # Independent checker approves the request
    ApprovalService.approve_request(
        approval_request_id=app_req.id,
        approver=finance_officer_checker,
        notes="Authorized high-value engine refund",
    )
    app_req.refresh_from_db()
    assert app_req.status == ApprovalStatusChoices.APPROVED

    # Now execute request through ApprovalService or dispatch_gateway_refund
    with patch('apps.marketplace.payments.service.StripePaymentProvider.issue_refund') as mock_issue:
        mock_issue.return_value = (True, "re_test_mock_gateway_123", {"status": "succeeded"})

        dispatched = RefundService.dispatch_gateway_refund(
            refund=high_value_refund,
            actor=finance_officer_checker,
        )

        assert dispatched.status == RefundStatusChoices.SUCCEEDED
        assert dispatched.gateway_refund_id == "re_test_mock_gateway_123"

        app_req.refresh_from_db()
        assert app_req.status == ApprovalStatusChoices.EXECUTED
        assert app_req.executed_by == finance_officer_checker


@pytest.mark.django_db
def test_duplicate_gateway_execution_prevented(
    high_value_refund,
    finance_officer_maker,
    finance_officer_checker,
):
    """Executing an already executed approval request is blocked idempotently."""
    app_req = ApprovalService.create_request(
        requester=finance_officer_maker,
        action_type='REFUND_DISPATCH',
        target_type='Refund',
        target_id=str(high_value_refund.id),
        amount=Decimal('750.00'),
        currency='GBP',
    )
    ApprovalService.approve_request(app_req.id, approver=finance_officer_checker)

    with patch('apps.marketplace.payments.service.StripePaymentProvider.issue_refund') as mock_issue:
        mock_issue.return_value = (True, "re_test_duplicate_prevented", {})
        ApprovalService.execute_request(app_req.id, executor=finance_officer_checker)

    app_req.refresh_from_db()
    assert app_req.status == ApprovalStatusChoices.EXECUTED

    # Second execution attempt is rejected
    with pytest.raises(DjangoValidationError) as exc:
        ApprovalService.execute_request(app_req.id, executor=finance_officer_checker)
    assert "already been executed" in str(exc.value).lower()


@pytest.mark.django_db
def test_low_value_refund_dispatches_directly_without_maker_checker(
    low_value_refund,
    finance_officer_maker,
):
    """Refund <= £500 dispatches directly to gateway without requiring dual-authorization."""
    with patch('apps.marketplace.payments.service.StripePaymentProvider.issue_refund') as mock_issue:
        mock_issue.return_value = (True, "re_test_low_value_direct", {})

        dispatched = RefundService.dispatch_gateway_refund(
            refund=low_value_refund,
            actor=finance_officer_maker,
        )

        assert dispatched.status == RefundStatusChoices.SUCCEEDED
        # No ApprovalRequest was required or created
        assert not ApprovalRequest.objects.filter(target_id=str(low_value_refund.id)).exists()


# =============================================================================
# 6. Access Control: Non-Staff (Buyer) Denied Access
# =============================================================================

@pytest.mark.django_db
def test_non_staff_buyer_forbidden_on_all_approval_endpoints(buyer_user, finance_officer_maker):
    """Buyers and unauthorized users receive 403 Forbidden on all Maker-Checker endpoints."""
    req = ApprovalService.create_request(
        requester=finance_officer_maker,
        action_type='REFUND_DISPATCH',
        target_type='Refund',
        target_id='test-buyer-denied',
        amount=Decimal('600.00'),
    )

    client = APIClient()
    client.force_authenticate(user=buyer_user)

    assert client.get("/api/v1/admin/approvals/").status_code == status.HTTP_403_FORBIDDEN
    assert client.get(f"/api/v1/admin/approvals/{req.id}/").status_code == status.HTTP_403_FORBIDDEN
    assert client.post(f"/api/v1/admin/approvals/{req.id}/approve/").status_code == status.HTTP_403_FORBIDDEN
    assert client.post(f"/api/v1/admin/approvals/{req.id}/reject/").status_code == status.HTTP_403_FORBIDDEN
    assert client.post(f"/api/v1/admin/approvals/{req.id}/cancel/").status_code == status.HTTP_403_FORBIDDEN
    assert client.post(f"/api/v1/admin/approvals/{req.id}/execute/").status_code == status.HTTP_403_FORBIDDEN


# =============================================================================
# 7. Audit Logging Verification
# =============================================================================

@pytest.mark.django_db
def test_audit_logging_maker_checker_lifecycle(
    finance_officer_maker,
    finance_officer_checker,
    high_value_refund,
):
    """All approval actions record immutable audit entries with proper event types."""
    # 1. Create request
    req = ApprovalService.create_request(
        requester=finance_officer_maker,
        action_type='REFUND_DISPATCH',
        target_type='Refund',
        target_id=str(high_value_refund.id),
        amount=Decimal('750.00'),
        currency='GBP',
        reason='Audit test refund',
    )
    assert AuditLog.objects.filter(
        event_type="approval.request.created",
        resource_id=str(req.id),
        actor_id=finance_officer_maker.id,
    ).exists()

    # 2. Approve request
    ApprovalService.approve_request(
        approval_request_id=req.id,
        approver=finance_officer_checker,
        notes="Audit log verified",
    )
    assert AuditLog.objects.filter(
        event_type="approval.request.approved",
        resource_id=str(req.id),
        actor_id=finance_officer_checker.id,
    ).exists()

    # 3. Execute request
    with patch('apps.marketplace.payments.service.StripePaymentProvider.issue_refund') as mock_issue:
        mock_issue.return_value = (True, "re_audit_test_123", {})
        ApprovalService.execute_request(req.id, executor=finance_officer_checker)

    assert AuditLog.objects.filter(
        event_type="approval.request.execution.attempted",
        resource_id=str(req.id),
        actor_id=finance_officer_checker.id,
    ).exists()

    assert AuditLog.objects.filter(
        event_type="approval.request.execution.success",
        resource_id=str(req.id),
        actor_id=finance_officer_checker.id,
    ).exists()


# =============================================================================
# 8. Approval Integrity & Concurrent Execution Defense
# =============================================================================

@pytest.mark.django_db
def test_modified_refund_amount_invalidates_prior_approval(
    high_value_refund,
    finance_officer_maker,
    finance_officer_checker,
):
    """If refund amount is modified after approval, prior approval cannot be used to execute dispatch."""
    app_req = ApprovalService.create_request(
        requester=finance_officer_maker,
        action_type='REFUND_DISPATCH',
        target_type='Refund',
        target_id=str(high_value_refund.id),
        amount=high_value_refund.amount,
        currency='GBP',
    )
    app_req = ApprovalService.approve_request(app_req.id, approver=finance_officer_checker)

    # Tamper with refund amount after approval (e.g. changed from 750.00 to 950.00)
    high_value_refund.amount = Decimal('950.00')
    high_value_refund.save(update_fields=['amount'])

    with pytest.raises(DjangoValidationError) as exc:
        RefundService.dispatch_gateway_refund(
            refund=high_value_refund,
            actor=finance_officer_checker,
            approved_request=app_req,
        )
    assert "integrity violation" in str(exc.value).lower()
    assert "approved amount" in str(exc.value).lower()


@pytest.mark.django_db
def test_approved_request_cannot_be_reused_by_different_refund(
    high_value_refund,
    low_value_refund,
    finance_officer_maker,
    finance_officer_checker,
):
    """An approved request tied to Refund A cannot be hijacked or reused to dispatch Refund B."""
    app_req = ApprovalService.create_request(
        requester=finance_officer_maker,
        action_type='REFUND_DISPATCH',
        target_type='Refund',
        target_id=str(high_value_refund.id),
        amount=high_value_refund.amount,
        currency='GBP',
    )
    app_req = ApprovalService.approve_request(app_req.id, approver=finance_officer_checker)

    # Attempt to dispatch low_value_refund using high_value_refund's approval
    with pytest.raises(DjangoValidationError) as exc:
        RefundService.dispatch_gateway_refund(
            refund=low_value_refund,
            actor=finance_officer_checker,
            approved_request=app_req,
        )
    assert "integrity violation" in str(exc.value).lower()
    assert "target" in str(exc.value).lower()


@pytest.mark.django_db
def test_concurrent_execution_protection_blocks_duplicate_dispatch(
    low_value_refund,
    finance_officer_checker,
):
    """Refund currently in PROCESSING status cannot be concurrently dispatched by another worker."""
    low_value_refund.status = RefundStatusChoices.PROCESSING
    low_value_refund.save(update_fields=['status'])

    with pytest.raises(DjangoValidationError) as exc:
        RefundService.dispatch_gateway_refund(
            refund=low_value_refund,
            actor=finance_officer_checker,
        )
    assert "currently being processed" in str(exc.value).lower()


@pytest.mark.django_db
def test_action_target_mismatch_blocks_execution(
    high_value_refund,
    finance_officer_maker,
    finance_officer_checker,
):
    """Executing an approval with mismatched action_type or target_type is blocked."""
    app_req = ApprovalRequest.objects.create(
        requester=finance_officer_maker,
        action_type='UNKNOWN_ACTION',
        target_type='Refund',
        target_id=str(high_value_refund.id),
        amount=high_value_refund.amount,
        currency='GBP',
        status=ApprovalStatusChoices.APPROVED,
        approver=finance_officer_checker,
    )

    with pytest.raises(DjangoValidationError) as exc:
        ApprovalService.execute_request(app_req.id, executor=finance_officer_checker)
    assert "integrity violation" in str(exc.value).lower()


@pytest.mark.django_db
def test_modified_refund_currency_invalidates_prior_approval(
    high_value_refund,
    finance_officer_maker,
    finance_officer_checker,
):
    """If refund currency is altered after approval, execution is rejected."""
    app_req = ApprovalService.create_request(
        requester=finance_officer_maker,
        action_type='REFUND_DISPATCH',
        target_type='Refund',
        target_id=str(high_value_refund.id),
        amount=high_value_refund.amount,
        currency='GBP',
    )
    app_req = ApprovalService.approve_request(app_req.id, approver=finance_officer_checker)

    # Tamper with refund currency after approval (e.g. GBP -> EUR)
    high_value_refund.currency = 'EUR'
    high_value_refund.save(update_fields=['currency'])

    with pytest.raises(DjangoValidationError) as exc:
        RefundService.dispatch_gateway_refund(
            refund=high_value_refund,
            actor=finance_officer_checker,
            approved_request=app_req,
        )
    assert "integrity violation" in str(exc.value).lower()
    assert "approved currency" in str(exc.value).lower()


@pytest.mark.django_db
def test_concurrent_execution_dispatches_gateway_exactly_once(
    high_value_refund,
    finance_officer_maker,
    finance_officer_checker,
):
    """Simulates concurrent execution attempts against the same approved request.

    Asserts that:
    1. Gateway mock is called exactly once (mock_issue.call_count == 1).
    2. Concurrent competing execution attempt is blocked with ValidationError.
    3. Refund ends in SUCCEEDED and approval ends in EXECUTED.
    """
    app_req = ApprovalService.create_request(
        requester=finance_officer_maker,
        action_type='REFUND_DISPATCH',
        target_type='Refund',
        target_id=str(high_value_refund.id),
        amount=high_value_refund.amount,
        currency='GBP',
    )
    app_req = ApprovalService.approve_request(app_req.id, approver=finance_officer_checker)

    concurrent_error = []

    def mock_issue_refund_with_concurrency(*args, **kwargs):
        # While Worker 1 is in-flight with the payment gateway, Worker 2 attempts execution
        try:
            ApprovalService.execute_request(app_req.id, executor=finance_officer_checker)
        except DjangoValidationError as e:
            concurrent_error.append(str(e))
        except Exception as e:
            concurrent_error.append(f"Unexpected: {e}")
        return True, "re_test_concurrent_gateway_1", {"status": "succeeded"}

    with patch('apps.marketplace.payments.service.StripePaymentProvider.issue_refund', side_effect=mock_issue_refund_with_concurrency) as mock_issue:
        executed_req, dispatched_refund = ApprovalService.execute_request(
            app_req.id,
            executor=finance_officer_checker,
        )

    # 1. Assert gateway was contacted exactly once
    assert mock_issue.call_count == 1

    # 2. Assert competing attempt was rejected
    assert len(concurrent_error) == 1
    assert "currently being processed" in concurrent_error[0].lower()

    # 3. Assert consistent terminal states
    high_value_refund.refresh_from_db()
    assert high_value_refund.status == RefundStatusChoices.SUCCEEDED
    assert high_value_refund.gateway_refund_id == "re_test_concurrent_gateway_1"

    app_req.refresh_from_db()
    assert app_req.status == ApprovalStatusChoices.EXECUTED
    assert app_req.executed_by == finance_officer_checker
    assert app_req.execution_error == ""


@pytest.mark.django_db
def test_gateway_exception_handling_and_retry_behavior(
    high_value_refund,
    finance_officer_maker,
    finance_officer_checker,
):
    """If payment gateway raises a definitive business rejection (non-timeout):

    1. Refund transitions to FAILED (not locked in PROCESSING).
    2. ApprovalRequest retains APPROVED status with error recorded.
    3. Subsequent retry succeeds and transitions both to SUCCEEDED and EXECUTED.
    """
    app_req = ApprovalService.create_request(
        requester=finance_officer_maker,
        action_type='REFUND_DISPATCH',
        target_type='Refund',
        target_id=str(high_value_refund.id),
        amount=high_value_refund.amount,
        currency='GBP',
    )
    app_req = ApprovalService.approve_request(app_req.id, approver=finance_officer_checker)

    # First attempt: Gateway returns a definitive card declined / terminal rejection
    with patch(
        'apps.marketplace.payments.service.StripePaymentProvider.issue_refund',
        return_value=(False, "Card balance insufficient or account restricted", {}),
    ) as mock_issue:
        with pytest.raises(DjangoValidationError) as exc:
            ApprovalService.execute_request(app_req.id, executor=finance_officer_checker)

        assert mock_issue.call_count == 1
        assert "gateway" in str(exc.value).lower()

    # Verify failure state - not stuck in PROCESSING
    high_value_refund.refresh_from_db()
    assert high_value_refund.status == RefundStatusChoices.FAILED
    assert "restricted" in high_value_refund.failure_reason.lower()

    app_req.refresh_from_db()
    assert app_req.status == ApprovalStatusChoices.APPROVED  # Stays approved for retry
    assert "restricted" in app_req.execution_error.lower()

    # Second attempt: Gateway is restored, operator retries execution
    with patch('apps.marketplace.payments.service.StripePaymentProvider.issue_refund') as mock_issue_retry:
        mock_issue_retry.return_value = (True, "re_test_mock_retry_success_456", {"status": "succeeded"})

        executed_req, dispatched_refund = ApprovalService.execute_request(
            app_req.id,
            executor=finance_officer_checker,
        )

        assert mock_issue_retry.call_count == 1
        assert dispatched_refund.status == RefundStatusChoices.SUCCEEDED
        assert dispatched_refund.gateway_refund_id == "re_test_mock_retry_success_456"

    # Verify final consistent terminal state
    high_value_refund.refresh_from_db()
    assert high_value_refund.status == RefundStatusChoices.SUCCEEDED

    app_req.refresh_from_db()
    assert app_req.status == ApprovalStatusChoices.EXECUTED
    assert app_req.execution_error == ""


@pytest.mark.django_db
def test_gateway_timeout_transitions_to_processing_unknown_and_requires_reconciliation(
    high_value_refund,
    finance_officer_maker,
    finance_officer_checker,
):
    """When gateway network timeout occurs:
    1. Refund transitions to PROCESSING_UNKNOWN (never blindly marked as FAILED).
    2. ApprovalRequest retains APPROVED status with timeout recorded.
    3. Premature direct dispatch retry is rejected to avoid duplicate payouts.
    4. Safe reconciliation resolves ambiguous transaction via gateway inquiry.
    """
    app_req = ApprovalService.create_request(
        requester=finance_officer_maker,
        action_type='REFUND_DISPATCH',
        target_type='Refund',
        target_id=str(high_value_refund.id),
        amount=high_value_refund.amount,
        currency='GBP',
    )
    app_req = ApprovalService.approve_request(app_req.id, approver=finance_officer_checker)

    # First attempt: Gateway times out
    with patch(
        'apps.marketplace.payments.service.StripePaymentProvider.issue_refund',
        side_effect=RuntimeError("Gateway connection timed out after 30s"),
    ) as mock_issue:
        with pytest.raises(DjangoValidationError) as exc:
            ApprovalService.execute_request(app_req.id, executor=finance_officer_checker)

        assert mock_issue.call_count == 1
        assert "timeout" in str(exc.value).lower()

    # Verify intermediate ambiguous state: PROCESSING_UNKNOWN
    high_value_refund.refresh_from_db()
    assert high_value_refund.status == RefundStatusChoices.PROCESSING_UNKNOWN
    assert high_value_refund.idempotency_key == high_value_refund.refund_number
    assert "timed out" in high_value_refund.failure_reason.lower()

    app_req.refresh_from_db()
    assert app_req.status == ApprovalStatusChoices.APPROVED
    assert "timeout" in app_req.execution_error.lower()

    # Step 2: Attempting direct redispatch while in PROCESSING_UNKNOWN is BLOCKED
    with pytest.raises(DjangoValidationError) as exc_blocked:
        ApprovalService.execute_request(app_req.id, executor=finance_officer_checker)
    assert "reconciliation" in str(exc_blocked.value).lower()

    # Step 3: Reconcile via inquiry query to gateway
    with patch('apps.marketplace.payments.stripe_provider.StripePaymentProvider.inquire_refund') as mock_inquire:
        mock_inquire.return_value = ('SUCCEEDED', "re_stripe_inquired_ok_777", {"status": "succeeded"})

        reconciled_refund, status_res = RefundService.reconcile_refund(high_value_refund.id)

        assert status_res == "SUCCEEDED"
        assert reconciled_refund.status == RefundStatusChoices.SUCCEEDED
        assert reconciled_refund.gateway_refund_id == "re_stripe_inquired_ok_777"

    # Step 4: Verify ApprovalRequest was automatically executed upon successful reconciliation
    app_req.refresh_from_db()
    assert app_req.status == ApprovalStatusChoices.EXECUTED
    assert app_req.execution_error == ""

