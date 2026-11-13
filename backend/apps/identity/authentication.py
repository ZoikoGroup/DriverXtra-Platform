"""Account-status-aware JWT authentication and token refresh.

Enforces account status on every authenticated request and on every token refresh:
users whose status is SUSPENDED or DEACTIVATED (or whose ``is_active`` is False) are
rejected even if they still hold a previously issued access or refresh token.
PENDING accounts are not blocked here; login already requires an ACTIVE status.

Also re-applies the documented 15-minute access-token lifetime for staff and admin
accounts when an access token is obtained through token refresh (docs/auth-design.md §4).

Session-version revocation: every issued JWT carries the user's ``session_version`` as the
``sv`` claim. A database trigger increments the version whenever the account becomes unusable,
by any update path, so tokens issued before a suspension stay invalid after reactivation.
Tokens without ``sv`` (issued before migration 0008) are treated as version 0.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

STAFF_ACCESS_TOKEN_LIFETIME = timedelta(minutes=15)


def _blocked_statuses():
    from apps.identity.models import AccountStatusChoices
    return (AccountStatusChoices.SUSPENDED, AccountStatusChoices.DEACTIVATED)


def is_account_usable(user) -> bool:
    """True if the account may authenticate (active flag set and not suspended/deactivated)."""
    if user is None or not getattr(user, 'is_active', False):
        return False
    return getattr(user, 'status', None) not in _blocked_statuses()


def account_unusable_message(user) -> str:
    status_value = (getattr(user, 'status', '') or 'inactive').lower()
    if getattr(user, 'is_active', True) is False and status_value == 'active':
        status_value = 'inactive'
    return f"Account is currently {status_value}. Please contact support."


SESSION_VERSION_CLAIM = 'sv'
SESSION_REVOKED_MESSAGE = "Session revoked. Please log in again."


def claimed_session_version(claims):
    """Session version carried by a token or signed payload; a missing claim means version 0.

    Returns None for a malformed value so that callers reject it.
    """
    value = claims.get(SESSION_VERSION_CLAIM, 0)
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def session_version_matches(user, claims) -> bool:
    """True if the token/payload session version equals the user's current session version."""
    claimed = claimed_session_version(claims)
    return claimed is not None and claimed == (getattr(user, 'session_version', 0) or 0)


def stamp_session_version(refresh, user):
    """Add the user's current session version to a refresh token.

    Call before deriving ``refresh.access_token`` so the access token copies the claim.
    """
    refresh[SESSION_VERSION_CLAIM] = user.session_version
    return refresh


def user_authentication_rule(user) -> bool:
    """SimpleJWT USER_AUTHENTICATION_RULE: applied on token refresh."""
    return is_account_usable(user)


def requires_short_lived_access(user, active_role=None) -> bool:
    """Same staff/admin condition used at login and MFA verification."""
    from apps.identity.models import RoleChoices
    is_staff_or_admin = (
        user.is_staff
        or user.is_superuser
        or user.has_role(RoleChoices.STAFF)
        or user.has_role(RoleChoices.ADMIN)
    )
    return bool(is_staff_or_admin or active_role in (RoleChoices.STAFF, RoleChoices.ADMIN))


class StatusAwareJWTAuthentication(JWTAuthentication):
    """JWTAuthentication that also rejects SUSPENDED/DEACTIVATED accounts on every request."""

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if not is_account_usable(user):
            raise AuthenticationFailed(account_unusable_message(user), code="account_inactive")
        if not session_version_matches(user, validated_token):
            raise AuthenticationFailed(SESSION_REVOKED_MESSAGE, code="session_revoked")
        return user


class StaffAwareTokenRefreshSerializer(TokenRefreshSerializer):
    """Token refresh that keeps the 15-minute access lifetime for staff/admin accounts.

    Account status is enforced by the parent serializer through USER_AUTHENTICATION_RULE.
    The session version is checked BEFORE the parent rotates/blacklists the token, so a revoked
    refresh token is never exchanged for a new pair. The ``sv`` claim is carried forward by
    rotation and copied into the new access token.
    """

    def validate(self, attrs):
        try:
            presented = RefreshToken(attrs['refresh'])
        except TokenError:
            presented = None  # invalid/expired/blacklisted: the parent raises the standard error
        if presented is not None:
            user_id = presented.payload.get(api_settings.USER_ID_CLAIM)
            user = get_user_model().objects.filter(**{api_settings.USER_ID_FIELD: user_id}).first() if user_id else None
            if user is not None and not session_version_matches(user, presented.payload):
                raise AuthenticationFailed(SESSION_REVOKED_MESSAGE, code="session_revoked")

        data = super().validate(attrs)

        access = AccessToken(data['access'])
        user_id = access.payload.get(api_settings.USER_ID_CLAIM)
        user = get_user_model().objects.filter(**{api_settings.USER_ID_FIELD: user_id}).first() if user_id else None
        if user is not None and requires_short_lived_access(user, access.payload.get('active_role')):
            access.set_exp(lifetime=STAFF_ACCESS_TOKEN_LIFETIME)
            data['access'] = str(access)
        return data
