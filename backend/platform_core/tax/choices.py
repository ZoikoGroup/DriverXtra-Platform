"""Statutory choices and enums for indirect tax regimes (GST, VAT)."""

from enum import Enum


class TaxScheme(str, Enum):
    """Canonical indirect tax regime."""
    GST = 'GST'
    VAT = 'VAT'


class TaxType(str, Enum):
    """Statutory tax calculation category."""
    INTRA_STATE = 'INTRA_STATE'      # India GST: CGST + SGST
    INTER_STATE = 'INTER_STATE'      # India GST: IGST
    UK_VAT = 'UK_VAT'                # United Kingdom: Single line VAT
    OUTSIDE_SCOPE = 'OUTSIDE_SCOPE'  # Outside statutory scope (e.g. DVSA MOT inspection fee)
    EXEMPT = 'EXEMPT'                # Exempt supplies under statutory schedule
    ZERO_RATED = 'ZERO_RATED'        # Taxable supply zero-rated under statutory schedule
    BLOCKED = 'BLOCKED'              # Invoicing blocked due to compliance/governance conflict


class TaxCategory(str, Enum):
    """Statutory rate schedule bracket."""
    STANDARD = 'STANDARD'
    REDUCED = 'REDUCED'              # E.g. UK VATA Schedule 7A (child car seats @ 5%)
    ZERO_RATED = 'ZERO_RATED'        # E.g. VATA Schedule 8 Group 16 helmets, Group 3 books
    EXEMPT = 'EXEMPT'                # E.g. Statutory exempt schedules
    OUTSIDE_SCOPE = 'OUTSIDE_SCOPE'  # Statutory fees / disbursements under Notice 700 §25.4
    UNREGISTERED = 'UNREGISTERED'    # Below threshold small business (no tax levied)


class DocumentType(str, Enum):
    """Statutory commercial document issued for the transaction."""
    TAX_INVOICE = 'TAX_INVOICE'
    BILL_OF_SUPPLY = 'BILL_OF_SUPPLY'            # Section 31(3)(c) CGST Act for unregistered/exempt
    COMMERCIAL_INVOICE = 'COMMERCIAL_INVOICE'    # Non-VAT commercial invoice (UK)
    DISBURSEMENT_NOTE = 'DISBURSEMENT_NOTE'      # Pure agency disbursement (MOT Notice 700 §25.4)
    BLOCKED = 'BLOCKED'                          # Invoicing withheld pending compliance review


class SupplierRegistrationState(str, Enum):
    """Statutory legal status of supplier tax registration."""
    NOT_LIABLE_TO_REGISTER = 'NOT_LIABLE_TO_REGISTER'        # Below threshold (Sec 22 CGST / UK VATA S1)
    VOLUNTARILY_REGISTERED = 'VOLUNTARILY_REGISTERED'        # Registered under Sec 25(3) CGST / UK VATA
    ACTIVE_MANDATORY_REGISTRATION = 'ACTIVE_MANDATORY_REGISTRATION' # Legally liable & verified
    SUSPENDED_OR_CANCELLED = 'SUSPENDED_OR_CANCELLED'        # Suspended (CGST Rule 21A) or cancelled
    UNVERIFIED_REGISTRATION = 'UNVERIFIED_REGISTRATION'      # Formally unconfirmed on government registry


class ClassificationGovernanceStatus(str, Enum):
    """Governance status of HSN/SAC service or product classification."""
    CONFIRMED = 'CONFIRMED'                                  # Direct, unambiguous statutory mapping
    PROVISIONAL = 'PROVISIONAL'                              # Requires factual/contractual verification
    UNRESOLVED_LEGAL_QUESTION = 'UNRESOLVED_LEGAL_QUESTION'  # Contested or complex; requires tax review

