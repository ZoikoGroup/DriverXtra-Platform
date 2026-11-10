from rest_framework import serializers
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from typing import Any
from django.contrib.auth import get_user_model
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from .models import User, UserRole, RoleChoices, AccountStatusChoices


RESTRICTED_PUBLIC_ROLES = {
    RoleChoices.ADMIN,
    RoleChoices.STAFF,
    'MARKETPLACE_ADMIN',
    'OPERATIONS',
    'DISPUTE_ANALYST',
    'FINANCE_OPS',
}


class UserRegistrationSerializer(serializers.ModelSerializer):
    """Serializer for public user registration with input validation,

    duplicate-email prevention, and strict privilege-escalation prevention.
    """
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'},
        help_text="Password must meet platform security standards (min 8 chars)."
    )
    roles = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        write_only=True,
        help_text="Initial roles requested (e.g., BUYER, SELLER, WORKSHOP)."
    )

    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'password',
            'first_name',
            'last_name',
            'phone_number',
            'roles',
            'status',
            'is_email_verified',
            'email_verified_at',
            'created_at',
        ]
        read_only_fields = ['id', 'status', 'is_email_verified', 'email_verified_at', 'created_at']

    def validate_email(self, value):
        normalized = value.strip().lower()
        if User.objects.filter(email=normalized).exists():
            raise serializers.ValidationError("A user with this email address already exists.")
        return normalized

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value

    def validate_roles(self, value):
        """Enforces restriction allowing only BUYER registration for public sign-ups."""
        if not value:
            return [RoleChoices.BUYER]

        for r in value:
            norm = RoleChoices.normalize_role(r)
            if norm in RESTRICTED_PUBLIC_ROLES or r.strip().upper() in RESTRICTED_PUBLIC_ROLES:
                raise serializers.ValidationError(
                    f"Self-assignment of staff or administrative role '{r}' is prohibited for public registration."
                )
            if norm in [RoleChoices.SELLER, RoleChoices.WORKSHOP]:
                raise serializers.ValidationError(
                    f"Registration only permits the BUYER role. To become a {norm}, please apply via the Seller Onboarding verification process."
                )
            if norm != RoleChoices.BUYER:
                raise serializers.ValidationError(f"Invalid platform role: '{r}'.")

        return [RoleChoices.BUYER]

    def create(self, validated_data):
        validated_data.pop('roles', None)
        password = validated_data.pop('password')

        user = User.objects.create_user(
            password=password,
            status=AccountStatusChoices.ACTIVE,
            is_email_verified=False,
            email_verified_at=None,
            **validated_data
        )

        user.add_role(RoleChoices.BUYER)

        return user


class UserLoginSerializer(serializers.Serializer):
    """Serializer for authenticating users and issuing JWT access/refresh tokens."""

    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True, write_only=True, style={'input_type': 'password'})
    code = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, attrs):
        email = attrs.get('email', '').strip().lower()
        password = attrs.get('password', '')
        code = attrs.get('code', '').strip()

        user = User.objects.filter(email=email).first()

        if user is None or not user.check_password(password):
            raise serializers.ValidationError("Invalid email or password.")

        if not user.is_active or user.status != AccountStatusChoices.ACTIVE:
            raise serializers.ValidationError(
                f"Account is currently {user.status.lower()}. Please contact support."
            )

        if not user.is_email_verified:
            raise serializers.ValidationError(
                "Email address is not verified. Please verify your email before logging in."
            )

        is_staff_or_admin = (
            user.is_staff
            or user.has_role(RoleChoices.STAFF)
            or user.has_role(RoleChoices.ADMIN)
            or user.is_superuser
        )
        active_role = user.get_default_role()

        # Enforce mandatory MFA for staff and admin accounts when enabled
        mfa_enforced = getattr(settings, 'MFA_MANDATORY_ENFORCED', False)
        if mfa_enforced and is_staff_or_admin:
            if not user.has_mfa_enabled:
                from django.core import signing
                pre_auth_token = signing.dumps(
                    {'user_id': str(user.id), 'action': 'mfa_enrollment'},
                    salt='driverxtra.mfa',
                )
                return {
                    'user': user,
                    'mfa_required': True,
                    'mfa_enrollment_required': True,
                    'active_role': active_role,
                    'pre_auth_token': pre_auth_token,
                }
            elif not code:
                from django.core import signing
                pre_auth_token = signing.dumps(
                    {'user_id': str(user.id), 'action': 'mfa_login'},
                    salt='driverxtra.mfa',
                )
                return {
                    'user': user,
                    'mfa_required': True,
                    'mfa_enrollment_required': False,
                    'active_role': active_role,
                    'pre_auth_token': pre_auth_token,
                }
            else:
                profile = getattr(user, 'staff_profile', None)
                if not profile or not profile.verify_totp(code):
                    raise serializers.ValidationError({"code": "Invalid two-factor authentication code."})

        # Generate SimpleJWT tokens with active_role claim
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

        # 15-minute access tokens for staff/admin
        if is_staff_or_admin or active_role in (RoleChoices.STAFF, RoleChoices.ADMIN):
            from datetime import timedelta
            access.set_exp(lifetime=timedelta(minutes=15))

        return {
            'user': user,
            'mfa_required': False,
            'active_role': active_role,
            'tokens': {
                'access': str(access),
                'refresh': str(refresh),
            }
        }


