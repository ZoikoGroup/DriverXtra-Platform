"""WebSocket session security for workshop chat (JWTAuthMiddleware + WorkshopChatConsumer).

Covers: connection-time account/session-version checks, per-message re-checks, per-broadcast
re-checks for connections opened before a suspension, close code 4401, and that rejected
messages are neither persisted nor broadcast. Legitimate buyer/workshop chat keeps working.
"""
import pytest
from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import RefreshToken

from apps.identity.authentication import stamp_session_version
from apps.identity.models import AccountStatusChoices, User
from apps.workshops.messaging_service import get_or_create_conversation_for_booking
from apps.workshops.middleware import JWTAuthMiddlewareStack, _authenticate_token
from apps.workshops.models import WorkshopMessage
from apps.workshops.routing import websocket_urlpatterns
from tests.test_workshop_messaging import (  # noqa: F401  (fixtures)
    booking,
    buyer,
    organisation,
    other_buyer,
    vehicle,
    workshop_owner,
    workshop_profile,
)

CLOSE_CODE = 4401


def _access_token(user, with_sv=True):
    refresh = RefreshToken.for_user(user)
    if with_sv:
        stamp_session_version(refresh, user)
    return str(refresh.access_token)


def _set_status(user, value):
    User.objects.filter(pk=user.pk).update(status=value)


# --------------------------------------------------------------------------- middleware (sync)

@pytest.mark.django_db
def test_middleware_applies_account_status_and_session_version(buyer, other_buyer):
    token = _access_token(buyer)
    user, sv = _authenticate_token(token)
    assert user.pk == buyer.pk and sv == 0

    _set_status(buyer, AccountStatusChoices.SUSPENDED)  # is_active stays True
    user, sv = _authenticate_token(token)
    assert isinstance(user, AnonymousUser) and sv is None

    _set_status(buyer, AccountStatusChoices.ACTIVE)  # reactivated: old token's version is stale
    assert isinstance(_authenticate_token(token)[0], AnonymousUser)

    fresh_user, fresh_sv = _authenticate_token(_access_token(User.objects.get(pk=buyer.pk)))
    assert fresh_user.pk == buyer.pk and fresh_sv == 1

    # Tokens issued before session versions existed (no 'sv') count as version 0.
    legacy_user, legacy_sv = _authenticate_token(_access_token(other_buyer, with_sv=False))
    assert legacy_user.pk == other_buyer.pk and legacy_sv == 0


# --------------------------------------------------------------------------- full stack (async)

def _application():
    return JWTAuthMiddlewareStack(URLRouter(websocket_urlpatterns))


async def _connect(conv_id, token):
    communicator = WebsocketCommunicator(_application(), f"/ws/workshops/conversations/{conv_id}/?token={token}")
    connected, code = await communicator.connect()
    return communicator, connected, code


@database_sync_to_async
def _conversation(booking, buyer):
    return get_or_create_conversation_for_booking(booking, buyer)


@database_sync_to_async
def _db_set_status(user, value):
    _set_status(user, value)


@database_sync_to_async
def _message_count(conv):
    return WorkshopMessage.objects.filter(conversation=conv).count()


@database_sync_to_async
def _token(user):
    return _access_token(User.objects.get(pk=user.pk))


@pytest.mark.django_db(transaction=True)
def test_connection_rejected_for_suspended_or_revoked_token(booking, buyer):
    async def run():
        conv = await _conversation(booking, buyer)
        token = await _token(buyer)

        ok, connected, _ = await _connect(conv.id, token)
        assert connected
        await ok.disconnect()

        await _db_set_status(buyer, AccountStatusChoices.SUSPENDED)
        _, connected, code = await _connect(conv.id, token)
        assert not connected and code == CLOSE_CODE

        await _db_set_status(buyer, AccountStatusChoices.ACTIVE)
        _, connected, code = await _connect(conv.id, token)  # pre-suspension token stays revoked
        assert not connected and code == CLOSE_CODE

        fresh, connected, _ = await _connect(conv.id, await _token(buyer))
        assert connected
        await fresh.disconnect()

    async_to_sync(run)()


