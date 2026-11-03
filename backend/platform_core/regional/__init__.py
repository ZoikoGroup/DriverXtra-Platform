"""DriverXtra Platform Core - Reusable Regional Configuration Module.

Provides authoritative multi-country specifications, choices, validators, and endpoints.
"""

from .choices import (
    CountryCode,
    CurrencyCode,
    OdometerUnit,
    TaxScheme,
)
from .subdivisions import (
    SubdivisionSpecification,
    UK_SUBDIVISIONS,
    INDIA_SUBDIVISIONS,
    get_subdivision_by_gst_state_code,
    derive_jurisdiction_from_tax_id,
)
from .specs import (
    CountrySpecification,
    COUNTRY_SPECIFICATIONS,
    is_supported_country,
    get_supported_country_codes,
    get_country_spec,
    get_default_currency_for_country,
    get_default_odometer_unit_for_country,
    get_default_jurisdiction_for_country,
)
from .validators import (
    normalize_country_code,
    validate_country_code,
    validate_jurisdiction,
    derive_country_from_jurisdiction,
    validate_gstin_format,
    validate_uk_vat_format,
    derive_regional_context_for_vehicle_and_buyer,
)

__all__ = [
    'CountryCode',
    'CurrencyCode',
    'OdometerUnit',
    'TaxScheme',
    'SubdivisionSpecification',
    'UK_SUBDIVISIONS',
    'INDIA_SUBDIVISIONS',
    'get_subdivision_by_gst_state_code',
    'derive_jurisdiction_from_tax_id',
    'CountrySpecification',
    'COUNTRY_SPECIFICATIONS',
    'is_supported_country',
    'get_supported_country_codes',
    'get_country_spec',
    'get_default_currency_for_country',
    'get_default_odometer_unit_for_country',
    'get_default_jurisdiction_for_country',
    'normalize_country_code',
    'validate_country_code',
    'validate_jurisdiction',
    'derive_country_from_jurisdiction',
    'validate_gstin_format',
    'validate_uk_vat_format',
    'derive_regional_context_for_vehicle_and_buyer',
]
