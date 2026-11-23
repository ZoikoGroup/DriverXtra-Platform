"""ENG-04a — non-binding checkout → commercial quote adapter.

All commercial fixtures here are DRAFT (SKU, rate, role profile) and no country gate is created or opened:
nothing is approved or activated. Amounts and the 8% rate are test fixtures (Appendix A illustration),
not approved prices.
"""

from decimal import Decimal
from pathlib import Path

import pytest
from django.conf import settings

from apps.catalogue.models import PartCategory
from apps.commercial.models import PartyRoleSnapshot, QuoteLine, QuoteSnapshot
from apps.commercial.services.quotes import FeeItem
from apps.identity.models import RoleChoices, User
from apps.marketplace import commercial_quote_adapter as adapter
from apps.marketplace.models import ListingStatusChoices, Order, SparePartListing
from platform_core.events.models import OutboxEvent
from tests.test_commercial_control_plane import (  # noqa: F401  (fixtures re-exported for pytest)
    customer,
    make_profile,
    make_rate,
    make_sku,
    maker,
    seller_org,
)

CALCULATE_URL = "/api/v1/marketplace/orders/calculate/"
PARTS_FEE = [FeeItem('DX-PARTS-TAKE', 'SUPPLIER')]


# --- fixtures -------------------------------------------------------------------------------------

@pytest.fixture
def parts_category(db):
    return PartCategory.objects.create(name="Braking Systems", slug="braking-systems-eng04a")


def _part(seller, category, *, name, mpn, price, currency, gst_rate="0.00"):
    return SparePartListing.objects.create(
        seller=seller, name=name, brand="TestBrand", mpn=mpn, category=category, price=Decimal(price),
        currency=currency, hsn_code="8708", gst_rate=Decimal(gst_rate), status=ListingStatusChoices.APPROVED,
        is_active=True, stock_quantity=10,
    )


@pytest.fixture
def in_part(seller_user, parts_category):
    return _part(seller_user, parts_category, name="Brake Disc (IN)", mpn="ENG04A-IN", price="4000.00",
                 currency="INR", gst_rate="18.00")


@pytest.fixture
def uk_part(seller_user, parts_category):
    return _part(seller_user, parts_category, name="Brake Pads (UK)", mpn="ENG04A-UK", price="120.00",
                 currency="GBP")


@pytest.fixture
def second_seller_in_part(parts_category):
    other = User.objects.create_user(email='second.seller.eng04a@driverxtra.test', password='Str0ng-Passw0rd!x',
                                     is_email_verified=True)
    other.add_role(RoleChoices.SELLER)
    return _part(other, parts_category, name="Brake Hose (IN)", mpn="ENG04A-IN-2", price="500.00",
                 currency="INR", gst_rate="18.00")


def draft_parts_fee(maker, *, country, currency):
    """DRAFT parts take-rate SKU and DRAFT 8% seller-paid rate (never approved)."""
    sku = make_sku(maker, code='DX-PARTS-TAKE', name='Parts platform fee', family='COMMERCE', revenue_code='COM-01',
                   vertical='PARTS', fee_basis='PERCENT_OF_BASE', billing_interval='PER_EVENT',
                   entitlement_type='NONE')
    make_rate(sku, maker, country=country, currency=currency, payer_role='SUPPLIER', bps=800)
    return sku


def draft_parts_profile(maker, *, code, country):
    return make_profile(maker, code=code, country=country, vertical='PARTS', profile_type='FACILITATED_ORDER',
                        seller_of_record='THIRD_PARTY_SELLER', service_performer='NONE',
                        platform_role='MARKETPLACE_FACILITATOR', payment_role='PSP_DIRECT_SETTLEMENT',
                        tax_party='SELLER', invoice_issuer='SELLER')


def calculate(client, part, *, country, currency, extra_items=()):
    items = [{"listing_id": str(part.id), "quantity": 1}] + [
        {"listing_id": str(p.id), "quantity": 1} for p in extra_items
    ]
    payload = {"items": items, "currency": currency, "shipping_country": country}
    if country == "India":
        payload.update({"place_of_supply": "MH", "shipping_state": "MH"})
    res = client.post(CALCULATE_URL, payload, format="json")
    assert res.status_code == 200, res.content
    return res.json()


def persisted_counts():
    return (QuoteSnapshot.objects.count(), QuoteLine.objects.count(), PartyRoleSnapshot.objects.count(),
            OutboxEvent.objects.count())


# --- exact minor-unit conversion ------------------------------------------------------------------

@pytest.mark.parametrize("amount,currency,expected", [
    ("103.20", "GBP", 10320), ("0.01", "GBP", 1), (Decimal("4720.00"), "INR", 472000), (0, "USD", 0),
    ("120", "GBP", 12000), ("7.2", "USD", 720),
])
def test_to_minor_units_is_exact(amount, currency, expected):
    assert adapter.to_minor_units(amount, currency) == expected


