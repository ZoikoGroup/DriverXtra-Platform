"""Authoritative regional choices and enums for DriverXtra multi-country architecture.

Separates sovereign country codes, currencies, measurement units, and tax regimes.
"""

from django.db import models


class CountryCode(models.TextChoices):
    """Authoritative ISO 3166-1 alpha-2 country codes."""
    IN = 'IN', 'India'
    GB = 'GB', 'United Kingdom'


class CurrencyCode(models.TextChoices):
    """Authoritative ISO 4217 three-letter currency codes."""
    INR = 'INR', 'Indian Rupee'
    GBP = 'GBP', 'British Pound'


class OdometerUnit(models.TextChoices):
    """Authoritative vehicle and work order odometer measurement units."""
    KM = 'km', 'Kilometres'
    MI = 'mi', 'Miles'


class TaxScheme(models.TextChoices):
    """Sovereign indirect tax schemes."""
    GST = 'GST', 'Goods and Services Tax'
    VAT = 'VAT', 'Value Added Tax'

