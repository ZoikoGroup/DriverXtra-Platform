"""
Management command to process advertising campaigns:
- Activates SCHEDULED campaigns whose start date has arrived.
- Expires ACTIVE campaigns whose end date has passed.
- Aggregates daily metrics.

Usage:
    python manage.py process_advertising_campaigns [--activate] [--expire] [--aggregate] [--all]
"""

from django.core.management.base import BaseCommand
from apps.marketplace.advertising_service import AdvertisingCampaignService
from apps.marketplace.tasks import aggregate_campaign_daily_metrics_task


class Command(BaseCommand):
    help = "Processes advertising campaign activations, expirations, and daily metrics aggregation."

    def add_arguments(self, parser):
        parser.add_argument(
            '--activate',
            action='store_true',
            help='Activate scheduled campaigns whose start date has arrived.',
        )
        parser.add_argument(
            '--expire',
            action='store_true',
            help='Complete expired campaigns whose end date has passed.',
        )
        parser.add_argument(
            '--aggregate',
            action='store_true',
            help='Aggregate daily impression and click metrics.',
        )
        parser.add_argument(
            '--recover',
            action='store_true',
            help='Recover held paid advertising campaigns whose live payment was verified.',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            default=True,
            help='Run all advertising lifecycle routines (default).',
        )

    def handle(self, *args, **options):
        run_all = options.get('all') and not (
            options.get('activate') or options.get('expire') or options.get('aggregate') or options.get('recover')
        )

        if run_all or options.get('recover'):
            self.stdout.write("Recovering held paid advertising campaigns...")
            recovered = AdvertisingCampaignService.recover_held_paid_campaigns()
            self.stdout.write(self.style.SUCCESS(f"Successfully recovered {recovered} campaign(s)."))

        if run_all or options.get('activate'):
            self.stdout.write("Activating scheduled advertising campaigns...")
            activated = AdvertisingCampaignService.activate_scheduled_campaigns()
            self.stdout.write(self.style.SUCCESS(f"Successfully activated {activated} campaign(s)."))

        if run_all or options.get('expire'):
            self.stdout.write("Expiring completed advertising campaigns...")
            completed = AdvertisingCampaignService.complete_expired_campaigns()
            self.stdout.write(self.style.SUCCESS(f"Successfully completed {completed} campaign(s)."))

        if run_all or options.get('aggregate'):
            self.stdout.write("Aggregating campaign daily metrics...")
            result = aggregate_campaign_daily_metrics_task()
            self.stdout.write(self.style.SUCCESS(f"Aggregated {result.get('aggregated_count', 0)} metric record(s)."))
