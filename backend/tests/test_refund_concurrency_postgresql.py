"""ENG-05a-PG — PostgreSQL concurrency verification for shared-order refund limits.

These tests exercise *real* concurrent transactions: every request runs in its own thread with its own
PostgreSQL connection, through the real HTTP endpoints. They are skipped on any other database vendor,
because SQLite cannot provide evidence of PostgreSQL row-lock behaviour.

How overlap is forced (and proven):
    ``LockContentionGate`` wraps ``RefundService.get_order_refund_summary`` as a pass-through. Both refund
    services call it only *after* ``Order.objects.select_for_update()`` has locked the order row, so the first
    request to reach it is the lock holder. The holder keeps its transaction open and polls PostgreSQL until it
    observes the competing request's backend blocked by the holder's own backend PID
    (``pg_blocking_pids``) on the ``SELECT ... FOR UPDATE`` of the order row. Only then does it continue.
    Each test asserts that this contention was observed, so a test cannot pass by running the two requests
    one after another. No production code is patched other than this pass-through observation hook.

Order fixture (from test_shipping_and_logistics): seller_user owns item A (total 2832.00), seller_b owns
item B (total 2360.00); order total 5192.00. Marked online-PAID for refund eligibility.

Run with:  TEST_USE_SQLITE=False  pytest tests/test_refund_concurrency_postgresql.py
"""

import threading
import time
import uuid
from decimal import Decimal
from unittest import mock

import pytest
from django.db import connection
from rest_framework import status
from rest_framework.test import APIClient

from apps.identity.models import RoleChoices
from apps.marketplace.models import (
    Dispute,
    Order,
    PaymentStatusChoices,
    PaymentWebhookEvent,
    Refund,
    RefundStatusChoices,
)
from apps.marketplace.payments import chargebacks
from apps.marketplace.returns.service import RefundService
from platform_core.audit.models import AuditLog
from tests.test_shared_order_seller_isolation import (
    SHARE_A,
    SHARE_B,
    _mark_paid_online,
    _single_seller_order,
)
from tests.test_stripe_chargeback_intake import (
    _gbp_single_seller_order,
    dispute_event,
    post_event,
)
from tests.test_shipping_and_logistics import (  # noqa: F401  (fixtures re-exported for pytest)
    brake_category,
    multi_seller_order,
    seller_b,
)

