"""ENG-04a — non-binding adapter from a marketplace checkout calculation to the commercial quote engine.

Purpose: prove that a supported, single-seller checkout calculation can be represented exactly in the existing
commercial QuoteRequest / compute_quote model, and surface the cases that cannot, without changing checkout.

Hard constraints (by design, not configuration):
- Always calls ``compute_quote(..., binding=False)``: a preview that persists nothing (no QuoteSnapshot,
  QuoteLine, role snapshot or outbox event) and never activates a price, role, SKU, payment mode or market.
- NOT wired into checkout, payment or order flows. Nothing in the request path imports this module.
- Money is converted from major to minor units exactly; any amount that is not a whole number of minor
  units is rejected (``FRACTIONAL_MINOR_UNIT``). Nothing is rounded.
- Unsupported checkout shapes are rejected with explicit reason codes instead of being approximated:
  FX-converted prices, multi-seller carts and inconsistent totals.
"""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional

from apps.commercial.choices import PayerRoleChoices, VerticalChoices
from apps.commercial.errors import CommercialRuleViolation
from apps.commercial.money import currency_exponent, normalize_currency
from apps.commercial.services.quotes import FeeItem, QuoteComputation, QuoteRequest, compute_quote

# Reason codes returned when a checkout calculation cannot be represented as a quote preview.
FX_CONVERTED_PRICE_NOT_SUPPORTED = 'FX_CONVERTED_PRICE_NOT_SUPPORTED'
MULTI_SELLER_NOT_SUPPORTED = 'MULTI_SELLER_NOT_SUPPORTED'
FRACTIONAL_MINOR_UNIT = 'FRACTIONAL_MINOR_UNIT'
INVALID_AMOUNT = 'INVALID_AMOUNT'
UNSUPPORTED_CURRENCY = 'UNSUPPORTED_CURRENCY'
CHECKOUT_TOTALS_INCONSISTENT = 'CHECKOUT_TOTALS_INCONSISTENT'
LISTING_NOT_FOUND = 'LISTING_NOT_FOUND'
UNIT_PRICE_MISMATCH = 'UNIT_PRICE_MISMATCH'
EMPTY_CALCULATION = 'EMPTY_CALCULATION'


class QuoteAdapterUnsupported(Exception):
    """Raised internally when a value or checkout shape cannot be mapped exactly."""

    def __init__(self, reason_code: str, reason: str):
        super().__init__(reason)
        self.reason_code = reason_code
        self.reason = reason


@dataclass
class CheckoutQuotePreview:
    """Outcome of mapping a checkout calculation into a non-binding commercial quote preview."""

    supported: bool
    reason_code: Optional[str] = None
    reason: str = ''
    checkout_total_minor: Optional[int] = None
    quote_request: Optional[QuoteRequest] = None
    computation: Optional[QuoteComputation] = None
    blocking_reasons: List[dict] = field(default_factory=list)

    @property
    def totals_match(self) -> bool:
        return (
            self.computation is not None
            and self.checkout_total_minor is not None
            and self.computation.customer_total_minor == self.checkout_total_minor
        )


def to_minor_units(amount: Any, currency: str) -> int:
    """Exact major-to-minor conversion using the commercial currency exponent. Never rounds.

    Accepts ``Decimal``, ``int`` or a decimal string (as returned by the checkout API). Floats are rejected
    because they cannot represent money exactly.
    """
    try:
        code = normalize_currency(currency)
        exponent = currency_exponent(code)
    except CommercialRuleViolation as exc:
        raise QuoteAdapterUnsupported(UNSUPPORTED_CURRENCY, exc.message) from exc

    if isinstance(amount, bool) or isinstance(amount, float):
        raise QuoteAdapterUnsupported(INVALID_AMOUNT, f'Amount {amount!r} must be a Decimal, int or decimal string.')
    try:
        value = Decimal(str(amount).strip()) if not isinstance(amount, Decimal) else amount
    except (InvalidOperation, ValueError) as exc:
        raise QuoteAdapterUnsupported(INVALID_AMOUNT, f'Amount {amount!r} is not a valid decimal.') from exc
    if not value.is_finite():
        raise QuoteAdapterUnsupported(INVALID_AMOUNT, f'Amount {amount!r} is not finite.')
    if value < 0:
        raise QuoteAdapterUnsupported(INVALID_AMOUNT, f'Amount {amount!r} cannot be negative.')

    scaled = value.scaleb(exponent)
    if scaled != scaled.to_integral_value():
        raise QuoteAdapterUnsupported(
            FRACTIONAL_MINOR_UNIT,
            f'{amount} {code} is not a whole number of minor units (exponent {exponent}); it will not be rounded.',
        )
    return int(scaled)


def build_quote_request(
    *,
    customer,
    country_code: str,
    currency: str,
    role_profile_code: str,
    fee_items: Iterable[FeeItem],
    face_value,
    tax,
    discount=0,
    delivery=0,
    vertical: str = VerticalChoices.PARTS,
    customer_role: str = PayerRoleChoices.BUYER,
    seller_organisation=None,
    tax_determination_reference: str = '',
    terms_version: str = '',
) -> QuoteRequest:
    """Build the existing commercial QuoteRequest from major-unit amounts, converting each exactly."""
    return QuoteRequest(
        customer=customer,
        customer_role=customer_role,
        country_code=country_code,
        vertical=vertical,
        currency=normalize_currency(currency),
        role_profile_code=role_profile_code,
        fee_items=list(fee_items),
        terms_version=terms_version,
        tax_determination_reference=tax_determination_reference,
        face_value_minor=to_minor_units(face_value, currency),
        discount_minor=to_minor_units(discount, currency),
        delivery_minor=to_minor_units(delivery, currency),
        tax_minor=to_minor_units(tax, currency),
        seller_organisation=seller_organisation,
    )


