"""Country / corridor activation gates (§9 activation bundle, §21 country gate state machine, §22, COM-008).

Every gate starts DESIGNED (closed). Only ENABLED is open. A missing gate is treated as closed:
there is no default-permissive market.
"""

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from platform_core.events.outbox import emit_event

from ..choices import (
    GATE_ACTIVATION_SEQUENCE,
    GateCapabilityChoices,
    GateStatusChoices as G,
    RoleProfileStatusChoices,
)
from ..errors import CommercialRuleViolation
from ..models import CountryGate, CountryGateTransition, PartyRoleProfile
from ..money import normalize_currency
from .common import audit, normalize_country, require_text

EVIDENCE_REQUIRED_STEPS = {G.LEGALLY_REVIEWED, G.PARTNER_VERIFIED, G.FINANCE_SIGNED, G.TECHNICAL_REHEARSED}
CONFIG_FIELDS = ('allowed_currencies', 'tax_schedule_reference', 'notes')


def allowed_transitions(status: str) -> set:
    allowed = set()
    if status in GATE_ACTIVATION_SEQUENCE[:-1]:
        allowed.add(GATE_ACTIVATION_SEQUENCE[GATE_ACTIVATION_SEQUENCE.index(status) + 1])
    if status == G.ENABLED:
        allowed.add(G.SUSPENDED)
    if status == G.SUSPENDED:
        allowed.add(G.ENABLED)
    if status != G.WITHDRAWN:
        allowed.add(G.WITHDRAWN)
    else:
        allowed.add(G.DESIGNED)
    return allowed


def _normalize_currencies(values) -> list:
    if values is None:
        return []
    if not isinstance(values, (list, tuple)):
        raise CommercialRuleViolation('INVALID_CURRENCIES', 'allowed_currencies must be a list of ISO 4217 codes.', 400)
    normalized = []
    for value in values:
        code = normalize_currency(value)
        if code not in normalized:
            normalized.append(code)
    return normalized


def create_gate(data: dict, actor) -> CountryGate:
    country = normalize_country(data.get('country_code'))
    vertical = data.get('vertical')
    capability = data.get('capability')
    if CountryGate.objects.filter(country_code=country, vertical=vertical, capability=capability).exists():
        raise CommercialRuleViolation(
            'GATE_EXISTS', f"A gate for {country}/{vertical}/{capability} already exists.",
        )
    with transaction.atomic():
        gate = CountryGate.objects.create(
            country_code=country,
            vertical=vertical,
            capability=capability,
            status=G.DESIGNED,  # always closed on creation
            allowed_currencies=_normalize_currencies(data.get('allowed_currencies')),
            tax_schedule_reference=(data.get('tax_schedule_reference') or '').strip(),
            notes=data.get('notes') or '',
            created_by=actor,
        )
        audit(actor, 'commercial.gate.created', 'commercial:gate.create', 'CountryGate', gate.id,
              {'country_code': country, 'vertical': vertical, 'capability': capability})
    return gate


def update_gate_config(gate: CountryGate, data: dict, actor) -> CountryGate:
    with transaction.atomic():
        gate = CountryGate.objects.select_for_update().get(pk=gate.pk)
        if gate.status == G.ENABLED:
            raise CommercialRuleViolation(
                'GATE_OPEN', 'An enabled gate cannot be reconfigured; suspend it first.',
            )
        changed = []
        if 'allowed_currencies' in data:
            gate.allowed_currencies = _normalize_currencies(data['allowed_currencies'])
            changed.append('allowed_currencies')
        if 'tax_schedule_reference' in data:
            gate.tax_schedule_reference = (data['tax_schedule_reference'] or '').strip()
            changed.append('tax_schedule_reference')
        if 'notes' in data:
            gate.notes = data['notes'] or ''
            changed.append('notes')
        if changed:
            gate.save()
            audit(actor, 'commercial.gate.configured', 'commercial:gate.configure', 'CountryGate', gate.id,
                  {'fields': changed})
    return gate


def _approved_role_profile_exists(gate: CountryGate) -> bool:
    now = timezone.now()
    return PartyRoleProfile.objects.filter(
        country_code=gate.country_code,
        vertical=gate.vertical,
        status=RoleProfileStatusChoices.APPROVED,
        effective_from__lte=now,
    ).filter(Q(effective_to__isnull=True) | Q(effective_to__gt=now)).exists()