pytestmark = [
    pytest.mark.skipif(
        connection.vendor != "postgresql",
        reason="PostgreSQL row-lock concurrency tests; run with TEST_USE_SQLITE=False against PostgreSQL.",
    ),
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

ORDER_TOTAL = SHARE_A + SHARE_B  # 5192.00
HOLD_TIMEOUT_S = 15.0
THREAD_TIMEOUT_S = 60.0
ORDER_BALANCE_MSG = "exceeds maximum available refundable balance"


# =============================================================================
# Concurrency harness
# =============================================================================

class LockContentionGate:
    """Pass-through wrapper that holds the first order-lock holder until a competitor is seen blocked on it."""

    def __init__(self):
        self._mutex = threading.Lock()
        self._entries = 0
        self.holder_has_lock = threading.Event()
        self.holder_pid = None
        self.waiter = None          # dict describing the blocked competing backend, once observed
        self.hold_seconds = None

    def _first_entry(self):
        with self._mutex:
            self._entries += 1
            return self._entries == 1

    def install(self):
        """Hold point: RefundService.get_order_refund_summary (refund paths, after the order row lock)."""
        original = RefundService.get_order_refund_summary  # bound classmethod
        gate = self

        def gated_summary(cls, order):
            if gate._first_entry():
                gate._hold_until_competitor_blocked()
            return original(order)

        return mock.patch.object(RefundService, "get_order_refund_summary", classmethod(gated_summary))

    def install_on_function(self, module, name):
        """Hold point: a module-level function called inside a locked transaction (e.g. chargeback intake)."""
        original = getattr(module, name)
        gate = self

        def gated(*args, **kwargs):
            if gate._first_entry():
                gate._hold_until_competitor_blocked()
            return original(*args, **kwargs)

        return mock.patch.object(module, name, gated)

    def _hold_until_competitor_blocked(self):
        # We are inside the service's transaction.atomic(), after select_for_update() on the order row.
        assert connection.in_atomic_block, "gate must run inside the refund transaction"
        started = time.monotonic()
        with connection.cursor() as cur:
            cur.execute("SELECT pg_backend_pid()")
            self.holder_pid = cur.fetchone()[0]
            self.holder_has_lock.set()
            while time.monotonic() - started < HOLD_TIMEOUT_S:
                # pg_stat_activity is snapshotted per transaction; clear it so each poll is live.
                cur.execute("SELECT pg_stat_clear_snapshot()")
                cur.execute(
                    """
                    SELECT a.pid, a.wait_event_type, a.wait_event, a.state, a.query
                    FROM pg_stat_activity a
                    WHERE a.datname = current_database()
                      AND pg_backend_pid() = ANY(pg_blocking_pids(a.pid))
                      AND a.wait_event_type = 'Lock'  -- stats snapshot can lag the live lock graph; wait for both
                    """
                )
                row = cur.fetchone()
                if row:
                    # pg_stat_activity.query is truncated (track_activity_query_size), so read the waiter's
                    # locks to prove it is a SELECT ... FOR UPDATE (RowShareLock) on the order table.
                    cur.execute(
                        "SELECT locktype, relation::regclass::text, mode, granted FROM pg_locks WHERE pid = %s",
                        [row[0]],
                    )
                    self.waiter = {
                        "pid": row[0], "wait_event_type": row[1], "wait_event": row[2],
                        "state": row[3], "query": row[4], "locks": cur.fetchall(),
                        "observed_after_s": round(time.monotonic() - started, 3),
                    }
                    break
                time.sleep(0.02)
        self.hold_seconds = round(time.monotonic() - started, 3)

    def assert_contention_observed(self, table=None, query_prefix=None, relation_lock="RowShareLock"):
        """Default: the competitor is blocked in SELECT ... FOR UPDATE on the order row.
        Pass table/query_prefix/relation_lock for other blocking statements (e.g. a unique-key INSERT)."""
        assert self.waiter is not None, (
            "No competing transaction was observed blocked on the order row lock; the requests did not overlap."
        )
        assert self.waiter["pid"] != self.holder_pid
        assert self.waiter["wait_event_type"] == "Lock", self.waiter
        table = table or Order._meta.db_table
        query_prefix = query_prefix or f'SELECT "{table}".'
        assert self.waiter["query"].startswith(query_prefix), self.waiter["query"][:120]
        locks = self.waiter["locks"]
        assert ("relation", table, relation_lock, True) in locks, locks   # e.g. taken by SELECT ... FOR UPDATE
        assert any(not granted for (_, _, _, granted) in locks), locks     # and still waiting on the holder
        print(
            f"[ENG-05a-PG] holder_pid={self.holder_pid} waiter_pid={self.waiter['pid']} "
            f"wait={self.waiter['wait_event_type']}/{self.waiter['wait_event']} "
            f"observed_after_s={self.waiter['observed_after_s']} holder_held_lock_s={self.hold_seconds} "
            f"waiter_ungranted={[lk for lk in locks if not lk[3]]}"
        )


def _client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def run_concurrently(calls, gate, first_label=None):
    """Run each (label, fn) in its own thread with its own DB connection.

    first_label=None  -> all threads are released together by a barrier (winner not chosen).
    first_label=<lbl> -> that call starts first; the others start once it holds the order lock,
                         so they are guaranteed to queue behind it (deterministic winner).
    Returns {label: {"status": int, "body": dict, "elapsed_s": float}}.
    """
    results = {}
    errors = {}
    barrier = threading.Barrier(len(calls))

    def worker(label, fn):
        try:
            if first_label is None:
                barrier.wait(timeout=THREAD_TIMEOUT_S)
            elif label != first_label:
                assert gate.holder_has_lock.wait(timeout=THREAD_TIMEOUT_S), "first request never took the lock"
            started = time.monotonic()
            response = fn()
            results[label] = {
                "status": response.status_code,
                "body": response.json() if response.content else {},
                "elapsed_s": round(time.monotonic() - started, 3),
            }
        except BaseException as exc:  # surfaced to the main thread below
            errors[label] = exc
        finally:
            connection.close()  # each thread owns its own PostgreSQL connection

    threads = [threading.Thread(target=worker, args=call, name=f"refund-{call[0]}") for call in calls]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=THREAD_TIMEOUT_S)
        assert not thread.is_alive(), f"{thread.name} did not finish"
    if errors:
        raise AssertionError(f"Request thread(s) raised: {errors!r}")
    print("[ENG-05a-PG] " + "; ".join(
        f"{label}: HTTP {r['status']} {r['body'].get('code', '')} in {r['elapsed_s']}s" for label, r in results.items()
    ))
    return results


