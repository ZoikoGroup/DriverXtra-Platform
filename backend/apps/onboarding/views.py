from rest_framework import views, status, generics, permissions
from rest_framework.response import Response
from django.core.exceptions import ValidationError as DjangoValidationError
from common.permissions import IsPlatformStaff
from apps.onboarding.models import SellerApplication, SellerApplicationStatusChoices
from apps.onboarding.serializers import (
    SellerApplicationSerializer,
    SellerApplicationCreateUpdateSerializer,
    SellerApplicationReviewSerializer,
)


class SellerApplicationMeView(views.APIView):
    """Retrieve, create, or update the current user's seller onboarding application.

    GET /api/v1/seller/application/
    POST /api/v1/seller/application/
    PATCH /api/v1/seller/application/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        # Return the latest application for this user
        return SellerApplication.objects.filter(user=self.request.user).first()

    def get(self, request):
        application = self.get_object()
        if not application:
            return Response(
                {
                    "status": "none",
                    "message": "No seller application found for this account.",
                    "application": None,
                },
                status=status.HTTP_200_OK,
            )
        serializer = SellerApplicationSerializer(application)
        return Response(
            {
                "status": "success",
                "application": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = SellerApplicationCreateUpdateSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        application = serializer.save()
        return Response(
            {
                "status": "success",
                "message": (
                    "Seller application submitted for review."
                    if application.status == SellerApplicationStatusChoices.PENDING
                    else "Seller application draft saved."
                ),
                "application": SellerApplicationSerializer(application).data,
            },
            status=status.HTTP_201_CREATED,
        )

    def patch(self, request):
        application = self.get_object()
        if not application:
            return Response(
                {
                    "status": "error",
                    "message": "No existing seller application found to update.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if application.status == SellerApplicationStatusChoices.APPROVED:
            return Response(
                {
                    "status": "error",
                    "message": "Approved seller applications cannot be modified.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = SellerApplicationCreateUpdateSerializer(
            instance=application,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        updated_app = serializer.save()
        return Response(
            {
                "status": "success",
                "message": "Seller application updated.",
                "application": SellerApplicationSerializer(updated_app).data,
            },
            status=status.HTTP_200_OK,
        )


class SellerApplicationSubmitView(views.APIView):
    """Submit an existing draft or rejected seller application for review.

    POST /api/v1/seller/application/submit/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        application = SellerApplication.objects.filter(user=request.user).first()
        if not application:
            return Response(
                {"status": "error", "message": "No seller application found to submit."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            application.submit_for_review()
        except DjangoValidationError as exc:
            return Response(
                {"status": "error", "message": exc.messages[0] if hasattr(exc, "messages") else str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "status": "success",
                "message": "Application submitted for review.",
                "application": SellerApplicationSerializer(application).data,
            },
            status=status.HTTP_200_OK,
        )


class AdminSellerApplicationListView(generics.ListAPIView):
    """List all seller onboarding applications for platform staff and admins.

    GET /api/v1/admin/seller-applications/?status=PENDING
    """
    permission_classes = [IsPlatformStaff]
    serializer_class = SellerApplicationSerializer

    def get_queryset(self):
        queryset = SellerApplication.objects.select_related("user", "organisation", "reviewed_by").all()
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter.upper())
        return queryset


class AdminSellerApplicationDetailView(generics.RetrieveAPIView):
    """Retrieve full detail of a specific seller application.

    GET /api/v1/admin/seller-applications/<id>/
    """
    permission_classes = [IsPlatformStaff]
    serializer_class = SellerApplicationSerializer
    queryset = SellerApplication.objects.select_related("user", "organisation", "reviewed_by").all()
    lookup_field = "id"


class AdminSellerApplicationReviewView(views.APIView):
    """Approve or reject a seller onboarding application.

    POST /api/v1/admin/seller-applications/<id>/review/
    """
    permission_classes = [IsPlatformStaff]

    def post(self, request, id):
        application = generics.get_object_or_404(SellerApplication, id=id)

        serializer = SellerApplicationReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action = serializer.validated_data["action"]
        reason = serializer.validated_data.get("reason", "")
        admin_notes = serializer.validated_data.get("admin_notes", "")

        try:
            if action == "APPROVE":
                application.approve(reviewer=request.user, notes=admin_notes)
                message = f"Seller application for '{application.business_name}' approved. Seller privileges granted."
            else:
                application.reject(reviewer=request.user, reason=reason, notes=admin_notes)
                message = f"Seller application for '{application.business_name}' rejected."
        except DjangoValidationError as exc:
            return Response(
                {"status": "error", "message": exc.messages[0] if hasattr(exc, "messages") else str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "status": "success",
                "message": message,
                "application": SellerApplicationSerializer(application).data,
            },
            status=status.HTTP_200_OK,
        )
