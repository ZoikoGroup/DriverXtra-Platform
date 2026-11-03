"""Strongly-typed data models for tax transactions, line items, and calculation snapshots."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional, List, Dict, Any
from .choices import (
    TaxScheme,
    TaxType,
    TaxCategory,
    DocumentType,
    SupplierRegistrationState,
    ClassificationGovernanceStatus,
)


@dataclass(frozen=True)
class TaxTransactionContext:
    """Legal, jurisdictional, and factual parameters governing a transaction."""
    country_code: str                               # 'IN' or 'GB'
    supplier_jurisdiction: str                      # ISO 3166-2 (e.g. 'IN-TG', 'GB-ENG')
    supplier_tax_id: Optional[str]                  # Stored GSTIN or UK VAT number
    supplier_registration_state: SupplierRegistrationState # 5 statutory states
    can_collect_tax: bool                           # Administrative collection authorization
    currency: str                                   # 'INR' or 'GBP'
    transaction_date: str                           # ISO-8601 date (e.g. '2026-11-03')
    
    # Customer parameters
    customer_jurisdiction: Optional[str] = None     # ISO 3166-2 if known
    customer_tax_id: Optional[str] = None           # Customer GSTIN / VAT number if B2B
    customer_address_on_record: Optional[str] = None # Full address string on record with supplier
    is_b2b: bool = False                            # True if purchasing under registered business account
    
    # Physical and evidentiary facts
    delivery_jurisdiction: Optional[str] = None     # Destination state for shipped goods
    physical_performance_jurisdiction: Optional[str] = None # Where physical vehicle repair took place
    b2b_contracting_jurisdiction: Optional[str] = None      # State of PO/contracting establishment
    b2b_evidence_present: bool = False              # PO, contract, or authorized business verification


@dataclass(frozen=True)
class TaxLineInput:
    """Line item submitted for tax calculation."""
    line_id: str
    item_type: str                                  # 'LABOUR', 'PART', 'DIAGNOSTIC', 'TOWING', 'MOT_FEE', etc.
    description: str
    taxable_amount: Decimal                         # Net amount before tax (unit_price * qty - discount)
    classification_code: Optional[str] = None       # 8-digit HSN, 6-digit SAC, or schedule reference
    catalogue_part_id: Optional[str] = None         # Link to pre-verified catalogue part
    is_disbursement: bool = False                   # True for pass-through statutory fee (e.g. MOT test)
    candidate_rate: Optional[Decimal] = None        # Explicit candidate percentage if permitted


@dataclass(frozen=True)
class TaxComponentBreakdown:
    """Standardized multi-component tax breakdown supporting dual GST and single VAT."""
    cgst_rate: Decimal = Decimal('0.00')
    cgst_amount: Decimal = Decimal('0.00')
    sgst_rate: Decimal = Decimal('0.00')
    sgst_amount: Decimal = Decimal('0.00')
    igst_rate: Decimal = Decimal('0.00')
    igst_amount: Decimal = Decimal('0.00')
    vat_rate: Decimal = Decimal('0.00')
    vat_amount: Decimal = Decimal('0.00')

    def to_dict(self) -> Dict[str, str]:
        """Convert all Decimal component values to string format for JSON persistence."""
        return {k: str(v) for k, v in self.__dict__.items()}


@dataclass(frozen=True)
class TaxLineResult:
    """Calculated tax breakdown for an individual transaction line item."""
    line_id: str
    item_type: str
    description: str
    classification_code: str                        # 8-digit HSN or 6-digit SAC
    governance_status: ClassificationGovernanceStatus # CONFIRMED, PROVISIONAL, UNRESOLVED_LEGAL_QUESTION
    statutory_category: TaxCategory
    legal_citation: str                             # Authoritative statutory entry reference
    taxable_amount: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    components: TaxComponentBreakdown


@dataclass(frozen=True)
class TaxCalculationResult:
    """Complete statutory tax calculation result and immutable snapshot."""
    document_type: DocumentType
    tax_scheme: TaxScheme
    tax_type: TaxType
    place_of_supply: str
    legal_place_of_supply_basis: str
    supplier_jurisdiction: str
    supplier_registration_state: SupplierRegistrationState
    can_collect_tax: bool
    currency: str
    taxable_amount: Decimal
    effective_tax_rate: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    requires_tax_review: bool
    review_reason: str
    components: TaxComponentBreakdown
    lines: List[TaxLineResult]

    def to_snapshot(self) -> Dict[str, Any]:
        """Serializes result into immutable JSON dictionary for transaction snapshot storage."""
        return {
            'document_type': self.document_type.value,
            'tax_scheme': self.tax_scheme.value,
            'tax_type': self.tax_type.value,
            'place_of_supply': self.place_of_supply,
            'legal_place_of_supply_basis': self.legal_place_of_supply_basis,
            'supplier_jurisdiction': self.supplier_jurisdiction,
            'supplier_registration_state': self.supplier_registration_state.value,
            'can_collect_tax': self.can_collect_tax,
            'currency': self.currency,
            'taxable_amount': str(self.taxable_amount),
            'effective_tax_rate': str(self.effective_tax_rate),
            'tax_amount': str(self.tax_amount),
            'total_amount': str(self.total_amount),
            'requires_tax_review': self.requires_tax_review,
            'review_reason': self.review_reason,
            'components': self.components.to_dict(),
            'lines': [
                {
                    'line_id': l.line_id,
                    'item_type': l.item_type,
                    'description': l.description,
                    'classification_code': l.classification_code,
                    'governance_status': l.governance_status.value,
                    'statutory_category': l.statutory_category.value,
                    'legal_citation': l.legal_citation,
                    'taxable_amount': str(l.taxable_amount),
                    'tax_rate': str(l.tax_rate),
                    'tax_amount': str(l.tax_amount),
                    'total_amount': str(l.total_amount),
                    'components': l.components.to_dict(),
                }
                for l in self.lines
            ],
        }