def _record(user, order, amount):
    def call():
        return _client_for(user).post(
            f"/api/v1/marketplace/seller/orders/{order.id}/record-refund/",
            {"amount": str(amount), "transaction_reference": f"UTR{uuid.uuid4().hex[:12].upper()}",
             "refund_method": "BANK_TRANSFER"},
            format="json",
        )
    return call


def _platform_request(user, order, amount):
    def call():
        return _client_for(user).post(
            f"/api/v1/marketplace/seller/orders/{order.id}/request-platform-refund/",
            {"amount": str(amount), "reason": "Customer return"},
            format="json",
        )
    return call


def _admin_refund(user, order, amount, dispute=None):
    def call():
        payload = {"amount": str(amount), "reason": "Operations refund"}
        if dispute is not None:
            payload["dispute_id"] = str(dispute.id)
        return _client_for(user).post(f"/api/v1/marketplace/admin/orders/{order.id}/refund/", payload, format="json")
    return call


def _active_refunds(order):
    return list(Refund.objects.filter(
        order=order,
        status__in=[RefundStatusChoices.PENDING, RefundStatusChoices.PROCESSING,
                    RefundStatusChoices.PROCESSING_UNKNOWN, RefundStatusChoices.SUCCEEDED],
    ))


def _assert_no_lingering_locks():
    with connection.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid "
            "WHERE a.datname = current_database() AND NOT l.granted"
        )
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT pg_stat_clear_snapshot()")
        cur.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
            "AND state LIKE 'idle in transaction%' AND pid <> pg_backend_pid()"
        )
        assert cur.fetchone()[0] == 0


def _split(results):
    winners = {k: v for k, v in results.items() if v["status"] == status.HTTP_201_CREATED}
    losers = {k: v for k, v in results.items() if v["status"] != status.HTTP_201_CREATED}
    return winners, losers


# =============================================================================
# 1. Competing sellers on the same shared order
# =============================================================================

def test_pg_two_sellers_refund_full_shares_simultaneously(multi_seller_order, seller_user, seller_b):
    """Both sellers refund their entire share at the same moment: serialized, both allowed, total == order."""
    order = _mark_paid_online(multi_seller_order[0])
    gate = LockContentionGate()
    with gate.install():
        results = run_concurrently(
            [("seller_a", _record(seller_user, order, SHARE_A)), ("seller_b", _record(seller_b, order, SHARE_B))],
            gate,
        )
    gate.assert_contention_observed()

    assert results["seller_a"]["status"] == status.HTTP_201_CREATED, results
    assert results["seller_b"]["status"] == status.HTTP_201_CREATED, results
    refunds = _active_refunds(order)
    assert len(refunds) == 2
    assert {r.created_by_id: r.amount for r in refunds} == {seller_user.id: SHARE_A, seller_b.id: SHARE_B}
    assert sum(r.amount for r in refunds) == ORDER_TOTAL == order.total_amount
    assert len({r.refund_number for r in refunds}) == 2
    assert RefundService.get_order_refund_summary(Order.objects.get(id=order.id))["available_refundable"] == 0
    _assert_no_lingering_locks()


