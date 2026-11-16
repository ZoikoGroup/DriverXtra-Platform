from django.core.management.base import BaseCommand
from apps.marketplace.vehicle_offers_service import process_vehicle_payment_verification_escalations


class Command(BaseCommand):
    help = (
        "Evaluates submitted offline vehicle payment reports against the 48-hour warning, "
        "72-hour overdue, and 120-hour operations escalation milestones."
    )

    def handle(self, *args, **options):
        self.stdout.write("Evaluating vehicle order payment verification milestones (48h, 72h, 120h)...")
        results = process_vehicle_payment_verification_escalations()
        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully processed escalations: "
                f"{results['warnings_48h']} 48h warning(s), "
                f"{results['overdue_72h']} 72h overdue warning(s), "
                f"{results['escalated_120h']} 120h operations escalation(s)."
            )
        )

