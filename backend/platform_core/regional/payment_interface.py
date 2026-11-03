"""Regional configuration interface for payment providers and currency isolation.

Defines architectural contracts for payment gateway routing in later stages.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any
from .choices import CurrencyCode


class BaseRegionalPaymentConfig(ABC):
    """Abstract interface defining country-specific payment capabilities."""

    @property
    @abstractmethod
    def primary_provider_name(self) -> str:
        """Name of the canonical payment provider for this sovereign jurisdiction."""
        pass

    @property
    @abstractmethod
    def supported_currencies(self) -> List[CurrencyCode]:
        """Currencies validly supported for payment collection in this country."""
        pass

    @abstractmethod
    def get_payment_summary(self) -> Dict[str, Any]:
        """Returns payment routing metadata for serialization."""
        pass


class IndiaPaymentRegionalConfig(BaseRegionalPaymentConfig):
    """Payment routing interface for India (Razorpay domestic INR)."""

    @property
    def primary_provider_name(self) -> str:
        return 'RAZORPAY'

    @property
    def supported_currencies(self) -> List[CurrencyCode]:
        return [CurrencyCode.INR]

    def get_payment_summary(self) -> Dict[str, Any]:
        return {
            'primary_provider': self.primary_provider_name,
            'supported_currencies': [c.value for c in self.supported_currencies],
            'domestic_methods': ['UPI', 'NETBANKING', 'CARDS'],
        }


class UKPaymentRegionalConfig(BaseRegionalPaymentConfig):
    """Payment routing interface for United Kingdom (Stripe domestic GBP)."""

    @property
    def primary_provider_name(self) -> str:
        return 'STRIPE'

    @property
    def supported_currencies(self) -> List[CurrencyCode]:
        return [CurrencyCode.GBP]

    def get_payment_summary(self) -> Dict[str, Any]:
        return {
            'primary_provider': self.primary_provider_name,
            'supported_currencies': [c.value for c in self.supported_currencies],
            'domestic_methods': ['CARDS', 'BACS_DIRECT_DEBIT'],
        }