def preview_quote(request: QuoteRequest) -> QuoteComputation:
    """Non-binding preview through the existing engine. binding=False is fixed: nothing is persisted."""
    return compute_quote(request, binding=False)


def _validate_and_resolve_seller(calculation: Dict[str, Any], currency: str, country: str):
    """Checks single-seller, no-FX and unit-price consistency against the existing pricing resolver."""
    from apps.marketplace.models import SparePartListing
    from apps.marketplace.pricing import PriceCalculationError, resolve_authoritative_unit_price

    items = calculation.get('items') or []
    if not items:
        raise QuoteAdapterUnsupported(EMPTY_CALCULATION, 'The checkout calculation has no items.')

    listing_ids = [str(item.get('listing_id')) for item in items]
    listings = {str(l.id): l for l in SparePartListing.objects.filter(id__in=listing_ids).select_related('organisation')}
    missing = [lid for lid in listing_ids if lid not in listings]
    if missing:
        raise QuoteAdapterUnsupported(LISTING_NOT_FOUND, f'Listings not found: {", ".join(missing)}.')

    sellers = {(listings[lid].seller_id, listings[lid].organisation_id) for lid in listing_ids}
    if len(sellers) > 1:
        raise QuoteAdapterUnsupported(
            MULTI_SELLER_NOT_SUPPORTED,
            'The cart contains items from more than one seller; a quote has a single seller of record.',
        )

    for item in items:
        listing = listings[str(item.get('listing_id'))]
        try:
            unit_price, _source_currency, is_converted = resolve_authoritative_unit_price(
                listing=listing, destination_currency=currency, destination_country=country,
            )
        except PriceCalculationError as exc:
            raise QuoteAdapterUnsupported(UNIT_PRICE_MISMATCH, str(exc)) from exc
        if is_converted:
            raise QuoteAdapterUnsupported(
                FX_CONVERTED_PRICE_NOT_SUPPORTED,
                f"'{listing.name}' is priced in {listing.currency} and converted to {currency} at a configured "
                f"exchange rate; FX-converted prices are not quotable.",
            )
        if to_minor_units(unit_price, currency) != to_minor_units(item.get('unit_price'), currency):
            raise QuoteAdapterUnsupported(
                UNIT_PRICE_MISMATCH,
                f"Unit price for '{listing.name}' differs from the authoritative listing price.",
            )

    return listings[listing_ids[0]].organisation


def preview_checkout_quote(
    calculation: Dict[str, Any],
    *,
    customer,
    role_profile_code: str,
    fee_items: Iterable[FeeItem],
    tax_determination_reference: str = '',
) -> CheckoutQuotePreview:
    """Map a checkout preview (the ``/orders/calculate/`` response body) to a non-binding quote preview.

    Supported shape only: single seller, listing-native or stored per-country prices (no FX conversion), and
    totals that are exact in minor units and internally consistent. Checkout has no discount or delivery
    lines today, so both map to zero.
    """
    try:
        currency = normalize_currency(calculation.get('currency'))
    except CommercialRuleViolation as exc:
        return CheckoutQuotePreview(False, UNSUPPORTED_CURRENCY, exc.message)
    country = (calculation.get('country') or '').strip().upper()

    try:
        items = calculation.get('items') or []
        face_minor = sum(to_minor_units(item.get('taxable_amount'), currency) for item in items)
        tax_minor = sum(to_minor_units(item.get('tax_amount'), currency) for item in items)
        subtotal_minor = to_minor_units(calculation.get('subtotal_taxable_amount'), currency)
        total_tax_minor = to_minor_units(calculation.get('total_tax_amount'), currency)
        checkout_total_minor = to_minor_units(calculation.get('total_amount'), currency)

        if (face_minor, tax_minor) != (subtotal_minor, total_tax_minor) or face_minor + tax_minor != checkout_total_minor:
            raise QuoteAdapterUnsupported(
                CHECKOUT_TOTALS_INCONSISTENT,
                'Checkout line amounts do not add up to the checkout subtotal, tax and total.',
            )

        seller_organisation = _validate_and_resolve_seller(calculation, currency, country)
        request = build_quote_request(
            customer=customer, country_code=country, currency=currency, role_profile_code=role_profile_code,
            fee_items=fee_items, face_value=calculation.get('subtotal_taxable_amount'),
            tax=calculation.get('total_tax_amount'), seller_organisation=seller_organisation,
            tax_determination_reference=tax_determination_reference,
        )
    except QuoteAdapterUnsupported as exc:
        return CheckoutQuotePreview(False, exc.reason_code, exc.reason)

    try:
        computation = preview_quote(request)
    except CommercialRuleViolation as exc:
        # The engine itself refused the preview (for example no rate exists for a fee SKU).
        return CheckoutQuotePreview(False, exc.rule, exc.message, checkout_total_minor=checkout_total_minor,
                                    quote_request=request)

    return CheckoutQuotePreview(
        True, checkout_total_minor=checkout_total_minor, quote_request=request, computation=computation,
        blocking_reasons=list(computation.blocking_reasons),
    )
