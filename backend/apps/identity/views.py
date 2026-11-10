import logging
from rest_framework import generics, status, views
from rest_framework.views import APIView
from django.db import models
from django.core.exceptions import ValidationError as DjangoValidationError

logger = logging.getLogger(__name__)
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle
from django.utils import timezone
from django.core import signing
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
from .models import (
    User,
    UserRole,
    RoleChoices,
    AccountStatusChoices,
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
from common.permissions import IsMarketplaceAdmin, IsPlatformStaff, HasPermission
from platform_core.audit.writer import record_audit_entry, record_denied_audit_entry
from rest_framework import serializers as drf_serializers
from rest_framework_simplejwt.views import TokenRefreshView
from django.db import transaction
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
    StaffAwareTokenRefreshSerializer,
    MFAVerifySerializer,
    StaffRoleSerializer,
    StaffMemberSerializer,
    StaffMemberUpdateSerializer,
    StaffInvitationSerializer,
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
            enrollment_required = validated_data.get('mfa_enrollment_required', False)
            return Response(
                {
                    "status": "mfa_enrollment_required" if enrollment_required else "mfa_required",
                    "code": "MFA_ENROLLMENT_REQUIRED" if enrollment_required else "MFA_REQUIRED",
                    "message": (
                        "Two-factor authentication enrollment required before accessing the platform."
                        if enrollment_required
                        else "Two-factor authentication code required."
                    ),
                    "mfa_required": True,
                    "pre_auth_token": validated_data['pre_auth_token'],
                    "email": user.email,
                    "active_role": validated_data.get('active_role', user.get_default_role()),
                    "mfa_enrollment_required": enrollment_required,
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


class StaffTokenRefreshView(TokenRefreshView):
    """Token refresh view applying staff-aware access token lifetime clamping (15 minutes)."""
    serializer_class = StaffAwareTokenRefreshSerializer


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
    Failure-safe: wrapped in transaction.atomic so email delivery failures
    automatically roll back user creation, preventing stranded PENDING accounts.
    Supports retrying invitations for accounts in PENDING status.
    """
    permission_classes = [IsMarketplaceAdmin]

    @transaction.atomic
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

        # Re-invitation / idempotent pending user handling
        user = User.objects.filter(email=email).first()
        if user:
            user.first_name = first_name
            user.last_name = last_name
            user.is_staff = True
            user.is_email_verified = True
            user.status = 'PENDING'
            user.set_unusable_password()
            user.save()
            user.add_role(RoleChoices.STAFF)

            # Invalidate any previous unconsumed invite tokens
            StaffInviteToken.objects.filter(user=user, consumed_at__isnull=True).delete()

            profile, _ = StaffProfile.objects.get_or_create(user=user)
            profile.staff_role = staff_role
            profile.department = department
            profile.totp_enabled = False
            profile.save()
        else:
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

        try:
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
        except Exception as mail_exc:
            logger.error("Failed to deliver staff invitation email to %s: %s", user.email, str(mail_exc))
            corr_id = getattr(request, 'correlation_id', '')
            record_denied_audit_entry(
                action="staff:invite",
                resource_type="User",
                resource_id=str(user.id),
                actor_id=request.user.id,
                reason_code="EMAIL_DELIVERY_FAILED",
                correlation_id=corr_id,
                metadata={"email": user.email, "error": str(mail_exc)},
            )
            raise drf_serializers.ValidationError({
                "email": "Failed to deliver invitation email. The operation has been safely rolled back. Please verify the email address or try again later."
            })

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

        resp_data = {
            "status": "success",
            "message": "Staff invitation dispatched successfully.",
            "email": user.email,
            "staff_role": staff_role.code,
        }
        if getattr(settings, 'DEBUG', False):
            resp_data["invite_token"] = raw_token

        return Response(resp_data, status=status.HTTP_201_CREATED)


class StaffSetPasswordView(views.APIView):
    """Set account password for an invited staff user using their single-use token.

    POST /api/v1/auth/staff/set-password/
    """
    permission_classes = [AllowAny]

    @transaction.atomic
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
    Accepts authenticated users or unauthenticated users with a valid mfa_enrollment pre_auth_token.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        user = None
        pre_auth_token = request.data.get('pre_auth_token') or request.headers.get('X-MFA-Token', '').strip()

        if request.user and request.user.is_authenticated:
            user = request.user
        elif pre_auth_token:
            try:
                data = signing.loads(pre_auth_token, salt='driverxtra.mfa', max_age=300)
                if data.get('action') != 'mfa_enrollment':
                    return Response(
                        {"status": "error", "code": 400, "message": "Invalid token purpose for MFA enrollment."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                user_id = data.get('user_id')
                user = User.objects.filter(id=user_id, is_active=True).first()
                if not user:
                    return Response(
                        {"status": "error", "code": 404, "message": "User not found."},
                        status=status.HTTP_404_NOT_FOUND,
                    )
                if user.has_mfa_enabled:
                    return Response(
                        {"status": "error", "code": 400, "message": "MFA is already enrolled for this account."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            except Exception:
                return Response(
                    {"status": "error", "code": 400, "message": "Invalid or expired MFA session. Please log in again."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            return Response(
                {"status": "error", "code": 401, "message": "Authentication or valid MFA enrollment token required."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        profile, _ = StaffProfile.objects.get_or_create(user=user)

        plain_secret = generate_new_totp_secret()
        profile.set_totp_secret(plain_secret)
        profile.totp_enabled = False
        profile.save()

        uri = get_totp_provisioning_uri(plain_secret, user.email)

        resp_data = {
            "status": "success",
            "secret": plain_secret,
            "qr_code_uri": uri,
            "message": "TOTP secret generated. Please verify with a code from your authenticator app to enable MFA.",
        }
        if pre_auth_token:
            resp_data["pre_auth_token"] = pre_auth_token

        return Response(resp_data, status=status.HTTP_200_OK)


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
            import hashlib
            from django.core.cache import cache

            cache_key = f"mfa_used_{hashlib.sha256(pre_auth_token.encode()).hexdigest()}"
            if cache.get(cache_key):
                return Response(
                    {"status": "error", "code": 400, "message": "MFA session token has already been used. Please log in again."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Login completion mode or enrollment verification mode via pre_auth_token
            try:
                data = signing.loads(pre_auth_token, salt='driverxtra.mfa', max_age=300)
                user_id = data.get('user_id')
                action = data.get('action', 'mfa_login')
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

            cache.set(cache_key, True, timeout=360)

            # If this was an enrollment verification, activate MFA on the profile
            if action == 'mfa_enrollment':
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


# =========================================================
# MAKER-CHECKER APPROVAL ENGINE VIEWS
# =========================================================

class ApprovalRequestListView(APIView):
    """GET /api/v1/admin/approvals/

    List and filter Maker-Checker approval requests.
    Requires Platform Staff membership.
    """
    permission_classes = [IsPlatformStaff]

    def get(self, request):
        from apps.identity.models import ApprovalRequest
        from apps.identity.serializers import ApprovalRequestSerializer

        queryset = ApprovalRequest.objects.select_related(
            'requester',
            'approver',
            'executed_by',
            'requester__staff_profile__staff_role',
            'approver__staff_profile__staff_role',
        ).all().order_by('-requested_at')

        status_param = request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param.strip().upper())

        action_param = request.query_params.get('action_type')
        if action_param:
            queryset = queryset.filter(action_type=action_param.strip().upper())

        target_param = request.query_params.get('target_type')
        if target_param:
            queryset = queryset.filter(target_type=target_param.strip())

        search_param = request.query_params.get('search')
        if search_param:
            term = search_param.strip()
            queryset = queryset.filter(
                models.Q(target_id__icontains=term)
                | models.Q(reason__icontains=term)
                | models.Q(notes__icontains=term)
                | models.Q(requester__email__icontains=term)
            )

        serializer = ApprovalRequestSerializer(queryset, many=True, context={'request': request})
        return Response({
            "status": "success",
            "count": queryset.count(),
            "results": serializer.data,
        }, status=status.HTTP_200_OK)


class ApprovalRequestDetailView(APIView):
    """GET /api/v1/admin/approvals/<id>/

    Retrieve details for a single approval request.
    """
    permission_classes = [IsPlatformStaff]

    def get(self, request, pk):
        from apps.identity.models import ApprovalRequest
        from apps.identity.serializers import ApprovalRequestSerializer

        try:
            req = ApprovalRequest.objects.select_related(
                'requester',
                'approver',
                'executed_by',
                'requester__staff_profile__staff_role',
                'approver__staff_profile__staff_role',
            ).get(id=pk)
        except (ApprovalRequest.DoesNotExist, DjangoValidationError, ValueError):
            return Response({"error": "Approval request not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ApprovalRequestSerializer(req, context={'request': request})
        return Response({
            "status": "success",
            "approval_request": serializer.data,
        }, status=status.HTTP_200_OK)


class ApprovalRequestApproveView(APIView):
    """POST /api/v1/admin/approvals/<id>/approve/

    Authorizes an approval request.
    Maker cannot approve own request. Requires 'finance.payout' or admin.
    """
    permission_classes = [IsPlatformStaff]

    def post(self, request, pk):
        from apps.identity.approval_service import ApprovalService
        from apps.identity.serializers import ApprovalActionSerializer, ApprovalRequestSerializer

        serializer = ApprovalActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        notes = serializer.validated_data.get('notes', '')

        try:
            approved_req = ApprovalService.approve_request(
                approval_request_id=pk,
                approver=request.user,
                notes=notes,
            )
            return Response({
                "status": "success",
                "message": "Approval request approved successfully.",
                "approval_request": ApprovalRequestSerializer(approved_req, context={'request': request}).data,
            }, status=status.HTTP_200_OK)
        except DjangoValidationError as exc:
            msg = exc.message if hasattr(exc, 'message') else str(exc)
            if "permission denied" in msg.lower():
                return Response({"detail": msg}, status=status.HTTP_403_FORBIDDEN)
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)




class StaffRoleListView(views.APIView):
    """GET /api/v1/admin/staff/roles/
    List active platform staff roles and their granted capabilities.
    """
    permission_classes = [IsMarketplaceAdmin]

    def get(self, request):
        roles = StaffRole.objects.all().prefetch_related('role_permissions__permission').order_by('name')
        return Response({
            "status": "success",
            "roles": StaffRoleSerializer(roles, many=True).data,
        }, status=status.HTTP_200_OK)


class StaffMetricsView(views.APIView):
    """GET /api/v1/admin/staff/metrics/
    Aggregated operational metrics for staff dashboard.
    """
    permission_classes = [IsMarketplaceAdmin]

    def get(self, request):
        staff_qs = User.objects.filter(
            models.Q(is_staff=True) |
            models.Q(staff_profile__isnull=False) |
            models.Q(user_roles__role__in=['STAFF', RoleChoices.ADMIN])
        ).distinct()

        total_staff = staff_qs.count()
        active_staff = staff_qs.filter(status=AccountStatusChoices.ACTIVE, is_active=True).count()
        suspended_staff = staff_qs.filter(models.Q(status=AccountStatusChoices.SUSPENDED) | models.Q(is_active=False)).count()
        pending_invitations = StaffInviteToken.objects.filter(
            consumed_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).count()

        mfa_enrolled_count = staff_qs.filter(staff_profile__totp_enabled=True).count()
        mfa_rate = round((mfa_enrolled_count / total_staff * 100), 1) if total_staff > 0 else 0.0

        role_dist = {}
        for role in StaffRole.objects.all():
            role_dist[role.code] = staff_qs.filter(staff_profile__staff_role=role).count()
        role_dist['ADMIN'] = staff_qs.filter(models.Q(is_superuser=True) | models.Q(user_roles__role=RoleChoices.ADMIN)).distinct().count()

        return Response({
            "status": "success",
            "metrics": {
                "total_staff": total_staff,
                "active_staff": active_staff,
                "suspended_staff": suspended_staff,
                "pending_invitations": pending_invitations,
                "mfa_enrolled_count": mfa_enrolled_count,
                "mfa_adoption_percentage": mfa_rate,
                "role_distribution": role_dist,
            }
        }, status=status.HTTP_200_OK)


class StaffMemberListView(views.APIView):
    """GET /api/v1/admin/staff/
    Search and filter staff directory.
    """
    permission_classes = [IsMarketplaceAdmin]

    def get(self, request):
        staff_qs = User.objects.filter(
            models.Q(is_staff=True) |
            models.Q(staff_profile__isnull=False) |
            models.Q(user_roles__role__in=['STAFF', RoleChoices.ADMIN])
        ).distinct().select_related('staff_profile__staff_role').order_by('-date_joined')

        search = request.query_params.get('search', '').strip()
        if search:
            staff_qs = staff_qs.filter(
                models.Q(email__icontains=search) |
                models.Q(first_name__icontains=search) |
                models.Q(last_name__icontains=search)
            )

        role = request.query_params.get('role', '').strip().upper()
        if role:
            if role == 'ADMIN':
                staff_qs = staff_qs.filter(
                    models.Q(is_superuser=True) |
                    models.Q(user_roles__role=RoleChoices.ADMIN) |
                    models.Q(staff_profile__staff_role__code='ADMIN')
                )
            else:
                staff_qs = staff_qs.filter(staff_profile__staff_role__code=role)

        status_param = request.query_params.get('status', '').strip().upper()
        if status_param:
            if status_param == AccountStatusChoices.ACTIVE:
                staff_qs = staff_qs.filter(status=AccountStatusChoices.ACTIVE, is_active=True)
            elif status_param == AccountStatusChoices.SUSPENDED:
                staff_qs = staff_qs.filter(models.Q(status=AccountStatusChoices.SUSPENDED) | models.Q(is_active=False))
            else:
                staff_qs = staff_qs.filter(status=status_param)

        mfa_param = request.query_params.get('mfa', '').strip().lower()
        if mfa_param in ('true', '1'):
            staff_qs = staff_qs.filter(staff_profile__totp_enabled=True)
        elif mfa_param in ('false', '0'):
            staff_qs = staff_qs.filter(models.Q(staff_profile__totp_enabled=False) | models.Q(staff_profile__isnull=True))

        data = StaffMemberSerializer(staff_qs, many=True).data
        return Response({
            "status": "success",
            "count": len(data),
            "results": data,
        }, status=status.HTTP_200_OK)


class StaffMemberDetailView(views.APIView):
    """GET /api/v1/admin/staff/<pk>/
    PATCH /api/v1/admin/staff/<pk>/
    View and modify staff member role, department, or status.
    """
    permission_classes = [IsMarketplaceAdmin]

    def _get_target_user(self, pk):
        import uuid
        try:
            uuid.UUID(str(pk))
        except (ValueError, TypeError, AttributeError):
            return None

        try:
            return User.objects.filter(id=pk).select_related('staff_profile__staff_role').first()
        except (DjangoValidationError, ValueError):
            return None

    def get(self, request, pk):
        user = self._get_target_user(pk)
        if not user:
            return Response({"error": "Staff member not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response({
            "status": "success",
            "staff_member": StaffMemberSerializer(user).data,
        }, status=status.HTTP_200_OK)

    def patch(self, request, pk):
        user = self._get_target_user(pk)
        if not user:
            return Response({"error": "Staff member not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = StaffMemberUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        target_status = validated.get('status')
        target_role = validated.get('staff_role')
        target_department = validated.get('department')

        # Prevent admin from suspending themselves
        if target_status == AccountStatusChoices.SUSPENDED and str(request.user.id) == str(user.id):
            return Response({"error": "Cannot suspend your own administrator account."}, status=status.HTTP_400_BAD_REQUEST)

        # Update status
        if target_status:
            user.status = target_status
            if target_status == AccountStatusChoices.SUSPENDED:
                user.is_active = False
            elif target_status == AccountStatusChoices.ACTIVE:
                user.is_active = True
            user.save(update_fields=['status', 'is_active', 'updated_at'])

        # Update staff profile
        profile, _ = StaffProfile.objects.get_or_create(user=user)
        updated_profile_fields = []
        if target_role:
            role_obj = StaffRole.objects.get(code=target_role)
            profile.staff_role = role_obj
            updated_profile_fields.append('staff_role')
        if target_department is not None and target_department.strip():
            profile.department = target_department.strip()
            updated_profile_fields.append('department')

        if updated_profile_fields:
            updated_profile_fields.append('updated_at')
            profile.save(update_fields=updated_profile_fields)

        corr_id = getattr(request, 'correlation_id', '')
        record_audit_entry(
            event_type="staff.member.updated",
            action="staff:update",
            resource_type="User",
            resource_id=str(user.id),
            actor_id=request.user.id,
            correlation_id=corr_id,
            metadata={
                "target_email": user.email,
                "new_status": target_status,
                "new_role": target_role,
                "new_department": target_department,
            },
        )

        user.refresh_from_db()
        return Response({
            "status": "success",
            "message": "Staff member updated successfully.",
            "staff_member": StaffMemberSerializer(user).data,
        }, status=status.HTTP_200_OK)


class StaffInvitationListView(views.APIView):
    """GET /api/v1/admin/staff/invitations/
    List and filter pending, accepted, and expired staff invitations.
    """
    permission_classes = [IsMarketplaceAdmin]

    def get(self, request):
        now = timezone.now()
        qs = StaffInviteToken.objects.all().select_related('user__staff_profile__staff_role').order_by('-created_at')

        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                models.Q(user__email__icontains=search) |
                models.Q(user__first_name__icontains=search) |
                models.Q(user__last_name__icontains=search)
            )

        status_param = request.query_params.get('status', '').strip().upper()
        if status_param == 'PENDING':
            qs = qs.filter(consumed_at__isnull=True, expires_at__gt=now)
        elif status_param == 'EXPIRED':
            qs = qs.filter(consumed_at__isnull=True, expires_at__lte=now)
        elif status_param == 'ACCEPTED':
            qs = qs.filter(consumed_at__isnull=False)

        data = StaffInvitationSerializer(qs, many=True).data
        return Response({
            "status": "success",
            "count": len(data),
            "results": data,
        }, status=status.HTTP_200_OK)


class StaffInvitationResendView(views.APIView):
    """POST /api/v1/admin/staff/invitations/<pk>/resend/
    Generates a new secure token, extends validity to 48 hours, and dispatches an invitation email.
    """
    permission_classes = [IsMarketplaceAdmin]

    @transaction.atomic
    def post(self, request, pk):
        import uuid
        try:
            uuid.UUID(str(pk))
        except (ValueError, TypeError, AttributeError):
            return Response({"error": "Invitation not found."}, status=status.HTTP_404_NOT_FOUND)

        import secrets
        import hashlib
        from datetime import timedelta
        from django.core.mail import send_mail
        from django.conf import settings

        invite = StaffInviteToken.objects.filter(models.Q(id=pk) | models.Q(user__id=pk)).select_related('user__staff_profile__staff_role').first()
        if not invite:
            return Response({"error": "Invitation not found."}, status=status.HTTP_404_NOT_FOUND)

        if invite.consumed_at is not None or invite.user.status == AccountStatusChoices.ACTIVE:
            return Response({
                "error": "Cannot resend invitation for an account that has already been activated."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Invalidate existing token and issue a fresh one
        raw_token = secrets.token_urlsafe(32)
        invite.token_hash = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()
        invite.expires_at = timezone.now() + timedelta(days=2)
        invite.save(update_fields=['token_hash', 'expires_at', 'updated_at'])

        user = invite.user
        staff_role_name = user.staff_profile.staff_role.name if (hasattr(user, 'staff_profile') and user.staff_profile.staff_role) else "Operations Staff"
        department = user.staff_profile.department if hasattr(user, 'staff_profile') else "Operations"

        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000').rstrip('/')
        invite_link = f"{frontend_url}/set-password?token={raw_token}"

        try:
            send_mail(
                subject="DriverXtra Staff Invitation (Resent)",
                message=(
                    f"Hello {user.full_name or user.email},\n\n"
                    f"Your invitation to join DriverXtra Operations as a {staff_role_name} ({department}) has been refreshed.\n\n"
                    f"Please set your password using this link:\n{invite_link}\n\n"
                    f"This link expires in 48 hours.\n\nDriverXtra Operations Team"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
        except Exception as mail_exc:
            logger.error("Failed to deliver resent staff invitation email to %s: %s", user.email, str(mail_exc))
            corr_id = getattr(request, 'correlation_id', '')
            record_denied_audit_entry(
                action="staff:invite_resend",
                resource_type="User",
                resource_id=str(user.id),
                actor_id=request.user.id,
                reason_code="EMAIL_DELIVERY_FAILED",
                correlation_id=corr_id,
                metadata={"email": user.email, "error": str(mail_exc)},
            )
            return Response({
                "error": "Failed to deliver invitation email. Please verify the email server or recipient address."
            }, status=status.HTTP_400_BAD_REQUEST)

        corr_id = getattr(request, 'correlation_id', '')
        record_audit_entry(
            event_type="staff.invite.resent",
            action="staff:invite_resend",
            resource_type="User",
            resource_id=str(user.id),
            actor_id=request.user.id,
            correlation_id=corr_id,
            metadata={"email": user.email, "invite_id": str(invite.id)},
        )

        resp = {
            "status": "success",
            "message": "Staff invitation dispatched successfully.",
            "email": user.email,
        }
        if getattr(settings, 'DEBUG', False):
            resp["invite_token"] = raw_token
        return Response(resp, status=status.HTTP_200_OK)


class StaffInvitationRevokeView(views.APIView):
    """POST /api/v1/admin/staff/invitations/<pk>/revoke/
    DELETE /api/v1/admin/staff/invitations/<pk>/revoke/
    Revokes a pending staff invitation and safely cleans up unactivated invite records.
    """
    permission_classes = [IsMarketplaceAdmin]

    @transaction.atomic
    def post(self, request, pk):
        return self._revoke(request, pk)

    @transaction.atomic
    def delete(self, request, pk):
        return self._revoke(request, pk)

    def _revoke(self, request, pk):
        import uuid
        try:
            uuid.UUID(str(pk))
        except (ValueError, TypeError, AttributeError):
            return Response({"error": "Invitation not found."}, status=status.HTTP_404_NOT_FOUND)

        invite = StaffInviteToken.objects.filter(models.Q(id=pk) | models.Q(user__id=pk)).select_related('user').first()
        if not invite:
            return Response({"error": "Invitation not found."}, status=status.HTTP_404_NOT_FOUND)

        if invite.consumed_at is not None or invite.user.status == AccountStatusChoices.ACTIVE:
            return Response({
                "error": "Cannot revoke an invitation that has already been accepted and activated."
            }, status=status.HTTP_400_BAD_REQUEST)

        user = invite.user
        email = user.email

        # Delete token and pending user record safely
        invite.delete()
        if user.status == AccountStatusChoices.PENDING and not user.has_usable_password():
            user.delete()

        corr_id = getattr(request, 'correlation_id', '')
        record_audit_entry(
            event_type="staff.invite.revoked",
            action="staff:invite_revoke",
            resource_type="StaffInviteToken",
            resource_id=str(pk),
            actor_id=request.user.id,
            correlation_id=corr_id,
            metadata={"email": email},
        )

        return Response({
            "status": "success",
            "message": "Staff invitation successfully revoked.",
        }, status=status.HTTP_200_OK)



class ApprovalRequestRejectView(APIView):
    """POST /api/v1/admin/approvals/<id>/reject/

    Rejects a pending approval request with a required reason.
    Maker cannot review own request. Requires 'finance.payout' or admin.
    """
    permission_classes = [IsPlatformStaff]

    def post(self, request, pk):
        from apps.identity.approval_service import ApprovalService
        from apps.identity.serializers import ApprovalActionSerializer, ApprovalRequestSerializer

        serializer = ApprovalActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get('reason', '').strip()
        notes = serializer.validated_data.get('notes', '').strip()

        if not reason:
            return Response({"error": "A rejection reason is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            rejected_req = ApprovalService.reject_request(
                approval_request_id=pk,
                approver=request.user,
                reason=reason,
                notes=notes,
            )
            return Response({
                "status": "success",
                "message": "Approval request rejected.",
                "approval_request": ApprovalRequestSerializer(rejected_req, context={'request': request}).data,
            }, status=status.HTTP_200_OK)
        except DjangoValidationError as exc:
            msg = exc.message if hasattr(exc, 'message') else str(exc)
            if "permission denied" in msg.lower():
                return Response({"detail": msg}, status=status.HTTP_403_FORBIDDEN)
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)




class StaffRoleListView(views.APIView):
    """GET /api/v1/admin/staff/roles/
    List active platform staff roles and their granted capabilities.
    """
    permission_classes = [IsMarketplaceAdmin]

    def get(self, request):
        roles = StaffRole.objects.all().prefetch_related('role_permissions__permission').order_by('name')
        return Response({
            "status": "success",
            "roles": StaffRoleSerializer(roles, many=True).data,
        }, status=status.HTTP_200_OK)


class StaffMetricsView(views.APIView):
    """GET /api/v1/admin/staff/metrics/
    Aggregated operational metrics for staff dashboard.
    """
    permission_classes = [IsMarketplaceAdmin]

    def get(self, request):
        staff_qs = User.objects.filter(
            models.Q(is_staff=True) |
            models.Q(staff_profile__isnull=False) |
            models.Q(user_roles__role__in=['STAFF', RoleChoices.ADMIN])
        ).distinct()

        total_staff = staff_qs.count()
        active_staff = staff_qs.filter(status=AccountStatusChoices.ACTIVE, is_active=True).count()
        suspended_staff = staff_qs.filter(models.Q(status=AccountStatusChoices.SUSPENDED) | models.Q(is_active=False)).count()
        pending_invitations = StaffInviteToken.objects.filter(
            consumed_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).count()

        mfa_enrolled_count = staff_qs.filter(staff_profile__totp_enabled=True).count()
        mfa_rate = round((mfa_enrolled_count / total_staff * 100), 1) if total_staff > 0 else 0.0

        role_dist = {}
        for role in StaffRole.objects.all():
            role_dist[role.code] = staff_qs.filter(staff_profile__staff_role=role).count()
        role_dist['ADMIN'] = staff_qs.filter(models.Q(is_superuser=True) | models.Q(user_roles__role=RoleChoices.ADMIN)).distinct().count()

        return Response({
            "status": "success",
            "metrics": {
                "total_staff": total_staff,
                "active_staff": active_staff,
                "suspended_staff": suspended_staff,
                "pending_invitations": pending_invitations,
                "mfa_enrolled_count": mfa_enrolled_count,
                "mfa_adoption_percentage": mfa_rate,
                "role_distribution": role_dist,
            }
        }, status=status.HTTP_200_OK)


class StaffMemberListView(views.APIView):
    """GET /api/v1/admin/staff/
    Search and filter staff directory.
    """
    permission_classes = [IsMarketplaceAdmin]

    def get(self, request):
        staff_qs = User.objects.filter(
            models.Q(is_staff=True) |
            models.Q(staff_profile__isnull=False) |
            models.Q(user_roles__role__in=['STAFF', RoleChoices.ADMIN])
        ).distinct().select_related('staff_profile__staff_role').order_by('-date_joined')

        search = request.query_params.get('search', '').strip()
        if search:
            staff_qs = staff_qs.filter(
                models.Q(email__icontains=search) |
                models.Q(first_name__icontains=search) |
                models.Q(last_name__icontains=search)
            )

        role = request.query_params.get('role', '').strip().upper()
        if role:
            if role == 'ADMIN':
                staff_qs = staff_qs.filter(
                    models.Q(is_superuser=True) |
                    models.Q(user_roles__role=RoleChoices.ADMIN) |
                    models.Q(staff_profile__staff_role__code='ADMIN')
                )
            else:
                staff_qs = staff_qs.filter(staff_profile__staff_role__code=role)

        status_param = request.query_params.get('status', '').strip().upper()
        if status_param:
            if status_param == AccountStatusChoices.ACTIVE:
                staff_qs = staff_qs.filter(status=AccountStatusChoices.ACTIVE, is_active=True)
            elif status_param == AccountStatusChoices.SUSPENDED:
                staff_qs = staff_qs.filter(models.Q(status=AccountStatusChoices.SUSPENDED) | models.Q(is_active=False))
            else:
                staff_qs = staff_qs.filter(status=status_param)

        mfa_param = request.query_params.get('mfa', '').strip().lower()
        if mfa_param in ('true', '1'):
            staff_qs = staff_qs.filter(staff_profile__totp_enabled=True)
        elif mfa_param in ('false', '0'):
            staff_qs = staff_qs.filter(models.Q(staff_profile__totp_enabled=False) | models.Q(staff_profile__isnull=True))

        data = StaffMemberSerializer(staff_qs, many=True).data
        return Response({
            "status": "success",
            "count": len(data),
            "results": data,
        }, status=status.HTTP_200_OK)


class StaffMemberDetailView(views.APIView):
    """GET /api/v1/admin/staff/<pk>/
    PATCH /api/v1/admin/staff/<pk>/
    View and modify staff member role, department, or status.
    """
    permission_classes = [IsMarketplaceAdmin]

    def _get_target_user(self, pk):
        import uuid
        try:
            uuid.UUID(str(pk))
        except (ValueError, TypeError, AttributeError):
            return None

        try:
            return User.objects.filter(id=pk).select_related('staff_profile__staff_role').first()
        except (DjangoValidationError, ValueError):
            return None

    def get(self, request, pk):
        user = self._get_target_user(pk)
        if not user:
            return Response({"error": "Staff member not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response({
            "status": "success",
            "staff_member": StaffMemberSerializer(user).data,
        }, status=status.HTTP_200_OK)

    def patch(self, request, pk):
        user = self._get_target_user(pk)
        if not user:
            return Response({"error": "Staff member not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = StaffMemberUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        target_status = validated.get('status')
        target_role = validated.get('staff_role')
        target_department = validated.get('department')

        # Prevent admin from suspending themselves
        if target_status == AccountStatusChoices.SUSPENDED and str(request.user.id) == str(user.id):
            return Response({"error": "Cannot suspend your own administrator account."}, status=status.HTTP_400_BAD_REQUEST)

        # Update status
        if target_status:
            user.status = target_status
            if target_status == AccountStatusChoices.SUSPENDED:
                user.is_active = False
            elif target_status == AccountStatusChoices.ACTIVE:
                user.is_active = True
            user.save(update_fields=['status', 'is_active', 'updated_at'])

        # Update staff profile
        profile, _ = StaffProfile.objects.get_or_create(user=user)
        updated_profile_fields = []
        if target_role:
            role_obj = StaffRole.objects.get(code=target_role)
            profile.staff_role = role_obj
            updated_profile_fields.append('staff_role')
        if target_department is not None and target_department.strip():
            profile.department = target_department.strip()
            updated_profile_fields.append('department')

        if updated_profile_fields:
            updated_profile_fields.append('updated_at')
            profile.save(update_fields=updated_profile_fields)

        corr_id = getattr(request, 'correlation_id', '')
        record_audit_entry(
            event_type="staff.member.updated",
            action="staff:update",
            resource_type="User",
            resource_id=str(user.id),
            actor_id=request.user.id,
            correlation_id=corr_id,
            metadata={
                "target_email": user.email,
                "new_status": target_status,
                "new_role": target_role,
                "new_department": target_department,
            },
        )

        user.refresh_from_db()
        return Response({
            "status": "success",
            "message": "Staff member updated successfully.",
            "staff_member": StaffMemberSerializer(user).data,
        }, status=status.HTTP_200_OK)


class StaffInvitationListView(views.APIView):
    """GET /api/v1/admin/staff/invitations/
    List and filter pending, accepted, and expired staff invitations.
    """
    permission_classes = [IsMarketplaceAdmin]

    def get(self, request):
        now = timezone.now()
        qs = StaffInviteToken.objects.all().select_related('user__staff_profile__staff_role').order_by('-created_at')

        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                models.Q(user__email__icontains=search) |
                models.Q(user__first_name__icontains=search) |
                models.Q(user__last_name__icontains=search)
            )

        status_param = request.query_params.get('status', '').strip().upper()
        if status_param == 'PENDING':
            qs = qs.filter(consumed_at__isnull=True, expires_at__gt=now)
        elif status_param == 'EXPIRED':
            qs = qs.filter(consumed_at__isnull=True, expires_at__lte=now)
        elif status_param == 'ACCEPTED':
            qs = qs.filter(consumed_at__isnull=False)

        data = StaffInvitationSerializer(qs, many=True).data
        return Response({
            "status": "success",
            "count": len(data),
            "results": data,
        }, status=status.HTTP_200_OK)


class StaffInvitationResendView(views.APIView):
    """POST /api/v1/admin/staff/invitations/<pk>/resend/
    Generates a new secure token, extends validity to 48 hours, and dispatches an invitation email.
    """
    permission_classes = [IsMarketplaceAdmin]

    @transaction.atomic
    def post(self, request, pk):
        import uuid
        try:
            uuid.UUID(str(pk))
        except (ValueError, TypeError, AttributeError):
            return Response({"error": "Invitation not found."}, status=status.HTTP_404_NOT_FOUND)

        import secrets
        import hashlib
        from datetime import timedelta
        from django.core.mail import send_mail
        from django.conf import settings

        invite = StaffInviteToken.objects.filter(models.Q(id=pk) | models.Q(user__id=pk)).select_related('user__staff_profile__staff_role').first()
        if not invite:
            return Response({"error": "Invitation not found."}, status=status.HTTP_404_NOT_FOUND)

        if invite.consumed_at is not None or invite.user.status == AccountStatusChoices.ACTIVE:
            return Response({
                "error": "Cannot resend invitation for an account that has already been activated."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Invalidate existing token and issue a fresh one
        raw_token = secrets.token_urlsafe(32)
        invite.token_hash = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()
        invite.expires_at = timezone.now() + timedelta(days=2)
        invite.save(update_fields=['token_hash', 'expires_at', 'updated_at'])

        user = invite.user
        staff_role_name = user.staff_profile.staff_role.name if (hasattr(user, 'staff_profile') and user.staff_profile.staff_role) else "Operations Staff"
        department = user.staff_profile.department if hasattr(user, 'staff_profile') else "Operations"

        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000').rstrip('/')
        invite_link = f"{frontend_url}/set-password?token={raw_token}"

        try:
            send_mail(
                subject="DriverXtra Staff Invitation (Resent)",
                message=(
                    f"Hello {user.full_name or user.email},\n\n"
                    f"Your invitation to join DriverXtra Operations as a {staff_role_name} ({department}) has been refreshed.\n\n"
                    f"Please set your password using this link:\n{invite_link}\n\n"
                    f"This link expires in 48 hours.\n\nDriverXtra Operations Team"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
        except Exception as mail_exc:
            logger.error("Failed to deliver resent staff invitation email to %s: %s", user.email, str(mail_exc))
            corr_id = getattr(request, 'correlation_id', '')
            record_denied_audit_entry(
                action="staff:invite_resend",
                resource_type="User",
                resource_id=str(user.id),
                actor_id=request.user.id,
                reason_code="EMAIL_DELIVERY_FAILED",
                correlation_id=corr_id,
                metadata={"email": user.email, "error": str(mail_exc)},
            )
            return Response({
                "error": "Failed to deliver invitation email. Please verify the email server or recipient address."
            }, status=status.HTTP_400_BAD_REQUEST)

        corr_id = getattr(request, 'correlation_id', '')
        record_audit_entry(
            event_type="staff.invite.resent",
            action="staff:invite_resend",
            resource_type="User",
            resource_id=str(user.id),
            actor_id=request.user.id,
            correlation_id=corr_id,
            metadata={"email": user.email, "invite_id": str(invite.id)},
        )

        resp = {
            "status": "success",
            "message": "Staff invitation dispatched successfully.",
            "email": user.email,
        }
        if getattr(settings, 'DEBUG', False):
            resp["invite_token"] = raw_token
        return Response(resp, status=status.HTTP_200_OK)


class StaffInvitationRevokeView(views.APIView):
    """POST /api/v1/admin/staff/invitations/<pk>/revoke/
    DELETE /api/v1/admin/staff/invitations/<pk>/revoke/
    Revokes a pending staff invitation and safely cleans up unactivated invite records.
    """
    permission_classes = [IsMarketplaceAdmin]

    @transaction.atomic
    def post(self, request, pk):
        return self._revoke(request, pk)

    @transaction.atomic
    def delete(self, request, pk):
        return self._revoke(request, pk)

    def _revoke(self, request, pk):
        import uuid
        try:
            uuid.UUID(str(pk))
        except (ValueError, TypeError, AttributeError):
            return Response({"error": "Invitation not found."}, status=status.HTTP_404_NOT_FOUND)

        invite = StaffInviteToken.objects.filter(models.Q(id=pk) | models.Q(user__id=pk)).select_related('user').first()
        if not invite:
            return Response({"error": "Invitation not found."}, status=status.HTTP_404_NOT_FOUND)

        if invite.consumed_at is not None or invite.user.status == AccountStatusChoices.ACTIVE:
            return Response({
                "error": "Cannot revoke an invitation that has already been accepted and activated."
            }, status=status.HTTP_400_BAD_REQUEST)

        user = invite.user
        email = user.email

        # Delete token and pending user record safely
        invite.delete()
        if user.status == AccountStatusChoices.PENDING and not user.has_usable_password():
            user.delete()

        corr_id = getattr(request, 'correlation_id', '')
        record_audit_entry(
            event_type="staff.invite.revoked",
            action="staff:invite_revoke",
            resource_type="StaffInviteToken",
            resource_id=str(pk),
            actor_id=request.user.id,
            correlation_id=corr_id,
            metadata={"email": email},
        )

        return Response({
            "status": "success",
            "message": "Staff invitation successfully revoked.",
        }, status=status.HTTP_200_OK)



class ApprovalRequestCancelView(APIView):
    """POST /api/v1/admin/approvals/<id>/cancel/

    Cancels a pending approval request.
    Only requester or platform administrator can cancel.
    """
    permission_classes = [IsPlatformStaff]

    def post(self, request, pk):
        from apps.identity.approval_service import ApprovalService
        from apps.identity.serializers import ApprovalActionSerializer, ApprovalRequestSerializer

        serializer = ApprovalActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        notes = serializer.validated_data.get('notes', '')

        try:
            cancelled_req = ApprovalService.cancel_request(
                approval_request_id=pk,
                actor=request.user,
                notes=notes,
            )
            return Response({
                "status": "success",
                "message": "Approval request cancelled.",
                "approval_request": ApprovalRequestSerializer(cancelled_req, context={'request': request}).data,
            }, status=status.HTTP_200_OK)
        except DjangoValidationError as exc:
            msg = exc.message if hasattr(exc, 'message') else str(exc)
            if "permission denied" in msg.lower():
                return Response({"detail": msg}, status=status.HTTP_403_FORBIDDEN)
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)




class StaffRoleListView(views.APIView):
    """GET /api/v1/admin/staff/roles/
    List active platform staff roles and their granted capabilities.
    """
    permission_classes = [IsMarketplaceAdmin]

    def get(self, request):
        roles = StaffRole.objects.all().prefetch_related('role_permissions__permission').order_by('name')
        return Response({
            "status": "success",
            "roles": StaffRoleSerializer(roles, many=True).data,
        }, status=status.HTTP_200_OK)


class StaffMetricsView(views.APIView):
    """GET /api/v1/admin/staff/metrics/
    Aggregated operational metrics for staff dashboard.
    """
    permission_classes = [IsMarketplaceAdmin]

    def get(self, request):
        staff_qs = User.objects.filter(
            models.Q(is_staff=True) |
            models.Q(staff_profile__isnull=False) |
            models.Q(user_roles__role__in=['STAFF', RoleChoices.ADMIN])
        ).distinct()

        total_staff = staff_qs.count()
        active_staff = staff_qs.filter(status=AccountStatusChoices.ACTIVE, is_active=True).count()
        suspended_staff = staff_qs.filter(models.Q(status=AccountStatusChoices.SUSPENDED) | models.Q(is_active=False)).count()
        pending_invitations = StaffInviteToken.objects.filter(
            consumed_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).count()

        mfa_enrolled_count = staff_qs.filter(staff_profile__totp_enabled=True).count()
        mfa_rate = round((mfa_enrolled_count / total_staff * 100), 1) if total_staff > 0 else 0.0

        role_dist = {}
        for role in StaffRole.objects.all():
            role_dist[role.code] = staff_qs.filter(staff_profile__staff_role=role).count()
        role_dist['ADMIN'] = staff_qs.filter(models.Q(is_superuser=True) | models.Q(user_roles__role=RoleChoices.ADMIN)).distinct().count()

        return Response({
            "status": "success",
            "metrics": {
                "total_staff": total_staff,
                "active_staff": active_staff,
                "suspended_staff": suspended_staff,
                "pending_invitations": pending_invitations,
                "mfa_enrolled_count": mfa_enrolled_count,
                "mfa_adoption_percentage": mfa_rate,
                "role_distribution": role_dist,
            }
        }, status=status.HTTP_200_OK)


class StaffMemberListView(views.APIView):
    """GET /api/v1/admin/staff/
    Search and filter staff directory.
    """
    permission_classes = [IsMarketplaceAdmin]

    def get(self, request):
        staff_qs = User.objects.filter(
            models.Q(is_staff=True) |
            models.Q(staff_profile__isnull=False) |
            models.Q(user_roles__role__in=['STAFF', RoleChoices.ADMIN])
        ).distinct().select_related('staff_profile__staff_role').order_by('-date_joined')

        search = request.query_params.get('search', '').strip()
        if search:
            staff_qs = staff_qs.filter(
                models.Q(email__icontains=search) |
                models.Q(first_name__icontains=search) |
                models.Q(last_name__icontains=search)
            )

        role = request.query_params.get('role', '').strip().upper()
        if role:
            if role == 'ADMIN':
                staff_qs = staff_qs.filter(
                    models.Q(is_superuser=True) |
                    models.Q(user_roles__role=RoleChoices.ADMIN) |
                    models.Q(staff_profile__staff_role__code='ADMIN')
                )
            else:
                staff_qs = staff_qs.filter(staff_profile__staff_role__code=role)

        status_param = request.query_params.get('status', '').strip().upper()
        if status_param:
            if status_param == AccountStatusChoices.ACTIVE:
                staff_qs = staff_qs.filter(status=AccountStatusChoices.ACTIVE, is_active=True)
            elif status_param == AccountStatusChoices.SUSPENDED:
                staff_qs = staff_qs.filter(models.Q(status=AccountStatusChoices.SUSPENDED) | models.Q(is_active=False))
            else:
                staff_qs = staff_qs.filter(status=status_param)

        mfa_param = request.query_params.get('mfa', '').strip().lower()
        if mfa_param in ('true', '1'):
            staff_qs = staff_qs.filter(staff_profile__totp_enabled=True)
        elif mfa_param in ('false', '0'):
            staff_qs = staff_qs.filter(models.Q(staff_profile__totp_enabled=False) | models.Q(staff_profile__isnull=True))

        data = StaffMemberSerializer(staff_qs, many=True).data
        return Response({
            "status": "success",
            "count": len(data),
            "results": data,
        }, status=status.HTTP_200_OK)


class StaffMemberDetailView(views.APIView):
    """GET /api/v1/admin/staff/<pk>/
    PATCH /api/v1/admin/staff/<pk>/
    View and modify staff member role, department, or status.
    """
    permission_classes = [IsMarketplaceAdmin]

    def _get_target_user(self, pk):
        import uuid
        try:
            uuid.UUID(str(pk))
        except (ValueError, TypeError, AttributeError):
            return None

        try:
            return User.objects.filter(id=pk).select_related('staff_profile__staff_role').first()
        except (DjangoValidationError, ValueError):
            return None

    def get(self, request, pk):
        user = self._get_target_user(pk)
        if not user:
            return Response({"error": "Staff member not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response({
            "status": "success",
            "staff_member": StaffMemberSerializer(user).data,
        }, status=status.HTTP_200_OK)

    def patch(self, request, pk):
        user = self._get_target_user(pk)
        if not user:
            return Response({"error": "Staff member not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = StaffMemberUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        target_status = validated.get('status')
        target_role = validated.get('staff_role')
        target_department = validated.get('department')

        # Prevent admin from suspending themselves
        if target_status == AccountStatusChoices.SUSPENDED and str(request.user.id) == str(user.id):
            return Response({"error": "Cannot suspend your own administrator account."}, status=status.HTTP_400_BAD_REQUEST)

        # Update status
        if target_status:
            user.status = target_status
            if target_status == AccountStatusChoices.SUSPENDED:
                user.is_active = False
            elif target_status == AccountStatusChoices.ACTIVE:
                user.is_active = True
            user.save(update_fields=['status', 'is_active', 'updated_at'])

        # Update staff profile
        profile, _ = StaffProfile.objects.get_or_create(user=user)
        updated_profile_fields = []
        if target_role:
            role_obj = StaffRole.objects.get(code=target_role)
            profile.staff_role = role_obj
            updated_profile_fields.append('staff_role')
        if target_department is not None and target_department.strip():
            profile.department = target_department.strip()
            updated_profile_fields.append('department')

        if updated_profile_fields:
            updated_profile_fields.append('updated_at')
            profile.save(update_fields=updated_profile_fields)

        corr_id = getattr(request, 'correlation_id', '')
        record_audit_entry(
            event_type="staff.member.updated",
            action="staff:update",
            resource_type="User",
            resource_id=str(user.id),
            actor_id=request.user.id,
            correlation_id=corr_id,
            metadata={
                "target_email": user.email,
                "new_status": target_status,
                "new_role": target_role,
                "new_department": target_department,
            },
        )

        user.refresh_from_db()
        return Response({
            "status": "success",
            "message": "Staff member updated successfully.",
            "staff_member": StaffMemberSerializer(user).data,
        }, status=status.HTTP_200_OK)


class StaffInvitationListView(views.APIView):
    """GET /api/v1/admin/staff/invitations/
    List and filter pending, accepted, and expired staff invitations.
    """
    permission_classes = [IsMarketplaceAdmin]

    def get(self, request):
        now = timezone.now()
        qs = StaffInviteToken.objects.all().select_related('user__staff_profile__staff_role').order_by('-created_at')

        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                models.Q(user__email__icontains=search) |
                models.Q(user__first_name__icontains=search) |
                models.Q(user__last_name__icontains=search)
            )

        status_param = request.query_params.get('status', '').strip().upper()
        if status_param == 'PENDING':
            qs = qs.filter(consumed_at__isnull=True, expires_at__gt=now)
        elif status_param == 'EXPIRED':
            qs = qs.filter(consumed_at__isnull=True, expires_at__lte=now)
        elif status_param == 'ACCEPTED':
            qs = qs.filter(consumed_at__isnull=False)

        data = StaffInvitationSerializer(qs, many=True).data
        return Response({
            "status": "success",
            "count": len(data),
            "results": data,
        }, status=status.HTTP_200_OK)


class StaffInvitationResendView(views.APIView):
    """POST /api/v1/admin/staff/invitations/<pk>/resend/
    Generates a new secure token, extends validity to 48 hours, and dispatches an invitation email.
    """
    permission_classes = [IsMarketplaceAdmin]

    @transaction.atomic
    def post(self, request, pk):
        import uuid
        try:
            uuid.UUID(str(pk))
        except (ValueError, TypeError, AttributeError):
            return Response({"error": "Invitation not found."}, status=status.HTTP_404_NOT_FOUND)

        import secrets
        import hashlib
        from datetime import timedelta
        from django.core.mail import send_mail
        from django.conf import settings

        invite = StaffInviteToken.objects.filter(models.Q(id=pk) | models.Q(user__id=pk)).select_related('user__staff_profile__staff_role').first()
        if not invite:
            return Response({"error": "Invitation not found."}, status=status.HTTP_404_NOT_FOUND)

        if invite.consumed_at is not None or invite.user.status == AccountStatusChoices.ACTIVE:
            return Response({
                "error": "Cannot resend invitation for an account that has already been activated."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Invalidate existing token and issue a fresh one
        raw_token = secrets.token_urlsafe(32)
        invite.token_hash = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()
        invite.expires_at = timezone.now() + timedelta(days=2)
        invite.save(update_fields=['token_hash', 'expires_at', 'updated_at'])

        user = invite.user
        staff_role_name = user.staff_profile.staff_role.name if (hasattr(user, 'staff_profile') and user.staff_profile.staff_role) else "Operations Staff"
        department = user.staff_profile.department if hasattr(user, 'staff_profile') else "Operations"

        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000').rstrip('/')
        invite_link = f"{frontend_url}/set-password?token={raw_token}"

        try:
            send_mail(
                subject="DriverXtra Staff Invitation (Resent)",
                message=(
                    f"Hello {user.full_name or user.email},\n\n"
                    f"Your invitation to join DriverXtra Operations as a {staff_role_name} ({department}) has been refreshed.\n\n"
                    f"Please set your password using this link:\n{invite_link}\n\n"
                    f"This link expires in 48 hours.\n\nDriverXtra Operations Team"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
        except Exception as mail_exc:
            logger.error("Failed to deliver resent staff invitation email to %s: %s", user.email, str(mail_exc))
            corr_id = getattr(request, 'correlation_id', '')
            record_denied_audit_entry(
                action="staff:invite_resend",
                resource_type="User",
                resource_id=str(user.id),
                actor_id=request.user.id,
                reason_code="EMAIL_DELIVERY_FAILED",
                correlation_id=corr_id,
                metadata={"email": user.email, "error": str(mail_exc)},
            )
            return Response({
                "error": "Failed to deliver invitation email. Please verify the email server or recipient address."
            }, status=status.HTTP_400_BAD_REQUEST)

        corr_id = getattr(request, 'correlation_id', '')
        record_audit_entry(
            event_type="staff.invite.resent",
            action="staff:invite_resend",
            resource_type="User",
            resource_id=str(user.id),
            actor_id=request.user.id,
            correlation_id=corr_id,
            metadata={"email": user.email, "invite_id": str(invite.id)},
        )

        resp = {
            "status": "success",
            "message": "Staff invitation dispatched successfully.",
            "email": user.email,
        }
        if getattr(settings, 'DEBUG', False):
            resp["invite_token"] = raw_token
        return Response(resp, status=status.HTTP_200_OK)


class StaffInvitationRevokeView(views.APIView):
    """POST /api/v1/admin/staff/invitations/<pk>/revoke/
    DELETE /api/v1/admin/staff/invitations/<pk>/revoke/
    Revokes a pending staff invitation and safely cleans up unactivated invite records.
    """
    permission_classes = [IsMarketplaceAdmin]

    @transaction.atomic
    def post(self, request, pk):
        return self._revoke(request, pk)

    @transaction.atomic
    def delete(self, request, pk):
        return self._revoke(request, pk)

    def _revoke(self, request, pk):
        import uuid
        try:
            uuid.UUID(str(pk))
        except (ValueError, TypeError, AttributeError):
            return Response({"error": "Invitation not found."}, status=status.HTTP_404_NOT_FOUND)

        invite = StaffInviteToken.objects.filter(models.Q(id=pk) | models.Q(user__id=pk)).select_related('user').first()
        if not invite:
            return Response({"error": "Invitation not found."}, status=status.HTTP_404_NOT_FOUND)

        if invite.consumed_at is not None or invite.user.status == AccountStatusChoices.ACTIVE:
            return Response({
                "error": "Cannot revoke an invitation that has already been accepted and activated."
            }, status=status.HTTP_400_BAD_REQUEST)

        user = invite.user
        email = user.email

        # Delete token and pending user record safely
        invite.delete()
        if user.status == AccountStatusChoices.PENDING and not user.has_usable_password():
            user.delete()

        corr_id = getattr(request, 'correlation_id', '')
        record_audit_entry(
            event_type="staff.invite.revoked",
            action="staff:invite_revoke",
            resource_type="StaffInviteToken",
            resource_id=str(pk),
            actor_id=request.user.id,
            correlation_id=corr_id,
            metadata={"email": email},
        )

        return Response({
            "status": "success",
            "message": "Staff invitation successfully revoked.",
        }, status=status.HTTP_200_OK)



class ApprovalRequestExecuteView(APIView):
    """POST /api/v1/admin/approvals/<id>/execute/

    Executes an approved request (e.g. gateway refund dispatch).
    Requires 'finance.payout' or admin. Status must be APPROVED.
    """
    permission_classes = [IsPlatformStaff, HasPermission('finance.payout')]

    def post(self, request, pk):
        from apps.identity.approval_service import ApprovalService
        from apps.identity.serializers import ApprovalRequestSerializer

        try:
            executed_req, result = ApprovalService.execute_request(
                approval_request_id=pk,
                executor=request.user,
            )
            return Response({
                "status": "success",
                "message": "Approval request executed successfully.",
                "approval_request": ApprovalRequestSerializer(executed_req, context={'request': request}).data,
            }, status=status.HTTP_200_OK)
        except DjangoValidationError as exc:
            msg = exc.message if hasattr(exc, 'message') else str(exc)
            if "permission denied" in msg.lower():
                return Response({"detail": msg}, status=status.HTTP_403_FORBIDDEN)
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class StaffRoleListView(views.APIView):
    """GET /api/v1/admin/staff/roles/
    List active platform staff roles and their granted capabilities.
    """
    permission_classes = [IsMarketplaceAdmin]

    def get(self, request):
        roles = StaffRole.objects.all().prefetch_related('role_permissions__permission').order_by('name')
        return Response({
            "status": "success",
            "roles": StaffRoleSerializer(roles, many=True).data,
        }, status=status.HTTP_200_OK)


class StaffMetricsView(views.APIView):
    """GET /api/v1/admin/staff/metrics/
    Aggregated operational metrics for staff dashboard.
    """
    permission_classes = [IsMarketplaceAdmin]

    def get(self, request):
        staff_qs = User.objects.filter(
            models.Q(is_staff=True) |
            models.Q(staff_profile__isnull=False) |
            models.Q(user_roles__role__in=['STAFF', RoleChoices.ADMIN])
        ).distinct()

        total_staff = staff_qs.count()
        active_staff = staff_qs.filter(status=AccountStatusChoices.ACTIVE, is_active=True).count()
        suspended_staff = staff_qs.filter(models.Q(status=AccountStatusChoices.SUSPENDED) | models.Q(is_active=False)).count()
        pending_invitations = StaffInviteToken.objects.filter(
            consumed_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).count()

        mfa_enrolled_count = staff_qs.filter(staff_profile__totp_enabled=True).count()
        mfa_rate = round((mfa_enrolled_count / total_staff * 100), 1) if total_staff > 0 else 0.0

        role_dist = {}
        for role in StaffRole.objects.all():
            role_dist[role.code] = staff_qs.filter(staff_profile__staff_role=role).count()
        role_dist['ADMIN'] = staff_qs.filter(models.Q(is_superuser=True) | models.Q(user_roles__role=RoleChoices.ADMIN)).distinct().count()

        return Response({
            "status": "success",
            "metrics": {
                "total_staff": total_staff,
                "active_staff": active_staff,
                "suspended_staff": suspended_staff,
                "pending_invitations": pending_invitations,
                "mfa_enrolled_count": mfa_enrolled_count,
                "mfa_adoption_percentage": mfa_rate,
                "role_distribution": role_dist,
            }
        }, status=status.HTTP_200_OK)


class StaffMemberListView(views.APIView):
    """GET /api/v1/admin/staff/
    Search and filter staff directory.
    """
    permission_classes = [IsMarketplaceAdmin]

    def get(self, request):
        staff_qs = User.objects.filter(
            models.Q(is_staff=True) |
            models.Q(staff_profile__isnull=False) |
            models.Q(user_roles__role__in=['STAFF', RoleChoices.ADMIN])
        ).distinct().select_related('staff_profile__staff_role').order_by('-date_joined')

        search = request.query_params.get('search', '').strip()
        if search:
            staff_qs = staff_qs.filter(
                models.Q(email__icontains=search) |
                models.Q(first_name__icontains=search) |
                models.Q(last_name__icontains=search)
            )

        role = request.query_params.get('role', '').strip().upper()
        if role:
            if role == 'ADMIN':
                staff_qs = staff_qs.filter(
                    models.Q(is_superuser=True) |
                    models.Q(user_roles__role=RoleChoices.ADMIN) |
                    models.Q(staff_profile__staff_role__code='ADMIN')
                )
            else:
                staff_qs = staff_qs.filter(staff_profile__staff_role__code=role)

        status_param = request.query_params.get('status', '').strip().upper()
        if status_param:
            if status_param == AccountStatusChoices.ACTIVE:
                staff_qs = staff_qs.filter(status=AccountStatusChoices.ACTIVE, is_active=True)
            elif status_param == AccountStatusChoices.SUSPENDED:
                staff_qs = staff_qs.filter(models.Q(status=AccountStatusChoices.SUSPENDED) | models.Q(is_active=False))
            else:
                staff_qs = staff_qs.filter(status=status_param)

        mfa_param = request.query_params.get('mfa', '').strip().lower()
        if mfa_param in ('true', '1'):
            staff_qs = staff_qs.filter(staff_profile__totp_enabled=True)
        elif mfa_param in ('false', '0'):
            staff_qs = staff_qs.filter(models.Q(staff_profile__totp_enabled=False) | models.Q(staff_profile__isnull=True))

        data = StaffMemberSerializer(staff_qs, many=True).data
        return Response({
            "status": "success",
            "count": len(data),
            "results": data,
        }, status=status.HTTP_200_OK)


class StaffMemberDetailView(views.APIView):
    """GET /api/v1/admin/staff/<pk>/
    PATCH /api/v1/admin/staff/<pk>/
    View and modify staff member role, department, or status.
    """
    permission_classes = [IsMarketplaceAdmin]

    def _get_target_user(self, pk):
        import uuid
        try:
            uuid.UUID(str(pk))
        except (ValueError, TypeError, AttributeError):
            return None

        try:
            return User.objects.filter(id=pk).select_related('staff_profile__staff_role').first()
        except (DjangoValidationError, ValueError):
            return None

    def get(self, request, pk):
        user = self._get_target_user(pk)
        if not user:
            return Response({"error": "Staff member not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response({
            "status": "success",
            "staff_member": StaffMemberSerializer(user).data,
        }, status=status.HTTP_200_OK)

    def patch(self, request, pk):
        user = self._get_target_user(pk)
        if not user:
            return Response({"error": "Staff member not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = StaffMemberUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        target_status = validated.get('status')
        target_role = validated.get('staff_role')
        target_department = validated.get('department')

        # Prevent admin from suspending themselves
        if target_status == AccountStatusChoices.SUSPENDED and str(request.user.id) == str(user.id):
            return Response({"error": "Cannot suspend your own administrator account."}, status=status.HTTP_400_BAD_REQUEST)

        # Check if target is an administrator, and ensure we do not suspend or demote the last active admin
        is_target_admin = (
            user.is_superuser
            or user.has_role(RoleChoices.ADMIN)
            or (hasattr(user, 'staff_profile') and user.staff_profile and user.staff_profile.staff_role and user.staff_profile.staff_role.code == 'ADMIN')
        )
        if is_target_admin:
            other_active_admins = User.objects.filter(
                models.Q(is_superuser=True) |
                models.Q(user_roles__role=RoleChoices.ADMIN) |
                models.Q(staff_profile__staff_role__code='ADMIN'),
                is_active=True,
                status=AccountStatusChoices.ACTIVE,
            ).exclude(id=user.id).distinct().count()

            if other_active_admins == 0:
                if target_status in (AccountStatusChoices.SUSPENDED, AccountStatusChoices.DEACTIVATED):
                    return Response({
                        "error": "Cannot suspend the last active platform administrator."
                    }, status=status.HTTP_400_BAD_REQUEST)
                if target_role and target_role != 'ADMIN':
                    return Response({
                        "error": "Cannot demote the last active platform administrator."
                    }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            # Update status
            if target_status:
                user.status = target_status
                if target_status in (AccountStatusChoices.SUSPENDED, AccountStatusChoices.DEACTIVATED):
                    user.is_active = False
                elif target_status == AccountStatusChoices.ACTIVE:
                    user.is_active = True
                user.save(update_fields=['status', 'is_active', 'updated_at'])

                # If staff user was deactivated or suspended, unassign any active support tickets
                if not user.is_active:
                    from apps.support.services import TicketService
                    corr_id = getattr(request, 'correlation_id', '')
                    TicketService.handle_agent_deactivation(
                        agent=user,
                        actor=request.user,
                        correlation_id=corr_id,
                    )

            # Update staff profile
            profile, _ = StaffProfile.objects.get_or_create(user=user)
            updated_profile_fields = []
            if target_role:
                role_obj = StaffRole.objects.get(code=target_role)
                profile.staff_role = role_obj
                updated_profile_fields.append('staff_role')
                if user.has_role(RoleChoices.ADMIN) and target_role != 'ADMIN':
                    user.remove_role(RoleChoices.ADMIN)
            if target_department is not None and target_department.strip():
                profile.department = target_department.strip()
                updated_profile_fields.append('department')

            if updated_profile_fields:
                updated_profile_fields.append('updated_at')
                profile.save(update_fields=updated_profile_fields)

            corr_id = getattr(request, 'correlation_id', '')
            record_audit_entry(
                event_type="staff.member.updated",
                action="staff:update",
                resource_type="User",
                resource_id=str(user.id),
                actor_id=request.user.id,
                correlation_id=corr_id,
                metadata={
                    "target_email": user.email,
                    "new_status": target_status,
                    "new_role": target_role,
                    "new_department": target_department,
                },
            )

        user.refresh_from_db()
        return Response({
            "status": "success",
            "message": "Staff member updated successfully.",
            "staff_member": StaffMemberSerializer(user).data,
        }, status=status.HTTP_200_OK)


class StaffInvitationListView(views.APIView):
    """GET /api/v1/admin/staff/invitations/
    List and filter pending, accepted, and expired staff invitations.
    """
    permission_classes = [IsMarketplaceAdmin]

    def get(self, request):
        now = timezone.now()
        qs = StaffInviteToken.objects.all().select_related('user__staff_profile__staff_role').order_by('-created_at')

        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                models.Q(user__email__icontains=search) |
                models.Q(user__first_name__icontains=search) |
                models.Q(user__last_name__icontains=search)
            )

        status_param = request.query_params.get('status', '').strip().upper()
        if status_param == 'PENDING':
            qs = qs.filter(consumed_at__isnull=True, expires_at__gt=now)
        elif status_param == 'EXPIRED':
            qs = qs.filter(consumed_at__isnull=True, expires_at__lte=now)
        elif status_param == 'ACCEPTED':
            qs = qs.filter(consumed_at__isnull=False)

        data = StaffInvitationSerializer(qs, many=True).data
        return Response({
            "status": "success",
            "count": len(data),
            "results": data,
        }, status=status.HTTP_200_OK)


class StaffInvitationResendView(views.APIView):
    """POST /api/v1/admin/staff/invitations/<pk>/resend/
    Generates a new secure token, extends validity to 48 hours, and dispatches an invitation email.
    """
    permission_classes = [IsMarketplaceAdmin]

    @transaction.atomic
    def post(self, request, pk):
        import uuid
        try:
            uuid.UUID(str(pk))
        except (ValueError, TypeError, AttributeError):
            return Response({"error": "Invitation not found."}, status=status.HTTP_404_NOT_FOUND)

        import secrets
        import hashlib
        from datetime import timedelta
        from django.core.mail import send_mail
        from django.conf import settings

        invite = StaffInviteToken.objects.filter(models.Q(id=pk) | models.Q(user__id=pk)).select_related('user__staff_profile__staff_role').first()
        if not invite:
            return Response({"error": "Invitation not found."}, status=status.HTTP_404_NOT_FOUND)

        if invite.consumed_at is not None or invite.user.status == AccountStatusChoices.ACTIVE:
            return Response({
                "error": "Cannot resend invitation for an account that has already been activated."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Invalidate existing token and issue a fresh one
        raw_token = secrets.token_urlsafe(32)
        invite.token_hash = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()
        invite.expires_at = timezone.now() + timedelta(days=2)
        invite.save(update_fields=['token_hash', 'expires_at', 'updated_at'])

        user = invite.user
        staff_role_name = user.staff_profile.staff_role.name if (hasattr(user, 'staff_profile') and user.staff_profile.staff_role) else "Operations Staff"
        department = user.staff_profile.department if hasattr(user, 'staff_profile') else "Operations"

        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000').rstrip('/')
        invite_link = f"{frontend_url}/set-password?token={raw_token}"

        try:
            send_mail(
                subject="DriverXtra Staff Invitation (Resent)",
                message=(
                    f"Hello {user.full_name or user.email},\n\n"
                    f"Your invitation to join DriverXtra Operations as a {staff_role_name} ({department}) has been refreshed.\n\n"
                    f"Please set your password using this link:\n{invite_link}\n\n"
                    f"This link expires in 48 hours.\n\nDriverXtra Operations Team"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
        except Exception as mail_exc:
            logger.error("Failed to deliver resent staff invitation email to %s: %s", user.email, str(mail_exc))
            corr_id = getattr(request, 'correlation_id', '')
            record_denied_audit_entry(
                action="staff:invite_resend",
                resource_type="User",
                resource_id=str(user.id),
                actor_id=request.user.id,
                reason_code="EMAIL_DELIVERY_FAILED",
                correlation_id=corr_id,
                metadata={"email": user.email, "error": str(mail_exc)},
            )
            return Response({
                "error": "Failed to deliver invitation email. Please verify the email server or recipient address."
            }, status=status.HTTP_400_BAD_REQUEST)

        corr_id = getattr(request, 'correlation_id', '')
        record_audit_entry(
            event_type="staff.invite.resent",
            action="staff:invite_resend",
            resource_type="User",
            resource_id=str(user.id),
            actor_id=request.user.id,
            correlation_id=corr_id,
            metadata={"email": user.email, "invite_id": str(invite.id)},
        )

        resp = {
            "status": "success",
            "message": "Staff invitation dispatched successfully.",
            "email": user.email,
        }
        if getattr(settings, 'DEBUG', False):
            resp["invite_token"] = raw_token
        return Response(resp, status=status.HTTP_200_OK)


class StaffInvitationRevokeView(views.APIView):
    """POST /api/v1/admin/staff/invitations/<pk>/revoke/
    DELETE /api/v1/admin/staff/invitations/<pk>/revoke/
    Revokes a pending staff invitation and safely cleans up unactivated invite records.
    """
    permission_classes = [IsMarketplaceAdmin]

    @transaction.atomic
    def post(self, request, pk):
        return self._revoke(request, pk)

    @transaction.atomic
    def delete(self, request, pk):
        return self._revoke(request, pk)

    def _revoke(self, request, pk):
        import uuid
        try:
            uuid.UUID(str(pk))
        except (ValueError, TypeError, AttributeError):
            return Response({"error": "Invitation not found."}, status=status.HTTP_404_NOT_FOUND)

        invite = StaffInviteToken.objects.filter(models.Q(id=pk) | models.Q(user__id=pk)).select_related('user').first()
        if not invite:
            return Response({"error": "Invitation not found."}, status=status.HTTP_404_NOT_FOUND)

        if invite.consumed_at is not None or invite.user.status == AccountStatusChoices.ACTIVE:
            return Response({
                "error": "Cannot revoke an invitation that has already been accepted and activated."
            }, status=status.HTTP_400_BAD_REQUEST)

        user = invite.user
        email = user.email

        # Delete token and pending user record safely
        invite.delete()
        if user.status == AccountStatusChoices.PENDING and not user.has_usable_password():
            user.delete()

        corr_id = getattr(request, 'correlation_id', '')
        record_audit_entry(
            event_type="staff.invite.revoked",
            action="staff:invite_revoke",
            resource_type="StaffInviteToken",
            resource_id=str(pk),
            actor_id=request.user.id,
            correlation_id=corr_id,
            metadata={"email": email},
        )

        return Response({
            "status": "success",
            "message": "Staff invitation successfully revoked.",
        }, status=status.HTTP_200_OK)


