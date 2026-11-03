from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError
from .models import (
    Organisation,
    OrganisationMembership,
    OrganisationRoleChoices,
    OrganisationTypeChoices,
)
from apps.identity.models import User
from platform_core.regional import (
    CountryCode,
    validate_country_code,
    validate_jurisdiction,
    derive_country_from_jurisdiction,
    get_default_jurisdiction_for_country,
    get_default_currency_for_country,
    get_default_odometer_unit_for_country,
    get_country_spec,
    is_supported_country,
)


class OrganisationMemberSerializer(serializers.ModelSerializer):
    """Serializes organisation membership details."""

    user_id = serializers.UUIDField(source='user.id', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    full_name = serializers.CharField(source='user.full_name', read_only=True)

    class Meta:
        model = OrganisationMembership
        fields = [
            'id',
            'user_id',
            'email',
            'full_name',
            'role',
            'is_active',
            'joined_at',
        ]
        read_only_fields = ['id', 'user_id', 'email', 'full_name', 'joined_at']


class OrganisationSerializer(serializers.ModelSerializer):
    """Serializes organisation details with current user's membership and regional context."""

    user_role = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()
    default_currency = serializers.SerializerMethodField()
    default_odometer_unit = serializers.SerializerMethodField()
    tax_scheme = serializers.SerializerMethodField()
    subdivision_name = serializers.SerializerMethodField()
    gst_state_code = serializers.SerializerMethodField()

    country = serializers.CharField(
        max_length=2,
        required=False,
        help_text="Authoritative ISO 3166-1 alpha-2 country code (e.g. IN, GB).",
    )
    jurisdiction = serializers.CharField(
        max_length=50,
        required=False,
        help_text="Authoritative ISO 3166-2 legal jurisdiction (e.g. IN-TG, GB-ENG).",
    )

    class Meta:
        model = Organisation
        fields = [
            'id',
            'name',
            'slug',
            'type',
            'country',
            'jurisdiction',
            'created_by',
            'is_active',
            'user_role',
            'member_count',
            'default_currency',
            'default_odometer_unit',
            'tax_scheme',
            'subdivision_name',
            'gst_state_code',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'slug',
            'created_by',
            'is_active',
            'created_at',
            'updated_at',
            'user_role',
            'member_count',
            'default_currency',
            'default_odometer_unit',
            'tax_scheme',
            'subdivision_name',
            'gst_state_code',
        ]

    def get_user_role(self, obj) -> str | None:
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            return obj.get_member_role(request.user)
        return None

    def get_member_count(self, obj) -> int:
        return obj.memberships.filter(is_active=True).count()

    def get_default_currency(self, obj) -> str:
        return get_default_currency_for_country(obj.country)

    def get_default_odometer_unit(self, obj) -> str:
        return get_default_odometer_unit_for_country(obj.country)

    def get_tax_scheme(self, obj) -> str:
        spec = get_country_spec(obj.country)
        return spec.tax_config.tax_scheme.value

    def get_subdivision_name(self, obj) -> str | None:
        sub = obj.subdivision_specification
        return sub.name if sub else None

    def get_gst_state_code(self, obj) -> str | None:
        sub = obj.subdivision_specification
        return sub.gst_state_code if sub else None

    def validate_type(self, value):
        if value == OrganisationTypeChoices.INTERNAL_OPS:
            request = self.context.get('request')
            user = request.user if request else None
            is_admin = user and (user.is_superuser or user.has_role('ADMIN'))
            if not is_admin:
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied("Only platform administrators may create Internal Operations organisations.")
        return value

    def validate(self, attrs):
        instance = getattr(self, 'instance', None)

        # Determine target country
        country = attrs.get('country')
        if not country and instance:
            country = instance.country

        # Determine target jurisdiction
        jurisdiction = attrs.get('jurisdiction')
        if not jurisdiction and instance:
            jurisdiction = instance.jurisdiction

        # Harmonize country and jurisdiction
        if jurisdiction and not country:
            country = derive_country_from_jurisdiction(jurisdiction)
        elif country and not jurisdiction:
            if is_supported_country(country):
                jurisdiction = get_default_jurisdiction_for_country(country)

        # Fallback to GB default ONLY if neither country nor jurisdiction were specified at all
        if not country and not jurisdiction:
            country = CountryCode.GB.value
            jurisdiction = 'GB-ENG'

        # Validate with authoritative regional validator
        try:
            valid_country = validate_country_code(country)
            valid_jurisdiction = validate_jurisdiction(valid_country, jurisdiction)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'country_or_jurisdiction': str(exc.message if hasattr(exc, 'message') else exc)})

        attrs['country'] = valid_country
        attrs['jurisdiction'] = valid_jurisdiction
        return attrs

    def create(self, validated_data):
        user = self.context['request'].user
        validated_data['created_by'] = user
        organisation = Organisation.objects.create(**validated_data)

        # The creator automatically receives the OWNER role
        OrganisationMembership.objects.create(
            organisation=organisation,
            user=user,
            role=OrganisationRoleChoices.OWNER,
            is_active=True,
        )
        return organisation


class AddMemberSerializer(serializers.Serializer):
    """Validates inputs for adding or inviting a user to an organisation."""

    email = serializers.EmailField(required=True)
    role = serializers.ChoiceField(
        choices=OrganisationRoleChoices.choices,
        default=OrganisationRoleChoices.MEMBER,
    )

    def validate_email(self, value):
        normalized = value.strip().lower()
        if not User.objects.filter(email=normalized).exists():
            raise serializers.ValidationError("User with this email address does not exist on the platform.")
        return normalized

    def validate_role(self, value):
        if value == OrganisationRoleChoices.OWNER:
            raise serializers.ValidationError("Cannot assign OWNER role directly. Ownership must be transferred.")
        return value
