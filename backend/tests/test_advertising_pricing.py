"""
Unit tests for Phase 7.2 Advertising Pricing & Digital Service Tax calculation module.
Validates:
- Standard packages (7d, 14d, 30d) and custom durations.
- Statutory tax rates: UK 20% VAT vs India 18% GST (SAC 998365).
- Integer minor units exactness (no lost pennies/paise).
- Pro-rata whole-day refund calculations.
"""

import pytest
from apps.marketplace.advertising_pricing import (
    calculate_campaign_pricing,
    calculate_pro_rata_refund,
    normalize_advertising_country,
    ADVERTISING_PACKAGES,
    BASE_DAILY_RATES_MINOR,
    STATUTORY_ADVERTISING_TAX_RATES,
)


class TestAdvertisingPricingCalculation:
    """Tests for package pricing and tax calculation logic."""

    def test_uk_7_days_package_pricing(self):
        """7-day UK package should be £35.00 net + 20% VAT (£7.00) = £42.00 total."""
        quote = calculate_campaign_pricing(
            currency='GBP',
            package_code='7_DAYS',
            target_country='GB',
        )

        assert quote['package_code'] == '7_DAYS'
        assert quote['duration_days'] == 7
        assert quote['currency'] == 'GBP'
        assert quote['net_amount_minor'] == 3500  # £35.00
        assert quote['tax_amount_minor'] == 700   # £7.00 (20% VAT)
        assert quote['total_amount_minor'] == 4200  # £42.00
        assert quote['tax_regime'] == 'UK VAT'
        assert quote['tax_rate_percent'] == 20.0
        assert quote['country'] == 'GB'
        assert quote['daily_rate_minor'] == 600  # 4200 / 7 = 600

    def test_india_14_days_package_pricing(self):
        """14-day India package should be ₹6,000 net + 18% GST (₹1,080) = ₹7,080 total with SAC 998365."""
        quote = calculate_campaign_pricing(
            currency='INR',
            package_code='14_DAYS',
            target_country='IN',
        )

        assert quote['package_code'] == '14_DAYS'
        assert quote['duration_days'] == 14
        assert quote['currency'] == 'INR'
        assert quote['net_amount_minor'] == 600000  # ₹6,000.00
        assert quote['tax_amount_minor'] == 108000  # ₹1,080.00 (18% GST)
        assert quote['total_amount_minor'] == 708000  # ₹7,080.00
        assert quote['tax_regime'] in ('Indian GST', 'India GST')
        assert quote['sac_code'] == '998365'
        assert quote['tax_rate_percent'] == 18.0
        assert quote['country'] == 'IN'

    def test_custom_duration_bounds(self):
        """Custom duration must enforce 3 to 90 days."""
        with pytest.raises(ValueError, match="between 3 and 90 days"):
            calculate_campaign_pricing('GBP', package_code='CUSTOM', custom_duration_days=2)

        with pytest.raises(ValueError, match="between 3 and 90 days"):
            calculate_campaign_pricing('GBP', package_code='CUSTOM', custom_duration_days=91)

        # Valid custom duration 10 days
        quote = calculate_campaign_pricing('GBP', package_code='CUSTOM', custom_duration_days=10, target_country='GB')
        assert quote['duration_days'] == 10
        assert quote['net_amount_minor'] == 5000  # 10 * 500 minor units (£50.00)
        assert quote['tax_amount_minor'] == 1000  # 20% = £10.00
        assert quote['total_amount_minor'] == 6000  # £60.00

    def test_country_normalization(self):
        """Verify country strings normalize to GB or IN."""
        assert normalize_advertising_country('gb') == 'GB'
        assert normalize_advertising_country('UNITED KINGDOM') == 'GB'
        assert normalize_advertising_country('uk') == 'GB'
        assert normalize_advertising_country('in') == 'IN'
        assert normalize_advertising_country('india') == 'IN'
        assert normalize_advertising_country('BHARAT') == 'IN'


class TestProRataRefundCalculation:
    """Tests for pro-rata refund computation."""

    def test_unserved_campaign_full_refund(self):
        """A campaign cancelled on day 0 gets 100% refund of total budget."""
        refund = calculate_pro_rata_refund(
            total_budget_minor=4200,
            duration_days=7,
            days_served=0,
        )
        assert refund == 4200

    def test_partially_served_campaign_pro_rata(self):
        """A 14-day campaign with 4 days served should refund 10/14 of total budget."""
        total_budget = 708000
        refund = calculate_pro_rata_refund(
            total_budget_minor=total_budget,
            duration_days=14,
            days_served=4,
        )
        # unserved = 10 days -> (708000 * 10) // 14 = 505714
        expected = (total_budget * 10) // 14
        assert refund == expected

    def test_fully_completed_campaign_zero_refund(self):
        """A campaign where days_served >= duration_days receives 0 refund."""
        refund = calculate_pro_rata_refund(
            total_budget_minor=4200,
            duration_days=7,
            days_served=7,
        )
        assert refund == 0

        refund_over = calculate_pro_rata_refund(
            total_budget_minor=4200,
            duration_days=7,
            days_served=8,
        )
        assert refund_over == 0