class UserLogoutSerializer(serializers.Serializer):
    """Serializer for invalidating/blacklisting JWT refresh token upon logout."""

    refresh = serializers.CharField(required=True)

    def validate(self, attrs):
        self.token = attrs['refresh']
        return attrs

    def save(self, **kwargs):
        try:
            token = RefreshToken(self.token)
            token.blacklist()
        except TokenError as exc:
            raise serializers.ValidationError({'refresh': str(exc)})


class StaffAwareTokenRefreshSerializer(TokenRefreshSerializer):
    """Staff-aware token refresh serializer.

    Enforces 15-minute access token lifetime for platform staff and admins,
    while preserving standard lifetime for regular buyers.
    Authoritatively checks the database user identity rather than trusting token claims.
    """

    def validate(self, attrs: dict[str, Any]) -> dict[str, str]:
        refresh = self.token_class(attrs["refresh"])

        user_id = refresh.payload.get(api_settings.USER_ID_CLAIM, None)
        user = None
        if user_id:
            try:
                user = get_user_model().objects.filter(
                    **{api_settings.USER_ID_FIELD: user_id}
                ).first()
            except Exception:
                user = None

        if not user or not user.is_active or getattr(user, 'status', 'ACTIVE') != 'ACTIVE' or not api_settings.USER_AUTHENTICATION_RULE(user):
            raise AuthenticationFailed(
                self.error_messages["no_active_account"],
                "no_active_account",
            )

        access_token = refresh.access_token

        # Authoritatively evaluate permissions and roles from database record
        is_staff_or_admin = (
            user.is_staff
            or user.has_role(RoleChoices.STAFF)
            or user.has_role(RoleChoices.ADMIN)
            or user.is_superuser
        )
        active_role = user.get_default_role()

        # Update claims authoritatively
        access_token['email'] = user.email
        access_token['roles'] = user.roles
        access_token['full_name'] = user.full_name
        access_token['active_role'] = active_role

        if is_staff_or_admin or active_role in (RoleChoices.STAFF, RoleChoices.ADMIN):
            from datetime import timedelta
            access_token.set_exp(lifetime=timedelta(minutes=15))

        data = {"access": str(access_token)}

        if api_settings.ROTATE_REFRESH_TOKENS:
            if api_settings.BLACKLIST_AFTER_ROTATION:
                try:
                    refresh.blacklist()
                except AttributeError:
                    pass

            refresh.set_jti()
            refresh.set_exp()
            refresh.set_iat()

            refresh['email'] = user.email
            refresh['roles'] = user.roles
            refresh['full_name'] = user.full_name
            refresh['active_role'] = active_role

            refresh.outstand()

            data["refresh"] = str(refresh)

        return data


