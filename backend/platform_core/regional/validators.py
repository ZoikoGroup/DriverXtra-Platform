"""Authoritative country and jurisdiction validators for the DriverXtra platform.

Enforces:
- Country support verification (IN, GB).
- ISO 3166-2 jurisdiction validity.
- Strict country and jurisdiction mismatch rejection.
- Free-text country string normalization.
"""

from typing import Optional
import re
from django.core.exceptions import ValidationError
from .choices import CountryCode
from .specs import (
    COUNTRY_SPECIFICATIONS,
    is_supported_country,
    get_supported_country_codes,
    get_country_spec,
)


def normalize_country_code(value: Optional[str]) -> Optional[str]:
    """Normalizes country input (common aliases, full names) to canonical ISO alpha-2 code."""
    if not value or not isinstance(value, str):
        return None

    clean = value.strip().upper()
    if clean in ('IN', 'IND', 'INDIA', 'BHARAT'):
        return CountryCode.IN.value
    if clean in ('GB', 'UK', 'GBR', 'UNITED KINGDOM', 'GREAT BRITAIN', 'ENGLAND', 'SCOTLAND', 'WALES', 'NORTHERN IRELAND'):
        return CountryCode.GB.value

    return clean


def validate_country_code(country_code: Optional[str]) -> str:
    """Validates that country_code is a supported ISO alpha-2 country.

    Raises:
        ValidationError: If country_code is missing or unsupported.
    """
    if not country_code:
        raise ValidationError("Country code is required.")

    normalized = normalize_country_code(country_code)
    if not is_supported_country(normalized):
        supported = ', '.join(get_supported_country_codes())
        raise ValidationError(
            f"Unsupported country '{country_code}'. Supported countries are: {supported}."
        )

    return normalized


def validate_jurisdiction(country_code: Optional[str], jurisdiction: Optional[str]) -> str:
    """Validates that jurisdiction is a valid ISO 3166-2 subdivision of the specified country.

    Strictly enforces that country and jurisdiction match.
    Rejects:
    - Empty or missing jurisdiction.
    - Unsupported country.
    - Jurisdiction belonging to another country (e.g. IN with GB-ENG or GB with IN-TG).
    - Unrecognized jurisdiction for the country.

    Returns:
        Canonical jurisdiction code (e.g. 'IN-TG', 'GB-ENG').

    Raises:
        ValidationError: If validation fails.
    """
    valid_country = validate_country_code(country_code)

    if not jurisdiction or not str(jurisdiction).strip():
        raise ValidationError("Jurisdiction code is required.")

    clean_jurisdiction = str(jurisdiction).strip().upper()
    country_spec = get_country_spec(valid_country)

    # Check if jurisdiction belongs to another supported country (explicit mismatch detection)
    for other_country, other_spec in COUNTRY_SPECIFICATIONS.items():
        if other_country != valid_country and other_spec.is_valid_jurisdiction(clean_jurisdiction):
            raise ValidationError(
                f"Country and jurisdiction mismatch: Jurisdiction '{clean_jurisdiction}' belongs to "
                f"'{other_spec.name}' ({other_country}), not '{country_spec.name}' ({valid_country})."
            )

    # Check if recognized under target country
    if not country_spec.is_valid_jurisdiction(clean_jurisdiction):
        raise ValidationError(
            f"Jurisdiction '{clean_jurisdiction}' is not a valid subdivision for '{country_spec.name}' ({valid_country})."
        )

    return clean_jurisdiction


def derive_country_from_jurisdiction(jurisdiction: Optional[str]) -> Optional[str]:
    """Infers canonical country code from a valid ISO 3166-2 jurisdiction code (e.g. 'GB-ENG' -> 'GB')."""
    if not jurisdiction or not isinstance(jurisdiction, str):
        return None

    clean = jurisdiction.strip().upper()
    for country_code, spec in COUNTRY_SPECIFICATIONS.items():
        if spec.is_valid_jurisdiction(clean):
            return country_code

    # Fallback to standard ISO prefix parsing (e.g. 'IN-TG' -> 'IN')
    if '-' in clean:
        prefix = clean.split('-')[0]
        if is_supported_country(prefix):
            return prefix

    return None


# =============================================================================
# STATUTORY TAX ID VALIDATORS
# =============================================================================

# Statutory Tax ID Regular Expressions
GSTIN_REGEX = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")
UK_VAT_REGEX = re.compile(r"^(?:GB)?([0-9]{9}|[0-9]{12})$")

# Vehicle regional identifiers (WMI prefixes and registration plate patterns)
INDIA_WMI_REGEX = re.compile(r"^M[A-E]", re.IGNORECASE)
UK_WMI_REGEX = re.compile(r"^S[A-M]", re.IGNORECASE)
INDIA_PLATE_REGEX = re.compile(
    r"^(TS|AP|MH|DL|KA|TN|KL|HR|UP|GJ|WB|RJ|MP|PB|BR|JH|CH|UK|GA|OD)[0-9]{1,2}",
    re.IGNORECASE,
)
UK_PLATE_REGEX = re.compile(r"^[A-Z]{2}[0-9]{2}\s?[A-Z]{3}$", re.IGNORECASE)