@pytest.mark.parametrize("first", ["seller_a", "seller_b"])
def test_pg_seller_overreach_while_other_seller_refunds(multi_seller_order, seller_user, seller_b, first):
    """Seller A tries more than A's share while B refunds B's full share: A is refused either way, B unaffected."""
    order = _mark_paid_online(multi_seller_order[0])
    gate = LockContentionGate()
    with gate.install():
        results = run_concurrently(
            [("seller_a", _record(seller_user, order, SHARE_A + Decimal("0.01"))),
             ("seller_b", _record(seller_b, order, SHARE_B))],
            gate, first_label=first,
        )
    gate.assert_contention_observed()

    assert results["seller_b"]["status"] == status.HTTP_201_CREATED, results
    assert results["seller_a"]["status"] == status.HTTP_400_BAD_REQUEST, results
    if first == "seller_a":
        # Order balance (5192.00) allows it; the seller-share check refuses it.
        assert results["seller_a"]["body"]["code"] == "SELLER_REFUND_LIMIT_EXCEEDED"
    else:
        # B's committed refund leaves 2832.00 order balance, so the order-level check refuses 2832.01 first.
        assert ORDER_BALANCE_MSG in results["seller_a"]["body"]["error"]
    refunds = _active_refunds(order)
    assert [(r.created_by_id, r.amount) for r in refunds] == [(seller_b.id, SHARE_B)]
    _assert_no_lingering_locks()


# =============================================================================
# 2. Same seller, concurrent requests that together exceed the seller's share
# =============================================================================

def test_pg_same_seller_concurrent_direct_refunds_cannot_exceed_share(multi_seller_order, seller_user):
    order = _mark_paid_online(multi_seller_order[0])
    audit_before = AuditLog.objects.filter(event_type="marketplace.refund.seller_evidence_submitted").count()
    gate = LockContentionGate()
    with gate.install():
        results = run_concurrently(
            [("first", _record(seller_user, order, Decimal("2000.00"))),
             ("second", _record(seller_user, order, Decimal("2000.00")))],
            gate,
        )
    gate.assert_contention_observed()

    winners, losers = _split(results)
    assert len(winners) == 1 and len(losers) == 1, results
    loser = next(iter(losers.values()))
    assert loser["status"] == status.HTTP_400_BAD_REQUEST
    assert loser["body"]["code"] == "SELLER_REFUND_LIMIT_EXCEEDED"
    assert "INR 832.00" in loser["body"]["error"]  # remaining share computed from the winner's committed refund

    # The losing transaction left nothing behind: one refund, one evidence audit entry, order untouched.
    refunds = _active_refunds(order)
    assert [r.amount for r in refunds] == [Decimal("2000.00")]
    assert Refund.objects.filter(order=order).count() == 1
    assert AuditLog.objects.filter(
        event_type="marketplace.refund.seller_evidence_submitted").count() == audit_before + 1
    order.refresh_from_db()
    assert order.payment_status == PaymentStatusChoices.PAID
    _assert_no_lingering_locks()

    # Remaining share is exactly what the winner left (no double counting, no lost update).
    assert _record(seller_user, order, Decimal("832.01"))().json()["code"] == "SELLER_REFUND_LIMIT_EXCEEDED"
    assert _record(seller_user, order, Decimal("832.00"))().status_code == status.HTTP_201_CREATED


