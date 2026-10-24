"""Notification creation and email delivery services.

In-app notifications are written in the caller's transaction (inside a savepoint).
Emails are only attempted after that transaction commits, and delivery failures are
recorded on the notification instead of being raised into the business request.
"""

import logging
from functools import partial

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from apps.notifications.models import Notification, EmailStatusChoices

logger = logging.getLogger(__name__)

MAX_ERROR_LENGTH = 500


def email_enabled() -> bool:
    return bool(getattr(settings, 'NOTIFICATIONS_EMAIL_ENABLED', False))


def max_email_attempts() -> int:
    return int(getattr(settings, 'NOTIFICATIONS_EMAIL_MAX_ATTEMPTS', 5))


def build_absolute_link(link: str) -> str:
    if not link:
        return ''
    if link.startswith('http://') or link.startswith('https://'):
        return link
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000').rstrip('/')
    return f"{frontend_url}/{link.lstrip('/')}"


def create_notification(
    *,
    recipient,
    audit_entry,
    title: str,
    message: str = '',
    link: str = '',
    resource_type: str = '',
    resource_id: str = '',
    event_type: str = '',
):
    """Create one notification per (audit entry, recipient) and schedule its email after commit.

    Returns the notification, or None if one already existed for this audit entry and recipient.
    """
    send_email = email_enabled() and bool(recipient.email)

    with transaction.atomic():
        notification, created = Notification.objects.get_or_create(
            source_audit_id=audit_entry.id,
            recipient=recipient,
            defaults={
                'event_type': event_type or audit_entry.event_type,
                'title': title[:255],
                'message': message,
                'link': link,
                'resource_type': resource_type or audit_entry.resource_type,
                'resource_id': str(resource_id or audit_entry.resource_id),
                'email_status': EmailStatusChoices.PENDING if send_email else EmailStatusChoices.NOT_REQUIRED,
            },
        )

    if not created:
        return None

    if send_email:
        transaction.on_commit(partial(_deliver_after_commit, notification.id), robust=True)

    return notification


def _deliver_after_commit(notification_id):
    try:
        deliver_notification_email(notification_id)
    except Exception:
        logger.exception("Unexpected error delivering notification email %s", notification_id)


def _safe_error(exc: Exception) -> str:
    # Exception text from the mail backend (e.g. SMTP server response) never contains our
    # configured credentials; truncate to keep the record compact.
    return f"{exc.__class__.__name__}: {str(exc)}"[:MAX_ERROR_LENGTH]


def deliver_notification_email(notification_id) -> bool:
    """Attempt to email a PENDING or FAILED notification. Returns True if the email was sent."""
    with transaction.atomic():
        notification = (
            Notification.objects.select_for_update()
            .select_related('recipient')
            .filter(pk=notification_id)
            .first()
        )
        if notification is None:
            return False
        if notification.email_status not in (EmailStatusChoices.PENDING, EmailStatusChoices.FAILED):
            return False
        if notification.email_attempts >= max_email_attempts():
            return False

        recipient = notification.recipient
        notification.email_attempts += 1

        context = {
            'recipient_name': recipient.first_name or recipient.full_name,
            'title': notification.title,
            'message': notification.message,
            'link': build_absolute_link(notification.link),
        }
        try:
            send_mail(
                subject=f"DriverXtra: {notification.title}",
                message=render_to_string('notifications/email/notification.txt', context),
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@driverxtra.com'),
                recipient_list=[recipient.email],
                fail_silently=False,
            )
        except Exception as exc:
            notification.email_status = EmailStatusChoices.FAILED
            notification.email_error = _safe_error(exc)
            notification.save(update_fields=['email_status', 'email_error', 'email_attempts', 'updated_at'])
            logger.warning(
                "Notification email failed (notification=%s, attempt=%s, error=%s)",
                notification.id,
                notification.email_attempts,
                exc.__class__.__name__,
            )
            return False

        notification.email_status = EmailStatusChoices.SENT
        notification.email_error = ''
        notification.emailed_at = timezone.now()
        notification.save(update_fields=['email_status', 'email_error', 'email_attempts', 'emailed_at', 'updated_at'])
        return True