def validate_gstin_format(gstin: Optional[str]) -> bool:
    """Validates structural format of an Indian GSTIN (15-character statutory format).

    Note: Format validation confirms structure only and does NOT assert active registration
    with the GST portal / tax authority.
    """
    if not gstin or not isinstance(gstin, str):
        return False
    clean = gstin.strip().upper()
    return bool(GSTIN_REGEX.match(clean))


def validate_uk_vat_format(vat_number: Optional[str]) -> bool:
    """Validates structural format of a UK VAT registration number (9 or 12 digits, optional 'GB' prefix).

    Note: Format validation confirms structure only and does NOT assert active registration
    with HMRC.
    """
    if not vat_number or not isinstance(vat_number, str):
        return False
    clean = vat_number.strip().upper().replace(" ", "")
    return bool(UK_VAT_REGEX.match(clean))


def derive_regional_context_for_vehicle_and_buyer(vehicle=None, buyer=None) -> dict:
    """Derives reliable regional country, currency, and odometer unit for a vehicle and its owner.

    Sources evaluated in strict priority order (authoritative stored context only):
    1. Past platform-verified service records or workshop bookings for the vehicle.
    2. Active organisation membership of the buyer/owner (IN -> INR, GB -> GBP).
    3. Approved seller applications of the buyer/owner (IN -> INR, GB -> GBP).
    4. Buyer order history (shipping country/currency).

    Odometer unit is derived strictly from stored vehicle cluster preference, or the
    authoritative country specification (km for IN, mi for GB).
    Legal/financial jurisdiction and currency are NEVER inferred from VIN prefixes,
    registration plates, or odometer units.

    Returns:
        dict with keys 'country', 'currency', 'odometer_unit'. Any key may be None if indeterminate.
    """
    result = {'country': None, 'currency': None, 'odometer_unit': None}

    # 1. Stored vehicle odometer unit
    if vehicle and getattr(vehicle, 'odometer_unit', None):
        result['odometer_unit'] = str(vehicle.odometer_unit).strip().lower()

    # 2. Existing verified records on the vehicle
    if vehicle:
        latest_record = (
            vehicle.service_records.filter(currency__isnull=False)
            .exclude(currency='')
            .order_by('-service_date', '-created_at')
            .first()
            if hasattr(vehicle, 'service_records')
            else None
        )
        if latest_record and latest_record.currency:
            result['currency'] = latest_record.currency
            if latest_record.currency == 'INR':
                result['country'] = 'IN'
            elif latest_record.currency == 'GBP':
                result['country'] = 'GB'

        if not result['currency']:
            latest_booking = (
                vehicle.workshop_bookings.filter(workshop__isnull=False)
                .select_related('workshop')
                .order_by('-created_at')
                .first()
                if hasattr(vehicle, 'workshop_bookings')
                else None
            )
            if latest_booking and latest_booking.workshop:
                result['currency'] = latest_booking.workshop.currency
                result['country'] = latest_booking.workshop.country

    user = buyer or (getattr(vehicle, 'user', None) if vehicle else None)

    # 3. User's active organisation memberships
    if not result['currency'] and user and hasattr(user, 'organisation_memberships'):
        org_membership = (
            user.organisation_memberships.filter(is_active=True)
            .select_related('organisation')
            .order_by('-created_at', '-id')
            .first()
        )
        if org_membership and org_membership.organisation and org_membership.organisation.country:
            org_c = normalize_country_code(org_membership.organisation.country)
            result['country'] = org_c
            result['currency'] = 'INR' if org_c == 'IN' else ('GBP' if org_c == 'GB' else None)

    # 4. User's approved seller applications
    if not result['currency'] and user and hasattr(user, 'seller_applications'):
        app = (
            user.seller_applications.filter(status='APPROVED').order_by('-created_at', '-id').first()
            or user.seller_applications.order_by('-created_at', '-id').first()
        )
        if app and app.country:
            norm_c = normalize_country_code(app.country)
            result['country'] = norm_c
            result['currency'] = 'INR' if norm_c == 'IN' else ('GBP' if norm_c == 'GB' else None)

    # 5. User's buyer orders
    if not result['currency'] and user and hasattr(user, 'buyer_orders'):
        latest_order = user.buyer_orders.exclude(currency='').order_by('-created_at', '-id').first()
        if latest_order:
            result['currency'] = latest_order.currency
            if latest_order.shipping_country:
                result['country'] = normalize_country_code(latest_order.shipping_country)

    # 6. Default odometer unit from authoritative country if not already set on vehicle
    if not result['odometer_unit'] and result['country']:
        if result['country'] == 'IN':
            result['odometer_unit'] = 'km'
        elif result['country'] == 'GB':
            result['odometer_unit'] = 'mi'

    return result

