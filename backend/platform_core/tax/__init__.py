"""DriverXtra Centralized Multi-Country Statutory Tax Engine."""

from .choices import (
    TaxScheme,
    TaxType,
    TaxCategory,
    DocumentType,
    SupplierRegistrationState,
    ClassificationGovernanceStatus,
)
from .exceptions import (
    TaxEngineError,
    TaxAuthorizationError,
    UnclassifiedItemError,
    AmbiguousPlaceOfSupplyError,
    BlockedInvoiceError,
)
from .models_data import (
    TaxTransactionContext,
    TaxLineInput,
    TaxComponentBreakdown,
    TaxLineResult,
    TaxCalculationResult,
)
from .engine import TaxEngineService
from .regimes.base import quantize_currency
from .registry.india_hsn import (
    STATUTORY_INDIAN_HSN_REGISTRY,
    get_tariff_entry_for_date,
    validate_tariff_classification,
)
from .registry.india_sac import (
    STATUTORY_INDIAN_SAC_REGISTRY,
    get_sac_entry,
    resolve_workshop_service_sac,
)
from .registry.uk_vat_schedules import (
    UK_VAT_STANDARD_RATE,
    UK_VAT_REDUCED_RATE,
    UK_VAT_ZERO_RATE,
    resolve_uk_vat_classification,
)
from .supplier_resolver import resolve_marketplace_supplier_tax_context

__all__ = [
    'TaxScheme',
    'TaxType',
    'TaxCategory',
    'DocumentType',
    'SupplierRegistrationState',
    'ClassificationGovernanceStatus',
    'TaxEngineError',
    'TaxAuthorizationError',
    'UnclassifiedItemError',
    'AmbiguousPlaceOfSupplyError',
    'BlockedInvoiceError',
    'TaxTransactionContext',
    'TaxLineInput',
    'TaxComponentBreakdown',
    'TaxLineResult',
    'TaxCalculationResult',
    'TaxEngineService',
    'quantize_currency',
    'STATUTORY_INDIAN_HSN_REGISTRY',
    'get_tariff_entry_for_date',
    'validate_tariff_classification',
    'STATUTORY_INDIAN_SAC_REGISTRY',
    'get_sac_entry',
    'resolve_workshop_service_sac',
    'UK_VAT_STANDARD_RATE',
    'UK_VAT_REDUCED_RATE',
    'UK_VAT_ZERO_RATE',
    'resolve_uk_vat_classification',
    'resolve_marketplace_supplier_tax_context',
]

