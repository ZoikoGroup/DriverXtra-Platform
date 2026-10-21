from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
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

        # Enforce MFA for users who have MFA enabled
        if is_staff_or_admin and user.has_mfa_enabled:
            if not code:
                from django.core import signing
                pre_auth_token = signing.dumps({'user_id': str(user.id), 'action': 'mfa_login'}, salt='driverxtra.mfa')
                return {
                    'user': user,
                    'mfa_required': True,
                    'pre_auth_token': pre_auth_token,
                }
            else:
                if not user.staff_profile.verify_totp(code):
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
        if User.objects.filter(email=normalized).exists():
            raise serializers.ValidationError("A user with this email address already exists on the platform.")
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