class OrganisationMembershipSummarySerializer(serializers.Serializer):
    """Lightweight representation of user's active organisation memberships."""
    organisation_id = serializers.UUIDField(source='organisation.id')
    organisation_name = serializers.CharField(source='organisation.name')
    organisation_slug = serializers.CharField(source='organisation.slug')
    organisation_type = serializers.CharField(source='organisation.type')
    role = serializers.CharField()
    joined_at = serializers.DateTimeField()


class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for retrieving full user profile and permitting safe profile updates."""

    roles = serializers.ListField(child=serializers.CharField(), read_only=True)
    full_name = serializers.CharField(read_only=True)
    organisations = serializers.SerializerMethodField()
    active_role = serializers.SerializerMethodField()
    has_mfa_enabled = serializers.BooleanField(read_only=True)
    staff_role = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'first_name',
            'last_name',
            'phone_number',
            'full_name',
            'status',
            'is_email_verified',
            'email_verified_at',
            'roles',
            'active_role',
            'has_mfa_enabled',
            'staff_role',
            'permissions',
            'is_staff',
            'is_superuser',
            'organisations',
            'date_joined',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'email',
            'status',
            'is_email_verified',
            'email_verified_at',
            'roles',
            'active_role',
            'has_mfa_enabled',
            'staff_role',
            'permissions',
            'is_staff',
            'is_superuser',
            'organisations',
            'date_joined',
            'created_at',
            'updated_at',
        ]

    def get_active_role(self, obj) -> str:
        request = self.context.get('request')
        if request and hasattr(request, 'auth') and isinstance(request.auth, dict):
            return request.auth.get('active_role') or obj.get_default_role()
        return obj.get_default_role()

    def get_staff_role(self, obj):
        profile = getattr(obj, 'staff_profile', None)
        if profile and profile.staff_role:
            return {
                'code': profile.staff_role.code,
                'name': profile.staff_role.name,
                'department': profile.department,
            }
        return None

    def get_permissions(self, obj) -> list[str]:
        if obj.is_superuser or obj.has_role(RoleChoices.ADMIN):
            from apps.identity.models import Permission
            return list(Permission.objects.values_list('code', flat=True))
        profile = getattr(obj, 'staff_profile', None)
        if profile and profile.staff_role:
            return list(profile.staff_role.role_permissions.values_list('permission__code', flat=True))
        return []

    def get_organisations(self, obj):
        memberships = obj.organisation_memberships.filter(is_active=True).select_related('organisation')
        return OrganisationMembershipSummarySerializer(memberships, many=True).data

    def update(self, instance, validated_data):
        # Only permit updating personal info (first_name, last_name, phone_number)
        instance.first_name = validated_data.get('first_name', instance.first_name)
        instance.last_name = validated_data.get('last_name', instance.last_name)
        instance.phone_number = validated_data.get('phone_number', instance.phone_number)
        instance.save()
        return instance


import re


def _clean_token_input(value: str) -> str:
    """Robustly extracts raw token from full URLs, query strings, labels, and quoted inputs."""
    if not value:
        return ""
    val = value.strip()

    # 1. If contains token= parameter anywhere (URL, query string, or standalone token=)
    if "token=" in val:
        m = re.search(r"(?:[?&]|(?<!\w))token=([^&\s]+)", val)
        if m:
            val = m.group(1).strip()

    # 2. If labeled like "Verification Token: xyz", "Reset Token: xyz", "Token: xyz", "Token - xyz", etc.
    label_match = re.search(
        r"^(?:(?:verification|password\s+reset|reset)\s+)?token\s*[:=\-]\s*([^\s]+)",
        val,
        re.IGNORECASE,
    )
    if label_match:
        val = label_match.group(1).strip()

    # 3. If trailing query params were copied (e.g. "tok_val&email=...")
    if "&" in val:
        val = val.split("&")[0].strip()

    # 4. Strip surrounding quotes and whitespace
    val = val.strip("\"'").strip()
    return val


class VerifyEmailSerializer(serializers.Serializer):
    """Serializer for verifying email ownership via token."""
    token = serializers.CharField(required=True, trim_whitespace=True)

    def validate_token(self, value):
        val = _clean_token_input(value)
        if not val:
            raise serializers.ValidationError("Verification token cannot be empty.")
        return val


class ResendVerificationSerializer(serializers.Serializer):
    """Serializer for requesting a fresh email verification link."""
    email = serializers.EmailField(required=True)


class PasswordResetRequestSerializer(serializers.Serializer):
    """Serializer for requesting password reset instructions."""
    email = serializers.EmailField(required=True)


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Serializer for confirming a password reset via token and new password."""
    token = serializers.CharField(required=True, trim_whitespace=True)
    new_password = serializers.CharField(
        required=True,
        write_only=True,
        style={'input_type': 'password'},
        help_text="New password meeting platform security standards (min 8 chars)."
    )

    def validate_token(self, value):
        val = _clean_token_input(value)
        if not val:
            raise serializers.ValidationError("Password reset token cannot be empty.")
        return val

    def validate_new_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value


