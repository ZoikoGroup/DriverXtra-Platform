from django.core.management.base import BaseCommand

from platform_core.events.outbox import publish_pending_events


class Command(BaseCommand):
    help = "Deliver pending outbox events to registered in-process consumers (at-least-once, consumer-deduplicated)."

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100, help='Maximum events to process (default 100).')

    def handle(self, *args, **options):
        results = publish_pending_events(limit=max(options['limit'], 0))
        self.stdout.write(self.style.SUCCESS(
            f"Outbox: {results['published']} published, {results['failed']} failed."
        ))
