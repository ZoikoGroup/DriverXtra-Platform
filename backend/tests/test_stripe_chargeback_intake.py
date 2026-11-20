"""G17a — Stripe chargeback intake and refund guard (recorded exception only; no money movement).

Covers acceptance tests AT-01..AT-18 of the G17a plan (see
docs/commercial/implementation-assessment/03_G17a_Stripe_Chargeback_Intake_Evidence_2026-11-20.md).
Runs on SQLite and PostgreSQL. Genuine-concurrency cases live in test_refund_concurrency_postgresql.py.

Approved decisions exercised here:
  1. warning_* inquiries are recorded but do not block refunds.
  2. while a chargeback blocks: no new approval/dispatch/settlement of existing refunds; their state is preserved;
     reconciliation, failure recording and rejection stay available.
  3. lost keeps refunds blocked (CHARGEBACK_LOST); won lifts the block.
  4. seller direct refunds record an already-completed payment and stay allowed (share/balance rules unchanged).
"""

import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal

import pytest
from django.conf import settings
from django.db import connection
from rest_framework import status
from rest_framework.test import APIClient

from apps.identity.models import ApprovalRequest, RoleChoices
from apps.marketplace.models import (
    Order,
    OrderItem,
    OrderStatusChoices,
    PaymentMethodChoices,
    PaymentStatusChoices,
    PaymentTransaction,
    PaymentWebhookEvent,
    Refund,
    RefundMethodChoices,
    RefundStatusChoices,
)
from apps.marketplace.payments import chargebacks
from apps.marketplace.returns.service import RefundService
from apps.notifications.models import Notification
from platform_core.audit.models import AuditLog
from tests.test_shared_order_seller_isolation import SHARE_A
from tests.test_shipping_and_logistics import (  # noqa: F401  (fixtures re-exported for pytest)
    brake_category,
    multi_seller_order,
    seller_b,
)

WEBHOOK_URL = "/api/v1/marketplace/payments/webhook/STRIPE/"
T0 = 1_763_600_000  # fixed Stripe event clock for deterministic ordering


# =============================================================================
# Helpers
# =============================================================================

def _stripe_paid(order, pi=None):
    """Mark an existing order as an online payment captured under a Stripe PaymentIntent (currency is immutable)."""
    order.payment_method = PaymentMethodChoices.ONLINE
    order.payment_status = PaymentStatusChoices.PAID
    order.payment_reference = pi or f"pi_test_{uuid.uuid4().hex[:16]}"
    order.save(update_fields=["payment_method", "payment_status", "payment_reference", "updated_at"])
    return order


def _gbp_single_seller_order(buyer, listing, quantity=2, pi=None):
    """Single-seller UK order paid by Stripe in GBP (the currency Stripe supports here)."""
    taxable = listing.price * quantity
    total = (taxable * Decimal("1.20")).quantize(Decimal("0.01"))
    order = Order.objects.create(
        buyer=buyer, order_number=f"DX-ORD-GBP-{uuid.uuid4().hex[:6].upper()}",
        status=OrderStatusChoices.CONFIRMED, payment_method=PaymentMethodChoices.ONLINE,
        payment_status=PaymentStatusChoices.PAID, currency="GBP", shipping_country="United Kingdom",
        payment_reference=pi or f"pi_test_{uuid.uuid4().hex[:16]}",
        subtotal_taxable_amount=taxable, total_tax_amount=total - taxable, total_amount=total,
    )
    OrderItem.objects.create(
        order=order, listing=listing, item_type="PART", title=listing.name, brand=listing.brand, mpn=listing.mpn,
        hsn_code=listing.hsn_code, gst_rate=listing.gst_rate, unit_price=listing.price, quantity=quantity,
        taxable_amount=taxable, tax_amount=total - taxable, total_amount=total,
    )
    return order


def dispute_event(pi, status_, event_type="charge.dispute.created", dispute_id="dp_test_1", created=T0,
                  amount=1000, currency="gbp", reason="fraudulent", balance_transactions=None, event_id=None,
                  due_by=T0 + 7 * 86400):
    return {
        "id": event_id or f"evt_{uuid.uuid4().hex[:20]}",
        "object": "event",
        "type": event_type,
        "created": created,
        "livemode": False,
        "data": {"object": {
            "id": dispute_id, "object": "dispute", "payment_intent": pi, "charge": f"ch_{dispute_id}",
            "amount": amount, "currency": currency, "reason": reason, "status": status_,
            "evidence_details": {"due_by": due_by, "past_due": False, "has_evidence": False},
            "balance_transactions": balance_transactions or [],
            "metadata": {},
        }},
    }


