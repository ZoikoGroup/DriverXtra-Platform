from rest_framework import serializers
from apps.marketplace.models import (
    VehicleListing,
    SparePartListing,
    ListingStatusChoices,
)
from apps.organisations.models import Organisation, OrganisationRoleChoices
from apps.catalogue.serializers import (
    VehicleMakeSerializer,
    VehicleModelSerializer,
    VehicleVariantSerializer,
    PartCategorySerializer,
)


class VehicleListingSellerSerializer(serializers.ModelSerializer):
    seller_name = serializers.CharField(source='seller.full_name', read_only=True)
    organisation_name = serializers.CharField(source='organisation.name', read_only=True, allow_null=True)
    make_name = serializers.CharField(source='make.name', read_only=True)
    model_name = serializers.CharField(source='model.name', read_only=True)
    variant_name = serializers.CharField(source='variant.display_name', read_only=True, allow_null=True)
    masked_vin = serializers.CharField(read_only=True)
    masked_registration = serializers.CharField(read_only=True)

    class Meta:
        model = VehicleListing
        fields = [
            'id',
            'seller',
            'seller_name',
            'organisation',
            'organisation_name',
            'title',
            'make',
            'make_name',
            'model',
            'model_name',
            'variant',
            'variant_name',
            'year',
            'registration_number',
            'vin',
            'masked_vin',
            'masked_registration',
            'mileage',
            'fuel_type',
            'transmission',
            'body_type',
            'price',
            'currency',
            'condition',
            'description',
            'primary_image_url',
            'images',
            'location_city',
            'location_postcode',
            'status',
            'rejection_reason',
            'admin_notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'seller',
            'seller_name',
            'status',
            'rejection_reason',
            'admin_notes',
            'created_at',
            'updated_at',
        ]

    def validate_organisation(self, value):
        if not value:
            return None
        user = self.context['request'].user
        # Platform staff/admins bypass
        if user.is_staff or user.has_role('ADMIN') or user.has_role('MARKETPLACE_ADMIN'):
            return value

        membership = value.memberships.filter(user=user, is_active=True).first()
        if not membership or membership.role not in (
            OrganisationRoleChoices.OWNER,
            OrganisationRoleChoices.ADMIN,
        ):
            raise serializers.ValidationError(
                "You are not authorized to create inventory for this organisation. "
                "Must be an active OWNER or ADMIN."
            )
        return value

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Asking price must be greater than zero.")
        return value

    def validate_year(self, value):
        if value < 1900 or value > 2050:
            raise serializers.ValidationError("Please provide a valid manufacturing year.")
        return value


class SparePartListingSellerSerializer(serializers.ModelSerializer):
    seller_name = serializers.CharField(source='seller.full_name', read_only=True)
    organisation_name = serializers.CharField(source='organisation.name', read_only=True, allow_null=True)
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model = SparePartListing
        fields = [
            'id',
            'seller',
            'seller_name',
            'organisation',
            'organisation_name',
            'name',
            'brand',
            'mpn',
            'oem_numbers',
            'category',
            'category_name',
            'description',
            'price',
            'currency',
            'stock_quantity',
            'condition',
            'primary_image_url',
            'images',
            'compatible_variants',
            'compatibility_notes',
            'status',
            'rejection_reason',
            'admin_notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'seller',
            'seller_name',
            'status',
            'rejection_reason',
            'admin_notes',
            'created_at',
            'updated_at',
        ]

    def validate_organisation(self, value):
        if not value:
            return None
        user = self.context['request'].user
        if user.is_staff or user.has_role('ADMIN') or user.has_role('MARKETPLACE_ADMIN'):
            return value

        membership = value.memberships.filter(user=user, is_active=True).first()
        if not membership or membership.role not in (
            OrganisationRoleChoices.OWNER,
            OrganisationRoleChoices.ADMIN,
        ):
            raise serializers.ValidationError(
                "You are not authorized to submit spare parts for this organisation. "
                "Must be an active OWNER or ADMIN."
            )
        return value

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Part price must be greater than zero.")
        return value

    def validate_stock_quantity(self, value):
        if value < 0:
            raise serializers.ValidationError("Available stock quantity cannot be negative.")
        return value


class ListingReviewSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=['APPROVE', 'REJECT', 'REQUEST_CHANGES'],
        help_text="Approval action: APPROVE, REJECT, or REQUEST_CHANGES"
    )
    rejection_reason = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Mandatory if action is REJECT or REQUEST_CHANGES"
    )
    admin_notes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        action = attrs.get('action')
        reason = attrs.get('rejection_reason', '').strip()
        if action in ('REJECT', 'REQUEST_CHANGES') and not reason:
            raise serializers.ValidationError({
                'rejection_reason': f"A clear reason is required when choosing {action}."
            })
        return attrs


class VehicleListingPublicSerializer(serializers.ModelSerializer):
    make_name = serializers.CharField(source='make.name', read_only=True)
    model_name = serializers.CharField(source='model.name', read_only=True)
    variant_details = VehicleVariantSerializer(source='variant', read_only=True)
    seller_name = serializers.CharField(source='seller.full_name', read_only=True)
    organisation_name = serializers.CharField(source='organisation.name', read_only=True, allow_null=True)
    masked_vin = serializers.CharField(read_only=True)
    masked_registration = serializers.CharField(read_only=True)

    class Meta:
        model = VehicleListing
        fields = [
            'id',
            'title',
            'make',
            'make_name',
            'model',
            'model_name',
            'variant',
            'variant_details',
            'year',
            'masked_vin',
            'masked_registration',
            'mileage',
            'fuel_type',
            'transmission',
            'body_type',
            'price',
            'currency',
            'condition',
            'description',
            'primary_image_url',
            'images',
            'location_city',
            'location_postcode',
            'seller_name',
            'organisation_name',
            'status',
            'created_at',
        ]


class SparePartListingPublicSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_slug = serializers.CharField(source='category.slug', read_only=True)
    seller_name = serializers.CharField(source='seller.full_name', read_only=True)
    organisation_name = serializers.CharField(source='organisation.name', read_only=True, allow_null=True)
    compatible_variants = VehicleVariantSerializer(many=True, read_only=True)

    class Meta:
        model = SparePartListing
        fields = [
            'id',
            'name',
            'brand',
            'mpn',
            'oem_numbers',
            'category',
            'category_name',
            'category_slug',
            'description',
            'price',
            'currency',
            'stock_quantity',
            'condition',
            'primary_image_url',
            'images',
            'compatible_variants',
            'compatibility_notes',
            'seller_name',
            'organisation_name',
            'status',
            'created_at',
        ]
