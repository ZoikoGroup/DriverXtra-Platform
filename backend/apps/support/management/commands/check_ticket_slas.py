import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.support.services import TicketService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Evaluates SLA response/resolution deadlines, advances escalation stages, and auto-closes inactive tickets."

    def handle(self, *args, **options):
        now = timezone.now()
        self.stdout.write(f"[{now.isoformat()}] Starting customer support SLA and escalation evaluation...")
        try:
            metrics = TicketService.check_slas_and_escalate(now=now)
            self.stdout.write(self.style.SUCCESS(
                f"SLA Check complete. Evaluated: {metrics['evaluated']}, "
                f"75% Warnings: {metrics['warning_75_escalated']}, "
                f"100% Breaches: {metrics['breach_100_escalated']}, "
                f"Tier 3 Escalations: {metrics['tier_3_escalated']}, "
                f"Auto-Closed Inactive: {metrics['auto_closed_inactive']}."
            ))
        except Exception as exc:
            logger.exception("Error executing check_ticket_slas command: %s", exc)
            self.stderr.write(self.style.ERROR(f"SLA Check failed: {exc}"))
            raise

