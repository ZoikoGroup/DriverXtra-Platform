from rest_framework import permissions

class IsMarketplaceAdmin(permissions.BasePermission):
    """Allows access only to Marketplace Administrators or Superusers."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return (
            user.is_superuser
            or user.has_role('ADMIN')
            or user.has_role('MARKETPLACE_ADMIN')
        )


class IsPlatformStaff(permissions.BasePermission):
    """Allows access to Platform Staff, Operations, and Marketplace Admins."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return (
            user.is_staff
            or user.is_superuser
            or user.has_role('STAFF')
            or user.has_role('OPERATIONS')
            or user.has_role('ADMIN')
            or user.has_role('MARKETPLACE_ADMIN')
        )


class IsOrganisationMember(permissions.BasePermission):
    """Allows access to users who are active members of the target organisation,

    or to platform administrators.
    """

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not (user and user.is_authenticated):
            return False

        # Platform admins bypass organisation membership check
        if user.is_superuser or user.has_role('ADMIN') or user.has_role('MARKETPLACE_ADMIN'):
            return True

        # Check membership on organisation model
        if hasattr(obj, 'is_member'):
            return obj.is_member(user)
        # If object is membership itself
        if hasattr(obj, 'organisation'):
            return obj.organisation.is_member(user)

        return False


class IsOrganisationAdminOrOwner(permissions.BasePermission):
    """Allows management actions only to Organisation OWNER or ADMIN,

    or to platform administrators.
    """

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not (user and user.is_authenticated):
            return False

        # Platform admins bypass
        if user.is_superuser or user.has_role('ADMIN') or user.has_role('MARKETPLACE_ADMIN'):
            return True

        # Resolve organisation instance
        organisation = obj if hasattr(obj, 'get_member_role') else getattr(obj, 'organisation', None)
        if not organisation:
            return False

        role = organisation.get_member_role(user)
        return role in ('OWNER', 'ADMIN')


def HasPermission(permission_code: str):
    """DRF permission class factory requiring the user to hold the specified permission code.

    Platform administrators (ADMIN / Superuser) bypass all checks.
    """
    class _HasPermission(permissions.BasePermission):
        message = f"You do not have the required '{permission_code}' permission."

        def has_permission(self, request, view):
            user = request.user
            if not (user and user.is_authenticated):
                return False
            if user.is_superuser or user.has_role('ADMIN') or user.has_role('MARKETPLACE_ADMIN'):
                return True
            if hasattr(user, 'has_permission'):
                return user.has_permission(permission_code)
            return False

    return _HasPermission
