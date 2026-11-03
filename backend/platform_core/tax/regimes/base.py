"""Abstract strategy base class for sovereign indirect tax regimes."""

from abc import ABC, abstractmethod
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Tuple
from platform_core.tax.models_data import (
    TaxTransactionContext,
    TaxLineInput,
    TaxCalculationResult,
    TaxLineResult,
)


PAISE_OR_PENCE = Decimal('0.01')


def quantize_currency(amount: Decimal) -> Decimal:
    """Strictly rounds to 2 decimal places (minor units: paise/pence) using ROUND_HALF_UP."""
    return amount.quantize(PAISE_OR_PENCE, rounding=ROUND_HALF_UP)


class BaseTaxRegime(ABC):
    """Abstract tax regime strategy defining calculation contracts."""

    @abstractmethod
    def calculate_tax(
        self,
        context: TaxTransactionContext,
        lines: List[TaxLineInput],
        discount_amount: Decimal = Decimal('0.00'),
    ) -> TaxCalculationResult:
        """Calculates statutory tax determination for transaction lines."""
        pass

