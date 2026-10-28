from decimal import Decimal
from typing import Dict, Any, Tuple, Optional
from django.conf import settings
from apps.marketplace.tax import quantize_currency, calculate_gst_breakdown


class PriceCalculationError(Exception):
    """Exception raised when an item cannot be safely priced or converted for checkout."""
    def __init__(self, message: str, listing_id: Optional[str] = None, listing_name: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.listing_id = listing_id
        self.listing_name = listing_name


SUPPORTED_DESTINATION_CURRENCIES: Dict[str, str] = {
    "IN": "INR",
    "GB": "GBP",
}


def normalize_destination_country(country_str: Optional[str]) -> Tuple[str, str]:
    """
    Normalizes a destination country string to (country_code, canonical_name).
    Currently supports India ('IN') and United Kingdom ('GB').
    Raises PriceCalculationError if destination country is not supported.
    """
    if not country_str or not country_str.strip():
        # Default destination is India
        return "IN", "India"

    raw = country_str.strip().upper()
    if raw in ("IN", "INDIA", "BHARAT"):
        return "IN", "India"
    elif raw in ("GB", "UK", "UNITED KINGDOM", "GREAT BRITAIN", "ENGLAND", "SCOTLAND", "WALES", "NORTHERN IRELAND"):
        return "GB", "United Kingdom"
    else:
        raise PriceCalculationError(
            f"Delivery to '{country_str}' is not supported. DriverXtra currently supports delivery to India (INR) and the United Kingdom (GBP)."
        )


def get_required_currency_for_country(country_str: Optional[str]) -> str:
    """
    Returns the required checkout currency strictly determined by destination country:
    - India -> 'INR'
    - United Kingdom -> 'GBP'
    """
    country_code, _ = normalize_destination_country(country_str)
    return SUPPORTED_DESTINATION_CURRENCIES[country_code]


def get_configured_exchange_rate(from_currency: str, to_currency: str) -> Optional[Decimal]:
    """
    Retrieves the explicitly configured server-side exchange rate between two currencies.
    Returns None if conversion is not configured or disabled.
    Never returns a fallback 1:1 rate between different currencies.
    """
    from_c = (from_currency or "").strip().upper()
    to_c = (to_currency or "").strip().upper()

    if not from_c or not to_c:
        return None

    if from_c == to_c:
        return Decimal("1.00")

    rates = getattr(settings, 'CURRENCY_EXCHANGE_RATES', None)
    if not rates or not isinstance(rates, dict):
        return None

    # Check tuple key (from_c, to_c)
    rate = rates.get((from_c, to_c))
    if rate is None:
        # Check string key e.g. "GBP_INR" or "GBP/INR"
        rate = rates.get(f"{from_c}_{to_c}")
    if rate is None:
        rate = rates.get(f"{from_c}/{to_c}")

    if rate is None:
        return None

    try:
        dec_rate = Decimal(str(rate))
        if dec_rate <= Decimal("0.00"):
            return None
        return dec_rate
    except Exception:
        return None


def resolve_authoritative_unit_price(
    listing: Any,
    destination_currency: str,
    destination_country: Optional[str] = None,
) -> Tuple[Decimal, str, bool]:
    """
    Resolves the authoritative unit price in the required destination currency:
    1. If listing is natively priced in destination_currency, use listing.price.
    2. If listing has explicit country-specific price (e.g. listing.country_prices dict), use that stored price.
    3. If listing only has one currency, convert using explicitly configured server-side exchange-rate service.
    4. If conversion is not configured or fails, raises PriceCalculationError with clear explanation.

    Returns:
        (authoritative_price_decimal, source_currency, is_converted)
    """
    target_currency = (destination_currency or "").strip().upper()
    listing_currency = getattr(listing, 'currency', 'INR').strip().upper()
    base_price = Decimal(str(getattr(listing, 'price', '0.00')))

    if base_price <= Decimal('0.00'):
        raise PriceCalculationError(
            f"Item '{getattr(listing, 'name', 'Spare Part')}' does not have a valid positive listing price.",
            listing_id=str(getattr(listing, 'id', '')),
            listing_name=getattr(listing, 'name', ''),
        )

    # 1. Native currency match: use stored listing price
    if listing_currency == target_currency:
        return quantize_currency(base_price), listing_currency, False

    # 2. Stored country-specific / currency-specific price override
    country_prices = getattr(listing, 'country_prices', None)
    if isinstance(country_prices, dict) and country_prices:
        # Check by target currency code (e.g. "INR" or "GBP")
        if target_currency in country_prices and country_prices[target_currency] is not None:
            try:
                stored_override = quantize_currency(Decimal(str(country_prices[target_currency])))
                if stored_override > Decimal('0.00'):
                    return stored_override, target_currency, False
            except Exception:
                pass
        # Check by destination country name / code if provided
        if destination_country:
            try:
                code, name = normalize_destination_country(destination_country)
                for k in (code, name, code.lower(), name.lower()):
                    if k in country_prices and country_prices[k] is not None:
                        stored_override = quantize_currency(Decimal(str(country_prices[k])))
                        if stored_override > Decimal('0.00'):
                            return stored_override, target_currency, False
            except Exception:
                pass

    # 3. Server-side exchange-rate conversion service
    rate = get_configured_exchange_rate(listing_currency, target_currency)
    if rate is None:
        raise PriceCalculationError(
            f"Listing '{getattr(listing, 'name', 'Spare Part')}' currency ({listing_currency}) does not match order currency ({target_currency}). Item lacks a valid price for {target_currency} and currency conversion from {listing_currency} to {target_currency} is not configured.",
            listing_id=str(getattr(listing, 'id', '')),
            listing_name=getattr(listing, 'name', ''),
        )

    # Convert using Decimal arithmetic and quantize to minor currency units (paise/pence)
    converted = quantize_currency(base_price * rate)
    if converted <= Decimal('0.00'):
        raise PriceCalculationError(
            f"Item '{getattr(listing, 'name', 'Spare Part')}' cannot be safely converted to {target_currency}.",
            listing_id=str(getattr(listing, 'id', '')),
            listing_name=getattr(listing, 'name', ''),
        )

    return converted, listing_currency, True


def calculate_item_tax_breakdown(
    unit_price: Decimal,
    quantity: int,
    listing: Any,
    country_code: str,
    place_of_supply: Optional[str] = None,
    seller_state: Optional[str] = None,
    shipping_state: Optional[str] = None,
    shipping_city: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Computes line-level financial amounts and taxes based on destination country rules.
    - India: Statutory GST breakdown (CGST, SGST, IGST) via CBIC rules.
    - UK: Kept cleanly isolated from Indian GST; applies UK VAT when configured.
    """
    line_taxable = quantize_currency(unit_price * quantity)

    if country_code == 'GB':
        # UK Order: Indian GST (CGST/SGST/IGST) strictly does not apply.
        # UK VAT is managed separately.
        uk_vat_rate = Decimal(str(getattr(settings, 'UK_VAT_RATE', Decimal('0.00'))))
        if uk_vat_rate > Decimal('0.00'):
            line_tax = quantize_currency(line_taxable * (uk_vat_rate / Decimal('100.00')))
        else:
            line_tax = Decimal('0.00')

        line_total = line_taxable + line_tax
        return {
            "gst_rate": uk_vat_rate,
            "taxable_amount": line_taxable,
            "cgst_amount": Decimal('0.00'),
            "sgst_amount": Decimal('0.00'),
            "igst_amount": Decimal('0.00'),
            "tax_amount": line_tax,
            "total_amount": line_total,
            "effective_place_of_supply": shipping_state or shipping_city or 'UK',
        }
    else:
        # India Order: Statutory GST breakdown (CGST/SGST/IGST)
        gst_rate = getattr(listing, 'gst_rate', None) or Decimal('0.00')
        effective_place_of_supply = place_of_supply or shipping_state or 'MH'

        breakdown = calculate_gst_breakdown(
            price=line_taxable,
            gst_rate=gst_rate,
            place_of_supply=effective_place_of_supply,
            seller_state=seller_state,
        )

        return {
            "gst_rate": gst_rate,
            "taxable_amount": line_taxable,
            "cgst_amount": breakdown['cgst_amount'],
            "sgst_amount": breakdown['sgst_amount'],
            "igst_amount": breakdown['igst_amount'],
            "tax_amount": breakdown['gst_amount'],
            "total_amount": breakdown['total_price'],
            "effective_place_of_supply": effective_place_of_supply,
        }
