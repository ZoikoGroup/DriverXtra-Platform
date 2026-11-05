import logging
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken

logger = logging.getLogger(__name__)
User = get_user_model()


@database_sync_to_async
def get_user_from_token(token_string: str):
    try:
        access_token = AccessToken(token_string)
        user_id = access_token.get("user_id")
        if not user_id:
            return AnonymousUser()
        return User.objects.get(pk=user_id, is_active=True)
    except (InvalidToken, TokenError, User.DoesNotExist, Exception) as exc:
        logger.debug("WebSocket JWT authentication failed: %s", exc)
        return AnonymousUser()


class JWTAuthMiddleware:
    """
    Channels middleware that populates scope['user'] from a SimpleJWT token
    provided either as a query parameter ?token=<jwt> or Authorization header.
    """

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        query_string = scope.get("query_string", b"").decode("utf-8")
        query_params = parse_qs(query_string)
        token = None

        if "token" in query_params:
            token = query_params["token"][0]
        else:
            headers = dict(scope.get("headers", []))
            auth_header = headers.get(b"authorization", b"").decode("utf-8")
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ", 1)[1].strip()

        if token:
            scope["user"] = await get_user_from_token(token)
        else:
            scope["user"] = AnonymousUser()

        return await self.inner(scope, receive, send)


def JWTAuthMiddlewareStack(inner):
    return JWTAuthMiddleware(inner)

