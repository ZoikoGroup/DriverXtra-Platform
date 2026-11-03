"""Unified Tax Engine Service facade for DriverXtra.

Orchestrates:
- Jurisdiction routing to sovereign tax regimes (India GST vs UK VAT).
- Supplier registration state machine and tax-collection authorization.
- Classification governance enforcement (CONFIRMED, PROVISIONAL, UNRESOLVED_LEGAL_QUESTION).
- Immutability of transaction snapshots.
- Decimal-exact rounding and balancing guarantees.
"""

from decimal import Decimal
from typing import List, Optional, Dict, Any
from .choices import (
    TaxScheme,
    TaxType,
    DocumentType,
    SupplierRegistrationState,
    ClassificationGovernanceStatus,
)
from .exceptions import (
    TaxEngineError,
    TaxAuthorizationError,
    UnclassifiedItemError,
    BlockedInvoiceError,
)
from .models_data import (
    TaxTransactionContext,
    TaxLineInput,
    TaxCalculationResult,
    TaxLineResult,
)
from .regimes.india_gst import IndiaGSTRegime
from .regimes.uk_vat import UKVATRegime
from .regimes.base import quantize_currency


class TaxEngineService:
    """Authoritative, configurable, jurisdiction-aware tax calculation engine."""

    _regimes = {
        'IN': IndiaGSTRegime(),
        'GB': UKVATRegime(),
    }

    @classmethod
    def get_regime(cls, country_code: str):
        """Resolves statutory regime strategy for sovereign country code."""
        code_clean = (country_code or "").strip().upper()
        if code_clean not in cls._regimes:
            raise TaxEngineError(
                f"Unsupported country '{country_code}' for indirect tax calculation. "
                f"DriverXtra supports India ('IN') and United Kingdom ('GB')."
            )
        return cls._regimes[code_clean]

    @classmethod
    def calculate_transaction_tax(
        cls,
        context: TaxTransactionContext,
        lines: List[TaxLineInput],
        discount_amount: Decimal = Decimal('0.00'),
    ) -> TaxCalculationResult:
        """Calculates statutory tax determination and returns immutable snapshot.

        Enforces mandatory safeguards:
        - Rejects empty line item sets.
        - Routes to sovereign regime strategy.
        - Enforces classification governance: PROVISIONAL or UNRESOLVED classifications
          cannot automatically generate production Tax Invoices.
        - Enforces supplier authorization: unauthorized tax collection is blocked.
        """
        if not lines:
            raise TaxEngineError("At least one line item is required to determine tax.")

        regime = cls.get_regime(context.country_code)
        result = regime.calculate_tax(
            context=context,
            lines=lines,
            discount_amount=discount_amount,
        )

        # Enforce governance rule:
        # Provisional or unresolved classifications must not automatically generate production tax invoices
        has_provisional_or_unresolved = any(
            l.governance_status in (ClassificationGovernanceStatus.PROVISIONAL, ClassificationGovernanceStatus.UNRESOLVED_LEGAL_QUESTION)
            for l in result.lines
        )

        if has_provisional_or_unresolved and result.document_type == DocumentType.TAX_INVOICE:
            # Downgrade document type to BLOCKED pending administrative tax review
            unconfirmed_lines = [
                f"'{l.description}' ({l.governance_status.value})"
                for l in result.lines
                if l.governance_status != ClassificationGovernanceStatus.CONFIRMED
            ]
            reasons = result.review_reason
            add_reason = f"Provisional or unresolved line classifications detected: {', '.join(unconfirmed_lines)}. Production tax invoice blocked."
            combined_reasons = f"{reasons}; {add_reason}" if reasons else add_reason

            result = TaxCalculationResult(
                document_type=DocumentType.BLOCKED,
                tax_scheme=result.tax_scheme,
                tax_type=TaxType.BLOCKED,
                place_of_supply=result.place_of_supply,
                legal_place_of_supply_basis=result.legal_place_of_supply_basis,
                supplier_jurisdiction=result.supplier_jurisdiction,
                supplier_registration_state=result.supplier_registration_state,
                can_collect_tax=result.can_collect_tax,
                currency=result.currency,
                taxable_amount=result.taxable_amount,
                effective_tax_rate=result.effective_tax_rate,
                tax_amount=result.tax_amount,
                total_amount=result.total_amount,
                requires_tax_review=True,
                review_reason=combined_reasons,
                components=result.components,
                lines=result.lines,
            )

        return result

    @classmethod
    def calculate_line_tax(
        cls,
        context: TaxTransactionContext,
        line: TaxLineInput,
    ) -> TaxLineResult:
        """Helper to calculate tax determination for a single line item."""
        res = cls.calculate_transaction_tax(context=context, lines=[line])
        return res.lines[0]

