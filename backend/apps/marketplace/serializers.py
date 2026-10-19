from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from apps.marketplace.models import (
    VehicleListing,
    SparePartListing,
    StockMovement,
    StockMovementReasonChoices,
    PriceChange,
    ListingStatusChoices,
)
from apps.catalogue.models import Part
from apps.marketplace.services import change_price, _UNSET
from apps.organisations.models import Organisation, OrganisationRoleChoices
from apps.catalogue.serializers import (
    VehicleMakeSerializer,
    VehicleModelSerializer,
    VehicleVariantSerializer,
    PartCategorySerializer,
)


def compute_price_flags(listing):
    """Computes reviewer price flags for a spare part listing against comparable approved offers."""
    if not listing or not getattr(listing, 'catalogue_part_id', None):
        return {
            "flag": "INSUFFICIENT_COMPARABLES",
            "median": None,
            "comparable_count": 0,
            "deviation": None,
        }

    threshold = getattr(settings, 'PRICE_OUTLIER_THRESHOLD', Decimal('0.5'))
    if not isinstance(threshold, Decimal):
        threshold = Decimal(str(threshold))

    comparables_qs = SparePartListing.objects.filter(
        catalogue_part_id=listing.catalogue_part_id,
        currency=listing.currency,
        status=ListingStatusChoices.APPROVED,
        is_active=True,
    ).exclude(id=listing.id)

    prices = sorted([Decimal(str(p)) for p in comparables_qs.values_list('price', flat=True)])
    count = len(prices)

    if count == 0:
        return {
            "flag": "INSUFFICIENT_COMPARABLES",
            "median": None,
            "comparable_count": 0,
            "deviation": None,
        }

    mid = count // 2
    if count % 2 == 1:
        median = prices[mid]
    else:
        median = (prices[mid - 1] + prices[mid]) / Decimal('2')

    if median <= Decimal('0'):
        return {
            "flag": "MEDIAN_UNAVAILABLE",
            "median": median,
            "comparable_count": count,
            "deviation": None,
        }

    listing_price = Decimal(str(listing.price))
    deviation = abs(listing_price - median) / median

    if count < 3:
        flag = "INSUFFICIENT_COMPARABLES"
    elif deviation > threshold:
        flag = "OUTLIER_VS_MEDIAN"
    else:
        flag = None

    return {
        "flag": flag,
        "median": median,
        "comparable_count": count,
        "deviation": deviation,
    }


