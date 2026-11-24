from decimal import Decimal
from rest_framework import serializers

from apps.organisations.models import Organisation
from apps.catalogue.models import PartCategory
from apps.marketplace.models import (
    SparePartListing,
    VehicleListing,
    DealerTier,
    DealerOrganisationProfile,
    DealerPricingRule,
    DealerPricingRuleTypeChoices,
)


class DealerTierSerializer(serializers.ModelSerializer):
    class Meta:
        model = DealerTier
        fields = [
            'id',
            'code',
            'name',
            'description',
            'default_discount_percentage',
            'priority',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class DealerOrganisationProfileSerializer(serializers.ModelSerializer):
    organisation_name = serializers.CharField(source='organisation.name', read_only=True)
    organisation_slug = serializers.CharField(source='organisation.slug', read_only=True)
    organisation_country = serializers.CharField(source='organisation.country', read_only=True)
    organisation_jurisdiction = serializers.CharField(source='organisation.jurisdiction', read_only=True)
    organisation_type = serializers.CharField(source='organisation.type', read_only=True)
    tier_details = DealerTierSerializer(source='tier', read_only=True)
    rejection_reason = serializers.CharField(read_only=True)
    application_data = serializers.SerializerMethodField()
    verified_by_name = serializers.SerializerMethodField()

    class Meta:
        model = DealerOrganisationProfile
        fields = [
            'id',
            'organisation',
            'organisation_name',
            'organisation_slug',
            'organisation_country',
            'organisation_jurisdiction',
            'organisation_type',
            'tier',
            'tier_details',
            'is_verified_dealer',
            'status',
            'custom_discount_cap',
            'notes',
            'rejection_reason',
            'application_data',
            'verified_at',
            'verified_by',
            'verified_by_name',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'verified_at', 'verified_by']

    def get_application_data(self, obj) -> dict:
        return obj.get_application_data()

    def get_verified_by_name(self, obj) -> str:
        if obj.verified_by:
            return getattr(obj.verified_by, 'full_name', '') or obj.verified_by.email
        return ''


class DealerPricingRuleSerializer(serializers.ModelSerializer):
    organisation_name = serializers.CharField(source='organisation.name', read_only=True)
    dealer_tier_code = serializers.CharField(source='dealer_tier.code', read_only=True)
    dealer_tier_name = serializers.CharField(source='dealer_tier.name', read_only=True)
    part_name = serializers.CharField(source='part_listing.name', read_only=True)
    vehicle_title = serializers.CharField(source='vehicle_listing.title', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model = DealerPricingRule
        fields = [
            'id',
            'name',
            'rule_type',
            'organisation',
            'organisation_name',
            'dealer_tier',
            'dealer_tier_code',
            'dealer_tier_name',
            'part_listing',
            'part_name',
            'vehicle_listing',
            'vehicle_title',
            'category',
            'category_name',
            'min_quantity',
            'max_quantity',
            'discount_percentage',
            'fixed_price',
            'currency',
            'priority',
            'start_date',
            'end_date',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        rule_type = attrs.get('rule_type', getattr(self.instance, 'rule_type', DealerPricingRuleTypeChoices.PERCENTAGE_DISCOUNT))
        discount_percentage = attrs.get('discount_percentage', getattr(self.instance, 'discount_percentage', Decimal('0.00')))
        fixed_price = attrs.get('fixed_price', getattr(self.instance, 'fixed_price', None))
        min_qty = attrs.get('min_quantity', getattr(self.instance, 'min_quantity', 1))
        max_qty = attrs.get('max_quantity', getattr(self.instance, 'max_quantity', None))

        if rule_type == DealerPricingRuleTypeChoices.PERCENTAGE_DISCOUNT:
            if discount_percentage is None or discount_percentage < Decimal('0.00') or discount_percentage > Decimal('100.00'):
                raise serializers.ValidationError({
                    'discount_percentage': 'Discount percentage must be between 0.00 and 100.00.'
                })
        elif rule_type == DealerPricingRuleTypeChoices.FIXED_PRICE:
            if fixed_price is None or fixed_price <= Decimal('0.00'):
                raise serializers.ValidationError({
                    'fixed_price': 'Fixed dealer price must be a positive decimal amount.'
                })

        if min_qty < 1:
            raise serializers.ValidationError({'min_quantity': 'Minimum quantity must be at least 1.'})

        if max_qty is not None and max_qty < min_qty:
            raise serializers.ValidationError({
                'max_quantity': f'Maximum quantity ({max_qty}) cannot be less than minimum quantity ({min_qty}).'
            })

        start_date = attrs.get('start_date', getattr(self.instance, 'start_date', None))
        end_date = attrs.get('end_date', getattr(self.instance, 'end_date', None))
        if start_date and end_date and end_date < start_date:
            raise serializers.ValidationError({
                'end_date': 'End date must be greater than or equal to start date.'
            })

        return attrs


class AssignDealerTierSerializer(serializers.Serializer):
    tier_code = serializers.CharField(max_length=50, required=True)
    status = serializers.ChoiceField(
        choices=['PENDING', 'ACTIVE', 'SUSPENDED', 'REJECTED'],
        default='ACTIVE',
    )
    is_verified = serializers.BooleanField(default=True)
    notes = serializers.CharField(required=False, allow_blank=True, default='')
    custom_discount_cap = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        allow_null=True,
    )


class DealerApplicationSubmitSerializer(serializers.Serializer):
    organisation_id = serializers.UUIDField(required=False, allow_null=True)
    company_registration_number = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    tax_id = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    website_url = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    contact_email = serializers.EmailField(required=False, allow_blank=True, default='')
    contact_phone = serializers.CharField(max_length=50, required=False, allow_blank=True, default='')
    notes = serializers.CharField(required=False, allow_blank=True, default='')
    requested_tier = serializers.CharField(max_length=50, required=False, default='STANDARD')


class DealerApplicationReviewSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['APPROVE', 'REJECT'], required=True)
    tier_code = serializers.CharField(max_length=50, required=False, default='STANDARD')
    rejection_reason = serializers.CharField(required=False, allow_blank=True, default='')
    admin_notes = serializers.CharField(required=False, allow_blank=True, default='')
    custom_discount_cap = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        allow_null=True,
    )

    def validate(self, attrs):
        action = attrs.get('action')
        rejection_reason = (attrs.get('rejection_reason') or '').strip()
        if action == 'REJECT' and not rejection_reason:
            raise serializers.ValidationError({
                'rejection_reason': 'A rejection reason is required when rejecting an application.'
            })
        return attrs


class B2BQuoteItemInputSerializer(serializers.Serializer):
    listing_id = serializers.UUIDField(required=True)
    quantity = serializers.IntegerField(min_value=1, default=1)


class B2BQuoteRequestSerializer(serializers.Serializer):
    items = B2BQuoteItemInputSerializer(many=True, required=True)
    organisation_id = serializers.UUIDField(required=False, allow_null=True)
    currency = serializers.CharField(max_length=10, required=False, allow_blank=True, default='')
    shipping_country = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
