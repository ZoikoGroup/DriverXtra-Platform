from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from apps.notifications.models import Notification, EmailStatusChoices
from apps.notifications.services import deliver_notification_email, email_enabled, max_email_attempts


class Command(BaseCommand):
    help = (
        "Retry notification emails that are FAILED, or PENDING for longer than --min-age-seconds, "
        "while their attempt count is below NOTIFICATIONS_EMAIL_MAX_ATTEMPTS."
    )

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100, help='Maximum notifications to process (default 100).')
        parser.add_argument(
            '--min-age-seconds',
            type=int,
            default=60,
            help='Only retry PENDING emails older than this, to avoid racing the post-commit send (default 60).',
        )
        parser.add_argument('--dry-run', action='store_true', help='List eligible notifications without sending.')

    def handle(self, *args, **options):
        if not email_enabled():
            self.stdout.write(self.style.WARNING(
                "NOTIFICATIONS_EMAIL_ENABLED is False; no emails will be retried."
            ))
            return

        pending_cutoff = timezone.now() - timedelta(seconds=max(options['min_age_seconds'], 0))
        eligible = Notification.objects.filter(email_attempts__lt=max_email_attempts()).filter(
            Q(email_status=EmailStatusChoices.FAILED)
            | Q(email_status=EmailStatusChoices.PENDING, created_at__lte=pending_cutoff)
        )
        ids = list(eligible.order_by('created_at').values_list('id', flat=True)[: max(options['limit'], 0)])

        if options['dry_run']:
            self.stdout.write(f"{len(ids)} notification email(s) eligible for retry.")
            return

        sent = failed = 0
        for notification_id in ids:
            if deliver_notification_email(notification_id):
                sent += 1
            else:
                failed += 1

        self.stdout.write(self.style.SUCCESS(
            f"Processed {len(ids)} notification email(s): {sent} sent, {failed} not sent."
        ))
