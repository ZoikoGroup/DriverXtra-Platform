"""Quote formation and immutable acceptance (§7 quote formation, §21 quote_snapshot, COM-001/002, Appendix A).

Binding quotes require: an ENABLED country gate (BINDING_QUOTE capability), an allowed currency,
an APPROVED and effective party role profile, APPROVED non-regulated SKUs, APPROVED effective
rates, and tax determination evidence. Any failure rejects the quote.

Previews run the same calculation over draft/illustrative data and return the reasons a binding
quote would be refused. Previews are never persisted and are always labelled non-binding.
"""

import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import List, Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from platform_core.events.outbox import emit_event

from ..choices import (
    CatalogueStatusChoices,
    GateCapabilityChoices,
    QuoteLineTypeChoices as LineType,
    QuoteStatusChoices,
    RoleProfileStatusChoices,
)
from ..errors import CommercialRuleViolation
from ..models import CommercialSku, CountryGate, QuoteLine, QuoteSnapshot
from ..money import currency_exponent, normalize_currency
from . import roles as role_service
from .common import audit, canonical_hash, normalize_country, require_text
from .rates import calculate_fee, resolve_rate

FEE_BASE_RULE = 'GOODS_NET_OF_DISCOUNT_EXCL_TAX_DELIVERY_V1'
MAX_FEE_ITEMS = 10
PREVIEW_RATE_STATUSES = (
    CatalogueStatusChoices.APPROVED, CatalogueStatusChoices.ILLUSTRATIVE, CatalogueStatusChoices.DRAFT,
)


def quote_ttl() -> timedelta:
    return timedelta(seconds=int(getattr(settings, 'COMMERCIAL_QUOTE_TTL_SECONDS', 1800)))


@dataclass
class FeeItem:
    sku_code: str
    payer_role: str
    quantity: int = 1
    plan_code: str = ''


@dataclass
class QuoteRequest:
    customer: object
    customer_role: str
    country_code: str
    vertical: str
    currency: str
    role_profile_code: str
    fee_items: List[FeeItem]
    terms_version: str = ''
    tax_determination_reference: str = ''
    face_value_minor: int = 0
    discount_minor: int = 0
    delivery_minor: int = 0
    tax_minor: int = 0
    organisation: Optional[object] = None
    seller_organisation: Optional[object] = None


@dataclass
class ComputedLine:
    line_type: str
    description: str
    amount_minor: int
    is_customer_payable: bool
    sku: Optional[CommercialSku] = None
    rate_schedule: Optional[object] = None
    quantity: int = 1
    payer_role: str = ''


@dataclass
class QuoteComputation:
    country_code: str
    vertical: str
    currency: str
    exponent: int
    lines: List[ComputedLine]
    face_value_minor: int
    discount_minor: int
    delivery_minor: int
    tax_minor: int
    commissionable_base_minor: int
    platform_fee_minor: int
    customer_total_minor: int
    gate: Optional[CountryGate] = None
    role_profile: Optional[object] = None
    parties: Optional[dict] = None
    blocking_reasons: List[dict] = field(default_factory=list)


def _validate_amounts(request: QuoteRequest):
    for name in ('face_value_minor', 'discount_minor', 'delivery_minor', 'tax_minor'):
        value = getattr(request, name)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise CommercialRuleViolation('INVALID_AMOUNTS', f'{name} must be a non-negative integer (minor units).', 400)
    if request.discount_minor > request.face_value_minor:
        raise CommercialRuleViolation('INVALID_AMOUNTS', 'discount_minor cannot exceed face_value_minor.', 400)
    if not request.fee_items:
        raise CommercialRuleViolation('NO_FEE_ITEMS', 'At least one commercial SKU is required.', 400)
    if len(request.fee_items) > MAX_FEE_ITEMS:
        raise CommercialRuleViolation('TOO_MANY_FEE_ITEMS', f'A quote may contain at most {MAX_FEE_ITEMS} SKUs.', 400)
    codes = [item.sku_code.strip().upper() for item in request.fee_items]
    if len(codes) != len(set(codes)):
        raise CommercialRuleViolation(
            'DUPLICATE_FEE_SKU', 'The same SKU cannot be charged twice in one quote (no undisclosed fee stacking).', 400,
        )
    for item in request.fee_items:
        if not isinstance(item.quantity, int) or item.quantity < 1:
            raise CommercialRuleViolation('INVALID_QUANTITY', 'Quantities must be positive integers.', 400)


