from django.core.management.base import BaseCommand
from apps.marketplace.vehicle_offers_service import cancel_expired_payment_orders


class Command(BaseCommand):
    help = "Finds and auto-expires VehicleOrder records where the 5-business-day payment deadline has passed, safely releasing the vehicle."

    def handle(self, *args, **options):
        self.stdout.write("Evaluating unfulfilled vehicle reservations with expired payment deadlines...")
        cancelled_count = cancel_expired_payment_orders()
        self.stdout.write(
            self.style.SUCCESS(f"Successfully processed and cancelled {cancelled_count} expired vehicle order(s).")
        )

