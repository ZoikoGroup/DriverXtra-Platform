from django.core.management.base import BaseCommand
from apps.marketplace.vehicle_offers_service import expire_pending_vehicle_offers


class Command(BaseCommand):
    help = "Finds and auto-expires VehiclePurchaseOffer records where the response deadline has passed, recording immutable audit actions."

    def handle(self, *args, **options):
        self.stdout.write("Evaluating pending vehicle purchase offers with expired negotiation deadlines...")
        expired_count = expire_pending_vehicle_offers()
        self.stdout.write(
            self.style.SUCCESS(f"Successfully processed and expired {expired_count} vehicle purchase offer(s).")
        )

