"""
Commercial pricing, duration calculation, and digital advertising tax engine for DriverXtra.

Phase 7.2:
- Supports standard fixed-duration advertising packages (7d, 14d, 30d) and custom durations (3-90d).
- All financial calculations execute strictly in integer minor units (pence/paise).
- Enforces statutory digital advertising tax regimes:
    * UK: 20% VAT on digital advertising services.
    * India: 18% GST (SAC 998365 - Advertising Services) on digital advertising.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, Tuple, Optional
import datetime


# =============================================================================
# STATUTORY COMMERCIAL ADVERTISING PACKAGES
# =============================================================================

ADVERTISING_PACKAGES: Dict[str, Dict[str, Any]] = {
    'AD_PKG_7D': {
        'code': 'AD_PKG_7D',
        'name': '7 Days Starter Promotion',
        'days': 7,
        'currencies': {
            'GBP': {'price_minor': 3500, 'daily_minor': 500, 'currency': 'GBP'},      # £35.00 (£5.00/day)
            'INR': {'price_minor': 350000, 'daily_minor': 50000, 'currency': 'INR'},  # ₹3,500.00 (₹500.00/day)
        },
    },
    'AD_PKG_14D': {
        'code': 'AD_PKG_14D',
        'name': '14 Days Growth Campaign',
        'days': 14,
        'currencies': {
            'GBP': {'price_minor': 6000, 'daily_minor': 428, 'currency': 'GBP'},      # £60.00 (£4.28/day)
            'INR': {'price_minor': 600000, 'daily_minor': 42857, 'currency': 'INR'},  # ₹6,000.00 (₹428.57/day)
        },
    },
    'AD_PKG_30D': {
        'code': 'AD_PKG_30D',
        'name': '30 Days Maximum Impact',
        'days': 30,
        'currencies': {
            'GBP': {'price_minor': 11000, 'daily_minor': 366, 'currency': 'GBP'},     # £110.00 (£3.66/day)
            'INR': {'price_minor': 1100000, 'daily_minor': 36666, 'currency': 'INR'}, # ₹11,000.00 (₹366.66/day)
        },
    },
}

# Base standard daily rates for custom durations
BASE_DAILY_RATES_MINOR: Dict[str, int] = {
    'GBP': 500,      # £5.00 / day
    'INR': 50000,    # ₹500.00 / day
}

# Statutory tax rates for digital advertising services
STATUTORY_ADVERTISING_TAX_RATES: Dict[str, Dict[str, Any]] = {
    'GB': {
        'tax_name': 'UK VAT',
        'rate_percent': Decimal('20.00'),
        'service_code': 'VAT-UK-DIGITAL-AD',
        'description': 'UK Value Added Tax (20%) on digital advertising placements',
    },
    'IN': {
        'tax_name': 'Indian GST',
        'rate_percent': Decimal('18.00'),
        'service_code': 'SAC-998365',
        'description': 'Goods and Services Tax (18%) under SAC 998365 (Internet Advertising Services)',
    },
}

# =============================================================================
# TAX COMPLIANCE & LEGAL ASSUMPTIONS GATEWAY
# =============================================================================
# Statutory Tax Assumptions and Jurisdictional Dependencies:
# 1. United Kingdom (GB):
#    - Service Code: VAT-UK-DIGITAL-AD (Standard rated UK VAT at 20.0%).
#    - Supply Type: Electronically Supplied Services (B2B digital advertising).
#    - Jurisdiction Dependencies: Applied to UK-established dealerships. If foreign or EU
#      advertisers purchase advertising, cross-border reverse charge rules (0% UK VAT with customer
#      VAT identifier recorded) require formal qualification and validation.
#
# 2. India (IN):
#    - Service Code: SAC-998365 (Internet Advertising Services, standard rate 18.0% GST).
#    - Component breakdown: CGST 9% + SGST 9% for intra-state supplies, or IGST 18% for inter-state supplies.
#    - Jurisdiction Dependencies: Assumes domestic supply to Indian dealerships with valid GSTIN.
#      Cross-border supply or SEZ (Special Economic Zone) zero-rating requires formal documentation.
#
# 3. Regulatory / Commercial Signoff Gate:
#    - LIVE_ADVERTISING_CHARGES_ENABLED: Default False (falls back to LIVE_ADVERTISING_PAYMENTS_ENABLED).
#    - LIVE_ADVERTISING_REFUNDS_ENABLED: Explicit Default False.
#    - In staging and development, mock and test gateway modes operate freely.
#    - Live commercial payment charges and live outbound refunds are independently controlled
#      pending formal tax counsel, accountant, and compliance approval.
def is_live_advertising_charge_authorized() -> bool:
    """
    Returns True only if live advertising charges (payment sessions/captures)
    have received formal tax and compliance approval.
    Defaults to False in standard configuration.
    """
    from django.conf import settings
    return getattr(
        settings,
        'LIVE_ADVERTISING_CHARGES_ENABLED',
        getattr(settings, 'LIVE_ADVERTISING_PAYMENTS_ENABLED', False)
    )


def is_live_advertising_refund_authorized() -> bool:
    """
    Returns True only if live advertising gateway refunds have received formal compliance approval.
    Defaults to False in standard configuration.
    """
    from django.conf import settings
    return getattr(settings, 'LIVE_ADVERTISING_REFUNDS_ENABLED', False)


def is_live_advertising_payment_authorized() -> bool:
    """
    Backwards-compatible alias for charge authorization.
    """
    return is_live_advertising_charge_authorized()



def normalize_advertising_country(country_code: Optional[str], currency: Optional[str] = None) -> str:
    """Resolves authoritative country code from organisation or currency."""
    if country_code:
        c = str(country_code).strip().upper()
        if c in ('GB', 'UK', 'GB-ENG', 'GB-SCT', 'GB-WLS', 'GB-NIR'):
            return 'GB'
        if c in ('IN', 'INDIA', 'BHARAT', 'IN-DL', 'IN-MH', 'IN-KA', 'IN-TN'):
            return 'IN'
    if currency:
        curr = str(currency).strip().upper()
        if curr == 'GBP':
            return 'GB'
        if curr == 'INR':
            return 'IN'
    return 'GB'


def calculate_campaign_pricing(
    *args,
    start_date: Optional[datetime.date] = None,
    end_date: Optional[datetime.date] = None,
    currency: Optional[str] = None,
    package_code: Optional[str] = None,
    country_code: Optional[str] = None,
    target_country: Optional[str] = None,
    duration_days: Optional[int] = None,
    custom_duration_days: Optional[int] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Calculates campaign pricing, duration, daily rate, and applicable statutory tax breakdown.
    Supports both date-range and package-code/duration parameter invocations.
    All monetary amounts are returned in integer minor units.
    """
    # Extract positional arguments if provided
    for arg in args:
        if isinstance(arg, datetime.date):
            if start_date is None:
                start_date = arg
            elif end_date is None:
                end_date = arg
        elif isinstance(arg, str):
            if currency is None and arg.upper() in ('GBP', 'INR'):
                currency = arg

    curr = str(currency or kwargs.get('curr') or 'GBP').strip().upper()
    if curr not in ('GBP', 'INR'):
        raise ValueError(f"Unsupported advertising currency '{currency}'. Supported: GBP, INR.")

    # Determine duration
    if start_date is not None and end_date is not None:
        if end_date < start_date:
            raise ValueError("Campaign end_date cannot be earlier than start_date.")
        days = (end_date - start_date).days + 1
    else:
        req_days = custom_duration_days or duration_days
        if req_days is not None:
            days = int(req_days)
        elif package_code in ('7_DAYS', 'AD_PKG_7D'):
            days = 7
        elif package_code in ('14_DAYS', 'AD_PKG_14D'):
            days = 14
        elif package_code in ('30_DAYS', 'AD_PKG_30D'):
            days = 30
        else:
            days = 7

    # Validate custom duration bounds
    code_str = str(package_code or '').strip().upper()
    if code_str == 'CUSTOM' or (package_code and 'CUSTOM' in code_str) or custom_duration_days is not None:
        if days < 3 or days > 90:
            raise ValueError("Custom duration must be between 3 and 90 days.")

    # Resolve country
    cntry = normalize_advertising_country(target_country or country_code, curr)
    tax_config = STATUTORY_ADVERTISING_TAX_RATES.get(cntry, STATUTORY_ADVERTISING_TAX_RATES['GB'])
    tax_rate = tax_config['rate_percent']

    # Map package code to rate schedule
    pkg_key = None
    if code_str in ('7_DAYS', 'AD_PKG_7D'):
        pkg_key = 'AD_PKG_7D'
    elif code_str in ('14_DAYS', 'AD_PKG_14D'):
        pkg_key = 'AD_PKG_14D'
    elif code_str in ('30_DAYS', 'AD_PKG_30D'):
        pkg_key = 'AD_PKG_30D'

    if pkg_key and pkg_key in ADVERTISING_PACKAGES and ADVERTISING_PACKAGES[pkg_key]['days'] == days:
        net_minor = ADVERTISING_PACKAGES[pkg_key]['currencies'][curr]['price_minor']
    else:
        # Custom duration pricing
        if days >= 30:
            daily_rate_custom = int(BASE_DAILY_RATES_MINOR[curr] * 0.73)
        elif days >= 14:
            daily_rate_custom = int(BASE_DAILY_RATES_MINOR[curr] * 0.85)
        else:
            daily_rate_custom = BASE_DAILY_RATES_MINOR[curr]
        net_minor = daily_rate_custom * days

    # Strict integer half-up tax calculation
    tax_decimal = (Decimal(net_minor) * (tax_rate / Decimal('100.00'))).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    tax_minor = int(tax_decimal)
    total_minor = net_minor + tax_minor
    daily_rate_minor = total_minor // days if days > 0 else 0

    return {
        'package_code': package_code or f"CUSTOM_{days}D",
        'duration_days': days,
        'currency': curr,
        'country': cntry,
        'net_amount_minor': net_minor,
        'tax_amount_minor': tax_minor,
        'total_amount_minor': total_minor,
        'total_budget_minor': total_minor,
        'daily_rate_minor': daily_rate_minor,
        'tax_regime': tax_config['tax_name'],
        'tax_name': tax_config['tax_name'],
        'sac_code': '998365' if cntry == 'IN' else None,
        'service_code': tax_config['service_code'],
        'tax_rate_percent': float(tax_rate),
        'description': tax_config['description'],
        'net_amount_display': f"{net_minor / 100:.2f}",
        'tax_amount_display': f"{tax_minor / 100:.2f}",
        'total_budget_display': f"{total_minor / 100:.2f}",
    }


