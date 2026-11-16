from django.core.management.base import BaseCommand
from apps.marketplace.vehicle_documents_service import check_expired_vehicle_documents


class Command(BaseCommand):
    help = "Finds verified vehicle compliance documents whose expiry date has passed, transitions them to EXPIRED, records review events, and adjusts order readiness."

    def handle(self, *args, **options):
        self.stdout.write("Evaluating verified vehicle purchase documents for expiry...")
        expired_count = check_expired_vehicle_documents()
        self.stdout.write(
            self.style.SUCCESS(f"Successfully processed {expired_count} expired vehicle purchase document(s).")
        )

