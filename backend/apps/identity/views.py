from rest_framework import generics, status, views
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle
from django.utils import timezone
from django.core import signing
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
from .models import (
    User,
    RoleChoices,
    EmailVerificationToken,
    PasswordResetToken,
    StaffRole,
    StaffProfile,
    StaffInviteToken,
)
from .services import (
    create_and_send_email_verification,
    create_and_send_password_reset,
    hash_token,
)
from .security import (
    generate_new_totp_secret,
    get_totp_provisioning_uri,
    verify_totp_code,
)
from .throttling import AuthRateThrottle, PasswordResetRateThrottle
from common.permissions import IsMarketplaceAdmin
from platform_core.audit.writer import record_audit_entry, record_denied_audit_entry
from rest_framework import serializers as drf_serializers
from .serializers import (
    UserRegistrationSerializer,
    UserLoginSerializer,
    UserLogoutSerializer,
    UserProfileSerializer,
    VerifyEmailSerializer,
    ResendVerificationSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    SwitchRoleSerializer,
    StaffInviteSerializer,
    StaffSetPasswordSerializer,
    MFAVerifySerializer,
)


class RegisterView(generics.CreateAPIView):
    """Register a new user account and dispatch email verification.

    POST /api/v1/auth/register/
    """
    permission_classes = [AllowAny]
    serializer_class = UserRegistrationSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Generate and dispatch verification token email
        create_and_send_email_verification(user)

        # Audit registration success
        corr_id = getattr(request, 'correlation_id', '')
        record_audit_entry(
            event_type="auth.registration.success",
            action="auth:register",
            resource_type="User",
            resource_id=str(user.id),
            actor_id=user.id,
            correlation_id=corr_id,
            metadata={"email": user.email, "roles": user.roles},
        )

        profile_data = UserProfileSerializer(user).data
        return Response(
            {
                "status": "success",
                "message": "User registered successfully. Please check your email to verify your account.",
                "user": profile_data,
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(views.APIView):
    """Authenticate with email and password to receive JWT tokens.

    POST /api/v1/auth/login/
    """
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        corr_id = getattr(request, 'correlation_id', '')
        serializer = UserLoginSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except drf_serializers.ValidationError as exc:
            email = request.data.get('email', '')
            user = User.objects.filter(email=email.strip().lower()).first() if email else None
            record_denied_audit_entry(
                action="auth:login",
                resource_type="User",
                resource_id=str(user.id) if user else "",
                actor_id=user.id if user else None,
                reason_code="LOGIN_FAILED",
                correlation_id=corr_id,
                metadata={"email": email.strip().lower() if email else ""},
            )
            raise exc

        validated_data = serializer.validated_data
        user = validated_data['user']

        if validated_data.get('mfa_required'):
            return Response(
                {
                    "status": "mfa_required",
                    "code": "MFA_REQUIRED",
                    "message": "Two-factor authentication code required.",
                    "pre_auth_token": validated_data['pre_auth_token'],
                    "email": user.email,
                },
                status=status.HTTP_200_OK,
            )

        tokens = validated_data['tokens']
        profile_data = UserProfileSerializer(user, context={'request': request}).data

        record_audit_entry(
            event_type="auth.login.success",
            action="auth:login",
            resource_type="User",
            resource_id=str(user.id),
            actor_id=user.id,
            correlation_id=corr_id,
            metadata={"email": user.email, "active_role": validated_data.get('active_role')},
        )

        return Response(
            {
                "status": "success",
                "message": "Authentication successful.",
                "active_role": validated_data.get('active_role'),
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


class VerifyEmailView(views.APIView):
    """Verify account ownership via email verification token.

    POST /api/v1/auth/verify-email/
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        raw_token = serializer.validated_data["token"]
        token_digest = hash_token(raw_token)

        verification_record = EmailVerificationToken.objects.filter(token_hash=token_digest).first()
        if not verification_record:
            return Response(
                {
                    "status": "error",
                    "code": 400,
                    "message": "Invalid or expired email verification token.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if verification_record.consumed_at is not None:
            return Response(
                {
                    "status": "error",
                    "code": 400,
                    "message": "This email verification token has already been used.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if verification_record.expires_at < timezone.now():
            return Response(
                {
                    "status": "error",
                    "code": 400,
                    "message": "This email verification token has expired. Please request a new one.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Mark token consumed
        now = timezone.now()
        verification_record.consumed_at = now
        verification_record.save(update_fields=["consumed_at", "updated_at"])

        # Mark user verified
        user = verification_record.user
        user.is_email_verified = True
        user.email_verified_at = now
        user.save(update_fields=["is_email_verified", "email_verified_at", "updated_at"])

        return Response(
            {
                "status": "success",
                "message": "Email address verified successfully. You may now log in.",
            },
            status=status.HTTP_200_OK,
        )


class ResendVerificationView(views.APIView):
    """Request a new email verification token.

    POST /api/v1/auth/resend-verification/
    """
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "resend_verification"

    def post(self, request):
        serializer = ResendVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"].strip().lower()
        user = User.objects.filter(email=email).first()

        # Always return generic enumeration-safe response
        if user and not user.is_email_verified and user.is_active:
            create_and_send_email_verification(user)

        return Response(
            {
                "status": "success",
                "message": "If an unverified account exists with this email address, a verification link has been sent.",
            },
            status=status.HTTP_200_OK,
        )


class PasswordResetRequestView(views.APIView):
    """Request password reset instructions.

    POST /api/v1/auth/password-reset/request/
    """
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"].strip().lower()
        user = User.objects.filter(email=email).first()

        # Always return generic enumeration-safe response
        if user and user.is_active:
            create_and_send_password_reset(user)

        return Response(
            {
                "status": "success",
                "message": "If an account exists with this email address, password reset instructions have been sent.",
            },
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(views.APIView):
    """Confirm password reset via single-use token and set new password.

    POST /api/v1/auth/password-reset/confirm/
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        raw_token = serializer.validated_data["token"]
        new_password = serializer.validated_data["new_password"]
        token_digest = hash_token(raw_token)

        reset_record = PasswordResetToken.objects.filter(token_hash=token_digest).first()
        if not reset_record:
            return Response(
                {
                    "status": "error",
                    "code": 400,
                    "message": "Invalid or expired password reset token.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if reset_record.consumed_at is not None:
            return Response(
                {
                    "status": "error",
                    "code": 400,
                    "message": "This password reset token has already been used.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if reset_record.expires_at < timezone.now():
            return Response(
                {
                    "status": "error",
                    "code": 400,
                    "message": "This password reset token has expired. Please request a new one.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Update password
        user = reset_record.user
        user.set_password(new_password)
        user.save(update_fields=["password", "updated_at"])

        # Consume token
        reset_record.consumed_at = timezone.now()
        reset_record.save(update_fields=["consumed_at", "updated_at"])

        # Blacklist all outstanding refresh tokens for this user
        for ot in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=ot)

        # Audit password reset success
        corr_id = getattr(request, 'correlation_id', '')
        record_audit_entry(
            event_type="auth.password_reset.success",
            action="auth:password_reset.confirm",
            resource_type="User",
            resource_id=str(user.id),
            actor_id=user.id,
            correlation_id=corr_id,
            metadata={"email": user.email},
        )

        return Response(
            {
                "status": "success",
                "message": "Password has been successfully reset. Please log in with your new password.",
            },
            status=status.HTTP_200_OK,
        )


class SwitchRoleView(views.APIView):
    """Switch user active role in the JWT token.

    POST /api/v1/auth/switch-role/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = SwitchRoleSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        new_role = serializer.validated_data['role']
        user = request.user

        refresh = RefreshToken.for_user(user)
        refresh['email'] = user.email
        refresh['roles'] = user.roles
        refresh['full_name'] = user.full_name
        refresh['active_role'] = new_role

        access = refresh.access_token
        access['email'] = user.email
        access['roles'] = user.roles
        access['full_name'] = user.full_name
        access['active_role'] = new_role

        is_staff_or_admin = (
            user.is_staff
            or user.has_role(RoleChoices.STAFF)
            or user.has_role(RoleChoices.ADMIN)
            or user.is_superuser
        )
        if is_staff_or_admin or new_role in (RoleChoices.STAFF, RoleChoices.ADMIN):
            from datetime import timedelta
            access.set_exp(lifetime=timedelta(minutes=15))

        corr_id = getattr(request, 'correlation_id', '')
        record_audit_entry(
            event_type="auth.role.switched",
            action="auth:switch_role",
            resource_type="User",
            resource_id=str(user.id),
            actor_id=user.id,
            correlation_id=corr_id,
            metadata={"email": user.email, "new_active_role": new_role},
        )

        return Response(
            {
                "status": "success",
                "message": f"Active role switched to {new_role}.",
                "active_role": new_role,
                "tokens": {
                    "access": str(access),
                    "refresh": str(refresh),
                },
            },
            status=status.HTTP_200_OK,
        )


class StaffInviteView(views.APIView):
    """Create a pending staff user with a single-use set-password token.

    POST /api/v1/admin/staff/invite/
    """
    permission_classes = [IsMarketplaceAdmin]

    def post(self, request):
        serializer = StaffInviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        email = data['email']
        first_name = data.get('first_name', '')
        last_name = data.get('last_name', '')
        staff_role_code = data['staff_role']
        department = data.get('department', 'Operations')

        staff_role = StaffRole.objects.get(code=staff_role_code)

        user = User.objects.create_user(
            email=email,
            first_name=first_name,
            last_name=last_name,
            is_staff=True,
            is_email_verified=True,
            status='PENDING',
        )
        user.set_unusable_password()
        user.save()
        user.add_role(RoleChoices.STAFF)

        StaffProfile.objects.create(
            user=user,
            staff_role=staff_role,
            department=department,
            totp_enabled=False,
        )

        import secrets
        import hashlib
        from datetime import timedelta
        from django.core.mail import send_mail
        from django.conf import settings

        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()

        StaffInviteToken.objects.create(
            user=user,
            token_hash=token_hash,
            expires_at=timezone.now() + timedelta(days=2),
        )

        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000').rstrip('/')
        invite_link = f"{frontend_url}/set-password?token={raw_token}"

        send_mail(
            subject="DriverXtra Staff Invitation",
            message=(
                f"Hello {user.full_name or user.email},\n\n"
                f"You have been invited to join DriverXtra Operations as a {staff_role.name} ({department}).\n\n"
                f"Please set your password using this link:\n{invite_link}\n\n"
                f"This link expires in 48 hours.\n\nDriverXtra Operations Team"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )

        corr_id = getattr(request, 'correlation_id', '')
        record_audit_entry(
            event_type="staff.invited",
            action="staff:invite",
            resource_type="User",
            resource_id=str(user.id),
            actor_id=request.user.id,
            correlation_id=corr_id,
            metadata={
                "invited_email": user.email,
                "staff_role": staff_role.code,
                "department": department,
            },
        )

        return Response(
            {
                "status": "success",
                "message": "Staff invitation dispatched successfully.",
                "email": user.email,
                "staff_role": staff_role.code,
            },
            status=status.HTTP_201_CREATED,
        )


class StaffSetPasswordView(views.APIView):
    """Set account password for an invited staff user using their single-use token.

    POST /api/v1/auth/staff/set-password/
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = StaffSetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        invite_token = serializer.validated_data['invite_token']
        new_password = serializer.validated_data['new_password']
        user = invite_token.user

        user.set_password(new_password)
        user.status = 'ACTIVE'
        user.is_active = True
        user.is_email_verified = True
        user.email_verified_at = timezone.now()
        user.save()

        invite_token.consumed_at = timezone.now()
        invite_token.save()

        corr_id = getattr(request, 'correlation_id', '')
        record_audit_entry(
            event_type="staff.invite.accepted",
            action="staff:set_password",
            resource_type="User",
            resource_id=str(user.id),
            actor_id=user.id,
            correlation_id=corr_id,
            metadata={"email": user.email},
        )

        return Response(
            {
                "status": "success",
                "message": "Password initialized successfully. You may now log in to DriverXtra.",
            },
            status=status.HTTP_200_OK,
        )


class MFAEnrolView(views.APIView):
    """Generate TOTP MFA secret and QR code URI for authenticator setup.

    POST /api/v1/auth/mfa/enrol/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        profile, _ = StaffProfile.objects.get_or_create(user=user)

        plain_secret = generate_new_totp_secret()
        profile.set_totp_secret(plain_secret)
        profile.totp_enabled = False
        profile.save()

        uri = get_totp_provisioning_uri(plain_secret, user.email)

        return Response(
            {
                "status": "success",
                "secret": plain_secret,
                "qr_code_uri": uri,
                "message": "TOTP secret generated. Please verify with a code from your authenticator app to enable MFA.",
            },
            status=status.HTTP_200_OK,
        )


class MFAVerifyView(views.APIView):
    """Verify TOTP code for either enrolment activation or login challenge completion.

    POST /api/v1/auth/mfa/verify/
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = MFAVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        code = serializer.validated_data['code']
        pre_auth_token = serializer.validated_data.get('pre_auth_token', '').strip()

        if pre_auth_token:
            # Login completion mode
            try:
                data = signing.loads(pre_auth_token, salt='driverxtra.mfa', max_age=300)
                user_id = data.get('user_id')
                user = User.objects.get(id=user_id)
            except Exception:
                return Response(
                    {"status": "error", "code": 400, "message": "Invalid or expired MFA session. Please log in again."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            profile = getattr(user, 'staff_profile', None)
            if not profile or not profile.verify_totp(code):
                return Response(
                    {"status": "error", "code": 400, "message": "Invalid two-factor authentication code."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            active_role = user.get_default_role()
            refresh = RefreshToken.for_user(user)
            refresh['email'] = user.email
            refresh['roles'] = user.roles
            refresh['full_name'] = user.full_name
            refresh['active_role'] = active_role

            access = refresh.access_token
            access['email'] = user.email
            access['roles'] = user.roles
            access['full_name'] = user.full_name
            access['active_role'] = active_role

            is_staff_or_admin = (
                user.is_staff
                or user.has_role(RoleChoices.STAFF)
                or user.has_role(RoleChoices.ADMIN)
                or user.is_superuser
            )
            if is_staff_or_admin or active_role in (RoleChoices.STAFF, RoleChoices.ADMIN):
                from datetime import timedelta
                access.set_exp(lifetime=timedelta(minutes=15))

            corr_id = getattr(request, 'correlation_id', '')
            record_audit_entry(
                event_type="auth.login.success",
                action="auth:login",
                resource_type="User",
                resource_id=str(user.id),
                actor_id=user.id,
                correlation_id=corr_id,
                metadata={"email": user.email, "active_role": active_role, "mfa_verified": True},
            )

            return Response(
                {
                    "status": "success",
                    "message": "Authentication successful.",
                    "active_role": active_role,
                    "tokens": {
                        "access": str(access),
                        "refresh": str(refresh),
                    },
                    "user": UserProfileSerializer(user, context={'request': request}).data,
                },
                status=status.HTTP_200_OK,
            )
        else:
            # Enrolment verification mode for authenticated user
            if not request.user or not request.user.is_authenticated:
                return Response(
                    {"status": "error", "code": 401, "message": "Authentication required to activate MFA."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            user = request.user
            profile = getattr(user, 'staff_profile', None)
            if not profile or not profile.verify_totp(code):
                return Response(
                    {"status": "error", "code": 400, "message": "Invalid two-factor authentication code."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            profile.totp_enabled = True
            profile.save(update_fields=['totp_enabled', 'updated_at'])

            corr_id = getattr(request, 'correlation_id', '')
            record_audit_entry(
                event_type="staff.mfa.enrolled",
                action="auth:mfa.enrol",
                resource_type="User",
                resource_id=str(user.id),
                actor_id=user.id,
                correlation_id=corr_id,
                metadata={"email": user.email},
            )

            return Response(
                {
                    "status": "success",
                    "message": "Two-factor authentication verified and enabled.",
                },
                status=status.HTTP_200_OK,
            )