def _resolve_sku(sku_code: str, vertical: str, binding: bool, reasons: list) -> CommercialSku:
    code = (sku_code or '').strip().upper()
    approved = CommercialSku.objects.filter(sku_code=code, status=CatalogueStatusChoices.APPROVED).order_by('-version').first()
    sku = approved
    if sku is None:
        if binding:
            raise CommercialRuleViolation('SKU_NOT_APPROVED', f'{code} has no APPROVED version; it cannot be quoted.')
        sku = (
            CommercialSku.objects.filter(sku_code=code)
            .exclude(status=CatalogueStatusChoices.RETIRED)
            .order_by('-version')
            .first()
        )
        if sku is None:
            raise CommercialRuleViolation('SKU_NOT_FOUND', f'SKU {code} does not exist.', 404)
        reasons.append({'rule': 'SKU_NOT_APPROVED', 'message': f'{code} v{sku.version} is {sku.status}.'})
    if sku.is_regulated:
        if binding:
            raise CommercialRuleViolation('REGULATED_SKU_BLOCKED', f'{code} is a regulated/gated product.')
        reasons.append({'rule': 'REGULATED_SKU_BLOCKED', 'message': f'{code} is a regulated/gated product.'})
    if sku.vertical != vertical:
        raise CommercialRuleViolation('VERTICAL_MISMATCH', f'{code} belongs to {sku.vertical}, not {vertical}.', 400)
    return sku


def compute_quote(request: QuoteRequest, *, binding: bool, at=None) -> QuoteComputation:
    at = at or timezone.now()
    reasons: list = []
    country = normalize_country(request.country_code)
    currency = normalize_currency(request.currency)
    _validate_amounts(request)

    # 1. Jurisdiction gate and currency eligibility.
    gate = None
    if binding:
        from .gates import get_open_gate
        gate = get_open_gate(country, request.vertical, GateCapabilityChoices.BINDING_QUOTE)
        if currency not in (gate.allowed_currencies or []):
            raise CommercialRuleViolation('CURRENCY_NOT_PERMITTED', f'{currency} is not permitted in {country}.')
    else:
        gate = CountryGate.objects.filter(
            country_code=country, vertical=request.vertical, capability=GateCapabilityChoices.BINDING_QUOTE,
        ).first()
        if gate is None or not gate.is_open:
            reasons.append({'rule': 'COUNTRY_GATE_CLOSED',
                            'message': f'{country}/{request.vertical} binding quotes are not activated '
                                       f'(gate: {gate.status if gate else "NOT_CONFIGURED"}).'})
        elif currency not in (gate.allowed_currencies or []):
            reasons.append({'rule': 'CURRENCY_NOT_PERMITTED', 'message': f'{currency} is not permitted in {country}.'})

    # 2. Legal role profile.
    profile = parties = None
    if binding:
        profile = role_service.resolve_profile(request.role_profile_code, country, request.vertical, at)
        parties = role_service.describe_parties(profile, request.seller_organisation)
    else:
        try:
            profile = role_service.resolve_profile(
                request.role_profile_code, country, request.vertical, at,
                statuses=(RoleProfileStatusChoices.APPROVED, RoleProfileStatusChoices.DRAFT),
            )
            if profile.status != RoleProfileStatusChoices.APPROVED:
                reasons.append({'rule': 'COMMERCIAL_ROLE_MISSING',
                                'message': f'Role profile {profile.code} v{profile.version} is {profile.status}.'})
            if profile.is_gated:
                reasons.append({'rule': 'GATED_ROLE_PROFILE', 'message': f'{profile.profile_type} is gated.'})
            parties = role_service.describe_parties(profile, request.seller_organisation)
        except CommercialRuleViolation as exc:
            reasons.append({'rule': exc.rule, 'message': exc.message})

    if binding:
        require_text(request.tax_determination_reference, 'TAX_DETERMINATION_REQUIRED',
                     'Binding quotes require tax determination evidence (tax_determination_reference).')
        require_text(request.terms_version, 'TERMS_VERSION_REQUIRED',
                     'Binding quotes require the version of the terms presented to the customer.')
    elif not (request.tax_determination_reference or '').strip():
        reasons.append({'rule': 'TAX_DETERMINATION_REQUIRED', 'message': 'No tax determination reference supplied.'})

    # 3. Face value, discount, delivery and tax lines (seller/customer amounts, not platform revenue).
    lines: List[ComputedLine] = []
    if request.face_value_minor:
        lines.append(ComputedLine(LineType.FACE_VALUE, 'Product/service face value', request.face_value_minor, True))
    if request.discount_minor:
        lines.append(ComputedLine(LineType.DISCOUNT, 'Discount', -request.discount_minor, True))
    if request.delivery_minor:
        lines.append(ComputedLine(LineType.DELIVERY, 'Delivery', request.delivery_minor, True))
    if request.tax_minor:
        lines.append(ComputedLine(LineType.TAX, 'Tax', request.tax_minor, True))

    commissionable_base = request.face_value_minor - request.discount_minor

    # 4. Platform fee lines from effective-dated rates.
    rate_statuses = (CatalogueStatusChoices.APPROVED,) if binding else PREVIEW_RATE_STATUSES
    platform_fee = 0
    customer_fees = 0
    for item in request.fee_items:
        sku = _resolve_sku(item.sku_code, request.vertical, binding, reasons)
        schedule = resolve_rate(
            sku, country_code=country, vertical=request.vertical, currency=currency,
            payer_role=item.payer_role, plan_code=item.plan_code, at=at, statuses=rate_statuses,
        )
        if not binding and schedule.status != CatalogueStatusChoices.APPROVED:
            reasons.append({'rule': 'RATE_NOT_APPROVED',
                            'message': f'Rate "{schedule.name}" is {schedule.status} (illustrative/non-binding).'})
        fee = calculate_fee(schedule, quantity=item.quantity, commissionable_base_minor=commissionable_base)
        payable = item.payer_role == request.customer_role
        lines.append(ComputedLine(
            LineType.PLATFORM_FEE, f'{sku.name} ({sku.sku_code} v{sku.version})', fee, payable,
            sku=sku, rate_schedule=schedule, quantity=item.quantity, payer_role=item.payer_role,
        ))
        platform_fee += fee
        if payable:
            customer_fees += fee

    customer_total = (
        request.face_value_minor - request.discount_minor + request.delivery_minor + request.tax_minor + customer_fees
    )
    return QuoteComputation(
        country_code=country, vertical=request.vertical, currency=currency, exponent=currency_exponent(currency),
        lines=lines, face_value_minor=request.face_value_minor, discount_minor=request.discount_minor,
        delivery_minor=request.delivery_minor, tax_minor=request.tax_minor,
        commissionable_base_minor=commissionable_base, platform_fee_minor=platform_fee,
        customer_total_minor=customer_total, gate=gate, role_profile=profile, parties=parties,
        blocking_reasons=reasons,
    )