class SwitchRoleSerializer(serializers.Serializer):
    """Validates requested target platform role for active role switching."""
    role = serializers.CharField(required=True)

    def validate_role(self, value):
        normalized = RoleChoices.normalize_role(value)
        user = self.context['request'].user
        if not (user.is_superuser or user.has_role(normalized)):
            raise serializers.ValidationError(f"User does not hold the '{normalized}' role.")
        return normalized


class StaffInviteSerializer(serializers.Serializer):
    """Validates platform staff onboarding invite issued by an administrator."""
    email = serializers.EmailField(required=True)
    first_name = serializers.CharField(required=False, allow_blank=True, default='')
    last_name = serializers.CharField(required=False, allow_blank=True, default='')
    staff_role = serializers.CharField(required=True)
    department = serializers.CharField(required=False, allow_blank=True, default='Operations')

    def validate_email(self, value):
        normalized = value.strip().lower()
        existing = User.objects.filter(email=normalized).first()
        if existing:
            if existing.status == AccountStatusChoices.ACTIVE or (existing.is_active and existing.has_usable_password()):
                raise serializers.ValidationError("A user with this email address already exists on the platform.")
            from apps.identity.models import StaffInviteToken
            from django.utils import timezone
            active_invite = StaffInviteToken.objects.filter(
                user=existing,
                consumed_at__isnull=True,
                expires_at__gt=timezone.now(),
            ).first()
            if active_invite:
                raise serializers.ValidationError(
                    "An active unexpired invitation is already pending for this email. Use the resend action if you wish to dispatch a new link."
                )
        return normalized

    def validate_staff_role(self, value):
        from apps.identity.models import StaffRole
        clean = value.strip().upper()
        if not StaffRole.objects.filter(code=clean).exists():
            raise serializers.ValidationError(f"Invalid staff role code: '{value}'.")
        return clean


class StaffSetPasswordSerializer(serializers.Serializer):
    """Validates single-use staff invite token and password initialization."""
    token = serializers.CharField(required=True, trim_whitespace=True)
    new_password = serializers.CharField(
        required=True,
        write_only=True,
        style={'input_type': 'password'},
        help_text="Password meeting platform security requirements.",
    )

    def validate(self, attrs):
        import hashlib
        from django.utils import timezone
        from apps.identity.models import StaffInviteToken

        token = attrs['token'].strip()
        new_password = attrs['new_password']

        token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
        invite_token = StaffInviteToken.objects.filter(token_hash=token_hash).select_related('user').first()

        if not invite_token or invite_token.consumed_at is not None:
            raise serializers.ValidationError({"token": "Invalid or already used invite token."})

        if invite_token.expires_at < timezone.now():
            raise serializers.ValidationError({"token": "Staff invitation link has expired."})

        try:
            validate_password(new_password, user=invite_token.user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"new_password": list(exc.messages)})

        attrs['invite_token'] = invite_token
        return attrs


class MFAVerifySerializer(serializers.Serializer):
    """Serializer for verifying a 6-digit TOTP code during enrollment or login."""
    code = serializers.CharField(required=True, trim_whitespace=True)
    pre_auth_token = serializers.CharField(required=False, allow_blank=True, default='')


