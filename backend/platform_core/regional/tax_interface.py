"""Regional configuration interface for indirect tax regimes (GST, VAT).

Defines architectural contracts without implementing full tax calculation logic.
"""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional, Dict, Any
from .choices import TaxScheme


class BaseRegionalTaxConfig(ABC):
    """Abstract interface defining country-specific tax rules and candidate rates."""

    @property
    @abstractmethod
    def tax_scheme(self) -> TaxScheme:
        """Returns canonical tax scheme (GST or VAT)."""
        pass

    @property
    @abstractmethod
    def default_candidate_rate_motor_repair(self) -> Decimal:
        """Standard candidate rate for applicable motor vehicle maintenance and repair services."""
        pass

    @property
    @abstractmethod
    def tax_id_label(self) -> str:
        """User-facing legal identifier label (e.g. 'GSTIN' or 'VAT Number')."""
        pass

    @abstractmethod
    def get_tax_summary(self) -> Dict[str, Any]:
        """Returns tax metadata payload for regional serialization."""
        pass


class IndiaGSTRegionalConfig(BaseRegionalTaxConfig):
    """Regional tax configuration interface for India (GST).

    Note: 18.00% is configured as candidate standard rate for applicable
    motor vehicle maintenance and repair (SAC 9987), but is NOT applied
    indiscriminately to every product or service.
    """

    @property
    def tax_scheme(self) -> TaxScheme:
        return TaxScheme.GST

    @property
    def default_candidate_rate_motor_repair(self) -> Decimal:
        return Decimal('18.00')

    @property
    def tax_id_label(self) -> str:
        return 'GSTIN'

    def get_tax_summary(self) -> Dict[str, Any]:
        return {
            'tax_scheme': self.tax_scheme.value,
            'tax_id_label': self.tax_id_label,
            'tax_components': ['CGST', 'SGST', 'IGST'],
            'standard_candidate_service_rate': str(self.default_candidate_rate_motor_repair),
            'service_sac_code': '9987',
        }


class UKVATRegionalConfig(BaseRegionalTaxConfig):
    """Regional tax configuration interface for United Kingdom (VAT).

    Standard UK VAT rate is 20.00%.
    """

    @property
    def tax_scheme(self) -> TaxScheme:
        return TaxScheme.VAT

    @property
    def default_candidate_rate_motor_repair(self) -> Decimal:
        return Decimal('20.00')

    @property
    def tax_id_label(self) -> str:
        return 'VAT Number'

    def get_tax_summary(self) -> Dict[str, Any]:
        return {
            'tax_scheme': self.tax_scheme.value,
            'tax_id_label': self.tax_id_label,
            'tax_components': ['VAT'],
            'standard_candidate_service_rate': str(self.default_candidate_rate_motor_repair),
        }