def post_event(body, sign=True):
    raw = json.dumps(body).encode("utf-8")
    headers = {}
    if sign:
        ts = int(time.time())
        mac = hmac.new(settings.STRIPE_WEBHOOK_SECRET.encode(), f"{ts}.{raw.decode()}".encode(), hashlib.sha256)
        headers["HTTP_STRIPE_SIGNATURE"] = f"t={ts},v1={mac.hexdigest()}"
    return APIClient().post(WEBHOOK_URL, data=raw, content_type="application/json", **headers)


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _admin_refund(admin, order, amount, **extra):
    return _client(admin).post(f"/api/v1/marketplace/admin/orders/{order.id}/refund/",
                               {"amount": str(amount), "reason": "Operations refund", **extra}, format="json")


def _seller_record(seller, order, amount):
    return _client(seller).post(f"/api/v1/marketplace/seller/orders/{order.id}/record-refund/",
                                {"amount": str(amount), "transaction_reference": f"UTR{uuid.uuid4().hex[:10]}",
                                 "refund_method": "BANK_TRANSFER"}, format="json")


def _audits(event_type):
    return AuditLog.objects.filter(event_type=event_type)


def _open(order, pi, **kw):
    res = post_event(dispute_event(pi, "needs_response", **kw))
    assert res.status_code == 200, res.content
    return res


@pytest.fixture
def gbp_order(multi_seller_order, buyer_user):
    """Single-seller (seller_user) order, Stripe GBP, paid; total 2880.00."""
    _, item_a, _ = multi_seller_order
    return _gbp_single_seller_order(buyer_user, item_a.listing, quantity=2)


# =============================================================================
# 1. Intake and recording (AT-01..AT-08, AT-15)
# =============================================================================

@pytest.mark.django_db
def test_dispute_created_is_linked_and_recorded_without_state_change(gbp_order):  # AT-01
    order = gbp_order
    refunds_before, txns_before = Refund.objects.count(), PaymentTransaction.objects.count()

    res = _open(order, order.payment_reference, amount=2832_00)
    assert res.json()["order_number"] == order.order_number

    event = PaymentWebhookEvent.objects.get(event_type="charge.dispute.created")
    assert event.order_id == order.id and event.processed
    audit = _audits("marketplace.payment.chargeback_opened").get()
    meta = audit.metadata
    assert audit.resource_id == str(order.id) and audit.actor_kind == "SYSTEM"
    assert meta["dispute_id"] == "dp_test_1" and meta["amount_minor"] == 2832_00 and meta["currency"] == "GBP"
    assert meta["reason"] == "fraudulent" and meta["status"] == "needs_response" and meta["state"] == "OPEN"
    assert meta["evidence_due_by"] == datetime.fromtimestamp(T0 + 7 * 86400, tz=dt_timezone.utc).isoformat()
    assert meta["currency_mismatch"] is False and meta["livemode"] is False

    order.refresh_from_db()
    assert (order.status, order.payment_status) == (OrderStatusChoices.CONFIRMED, PaymentStatusChoices.PAID)
    assert Refund.objects.count() == refunds_before and PaymentTransaction.objects.count() == txns_before


@pytest.mark.django_db
def test_invalid_or_missing_signature_is_rejected_and_nothing_recorded(gbp_order):  # AT-02
    body = dispute_event(gbp_order.payment_reference, "needs_response")
    assert post_event(body, sign=False).status_code == 400
    raw = json.dumps(body).encode()
    bad = APIClient().post(WEBHOOK_URL, data=raw, content_type="application/json",
                           HTTP_STRIPE_SIGNATURE=f"t={int(time.time())},v1={'0' * 64}")
    assert bad.status_code == 400
    assert not PaymentWebhookEvent.objects.filter(event_type__startswith="charge.dispute.").exists()
    assert not _audits("marketplace.payment.chargeback_opened").exists()


