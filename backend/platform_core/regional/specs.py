"""Authoritative country specifications and regional configuration registry.

Single source of truth for:
- Supported country definitions for India (IN) and the United Kingdom (GB).
- Country-to-default-currency mapping (IN -> INR, GB -> GBP).
- Country-to-default-odometer-unit mapping (IN -> km, GB -> mi).
- Country-to-default-jurisdiction mapping (IN -> IN-TG, GB -> GB-ENG).
- Valid ISO 3166-2 subdivisions and GST state codes.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from .choices import CountryCode, CurrencyCode, OdometerUnit, TaxScheme
from .subdivisions import (
    SubdivisionSpecification,
    UK_SUBDIVISIONS,
    INDIA_SUBDIVISIONS,
)
from .tax_interface import (
    BaseRegionalTaxConfig,
    IndiaGSTRegionalConfig,
    UKVATRegionalConfig,
)
from .payment_interface import (
    BaseRegionalPaymentConfig,
    IndiaPaymentRegionalConfig,
    UKPaymentRegionalConfig,
)


@dataclass(frozen=True)
class CountrySpecification:
    """Canonical sovereign country specification and regional defaults."""
    country_code: CountryCode
    name: str
    default_currency: CurrencyCode
    default_odometer_unit: OdometerUnit
    default_jurisdiction: str
    tax_config: BaseRegionalTaxConfig
    payment_config: BaseRegionalPaymentConfig
    subdivisions: Dict[str, SubdivisionSpecification]
    supported_currencies: Tuple[CurrencyCode, ...]
    supported_odometer_units: Tuple[OdometerUnit, ...]

    def is_valid_jurisdiction(self, jurisdiction: str) -> bool:
        """Checks if the given ISO 3166-2 code is a valid subdivision of this country."""
        return jurisdiction in self.subdivisions

    def get_subdivision(self, jurisdiction: str) -> Optional[SubdivisionSpecification]:
        """Returns the SubdivisionSpecification for a valid jurisdiction, or None."""
        return self.subdivisions.get(jurisdiction)


# =============================================================================
# AUTHORITATIVE COUNTRY SPECIFICATIONS REGISTRY
# =============================================================================

COUNTRY_SPECIFICATIONS: Dict[str, CountrySpecification] = {
    CountryCode.IN.value: CountrySpecification(
        country_code=CountryCode.IN,
        name='India',
        default_currency=CurrencyCode.INR,
        default_odometer_unit=OdometerUnit.KM,
        default_jurisdiction='IN-TG',
        tax_config=IndiaGSTRegionalConfig(),
        payment_config=IndiaPaymentRegionalConfig(),
        subdivisions=INDIA_SUBDIVISIONS,
        supported_currencies=(CurrencyCode.INR,),
        supported_odometer_units=(OdometerUnit.KM, OdometerUnit.MI),
    ),
    CountryCode.GB.value: CountrySpecification(
        country_code=CountryCode.GB,
        name='United Kingdom',
        default_currency=CurrencyCode.GBP,
        default_odometer_unit=OdometerUnit.MI,
        default_jurisdiction='GB-ENG',
        tax_config=UKVATRegionalConfig(),
        payment_config=UKPaymentRegionalConfig(),
        subdivisions=UK_SUBDIVISIONS,
        supported_currencies=(CurrencyCode.GBP,),
        supported_odometer_units=(OdometerUnit.MI, OdometerUnit.KM),
    ),
}


# =============================================================================
# PUBLIC CONFIGURATION ACCESSORS
# =============================================================================

def is_supported_country(country_code: Optional[str]) -> bool:
    """Verifies whether the given country code is supported by the platform."""
    if not country_code:
        return False
    return country_code.strip().upper() in COUNTRY_SPECIFICATIONS


def get_supported_country_codes() -> List[str]:
    """Returns list of supported ISO 3166-1 alpha-2 country codes."""
    return list(COUNTRY_SPECIFICATIONS.keys())


def get_country_spec(country_code: str) -> CountrySpecification:
    """Retrieves authoritative CountrySpecification or raises KeyError if unsupported."""
    clean = str(country_code).strip().upper()
    if clean not in COUNTRY_SPECIFICATIONS:
        raise KeyError(
            f"Unsupported country code '{country_code}'. "
            f"Supported countries are: {', '.join(get_supported_country_codes())}."
        )
    return COUNTRY_SPECIFICATIONS[clean]


def get_default_currency_for_country(country_code: str) -> str:
    """Authoritative mapping: country code to default transaction currency (e.g. IN -> INR, GB -> GBP)."""
    spec = get_country_spec(country_code)
    return spec.default_currency.value


def get_default_odometer_unit_for_country(country_code: str) -> str:
    """Authoritative mapping: country code to default vehicle odometer unit (e.g. IN -> km, GB -> mi)."""
    spec = get_country_spec(country_code)
    return spec.default_odometer_unit.value


def get_default_jurisdiction_for_country(country_code: str) -> str:
    """Authoritative mapping: country code to default legal jurisdiction (e.g. IN -> IN-TG, GB -> GB-ENG)."""
    spec = get_country_spec(country_code)
    return spec.default_jurisdiction

