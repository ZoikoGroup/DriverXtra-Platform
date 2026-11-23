"""G17a — Stripe chargeback (dispute) intake: recorded exception only, no money movement.

Stripe ``charge.dispute.*`` webhooks are already stored and deduplicated by ``PaymentService.process_webhook``
(``PaymentWebhookEvent``, unique ``event_id``). This module:

* links a dispute event to an existing order via ``payment_intent`` -> ``Order.payment_reference``
  (fallback: ``PaymentTransaction.provider_order_id``); zero or several matches are recorded as *unmatched*;
* records each lifecycle event as an internal audit entry (dispute ID, amount in minor units, currency, reason,
  status, evidence deadline, outcome and separately reported balance transactions — never netted);
* derives each dispute's state from the stored, processed webhook events of the order, for the refund guard.

It never moves money, submits evidence, holds payouts, allocates losses, writes ledger journals, changes order or
payment status, or notifies buyers/sellers (no notification resolver exists for these audit event types).

Refund guard policy (G17a decisions, 2026-11-20):
* inquiry (``warning_*``)            -> recorded, refunds NOT blocked (a refund may prevent escalation);
* open chargeback (any other status) -> new refunds, approval and dispatch blocked (``CHARGEBACK_OPEN``);
* lost                               -> stays blocked (``CHARGEBACK_LOST``) pending authorised financial resolution;
* won                                -> block lifted.
``won``/``lost`` are final in Stripe, so a late-delivered earlier event cannot reopen a closed dispute. Otherwise the
event with the latest Stripe ``created`` timestamp decides; on a tie the more restrictive state wins (fail closed).
"""

from datetime import datetime, timezone as dt_timezone
from typing import Any, Dict, List, Optional, Tuple

from django.core.exceptions import ValidationError as DjangoValidationError

from platform_core.audit.writer import record_audit_entry

DISPUTE_EVENT_PREFIX = 'charge.dispute.'
PROVIDER = 'STRIPE'

STATE_INQUIRY = 'INQUIRY'
STATE_OPEN = 'OPEN'
STATE_WON = 'WON'
STATE_LOST = 'LOST'
STATE_INQUIRY_CLOSED = 'INQUIRY_CLOSED'

BLOCKING_STATES = {STATE_OPEN: 'CHARGEBACK_OPEN', STATE_LOST: 'CHARGEBACK_LOST'}
_RESTRICTIVENESS = {STATE_INQUIRY_CLOSED: 0, STATE_WON: 0, STATE_INQUIRY: 1, STATE_OPEN: 2, STATE_LOST: 3}

UNMATCHED_NOT_FOUND = 'NOT_FOUND'
UNMATCHED_AMBIGUOUS = 'AMBIGUOUS'
UNMATCHED_NO_PAYMENT_INTENT = 'NO_PAYMENT_INTENT'


class ChargebackRefundBlocked(DjangoValidationError):
    """Raised by refund paths while a Stripe chargeback blocks refunds on the order (HTTP 400 + code)."""

    def __init__(self, code: str, message: str, disputes: List[Dict[str, Any]]):
        super().__init__(message, code=code)
        self.disputes = disputes


def is_dispute_event(provider_name: str, event_type: Optional[str]) -> bool:
    return provider_name == PROVIDER and bool(event_type) and event_type.startswith(DISPUTE_EVENT_PREFIX)


def classify_status(status: Optional[str]) -> str:
    """Map a Stripe dispute status to a G17a state. Unknown statuses fail closed as OPEN."""
    status = (status or '').strip().lower()
    if status == 'won':
        return STATE_WON
    if status == 'lost':
        return STATE_LOST
    if status == 'warning_closed':
        return STATE_INQUIRY_CLOSED
    if status.startswith('warning_'):
        return STATE_INQUIRY
    return STATE_OPEN  # needs_response, under_review, and any unrecognised status