@pytest.mark.django_db(transaction=True)
def test_legitimate_chat_between_buyer_and_workshop_still_works(booking, buyer, workshop_owner):
    async def run():
        conv = await _conversation(booking, buyer)
        buyer_ws, connected, _ = await _connect(conv.id, await _token(buyer))
        assert connected
        owner_ws, connected, _ = await _connect(conv.id, await _token(workshop_owner))
        assert connected

        await buyer_ws.send_json_to({"action": "send_message", "content": "Is my car ready?"})
        for ws in (buyer_ws, owner_ws):
            event = await ws.receive_json_from()
            assert event["type"] == "chat_message"
            assert event["message"]["content"] == "Is my car ready?"

        await owner_ws.send_json_to({"action": "send_message", "content": "Yes, collect at 4 PM."})
        for ws in (buyer_ws, owner_ws):
            event = await ws.receive_json_from()
            assert event["message"]["content"] == "Yes, collect at 4 PM."

        await buyer_ws.send_json_to({"action": "ping"})
        assert (await buyer_ws.receive_json_from())["type"] == "pong"
        assert await _message_count(conv) == 2
        await buyer_ws.disconnect()
        await owner_ws.disconnect()

    async_to_sync(run)()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('reactivate', [False, True], ids=['while_suspended', 'after_reactivation'])
def test_incoming_message_on_existing_connection_is_rejected(booking, buyer, workshop_owner, reactivate):
    async def run():
        conv = await _conversation(booking, buyer)
        buyer_ws, connected, _ = await _connect(conv.id, await _token(buyer))
        assert connected
        owner_ws, connected, _ = await _connect(conv.id, await _token(workshop_owner))
        assert connected
        before = await _message_count(conv)

        await _db_set_status(buyer, AccountStatusChoices.SUSPENDED)
        if reactivate:
            await _db_set_status(buyer, AccountStatusChoices.ACTIVE)

        await buyer_ws.send_json_to({"action": "send_message", "content": "Sent after suspension"})
        closed = await buyer_ws.receive_output()
        assert closed == {"type": "websocket.close", "code": CLOSE_CODE}
        assert await _message_count(conv) == before          # not persisted
        assert await owner_ws.receive_nothing(timeout=0.5)   # not broadcast
        await owner_ws.disconnect()

    async_to_sync(run)()


@pytest.mark.django_db(transaction=True)
def test_existing_connection_stops_receiving_broadcasts_after_suspension(booking, buyer, workshop_owner):
    """Server-to-client exposure: a connection opened before suspension must not receive new messages."""
    async def run():
        conv = await _conversation(booking, buyer)
        buyer_ws, connected, _ = await _connect(conv.id, await _token(buyer))
        assert connected
        owner_ws, connected, _ = await _connect(conv.id, await _token(workshop_owner))
        assert connected

        await _db_set_status(buyer, AccountStatusChoices.SUSPENDED)
        await owner_ws.send_json_to({"action": "send_message", "content": "Private update for the customer"})

        owner_event = await owner_ws.receive_json_from()
        assert owner_event["message"]["content"] == "Private update for the customer"
        buyer_output = await buyer_ws.receive_output()
        assert buyer_output == {"type": "websocket.close", "code": CLOSE_CODE}  # closed, not delivered
        assert await buyer_ws.receive_nothing(timeout=0.5)

        # The workshop side keeps working; later messages are not delivered to the closed connection.
        await owner_ws.send_json_to({"action": "send_message", "content": "Second update"})
        assert (await owner_ws.receive_json_from())["message"]["content"] == "Second update"
        assert await buyer_ws.receive_nothing(timeout=0.5)
        await owner_ws.disconnect()

    async_to_sync(run)()


@pytest.mark.django_db(transaction=True)
def test_mark_read_on_revoked_connection_is_rejected(booking, buyer, workshop_owner):
    async def run():
        conv = await _conversation(booking, buyer)
        buyer_ws, connected, _ = await _connect(conv.id, await _token(buyer))
        assert connected
        owner_ws, connected, _ = await _connect(conv.id, await _token(workshop_owner))
        assert connected

        await _db_set_status(buyer, AccountStatusChoices.DEACTIVATED)
        await buyer_ws.send_json_to({"action": "mark_read"})
        assert await buyer_ws.receive_output() == {"type": "websocket.close", "code": CLOSE_CODE}
        assert await owner_ws.receive_nothing(timeout=0.5)  # no read receipt broadcast
        await owner_ws.disconnect()

    async_to_sync(run)()