@pytest.mark.django_db
def test_duplicate_delivery_is_recorded_once(gbp_order):  # AT-03
    body = dispute_event(gbp_order.payment_reference, "needs_response", event_id="evt_dup_1")
    assert post_event(body).status_code == 200
    replay = post_event(body)
    assert replay.status_code == 200 and replay.json()["status"] == "already_processed"
    assert PaymentWebhookEvent.objects.filter(event_id="evt_dup_1").count() == 1
    assert _audits("marketplace.payment.chargeback_opened").count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("pi, reason", [("pi_unknown_123", "NOT_FOUND"), (None, "NO_PAYMENT_INTENT")])
def test_unmatched_dispute_stays_visible(gbp_order, pi, reason):  # AT-04
    res = post_event(dispute_event(pi, "needs_response"))
    assert res.status_code == 200 and res.json()["order_number"] is None
    event = PaymentWebhookEvent.objects.get(event_type="charge.dispute.created")
    assert event.order_id is None and event.processed
    audit = _audits("marketplace.payment.chargeback_unmatched").get()
    assert audit.reason_code == reason and audit.resource_id == str(event.id)
    assert audit.metadata["dispute_id"] == "dp_test_1"
    # Nothing was linked, so no order is blocked (documented limitation).
    assert chargebacks.dispute_states(gbp_order) == []


@pytest.mark.django_db
def test_ambiguous_payment_reference_is_unmatched(gbp_order, buyer_user, multi_seller_order):  # AT-05
    _, item_a, _ = multi_seller_order
    twin = _gbp_single_seller_order(buyer_user, item_a.listing, quantity=1, pi=gbp_order.payment_reference)
    post_event(dispute_event(gbp_order.payment_reference, "needs_response"))
    assert _audits("marketplace.payment.chargeback_unmatched").get().reason_code == "AMBIGUOUS"
    assert chargebacks.dispute_states(gbp_order) == chargebacks.dispute_states(twin) == []


@pytest.mark.django_db
def test_lost_lifecycle_records_fees_separately_and_keeps_refunds_blocked(gbp_order, admin_user):  # AT-06, AT-12
    order, pi = gbp_order, gbp_order.payment_reference
    withdrawal = [{"id": "txn_w1", "amount": -1000, "fee": 1500, "net": -2500, "currency": "gbp",
                   "reporting_category": "dispute",
                   "fee_details": [{"amount": 1500, "currency": "gbp", "type": "stripe_fee",
                                    "description": "Dispute fee"}]}]
    post_event(dispute_event(pi, "needs_response", created=T0))
    post_event(dispute_event(pi, "under_review", "charge.dispute.updated", created=T0 + 10))
    post_event(dispute_event(pi, "under_review", "charge.dispute.funds_withdrawn", created=T0 + 20,
                             balance_transactions=withdrawal))
    post_event(dispute_event(pi, "lost", "charge.dispute.closed", created=T0 + 30))

    for suffix in ("opened", "updated", "funds_withdrawn", "closed"):
        assert _audits(f"marketplace.payment.chargeback_{suffix}").count() == 1, suffix
    txn = _audits("marketplace.payment.chargeback_funds_withdrawn").get().metadata["balance_transactions"][0]
    assert (txn["amount_minor"], txn["fee_minor"]) == (-1000, 1500)       # recorded separately
    assert "net" not in txn and "net_minor" not in txn                     # never netted by the platform
    assert txn["fee_details"][0]["type"] == "stripe_fee"
    assert _audits("marketplace.payment.chargeback_closed").get().metadata["outcome"] == "lost"

    # Decision 3: lost keeps refunds blocked; refundable balance is not silently restored.
    res = _admin_refund(admin_user, order, "10.00")
    assert res.status_code == 400 and res.json()["code"] == "CHARGEBACK_LOST"
    assert Refund.objects.filter(order=order).count() == 0
    order.refresh_from_db()
    assert order.payment_status == PaymentStatusChoices.PAID  # no ledger/state change


