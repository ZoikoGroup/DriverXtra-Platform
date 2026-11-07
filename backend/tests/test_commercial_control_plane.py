"""R1 Commercial Control Plane — service-level tests.

Maps to Master Architecture v1.0 §24 acceptance tests:
  COM-001  quote only from the correct effective-dated market/contract SKU; closed gate, absent role,
           unapproved SKU or no effective rate rejects the quote
  COM-002  accepted (and issued) quotes stay immutable after pricing/rate/plan changes
  COM-003  fee base and fee calculation match the Appendix A golden vectors
  COM-008  no regulated SKU, role or gate can be enabled without a signed gate (blocked outright in R1)
Market codes and amounts here are test fixtures, not launch decisions or approved prices.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.commercial.choices import (
    CatalogueStatusChoices as CS,
    GateCapabilityChoices as Cap,
    GateStatusChoices as G,
    QuoteStatusChoices,
    RoleProfileStatusChoices as RS,
)
from apps.commercial.errors import CommercialRuleViolation, ImmutableCommercialRecordError
from apps.commercial.models import (
    CommercialSku, CountryGate, CountryGateTransition, PartyRoleSnapshot, QuoteLine, QuoteSnapshot, RateSchedule,
)
from apps.commercial.money import apply_basis_points, clamp_fee, divide_round_half_up
from apps.commercial.services import catalogue, gates, quotes, rates, roles
from apps.commercial.services.quotes import FeeItem, QuoteRequest
from apps.identity.models import User
from apps.organisations.models import Organisation
from platform_core.events.models import OutboxEvent


# ---------------------------------------------------------------------------
# Fixtures & builders
# ---------------------------------------------------------------------------

def _superuser(email):
    return User.objects.create_superuser(email=email, password='Str0ng-Passw0rd!x')


@pytest.fixture
def maker(db):
    return _superuser('maker@driverxtra.test')


@pytest.fixture
def checker(db):
    return _superuser('checker@driverxtra.test')


@pytest.fixture
def customer(db):
    return User.objects.create_user(email='dealer.customer@driverxtra.test', password='Str0ng-Passw0rd!x',
                                    is_email_verified=True)


@pytest.fixture
def seller_org(db, customer):
    return Organisation.objects.create(name='Test Parts Supplier Ltd', type='DEALER_GROUP', created_by=customer)


def rule_of(excinfo):
    return excinfo.value.rule


def make_sku(maker, code='DX-DEAL-GROWTH', **overrides):
    data = {
        'name': 'Dealer Growth', 'family': 'SUBSCRIPTION', 'revenue_code': 'SUB-01', 'vertical': 'VEHICLES',
        'fee_basis': 'RECURRING_FLAT', 'billing_interval': 'MONTHLY', 'entitlement_type': 'INVENTORY_SLOT',
        'illustrative_band_note': 'Illustrative test band only',
    }
    data.update(overrides)
    return catalogue.create_sku({'sku_code': code, **data}, maker)


def approve_sku(sku, checker):
    return catalogue.transition_sku(sku, CS.APPROVED, checker, 'Approved for test', approval_reference='CFO-TEST-1')


def make_rate(sku, maker, *, country='GB', currency='GBP', payer_role='DEALER', flat=24900, bps=None,
              priority=100, plan_code='', effective_from=None, effective_to=None, name='Test rate', **extra):
    data = {
        'name': name, 'country_code': country, 'currency': currency, 'payer_role': payer_role,
        'priority': priority, 'plan_code': plan_code,
        'effective_from': effective_from or timezone.now(), 'effective_to': effective_to,
    }
    if bps is not None:
        data['percentage_bps'] = bps
    else:
        data['flat_amount_minor'] = flat
    data.update(extra)
    return rates.create_rate(sku, data, maker)


def approve_rate(rate, checker):
    return rates.transition_rate(rate, CS.APPROVED, checker, 'Approved for test', approval_reference='CFO-RATE-1')


def make_profile(maker, code='GB-VEH-SOFTWARE', country='GB', vertical='VEHICLES', **overrides):
    data = {
        'code': code, 'name': 'Software-only dealer SaaS', 'profile_type': 'SOFTWARE_ONLY',
        'country_code': country, 'vertical': vertical, 'seller_of_record': 'PLATFORM',
        'service_performer': 'PLATFORM', 'platform_role': 'SOFTWARE_PROVIDER',
        'payment_role': 'SUBSCRIPTION_BILLING', 'tax_party': 'PLATFORM', 'invoice_issuer': 'PLATFORM',
        'legal_memo_reference': 'LEGAL-MEMO-TEST', 'effective_from': timezone.now() - timedelta(days=1),
    }
    data.update(overrides)
    return roles.create_profile(data, maker)


def approve_profile(profile, checker):
    return roles.transition_profile(profile, RS.APPROVED, checker, 'Approved for test', approval_reference='GC-TEST-1')


def walk_gate_to_rehearsed(gate, maker):
    for step in (G.LEGALLY_REVIEWED, G.PARTNER_VERIFIED, G.FINANCE_SIGNED, G.TECHNICAL_REHEARSED):
        gate = gates.transition_gate(gate, step, maker, f'{step} complete', evidence_reference=f'EVID-{step}')
    return gate


def open_gate(maker, checker, *, country='GB', vertical='VEHICLES', capability=Cap.BINDING_QUOTE, currencies=('GBP',)):
    gate = gates.create_gate({'country_code': country, 'vertical': vertical, 'capability': capability,
                              'allowed_currencies': list(currencies), 'tax_schedule_reference': 'TAX-SCHED-TEST'}, maker)
    gate = walk_gate_to_rehearsed(gate, maker)
    return gates.transition_gate(gate, G.ENABLED, checker, 'Go-live approved')


@pytest.fixture
def subscription_market(maker, checker):
    """A fully approved test market: approved role profile, open gate, approved SKU and rate."""
    approve_profile(make_profile(maker), checker)
    gate = open_gate(maker, checker)
    sku = approve_sku(make_sku(maker), checker)
    rate = approve_rate(make_rate(sku, maker), checker)
    return {'gate': gate, 'sku': sku, 'rate': rate}


def subscription_request(customer, **overrides):
    data = dict(
        customer=customer, customer_role='DEALER', country_code='GB', vertical='VEHICLES', currency='GBP',
        role_profile_code='GB-VEH-SOFTWARE', fee_items=[FeeItem('DX-DEAL-GROWTH', 'DEALER')],
        terms_version='DEALER-TERMS-TEST-1', tax_determination_reference='TAXDET-TEST-1',
    )
    data.update(overrides)
    return QuoteRequest(**data)


# ---------------------------------------------------------------------------
# Money (Appendix C: integer minor units, no floats)
# ---------------------------------------------------------------------------

def test_money_rounding_is_integer_half_up():
    assert apply_basis_points(9000, 800) == 720          # Appendix A parts basket fee
    assert apply_basis_points(3000, 800) == 240          # Appendix A partial-return fee credit
    assert apply_basis_points(1, 5000) == 1              # 0.5 rounds up
    assert apply_basis_points(1, 4999) == 0
    assert divide_round_half_up(-5, 2) == -3             # symmetric half away from zero
    assert clamp_fee(50, min_fee_minor=100) == 100
    assert clamp_fee(5000, max_fee_minor=1000) == 1000


@pytest.mark.django_db
def test_unknown_currency_is_rejected(maker, checker):
    sku = approve_sku(make_sku(maker), checker)
    with pytest.raises(CommercialRuleViolation) as exc:
        make_rate(sku, maker, currency='XXX')
    assert rule_of(exc) == 'UNSUPPORTED_CURRENCY'


# ---------------------------------------------------------------------------
# SKU catalogue
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_new_sku_starts_as_draft_and_cannot_be_self_approved(maker):
    sku = make_sku(maker)
    assert sku.status == CS.DRAFT
    assert sku.is_regulated is False
    with pytest.raises(CommercialRuleViolation) as exc:
        catalogue.transition_sku(sku, CS.APPROVED, maker, 'self approve', approval_reference='X')
    assert rule_of(exc) == 'SEPARATION_OF_DUTIES'


@pytest.mark.django_db
def test_sku_approval_requires_reference_and_freezes_the_version(maker, checker):
    sku = make_sku(maker)
    with pytest.raises(CommercialRuleViolation) as exc:
        catalogue.transition_sku(sku, CS.APPROVED, checker, 'ok', approval_reference='')
    assert rule_of(exc) == 'APPROVAL_REFERENCE_REQUIRED'

    sku = approve_sku(sku, checker)
    assert sku.approved_by == checker and sku.approval_reference == 'CFO-TEST-1'
    with pytest.raises(CommercialRuleViolation) as exc:
        catalogue.update_sku(sku, {'name': 'Renamed'}, maker)
    assert rule_of(exc) == 'SKU_FROZEN'
    assert OutboxEvent.objects.filter(topic='commercial.sku.published', aggregate_id=str(sku.id)).count() == 1


@pytest.mark.django_db
def test_approving_a_new_version_retires_the_previous_approved_version(maker, checker):
    v1 = approve_sku(make_sku(maker), checker)
    v2 = catalogue.create_new_version(v1, maker)
    assert (v2.version, v2.status) == (2, CS.DRAFT)
    approve_sku(v2, checker)
    v1.refresh_from_db()
    assert v1.status == CS.RETIRED
    assert CommercialSku.objects.filter(sku_code='DX-DEAL-GROWTH', status=CS.APPROVED).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize('overrides', [
    {'family': 'REGULATED', 'revenue_code': 'REG-01'},
    {'family': 'REFERRAL', 'revenue_code': 'REG-02'},
    {'family': 'PAYMENT', 'revenue_code': 'FIN-01'},
    {'family': 'COMMERCE', 'revenue_code': 'COM-04'},
    {'family': 'REFERRAL', 'revenue_code': 'REF-01', 'vertical': 'FINANCE_INSURANCE'},
])
def test_com_008_regulated_skus_cannot_be_approved(maker, checker, overrides):
    sku = make_sku(maker, code='DX-REG-TEST', fee_basis='FLAT_PER_UNIT', **overrides)
    assert sku.is_regulated is True
    with pytest.raises(CommercialRuleViolation) as exc:
        approve_sku(sku, checker)
    assert rule_of(exc) == 'REGULATED_SKU_BLOCKED'
    sku.refresh_from_db()
    assert sku.status == CS.DRAFT


# ---------------------------------------------------------------------------
# Country gates
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_gates_default_closed_and_absent_gates_are_closed(maker):
    gate = gates.create_gate({'country_code': 'gb', 'vertical': 'VEHICLES', 'capability': Cap.BINDING_QUOTE}, maker)
    assert (gate.country_code, gate.status, gate.is_open, gate.version) == ('GB', G.DESIGNED, False, 1)
    with pytest.raises(CommercialRuleViolation) as exc:
        gates.get_open_gate('GB', 'VEHICLES', Cap.BINDING_QUOTE)
    assert rule_of(exc) == 'COUNTRY_GATE_CLOSED'
    with pytest.raises(CommercialRuleViolation) as exc:
        gates.get_open_gate('FR', 'PARTS', Cap.BINDING_QUOTE)
    assert rule_of(exc) == 'COUNTRY_GATE_CLOSED'
    assert gates.is_gate_open('FR', 'PARTS', Cap.BINDING_QUOTE) is False


@pytest.mark.django_db
def test_gate_cannot_skip_activation_steps_and_needs_evidence(maker):
    gate = gates.create_gate({'country_code': 'GB', 'vertical': 'VEHICLES', 'capability': Cap.BINDING_QUOTE}, maker)
    with pytest.raises(CommercialRuleViolation) as exc:
        gates.transition_gate(gate, G.ENABLED, maker, 'skip')
    assert rule_of(exc) == 'INVALID_TRANSITION'
    with pytest.raises(CommercialRuleViolation) as exc:
        gates.transition_gate(gate, G.LEGALLY_REVIEWED, maker, 'no evidence')
    assert rule_of(exc) == 'EVIDENCE_REQUIRED'


@pytest.mark.django_db
def test_enabling_requires_tax_schedule_currency_role_profile_and_separation_of_duties(maker, checker):
    gate = gates.create_gate({'country_code': 'GB', 'vertical': 'VEHICLES', 'capability': Cap.BINDING_QUOTE}, maker)
    gate = walk_gate_to_rehearsed(gate, maker)

    with pytest.raises(CommercialRuleViolation) as exc:
        gates.transition_gate(gate, G.ENABLED, checker, 'enable')
    assert rule_of(exc) == 'TAX_SCHEDULE_MISSING'

    gates.update_gate_config(gate, {'tax_schedule_reference': 'TAX-SCHED-TEST'}, maker)
    with pytest.raises(CommercialRuleViolation) as exc:
        gates.transition_gate(gate, G.ENABLED, checker, 'enable')
    assert rule_of(exc) == 'CURRENCY_NOT_CONFIGURED'

    gates.update_gate_config(gate, {'allowed_currencies': ['gbp']}, maker)
    with pytest.raises(CommercialRuleViolation) as exc:
        gates.transition_gate(gate, G.ENABLED, checker, 'enable')
    assert rule_of(exc) == 'COMMERCIAL_ROLE_MISSING'

    approve_profile(make_profile(maker), checker)
    with pytest.raises(CommercialRuleViolation) as exc:
        gates.transition_gate(gate, G.ENABLED, maker, 'finance signer enabling')
    assert rule_of(exc) == 'SEPARATION_OF_DUTIES'

    gate = gates.transition_gate(gate, G.ENABLED, checker, 'Go-live approved')
    assert gate.is_open and gate.version == 6
    assert gate.allowed_currencies == ['GBP']
    assert CountryGateTransition.objects.filter(gate=gate).count() == 5


@pytest.mark.django_db
@pytest.mark.parametrize('vertical,capability', [
    ('FINANCE_INSURANCE', Cap.BINDING_QUOTE),
    ('VEHICLES', Cap.REGULATED_REFERRAL),
])
def test_com_008_regulated_gates_cannot_be_enabled(maker, checker, vertical, capability):
    approve_profile(make_profile(maker, code='REG-TEST-PROFILE', vertical='VEHICLES'), checker)
    gate = gates.create_gate({'country_code': 'GB', 'vertical': vertical, 'capability': capability,
                              'allowed_currencies': ['GBP'], 'tax_schedule_reference': 'TAX'}, maker)
    gate = walk_gate_to_rehearsed(gate, maker)
    with pytest.raises(CommercialRuleViolation) as exc:
        gates.transition_gate(gate, G.ENABLED, checker, 'attempt')
    assert rule_of(exc) == 'REGULATED_GATE_LOCKED'
    gate.refresh_from_db()
    assert gate.is_open is False


@pytest.mark.django_db
def test_gate_transitions_are_append_only_and_emit_events(maker, checker):
    approve_profile(make_profile(maker), checker)
    gate = open_gate(maker, checker)
    gate = gates.transition_gate(gate, G.SUSPENDED, maker, 'Incident')
    assert gate.is_open is False

    transition = CountryGateTransition.objects.filter(gate=gate).first()
    transition.reason = 'tampered'
    with pytest.raises(ImmutableCommercialRecordError):
        transition.save()
    with pytest.raises(ImmutableCommercialRecordError):
        CountryGateTransition.objects.filter(gate=gate).update(reason='x')
    with pytest.raises(ImmutableCommercialRecordError):
        CountryGateTransition.objects.filter(gate=gate).delete()

    assert OutboxEvent.objects.filter(topic='compliance.policy_changed', aggregate_id=str(gate.id)).count() == 6
    assert OutboxEvent.objects.filter(topic='eligibility.suspended', aggregate_id=str(gate.id)).count() == 1


@pytest.mark.django_db
def test_enabled_gate_config_is_locked(maker, checker):
    approve_profile(make_profile(maker), checker)
    gate = open_gate(maker, checker)
    with pytest.raises(CommercialRuleViolation) as exc:
        gates.update_gate_config(gate, {'allowed_currencies': ['USD']}, maker)
    assert rule_of(exc) == 'GATE_OPEN'


# ---------------------------------------------------------------------------
# Party role profiles
# ---------------------------------------------------------------------------

@pytest.mark.django_db
@pytest.mark.parametrize('overrides', [
    {'profile_type': 'REGULATED_INTRODUCER', 'platform_role': 'INTRODUCER'},
    {'profile_type': 'PRINCIPAL_SELLER', 'platform_role': 'PRINCIPAL'},
    {'profile_type': 'CROSS_BORDER_ORCHESTRATOR', 'platform_role': 'ORCHESTRATOR'},
    {'payment_role': 'PSP_CONDITIONAL_PAYOUT'},
    {'payment_role': 'PARTNER_REGULATED'},
])
def test_gated_role_profiles_cannot_be_approved(maker, checker, overrides):
    profile = make_profile(maker, code='GATED-PROFILE', **overrides)
    with pytest.raises(CommercialRuleViolation) as exc:
        approve_profile(profile, checker)
    assert rule_of(exc) == 'GATED_ROLE_PROFILE'


@pytest.mark.django_db
def test_role_profile_approval_requires_legal_memo_and_another_person(maker, checker):
    profile = make_profile(maker, legal_memo_reference='')
    with pytest.raises(CommercialRuleViolation) as exc:
        approve_profile(profile, checker)
    assert rule_of(exc) == 'LEGAL_MEMO_REQUIRED'
    profile = roles.update_profile(profile, {'legal_memo_reference': 'MEMO-1'}, maker)
    with pytest.raises(CommercialRuleViolation) as exc:
        roles.transition_profile(profile, RS.APPROVED, maker, 'self', approval_reference='X')
    assert rule_of(exc) == 'SEPARATION_OF_DUTIES'
    assert approve_profile(profile, checker).status == RS.APPROVED


# ---------------------------------------------------------------------------
# Rate schedules
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_rate_approval_requires_approved_sku_and_is_prospective_only(maker, checker):
    sku = make_sku(maker)
    rate = make_rate(sku, maker)
    with pytest.raises(CommercialRuleViolation) as exc:
        approve_rate(rate, checker)
    assert rule_of(exc) == 'SKU_NOT_APPROVED'

    approve_sku(sku, checker)
    past = make_rate(sku, maker, effective_from=timezone.now() - timedelta(days=2), name='Backdated')
    with pytest.raises(CommercialRuleViolation) as exc:
        approve_rate(past, checker)
    assert rule_of(exc) == 'RETROACTIVE_RATE'

    with pytest.raises(CommercialRuleViolation) as exc:
        rates.transition_rate(rate, CS.APPROVED, maker, 'self', approval_reference='X')
    assert rule_of(exc) == 'SEPARATION_OF_DUTIES'

    approve_rate(rate, checker)
    with pytest.raises(CommercialRuleViolation) as exc:
        rates.update_rate(rate, {'flat_amount_minor': 1}, maker)
    assert rule_of(exc) == 'RATE_FROZEN'


@pytest.mark.django_db
def test_overlapping_approved_rates_are_rejected(maker, checker):
    sku = approve_sku(make_sku(maker), checker)
    approve_rate(make_rate(sku, maker, name='A'), checker)
    with pytest.raises(CommercialRuleViolation) as exc:
        approve_rate(make_rate(sku, maker, name='B'), checker)
    assert rule_of(exc) == 'RATE_OVERLAP'


@pytest.mark.django_db
def test_rate_fields_are_validated_against_fee_basis(maker):
    flat_sku = make_sku(maker)
    with pytest.raises(CommercialRuleViolation) as exc:
        rates.create_rate(flat_sku, {'name': 'x', 'country_code': 'GB', 'currency': 'GBP', 'payer_role': 'DEALER',
                                     'effective_from': timezone.now(), 'percentage_bps': 800}, maker)
    assert rule_of(exc) == 'FLAT_AMOUNT_REQUIRED'
    usage_sku = make_sku(maker, code='DX-API-BASE', fee_basis='USAGE_METERED', family='API', revenue_code='API-01',
                         vertical='ENTERPRISE_API')
    with pytest.raises(CommercialRuleViolation) as exc:
        make_rate(usage_sku, maker, flat=100)
    assert rule_of(exc) == 'FEE_BASIS_NOT_QUOTABLE'


@pytest.mark.django_db
def test_rate_resolution_uses_priority_then_plan_specificity(maker, checker):
    sku = approve_sku(make_sku(maker), checker)
    base = approve_rate(make_rate(sku, maker, flat=24900, name='Base'), checker)
    plan = approve_rate(make_rate(sku, maker, flat=19900, plan_code='LAUNCH', name='Plan'), checker)
    promo = approve_rate(make_rate(sku, maker, flat=14900, priority=200, name='Promo'), checker)

    kwargs = dict(country_code='GB', vertical='VEHICLES', currency='GBP', payer_role='DEALER')
    assert rates.resolve_rate(sku, plan_code='LAUNCH', **kwargs) == promo
    rates.transition_rate(promo, CS.RETIRED, checker, 'Promo ended')
    assert rates.resolve_rate(sku, plan_code='LAUNCH', **kwargs) == plan
    assert rates.resolve_rate(sku, plan_code='', **kwargs) == base

    with pytest.raises(CommercialRuleViolation) as exc:
        rates.resolve_rate(sku, country_code='GB', vertical='VEHICLES', currency='GBP', payer_role='WORKSHOP')
    assert rule_of(exc) == 'RATE_NOT_FOUND'


@pytest.mark.django_db
def test_equal_priority_tie_is_ambiguous_not_silently_chosen(maker):
    # Approved rates can never tie (the overlap rule blocks it), but draft rates used by previews can.
    sku = make_sku(maker)
    make_rate(sku, maker, name='A', plan_code='X')
    make_rate(sku, maker, name='B', plan_code='X')
    with pytest.raises(CommercialRuleViolation) as exc:
        rates.resolve_rate(sku, country_code='GB', vertical='VEHICLES', currency='GBP', payer_role='DEALER',
                           plan_code='X', statuses=(CS.APPROVED, CS.DRAFT))
    assert rule_of(exc) == 'RATE_AMBIGUOUS'


# ---------------------------------------------------------------------------
# Quotes — COM-001 / COM-002 / Appendix A
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_binding_quote_issued_from_approved_effective_terms(subscription_market, customer):
    quote = quotes.issue_quote(subscription_request(customer))
    assert quote.status == QuoteStatusChoices.ISSUED
    assert (quote.currency, quote.currency_exponent) == ('GBP', 2)
    assert quote.platform_fee_minor == 24900
    assert quote.customer_total_minor == 24900
    assert quote.gate_version == subscription_market['gate'].version
    assert len(quote.terms_hash) == 64
    assert quote.role_snapshot.seller_of_record_party == 'platform'
    fee_line = quote.lines.get(line_type='PLATFORM_FEE')
    assert (fee_line.rate_schedule, fee_line.sku_version, fee_line.is_customer_payable) == (
        subscription_market['rate'], 1, True)
    assert OutboxEvent.objects.filter(topic='quote.issued', aggregate_id=str(quote.id)).count() == 1


@pytest.mark.django_db
def test_com_001_closed_or_absent_gate_rejects_binding_quote(subscription_market, customer, maker):
    with pytest.raises(CommercialRuleViolation) as exc:
        quotes.issue_quote(subscription_request(customer, country_code='IE', currency='EUR',
                                                role_profile_code='GB-VEH-SOFTWARE'))
    assert rule_of(exc) == 'COUNTRY_GATE_CLOSED'

    gates.transition_gate(subscription_market['gate'], G.SUSPENDED, maker, 'Incident')
    with pytest.raises(CommercialRuleViolation) as exc:
        quotes.issue_quote(subscription_request(customer))
    assert rule_of(exc) == 'COUNTRY_GATE_CLOSED'
    assert QuoteSnapshot.objects.count() == 0


@pytest.mark.django_db
def test_com_001_absent_or_expired_commercial_role_rejects(subscription_market, customer, maker, checker):
    with pytest.raises(CommercialRuleViolation) as exc:
        quotes.issue_quote(subscription_request(customer, role_profile_code='NO-SUCH-PROFILE'))
    assert rule_of(exc) == 'COMMERCIAL_ROLE_MISSING'

    approve_profile(make_profile(maker, code='EXPIRED-PROFILE', effective_from=timezone.now() - timedelta(days=10),
                                 effective_to=timezone.now() - timedelta(days=1)), checker)
    with pytest.raises(CommercialRuleViolation) as exc:
        quotes.issue_quote(subscription_request(customer, role_profile_code='EXPIRED-PROFILE'))
    assert rule_of(exc) == 'COMMERCIAL_ROLE_MISSING'


@pytest.mark.django_db
def test_com_001_unapproved_sku_or_no_effective_rate_rejects(subscription_market, customer, maker, checker):
    make_sku(maker, code='DX-DEAL-LAUNCH', name='Dealer Launch')  # DRAFT only
    with pytest.raises(CommercialRuleViolation) as exc:
        quotes.issue_quote(subscription_request(customer, fee_items=[FeeItem('DX-DEAL-LAUNCH', 'DEALER')]))
    assert rule_of(exc) == 'SKU_NOT_APPROVED'

    future_sku = approve_sku(make_sku(maker, code='DX-DEAL-ENT', name='Dealer Enterprise'), checker)
    approve_rate(make_rate(future_sku, maker, effective_from=timezone.now() + timedelta(days=30)), checker)
    with pytest.raises(CommercialRuleViolation) as exc:
        quotes.issue_quote(subscription_request(customer, fee_items=[FeeItem('DX-DEAL-ENT', 'DEALER')]))
    assert rule_of(exc) == 'RATE_NOT_FOUND'


@pytest.mark.django_db
def test_com_001_currency_and_evidence_requirements(subscription_market, customer):
    with pytest.raises(CommercialRuleViolation) as exc:
        quotes.issue_quote(subscription_request(customer, currency='USD'))
    assert rule_of(exc) == 'CURRENCY_NOT_PERMITTED'
    with pytest.raises(CommercialRuleViolation) as exc:
        quotes.issue_quote(subscription_request(customer, tax_determination_reference=''))
    assert rule_of(exc) == 'TAX_DETERMINATION_REQUIRED'
    with pytest.raises(CommercialRuleViolation) as exc:
        quotes.issue_quote(subscription_request(customer, terms_version=''))
    assert rule_of(exc) == 'TERMS_VERSION_REQUIRED'


@pytest.mark.django_db
def test_duplicate_fee_sku_is_rejected(subscription_market, customer):
    with pytest.raises(CommercialRuleViolation) as exc:
        quotes.issue_quote(subscription_request(customer, fee_items=[FeeItem('DX-DEAL-GROWTH', 'DEALER'),
                                                                      FeeItem('dx-deal-growth', 'DEALER')]))
    assert rule_of(exc) == 'DUPLICATE_FEE_SKU'


@pytest.mark.django_db
def test_appendix_a_parts_basket_golden_vector(maker, checker, customer, seller_org):
    """Goods $100.00; discount $10.00; shipping $6.00; tax $7.20; fee 8% of goods net of discount.
    Expected: buyer payable $103.20; fee base $90.00; platform fee $7.20 (borne by the seller)."""
    approve_profile(make_profile(
        maker, code='US-PARTS-FACILITATED', country='US', vertical='PARTS', profile_type='FACILITATED_ORDER',
        seller_of_record='THIRD_PARTY_SELLER', service_performer='NONE', platform_role='MARKETPLACE_FACILITATOR',
        payment_role='PSP_DIRECT_SETTLEMENT', tax_party='SELLER', invoice_issuer='SELLER',
    ), checker)
    open_gate(maker, checker, country='US', vertical='PARTS', currencies=('USD',))
    sku = approve_sku(make_sku(maker, code='DX-PARTS-TAKE', name='Parts platform fee', family='COMMERCE',
                               revenue_code='COM-01', vertical='PARTS', fee_basis='PERCENT_OF_BASE',
                               billing_interval='PER_EVENT', entitlement_type='NONE'), checker)
    approve_rate(make_rate(sku, maker, country='US', currency='USD', payer_role='SUPPLIER', bps=800), checker)

    quote = quotes.issue_quote(QuoteRequest(
        customer=customer, customer_role='BUYER', country_code='US', vertical='PARTS', currency='USD',
        role_profile_code='US-PARTS-FACILITATED', fee_items=[FeeItem('DX-PARTS-TAKE', 'SUPPLIER')],
        terms_version='BUYER-TERMS-TEST', tax_determination_reference='TAXDET-US-TEST',
        face_value_minor=10000, discount_minor=1000, delivery_minor=600, tax_minor=720,
        seller_organisation=seller_org,
    ))
    assert quote.commissionable_base_minor == 9000
    assert quote.platform_fee_minor == 720
    assert quote.customer_total_minor == 10320
    assert quote.role_snapshot.seller_of_record_party == f'org:{seller_org.id}'
    fee_line = quote.lines.get(line_type='PLATFORM_FEE')
    assert fee_line.is_customer_payable is False
    assert [l.amount_minor for l in quote.lines.order_by('position')] == [10000, -1000, 600, 720, 720]


@pytest.mark.django_db
def test_facilitated_order_requires_named_seller_of_record(maker, checker, customer):
    approve_profile(make_profile(
        maker, code='US-PARTS-FACILITATED', country='US', vertical='PARTS', profile_type='FACILITATED_ORDER',
        seller_of_record='THIRD_PARTY_SELLER', service_performer='NONE', platform_role='MARKETPLACE_FACILITATOR',
        payment_role='PSP_DIRECT_SETTLEMENT', tax_party='SELLER', invoice_issuer='SELLER',
    ), checker)
    open_gate(maker, checker, country='US', vertical='PARTS', currencies=('USD',))
    sku = approve_sku(make_sku(maker, code='DX-PARTS-TAKE', family='COMMERCE', revenue_code='COM-01',
                               vertical='PARTS', fee_basis='PERCENT_OF_BASE'), checker)
    approve_rate(make_rate(sku, maker, country='US', currency='USD', payer_role='SUPPLIER', bps=800), checker)
    with pytest.raises(CommercialRuleViolation) as exc:
        quotes.issue_quote(QuoteRequest(
            customer=customer, customer_role='BUYER', country_code='US', vertical='PARTS', currency='USD',
            role_profile_code='US-PARTS-FACILITATED', fee_items=[FeeItem('DX-PARTS-TAKE', 'SUPPLIER')],
            terms_version='T', tax_determination_reference='X', face_value_minor=10000,
        ))
    assert rule_of(exc) == 'SELLER_OF_RECORD_REQUIRED'


@pytest.mark.django_db
def test_com_002_accepted_quote_is_immutable_after_pricing_changes(subscription_market, customer, maker, checker):
    quote = quotes.issue_quote(subscription_request(customer))
    quote = quotes.accept_quote(quote, customer, terms_hash=quote.terms_hash, consent_notice_version='CONSENT-1')
    assert quote.status == QuoteStatusChoices.ACCEPTED
    frozen = {
        'customer_total_minor': quote.customer_total_minor, 'platform_fee_minor': quote.platform_fee_minor,
        'terms_hash': quote.terms_hash, 'gate_version': quote.gate_version,
        'lines': list(quote.lines.order_by('position').values_list('amount_minor', 'rate_schedule_id', 'sku_version')),
    }

    # Pricing, rate and plan change after acceptance.
    rates.transition_rate(subscription_market['rate'], CS.RETIRED, checker, 'Repriced')
    v2 = approve_sku(catalogue.create_new_version(subscription_market['sku'], maker), checker)
    approve_rate(make_rate(v2, maker, flat=39900, name='New price'), checker)

    reloaded = QuoteSnapshot.objects.get(pk=quote.pk)
    assert reloaded.customer_total_minor == frozen['customer_total_minor']
    assert reloaded.platform_fee_minor == frozen['platform_fee_minor']
    assert reloaded.terms_hash == frozen['terms_hash']
    assert list(reloaded.lines.order_by('position').values_list(
        'amount_minor', 'rate_schedule_id', 'sku_version')) == frozen['lines']

    # A new quote picks up the new price; the old one is untouched.
    assert quotes.issue_quote(subscription_request(customer)).platform_fee_minor == 39900


@pytest.mark.django_db
def test_com_002_snapshot_cannot_be_mutated_or_deleted(subscription_market, customer):
    quote = quotes.issue_quote(subscription_request(customer))
    quote.customer_total_minor = 1
    with pytest.raises(ImmutableCommercialRecordError):
        quote.save()

    quote = QuoteSnapshot.objects.get(pk=quote.pk)
    quote = quotes.accept_quote(quote, customer, terms_hash=quote.terms_hash, consent_notice_version='CONSENT-1')
    quote.status = QuoteStatusChoices.VOID
    with pytest.raises(ImmutableCommercialRecordError):
        quote.save()
    with pytest.raises(ImmutableCommercialRecordError):
        QuoteSnapshot.objects.filter(pk=quote.pk).update(customer_total_minor=0)
    with pytest.raises(ImmutableCommercialRecordError):
        QuoteSnapshot.objects.get(pk=quote.pk).delete()
    with pytest.raises(ImmutableCommercialRecordError):
        QuoteLine.objects.filter(quote=quote).update(amount_minor=0)
    with pytest.raises(ImmutableCommercialRecordError):
        PartyRoleSnapshot.objects.filter(pk=quote.role_snapshot_id).delete()


@pytest.mark.django_db
def test_issued_quote_keeps_price_until_expiry_after_rate_change(subscription_market, customer, maker, checker):
    quote = quotes.issue_quote(subscription_request(customer))
    rates.transition_rate(subscription_market['rate'], CS.RETIRED, checker, 'Repriced')
    approve_rate(make_rate(subscription_market['sku'], maker, flat=39900, name='New price'), checker)
    accepted = quotes.accept_quote(quote, customer, terms_hash=quote.terms_hash, consent_notice_version='C1')
    assert accepted.customer_total_minor == 24900


@pytest.mark.django_db
def test_accept_rejects_wrong_terms_other_users_and_double_acceptance(subscription_market, customer, maker):
    quote = quotes.issue_quote(subscription_request(customer))
    with pytest.raises(CommercialRuleViolation) as exc:
        quotes.accept_quote(quote, customer, terms_hash='0' * 64, consent_notice_version='C1')
    assert rule_of(exc) == 'TERMS_MISMATCH'
    with pytest.raises(CommercialRuleViolation) as exc:
        quotes.accept_quote(quote, maker, terms_hash=quote.terms_hash, consent_notice_version='C1')
    assert rule_of(exc) == 'NOT_QUOTE_OWNER'
    with pytest.raises(CommercialRuleViolation) as exc:
        quotes.accept_quote(quote, customer, terms_hash=quote.terms_hash, consent_notice_version='')
    assert rule_of(exc) == 'CONSENT_REQUIRED'

    quotes.accept_quote(quote, customer, terms_hash=quote.terms_hash, consent_notice_version='C1')
    with pytest.raises(CommercialRuleViolation) as exc:
        quotes.accept_quote(quote, customer, terms_hash=quote.terms_hash, consent_notice_version='C1')
    assert rule_of(exc) == 'QUOTE_NOT_OPEN'
    assert OutboxEvent.objects.filter(topic='quote.accepted', aggregate_id=str(quote.id)).count() == 1


@pytest.mark.django_db
def test_accept_rejects_expired_quotes_and_records_expiry(subscription_market, customer, settings):
    settings.COMMERCIAL_QUOTE_TTL_SECONDS = 0
    quote = quotes.issue_quote(subscription_request(customer))
    with pytest.raises(CommercialRuleViolation) as exc:
        quotes.accept_quote(quote, customer, terms_hash=quote.terms_hash, consent_notice_version='C1')
    assert rule_of(exc) == 'QUOTE_EXPIRED'
    assert QuoteSnapshot.objects.get(pk=quote.pk).status == QuoteStatusChoices.EXPIRED


@pytest.mark.django_db
def test_accept_rejects_when_gate_changed_since_issue(subscription_market, customer, maker, checker):
    quote = quotes.issue_quote(subscription_request(customer))
    gate = gates.transition_gate(subscription_market['gate'], G.SUSPENDED, maker, 'Incident')
    with pytest.raises(CommercialRuleViolation) as exc:
        quotes.accept_quote(quote, customer, terms_hash=quote.terms_hash, consent_notice_version='C1')
    assert rule_of(exc) == 'GATE_CHANGED'
    # Re-enabled gate is a new activation version: the old quote still cannot be accepted.
    gates.transition_gate(gate, G.ENABLED, checker, 'Resolved')
    with pytest.raises(CommercialRuleViolation) as exc:
        quotes.accept_quote(quote, customer, terms_hash=quote.terms_hash, consent_notice_version='C1')
    assert rule_of(exc) == 'GATE_CHANGED'


# ---------------------------------------------------------------------------
# Non-binding preview over illustrative data
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_preview_calculates_illustrative_pricing_without_persisting(maker, customer):
    sku = make_sku(maker)
    catalogue.transition_sku(sku, CS.ILLUSTRATIVE, maker, 'Price test band')
    rate = make_rate(sku, maker, flat=14900)
    rates.transition_rate(rate, CS.ILLUSTRATIVE, maker, 'Test band')

    computation = quotes.compute_quote(subscription_request(customer), binding=False)
    assert computation.customer_total_minor == 14900
    rules = {reason['rule'] for reason in computation.blocking_reasons}
    assert {'COUNTRY_GATE_CLOSED', 'COMMERCIAL_ROLE_MISSING', 'SKU_NOT_APPROVED', 'RATE_NOT_APPROVED'} <= rules
    assert QuoteSnapshot.objects.count() == 0
    assert OutboxEvent.objects.filter(topic__startswith='quote.').count() == 0

    with pytest.raises(CommercialRuleViolation) as exc:
        quotes.issue_quote(subscription_request(customer))
    assert rule_of(exc) == 'COUNTRY_GATE_CLOSED'


# ---------------------------------------------------------------------------
# Seed command
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_seed_command_loads_non_binding_skus_only_and_is_idempotent():
    from io import StringIO
    from django.core.management import call_command

    call_command('seed_illustrative_commercial_catalogue', stdout=StringIO())
    call_command('seed_illustrative_commercial_catalogue', stdout=StringIO())

    assert CommercialSku.objects.count() == 15
    assert not CommercialSku.objects.filter(status__in=[CS.APPROVED, CS.RETIRED]).exists()
    assert set(CommercialSku.objects.filter(status=CS.DRAFT).values_list('sku_code', flat=True)) == {
        'DX-SERVICE-BOOK', 'DX-REG-REF', 'DX-PAYMENT-FEE'}
    assert set(CommercialSku.objects.filter(is_regulated=True).values_list('sku_code', flat=True)) == {
        'DX-REG-REF', 'DX-PAYMENT-FEE'}
    assert RateSchedule.objects.count() == 0
    assert CountryGate.objects.count() == 0
