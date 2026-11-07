"""Integer minor-unit money helpers (Master Architecture §7, Appendix C).

Amounts are signed integers in the currency's minor unit with an explicit ISO 4217 exponent.
No floating-point arithmetic is used anywhere in commercial calculations.
"""

from .errors import CommercialRuleViolation

# ISO 4217 minor-unit exponents. Only listed currencies are accepted; adding one is a deliberate change.
CURRENCY_EXPONENTS = {
    # 2-decimal
    'AED': 2, 'AUD': 2, 'BRL': 2, 'CAD': 2, 'CHF': 2, 'CNY': 2, 'CZK': 2, 'DKK': 2, 'EUR': 2,
    'GBP': 2, 'HKD': 2, 'INR': 2, 'MXN': 2, 'MYR': 2, 'NOK': 2, 'NZD': 2, 'PLN': 2, 'QAR': 2,
    'SAR': 2, 'SEK': 2, 'SGD': 2, 'THB': 2, 'TRY': 2, 'USD': 2, 'ZAR': 2,
    # 0-decimal
    'CLP': 0, 'ISK': 0, 'JPY': 0, 'KRW': 0, 'VND': 0,
    # 3-decimal
    'BHD': 3, 'JOD': 3, 'KWD': 3, 'OMR': 3, 'TND': 3,
}

BASIS_POINTS_DENOMINATOR = 10_000


def normalize_currency(code) -> str:
    value = (code or '').strip().upper()
    if value not in CURRENCY_EXPONENTS:
        raise CommercialRuleViolation(
            'UNSUPPORTED_CURRENCY',
            f"Currency '{code}' is not a supported ISO 4217 code for commercial pricing.",
            status_code=400,
        )
    return value


def currency_exponent(code: str) -> int:
    return CURRENCY_EXPONENTS[normalize_currency(code)]


def divide_round_half_up(numerator: int, denominator: int) -> int:
    """Integer division rounding half away from zero."""
    if denominator <= 0:
        raise ValueError('denominator must be positive')
    sign = -1 if numerator < 0 else 1
    quotient, remainder = divmod(abs(numerator), denominator)
    if remainder * 2 >= denominator:
        quotient += 1
    return sign * quotient


def apply_basis_points(amount_minor: int, basis_points: int) -> int:
    """amount × bps / 10,000, rounded half-up to the minor unit (e.g. 9000 × 800 bps → 720)."""
    return divide_round_half_up(amount_minor * basis_points, BASIS_POINTS_DENOMINATOR)


def clamp_fee(fee_minor: int, min_fee_minor=None, max_fee_minor=None) -> int:
    if min_fee_minor is not None and fee_minor < min_fee_minor:
        fee_minor = min_fee_minor
    if max_fee_minor is not None and fee_minor > max_fee_minor:
        fee_minor = max_fee_minor
    return fee_minor
