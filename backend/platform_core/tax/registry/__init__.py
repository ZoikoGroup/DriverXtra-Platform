"""Classification registries for statutory HSN, SAC, and VAT schedules."""

from .base import BaseClassificationRegistry
from .india_hsn import (
    STATUTORY_INDIAN_HSN_REGISTRY,
    get_tariff_entry_for_date,
    validate_tariff_classification,
    resolve_automotive_part_hsn,
)
from .india_sac import (
    STATUTORY_INDIAN_SAC_REGISTRY,
    get_sac_entry,
    resolve_workshop_service_sac,
)
from .uk_vat_schedules import (
    UK_VAT_STANDARD_RATE,
    UK_VAT_REDUCED_RATE,
    UK_VAT_ZERO_RATE,
    resolve_uk_vat_classification,
)

__all__ = [
    'BaseClassificationRegistry',
    'STATUTORY_INDIAN_HSN_REGISTRY',
    'get_tariff_entry_for_date',
    'validate_tariff_classification',
    'resolve_automotive_part_hsn',
    'STATUTORY_INDIAN_SAC_REGISTRY',
    'get_sac_entry',
    'resolve_workshop_service_sac',
    'UK_VAT_STANDARD_RATE',
    'UK_VAT_REDUCED_RATE',
    'UK_VAT_ZERO_RATE',
    'resolve_uk_vat_classification',
]
