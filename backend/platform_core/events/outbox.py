"""Transactional outbox: emit events with business changes, publish them at-least-once.

Usage inside a business operation:

    with transaction.atomic():
        sku.save()
        emit_event('commercial.sku.published', aggregate_type='CommercialSku', aggregate_id=sku.id,
                   payload={...}, idempotency_key=f'commercial.sku.published:{sku.id}')

Consumers register with @register_consumer(topic, name) and are invoked by
`python manage.py publish_outbox_events`. Each consumer runs at most once per event.
"""

import logging
from collections import defaultdict
from typing import Callable, Dict, List, Optional, Tuple

from django.db import IntegrityError, transaction
from django.utils import timezone

from common.middleware import get_current_correlation_id
from platform_core.events.models import ConsumedEvent, OutboxEvent, OutboxStatusChoices

logger = logging.getLogger(__name__)

MAX_PUBLISH_ATTEMPTS = 10

_consumers: Dict[str, List[Tuple[str, Callable[[OutboxEvent], None]]]] = defaultdict(list)


def emit_event(
    topic: str,
    *,
    aggregate_type: str,
    aggregate_id,
    payload: Optional[dict] = None,
    idempotency_key: str,
    actor_id=None,
    schema_version: int = 1,
    correlation_id: str = '',
) -> OutboxEvent:
    """Write an outbox event in the caller's transaction.

    Re-emitting with the same idempotency key returns the existing event instead of duplicating it.
    """
    with transaction.atomic():
        event, _ = OutboxEvent.objects.get_or_create(
            idempotency_key=idempotency_key,
            defaults={
                'topic': topic,
                'schema_version': schema_version,
                'aggregate_type': aggregate_type,
                'aggregate_id': str(aggregate_id),
                'payload': payload or {},
                'actor_id': actor_id,
                'correlation_id': correlation_id or get_current_correlation_id(),
            },
        )
    return event


def register_consumer(topic: str, name: str):
    """Decorator registering an in-process consumer for a topic."""
    def decorator(func: Callable[[OutboxEvent], None]):
        if not any(existing_name == name for existing_name, _ in _consumers[topic]):
            _consumers[topic].append((name, func))
        return func
    return decorator


def consumers_for(topic: str) -> List[Tuple[str, Callable[[OutboxEvent], None]]]:
    return list(_consumers.get(topic, []))


def _deliver_to_consumer(event: OutboxEvent, name: str, func) -> None:
    """Run one consumer exactly once for this event (its effects and the dedupe marker commit together)."""
    with transaction.atomic():
        try:
            with transaction.atomic():
                ConsumedEvent.objects.create(consumer=name, event_id=event.id)
        except IntegrityError:
            return  # already consumed
        func(event)


def publish_pending_events(limit: int = 100) -> dict:
    """Deliver PENDING/FAILED events to registered consumers. Safe to run concurrently or repeatedly."""
    results = {'published': 0, 'failed': 0}
    candidate_ids = list(
        OutboxEvent.objects.filter(
            status__in=[OutboxStatusChoices.PENDING, OutboxStatusChoices.FAILED],
            attempts__lt=MAX_PUBLISH_ATTEMPTS,
        )
        .order_by('occurred_at', 'id')
        .values_list('id', flat=True)[:limit]
    )
    for event_id in candidate_ids:
        with transaction.atomic():
            event = (
                OutboxEvent.objects.select_for_update()
                .filter(pk=event_id, status__in=[OutboxStatusChoices.PENDING, OutboxStatusChoices.FAILED])
                .first()
            )
            if event is None:
                continue
            event.attempts += 1
            try:
                for name, func in consumers_for(event.topic):
                    _deliver_to_consumer(event, name, func)
            except Exception as exc:
                event.status = OutboxStatusChoices.FAILED
                event.last_error = f"{exc.__class__.__name__}: {exc}"[:1000]
                event.save(update_fields=['status', 'attempts', 'last_error'])
                logger.warning("Outbox event %s (%s) failed: %s", event.id, event.topic, exc.__class__.__name__)
                results['failed'] += 1
                continue
            event.status = OutboxStatusChoices.PUBLISHED
            event.published_at = timezone.now()
            event.last_error = ''
            event.save(update_fields=['status', 'attempts', 'published_at', 'last_error'])
            results['published'] += 1
    return results