def test_pg_same_seller_concurrent_platform_refund_requests_cannot_exceed_share(multi_seller_order, seller_user):
    """Seller-initiated platform refund path (create_refund with enforce_seller_share=True)."""
    order = _mark_paid_online(multi_seller_order[0])
    seller_user.add_role(RoleChoices.ADMIN)  # holds order.refund, and still sells item A (as in the ENG-05a suite)
    audit_before = AuditLog.objects.filter(event_type="marketplace.refund.created").count()
    gate = LockContentionGate()
    with gate.install():
        results = run_concurrently(
            [("first", _platform_request(seller_user, order, Decimal("2000.00"))),
             ("second", _platform_request(seller_user, order, Decimal("2000.00")))],
            gate,
        )
    gate.assert_contention_observed()

    winners, losers = _split(results)
    assert len(winners) == 1 and len(losers) == 1, results
    assert next(iter(winners.values()))["body"]["refund"]["status"] == RefundStatusChoices.PENDING
    loser = next(iter(losers.values()))
    assert loser["status"] == status.HTTP_400_BAD_REQUEST
    assert loser["body"]["code"] == "SELLER_REFUND_LIMIT_EXCEEDED"
    assert Refund.objects.filter(order=order).count() == 1
    assert AuditLog.objects.filter(event_type="marketplace.refund.created").count() == audit_before + 1
    _assert_no_lingering_locks()


# =============================================================================
# 3. Overall order refundable balance under concurrency (admin path unchanged: no seller-share limit)
# =============================================================================

def test_pg_two_admin_refunds_cannot_exceed_order_balance(multi_seller_order, admin_user):
    order = _mark_paid_online(multi_seller_order[0])
    amount = Decimal("3000.00")  # larger than either seller's share: admin refunds are not share-limited
    gate = LockContentionGate()
    with gate.install():
        results = run_concurrently(
            [("first", _admin_refund(admin_user, order, amount)), ("second", _admin_refund(admin_user, order, amount))],
            gate,
        )
    gate.assert_contention_observed()

    winners, losers = _split(results)
    assert len(winners) == 1 and len(losers) == 1, results
    loser = next(iter(losers.values()))
    assert loser["status"] == status.HTTP_400_BAD_REQUEST
    assert ORDER_BALANCE_MSG in loser["body"]["error"]
    assert "INR 2192.00" in loser["body"]["error"]
    refunds = _active_refunds(order)
    assert [r.amount for r in refunds] == [amount]
    _assert_no_lingering_locks()


@pytest.mark.parametrize("first", ["admin", "seller_b"])
def test_pg_admin_full_refund_and_seller_refund_cannot_exceed_order_balance(
        multi_seller_order, admin_user, seller_b, first):
    order = _mark_paid_online(multi_seller_order[0])
    gate = LockContentionGate()
    with gate.install():
        results = run_concurrently(
            [("admin", _admin_refund(admin_user, order, ORDER_TOTAL)), ("seller_b", _record(seller_b, order, SHARE_B))],
            gate, first_label=first,
        )
    gate.assert_contention_observed()

    loser_label = "seller_b" if first == "admin" else "admin"
    assert results[first]["status"] == status.HTTP_201_CREATED, results
    assert results[loser_label]["status"] == status.HTTP_400_BAD_REQUEST, results
    assert ORDER_BALANCE_MSG in results[loser_label]["body"]["error"]
    assert "code" not in results[loser_label]["body"]  # existing order-level rule, unchanged message shape
    refunds = _active_refunds(order)
    assert len(refunds) == 1
    assert sum(r.amount for r in refunds) <= ORDER_TOTAL
    _assert_no_lingering_locks()


# =============================================================================
# 4. Dispute refunds (admin path) racing a seller refund
# =============================================================================

