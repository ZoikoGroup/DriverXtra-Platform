from rest_framework import permissions

COMMERCIAL_MANAGE = 'commercial.manage'
COMMERCIAL_APPROVE = 'commercial.approve'
COUNTRY_GATE_MANAGE = 'country_gate.manage'

COMMERCIAL_PERMISSION_CODES = (COMMERCIAL_MANAGE, COMMERCIAL_APPROVE, COUNTRY_GATE_MANAGE)


def user_has(user, code: str) -> bool:
    if not (user and user.is_authenticated):
        return False
    return bool(user.is_superuser or user.has_permission(code))


class IsCommercialStaff(permissions.BasePermission):
    """Platform staff holding any commercial control-plane permission (read access to admin consoles)."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.is_platform_staff):
            return False
        return any(user_has(user, code) for code in COMMERCIAL_PERMISSION_CODES)
