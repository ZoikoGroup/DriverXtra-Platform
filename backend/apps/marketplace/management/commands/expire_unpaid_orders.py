from django.core.management.base import BaseCommand
from apps.marketplace.payments.service import PaymentService


class Command(BaseCommand):
    help = "Finds and auto-expires stale unpaid online orders, releasing held stock back to seller inventory."

    def add_arguments(self, parser):
        parser.add_argument(
            '--max-age-minutes',
            type=int,
            default=30,
            help="Maximum age in minutes before an unpaid online order is considered expired (default: 30).",
        )

    def handle(self, *args, **options):
        max_age = options['max_age_minutes']
        self.stdout.write(f"Checking for unpaid online orders older than {max_age} minutes...")
        expired = PaymentService.expire_stale_pending_orders(max_age_minutes=max_age)
        self.stdout.write(self.style.SUCCESS(f"Successfully auto-expired {expired} stale unpaid orders."))

