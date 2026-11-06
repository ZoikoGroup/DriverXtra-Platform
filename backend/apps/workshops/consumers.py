import logging
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.workshops.models import WorkshopConversation
from apps.workshops.messaging_service import (
    check_user_can_access_conversation,
    create_message,
    mark_messages_as_read,
)

logger = logging.getLogger(__name__)


class WorkshopChatConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer for real-time workshop messaging.
    Guarantees participant authorization, broadcast isolation per conversation,
    and automatic database persistence.
    """

    async def connect(self):
        self.user = self.scope.get("user")
        if not (self.user and self.user.is_authenticated):
            logger.warning("Unauthenticated WebSocket connection rejected.")
            await self.close(code=4401)
            return

        self.conversation_id = self.scope["url_route"]["kwargs"].get("conversation_id")
        self.conversation = await self._get_and_authorize_conversation()
        if not self.conversation:
            logger.warning(
                "Unauthorized WebSocket access attempt for conversation %s by user %s",
                self.conversation_id,
                self.user.id,
            )
            await self.close(code=4403)
            return

        self.room_group_name = f"workshop_chat_{self.conversation_id}"
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        logger.info(
            "WebSocket connected: user %s to room %s",
            self.user.id,
            self.room_group_name,
        )

    async def disconnect(self, close_code):
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
            logger.info("WebSocket disconnected from %s (code %s)", self.room_group_name, close_code)

    async def receive_json(self, content):
        action = content.get("action")
        if action == "send_message":
            text = content.get("content", "")
            attachment_url = content.get("attachment_url", "")
            try:
                await self._persist_and_broadcast_message(text, attachment_url)
            except Exception as err:
                logger.error("Error creating message: %s", err)
                await self.send_json({"type": "error", "message": str(err)})

        elif action == "mark_read":
            try:
                await self._mark_messages_read()
            except Exception as err:
                logger.error("Error marking messages read: %s", err)
                await self.send_json({"type": "error", "message": str(err)})

        elif action == "ping":
            await self.send_json({"type": "pong"})

        else:
            await self.send_json({"type": "error", "message": f"Unknown action: {action}"})

    async def chat_message(self, event):
        """Broadcast handler invoked by group_send for chat_message."""
        await self.send_json({
            "type": "chat_message",
            "message": event["message"],
        })

    async def read_receipt(self, event):
        """Broadcast handler invoked by group_send for read_receipt."""
        await self.send_json({
            "type": "read_receipt",
            "conversation_id": event["conversation_id"],
            "reader_id": event["reader_id"],
            "read_at": event["read_at"],
        })

    @database_sync_to_async
    def _get_and_authorize_conversation(self):
        try:
            conversation = (
                WorkshopConversation.objects.select_related(
                    "workshop__organisation", "booking"
                ).get(id=self.conversation_id)
            )
            if check_user_can_access_conversation(self.user, conversation):
                return conversation
            return None
        except (WorkshopConversation.DoesNotExist, Exception):
            return None

    @database_sync_to_async
    def _persist_and_broadcast_message(self, text, attachment_url):
        return create_message(
            conversation=self.conversation,
            sender=self.user,
            content=text,
            attachment_url=attachment_url,
        )

    @database_sync_to_async
    def _mark_messages_read(self):
        return mark_messages_as_read(
            conversation=self.conversation,
            user=self.user,
        )

