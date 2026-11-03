"""Sovereign tax calculation regime strategies."""

from .base import BaseTaxRegime, quantize_currency
from .india_gst import IndiaGSTRegime
from .uk_vat import UKVATRegime

__all__ = [
    'BaseTaxRegime',
    'quantize_currency',
    'IndiaGSTRegime',
    'UKVATRegime',
]