def _check_can_enable(gate: CountryGate, actor):
    if gate.is_regulated:
        raise CommercialRuleViolation(
            'REGULATED_GATE_LOCKED',
            'Regulated finance/insurance gates cannot be enabled in R1 (D06: recommended hold).',
        )
    if not gate.tax_schedule_reference:
        raise CommercialRuleViolation(
            'TAX_SCHEDULE_MISSING', 'A signed tax/role schedule reference is required before enabling a market.',
        )
    if not gate.allowed_currencies:
        raise CommercialRuleViolation(
            'CURRENCY_NOT_CONFIGURED', 'At least one ISO 4217 currency must be configured before enabling.',
        )
    if gate.capability != GateCapabilityChoices.DISCOVERY and not _approved_role_profile_exists(gate):
        raise CommercialRuleViolation(
            'COMMERCIAL_ROLE_MISSING',
            f'An approved, effective party role profile for {gate.country_code}/{gate.vertical} is required.',
        )
    finance_signoff = gate.transitions.filter(to_status=G.FINANCE_SIGNED).order_by('-created_at').first()
    if finance_signoff is None:
        raise CommercialRuleViolation('FINANCE_SIGNOFF_MISSING', 'The gate has no finance sign-off on record.')
    if finance_signoff.actor_id == actor.id:
        raise CommercialRuleViolation(
            'SEPARATION_OF_DUTIES', 'The person who recorded finance sign-off cannot also enable the gate.',
        )


def transition_gate(gate: CountryGate, to_status: str, actor, reason: str, evidence_reference: str = '') -> CountryGate:
    reason = require_text(reason, 'REASON_REQUIRED', 'A reason is required for every gate transition.')
    evidence_reference = (evidence_reference or '').strip()
    with transaction.atomic():
        gate = CountryGate.objects.select_for_update().get(pk=gate.pk)
        if to_status not in allowed_transitions(gate.status):
            raise CommercialRuleViolation(
                'INVALID_TRANSITION', f'Gate cannot move from {gate.status} to {to_status}.',
            )
        if to_status in EVIDENCE_REQUIRED_STEPS and not evidence_reference:
            raise CommercialRuleViolation(
                'EVIDENCE_REQUIRED', f'Moving to {to_status} requires an evidence reference (memo, contract or test record).',
                status_code=400,
            )
        if to_status == G.ENABLED:
            _check_can_enable(gate, actor)

        previous = gate.status
        gate.status = to_status
        gate.version += 1
        gate.save(update_fields=['status', 'version', 'updated_at'])
        CountryGateTransition.objects.create(
            gate=gate, from_status=previous, to_status=to_status, version_after=gate.version,
            actor=actor, reason=reason, evidence_reference=evidence_reference,
        )

        payload = {'country_code': gate.country_code, 'vertical': gate.vertical, 'capability': gate.capability,
                   'from': previous, 'to': to_status, 'version': gate.version}
        audit(actor, 'commercial.gate.transitioned', 'commercial:gate.transition', 'CountryGate', gate.id,
              {**payload, 'reason': reason, 'evidence_reference': evidence_reference})
        emit_event('compliance.policy_changed', aggregate_type='CountryGate', aggregate_id=gate.id,
                   payload=payload, idempotency_key=f'compliance.policy_changed:{gate.id}:{gate.version}',
                   actor_id=actor.id)
        if to_status in (G.SUSPENDED, G.WITHDRAWN):
            emit_event('eligibility.suspended', aggregate_type='CountryGate', aggregate_id=gate.id,
                       payload=payload, idempotency_key=f'eligibility.suspended:{gate.id}:{gate.version}',
                       actor_id=actor.id)
    return gate


def get_open_gate(country_code: str, vertical: str, capability: str) -> CountryGate:
    """Return the ENABLED gate for this scope or raise COUNTRY_GATE_CLOSED (absent gates are closed)."""
    gate = CountryGate.objects.filter(country_code=country_code, vertical=vertical, capability=capability).first()
    if gate is None or not gate.is_open:
        state = gate.status if gate else 'NOT_CONFIGURED'
        raise CommercialRuleViolation(
            'COUNTRY_GATE_CLOSED',
            f'{country_code}/{vertical}/{capability} is not activated (gate status: {state}).',
        )
    return gate


def is_gate_open(country_code: str, vertical: str, capability: str) -> bool:
    return CountryGate.objects.filter(
        country_code=country_code, vertical=vertical, capability=capability, status=G.ENABLED,
    ).exists()