def _iso_from_epoch(value: Any) -> Optional[str]:
    try:
        return datetime.fromtimestamp(int(value), tz=dt_timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def parse_dispute_event(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the recorded fields from a Stripe dispute event. Values are recorded as reported (no netting)."""
    obj = (payload.get('data') or {}).get('object') or {}
    evidence = obj.get('evidence_details') or {}
    balance_transactions = []
    for txn in obj.get('balance_transactions') or []:
        if not isinstance(txn, dict):
            continue
        balance_transactions.append({
            "id": txn.get('id'),
            "amount_minor": txn.get('amount'),
            "fee_minor": txn.get('fee'),
            "fee_details": [
                {"amount_minor": fd.get('amount'), "currency": (fd.get('currency') or '').upper(),
                 "type": fd.get('type'), "description": fd.get('description')}
                for fd in (txn.get('fee_details') or []) if isinstance(fd, dict)
            ],
            "currency": (txn.get('currency') or '').upper(),
            "reporting_category": txn.get('reporting_category'),
        })
    status = obj.get('status')
    state = classify_status(status)
    return {
        "dispute_id": obj.get('id'),
        "payment_intent": obj.get('payment_intent'),
        "charge": obj.get('charge'),
        "amount_minor": obj.get('amount'),
        "currency": (obj.get('currency') or '').upper(),
        "reason": obj.get('reason'),
        "status": status,
        "state": state,
        "is_inquiry": state in (STATE_INQUIRY, STATE_INQUIRY_CLOSED),
        "outcome": status if state in (STATE_WON, STATE_LOST, STATE_INQUIRY_CLOSED) else None,
        "evidence_due_by": _iso_from_epoch(evidence.get('due_by')),
        "evidence_past_due": evidence.get('past_due'),
        "balance_transactions": balance_transactions,
        "livemode": payload.get('livemode'),
        "event_created": _iso_from_epoch(payload.get('created')),
    }


def resolve_order(dispute_obj: Dict[str, Any]) -> Tuple[Optional[Any], Optional[str]]:
    """Link a dispute to exactly one existing order. Returns (order, None) or (None, unmatched_reason)."""
    from apps.marketplace.models import Order, PaymentTransaction

    payment_intent = (dispute_obj or {}).get('payment_intent')
    if not payment_intent:
        return None, UNMATCHED_NO_PAYMENT_INTENT

    matches = list(Order.objects.filter(payment_reference=payment_intent).values_list('id', flat=True)[:2])
    if not matches:
        matches = list(
            PaymentTransaction.objects.filter(provider=PROVIDER, provider_order_id=payment_intent)
            .values_list('order_id', flat=True).distinct()[:2]
        )
    if len(matches) == 1:
        return Order.objects.get(id=matches[0]), None
    return None, (UNMATCHED_AMBIGUOUS if matches else UNMATCHED_NOT_FOUND)


def record_dispute_event(
    webhook_record: Any,
    locked_order: Optional[Any],
    event_type: str,
    event_id: str,
    payload: Dict[str, Any],
    unmatched_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Record one Stripe dispute lifecycle event. Must run inside the webhook transaction (order row locked)."""
    details = parse_dispute_event(payload)
    metadata = {
        "provider": PROVIDER,
        "event_id": event_id,
        "event_type": event_type,
        "webhook_event_id": str(webhook_record.id),
        **details,
    }

    if locked_order is None:
        record_audit_entry(
            event_type="marketplace.payment.chargeback_unmatched",
            action="marketplace:payment.chargeback_intake",
            resource_type="PaymentWebhookEvent",
            resource_id=str(webhook_record.id),
            actor_kind="SYSTEM",
            reason_code=unmatched_reason or UNMATCHED_NOT_FOUND,
            metadata={**metadata, "unmatched_reason": unmatched_reason or UNMATCHED_NOT_FOUND},
        )
        return metadata

    order_currency = (locked_order.currency or '').upper()
    metadata.update({
        "order_number": locked_order.order_number,
        "order_currency": order_currency,
        "currency_mismatch": bool(details["currency"]) and details["currency"] != order_currency,
    })
    suffix = event_type[len(DISPUTE_EVENT_PREFIX):] or 'updated'
    audit_suffix = {'created': 'opened'}.get(suffix, suffix)
    record_audit_entry(
        event_type=f"marketplace.payment.chargeback_{audit_suffix}",
        action="marketplace:payment.chargeback_intake",
        resource_type="Order",
        resource_id=str(locked_order.id),
        actor_kind="SYSTEM",
        metadata=metadata,
    )
    return metadata


def dispute_states(order: Any) -> List[Dict[str, Any]]:
    """Current state of every Stripe dispute recorded against ``order`` (from processed webhook events)."""
    from apps.marketplace.models import PaymentWebhookEvent

    per_dispute: Dict[str, List[Tuple[int, str, Dict[str, Any]]]] = {}
    events = PaymentWebhookEvent.objects.filter(
        order=order, provider=PROVIDER, event_type__startswith=DISPUTE_EVENT_PREFIX, processed=True,
    ).only('payload', 'event_type')
    for event in events:
        payload = event.payload or {}
        details = parse_dispute_event(payload)
        dispute_id = details["dispute_id"]
        if not dispute_id:
            continue
        try:
            created = int(payload.get('created') or 0)
        except (TypeError, ValueError):
            created = 0
        per_dispute.setdefault(dispute_id, []).append((created, details["state"], details))

    results = []
    for dispute_id, entries in per_dispute.items():
        states = {state for _, state, _ in entries}
        if STATE_LOST in states:          # final in Stripe; fail closed if both final states ever appear
            state = STATE_LOST
        elif STATE_WON in states:
            state = STATE_WON
        else:
            latest = max(created for created, _, _ in entries)
            state = max((s for c, s, _ in entries if c == latest), key=lambda s: _RESTRICTIVENESS[s])
        latest_details = max(entries, key=lambda e: (e[0], _RESTRICTIVENESS[e[1]]))[2]
        results.append({
            "dispute_id": dispute_id,
            "state": state,
            "status": latest_details["status"],
            "amount_minor": latest_details["amount_minor"],
            "currency": latest_details["currency"],
            "reason": latest_details["reason"],
            "evidence_due_by": latest_details["evidence_due_by"],
            "blocks_refunds": state in BLOCKING_STATES,
        })
    results.sort(key=lambda d: d["dispute_id"])
    return results


def blocking_disputes(order: Any) -> List[Dict[str, Any]]:
    return [d for d in dispute_states(order) if d["blocks_refunds"]]


def assert_refunds_not_blocked(order: Any, operation: str) -> None:
    """Fail closed while a Stripe chargeback blocks refunds. Call with the order row locked."""
    blocking = blocking_disputes(order)
    if not blocking:
        return
    # Messages may reach sellers, so they carry no dispute identifiers, reasons or card-network details; staff see
    # those in the refund summary and the audit trail (buyer/seller notification is deferred, REF-08).
    if any(d["state"] == STATE_LOST for d in blocking):
        code = BLOCKING_STATES[STATE_LOST]
        message = (
            f"Cannot {operation} for order {order.order_number}: a payment chargeback on this order was lost. "
            "Refunds stay blocked until authorised financial resolution. Existing refunds are preserved unchanged."
        )
    else:
        code = BLOCKING_STATES[STATE_OPEN]
        message = (
            f"Cannot {operation} for order {order.order_number}: a payment chargeback on this order is open. "
            "Existing refunds are preserved unchanged; refunds resume only if the chargeback is resolved in the "
            "merchant's favour."
        )
    raise ChargebackRefundBlocked(code, message, blocking)