def _terms_payload(quote_number, request, computation, issued_at, expires_at, role_hash) -> dict:
    return {
        'quote_number': quote_number,
        'customer_id': str(request.customer.id),
        'organisation_id': str(request.organisation.id) if request.organisation else None,
        'customer_role': request.customer_role,
        'country_code': computation.country_code,
        'vertical': computation.vertical,
        'currency': computation.currency,
        'currency_exponent': computation.exponent,
        'gate_id': str(computation.gate.id),
        'gate_version': computation.gate.version,
        'role_snapshot_hash': role_hash,
        'tax_determination_reference': request.tax_determination_reference.strip(),
        'terms_version': request.terms_version.strip(),
        'fee_base_rule': FEE_BASE_RULE,
        'totals': {
            'face_value_minor': computation.face_value_minor,
            'discount_minor': computation.discount_minor,
            'delivery_minor': computation.delivery_minor,
            'tax_minor': computation.tax_minor,
            'commissionable_base_minor': computation.commissionable_base_minor,
            'platform_fee_minor': computation.platform_fee_minor,
            'customer_total_minor': computation.customer_total_minor,
        },
        'lines': [
            {
                'line_type': line.line_type,
                'amount_minor': line.amount_minor,
                'is_customer_payable': line.is_customer_payable,
                'sku_code': line.sku.sku_code if line.sku else '',
                'sku_version': line.sku.version if line.sku else None,
                'rate_schedule_id': str(line.rate_schedule.id) if line.rate_schedule else None,
                'quantity': line.quantity,
                'payer_role': line.payer_role,
            }
            for line in computation.lines
        ],
        'issued_at': issued_at.isoformat(),
        'expires_at': expires_at.isoformat(),
    }