@pytest.mark.django_db
def test_won_lifts_the_block(gbp_order, admin_user):  # AT-07, AT-12
    order, pi = gbp_order, gbp_order.payment_reference
    _open(order, pi, created=T0)
    assert _admin_refund(admin_user, order, "10.00").json()["code"] == "CHARGEBACK_OPEN"
    post_event(dispute_event(pi, "won", "charge.dispute.closed", created=T0 + 10))
    post_event(dispute_event(pi, "won", "charge.dispute.funds_reinstated", created=T0 + 20,
                             balance_transactions=[{"id": "txn_r1", "amount": 1000, "fee": -1500,
                                                    "currency": "gbp", "reporting_category": "dispute_reversal"}]))
    assert _audits("marketplace.payment.chargeback_funds_reinstated").count() == 1
    ok = _admin_refund(admin_user, order, "10.00")
    assert ok.status_code == 201, ok.content


@pytest.mark.django_db
def test_out_of_order_delivery_cannot_reopen_a_closed_dispute(gbp_order, admin_user):  # AT-08
    order, pi = gbp_order, gbp_order.payment_reference
    post_event(dispute_event(pi, "won", "charge.dispute.closed", created=T0 + 30))   # delivered first
    post_event(dispute_event(pi, "needs_response", created=T0))                       # late, older
    post_event(dispute_event(pi, "under_review", "charge.dispute.updated", created=T0 + 10))
    assert chargebacks.dispute_states(order)[0]["state"] == chargebacks.STATE_WON
    assert _admin_refund(admin_user, order, "10.00").status_code == 201


@pytest.mark.django_db
def test_same_timestamp_conflict_fails_closed(gbp_order):  # AT-08 (tie-break)
    pi = gbp_order.payment_reference
    post_event(dispute_event(pi, "warning_under_review", "charge.dispute.updated", created=T0))
    post_event(dispute_event(pi, "needs_response", "charge.dispute.updated", created=T0))
    assert chargebacks.dispute_states(gbp_order)[0]["state"] == chargebacks.STATE_OPEN


@pytest.mark.django_db
def test_currency_mismatch_is_flagged(gbp_order):  # AT-15
    post_event(dispute_event(gbp_order.payment_reference, "needs_response", currency="usd"))
    meta = _audits("marketplace.payment.chargeback_opened").get().metadata
    assert meta["currency"] == "USD" and meta["order_currency"] == "GBP" and meta["currency_mismatch"] is True


# =============================================================================
# 2. Refund guard on creation paths (AT-09, AT-10, AT-13, AT-14)
# =============================================================================

@pytest.mark.django_db
def test_inquiry_is_recorded_but_does_not_block_until_escalated(gbp_order, admin_user):  # AT-13 / decision 1
    order, pi = gbp_order, gbp_order.payment_reference
    post_event(dispute_event(pi, "warning_needs_response", created=T0))
    meta = _audits("marketplace.payment.chargeback_opened").get().metadata
    assert meta["is_inquiry"] is True and meta["state"] == "INQUIRY"
    assert _admin_refund(admin_user, order, "10.00").status_code == 201        # refund may prevent escalation
    post_event(dispute_event(pi, "needs_response", "charge.dispute.updated", created=T0 + 10))  # escalated
    assert _admin_refund(admin_user, order, "10.00").json()["code"] == "CHARGEBACK_OPEN"


@pytest.mark.django_db
@pytest.mark.parametrize("auto_process", [False, True])
def test_admin_refund_creation_blocked_while_open(gbp_order, admin_user, auto_process):  # AT-09
    order = gbp_order
    _open(order, order.payment_reference)
    res = _admin_refund(admin_user, order, "10.00", auto_process=auto_process)
    assert res.status_code == 400 and res.json()["code"] == "CHARGEBACK_OPEN"
    assert "dp_test_1" not in res.json()["error"]  # no dispute identifiers in the message
    assert Refund.objects.filter(order=order).count() == 0
    if connection.vendor == "postgresql":  # denied audit is autonomous only on PostgreSQL (existing writer design)
        denied = AuditLog.objects.get(reason_code="CHARGEBACK_OPEN", action="marketplace:refund.create",
                                      metadata__order_number=order.order_number)
        assert denied.status == AuditLog.STATUS_DENIED and denied.metadata["attempted_amount"] == "10.00"


@pytest.mark.django_db
def test_seller_platform_refund_request_blocked_while_open(gbp_order, seller_user):  # AT-09
    order = gbp_order
    seller_user.add_role(RoleChoices.ADMIN)  # holds order.refund and still sells the item (as in ENG-05a tests)
    _open(order, order.payment_reference)
    res = _client(seller_user).post(f"/api/v1/marketplace/seller/orders/{order.id}/request-platform-refund/",
                                    {"amount": "10.00", "reason": "Customer return"}, format="json")
    assert res.status_code == 400 and res.json()["code"] == "CHARGEBACK_OPEN"
    assert Refund.objects.filter(order=order).count() == 0


