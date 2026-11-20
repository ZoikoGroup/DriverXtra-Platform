"""R1 Commercial Control Plane — API tests (permissions, response contracts, closed-by-default behaviour)."""

import pytest
from rest_framework.test import APIClient

from apps.commercial.choices import GateCapabilityChoices as Cap, GateStatusChoices as G
from apps.commercial.models import CommercialSku, CountryGate, QuoteSnapshot
from apps.commercial.permissions import COMMERCIAL_PERMISSION_CODES
from apps.identity.models import Permission
from platform_core.events.models import OutboxEvent
from tests.test_commercial_control_plane import (  # noqa: F401  (fixtures re-exported for pytest)
    approve_profile,
    approve_rate,
    approve_sku,
    checker,
    customer,
    maker,
    make_profile,
    make_rate,
    make_sku,
    open_gate,
    subscription_market,
)

API = '/api/v1/commercial'


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def quote_payload(**overrides):
    payload = {
        'country_code': 'GB', 'vertical': 'VEHICLES', 'currency': 'GBP', 'customer_role': 'DEALER',
        'role_profile_code': 'GB-VEH-SOFTWARE',
        'fee_items': [{'sku_code': 'DX-DEAL-GROWTH', 'payer_role': 'DEALER'}],
        'terms_version': 'DEALER-TERMS-TEST-1', 'tax_determination_reference': 'TAXDET-TEST-1',
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
def test_commercial_permissions_are_seeded_by_migration():
    assert set(Permission.objects.filter(code__in=COMMERCIAL_PERMISSION_CODES).values_list('code', flat=True)) == set(
        COMMERCIAL_PERMISSION_CODES)


@pytest.mark.django_db
@pytest.mark.parametrize('path', ['/admin/skus/', '/admin/rate-schedules/', '/admin/role-profiles/',
                                  '/admin/country-gates/', '/admin/quotes/', '/admin/outbox/'])
def test_admin_endpoints_require_commercial_staff(api_client, buyer_user, staff_user, seller_user, path):
    assert api_client.get(API + path).status_code == 401
    assert client_for(buyer_user).get(API + path).status_code == 403
    assert client_for(seller_user).get(API + path).status_code == 403
    # Staff without a commercial permission (default verification officer scope) are denied.
    assert client_for(staff_user).get(API + path).status_code == 403


@pytest.mark.django_db
def test_create_sku_is_always_draft_and_rules_return_structured_errors(maker):
    client = client_for(maker)
    response = client.post(f'{API}/admin/skus/', {
        'sku_code': 'dx-deal-launch', 'name': 'Dealer Launch', 'family': 'SUBSCRIPTION', 'revenue_code': 'SUB-01',
        'vertical': 'VEHICLES', 'fee_basis': 'RECURRING_FLAT', 'billing_interval': 'MONTHLY', 'status': 'APPROVED',
    }, format='json')
    assert response.status_code == 201
    assert response.data['status'] == 'DRAFT'
    assert response.data['sku_code'] == 'DX-DEAL-LAUNCH'

    approve = client.post(f"{API}/admin/skus/{response.data['id']}/status/",
                          {'to_status': 'APPROVED', 'reason': 'x', 'approval_reference': 'CFO-1'}, format='json')
    assert approve.status_code == 409
    assert approve.data['status'] == 'error'
    assert approve.data['details']['rule'] == 'SEPARATION_OF_DUTIES'

    invalid = client.post(f"{API}/admin/skus/{response.data['id']}/status/", {'to_status': 'LIVE', 'reason': 'x'},
                          format='json')
    assert invalid.status_code == 400

    bad_choice = client.post(f'{API}/admin/skus/', {'sku_code': 'DX-BAD', 'name': 'x', 'family': 'NOPE',
                                                    'revenue_code': 'SUB-01', 'vertical': 'VEHICLES',
                                                    'fee_basis': 'RECURRING_FLAT'}, format='json')
    assert bad_choice.status_code == 400


@pytest.mark.django_db
def test_approved_sku_cannot_be_patched_via_api(maker, checker):
    sku = approve_sku(make_sku(maker), checker)
    response = client_for(maker).patch(f'{API}/admin/skus/{sku.id}/', {'name': 'Renamed'}, format='json')
    assert response.status_code == 409
    assert response.data['details']['rule'] == 'SKU_FROZEN'


@pytest.mark.django_db
def test_gate_api_creates_closed_gates_and_blocks_regulated_activation(maker, checker):
    client = client_for(maker)
    response = client.post(f'{API}/admin/country-gates/', {
        'country_code': 'gb', 'vertical': 'FINANCE_INSURANCE', 'capability': 'REGULATED_REFERRAL',
        'allowed_currencies': ['GBP'], 'tax_schedule_reference': 'TAX', 'status': 'ENABLED',
    }, format='json')
    assert response.status_code == 201
    assert (response.data['status'], response.data['is_open'], response.data['is_regulated']) == ('DESIGNED', False, True)
    gate_id = response.data['id']

    duplicate = client.post(f'{API}/admin/country-gates/', {
        'country_code': 'GB', 'vertical': 'FINANCE_INSURANCE', 'capability': 'REGULATED_REFERRAL'}, format='json')
    assert duplicate.status_code == 409

    for step in ('LEGALLY_REVIEWED', 'PARTNER_VERIFIED', 'FINANCE_SIGNED', 'TECHNICAL_REHEARSED'):
        step_response = client.post(f'{API}/admin/country-gates/{gate_id}/transition/',
                                    {'to_status': step, 'reason': 'ok', 'evidence_reference': f'E-{step}'}, format='json')
        assert step_response.status_code == 200, step_response.data
    enable = client_for(checker).post(f'{API}/admin/country-gates/{gate_id}/transition/',
                                      {'to_status': 'ENABLED', 'reason': 'go'}, format='json')
    assert enable.status_code == 409
    assert enable.data['details']['rule'] == 'REGULATED_GATE_LOCKED'

    detail = client.get(f'{API}/admin/country-gates/{gate_id}/')
    assert detail.data['status'] == 'TECHNICAL_REHEARSED'
    assert len(detail.data['transitions']) == 4


@pytest.mark.django_db
def test_public_plans_require_market_and_stay_empty_until_discovery_gate_enabled(api_client, subscription_market,
                                                                                 maker, checker):
    assert api_client.get(f'{API}/plans/').status_code == 400

    # Binding-quote gate is open in the fixture, but DISCOVERY is not: nothing is publicly displayed.
    closed = api_client.get(f'{API}/plans/', {'market': 'GB'})
    assert closed.status_code == 200
    assert closed.data['plans'] == [] and closed.data['activated_verticals'] == []

    open_gate(maker, checker, capability=Cap.DISCOVERY)
    response = api_client.get(f'{API}/plans/', {'market': 'gb'})
    assert response.data['activated_verticals'] == ['VEHICLES']
    [plan] = response.data['plans']
    assert plan['sku_code'] == 'DX-DEAL-GROWTH'
    assert plan['rates'][0]['flat_amount_minor'] == 24900
    assert plan['rates'][0]['currency'] == 'GBP' and plan['rates'][0]['currency_exponent'] == 2

    assert api_client.get(f'{API}/plans/', {'market': 'FR'}).data['plans'] == []


@pytest.mark.django_db
def test_quote_api_rejects_when_gate_closed(customer, maker):
    make_sku(maker)
    response = client_for(customer).post(f'{API}/quotes/', quote_payload(), format='json')
    assert response.status_code == 409
    assert response.data['details']['rule'] == 'COUNTRY_GATE_CLOSED'
    assert QuoteSnapshot.objects.count() == 0


@pytest.mark.django_db
def test_quote_issue_accept_flow_and_owner_isolation(subscription_market, customer, buyer_user):
    client = client_for(customer)
    issued = client.post(f'{API}/quotes/', quote_payload(), format='json')
    assert issued.status_code == 201, issued.data
    quote = issued.data
    assert (quote['status'], quote['customer_total_minor'], quote['currency_exponent']) == ('ISSUED', 24900, 2)
    assert quote['role_snapshot']['seller_of_record_party'] == 'platform'
    assert [line['line_type'] for line in quote['lines']] == ['PLATFORM_FEE']

    other = client_for(buyer_user)
    assert other.get(f"{API}/quotes/{quote['id']}/").status_code == 404
    assert other.post(f"{API}/quotes/{quote['id']}/accept/",
                      {'terms_hash': quote['terms_hash'], 'consent_notice_version': 'C1'}, format='json').status_code == 404
    assert other.get(f'{API}/quotes/').data['count'] == 0

    mismatch = client.post(f"{API}/quotes/{quote['id']}/accept/",
                           {'terms_hash': 'f' * 64, 'consent_notice_version': 'C1'}, format='json')
    assert mismatch.status_code == 409 and mismatch.data['details']['rule'] == 'TERMS_MISMATCH'

    accepted = client.post(f"{API}/quotes/{quote['id']}/accept/",
                           {'terms_hash': quote['terms_hash'], 'consent_notice_version': 'C1'}, format='json')
    assert accepted.status_code == 200
    assert accepted.data['status'] == 'ACCEPTED'
    assert client.get(f'{API}/quotes/').data['count'] == 1


@pytest.mark.django_db
def test_quote_for_organisation_requires_owner_or_admin(subscription_market, customer, buyer_user, test_organisation):
    response = client_for(buyer_user).post(f'{API}/quotes/', quote_payload(organisation_id=str(test_organisation.id)),
                                           format='json')
    assert response.status_code == 403
    assert response.data['details']['rule'] == 'ORGANISATION_NOT_AUTHORISED'


@pytest.mark.django_db
def test_quote_preview_is_non_binding_and_persists_nothing(maker, customer):
    sku = make_sku(maker)
    make_rate(sku, maker, flat=14900)
    response = client_for(maker).post(f'{API}/admin/quote-preview/', quote_payload(), format='json')
    assert response.status_code == 200, response.data
    assert response.data['binding'] is False
    assert response.data['pricing_label'] == 'NON_BINDING_PREVIEW'
    assert response.data['would_be_binding'] is False
    assert response.data['customer_total_minor'] == 14900
    rules = {reason['rule'] for reason in response.data['blocking_reasons']}
    assert 'COUNTRY_GATE_CLOSED' in rules and 'SKU_NOT_APPROVED' in rules
    assert QuoteSnapshot.objects.count() == 0

    assert client_for(customer).post(f'{API}/admin/quote-preview/', quote_payload(), format='json').status_code == 403


@pytest.mark.django_db
def test_admin_outbox_lists_emitted_events(subscription_market, maker):
    response = client_for(maker).get(f'{API}/admin/outbox/', {'topic': 'commercial.sku.published'})
    assert response.status_code == 200
    assert response.data['count'] == 1
    assert response.data['results'][0]['aggregate_id'] == str(subscription_market['sku'].id)
    assert OutboxEvent.objects.filter(topic='compliance.policy_changed').count() == 5


@pytest.mark.django_db
def test_rate_and_role_profile_api_round_trip(maker, checker):
    sku = approve_sku(make_sku(maker), checker)
    client = client_for(maker)
    rate = client.post(f'{API}/admin/rate-schedules/', {
        'sku': str(sku.id), 'name': 'Test', 'country_code': 'gb', 'currency': 'gbp', 'payer_role': 'DEALER',
        'effective_from': '2099-01-01T00:00:00Z', 'flat_amount_minor': 24900,
    }, format='json')
    assert rate.status_code == 201, rate.data
    assert (rate.data['status'], rate.data['country_code'], rate.data['currency'], rate.data['vertical']) == (
        'DRAFT', 'GB', 'GBP', 'VEHICLES')
    approved = client_for(checker).post(f"{API}/admin/rate-schedules/{rate.data['id']}/status/",
                                        {'to_status': 'APPROVED', 'reason': 'ok', 'approval_reference': 'CFO-9'},
                                        format='json')
    assert approved.status_code == 200 and approved.data['status'] == 'APPROVED'

    profile = client.post(f'{API}/admin/role-profiles/', {
        'code': 'gb-veh-ads', 'name': 'Advertising only', 'profile_type': 'ADVERTISING_ONLY', 'country_code': 'GB',
        'vertical': 'VEHICLES', 'seller_of_record': 'NONE', 'service_performer': 'PLATFORM',
        'platform_role': 'ADVERTISING_PUBLISHER', 'payment_role': 'SUBSCRIPTION_BILLING', 'tax_party': 'PLATFORM',
        'invoice_issuer': 'PLATFORM', 'legal_memo_reference': 'MEMO', 'effective_from': '2026-01-01T00:00:00Z',
    }, format='json')
    assert profile.status_code == 201, profile.data
    assert (profile.data['code'], profile.data['status']) == ('GB-VEH-ADS', 'DRAFT')


# =================================================================================================
# ENG-02 — D02 role-profile approval rules exercised through the admin API.
# Uses the existing PartyRoleProfile workflow; no rule is changed. References such as
# 'LEGAL-MEMO-TEST' / 'GC-REF-1' are test fixtures, not real legal approvals.
# =================================================================================================

def _commercial_staff(email, *permission_codes):
    """Staff user whose only permissions come from an explicit test staff role (no superuser/admin)."""
    import uuid
    from apps.identity.models import RoleChoices, StaffProfile, StaffRole, StaffRolePermission, User

    user = User.objects.create_user(email=email, password='Str0ng-Passw0rd!x', is_staff=True,
                                    is_email_verified=True)
    user.add_role(RoleChoices.STAFF)
    role = StaffRole.objects.create(code=f'COMMERCIAL_TEST_{uuid.uuid4().hex[:8].upper()}',
                                    name='Commercial test role')
    for code in permission_codes:
        StaffRolePermission.objects.create(staff_role=role, permission=Permission.objects.get(code=code))
    StaffProfile.objects.create(user=user, staff_role=role, department='Commercial')
    return user


def _transition(user, profile_id, to_status, reason='Test transition', approval_reference=''):
    payload = {'to_status': to_status, 'reason': reason}
    if approval_reference is not None:
        payload['approval_reference'] = approval_reference
    return client_for(user).post(f'{API}/admin/role-profiles/{profile_id}/status/', payload, format='json')


def _profile_state(profile_id):
    from apps.commercial.models import PartyRoleProfile
    return PartyRoleProfile.objects.get(id=profile_id)


@pytest.mark.django_db
def test_role_profile_approval_requires_commercial_approve_permission(maker):
    profile = make_profile(maker)
    manager = _commercial_staff('commercial.manager@driverxtra.test', 'commercial.manage')

    # Commercial staff without commercial.approve can read the profile but cannot approve or retire it.
    assert client_for(manager).get(f'{API}/admin/role-profiles/{profile.id}/').status_code == 200
    denied = _transition(manager, profile.id, 'APPROVED', approval_reference='GC-REF-1')
    assert denied.status_code == 403
    assert _transition(manager, profile.id, 'RETIRED').status_code == 403
    state = _profile_state(profile.id)
    assert (state.status, state.approved_by_id, state.approval_reference) == ('DRAFT', None, '')

    # Control: a non-superuser staff member granted commercial.approve through a staff role may approve.
    approver = _commercial_staff('commercial.approver@driverxtra.test', 'commercial.approve')
    allowed = _transition(approver, profile.id, 'APPROVED', approval_reference='GC-REF-1')
    assert allowed.status_code == 200, allowed.data
    assert allowed.data['status'] == 'APPROVED'


@pytest.mark.django_db
def test_role_profile_author_cannot_approve_own_profile(maker):
    created = client_for(maker).post(f'{API}/admin/role-profiles/', {
        'code': 'gb-veh-sod', 'name': 'Software-only', 'profile_type': 'SOFTWARE_ONLY', 'country_code': 'GB',
        'vertical': 'VEHICLES', 'seller_of_record': 'PLATFORM', 'service_performer': 'PLATFORM',
        'platform_role': 'SOFTWARE_PROVIDER', 'payment_role': 'SUBSCRIPTION_BILLING', 'tax_party': 'PLATFORM',
        'invoice_issuer': 'PLATFORM', 'legal_memo_reference': 'LEGAL-MEMO-TEST',
        'effective_from': '2026-01-01T00:00:00Z',
    }, format='json')
    assert created.status_code == 201, created.data

    # The author holds commercial.approve (superuser) but separation of duties still blocks self-approval.
    response = _transition(maker, created.data['id'], 'APPROVED', approval_reference='GC-REF-1')
    assert response.status_code == 409
    assert response.data['details']['rule'] == 'SEPARATION_OF_DUTIES'
    state = _profile_state(created.data['id'])
    assert (state.status, state.approved_by_id) == ('DRAFT', None)


@pytest.mark.django_db
@pytest.mark.parametrize('overrides', [
    {'profile_type': 'REGULATED_INTRODUCER'},
    {'profile_type': 'CROSS_BORDER_ORCHESTRATOR'},
    {'profile_type': 'PRINCIPAL_SELLER'},
    {'payment_role': 'PSP_CONDITIONAL_PAYOUT'},
    {'payment_role': 'PARTNER_REGULATED'},
    {'vertical': 'FINANCE_INSURANCE'},
], ids=['regulated-introducer', 'cross-border', 'principal-seller', 'mode-E-conditional-payout',
        'mode-F-partner-regulated', 'finance-insurance-vertical'])
def test_gated_role_profiles_cannot_be_approved(maker, checker, overrides):
    profile = make_profile(maker, code='GB-GATED-TEST', **overrides)
    detail = client_for(checker).get(f'{API}/admin/role-profiles/{profile.id}/')
    assert detail.data['is_gated'] is True

    response = _transition(checker, profile.id, 'APPROVED', approval_reference='GC-REF-1')
    assert response.status_code == 409
    assert response.data['details']['rule'] == 'GATED_ROLE_PROFILE'
    state = _profile_state(profile.id)
    assert (state.status, state.approved_by_id, state.approval_reference) == ('DRAFT', None, '')


@pytest.mark.django_db
@pytest.mark.parametrize('memo', ['', '   '], ids=['empty', 'whitespace'])
def test_role_profile_approval_requires_legal_memo_reference(maker, checker, memo):
    profile = make_profile(maker, legal_memo_reference=memo)
    response = _transition(checker, profile.id, 'APPROVED', approval_reference='GC-REF-1')
    assert response.status_code == 400
    assert response.data['details']['rule'] == 'LEGAL_MEMO_REQUIRED'
    assert _profile_state(profile.id).status == 'DRAFT'


@pytest.mark.django_db
@pytest.mark.parametrize('approval_reference', [None, '', '   '], ids=['missing', 'empty', 'whitespace'])
def test_role_profile_approval_requires_approval_reference(maker, checker, approval_reference):
    profile = make_profile(maker)
    response = _transition(checker, profile.id, 'APPROVED', approval_reference=approval_reference)
    assert response.status_code == 400
    assert response.data['details']['rule'] == 'APPROVAL_REFERENCE_REQUIRED'
    state = _profile_state(profile.id)
    assert (state.status, state.approved_by_id, state.approval_reference) == ('DRAFT', None, '')


@pytest.mark.django_db
def test_role_profile_transition_requires_reason(maker, checker):
    profile = make_profile(maker)
    response = _transition(checker, profile.id, 'APPROVED', reason='', approval_reference='GC-REF-1')
    assert response.status_code == 400
    assert response.data['details']['rule'] == 'REASON_REQUIRED'
    assert _profile_state(profile.id).status == 'DRAFT'


@pytest.mark.django_db
def test_valid_role_profile_approval_succeeds_and_is_audited(maker, checker):
    from platform_core.audit.models import AuditLog

    profile = make_profile(maker)
    response = _transition(checker, profile.id, 'APPROVED', reason='GC and CFO sign-off (test)',
                           approval_reference='  GC-REF-1  ')
    assert response.status_code == 200, response.data
    data = response.data
    assert (data['status'], data['version'], data['approval_reference']) == ('APPROVED', 1, 'GC-REF-1')
    assert data['approved_by_email'] == checker.email
    assert data['created_by_email'] == maker.email
    assert data['approved_at'] is not None
    assert data['status_reason'] == 'GC and CFO sign-off (test)'
    assert AuditLog.objects.filter(event_type='commercial.role_profile.approved', resource_id=str(profile.id),
                                   actor_id=checker.id).count() == 1

    # Approval is one-way: approving again is not a valid transition.
    again = _transition(checker, profile.id, 'APPROVED', approval_reference='GC-REF-2')
    assert again.status_code == 409
    assert again.data['details']['rule'] == 'INVALID_TRANSITION'
    assert _profile_state(profile.id).approval_reference == 'GC-REF-1'


@pytest.mark.django_db
def test_role_profile_versioning_supersedes_and_retirement_is_terminal(maker, checker):
    v1 = make_profile(maker)
    assert _transition(checker, v1.id, 'APPROVED', approval_reference='GC-REF-1').status_code == 200

    # An approved version is frozen.
    frozen = client_for(maker).patch(f'{API}/admin/role-profiles/{v1.id}/', {'name': 'Renamed'}, format='json')
    assert frozen.status_code == 409
    assert frozen.data['details']['rule'] == 'ROLE_PROFILE_FROZEN'

    # A commercial manager (no approve permission) creates v2 as a DRAFT copy.
    manager = _commercial_staff('commercial.versioner@driverxtra.test', 'commercial.manage')
    v2 = client_for(manager).post(f'{API}/admin/role-profiles/{v1.id}/new-version/', {}, format='json')
    assert v2.status_code == 201, v2.data
    assert (v2.data['code'], v2.data['version'], v2.data['status']) == (v1.code, 2, 'DRAFT')
    assert v2.data['legal_memo_reference'] == v1.legal_memo_reference
    assert v2.data['created_by_email'] == manager.email
    assert _profile_state(v1.id).status == 'APPROVED'  # still the live version until v2 is approved

    # Approving v2 (by someone other than its author) supersedes v1.
    approved_v2 = _transition(checker, v2.data['id'], 'APPROVED', approval_reference='GC-REF-2')
    assert approved_v2.status_code == 200, approved_v2.data
    old = _profile_state(v1.id)
    assert (old.status, old.status_reason) == ('RETIRED', 'Superseded by v2.')

    # Retirement requires commercial.approve, is allowed for an approved version and is terminal.
    assert _transition(manager, v2.data['id'], 'RETIRED').status_code == 403
    retired = _transition(checker, v2.data['id'], 'RETIRED', reason='Withdrawn (test)')
    assert retired.status_code == 200 and retired.data['status'] == 'RETIRED'
    for target in ('APPROVED', 'DRAFT'):
        response = _transition(checker, v2.data['id'], target, approval_reference='GC-REF-3')
        assert response.status_code in (400, 409)
        assert response.data['details']['rule'] in ('INVALID_TRANSITION', 'INVALID_STATUS')
    assert _profile_state(v2.data['id']).status == 'RETIRED'


@pytest.mark.django_db
def test_draft_role_profile_can_be_retired_without_approval(maker, checker):
    profile = make_profile(maker)
    response = _transition(checker, profile.id, 'RETIRED', reason='Not pursued (test)')
    assert response.status_code == 200
    state = _profile_state(profile.id)
    assert (state.status, state.approved_by_id) == ('RETIRED', None)
