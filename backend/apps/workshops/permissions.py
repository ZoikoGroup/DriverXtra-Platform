from rest_framework import permissions
from apps.organisations.models import OrganisationRoleChoices


def is_platform_admin_or_staff(user) -> bool:
    if not (user and user.is_authenticated):
        return False
    return (
        user.is_superuser
        or user.is_staff
        or user.has_role('ADMIN')
        or user.has_role('MARKETPLACE_ADMIN')
        or user.has_role('STAFF')
        or user.has_role('OPERATIONS')
    )


class IsWorkshopOwnerOrAdmin(permissions.BasePermission):
    """
    Grants access only to users who are active OWNER or ADMIN members of
    the organisation owning the target workshop profile, or platform admins.
    """
    message = "You must be an Owner or Admin of this workshop to perform this action."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not (user and user.is_authenticated):
            return False

        if is_platform_admin_or_staff(user):
            return True

        # Resolve organisation from object
        organisation = None
        if hasattr(obj, 'organisation'):
            organisation = obj.organisation
        elif hasattr(obj, 'workshop') and hasattr(obj.workshop, 'organisation'):
            organisation = obj.workshop.organisation
        elif hasattr(obj, 'booking') and hasattr(obj.booking, 'workshop'):
            organisation = obj.booking.workshop.organisation

        if not organisation:
            return False

        role = organisation.get_member_role(user)
        return role in (OrganisationRoleChoices.OWNER, OrganisationRoleChoices.ADMIN)


class IsWorkshopStaffOrMember(permissions.BasePermission):
    """
    Grants access to any active member (Owner, Admin, Member, Technician)
    of the organisation owning the workshop, or platform staff.
    """
    message = "You must be an authorised staff member of this workshop to view this resource."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not (user and user.is_authenticated):
            return False

        if is_platform_admin_or_staff(user):
            return True

        organisation = None
        if hasattr(obj, 'organisation'):
            organisation = obj.organisation
        elif hasattr(obj, 'workshop') and hasattr(obj.workshop, 'organisation'):
            organisation = obj.workshop.organisation
        elif hasattr(obj, 'booking') and hasattr(obj.booking, 'workshop'):
            organisation = obj.booking.workshop.organisation

        if not organisation:
            return False

        return organisation.is_member(user)


class IsBookingBuyerOrWorkshopStaff(permissions.BasePermission):
    """
    Allows access if the user is either the buyer who placed the booking
    OR an active staff member of the workshop performing the service.
    """
    message = "You do not have permission to access this booking."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not (user and user.is_authenticated):
            return False

        if is_platform_admin_or_staff(user):
            return True

        # Check if user is the booking buyer
        buyer = getattr(obj, 'buyer', None)
        if not buyer and hasattr(obj, 'booking'):
            buyer = getattr(obj.booking, 'buyer', None)
        if buyer and buyer.id == user.id:
            return True

        # Check if user is workshop staff
        organisation = None
        if hasattr(obj, 'workshop') and hasattr(obj.workshop, 'organisation'):
            organisation = obj.workshop.organisation
        elif hasattr(obj, 'booking') and hasattr(obj.booking, 'workshop'):
            organisation = obj.booking.workshop.organisation

        if organisation and organisation.is_member(user):
            return True

        return False

