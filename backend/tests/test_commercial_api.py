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
