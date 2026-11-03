"""Abstract base specification for tariff and service classification registries."""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional, Dict, Any
from platform_core.tax.choices import ClassificationGovernanceStatus


class BaseClassificationRegistry(ABC):
    """Abstract interface for statutory classification registries."""

    @abstractmethod
    def get_entry(self, code: str, transaction_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieve classification entry for code on transaction date."""
        pass

