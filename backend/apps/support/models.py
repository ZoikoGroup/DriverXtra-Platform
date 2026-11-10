import os
import uuid
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.utils import timezone
from common.models import BaseUUIDModel


class PrivateSupportStorage(FileSystemStorage):
    """
    Dedicated private filesystem storage for support attachments.
    Files are stored outside public MEDIA_ROOT and direct URL access is strictly forbidden.
    """
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('location', str(getattr(settings, 'PRIVATE_STORAGE_ROOT', settings.BASE_DIR / 'private_media')))
        kwargs.setdefault('base_url', None)
        super().__init__(*args, **kwargs)

    def url(self, name):
        raise ValueError("Private storage does not provide public URLs. Use the verified streaming download endpoint.")

    def deconstruct(self):
        return ('apps.support.models.PrivateSupportStorage', (), {})


private_support_storage = PrivateSupportStorage()


def ticket_attachment_upload_path(instance, filename: str) -> str:
    """Generates an unguessable storage path isolated per ticket."""
    ext = os.path.splitext(filename)[1].lower()
    ticket_id = str(instance.ticket_id or (instance.ticket.id if instance.ticket else 'unassigned'))
    return f"support_attachments/{ticket_id}/{uuid.uuid4().hex}{ext}"


class TicketCategoryChoices(models.TextChoices):
    GENERAL_INQUIRY = 'GENERAL_INQUIRY', 'General Inquiry'
    ORDER_ISSUE = 'ORDER_ISSUE', 'Order & Delivery Issue'
    PART_COMPATIBILITY = 'PART_COMPATIBILITY', 'Part Fitment & Compatibility'
    WORKSHOP_BOOKING = 'WORKSHOP_BOOKING', 'Workshop Booking & Services'
    PAYMENT_BILLING = 'PAYMENT_BILLING', 'Payment & Invoice Assistance'
    ACCOUNT_SECURITY = 'ACCOUNT_SECURITY', 'Account & Profile Security'
    RETURNS_ASSISTANCE = 'RETURNS_ASSISTANCE', 'Returns & Refunds Assistance'
    TECHNICAL_SUPPORT = 'TECHNICAL_SUPPORT', 'Technical Platform Issue'


class TicketPriorityChoices(models.TextChoices):
    LOW = 'LOW', 'Low'
    MEDIUM = 'MEDIUM', 'Medium'
    HIGH = 'HIGH', 'High'
    CRITICAL = 'CRITICAL', 'Critical'


class TicketStatusChoices(models.TextChoices):
    OPEN = 'OPEN', 'Open'
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
    WAITING_FOR_CUSTOMER = 'WAITING_FOR_CUSTOMER', 'Waiting for Customer'
    RESOLVED = 'RESOLVED', 'Resolved'
    CLOSED = 'CLOSED', 'Closed'


class EscalationStageChoices(models.IntegerChoices):
    NONE = 0, 'Normal'
    WARNING_75 = 1, 'Approaching Breach (75%)'
    BREACH_100 = 2, 'SLA Breached (100%)'
    TIER_3 = 3, 'Critical / Prolonged Escalation'


class SenderTypeChoices(models.TextChoices):
    CUSTOMER = 'CUSTOMER', 'Customer'
    AGENT = 'AGENT', 'Support Agent'
    SYSTEM = 'SYSTEM', 'System'


class TicketActivityTypeChoices(models.TextChoices):
    CREATED = 'CREATED', 'Ticket Created'
    ASSIGNED = 'ASSIGNED', 'Assigned / Reassigned'
    STATUS_CHANGED = 'STATUS_CHANGED', 'Status Changed'
    PRIORITY_CHANGED = 'PRIORITY_CHANGED', 'Priority Changed'
    CATEGORY_CHANGED = 'CATEGORY_CHANGED', 'Category Changed'
    PUBLIC_REPLY = 'PUBLIC_REPLY', 'Public Reply'
    INTERNAL_NOTE = 'INTERNAL_NOTE', 'Internal Staff Note'
    SLA_PAUSED = 'SLA_PAUSED', 'SLA Paused'
    SLA_RESUMED = 'SLA_RESUMED', 'SLA Resumed'
    ESCALATED = 'ESCALATED', 'Ticket Escalated'
    RESOLVED = 'RESOLVED', 'Ticket Resolved'
    REOPENED = 'REOPENED', 'Ticket Reopened'
    CLOSED = 'CLOSED', 'Ticket Closed'
    AGENT_DEACTIVATED_UNASSIGNED = 'AGENT_DEACTIVATED_UNASSIGNED', 'Agent Deactivated - Unassigned'
    SYSTEM_AUTO_CLOSED = 'SYSTEM_AUTO_CLOSED', 'System Auto-Closed (Inactivity)'


