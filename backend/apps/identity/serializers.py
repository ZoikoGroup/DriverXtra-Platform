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
            'created_at',
        ]
        read_only_fields = ['id', 'status', 'created_at']

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
        """Enforces restriction preventing public users from granting themselves staff or admin privileges."""
        if not value:
            return [RoleChoices.BUYER]

        normalized_roles = []
        for r in value:
            norm = RoleChoices.normalize_role(r)
            if norm in RESTRICTED_PUBLIC_ROLES or r.strip().upper() in RESTRICTED_PUBLIC_ROLES:
                raise serializers.ValidationError(
                    f"Self-assignment of staff or administrative role '{r}' is prohibited for public registration."
                )
            if norm not in [RoleChoices.BUYER, RoleChoices.SELLER, RoleChoices.WORKSHOP]:
                raise serializers.ValidationError(f"Invalid platform role: '{r}'.")
            if norm not in normalized_roles:
                normalized_roles.append(norm)

        return normalized_roles

    def create(self, validated_data):
        roles = validated_data.pop('roles', [RoleChoices.BUYER])
        password = validated_data.pop('password')

        user = User.objects.create_user(
            password=password,
            status=AccountStatusChoices.ACTIVE,
            **validated_data
        )

        for role in roles:
            user.add_role(role)

        return user


class UserLoginSerializer(serializers.Serializer):
    """Serializer for authenticating users and issuing JWT access/refresh tokens."""

    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True, write_only=True, style={'input_type': 'password'})

    def validate(self, attrs):
        email = attrs.get('email', '').strip().lower()
        password = attrs.get('password', '')

        user = User.objects.filter(email=email).first()

        if user is None or not user.check_password(password):
            raise serializers.ValidationError("Invalid email or password.")

        if not user.is_active or user.status != AccountStatusChoices.ACTIVE:
            raise serializers.ValidationError(
                f"Account is currently {user.status.lower()}. Please contact support."
            )

        # Generate SimpleJWT tokens with custom claims
        refresh = RefreshToken.for_user(user)
        refresh['email'] = user.email
        refresh['roles'] = user.roles
        refresh['full_name'] = user.full_name

        return {
            'user': user,
            'tokens': {
                'access': str(refresh.access_token),
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
            'roles',
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
            'roles',
            'is_staff',
            'is_superuser',
            'organisations',
            'date_joined',
            'created_at',
            'updated_at',
        ]

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