@pytest.mark.parametrize("amount,currency,reason_code", [
    ("10.005", "GBP", adapter.FRACTIONAL_MINOR_UNIT),
    ("0.001", "INR", adapter.FRACTIONAL_MINOR_UNIT),
    (10.5, "GBP", adapter.INVALID_AMOUNT),           # floats are never accepted for money
    ("-1.00", "GBP", adapter.INVALID_AMOUNT),
    ("abc", "GBP", adapter.INVALID_AMOUNT),
    ("NaN", "GBP", adapter.INVALID_AMOUNT),
    ("1.00", "XXX", adapter.UNSUPPORTED_CURRENCY),
])
def test_to_minor_units_rejects_instead_of_rounding(amount, currency, reason_code):
    with pytest.raises(adapter.QuoteAdapterUnsupported) as excinfo:
        adapter.to_minor_units(amount, currency)
    assert excinfo.value.reason_code == reason_code


# --- Appendix A golden vector (non-binding, DRAFT data) -------------------------------------------

@pytest.mark.django_db
def test_appendix_a_golden_vector_through_adapter(maker, customer, seller_org):
    """Goods 100.00; discount 10.00; shipping 6.00; tax 7.20; fee 8% of goods net of discount (seller-paid).
    Expected: buyer payable 103.20; fee base 90.00; platform fee 7.20."""
    draft_parts_profile(maker, code='US-PARTS-FACILITATED', country='US')
    draft_parts_fee(maker, country='US', currency='USD')
    before = persisted_counts()

    request = adapter.build_quote_request(
        customer=customer, country_code='US', currency='USD', role_profile_code='US-PARTS-FACILITATED',
        fee_items=PARTS_FEE, face_value='100.00', discount='10.00', delivery='6.00', tax='7.20',
        seller_organisation=seller_org,
    )
    assert (request.face_value_minor, request.discount_minor, request.delivery_minor, request.tax_minor) == (
        10000, 1000, 600, 720)

    computation = adapter.preview_quote(request)
    assert computation.commissionable_base_minor == 9000
    assert computation.platform_fee_minor == 720
    assert computation.customer_total_minor == 10320
    assert [line.amount_minor for line in computation.lines] == [10000, -1000, 600, 720, 720]
    fee_line = computation.lines[-1]
    assert fee_line.line_type == 'PLATFORM_FEE' and fee_line.is_customer_payable is False

    # Non-binding: every activation control is reported as blocking, and nothing was persisted.
    rules = {reason['rule'] for reason in computation.blocking_reasons}
    assert {'COUNTRY_GATE_CLOSED', 'COMMERCIAL_ROLE_MISSING', 'SKU_NOT_APPROVED', 'RATE_NOT_APPROVED',
            'TAX_DETERMINATION_REQUIRED'} <= rules
    assert persisted_counts() == before


# --- real checkout calculations -------------------------------------------------------------------

@pytest.mark.django_db
def test_india_single_seller_checkout_parity(buyer_auth_client, buyer_user, maker, in_part):
    draft_parts_profile(maker, code='IN-PARTS-FACILITATED', country='IN')
    draft_parts_fee(maker, country='IN', currency='INR')
    calc = calculate(buyer_auth_client, in_part, country="India", currency="INR")
    before = persisted_counts()

    preview = adapter.preview_checkout_quote(calc, customer=buyer_user, role_profile_code='IN-PARTS-FACILITATED',
                                             fee_items=PARTS_FEE)
    assert preview.supported, (preview.reason_code, preview.reason)
    assert preview.checkout_total_minor == adapter.to_minor_units(calc["total_amount"], "INR") == 472000
    assert (preview.computation.face_value_minor, preview.computation.tax_minor) == (400000, 72000)
    assert preview.computation.customer_total_minor == preview.checkout_total_minor
    assert preview.totals_match is True
    assert preview.computation.platform_fee_minor == 32000          # 8% of 4000.00, seller-paid
    assert all(not l.is_customer_payable for l in preview.computation.lines if l.line_type == 'PLATFORM_FEE')
    assert preview.blocking_reasons                                  # nothing approved -> never binding
    assert persisted_counts() == before
    assert Order.objects.count() == 0


@pytest.mark.django_db
def test_uk_single_seller_checkout_parity(buyer_auth_client, buyer_user, maker, uk_part):
    draft_parts_profile(maker, code='GB-PARTS-FACILITATED', country='GB')
    draft_parts_fee(maker, country='GB', currency='GBP')
    calc = calculate(buyer_auth_client, uk_part, country="United Kingdom", currency="GBP")
    before = persisted_counts()

    preview = adapter.preview_checkout_quote(calc, customer=buyer_user, role_profile_code='GB-PARTS-FACILITATED',
                                             fee_items=PARTS_FEE)
    assert preview.supported, (preview.reason_code, preview.reason)
    assert preview.checkout_total_minor == adapter.to_minor_units(calc["total_amount"], "GBP")
    assert preview.totals_match is True
    assert preview.computation.currency == 'GBP' and preview.computation.country_code == 'GB'
    assert persisted_counts() == before