class Ticket(BaseUUIDModel):
    """Authoritative Customer Support Ticket model with granular SLA and lifecycle tracking."""

    ticket_number = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="Collision-free unique ticket identifier (e.g. TICK-YYYYMMDD-XXXXXX).",
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='support_tickets',
        db_index=True,
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_support_tickets',
        db_index=True,
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='support_tickets_assigned',
    )
    assigned_at = models.DateTimeField(null=True, blank=True)

    subject = models.CharField(max_length=255)
    category = models.CharField(
        max_length=40,
        choices=TicketCategoryChoices.choices,
        default=TicketCategoryChoices.GENERAL_INQUIRY,
        db_index=True,
    )
    priority = models.CharField(
        max_length=20,
        choices=TicketPriorityChoices.choices,
        default=TicketPriorityChoices.MEDIUM,
        db_index=True,
    )
    status = models.CharField(
        max_length=30,
        choices=TicketStatusChoices.choices,
        default=TicketStatusChoices.OPEN,
        db_index=True,
    )
    description = models.TextField()
    related_order_number = models.CharField(max_length=100, blank=True, default='', db_index=True)
    is_confidential = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Confidential tickets are visible only to Platform Admins and cleared leads.",
    )

    # SLA tracking fields
    first_response_due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    first_responded_at = models.DateTimeField(null=True, blank=True)
    is_first_response_overdue = models.BooleanField(default=False, db_index=True)

    resolution_due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    is_resolution_overdue = models.BooleanField(default=False, db_index=True)

    sla_paused_at = models.DateTimeField(null=True, blank=True)
    total_paused_seconds = models.PositiveIntegerField(default=0)
    sla_breached = models.BooleanField(default=False, db_index=True)

    # Escalation tracking
    escalation_stage = models.PositiveSmallIntegerField(
        choices=EscalationStageChoices.choices,
        default=EscalationStageChoices.NONE,
        db_index=True,
    )
    is_escalated = models.BooleanField(default=False, db_index=True)
    escalated_at = models.DateTimeField(null=True, blank=True)
    escalation_reason = models.TextField(blank=True, default='')

    # Resolution & Closure
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_support_tickets',
    )
    resolution_summary = models.TextField(blank=True, default='')
    closed_at = models.DateTimeField(null=True, blank=True)
    reopen_count = models.PositiveIntegerField(default=0)

    # Inactivity tracking
    last_customer_activity_at = models.DateTimeField(default=timezone.now, db_index=True)
    last_agent_activity_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Support Ticket'
        verbose_name_plural = 'Support Tickets'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'priority']),
            models.Index(fields=['customer', 'status']),
            models.Index(fields=['assigned_to', 'status']),
            models.Index(fields=['is_confidential', 'status']),
            models.Index(fields=['is_escalated', 'status']),
            models.Index(fields=['status', 'last_customer_activity_at']),
        ]

    def __str__(self):
        return f"{self.ticket_number} - {self.subject} ({self.status})"


class TicketMessage(BaseUUIDModel):
    """Customer-Agent conversation messages and private internal notes."""

    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name='messages',
        db_index=True,
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='support_messages',
    )
    sender_type = models.CharField(
        max_length=20,
        choices=SenderTypeChoices.choices,
        default=SenderTypeChoices.CUSTOMER,
    )
    message = models.TextField()
    is_internal = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Internal notes are private to staff and NEVER visible to customers.",
    )

    class Meta:
        verbose_name = 'Ticket Message'
        verbose_name_plural = 'Ticket Messages'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['ticket', 'created_at']),
            models.Index(fields=['ticket', 'is_internal']),
        ]

    def __str__(self):
        kind = "Internal Note" if self.is_internal else "Public Message"
        sender_email = self.sender.email if self.sender else "System"
        return f"[{kind}] {self.ticket.ticket_number} by {sender_email}"


class TicketAttachment(BaseUUIDModel):
    """Secure file attachment uploaded to a ticket or message."""

    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name='attachments',
        db_index=True,
    )
    message = models.ForeignKey(
        TicketMessage,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='attachments',
    )
    uploader = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='support_attachments',
    )
    file = models.FileField(storage=private_support_storage, upload_to=ticket_attachment_upload_path)
    file_name = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(help_text="File size in bytes.")
    content_type = models.CharField(max_length=100)
    is_internal = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Internal attachments are served strictly to staff with support permissions.",
    )

    class Meta:
        verbose_name = 'Ticket Attachment'
        verbose_name_plural = 'Ticket Attachments'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['ticket', 'is_internal']),
        ]

    def __str__(self):
        return f"{self.file_name} ({self.file_size} bytes) - Ticket {self.ticket.ticket_number}"


class TicketActivity(BaseUUIDModel):
    """Audit and activity history for state transitions, assignments, and escalations."""

    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name='activities',
        db_index=True,
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='support_activities',
    )
    activity_type = models.CharField(
        max_length=50,
        choices=TicketActivityTypeChoices.choices,
        db_index=True,
    )
    old_value = models.CharField(max_length=255, blank=True, default='')
    new_value = models.CharField(max_length=255, blank=True, default='')
    notes = models.TextField(blank=True, default='')

    class Meta:
        verbose_name = 'Ticket Activity'
        verbose_name_plural = 'Ticket Activities'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['ticket', 'created_at']),
            models.Index(fields=['activity_type', 'created_at']),
        ]

    def __str__(self):
        actor_email = self.actor.email if self.actor else "System"
        return f"{self.ticket.ticket_number} - {self.activity_type} by {actor_email}"

