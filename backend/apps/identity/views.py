from rest_framework import generics, status, views
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from .models import User
from .serializers import (
    UserRegistrationSerializer,
    UserLoginSerializer,
    UserLogoutSerializer,
    UserProfileSerializer,
)


class RegisterView(generics.CreateAPIView):
    """Register a new user account.

    POST /api/v1/auth/register/
    """
    permission_classes = [AllowAny]
    serializer_class = UserRegistrationSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        profile_data = UserProfileSerializer(user).data
        return Response(
            {
                "status": "success",
                "message": "User registered successfully.",
                "user": profile_data,
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(views.APIView):
    """Authenticate with email and password to receive JWT tokens.

    POST /api/v1/auth/login/
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = UserLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        user = validated_data['user']
        tokens = validated_data['tokens']
        profile_data = UserProfileSerializer(user).data

        return Response(
            {
                "status": "success",
                "message": "Authentication successful.",
                "tokens": tokens,
                "user": profile_data,
            },
            status=status.HTTP_200_OK,
        )


class LogoutView(views.APIView):
    """Revoke JWT refresh token upon user logout.

    POST /api/v1/auth/logout/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = UserLogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {
                "status": "success",
                "message": "Successfully logged out. Refresh token invalidated.",
            },
            status=status.HTTP_200_OK,
        )


class UserProfileView(generics.RetrieveUpdateAPIView):
    """Retrieve or update profile details for the currently authenticated user.

    GET /api/v1/users/me/
    PATCH /api/v1/users/me/
    """
    permission_classes = [IsAuthenticated]
    serializer_class = UserProfileSerializer
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_object(self):
        return self.request.user