class ApprovalUserBriefSerializer(serializers.ModelSerializer):
    """Compact serializer for approval request actors."""
    staff_role = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'staff_role']

    def get_staff_role(self, obj):
        if hasattr(obj, 'staff_profile') and obj.staff_profile and obj.staff_profile.staff_role:
            return obj.staff_profile.staff_role.name
        if obj.is_superuser:
            return "Platform Superuser"
        return getattr(obj, 'role', '')


class ApprovalRequestSerializer(serializers.ModelSerializer):
    """Full serializer for Maker-Checker approval requests."""
    requester = ApprovalUserBriefSerializer(read_only=True)
    approver = ApprovalUserBriefSerializer(read_only=True)
    executed_by = ApprovalUserBriefSerializer(read_only=True)
    can_approve = serializers.SerializerMethodField()
    can_execute = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()
    is_requester = serializers.SerializerMethodField()

    class Meta:
        from apps.identity.models import ApprovalRequest
        model = ApprovalRequest
        fields = [
            'id',
            'action_type',
            'target_type',
            'target_id',
            'amount',
            'currency',
            'reason',
            'payload',
            'status',
            'rejection_reason',
            'notes',
            'requested_at',
            'reviewed_at',
            'executed_at',
            'execution_error',
            'requester',
            'approver',
            'executed_by',
            'can_approve',
            'can_execute',
            'can_cancel',
            'is_requester',
            'created_at',
            'updated_at',
        ]

    def _get_user(self):
        req = self.context.get('request')
        return req.user if (req and hasattr(req, 'user') and req.user.is_authenticated) else None

    def get_is_requester(self, obj) -> bool:
        user = self._get_user()
        return bool(user and str(user.id) == str(obj.requester_id))

    def get_can_approve(self, obj) -> bool:
        from apps.identity.models import ApprovalStatusChoices
        from apps.identity.approval_service import ApprovalService
        user = self._get_user()
        if not user or str(user.id) == str(obj.requester_id):
            return False
        if obj.status != ApprovalStatusChoices.PENDING:
            return False
        return ApprovalService.is_platform_admin(user) or ApprovalService.has_permission(user, 'finance.payout')

    def get_can_execute(self, obj) -> bool:
        from apps.identity.models import ApprovalStatusChoices
        from apps.identity.approval_service import ApprovalService
        user = self._get_user()
        if not user:
            return False
        if obj.status != ApprovalStatusChoices.APPROVED:
            return False
        return ApprovalService.is_platform_admin(user) or ApprovalService.has_permission(user, 'finance.payout')

    def get_can_cancel(self, obj) -> bool:
        from apps.identity.models import ApprovalStatusChoices
        from apps.identity.approval_service import ApprovalService
        user = self._get_user()
        if not user:
            return False
        if obj.status != ApprovalStatusChoices.PENDING:
            return False
        return str(user.id) == str(obj.requester_id) or ApprovalService.is_platform_admin(user)


class ApprovalActionSerializer(serializers.Serializer):
    """Payload serializer for approval, rejection, and cancellation actions."""
    notes = serializers.CharField(required=False, allow_blank=True, default='')
    reason = serializers.CharField(required=False, allow_blank=True, default='')


class StaffRoleSerializer(serializers.ModelSerializer):
    """Serializer for staff roles and their granted permissions."""
    permissions = serializers.SerializerMethodField()

    class Meta:
        from apps.identity.models import StaffRole
        model = StaffRole
        fields = ['id', 'code', 'name', 'description', 'permissions']

    def get_permissions(self, obj):
        return list(obj.role_permissions.values_list('permission__code', flat=True))