@pytest.mark.django_db
def test_chargeback_reason_takes_precedence_over_balance_error(gbp_order, admin_user):  # AT-10
    _open(gbp_order, gbp_order.payment_reference)
    res = _admin_refund(admin_user, gbp_order, "999999.00")
    assert res.status_code == 400 and res.json()["code"] == "CHARGEBACK_OPEN"


@pytest.mark.django_db
def test_one_open_dispute_among_several_still_blocks(gbp_order, admin_user):  # AT-14
    pi = gbp_order.payment_reference
    post_event(dispute_event(pi, "won", "charge.dispute.closed", dispute_id="dp_a", created=T0))
    post_event(dispute_event(pi, "needs_response", dispute_id="dp_b", created=T0))
    states = {d["dispute_id"]: d["state"] for d in chargebacks.dispute_states(gbp_order)}
    assert states == {"dp_a": "WON", "dp_b": "OPEN"}
    assert _admin_refund(admin_user, gbp_order, "10.00").json()["code"] == "CHARGEBACK_OPEN"


# =============================================================================
# 3. Existing refunds while blocked (AT-11 / decision 2)
# =============================================================================

def _snapshot(refund):
    refund.refresh_from_db()
    return (refund.status, refund.approved_by_id, refund.notes, refund.gateway_refund_id, refund.processed_at)


@pytest.mark.django_db
def test_pending_refund_preserved_and_approve_dispatch_process_blocked(gbp_order, admin_user):
    order = gbp_order
    gateway = RefundService.create_refund(order=order, amount=Decimal("20.00"), reason="Pre-dispute", actor=admin_user)
    manual = RefundService.create_refund(order=order, amount=Decimal("30.00"), reason="Pre-dispute manual",
                                         actor=admin_user, refund_method=RefundMethodChoices.BANK_TRANSFER)
    before = {r.id: _snapshot(r) for r in (gateway, manual)}
    _open(order, order.payment_reference)

    # Dispute events never touch existing refunds.
    assert {r.id: _snapshot(r) for r in (gateway, manual)} == before

    admin = _client(admin_user)
    for refund in (gateway, manual):
        for action in ("approve", "dispatch", "process"):
            res = admin.post(f"/api/v1/marketplace/admin/refunds/{refund.id}/{action}/", {}, format="json")
            assert res.status_code == 400, (action, res.content)
            assert res.json()["code"] == "CHARGEBACK_OPEN", (action, res.json())
            assert _snapshot(refund) == before[refund.id], action          # preserved, not modified
    assert Refund.objects.filter(order=order).count() == 2

    # Failure recording and rejection remain available.
    RefundService.fail_refund(manual, admin_user, failure_reason="Bank transfer bounced")
    manual.refresh_from_db()
    assert manual.status == RefundStatusChoices.FAILED
    RefundService.reject_refund(manual, admin_user, reason="Superseded by chargeback")
    manual.refresh_from_db()
    assert manual.status == RefundStatusChoices.CANCELLED

    # Won: approval and dispatch of the preserved pending refund resume.
    post_event(dispute_event(order.payment_reference, "won", "charge.dispute.closed", created=T0 + 99))
    approved = RefundService.approve_refund(gateway, admin_user)
    assert approved.status == RefundStatusChoices.SUCCEEDED


@pytest.mark.django_db
def test_high_value_dispatch_creates_no_maker_checker_request_while_blocked(gbp_order, admin_user):
    from apps.identity.approval_service import ApprovalService
    threshold = ApprovalService.get_threshold_for_currency("GBP")
    amount = (threshold + Decimal("1.00")).quantize(Decimal("0.01"))
    if amount > gbp_order.total_amount:
        pytest.skip("fixture order total is below the GBP maker-checker threshold")
    refund = RefundService.create_refund(order=gbp_order, amount=amount, reason="High value", actor=admin_user)
    _open(gbp_order, gbp_order.payment_reference)
    approvals_before = ApprovalRequest.objects.count()
    res = _client(admin_user).post(f"/api/v1/marketplace/admin/refunds/{refund.id}/dispatch/", {}, format="json")
    assert res.status_code == 400 and res.json()["code"] == "CHARGEBACK_OPEN"
    assert ApprovalRequest.objects.count() == approvals_before