@pytest.mark.parametrize("first", ["dispute_admin", "seller_b"])
def test_pg_dispute_refund_racing_seller_refund(multi_seller_order, admin_user, buyer_user, seller_b, first):
    order = _mark_paid_online(multi_seller_order[0])
    dispute = Dispute.objects.create(
        dispute_number=f"DISP-PG-{uuid.uuid4().hex[:8].upper()}", order=order, buyer=buyer_user, seller=seller_b,
        description="Item B not as described.",
    )
    gate = LockContentionGate()
    with gate.install():
        results = run_concurrently(
            [("dispute_admin", _admin_refund(admin_user, order, SHARE_B, dispute=dispute)),
             ("seller_b", _record(seller_b, order, SHARE_B))],
            gate, first_label=first,
        )
    gate.assert_contention_observed()

    refunds = _active_refunds(order)
    assert sum(r.amount for r in refunds) <= ORDER_TOTAL
    if first == "dispute_admin":
        # The committed dispute refund is attributed to seller B (dispute.seller), consuming B's share.
        assert results["dispute_admin"]["status"] == status.HTTP_201_CREATED, results
        assert results["seller_b"]["status"] == status.HTTP_400_BAD_REQUEST, results
        assert results["seller_b"]["body"]["code"] == "SELLER_REFUND_LIMIT_EXCEEDED"
        assert [(r.dispute_id, r.amount) for r in refunds] == [(dispute.id, SHARE_B)]
    else:
        # Existing admin/dispute behaviour is unchanged: only the order-level balance applies to the admin.
        assert results["seller_b"]["status"] == status.HTTP_201_CREATED, results
        assert results["dispute_admin"]["status"] == status.HTTP_201_CREATED, results
        assert sorted(r.amount for r in refunds) == [SHARE_B, SHARE_B]
    _assert_no_lingering_locks()


# =============================================================================
# 5. Single-seller orders: existing order-level behaviour under concurrency
# =============================================================================

def test_pg_single_seller_concurrent_refunds_cannot_exceed_order_balance(multi_seller_order, buyer_user,
                                                                        seller_user):
    _, item_a, _ = multi_seller_order
    order = _single_seller_order(buyer_user, item_a.listing, quantity=2)  # online PAID, total 2832.00
    amount = (order.total_amount * Decimal("0.6")).quantize(Decimal("0.01"))
    gate = LockContentionGate()
    with gate.install():
        results = run_concurrently(
            [("first", _record(seller_user, order, amount)), ("second", _record(seller_user, order, amount))],
            gate,
        )
    gate.assert_contention_observed()

    winners, losers = _split(results)
    assert len(winners) == 1 and len(losers) == 1, results
    loser = next(iter(losers.values()))
    assert loser["status"] == status.HTTP_400_BAD_REQUEST
    assert ORDER_BALANCE_MSG in loser["body"]["error"]
    assert "code" not in loser["body"]  # seller-share check is not involved on single-seller orders
    assert [r.amount for r in _active_refunds(order)] == [amount]
    _assert_no_lingering_locks()


# =============================================================================
# 6. G17a — Stripe chargeback intake racing refund actions (genuine concurrency)
# =============================================================================


def _webhook(body):
    return lambda: post_event(body)


def _gbp_paid_order(multi_seller_order, buyer_user):
    _, item_a, _ = multi_seller_order
    return _gbp_single_seller_order(buyer_user, item_a.listing, quantity=2)


def test_pg_refund_commits_before_concurrent_chargeback_intake(multi_seller_order, buyer_user, admin_user):
    """Refund holds the order lock; the dispute webhook waits on it, then records the chargeback afterwards."""
    order = _gbp_paid_order(multi_seller_order, buyer_user)
    body = dispute_event(order.payment_reference, "needs_response")
    gate = LockContentionGate()
    with gate.install():
        results = run_concurrently(
            [("refund", _admin_refund(admin_user, order, Decimal("10.00"))), ("webhook", _webhook(body))],
            gate, first_label="refund",
        )
    gate.assert_contention_observed()

    assert results["refund"]["status"] == status.HTTP_201_CREATED, results
    assert results["webhook"]["status"] == status.HTTP_200_OK, results
    assert Refund.objects.filter(order=order).count() == 1
    assert chargebacks.blocking_disputes(order)[0]["dispute_id"] == "dp_test_1"
    # From now on the guard applies.
    after = _admin_refund(admin_user, order, Decimal("10.00"))()
    assert after.status_code == 400 and after.json()["code"] == "CHARGEBACK_OPEN"
    _assert_no_lingering_locks()


