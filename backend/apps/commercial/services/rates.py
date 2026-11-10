"""Effective-dated rate schedules and fee calculation (§7 versioned precedence, §21 rate_schedule).

Resolution scope: SKU (approved version) × country × vertical × currency × payer role × plan.
Highest priority wins; an exact plan match beats a plan-agnostic schedule at the same priority;
an unresolved tie is an error rather than a silent choice.
"""

from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from platform_core.events.outbox import emit_event

from ..choices import (
    CatalogueStatusChoices as Status,
    FLAT_FEE_BASES,
    FeeBasisChoices,
    QUOTABLE_FEE_BASES,
)
from ..errors import CommercialRuleViolation
from ..models import RateSchedule
from ..money import apply_basis_points, clamp_fee, normalize_currency
from .common import audit, normalize_country, require_text

APPROVAL_CLOCK_SKEW = timedelta(seconds=60)
EDITABLE_STATUSES = {Status.DRAFT, Status.ILLUSTRATIVE}
RATE_EDITABLE_FIELDS = (
    'name', 'country_code', 'vertical', 'currency', 'payer_role', 'plan_code', 'priority', 'effective_from',
    'effective_to', 'flat_amount_minor', 'percentage_bps', 'min_fee_minor', 'max_fee_minor',
)
RATE_TRANSITIONS = {
    Status.DRAFT: {Status.ILLUSTRATIVE, Status.APPROVED, Status.RETIRED},
    Status.ILLUSTRATIVE: {Status.DRAFT, Status.APPROVED, Status.RETIRED},
    Status.APPROVED: {Status.RETIRED},
    Status.RETIRED: set(),
}


def _validate_rate(schedule: RateSchedule):
    sku = schedule.sku
    if sku.fee_basis not in QUOTABLE_FEE_BASES:
        raise CommercialRuleViolation(
            'FEE_BASIS_NOT_QUOTABLE', f'{sku.fee_basis} SKUs are priced by contract/usage and are not rate-scheduled in R1.', 400,
        )
    if schedule.vertical != sku.vertical:
        raise CommercialRuleViolation('VERTICAL_MISMATCH', 'Rate schedule vertical must match the SKU vertical.', 400)
    schedule.country_code = normalize_country(schedule.country_code)
    schedule.currency = normalize_currency(schedule.currency)
    schedule.plan_code = (schedule.plan_code or '').strip().upper()
    if schedule.effective_from is None:
        raise CommercialRuleViolation('EFFECTIVE_FROM_REQUIRED', 'effective_from is required.', 400)
    if schedule.effective_to is not None and schedule.effective_to <= schedule.effective_from:
        raise CommercialRuleViolation('INVALID_EFFECTIVE_WINDOW', 'effective_to must be after effective_from.', 400)
    if sku.fee_basis == FeeBasisChoices.PERCENT_OF_BASE:
        if schedule.percentage_bps is None:
            raise CommercialRuleViolation('PERCENTAGE_REQUIRED', 'Percentage SKUs require percentage_bps.', 400)
        if schedule.flat_amount_minor is not None:
            raise CommercialRuleViolation('AMBIGUOUS_RATE', 'Use either a percentage or a flat amount, not both.', 400)
    elif sku.fee_basis in FLAT_FEE_BASES:
        if schedule.flat_amount_minor is None:
            raise CommercialRuleViolation('FLAT_AMOUNT_REQUIRED', 'Flat-fee SKUs require flat_amount_minor.', 400)
        if schedule.percentage_bps is not None:
            raise CommercialRuleViolation('AMBIGUOUS_RATE', 'Use either a percentage or a flat amount, not both.', 400)
    for field in ('flat_amount_minor', 'min_fee_minor', 'max_fee_minor'):
        value = getattr(schedule, field)
        if value is not None and value < 0:
            raise CommercialRuleViolation('NEGATIVE_AMOUNT', f'{field} cannot be negative.', 400)
    if schedule.percentage_bps is not None and not 0 <= schedule.percentage_bps <= 10_000:
        raise CommercialRuleViolation('INVALID_PERCENTAGE', 'percentage_bps must be between 0 and 10000.', 400)
    if (schedule.min_fee_minor is not None and schedule.max_fee_minor is not None
            and schedule.min_fee_minor > schedule.max_fee_minor):
        raise CommercialRuleViolation('INVALID_FEE_BOUNDS', 'min_fee_minor cannot exceed max_fee_minor.', 400)


def create_rate(sku, data: dict, actor) -> RateSchedule:
    if sku.status == Status.RETIRED:
        raise CommercialRuleViolation('SKU_RETIRED', f'{sku.sku_code} v{sku.version} is retired.')
    schedule = RateSchedule(sku=sku, status=Status.DRAFT, created_by=actor)
    for field in RATE_EDITABLE_FIELDS:
        if field in data:
            setattr(schedule, field, data[field])
    if 'vertical' not in data:
        schedule.vertical = sku.vertical
    _validate_rate(schedule)
    with transaction.atomic():
        schedule.save()
        audit(actor, 'commercial.rate_schedule.created', 'commercial:rate.create', 'RateSchedule', schedule.id,
              {'sku_code': sku.sku_code, 'sku_version': sku.version, 'country_code': schedule.country_code,
               'currency': schedule.currency})
    return schedule


def update_rate(schedule: RateSchedule, data: dict, actor) -> RateSchedule:
    with transaction.atomic():
        schedule = RateSchedule.objects.select_for_update().select_related('sku').get(pk=schedule.pk)
        if schedule.status not in EDITABLE_STATUSES:
            raise CommercialRuleViolation(
                'RATE_FROZEN', f'Rate schedule is {schedule.status}; approved rates are never edited retroactively.',
            )
        for field in RATE_EDITABLE_FIELDS:
            if field in data:
                setattr(schedule, field, data[field])
        _validate_rate(schedule)
        schedule.save()
        audit(actor, 'commercial.rate_schedule.updated', 'commercial:rate.update', 'RateSchedule', schedule.id, {})
    return schedule


