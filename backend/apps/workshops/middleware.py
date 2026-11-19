import logging
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken

logger = logging.getLogger(__name__)
User = get_user_model()


def _authenticate_token(token_string: str):
    """Returns (user, session_version) for a valid access token, else (AnonymousUser(), None).

    Applies the same account rules as HTTP authentication: the account must be usable
    (is_active and not SUSPENDED/DEACTIVATED) and the token's session version ('sv', missing = 0)
    must equal the user's current session version.
    """
    from apps.identity.authentication import (
        claimed_session_version,
        is_account_usable,
        session_version_matches,
    )
    try:
        access_token = AccessToken(token_string)
        user_id = access_token.get("user_id")
        if not user_id:
            return AnonymousUser(), None
        user = User.objects.get(pk=user_id, is_active=True)
        if not is_account_usable(user) or not session_version_matches(user, access_token):
            logger.info("WebSocket JWT rejected: account unusable or session revoked (user %s).", user_id)
            return AnonymousUser(), None
        return user, claimed_session_version(access_token)
    except (InvalidToken, TokenError, User.DoesNotExist, Exception) as exc:
        logger.debug("WebSocket JWT authentication failed: %s", exc)
        return AnonymousUser(), None


@database_sync_to_async
def get_user_and_session_version_from_token(token_string: str):
    return _authenticate_token(token_string)


@database_sync_to_async
def get_user_from_token(token_string: str):
    return _authenticate_token(token_string)[0]


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
            user, session_version = await get_user_and_session_version_from_token(token)
            scope["user"] = user
            # Session version the connection was authenticated with; the consumer re-checks it
            # against the database on every incoming message and outgoing broadcast.
            scope["jwt_session_version"] = session_version
        else:
            scope["user"] = AnonymousUser()

        return await self.inner(scope, receive, send)


def JWTAuthMiddlewareStack(inner):
    return JWTAuthMiddleware(inner)

