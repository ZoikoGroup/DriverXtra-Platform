import logging
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.exceptions import PermissionDenied, ValidationError as DjangoValidationError
from django.db import transaction, models
from django.utils import timezone

from apps.notifications.models import Notification
from apps.workshops.models import (
    WorkshopBooking,
    WorkshopConversation,
    WorkshopMessage,
    WorkshopProfile,
    SenderTypeChoices,
)
from apps.workshops.permissions import is_workshop_staff_or_admin

logger = logging.getLogger(__name__)


def check_user_can_access_conversation(user, conversation: WorkshopConversation) -> bool:
    """
    Check if the user is a permitted participant:
    - The booking customer (buyer)
    - Workshop staff/admin/owner of the workshop
    - Platform administrator / superuser
    """
    if not (user and user.is_authenticated):
        return False
    if user.is_superuser:
        return True
    if user.id == conversation.buyer_id:
        return True
    return is_workshop_staff_or_admin(user, conversation.workshop)


def get_or_create_conversation_for_booking(booking: WorkshopBooking, user) -> WorkshopConversation:
    """
    Retrieves or initializes a persistent conversation thread for a booking.
    Enforces authorization check for the requesting user.
    """
    if not (user and user.is_authenticated):
        raise PermissionDenied("Authentication required to access conversation.")

    is_buyer = (user.id == booking.buyer_id)
    is_staff = is_workshop_staff_or_admin(user, booking.workshop) or user.is_superuser
    if not (is_buyer or is_staff):
        raise PermissionDenied("You are not authorized to access conversations for this booking.")

    conversation, _ = WorkshopConversation.objects.get_or_create(
        booking=booking,
        defaults={
            "workshop": booking.workshop,
            "buyer": booking.buyer,
        },
    )
    return conversation


def get_user_conversations(user):
    """
    Returns a queryset of conversations accessible to the given user,
    annotated with relevant counts and ordered by latest activity.
    """
    if not (user and user.is_authenticated):
        return WorkshopConversation.objects.none()

    if user.is_superuser:
        return WorkshopConversation.objects.all().order_by("-last_message_at")

    # Workshops where user is an active member
    org_ids = user.organisation_memberships.filter(is_active=True).values_list("organisation_id", flat=True)
    workshop_ids = WorkshopProfile.objects.filter(organisation_id__in=org_ids).values_list("id", flat=True)

    return (
        WorkshopConversation.objects.filter(
            models.Q(buyer=user) | models.Q(workshop_id__in=workshop_ids)
        )
        .select_related("booking", "workshop", "buyer")
        .order_by("-last_message_at")
        .distinct()
    )


def create_message(
    conversation: WorkshopConversation,
    sender,
    content: str,
    attachment_url: str = "",
) -> WorkshopMessage:
    """
    Persists a new message in PostgreSQL, updates conversation timestamps,
    broadcasts the event via Channels WebSocket, and alerts the counterparty.
    """
    if not check_user_can_access_conversation(sender, conversation):
        raise PermissionDenied("You are not authorized to send messages in this conversation.")

    clean_content = (content or "").strip()
    clean_attachment = (attachment_url or "").strip()
    if not clean_content and not clean_attachment:
        raise DjangoValidationError("Message content cannot be empty.")

    is_buyer = (sender.id == conversation.buyer_id)
    sender_type = SenderTypeChoices.BUYER if is_buyer else SenderTypeChoices.WORKSHOP

    with transaction.atomic():
        message = WorkshopMessage.objects.create(
            conversation=conversation,
            sender=sender,
            sender_type=sender_type,
            content=clean_content,
            attachment_url=clean_attachment,
        )
        conversation.last_message_at = message.created_at
        conversation.save(update_fields=["last_message_at", "updated_at"])

    # 1. Broadcast real-time message via Django Channels
    try:
        channel_layer = get_channel_layer()
        if channel_layer:
            sender_name = getattr(sender, "full_name", "") or getattr(sender, "email", "User")
            async_to_sync(channel_layer.group_send)(
                f"workshop_chat_{conversation.id}",
                {
                    "type": "chat_message",
                    "message": {
                        "id": str(message.id),
                        "conversation_id": str(conversation.id),
                        "sender_id": str(sender.id),
                        "sender_name": sender_name,
                        "sender_type": sender_type,
                        "content": message.content,
                        "attachment_url": message.attachment_url,
                        "is_read": message.is_read,
                        "read_at": None,
                        "created_at": message.created_at.isoformat(),
                    },
                },
            )
    except Exception as ws_err:
        logger.warning("Failed to broadcast WebSocket chat message: %s", ws_err)

    # 2. In-app notification to the counterparty
    try:
        recipient = None
        if sender_type == SenderTypeChoices.BUYER:
            recipient = getattr(conversation.workshop.organisation, "created_by", None)
        else:
            recipient = conversation.buyer

        if recipient and recipient.id != sender.id:
            booking_number = getattr(conversation.booking, "booking_number", "Booking")
            sender_name = getattr(sender, "full_name", "") or getattr(sender, "email", "User")
            preview = clean_content[:120] if clean_content else "Sent an attachment"
            with transaction.atomic():
                Notification.objects.create(
                    recipient=recipient,
                    source_audit_id=message.id,
                    event_type="workshop.message.received",
                    title=f"New Message #{booking_number}",
                    message=f"{sender_name}: {preview}",
                    link="/platform?tab=workshops",
                    resource_type="WorkshopConversation",
                    resource_id=str(conversation.id),
                )
    except Exception as notif_err:
        logger.warning("Failed to dispatch message in-app notification: %s", notif_err)

    return message


def mark_messages_as_read(conversation: WorkshopConversation, user) -> int:
    """
    Marks all unread messages from other participants as read,
    and broadcasts a read receipt to the WebSocket group.
    """
    if not check_user_can_access_conversation(user, conversation):
        raise PermissionDenied("You are not authorized to update messages in this conversation.")

    with transaction.atomic():
        updated = (
            WorkshopMessage.objects.filter(
                conversation=conversation,
                is_read=False,
            )
            .exclude(sender=user)
            .update(is_read=True, read_at=timezone.now())
        )

    if updated > 0:
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f"workshop_chat_{conversation.id}",
                    {
                        "type": "read_receipt",
                        "conversation_id": str(conversation.id),
                        "reader_id": str(user.id),
                        "read_at": timezone.now().isoformat(),
                    },
                )
        except Exception as ws_err:
            logger.warning("Failed to broadcast read receipt: %s", ws_err)

    return updated
