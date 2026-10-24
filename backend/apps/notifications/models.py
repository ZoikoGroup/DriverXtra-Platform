from django.conf import settings
from django.db import models
from common.models import BaseUUIDModel


class EmailStatusChoices(models.TextChoices):
    NOT_REQUIRED = 'NOT_REQUIRED', 'Not Required'
    PENDING = 'PENDING', 'Pending'
    SENT = 'SENT', 'Sent'
    FAILED = 'FAILED', 'Failed'


class Notification(BaseUUIDModel):
    """In-app notification generated from a successful AuditLog business event."""

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    event_type = models.CharField(max_length=150, db_index=True)
    title = models.CharField(max_length=255)
    message = models.TextField(blank=True, default='')
    link = models.CharField(
        max_length=500,
        blank=True,
        default='',
        help_text="Relative frontend path, e.g. /platform?tab=my_enquiries",
    )
    resource_type = models.CharField(max_length=100, blank=True, default='')
    resource_id = models.CharField(max_length=255, blank=True, default='')

    # Plain UUID reference (no FK): the audit table lives in the separate "platform" schema
    # and is append-only, so a cross-schema foreign key adds no integrity value.
    source_audit_id = models.UUIDField(db_index=True)

    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    email_status = models.CharField(
        max_length=20,
        choices=EmailStatusChoices.choices,
        default=EmailStatusChoices.NOT_REQUIRED,
        db_index=True,
    )
    email_error = models.TextField(blank=True, default='')
    email_attempts = models.PositiveIntegerField(default=0)
    emailed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['source_audit_id', 'recipient'],
                name='unique_notification_per_audit_recipient',
            )
        ]
        indexes = [
            models.Index(fields=['recipient', 'is_read', '-created_at']),
            models.Index(fields=['recipient', '-created_at']),
        ]

    def __str__(self):
        return f"{self.recipient.email} - {self.event_type} ({'read' if self.is_read else 'unread'})"