def test_pg_refund_waiting_on_chargeback_intake_is_refused(multi_seller_order, buyer_user, admin_user):
    """Dispute webhook holds the order lock; the refund waits, then sees the committed chargeback and is refused."""
    order = _gbp_paid_order(multi_seller_order, buyer_user)
    body = dispute_event(order.payment_reference, "needs_response")
    gate = LockContentionGate()
    with gate.install_on_function(chargebacks, "record_dispute_event"):
        results = run_concurrently(
            [("webhook", _webhook(body)), ("refund", _admin_refund(admin_user, order, Decimal("10.00")))],
            gate, first_label="webhook",
        )
    gate.assert_contention_observed()

    assert results["webhook"]["status"] == status.HTTP_200_OK, results
    assert results["refund"]["status"] == status.HTTP_400_BAD_REQUEST, results
    assert results["refund"]["body"]["code"] == "CHARGEBACK_OPEN"
    assert Refund.objects.filter(order=order).count() == 0
    # Denied entries are committed on an independent connection, so scope to this order.
    denied = AuditLog.objects.filter(reason_code="CHARGEBACK_OPEN", action="marketplace:refund.create",
                                     metadata__order_number=order.order_number)
    assert denied.count() == 1 and denied.get().status == AuditLog.STATUS_DENIED  # survived the rollback
    _assert_no_lingering_locks()


def test_pg_pending_refund_approval_waiting_on_chargeback_intake_is_refused(multi_seller_order, buyer_user,
                                                                            admin_user):
    """Decision 2 under concurrency: approval of a pre-existing pending refund queues behind the intake, is refused,
    and leaves the refund exactly as it was."""
    order = _gbp_paid_order(multi_seller_order, buyer_user)
    pending = RefundService.create_refund(order=order, amount=Decimal("20.00"), reason="Pre-dispute",
                                          actor=admin_user)
    before = (pending.status, pending.approved_by_id, pending.notes)
    body = dispute_event(order.payment_reference, "needs_response")

    def approve():
        return _client_for(admin_user).post(f"/api/v1/marketplace/admin/refunds/{pending.id}/approve/", {},
                                            format="json")

    gate = LockContentionGate()
    with gate.install_on_function(chargebacks, "record_dispute_event"):
        results = run_concurrently([("webhook", _webhook(body)), ("approve", approve)], gate, first_label="webhook")
    gate.assert_contention_observed()

    assert results["approve"]["status"] == status.HTTP_400_BAD_REQUEST, results
    assert results["approve"]["body"]["code"] == "CHARGEBACK_OPEN"
    pending.refresh_from_db()
    assert (pending.status, pending.approved_by_id, pending.notes) == before
    assert pending.status == RefundStatusChoices.PENDING
    _assert_no_lingering_locks()


def test_pg_concurrent_duplicate_dispute_delivery_is_recorded_once(multi_seller_order, buyer_user):
    """The same Stripe event delivered twice at once: the second insert waits on the unique event_id, then replays."""
    order = _gbp_paid_order(multi_seller_order, buyer_user)
    body = dispute_event(order.payment_reference, "needs_response", event_id="evt_pg_dup_1")
    table = PaymentWebhookEvent._meta.db_table
    gate = LockContentionGate()
    with gate.install_on_function(chargebacks, "record_dispute_event"):
        results = run_concurrently([("first", _webhook(body)), ("second", _webhook(body))], gate,
                                   first_label="first")
    gate.assert_contention_observed(table=table, query_prefix=f'INSERT INTO "{table}"',
                                    relation_lock="RowExclusiveLock")

    assert results["first"]["status"] == results["second"]["status"] == status.HTTP_200_OK, results
    assert results["second"]["body"]["status"] == "already_processed", results
    assert PaymentWebhookEvent.objects.filter(event_id="evt_pg_dup_1").count() == 1
    assert AuditLog.objects.filter(event_type="marketplace.payment.chargeback_opened",
                                   resource_id=str(order.id)).count() == 1
    _assert_no_lingering_locks()
