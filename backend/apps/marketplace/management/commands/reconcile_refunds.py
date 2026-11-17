from django.core.management.base import BaseCommand
from apps.marketplace.returns.service import RefundService


class Command(BaseCommand):
    help = "Finds and reconciles all refunds in PROCESSING_UNKNOWN status with payment gateway providers."

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch',
            type=int,
            default=50,
            help="Maximum number of ambiguous refunds to reconcile in this batch (default: 50).",
        )

    def handle(self, *args, **options):
        batch = options['batch']
        self.stdout.write(f"Reconciling up to {batch} pending-unknown refunds...")
        results = RefundService.reconcile_all_pending_unknown(max_batch=batch)
        self.stdout.write(
            self.style.SUCCESS(
                f"Reconciliation completed: {results['total_evaluated']} evaluated, "
                f"{results['succeeded']} succeeded, {results['failed']} confirmed failed, "
                f"{results['unknown']} remaining inconclusive."
            )
        )