# =============================================================================
# 4. Seller direct refunds record completed payments (decision 4)
# =============================================================================

@pytest.mark.django_db
@pytest.mark.parametrize("dispute_status", ["needs_response", "lost"])
def test_seller_direct_refund_recording_allowed_and_evidenced(gbp_order, seller_user, admin_user, dispute_status):
    order = gbp_order
    post_event(dispute_event(order.payment_reference, dispute_status))
    res = _seller_record(seller_user, order, "50.00")
    assert res.status_code == 201, res.content
    refund = Refund.objects.get(order=order)
    assert refund.gateway_provider == "SELLER_DIRECT" and refund.status == RefundStatusChoices.PROCESSING
    evidence = _audits("marketplace.refund.seller_evidence_submitted").get().metadata
    assert evidence["recorded_while_chargeback_blocks"] is True
    assert evidence["chargebacks_at_recording"][0]["dispute_id"] == "dp_test_1"
    assert evidence["transaction_reference"] == refund.gateway_refund_id

    # Completing a recorded seller-direct payment is a record, not a dispatch: still allowed.
    processed = RefundService.process_refund(refund, admin_user, notes="Buyer receipt verified")
    assert processed.status == RefundStatusChoices.SUCCEEDED


@pytest.mark.django_db
def test_buyer_can_confirm_receipt_of_seller_direct_refund_during_chargeback(gbp_order, seller_user, buyer_user):
    """Confirming receipt records a completed payment; it is not an approval or dispatch, so it stays available."""
    order = gbp_order
    assert _seller_record(seller_user, order, "50.00").status_code == 201
    _open(order, order.payment_reference)
    refund = Refund.objects.get(order=order)
    res = _client(buyer_user).post(f"/api/v1/marketplace/buyer/refunds/{refund.id}/confirm-receipt/", format="json")
    assert res.status_code == 200, res.content
    refund.refresh_from_db()
    assert refund.status == RefundStatusChoices.SUCCEEDED


@pytest.mark.django_db
def test_seller_direct_recording_keeps_share_and_balance_rules(multi_seller_order, seller_user):
    order = _stripe_paid(multi_seller_order[0])          # INR fixture order; intake links by PaymentIntent
    _open(order, order.payment_reference, currency="inr")
    over_share = _seller_record(seller_user, order, SHARE_A + Decimal("0.01"))
    assert over_share.status_code == 400 and over_share.json()["code"] == "SELLER_REFUND_LIMIT_EXCEEDED"
    assert _seller_record(seller_user, order, SHARE_A).status_code == 201
    again = _seller_record(seller_user, order, "0.01")
    assert again.status_code == 400 and again.json()["code"] == "SELLER_REFUND_LIMIT_EXCEEDED"


# =============================================================================
# 5. Visibility and no external notification (AT-17, AT-18)
# =============================================================================

@pytest.mark.django_db
def test_chargeback_events_create_no_notifications(gbp_order):  # AT-17 (REF-08 deferred)
    before = Notification.objects.count()
    pi = gbp_order.payment_reference
    post_event(dispute_event(pi, "needs_response", created=T0))
    post_event(dispute_event(pi, "lost", "charge.dispute.closed", created=T0 + 1))
    post_event(dispute_event("pi_unmatched", "needs_response", dispute_id="dp_x"))
    assert Notification.objects.count() == before


@pytest.mark.django_db
def test_refund_summary_exposes_chargebacks_to_staff_only(gbp_order, admin_user, buyer_user):  # AT-18
    _open(gbp_order, gbp_order.payment_reference)
    url = f"/api/v1/marketplace/orders/{gbp_order.id}/refund-summary/"
    staff = _client(admin_user).get(url).json()
    assert staff["chargeback_refund_block_code"] == "CHARGEBACK_OPEN"
    assert staff["chargebacks"][0]["dispute_id"] == "dp_test_1"
    buyer = _client(buyer_user).get(url)
    assert buyer.status_code == 200
    assert "chargebacks" not in buyer.json() and "chargeback_refund_block_code" not in buyer.json()
