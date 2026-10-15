from rest_framework import serializers
from .models import (
    Organisation,
    OrganisationMembership,
    OrganisationRoleChoices,
    OrganisationTypeChoices,
)
from apps.identity.models import User


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
    """Serializes organisation details with current user's membership context."""

    user_role = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = Organisation
        fields = [
            'id',
            'name',
            'slug',
            'type',
            'jurisdiction',
            'created_by',
            'is_active',
            'user_role',
            'member_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'slug', 'created_by', 'is_active', 'created_at', 'updated_at', 'user_role', 'member_count']

    def get_user_role(self, obj) -> str | None:
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            return obj.get_member_role(request.user)
        return None

    def get_member_count(self, obj) -> int:
        return obj.memberships.filter(is_active=True).count()

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