def issue_quote(request: QuoteRequest) -> QuoteSnapshot:
    issued_at = timezone.now()
    computation = compute_quote(request, binding=True, at=issued_at)
    expires_at = issued_at + quote_ttl()
    quote_number = f"DX-Q-{issued_at.strftime('%Y%m%d')}-{uuid.uuid4().hex[:10].upper()}"

    with transaction.atomic():
        role_snapshot = role_service.create_snapshot(computation.role_profile, computation.parties)
        terms_hash = canonical_hash(
            _terms_payload(quote_number, request, computation, issued_at, expires_at, role_snapshot.snapshot_hash)
        )
        quote = QuoteSnapshot.objects.create(
            quote_number=quote_number,
            customer=request.customer,
            organisation=request.organisation,
            customer_role=request.customer_role,
            country_code=computation.country_code,
            vertical=computation.vertical,
            currency=computation.currency,
            currency_exponent=computation.exponent,
            face_value_minor=computation.face_value_minor,
            discount_minor=computation.discount_minor,
            delivery_minor=computation.delivery_minor,
            tax_minor=computation.tax_minor,
            commissionable_base_minor=computation.commissionable_base_minor,
            platform_fee_minor=computation.platform_fee_minor,
            customer_total_minor=computation.customer_total_minor,
            fee_base_rule=FEE_BASE_RULE,
            gate=computation.gate,
            gate_version=computation.gate.version,
            role_snapshot=role_snapshot,
            tax_determination_reference=request.tax_determination_reference.strip(),
            terms_version=request.terms_version.strip(),
            terms_hash=terms_hash,
            expires_at=expires_at,
            created_at=issued_at,
        )
        for position, line in enumerate(computation.lines, start=1):
            QuoteLine.objects.create(
                quote=quote, position=position, line_type=line.line_type, description=line.description,
                sku_code=line.sku.sku_code if line.sku else '', sku_version=line.sku.version if line.sku else None,
                rate_schedule=line.rate_schedule, quantity=line.quantity, amount_minor=line.amount_minor,
                payer_role=line.payer_role, is_customer_payable=line.is_customer_payable,
            )
        audit(request.customer, 'commercial.quote.issued', 'commercial:quote.issue', 'QuoteSnapshot', quote.id,
              {'quote_number': quote_number, 'currency': quote.currency, 'customer_total_minor': quote.customer_total_minor})
        emit_event('quote.issued', aggregate_type='QuoteSnapshot', aggregate_id=quote.id,
                   payload={'quote_number': quote_number, 'terms_hash': terms_hash, 'currency': quote.currency,
                            'customer_total_minor': quote.customer_total_minor,
                            'platform_fee_minor': quote.platform_fee_minor},
                   idempotency_key=f'quote.issued:{quote.id}', actor_id=request.customer.id)
    return quote


def accept_quote(quote: QuoteSnapshot, actor, *, terms_hash: str, consent_notice_version: str) -> QuoteSnapshot:
    consent_notice_version = require_text(
        consent_notice_version, 'CONSENT_REQUIRED', 'Acceptance requires the consent notice version shown to the customer.',
    )
    expired = False
    with transaction.atomic():
        quote = QuoteSnapshot.objects.select_for_update().select_related('gate').get(pk=quote.pk)
        if quote.customer_id != actor.id:
            raise CommercialRuleViolation('NOT_QUOTE_OWNER', 'Only the quoted customer can accept this quote.', 403)
        if quote.status != QuoteStatusChoices.ISSUED:
            raise CommercialRuleViolation('QUOTE_NOT_OPEN', f'Quote {quote.quote_number} is {quote.status}.')
        if timezone.now() >= quote.expires_at:
            quote.status = QuoteStatusChoices.EXPIRED
            quote.save()
            expired = True
        else:
            if (terms_hash or '').strip() != quote.terms_hash:
                raise CommercialRuleViolation(
                    'TERMS_MISMATCH', 'The accepted terms do not match the issued quote; request a fresh quote.',
                )
            gate = quote.gate
            if not gate.is_open or gate.version != quote.gate_version:
                raise CommercialRuleViolation(
                    'GATE_CHANGED', 'Market activation changed since this quote was issued; request a fresh quote.',
                )
            quote.status = QuoteStatusChoices.ACCEPTED
            quote.accepted_at = timezone.now()
            quote.accepted_by = actor
            quote.consent_notice_version = consent_notice_version
            quote.accept_gate_version = gate.version
            quote.save()
            audit(actor, 'commercial.quote.accepted', 'commercial:quote.accept', 'QuoteSnapshot', quote.id,
                  {'quote_number': quote.quote_number, 'terms_hash': quote.terms_hash,
                   'consent_notice_version': consent_notice_version})
            emit_event('quote.accepted', aggregate_type='QuoteSnapshot', aggregate_id=quote.id,
                       payload={'quote_number': quote.quote_number, 'terms_hash': quote.terms_hash,
                                'currency': quote.currency, 'customer_total_minor': quote.customer_total_minor,
                                'platform_fee_minor': quote.platform_fee_minor},
                       idempotency_key=f'quote.accepted:{quote.id}', actor_id=actor.id)
    if expired:
        raise CommercialRuleViolation('QUOTE_EXPIRED', 'This quote has expired; request a fresh quote.')
    return quote
