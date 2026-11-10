import uuid

from django.db import models
from django.utils import timezone


class OutboxStatusChoices(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    PUBLISHED = 'PUBLISHED', 'Published'
    FAILED = 'FAILED', 'Failed'


class OutboxEvent(models.Model):
    """Transactional outbox entry (Master Architecture §20–21).

    Written in the same database transaction as the business change, so an event exists
    if and only if that change committed. Publication is at-least-once; consumers must
    de-duplicate with ConsumedEvent.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    topic = models.CharField(max_length=150, db_index=True)
    schema_version = models.PositiveIntegerField(default=1)
    aggregate_type = models.CharField(max_length=100)
    aggregate_id = models.CharField(max_length=255)
    payload = models.JSONField(default=dict, blank=True)
    correlation_id = models.CharField(max_length=255, blank=True, default='')
    actor_id = models.UUIDField(null=True, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
    idempotency_key = models.CharField(max_length=255, unique=True)

    status = models.CharField(
        max_length=20,
        choices=OutboxStatusChoices.choices,
        default=OutboxStatusChoices.PENDING,
    )
    attempts = models.PositiveIntegerField(default=0)
    published_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default='')

    class Meta:
        verbose_name = 'Outbox Event'
        verbose_name_plural = 'Outbox Events'
        ordering = ['occurred_at', 'id']
        indexes = [
            models.Index(fields=['status', 'occurred_at']),
            models.Index(fields=['aggregate_type', 'aggregate_id']),
        ]

    def __str__(self):
        return f"{self.topic} v{self.schema_version} ({self.aggregate_type}:{self.aggregate_id}) - {self.status}"


class ConsumedEvent(models.Model):
    """Records that a named consumer has handled an event, giving exactly-once effects on at-least-once delivery."""

    consumer = models.CharField(max_length=150)
    event_id = models.UUIDField()
    consumed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Consumed Event'
        verbose_name_plural = 'Consumed Events'
        constraints = [
            models.UniqueConstraint(fields=['consumer', 'event_id'], name='unique_consumer_event'),
        ]

    def __str__(self):
        return f"{self.consumer} <- {self.event_id}"