class VehicleListingSellerSerializer(serializers.ModelSerializer):
    seller_name = serializers.CharField(source='seller.full_name', read_only=True)
    organisation_name = serializers.CharField(source='organisation.name', read_only=True, allow_null=True)
    make_name = serializers.CharField(source='make.name', read_only=True)
    model_name = serializers.CharField(source='model.name', read_only=True)
    variant_name = serializers.CharField(source='variant.display_name', read_only=True, allow_null=True)
    masked_vin = serializers.CharField(read_only=True)
    masked_registration = serializers.CharField(read_only=True)
    reviewed_by_name = serializers.CharField(source='reviewed_by.full_name', read_only=True, allow_null=True)

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
            'reviewed_by',
            'reviewed_by_name',
            'reviewed_at',
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
            'reviewed_by',
            'reviewed_by_name',
            'reviewed_at',
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
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied(
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

    def validate(self, attrs):
        make = attrs.get('make')
        model = attrs.get('model')
        if make and model and model.make_id != make.id:
            raise serializers.ValidationError({"model": "Selected model does not belong to the selected vehicle make."})
        variant = attrs.get('variant')
        if variant and model and variant.model_id != model.id:
            raise serializers.ValidationError({"variant": "Selected variant does not belong to the selected vehicle model."})
        return attrs


class SparePartListingSellerSerializer(serializers.ModelSerializer):
    seller_name = serializers.CharField(source='seller.full_name', read_only=True)
    organisation_name = serializers.CharField(source='organisation.name', read_only=True, allow_null=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    catalogue_part_name = serializers.CharField(source='catalogue_part.name', read_only=True, allow_null=True)
    reviewed_by_name = serializers.CharField(source='reviewed_by.full_name', read_only=True, allow_null=True)
    availability = serializers.SerializerMethodField()
    price_flags = serializers.SerializerMethodField(read_only=True)
    catalogue_part = serializers.PrimaryKeyRelatedField(
        queryset=Part.objects.all(),
        required=False,
        allow_null=True,
    )
    compare_at_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        allow_null=True,
    )

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
            'catalogue_part',
            'catalogue_part_name',
            'description',
            'price',
            'compare_at_price',
            'price_flags',
            'currency',
            'stock_quantity',
            'low_stock_threshold',
            'availability',
            'condition',
            'primary_image_url',
            'images',
            'compatible_variants',
            'compatibility_notes',
            'status',
            'reviewed_by',
            'reviewed_by_name',
            'reviewed_at',
            'rejection_reason',
            'admin_notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'seller',
            'seller_name',
            'catalogue_part_name',
            'price_flags',
            'status',
            'reviewed_by',
            'reviewed_by_name',
            'reviewed_at',
            'rejection_reason',
            'admin_notes',
            'created_at',
            'updated_at',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance is not None and 'stock_quantity' in self.fields:
            self.fields['stock_quantity'].read_only = True

    def get_availability(self, obj) -> str:
        if obj.stock_quantity == 0:
            return 'OUT_OF_STOCK'
        if obj.stock_quantity <= obj.low_stock_threshold:
            return 'LOW_STOCK'
        return 'IN_STOCK'

    def get_price_flags(self, obj) -> dict:
        return compute_price_flags(obj)

    def validate(self, attrs):
        if self.instance is not None:
            initial_data = getattr(self, 'initial_data', {})
            if 'stock_quantity' in initial_data:
                raise serializers.ValidationError({
                    'stock_quantity': (
                        "Direct modification of stock_quantity via update is disabled. "
                        "Please use the dedicated stock adjustment endpoint: POST /api/v1/marketplace/parts/<id>/stock/."
                    )
                })

        price = attrs.get('price')
        if price is None and self.instance:
            price = self.instance.price

        compare_at = attrs.get('compare_at_price')
        if compare_at is None and self.instance and 'compare_at_price' not in getattr(self, 'initial_data', {}):
            compare_at = self.instance.compare_at_price

        if compare_at is not None and price is not None:
            if Decimal(str(compare_at)) <= Decimal(str(price)):
                raise serializers.ValidationError({
                    'compare_at_price': "Compare-at price must be strictly greater than retail price."
                })

        return attrs

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
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied(
                "You are not authorized to submit spare parts for this organisation. "
                "Must be an active OWNER or ADMIN."
            )
        return value

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Part price must be greater than zero.")
        max_price = getattr(settings, 'MAX_LISTING_PRICE', Decimal('100000'))
        if not isinstance(max_price, Decimal):
            max_price = Decimal(str(max_price))
        if value > max_price:
            raise serializers.ValidationError(
                f"Part price cannot exceed maximum allowable listing price of £{max_price}."
            )
        return value

    def validate_compare_at_price(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Compare-at price must be greater than zero.")
        return value

    def validate_catalogue_part(self, value):
        if value is not None and not value.is_active:
            raise serializers.ValidationError("Only active catalogue parts may be linked to marketplace listings.")
        return value

    def validate_stock_quantity(self, value):
        if value < 0:
            raise serializers.ValidationError("Available stock quantity cannot be negative.")
        return value

    def validate_low_stock_threshold(self, value):
        if value < 0:
            raise serializers.ValidationError("Low stock threshold cannot be negative.")
        return value

    def update(self, instance, validated_data):
        has_price = 'price' in validated_data
        new_price = validated_data.pop('price', None)

        initial_data = getattr(self, 'initial_data', {})
        has_compare_at = 'compare_at_price' in validated_data or 'compare_at_price' in initial_data
        new_compare_at = validated_data.pop('compare_at_price', None)

        request = self.context.get('request')
        actor = getattr(request, 'user', None) if request and getattr(request, 'user', None) and request.user.is_authenticated else None
        price_note = validated_data.pop('price_note', '') or ''

        with transaction.atomic():
            locked_instance = SparePartListing.objects.select_for_update().get(pk=instance.pk)

            target_price = new_price if has_price else locked_instance.price
            target_compare_at = new_compare_at if has_compare_at else locked_instance.compare_at_price

            price_changed = has_price and (Decimal(str(target_price)) != locked_instance.price)
            compare_at_changed = has_compare_at and (
                (target_compare_at is None and locked_instance.compare_at_price is not None) or
                (target_compare_at is not None and (locked_instance.compare_at_price is None or Decimal(str(target_compare_at)) != locked_instance.compare_at_price))
            )
            pricing_changed = price_changed or compare_at_changed

            catalogue_part_changed = False
            if 'catalogue_part' in validated_data:
                new_cat_part = validated_data['catalogue_part']
                if locked_instance.catalogue_part != new_cat_part:
                    catalogue_part_changed = True

            material_fields = {
                'description', 'name', 'brand', 'mpn', 'oem_numbers',
                'category', 'images', 'primary_image_url',
                'condition', 'compatible_variants'
            }
            other_material_changed = False
            for field in material_fields:
                if field in validated_data and getattr(locked_instance, field, None) != validated_data[field]:
                    other_material_changed = True
                    break

            # Save non-price fields ONCE via super().update()
            instance = super().update(instance, validated_data)

            if pricing_changed:
                change_price(
                    listing=instance,
                    new_price=target_price if has_price else None,
                    new_compare_at_price=target_compare_at if has_compare_at else _UNSET,
                    actor=actor,
                    note=price_note,
                )
            else:
                if instance.status == ListingStatusChoices.APPROVED and (catalogue_part_changed or other_material_changed):
                    instance.status = ListingStatusChoices.PENDING_APPROVAL
                    instance.rejection_reason = ""
                    instance.submitted_at = timezone.now()
                    instance.save(update_fields=['status', 'rejection_reason', 'submitted_at', 'updated_at'])

            return instance


class StockMovementSerializer(serializers.ModelSerializer):
    """Serializer for immutable stock movement records."""
    actor_name = serializers.CharField(source='actor.full_name', read_only=True, allow_null=True)

    class Meta:
        model = StockMovement
        fields = [
            'id',
            'listing',
            'delta',
            'resulting_quantity',
            'reason',
            'actor',
            'actor_name',
            'note',
            'created_at',
        ]
        read_only_fields = fields


class StockAdjustmentSerializer(serializers.Serializer):
    """Serializer for requesting manual stock adjustments."""
    delta = serializers.IntegerField(required=True)
    reason = serializers.ChoiceField(
        choices=[
            ('ADJUSTMENT', 'Manual Adjustment'),
            ('CORRECTION', 'Inventory Audit / Correction'),
        ],
        required=True,
        error_messages={
            'invalid_choice': "Reason must be either 'ADJUSTMENT' or 'CORRECTION'. 'INITIAL', 'SALE', and 'RETURN' cannot be submitted to this endpoint."
        }
    )
    note = serializers.CharField(required=False, allow_blank=True, default='')

    def validate_delta(self, value):
        if value == 0:
            raise serializers.ValidationError("Stock adjustment delta cannot be zero.")
        return value

    def validate_reason(self, value):
        if value not in ('ADJUSTMENT', 'CORRECTION'):
            raise serializers.ValidationError(
                f"Reason '{value}' is not allowed for manual stock adjustments. Must be 'ADJUSTMENT' or 'CORRECTION'."
            )
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
    availability = serializers.SerializerMethodField()

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
            'catalogue_part',
            'description',
            'price',
            'compare_at_price',
            'currency',
            'stock_quantity',
            'low_stock_threshold',
            'availability',
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

    def get_availability(self, obj) -> str:
        if obj.stock_quantity == 0:
            return 'OUT_OF_STOCK'
        if obj.stock_quantity <= obj.low_stock_threshold:
            return 'LOW_STOCK'
        return 'IN_STOCK'


class CataloguePartOfferSerializer(serializers.ModelSerializer):
    """Public serializer for competitive offers on a specific canonical catalogue part."""
    seller_name = serializers.CharField(source='seller.full_name', read_only=True)
    organisation_name = serializers.CharField(source='organisation.name', read_only=True, allow_null=True)
    availability = serializers.SerializerMethodField()
    is_available = serializers.SerializerMethodField()

    class Meta:
        model = SparePartListing
        fields = [
            'id',
            'price',
            'compare_at_price',
            'currency',
            'condition',
            'stock_quantity',
            'low_stock_threshold',
            'availability',
            'is_available',
            'seller_name',
            'organisation_name',
            'primary_image_url',
            'created_at',
        ]

    def get_availability(self, obj) -> str:
        if obj.stock_quantity == 0:
            return 'OUT_OF_STOCK'
        if obj.stock_quantity <= obj.low_stock_threshold:
            return 'LOW_STOCK'
        return 'IN_STOCK'

    def get_is_available(self, obj) -> bool:
        return obj.stock_quantity > 0 and self.get_availability(obj) != 'OUT_OF_STOCK'


class PriceChangeSerializer(serializers.ModelSerializer):
    """Serializer for immutable price modification audit trail."""
    actor_name = serializers.CharField(source='actor.full_name', read_only=True, allow_null=True)

    class Meta:
        model = PriceChange
        fields = [
            'id',
            'listing',
            'old_price',
            'new_price',
            'old_compare_at_price',
            'new_compare_at_price',
            'actor',
            'actor_name',
            'note',
            'created_at',
        ]
        read_only_fields = fields


class AdminPartListingReviewSerializer(SparePartListingSellerSerializer):
    """Admin review serializer for spare part listings with computed price flags."""
    price_flags = serializers.SerializerMethodField()

    class Meta(SparePartListingSellerSerializer.Meta):
        fields = SparePartListingSellerSerializer.Meta.fields

    def get_price_flags(self, obj) -> dict:
        return compute_price_flags(obj)


PartListingReviewSerializer = AdminPartListingReviewSerializer
