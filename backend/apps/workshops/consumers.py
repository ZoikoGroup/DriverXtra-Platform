import logging
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth import get_user_model

from apps.identity.authentication import is_account_usable

from apps.workshops.models import WorkshopConversation
from apps.workshops.messaging_service import (
    check_user_can_access_conversation,
    create_message,
    mark_messages_as_read,
)

logger = logging.getLogger(__name__)

# Application close code (4000-4999 range) for unauthenticated / revoked sessions, mirroring HTTP 401.
SESSION_INVALID_CLOSE_CODE = 4401


class WorkshopChatConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer for real-time workshop messaging.
    Guarantees participant authorization, broadcast isolation per conversation,
    and automatic database persistence.

    Session security: the account status and session version are checked when connecting,
    before processing every incoming message, and before delivering every broadcast to this
    connection. A suspended/deactivated account or a revoked session (version changed since the
    token was issued) gets the connection closed with code 4401; the rejected message is neither
    persisted nor broadcast, and no further broadcasts are delivered to it.
    """

    async def connect(self):
        self.user = self.scope.get("user")
        if not (self.user and self.user.is_authenticated):
            logger.warning("Unauthenticated WebSocket connection rejected.")
            await self.close(code=SESSION_INVALID_CLOSE_CODE)
            return

        if not await self._session_still_valid():
            logger.warning("WebSocket connection rejected: account unusable or session revoked (user %s).", self.user.id)
            await self.close(code=SESSION_INVALID_CLOSE_CODE)
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
        # Re-check before processing ANY incoming message (send_message, mark_read, ping, ...).
        if not await self._session_still_valid():
            await self._close_revoked_session()
            return

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
        # Connections opened before a suspension must not keep receiving messages.
        if not await self._session_still_valid():
            await self._close_revoked_session()
            return
        await self.send_json({
            "type": "chat_message",
            "message": event["message"],
        })

    async def read_receipt(self, event):
        """Broadcast handler invoked by group_send for read_receipt."""
        if not await self._session_still_valid():
            await self._close_revoked_session()
            return
        await self.send_json({
            "type": "read_receipt",
            "conversation_id": event["conversation_id"],
            "reader_id": event["reader_id"],
            "read_at": event["read_at"],
        })

    async def _close_revoked_session(self):
        """Stop delivery to this connection immediately and close it."""
        if getattr(self, "_session_revoked", False):
            return
        self._session_revoked = True
        logger.warning(
            "Closing WebSocket: account unusable or session revoked (user %s).",
            getattr(self.user, "id", None),
        )
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
        await self.close(code=SESSION_INVALID_CLOSE_CODE)

    @database_sync_to_async
    def _session_still_valid(self):
        """Fresh database check: account usable and session version unchanged since connect.

        The expected version comes from the JWT used to connect (set by JWTAuthMiddleware);
        a missing value means version 0, matching tokens issued before session versions existed.
        """
        if getattr(self, "_session_revoked", False):
            return False
        user_id = getattr(self.user, "pk", None)
        if user_id is None:
            return False
        current = (
            get_user_model().objects.filter(pk=user_id)
            .only("is_active", "status", "session_version")
            .first()
        )
        if current is None or not is_account_usable(current):
            return False
        expected = self.scope.get("jwt_session_version", 0)
        return expected is not None and current.session_version == expected

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