def _overlapping_approved(schedule: RateSchedule):
    qs = RateSchedule.objects.filter(
        sku=schedule.sku, country_code=schedule.country_code, vertical=schedule.vertical,
        currency=schedule.currency, payer_role=schedule.payer_role, plan_code=schedule.plan_code,
        priority=schedule.priority, status=Status.APPROVED,
    ).exclude(pk=schedule.pk)
    if schedule.effective_to is not None:
        qs = qs.filter(effective_from__lt=schedule.effective_to)
    return qs.filter(Q(effective_to__isnull=True) | Q(effective_to__gt=schedule.effective_from))


def transition_rate(schedule: RateSchedule, to_status: str, actor, reason: str, approval_reference: str = '') -> RateSchedule:
    reason = require_text(reason, 'REASON_REQUIRED', 'A reason is required for every rate status change.')
    with transaction.atomic():
        schedule = RateSchedule.objects.select_for_update().select_related('sku').get(pk=schedule.pk)
        if to_status not in RATE_TRANSITIONS.get(schedule.status, set()):
            raise CommercialRuleViolation('INVALID_TRANSITION', f'Rate cannot move from {schedule.status} to {to_status}.')
        if to_status == Status.APPROVED:
            sku = schedule.sku
            if sku.is_regulated:
                raise CommercialRuleViolation('REGULATED_SKU_BLOCKED', 'Rates for regulated/gated SKUs cannot be approved.')
            if sku.status != Status.APPROVED:
                raise CommercialRuleViolation(
                    'SKU_NOT_APPROVED', f'{sku.sku_code} v{sku.version} must be APPROVED before its rates can be approved.',
                )
            if schedule.created_by_id and schedule.created_by_id == actor.id:
                raise CommercialRuleViolation('SEPARATION_OF_DUTIES', 'The rate author cannot approve their own rate.')
            if schedule.effective_from < timezone.now() - APPROVAL_CLOCK_SKEW:
                raise CommercialRuleViolation(
                    'RETROACTIVE_RATE', 'Rate changes are prospective only; effective_from cannot be in the past.',
                )
            if _overlapping_approved(schedule).exists():
                raise CommercialRuleViolation(
                    'RATE_OVERLAP', 'An approved rate with the same scope and priority overlaps this effective window.',
                )
            schedule.approval_reference = require_text(
                approval_reference, 'APPROVAL_REFERENCE_REQUIRED', 'Approval requires a CFO approval reference.',
            )
            schedule.approved_by = actor
            schedule.approved_at = timezone.now()
        previous_status = schedule.status
        schedule.status = to_status
        schedule.status_reason = reason
        schedule.save()
        audit(actor, f'commercial.rate_schedule.{to_status.lower()}', 'commercial:rate.transition', 'RateSchedule',
              schedule.id, {'from': previous_status, 'to': to_status, 'reason': reason,
                            'approval_reference': schedule.approval_reference})
        if to_status in (Status.APPROVED, Status.RETIRED):
            topic = f'commercial.rate_schedule.{to_status.lower()}'
            emit_event(topic, aggregate_type='RateSchedule', aggregate_id=schedule.id,
                       payload={'sku_code': schedule.sku.sku_code, 'sku_version': schedule.sku.version,
                                'country_code': schedule.country_code, 'currency': schedule.currency,
                                'effective_from': schedule.effective_from.isoformat()},
                       idempotency_key=f'{topic}:{schedule.id}', actor_id=actor.id)
    return schedule


def resolve_rate(sku, *, country_code, vertical, currency, payer_role, plan_code='', at=None,
                 statuses=(Status.APPROVED,)) -> RateSchedule:
    at = at or timezone.now()
    plan_code = (plan_code or '').strip().upper()
    candidates = list(
        RateSchedule.objects.filter(
            sku=sku, country_code=country_code, vertical=vertical, currency=currency, payer_role=payer_role,
            status__in=statuses, effective_from__lte=at,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gt=at))
        .filter(Q(plan_code='') | Q(plan_code=plan_code))
    )
    if not candidates:
        raise CommercialRuleViolation(
            'RATE_NOT_FOUND',
            f'No {"/".join(statuses)} rate for {sku.sku_code} v{sku.version} in {country_code}/{currency} '
            f'for payer {payer_role}{" plan " + plan_code if plan_code else ""}.',
        )

    def rank(s):
        return (s.priority, 1 if s.plan_code else 0)

    candidates.sort(key=lambda s: (rank(s), s.effective_from), reverse=True)
    if len(candidates) > 1 and rank(candidates[0]) == rank(candidates[1]):
        raise CommercialRuleViolation(
            'RATE_AMBIGUOUS', f'Multiple rates for {sku.sku_code} share the top priority; set an explicit priority.',
        )
    return candidates[0]


def calculate_fee(schedule: RateSchedule, *, quantity: int, commissionable_base_minor: int) -> int:
    basis = schedule.sku.fee_basis
    if basis == FeeBasisChoices.PERCENT_OF_BASE:
        fee = apply_basis_points(commissionable_base_minor, schedule.percentage_bps)
    elif basis in FLAT_FEE_BASES:
        fee = schedule.flat_amount_minor * quantity
    else:
        raise CommercialRuleViolation('FEE_BASIS_NOT_QUOTABLE', f'{basis} cannot be quoted in R1.')
    return clamp_fee(fee, schedule.min_fee_minor, schedule.max_fee_minor)