def calculate_pro_rata_refund(
    campaign_total_minor: int = 0,
    start_date: Optional[datetime.date] = None,
    end_date: Optional[datetime.date] = None,
    cancellation_date: Optional[datetime.date] = None,
    total_budget_minor: Optional[int] = None,
    duration_days: Optional[int] = None,
    days_served: Optional[int] = None,
    **kwargs,
) -> int:
    """
    Calculates whole-day pro-rata refund in integer minor units when a campaign is cancelled early.
    Supports both date-based and day-count based calculations.
    """
    budget = total_budget_minor if total_budget_minor is not None else campaign_total_minor

    if duration_days is not None and days_served is not None:
        if duration_days <= 0 or days_served >= duration_days:
            return 0
        unserved_days = max(0, duration_days - days_served)
        return (budget * unserved_days) // duration_days

    if cancellation_date and start_date and end_date:
        if cancellation_date <= start_date:
            return budget
        if cancellation_date >= end_date:
            return 0
        tot_days = (end_date - start_date).days + 1
        elapsed = (cancellation_date - start_date).days
        remaining = max(0, tot_days - elapsed)
        return (budget * remaining) // tot_days if tot_days > 0 else 0

    return 0

    # Calculate proportional refund rounded half up
    refund_dec = (Decimal(campaign_total_minor) * (Decimal(remaining_days) / Decimal(total_days))).quantize(
        Decimal('1'), rounding=ROUND_HALF_UP
    )
    return int(refund_dec)