class StaffMemberSerializer(serializers.ModelSerializer):
    """Serializer for platform staff directory listings and detailed management."""
    staff_role = serializers.SerializerMethodField()
    department = serializers.SerializerMethodField()
    has_mfa_enabled = serializers.SerializerMethodField()
    pending_invite = serializers.SerializerMethodField()
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'first_name',
            'last_name',
            'full_name',
            'phone_number',
            'status',
            'is_active',
            'is_staff',
            'is_superuser',
            'roles',
            'staff_role',
            'department',
            'has_mfa_enabled',
            'last_login',
            'date_joined',
            'created_at',
            'pending_invite',
        ]
        read_only_fields = fields

    def get_staff_role(self, obj):
        profile = getattr(obj, 'staff_profile', None)
        if profile and profile.staff_role:
            perms = list(profile.staff_role.role_permissions.values_list('permission__code', flat=True))
            return {
                'id': str(profile.staff_role.id),
                'code': profile.staff_role.code,
                'name': profile.staff_role.name,
                'description': profile.staff_role.description,
                'permissions': perms,
            }
        if obj.is_superuser or obj.has_role(RoleChoices.ADMIN):
            from apps.identity.models import Permission
            all_perms = list(Permission.objects.values_list('code', flat=True))
            return {
                'id': 'platform-admin',
                'code': 'ADMIN',
                'name': 'Platform Administrator',
                'description': 'Full administrative access across all operational queues',
                'permissions': all_perms,
            }
        return None

    def get_department(self, obj):
        profile = getattr(obj, 'staff_profile', None)
        return profile.department if profile else 'Operations'

    def get_has_mfa_enabled(self, obj):
        return bool(obj.has_mfa_enabled)

    def get_pending_invite(self, obj):
        from apps.identity.models import StaffInviteToken
        from django.utils import timezone
        invite = StaffInviteToken.objects.filter(user=obj, consumed_at__isnull=True).order_by('-created_at').first()
        if not invite:
            return None
        return {
            'id': str(invite.id),
            'created_at': invite.created_at,
            'expires_at': invite.expires_at,
            'is_expired': bool(invite.expires_at < timezone.now()),
        }


class StaffMemberUpdateSerializer(serializers.Serializer):
    """Payload validator for modifying a staff member's role, department, or account status."""
    staff_role = serializers.CharField(required=False, allow_blank=True)
    department = serializers.CharField(required=False, allow_blank=True)
    status = serializers.ChoiceField(
        choices=[AccountStatusChoices.ACTIVE, AccountStatusChoices.SUSPENDED],
        required=False,
    )

    def validate_staff_role(self, value):
        from apps.identity.models import StaffRole
        if not value:
            return value
        clean = value.strip().upper()
        if not StaffRole.objects.filter(code=clean).exists():
            raise serializers.ValidationError(f"Invalid staff role code '{value}'.")
        return clean


class StaffInvitationSerializer(serializers.ModelSerializer):
    """Serializer for displaying pending and historical staff invitations."""
    email = serializers.CharField(source='user.email', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    user_id = serializers.UUIDField(source='user.id', read_only=True)
    staff_role = serializers.SerializerMethodField()
    staff_role_name = serializers.SerializerMethodField()
    department = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    is_expired = serializers.SerializerMethodField()
    is_consumed = serializers.SerializerMethodField()

    class Meta:
        from apps.identity.models import StaffInviteToken
        model = StaffInviteToken
        fields = [
            'id',
            'user_id',
            'email',
            'first_name',
            'last_name',
            'staff_role',
            'staff_role_name',
            'department',
            'status',
            'is_expired',
            'is_consumed',
            'created_at',
            'expires_at',
            'consumed_at',
        ]

    def get_staff_role(self, obj):
        profile = getattr(obj.user, 'staff_profile', None)
        return profile.staff_role.code if (profile and profile.staff_role) else 'STAFF'

    def get_staff_role_name(self, obj):
        profile = getattr(obj.user, 'staff_profile', None)
        return profile.staff_role.name if (profile and profile.staff_role) else 'Staff Member'

    def get_department(self, obj):
        profile = getattr(obj.user, 'staff_profile', None)
        return profile.department if profile else 'Operations'

    def get_is_consumed(self, obj) -> bool:
        return obj.consumed_at is not None

    def get_is_expired(self, obj) -> bool:
        from django.utils import timezone
        return bool(obj.consumed_at is None and obj.expires_at < timezone.now())

    def get_status(self, obj) -> str:
        from django.utils import timezone
        if obj.consumed_at is not None:
            return "ACCEPTED"
        if obj.expires_at < timezone.now():
            return "EXPIRED"
        return "PENDING"