@pytest.mark.django_db
def test_fx_converted_checkout_is_rejected(buyer_auth_client, buyer_user, maker, in_part):
    assert settings.CURRENCY_EXCHANGE_RATES  # checkout converts INR-priced parts for UK delivery
    draft_parts_fee(maker, country='GB', currency='GBP')
    calc = calculate(buyer_auth_client, in_part, country="United Kingdom", currency="GBP")

    preview = adapter.preview_checkout_quote(calc, customer=buyer_user, role_profile_code='GB-PARTS-FACILITATED',
                                             fee_items=PARTS_FEE)
    assert (preview.supported, preview.reason_code) == (False, adapter.FX_CONVERTED_PRICE_NOT_SUPPORTED)
    assert preview.computation is None


@pytest.mark.django_db
def test_multi_seller_checkout_is_rejected(buyer_auth_client, buyer_user, maker, in_part, second_seller_in_part):
    draft_parts_fee(maker, country='IN', currency='INR')
    calc = calculate(buyer_auth_client, in_part, country="India", currency="INR",
                     extra_items=[second_seller_in_part])

    preview = adapter.preview_checkout_quote(calc, customer=buyer_user, role_profile_code='IN-PARTS-FACILITATED',
                                             fee_items=PARTS_FEE)
    assert (preview.supported, preview.reason_code) == (False, adapter.MULTI_SELLER_NOT_SUPPORTED)
    assert preview.computation is None


@pytest.mark.django_db
@pytest.mark.parametrize("mutate,reason_code", [
    (lambda c: c.update(total_amount="4720.005"), adapter.FRACTIONAL_MINOR_UNIT),
    (lambda c: c["items"][0].update(tax_amount="720.001"), adapter.FRACTIONAL_MINOR_UNIT),
    (lambda c: c.update(total_amount="4721.00"), adapter.CHECKOUT_TOTALS_INCONSISTENT),
    (lambda c: c["items"][0].update(unit_price="3999.00"), adapter.UNIT_PRICE_MISMATCH),
], ids=["fractional-total", "fractional-line-tax", "inconsistent-total", "tampered-unit-price"])
def test_unrepresentable_calculations_are_rejected(buyer_auth_client, buyer_user, maker, in_part, mutate,
                                                   reason_code):
    draft_parts_fee(maker, country='IN', currency='INR')
    calc = calculate(buyer_auth_client, in_part, country="India", currency="INR")
    mutate(calc)
    preview = adapter.preview_checkout_quote(calc, customer=buyer_user, role_profile_code='IN-PARTS-FACILITATED',
                                             fee_items=PARTS_FEE)
    assert (preview.supported, preview.reason_code) == (False, reason_code)
    assert preview.computation is None


@pytest.mark.django_db
def test_engine_refusal_is_reported_not_raised(buyer_auth_client, buyer_user, in_part):
    """No rate exists for the fee SKU: the existing engine refuses and the adapter reports its rule."""
    calc = calculate(buyer_auth_client, in_part, country="India", currency="INR")
    preview = adapter.preview_checkout_quote(calc, customer=buyer_user, role_profile_code='IN-PARTS-FACILITATED',
                                             fee_items=PARTS_FEE)
    assert preview.supported is False
    assert preview.reason_code == 'SKU_NOT_FOUND'


# --- never binding, never wired -------------------------------------------------------------------

@pytest.mark.django_db
def test_adapter_only_calls_non_binding_preview(buyer_auth_client, buyer_user, maker, in_part, monkeypatch):
    from apps.commercial.services import quotes

    draft_parts_fee(maker, country='IN', currency='INR')
    calc = calculate(buyer_auth_client, in_part, country="India", currency="INR")
    calls = []
    real_compute = adapter.compute_quote

    def spy(request, *, binding, at=None):
        calls.append(binding)
        return real_compute(request, binding=binding, at=at)

    def forbidden(*args, **kwargs):
        raise AssertionError('issue_quote must never be called by the adapter')

    monkeypatch.setattr(adapter, 'compute_quote', spy)
    monkeypatch.setattr(quotes, 'issue_quote', forbidden)
    preview = adapter.preview_checkout_quote(calc, customer=buyer_user, role_profile_code='IN-PARTS-FACILITATED',
                                             fee_items=PARTS_FEE)
    assert preview.supported
    assert calls == [False]


def test_adapter_is_not_wired_into_runtime_code():
    apps_dir = Path(settings.BASE_DIR) / 'apps'
    references = [
        str(path.relative_to(apps_dir)) for path in apps_dir.rglob('*.py')
        if path.name != 'commercial_quote_adapter.py'
        and 'commercial_quote_adapter' in path.read_text(encoding='utf-8')
    ]
    assert references == []
