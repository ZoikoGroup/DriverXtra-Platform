from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, NotFound
from django.shortcuts import get_object_or_404
from .models import Organisation, OrganisationMembership, OrganisationRoleChoices
from .serializers import (
    OrganisationSerializer,
    OrganisationMemberSerializer,
    AddMemberSerializer,
)
from apps.identity.models import User
from common.permissions import IsOrganisationMember, IsOrganisationAdminOrOwner


class OrganisationListCreateView(generics.ListCreateAPIView):
    """List organisations the current user belongs to, or create a new organisation.

    GET /api/v1/organisations/
    POST /api/v1/organisations/
    """
    permission_classes = [IsAuthenticated]
    serializer_class = OrganisationSerializer

    def get_queryset(self):
        user = self.request.user
        # Platform admins and staff can view all active organisations
        if user.is_platform_admin or user.is_platform_staff:
            return Organisation.objects.filter(is_active=True)
        # Regular users only see organisations they belong to
        return Organisation.objects.filter(
            memberships__user=user,
            memberships__is_active=True,
            is_active=True,
        ).distinct()


class OrganisationDetailView(generics.RetrieveUpdateAPIView):
    """Retrieve organisation details or update organisation settings.

    GET /api/v1/organisations/{id}/
    PATCH /api/v1/organisations/{id}/
    """
    permission_classes = [IsAuthenticated, IsOrganisationMember]
    serializer_class = OrganisationSerializer
    queryset = Organisation.objects.filter(is_active=True)
    lookup_field = 'id'

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        # Updating requires OWNER or ADMIN role
        if request.method in ('PATCH', 'PUT'):
            role = obj.get_member_role(request.user)
            if not (request.user.is_platform_admin or role in ('OWNER', 'ADMIN')):
                raise PermissionDenied("Only organisation OWNER or ADMIN can modify organisation settings.")


class OrganisationMemberListCreateView(generics.GenericAPIView):
    """List members or add a new member to the organisation.

    GET /api/v1/organisations/{id}/members/
    POST /api/v1/organisations/{id}/members/
    """
    permission_classes = [IsAuthenticated]

    def get_organisation(self, org_id):
        try:
            return Organisation.objects.get(id=org_id, is_active=True)
        except (Organisation.DoesNotExist, ValueError):
            raise NotFound("Organisation not found.")

    def get(self, request, id):
        organisation = self.get_organisation(id)
        # Must be member or platform admin to view membership list
        if not (request.user.is_platform_admin or organisation.is_member(request.user)):
            raise PermissionDenied("You do not have permission to view members of this organisation.")

        memberships = organisation.memberships.filter(is_active=True).select_related('user')
        serializer = OrganisationMemberSerializer(memberships, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, id):
        organisation = self.get_organisation(id)
        user_role = organisation.get_member_role(request.user)

        # Enforce organisation-scoped permission: only OWNER or ADMIN can invite/add members
        if not (request.user.is_platform_admin or user_role in ('OWNER', 'ADMIN')):
            raise PermissionDenied("Only organisation OWNER or ADMIN can add or invite members.")

        serializer = AddMemberSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        target_email = serializer.validated_data['email']
        role_to_assign = serializer.validated_data['role']
        target_user = User.objects.get(email=target_email)

        membership = organisation.add_member(user=target_user, role=role_to_assign)
        response_serializer = OrganisationMemberSerializer(membership)

        return Response(
            {
                "status": "success",
                "message": f"User {target_email} added to organisation as {role_to_assign}.",
                "member": response_serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )
