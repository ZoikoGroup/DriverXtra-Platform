from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from apps.marketplace.models import (
    BulkUploadJob,
    BulkUploadRowError,
    BulkUploadTypeChoices,
    BulkUploadStatusChoices,
    BulkUploadDuplicatePolicy,
    VehicleListing,
    SparePartListing,
    StockMovement,
    StockMovementReasonChoices,
    PriceChange,
    ListingStatusChoices,
    BuyerFavouriteVehicle,
    BuyerFavouritePart,
    Order,
    OrderItem,
    OrderStatusChoices,
    PaymentMethodChoices,
    PaymentStatusChoices,
    CODCollectionStatusChoices,
    VehicleEnquiry,
    VehicleEnquiryStatusChoices,
    Shipment,
    ShipmentItem,
    TrackingEvent,
    CarrierChoices,
    ShipmentStatusChoices,
    ReturnRequest,
    ReturnRequestTypeChoices,
    ReturnRequestStatusChoices,
    ReturnReasonChoices,
    Refund,
    RefundStatusChoices,
    RefundMethodChoices,
    Dispute,
    DisputeCategoryChoices,
    DisputeStatusChoices,
    DisputeResolutionChoices,
    DisputePriorityChoices,
    DisputeEvent,
    DisputeEventTypeChoices,
    ProductReview,
    SellerReview,
    ReviewReport,
    ReviewStatusChoices,
    ReviewReportReasonChoices,
    ReviewReportStatusChoices,
    ReviewReportActionChoices,
    VehiclePurchaseOffer,
    VehicleOfferProposal,
    VehicleOfferAction,
    VehicleOrder,
    VehicleOfferStatusChoices,
    VehicleHandoverTypeChoices,
    VehicleOrderStatusChoices,
    VehiclePaymentReport,
    VehiclePaymentReportStatusChoices,
    VehiclePaymentEscalationLevelChoices,
    VehiclePaymentVerificationEvent,
    VehiclePaymentVerificationEventTypeChoices,
    VehicleListingAvailabilityChoices,
    VehiclePurchaseDocument,
    VehicleDocumentReviewEvent,
    VehicleDocumentCategoryChoices,
    VehicleDocumentOwnerRoleChoices,
    VehicleDocumentStatusChoices,
    VehicleDocumentReviewEventTypeChoices,
)
from apps.catalogue.models import Part
from apps.marketplace.services import change_price, _UNSET, get_seller_public_info
from apps.marketplace.fitment import (
    evaluate_listing_fitment,
    get_conflicting_variants,
    evaluate_listing_single_variant,
)
from apps.marketplace.tax import (
    validate_gst_classification,
    get_official_hsn_entry,
    resolve_default_hsn_for_category,
    calculate_gst_breakdown,
)
from platform_core.audit.writer import record_denied_audit_entry
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import URLValidator
from apps.organisations.models import Organisation, OrganisationRoleChoices
from apps.catalogue.serializers import (
    VehicleMakeSerializer,
    VehicleModelSerializer,
    VehicleVariantSerializer,
    PartCategorySerializer,
    validate_image_url_list,
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
    primary_image_url = serializers.CharField(required=False, allow_blank=True)

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

    def validate_primary_image_url(self, value):
        if not value:
            return ""
        val = value.strip()
        if not (val.startswith('/media/') or val.startswith('/static/')):
            validator = URLValidator()
            try:
                validator(val)
            except DjangoValidationError:
                raise serializers.ValidationError(f"Primary image URL is not a valid URL: '{value}'.")
        return val

    def validate_images(self, value):
        return validate_image_url_list(value, max_count=10)

    def validate(self, attrs):
        make = attrs.get('make')
        model = attrs.get('model')
        if make and model and model.make_id != make.id:
            raise serializers.ValidationError({"model": "Selected model does not belong to the selected vehicle make."})
        variant = attrs.get('variant')
        if variant and model and variant.model_id != model.id:
            raise serializers.ValidationError({"variant": "Selected variant does not belong to the selected vehicle model."})

        # Sync primary image and images
        primary = attrs.get('primary_image_url', getattr(self.instance, 'primary_image_url', ''))
        imgs = attrs.get('images', getattr(self.instance, 'images', []))
        if not primary and imgs:
            attrs['primary_image_url'] = imgs[0]
        elif primary and primary not in imgs and len(imgs) < 10:
            attrs['images'] = [primary] + [i for i in imgs if i != primary]

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
    fitment_verification = serializers.SerializerMethodField(read_only=True)
    fitment_summary = serializers.SerializerMethodField(read_only=True)
    primary_image_url = serializers.CharField(required=False, allow_blank=True)

    # Tax & HSN fields (Indian GST compliance)
    hsn_code = serializers.CharField(required=False, allow_blank=True, default='')
    gst_rate = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)
    is_tax_verified = serializers.BooleanField(read_only=True)
    price_before_gst = serializers.DecimalField(source='price', max_digits=10, decimal_places=2, read_only=True)
    gst_amount = serializers.SerializerMethodField(read_only=True)
    total_price = serializers.SerializerMethodField(read_only=True)
    tax_breakdown = serializers.SerializerMethodField(read_only=True)

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
            'hsn_code',
            'gst_rate',
            'is_tax_verified',
            'price_before_gst',
            'gst_amount',
            'total_price',
            'tax_breakdown',
            'price_flags',
            'currency',
            'country_prices',
            'stock_quantity',
            'low_stock_threshold',
            'availability',
            'condition',
            'primary_image_url',
            'images',
            'compatible_variants',
            'compatibility_notes',
            'fitment_verification',
            'fitment_summary',
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
            'fitment_verification',
            'fitment_summary',
            'is_tax_verified',
            'price_before_gst',
            'gst_amount',
            'total_price',
            'tax_breakdown',
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

    def _get_evaluations(self, obj):
        if not hasattr(obj, '_cached_fitment_evals'):
            variants = list(obj.compatible_variants.all())
            obj._cached_fitment_evals = evaluate_listing_fitment(obj, variants)
        return obj._cached_fitment_evals

    def get_fitment_verification(self, obj):
        return self._get_evaluations(obj)

    def get_fitment_summary(self, obj):
        evals = self._get_evaluations(obj)
        counts = {
            "verified": 0,
            "conditional": 0,
            "seller_claimed": 0,
            "conflict": 0,
        }
        for item in evals:
            st = item.get("status")
            if st == "VERIFIED":
                counts["verified"] += 1
            elif st == "CONDITIONAL":
                counts["conditional"] += 1
            elif st == "SELLER_CLAIMED":
                counts["seller_claimed"] += 1
            elif st == "CONFLICT":
                counts["conflict"] += 1
        return counts

    def get_availability(self, obj) -> str:
        if obj.stock_quantity == 0:
            return 'OUT_OF_STOCK'
        if obj.stock_quantity <= obj.low_stock_threshold:
            return 'LOW_STOCK'
        return 'IN_STOCK'

    def get_price_flags(self, obj) -> dict:
        return compute_price_flags(obj)

    def get_gst_amount(self, obj) -> Decimal:
        return obj.gst_amount

    def get_total_price(self, obj) -> Decimal:
        return obj.total_price

    def get_tax_breakdown(self, obj) -> dict:
        return obj.tax_breakdown

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

        # GST classification & rate validation
        if self.instance is None:
            # Creation mode: provide smart defaults if not supplied
            hsn = attrs.get('hsn_code')
            rate = attrs.get('gst_rate')
            cat = attrs.get('category')
            cat_name = getattr(cat, 'name', '') if cat else ''
            part_name = attrs.get('name', '')

            if not hsn and rate is None:
                default_hsn, default_rate = resolve_default_hsn_for_category(cat_name, part_name)
                attrs['hsn_code'] = default_hsn
                attrs['gst_rate'] = default_rate
                attrs['is_tax_verified'] = True
            elif hsn and rate is None:
                entry = get_official_hsn_entry(hsn)
                if entry:
                    attrs['gst_rate'] = entry['standard_rate']
                    attrs['is_tax_verified'] = entry['is_verified']
                else:
                    attrs['gst_rate'] = Decimal("18.00")
                    attrs['is_tax_verified'] = False
            else:
                is_valid, err_msg, is_verified = validate_gst_classification(hsn, rate)
                if not is_valid:
                    raise serializers.ValidationError({
                        'gst_rate': err_msg or "Invalid GST rate for specified HSN classification."
                    })
                attrs['is_tax_verified'] = is_verified
        else:
            # Update mode: only process tax fields if explicitly supplied in the request payload
            has_hsn_input = 'hsn_code' in getattr(self, 'initial_data', {})
            has_rate_input = 'gst_rate' in getattr(self, 'initial_data', {})
            if has_hsn_input or has_rate_input:
                effective_hsn = attrs.get('hsn_code', self.instance.hsn_code)
                effective_rate = attrs.get('gst_rate', self.instance.gst_rate)
                cat = attrs.get('category') or getattr(self.instance, 'category', None)
                cat_name = getattr(cat, 'name', '') if cat else ''
                part_name = attrs.get('name') or getattr(self.instance, 'name', '')

                if not effective_hsn and effective_rate is None:
                    default_hsn, default_rate = resolve_default_hsn_for_category(cat_name, part_name)
                    attrs['hsn_code'] = default_hsn
                    attrs['gst_rate'] = default_rate
                    attrs['is_tax_verified'] = True
                elif effective_hsn and effective_rate is None:
                    entry = get_official_hsn_entry(effective_hsn)
                    if entry:
                        attrs['gst_rate'] = entry['standard_rate']
                        attrs['is_tax_verified'] = entry['is_verified']
                    else:
                        attrs['gst_rate'] = Decimal("18.00")
                        attrs['is_tax_verified'] = False
                else:
                    is_valid, err_msg, is_verified = validate_gst_classification(effective_hsn, effective_rate)
                    if not is_valid:
                        raise serializers.ValidationError({
                            'gst_rate': err_msg or "Invalid GST rate for specified HSN classification."
                        })
                    attrs['is_tax_verified'] = is_verified

        # Sync primary image and images
        primary = attrs.get('primary_image_url', getattr(self.instance, 'primary_image_url', ''))
        imgs = attrs.get('images', getattr(self.instance, 'images', []))
        if not primary and imgs:
            attrs['primary_image_url'] = imgs[0]
        elif primary and primary not in imgs and len(imgs) < 10:
            attrs['images'] = [primary] + [i for i in imgs if i != primary]

        return attrs

    def validate_primary_image_url(self, value):
        if not value:
            return ""
        val = value.strip()
        if not (val.startswith('/media/') or val.startswith('/static/')):
            validator = URLValidator()
            try:
                validator(val)
            except DjangoValidationError:
                raise serializers.ValidationError(f"Primary image URL is not a valid URL: '{value}'.")
        return val

    def validate_images(self, value):
        return validate_image_url_list(value, max_count=10)

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
                'condition', 'compatible_variants',
                'hsn_code', 'gst_rate'
            }
            other_material_changed = False
            for field in material_fields:
                if field in validated_data and getattr(locked_instance, field, None) != validated_data[field]:
                    other_material_changed = True
                    break

            # Part C: Submission gate on APPROVED listing material-edits introducing CONFLICT
            if locked_instance.status == ListingStatusChoices.APPROVED:
                target_cat_part = validated_data.get('catalogue_part', locked_instance.catalogue_part)
                target_variants = validated_data.get(
                    'compatible_variants',
                    list(locked_instance.compatible_variants.all())
                )
                conflicts = get_conflicting_variants(target_cat_part, target_variants)
                if conflicts:
                    corr_id = getattr(request, 'correlation_id', '') if request else ''
                    record_denied_audit_entry(
                        action="listing:submit",
                        resource_type="SparePartListing",
                        resource_id=str(locked_instance.id),
                        reason_code="FITMENT_CONFLICT",
                        correlation_id=corr_id,
                        actor_id=getattr(actor, 'id', None),
                        metadata={
                            "listing_id": str(locked_instance.id),
                            "conflicting_variant_ids": [c["variant_id"] for c in conflicts],
                        },
                    )
                    raise serializers.ValidationError({
                        "compatible_variants": "Listing contains compatible variants that conflict with catalogue records (DOES_NOT_FIT).",
                        "conflicts": conflicts,
                    })

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
    seller_info = serializers.SerializerMethodField()

    def get_seller_info(self, obj):
        return get_seller_public_info(obj)

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
            'seller_info',
            'status',
            'availability_status',
            'created_at',
        ]


class SparePartListingPublicSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_slug = serializers.CharField(source='category.slug', read_only=True)
    seller_id = serializers.UUIDField(source='seller.id', read_only=True)
    seller_name = serializers.CharField(source='seller.full_name', read_only=True)
    organisation_name = serializers.CharField(source='organisation.name', read_only=True, allow_null=True)
    compatible_variants = VehicleVariantSerializer(many=True, read_only=True)
    availability = serializers.SerializerMethodField()
    fitment = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()
    seller_rating = serializers.SerializerMethodField()

    # Tax & GST Transparency
    hsn_code = serializers.CharField(read_only=True)
    gst_rate = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    is_tax_verified = serializers.BooleanField(read_only=True)
    price_before_gst = serializers.DecimalField(source='price', max_digits=10, decimal_places=2, read_only=True)
    gst_amount = serializers.SerializerMethodField(read_only=True)
    total_price = serializers.SerializerMethodField(read_only=True)
    tax_breakdown = serializers.SerializerMethodField(read_only=True)
    dealer_pricing = serializers.SerializerMethodField(read_only=True)

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
            'hsn_code',
            'gst_rate',
            'is_tax_verified',
            'price_before_gst',
            'gst_amount',
            'total_price',
            'tax_breakdown',
            'dealer_pricing',
            'currency',
            'country_prices',
            'stock_quantity',
            'low_stock_threshold',
            'availability',
            'fitment',
            'condition',
            'primary_image_url',
            'images',
            'compatible_variants',
            'compatibility_notes',
            'seller_id',
            'seller_name',
            'organisation_name',
            'rating',
            'review_count',
            'seller_rating',
            'status',
            'created_at',
        ]

    def get_rating(self, obj) -> float:
        if hasattr(obj, 'approved_avg_rating'):
            return round(float(obj.approved_avg_rating or 0.0), 1)
        from django.db.models import Avg
        avg = obj.reviews.filter(status=ReviewStatusChoices.APPROVED).aggregate(Avg('rating'))['rating__avg']
        return round(float(avg or 0.0), 1)

    def get_review_count(self, obj) -> int:
        if hasattr(obj, 'approved_review_count'):
            return int(obj.approved_review_count or 0)
        return obj.reviews.filter(status=ReviewStatusChoices.APPROVED).count()

    def get_seller_rating(self, obj) -> float:
        if hasattr(obj, 'approved_seller_avg_rating'):
            return round(float(obj.approved_seller_avg_rating or 0.0), 1)
        if not obj.seller_id:
            return 0.0
        from django.db.models import Avg
        avg = SellerReview.objects.filter(
            seller_id=obj.seller_id,
            status=ReviewStatusChoices.APPROVED,
        ).aggregate(Avg('rating'))['rating__avg']
        return round(float(avg or 0.0), 1)

    def get_gst_amount(self, obj) -> Decimal:
        return obj.gst_amount

    def get_total_price(self, obj) -> Decimal:
        return obj.total_price

    def get_tax_breakdown(self, obj) -> dict:
        return obj.tax_breakdown

    def get_availability(self, obj) -> str:
        if obj.stock_quantity == 0:
            return 'OUT_OF_STOCK'
        if obj.stock_quantity <= obj.low_stock_threshold:
            return 'LOW_STOCK'
        return 'IN_STOCK'

    def get_fitment(self, obj):
        if 'fits_vehicle' not in self.context:
            return None
        if self.context.get('fits_vehicle_no_variant'):
            return {
                "status": "UNKNOWN",
                "qualifications": "vehicle not linked to catalogue",
                "source": "NONE",
            }
        annotated = getattr(obj, '_annotated_fitment', None)
        if annotated is not None:
            return annotated
        target_variant = self.context.get('fits_vehicle_variant')
        if target_variant:
            return evaluate_listing_single_variant(obj, target_variant)
        return {
            "status": "UNKNOWN",
            "qualifications": "No confirmed compatibility record found for this part and vehicle variant.",
            "source": "NONE",
        }

    def get_dealer_pricing(self, obj):
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            return None
        from apps.marketplace.b2b_pricing_service import DealerPricingService

        cached_eligibility = self.context.get('_dealer_eligibility')
        if cached_eligibility is None:
            cached_eligibility = DealerPricingService.evaluate_dealer_eligibility(user=request.user)
            self.context['_dealer_eligibility'] = cached_eligibility

        is_eligible, _, org, profile, tier = cached_eligibility
        if not is_eligible:
            return None

        rules_pool = self.context.get('_dealer_rules_pool')
        if rules_pool is None:
            rules_pool = DealerPricingService.get_rules_for_entity(organisation=org, tier=tier)
            self.context['_dealer_rules_pool'] = rules_pool

        calc = DealerPricingService.calculate_item_price(
            listing=obj,
            quantity=1,
            user=request.user,
            organisation_id=org,
            rules_pool=rules_pool,
        )
        return {
            "is_eligible": True,
            "tier": calc['applied_tier'],
            "tier_name": calc['applied_tier_name'],
            "dealer_unit_price": str(calc['dealer_unit_price']),
            "discount_percentage": str(calc['discount_percentage']),
            "discount_amount_per_unit": str(calc['discount_amount_per_unit']),
            "is_discount_applied": calc['is_dealer_pricing_applied'],
            "minimum_order_quantity": calc['minimum_order_quantity'],
        }

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        if 'fits_vehicle' not in self.context:
            ret.pop('fitment', None)
        return ret


class CataloguePartOfferSerializer(serializers.ModelSerializer):
    """Public serializer for competitive offers on a specific canonical catalogue part."""
    seller_name = serializers.CharField(source='seller.full_name', read_only=True)
    organisation_name = serializers.CharField(source='organisation.name', read_only=True, allow_null=True)
    availability = serializers.SerializerMethodField()
    is_available = serializers.SerializerMethodField()

    hsn_code = serializers.CharField(read_only=True)
    gst_rate = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    is_tax_verified = serializers.BooleanField(read_only=True)
    price_before_gst = serializers.DecimalField(source='price', max_digits=10, decimal_places=2, read_only=True)
    gst_amount = serializers.SerializerMethodField(read_only=True)
    total_price = serializers.SerializerMethodField(read_only=True)
    tax_breakdown = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = SparePartListing
        fields = [
            'id',
            'price',
            'compare_at_price',
            'hsn_code',
            'gst_rate',
            'is_tax_verified',
            'price_before_gst',
            'gst_amount',
            'total_price',
            'tax_breakdown',
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

    def get_gst_amount(self, obj) -> Decimal:
        return obj.gst_amount

    def get_total_price(self, obj) -> Decimal:
        return obj.total_price

    def get_tax_breakdown(self, obj) -> dict:
        return obj.tax_breakdown

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


class BuyerFavouriteVehicleSerializer(serializers.ModelSerializer):
    """Serializer for saved buyer favourite vehicle listings."""

    vehicle = VehicleListingPublicSerializer(read_only=True)
    vehicle_id = serializers.UUIDField(write_only=True, required=False)
    is_available = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = BuyerFavouriteVehicle
        fields = [
            'id',
            'vehicle_id',
            'vehicle',
            'is_available',
            'created_at',
        ]
        read_only_fields = ['id', 'vehicle', 'is_available', 'created_at']

    def get_is_available(self, obj) -> bool:
        if not obj.vehicle:
            return False
        return (
            obj.vehicle.status == ListingStatusChoices.APPROVED
            and bool(obj.vehicle.is_active)
        )

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        if instance.vehicle_id:
            ret['vehicle_id'] = str(instance.vehicle_id)
        return ret

    def validate(self, attrs):
        initial = getattr(self, 'initial_data', {}) or {}
        raw_vid = (
            attrs.get('vehicle_id')
            or initial.get('vehicle_id')
            or initial.get('listing_id')
            or initial.get('vehicle')
        )
        if not raw_vid:
            raise serializers.ValidationError({"vehicle_id": "Vehicle listing ID is required."})

        try:
            vehicle = VehicleListing.objects.get(id=raw_vid)
        except (VehicleListing.DoesNotExist, ValueError):
            raise serializers.ValidationError({"vehicle_id": "Vehicle listing not found."})

        # Eligibility check: Only approved and active vehicle listings may be newly favourited
        if vehicle.status != ListingStatusChoices.APPROVED or not vehicle.is_active:
            raise serializers.ValidationError({
                "vehicle_id": "Only approved and active vehicle listings can be added to favourites."
            })

        attrs['vehicle'] = vehicle
        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        user = request.user if request else None
        vehicle = validated_data['vehicle']
        favourite, _ = BuyerFavouriteVehicle.objects.get_or_create(
            user=user,
            vehicle=vehicle,
        )
        return favourite


class BuyerFavouritePartSerializer(serializers.ModelSerializer):
    """Serializer for saved buyer favourite spare part listings."""

    part = SparePartListingPublicSerializer(read_only=True)
    part_id = serializers.UUIDField(write_only=True, required=False)
    is_available = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = BuyerFavouritePart
        fields = [
            'id',
            'part_id',
            'part',
            'is_available',
            'created_at',
        ]
        read_only_fields = ['id', 'part', 'is_available', 'created_at']

    def get_is_available(self, obj) -> bool:
        if not obj.part:
            return False
        return (
            obj.part.status == ListingStatusChoices.APPROVED
            and bool(obj.part.is_active)
        )

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        if instance.part_id:
            ret['part_id'] = str(instance.part_id)
        return ret

    def validate(self, attrs):
        initial = getattr(self, 'initial_data', {}) or {}
        raw_pid = (
            attrs.get('part_id')
            or initial.get('part_id')
            or initial.get('listing_id')
            or initial.get('part')
        )
        if not raw_pid:
            raise serializers.ValidationError({"part_id": "Spare part listing ID is required."})

        try:
            part = SparePartListing.objects.get(id=raw_pid)
        except (SparePartListing.DoesNotExist, ValueError):
            raise serializers.ValidationError({"part_id": "Spare part listing not found."})

        # Eligibility check: Only approved and active spare part listings may be newly favourited
        if part.status != ListingStatusChoices.APPROVED or not part.is_active:
            raise serializers.ValidationError({
                "part_id": "Only approved and active spare part listings can be added to favourites."
            })

        attrs['part'] = part
        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        user = request.user if request else None
        part = validated_data['part']
        favourite, _ = BuyerFavouritePart.objects.get_or_create(
            user=user,
            part=part,
        )
        return favourite


VALID_ORDER_STATUS_TRANSITIONS = {
    OrderStatusChoices.PENDING_CONFIRMATION: [
        OrderStatusChoices.CONFIRMED,
        OrderStatusChoices.CANCELLED,
    ],
    OrderStatusChoices.CONFIRMED: [
        OrderStatusChoices.PROCESSING,
        OrderStatusChoices.CANCELLED,
    ],
    OrderStatusChoices.PROCESSING: [
        OrderStatusChoices.COMPLETED,
        OrderStatusChoices.CANCELLED,
    ],
    OrderStatusChoices.COMPLETED: [],
    OrderStatusChoices.CANCELLED: [],
}


class OrderItemSerializer(serializers.ModelSerializer):
    seller_name = serializers.SerializerMethodField()
    seller_id = serializers.SerializerMethodField()
    listing_id = serializers.UUIDField(source='listing.id', read_only=True, allow_null=True)
    is_reviewed = serializers.SerializerMethodField()
    review = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = [
            'id',
            'listing_id',
            'seller_id',
            'seller_name',
            'item_type',
            'title',
            'brand',
            'mpn',
            'hsn_code',
            'gst_rate',
            'is_tax_verified',
            'unit_price',
            'quantity',
            'taxable_amount',
            'cgst_amount',
            'sgst_amount',
            'igst_amount',
            'tax_amount',
            'total_amount',
            'retail_unit_price',
            'discount_amount',
            'pricing_tier',
            'pricing_rule_snapshot',
            'is_reviewed',
            'review',
        ]
        read_only_fields = fields

    def get_seller_name(self, obj):
        if obj.listing and obj.listing.seller:
            return obj.listing.seller.full_name or obj.listing.seller.email
        return ""

    def get_seller_id(self, obj):
        if obj.listing and obj.listing.seller_id:
            return str(obj.listing.seller_id)
        return None

    def _get_review(self, obj):
        try:
            return obj.product_review
        except Exception:
            return None

    def get_is_reviewed(self, obj) -> bool:
        return self._get_review(obj) is not None

    def get_review(self, obj):
        rev = self._get_review(obj)
        if rev:
            return {
                "id": str(rev.id),
                "rating": rev.rating,
                "title": rev.title,
                "comment": rev.comment,
                "status": rev.status,
                "created_at": rev.created_at.isoformat(),
            }
        return None


class ShipmentItemSerializer(serializers.ModelSerializer):
    order_item_id = serializers.UUIDField(source='order_item.id', read_only=True)
    title = serializers.CharField(source='order_item.title', read_only=True)
    brand = serializers.CharField(source='order_item.brand', read_only=True)
    mpn = serializers.CharField(source='order_item.mpn', read_only=True)
    hsn_code = serializers.CharField(source='order_item.hsn_code', read_only=True)

    class Meta:
        model = ShipmentItem
        fields = [
            'id',
            'order_item_id',
            'title',
            'brand',
            'mpn',
            'hsn_code',
            'quantity',
            'created_at',
        ]
        read_only_fields = fields


class TrackingEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrackingEvent
        fields = [
            'id',
            'status',
            'location',
            'description',
            'event_timestamp',
            'external_checkpoint_id',
            'created_at',
        ]
        read_only_fields = fields


class ShipmentSerializer(serializers.ModelSerializer):
    order_id = serializers.UUIDField(source='order.id', read_only=True)
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    seller_name = serializers.CharField(source='seller.full_name', read_only=True)
    items = ShipmentItemSerializer(many=True, read_only=True)
    tracking_events = TrackingEventSerializer(many=True, read_only=True)

    class Meta:
        model = Shipment
        fields = [
            'id',
            'shipment_number',
            'order_id',
            'order_number',
            'seller_id',
            'seller_name',
            'carrier',
            'carrier_name',
            'tracking_number',
            'tracking_url',
            'status',
            'dispatched_at',
            'delivered_at',
            'estimated_delivery_at',
            'delivery_notes',
            'shipping_label_url',
            'items',
            'tracking_events',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    shipments = serializers.SerializerMethodField()
    return_requests = serializers.SerializerMethodField()
    refunds = serializers.SerializerMethodField()
    disputes = serializers.SerializerMethodField()
    buyer_email = serializers.CharField(source='buyer.email', read_only=True)
    buyer_name = serializers.CharField(source='buyer.full_name', read_only=True)
    cod_collected_by_name = serializers.CharField(source='cod_collected_by.full_name', read_only=True, allow_null=True)

    class Meta:
        model = Order
        fields = [
            'id',
            'order_number',
            'idempotency_key',
            'buyer_email',
            'buyer_name',
            'status',
            'payment_method',
            'payment_status',
            'payment_reference',
            'paid_at',
            'cod_collection_status',
            'cod_collected_at',
            'cod_collected_by',
            'cod_collected_by_name',
            'cod_collection_notes',
            'currency',
            'place_of_supply',
            'seller_state',
            'shipping_name',
            'shipping_phone',
            'shipping_address_line1',
            'shipping_address_line2',
            'shipping_city',
            'shipping_state',
            'shipping_postal_code',
            'shipping_country',
            'subtotal_taxable_amount',
            'cgst_amount',
            'sgst_amount',
            'igst_amount',
            'total_tax_amount',
            'total_amount',
            'organisation',
            'is_dealer_order',
            'total_discount_amount',
            'tax_breakdown',
            'items',
            'shipments',
            'return_requests',
            'refunds',
            'disputes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_shipments(self, obj):
        return ShipmentSerializer(obj.shipments.all(), many=True).data

    def get_return_requests(self, obj):
        return ReturnRequestSerializer(obj.return_requests.all(), many=True).data

    def get_refunds(self, obj):
        return RefundSerializer(obj.refunds.all(), many=True).data

    def get_disputes(self, obj):
        return DisputeSerializer(obj.disputes.all(), many=True).data


class SellerOrderSerializer(serializers.ModelSerializer):
    """
    Seller order serializer ensuring strict multi-seller order isolation.
    Displays only items belonging to the requesting seller, and computes
    financial totals (subtotal, taxes, total) for the seller's items only.
    """
    items = serializers.SerializerMethodField()
    shipments = serializers.SerializerMethodField()
    return_requests = serializers.SerializerMethodField()
    refunds = serializers.SerializerMethodField()
    disputes = serializers.SerializerMethodField()
    buyer_email = serializers.CharField(source='buyer.email', read_only=True)
    buyer_name = serializers.CharField(source='buyer.full_name', read_only=True)
    seller_subtotal_taxable_amount = serializers.SerializerMethodField()
    seller_cgst_amount = serializers.SerializerMethodField()
    seller_sgst_amount = serializers.SerializerMethodField()
    seller_igst_amount = serializers.SerializerMethodField()
    seller_total_tax_amount = serializers.SerializerMethodField()
    seller_total_amount = serializers.SerializerMethodField()
    seller_item_count = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id',
            'order_number',
            'buyer_email',
            'buyer_name',
            'status',
            'payment_method',
            'payment_status',
            'payment_reference',
            'paid_at',
            'cod_collection_status',
            'currency',
            'place_of_supply',
            'seller_state',
            'shipping_name',
            'shipping_phone',
            'shipping_address_line1',
            'shipping_address_line2',
            'shipping_city',
            'shipping_state',
            'shipping_postal_code',
            'shipping_country',
            'seller_subtotal_taxable_amount',
            'seller_cgst_amount',
            'seller_sgst_amount',
            'seller_igst_amount',
            'seller_total_tax_amount',
            'seller_total_amount',
            'seller_item_count',
            'items',
            'shipments',
            'return_requests',
            'refunds',
            'disputes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_shipments(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return []
        user = request.user

        from apps.organisations.models import OrganisationMembership, OrganisationRoleChoices
        from django.db.models import Q
        org_ids = set(OrganisationMembership.objects.filter(
            user=user,
            is_active=True,
            role__in=[OrganisationRoleChoices.OWNER, OrganisationRoleChoices.ADMIN],
        ).values_list('organisation_id', flat=True))

        seller_shipments = obj.shipments.filter(
            Q(seller=user) | Q(organisation_id__in=org_ids)
        ).distinct()
        return ShipmentSerializer(seller_shipments, many=True).data

    def get_return_requests(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return []
        user = request.user
        if user.is_staff or user.is_superuser:
            return ReturnRequestSerializer(obj.return_requests.all(), many=True).data

        from apps.organisations.models import OrganisationMembership, OrganisationRoleChoices
        from django.db.models import Q
        org_ids = set(OrganisationMembership.objects.filter(
            user=user,
            is_active=True,
            role__in=[OrganisationRoleChoices.OWNER, OrganisationRoleChoices.ADMIN],
        ).values_list('organisation_id', flat=True))

        return ReturnRequestSerializer(
            obj.return_requests.filter(
                Q(seller=user) | Q(order_item__listing__organisation_id__in=org_ids)
            ).distinct(),
            many=True,
        ).data

    def get_refunds(self, obj):
        return RefundSerializer(obj.refunds.all(), many=True).data

    def get_disputes(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return []
        user = request.user
        if user.is_staff or user.is_superuser:
            return DisputeSerializer(obj.disputes.all(), many=True).data
        return DisputeSerializer(obj.disputes.filter(seller=user), many=True).data

    def _get_seller_items(self, order):
        if hasattr(order, '_cached_seller_items'):
            return order._cached_seller_items
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            order._cached_seller_items = []
            return order._cached_seller_items
        user = request.user

        from apps.organisations.models import OrganisationMembership, OrganisationRoleChoices
        org_ids = set(OrganisationMembership.objects.filter(
            user=user,
            is_active=True,
            role__in=[OrganisationRoleChoices.OWNER, OrganisationRoleChoices.ADMIN],
        ).values_list('organisation_id', flat=True))

        items = []
        for item in order.items.all():
            if item.listing and (item.listing.seller_id == user.id or item.listing.organisation_id in org_ids):
                items.append(item)
        order._cached_seller_items = items
        return items

    def get_items(self, obj):
        seller_items = self._get_seller_items(obj)
        return OrderItemSerializer(seller_items, many=True).data

    def get_seller_subtotal_taxable_amount(self, obj):
        seller_items = self._get_seller_items(obj)
        total = sum((item.taxable_amount for item in seller_items), Decimal('0.00'))
        return str(total)

    def get_seller_cgst_amount(self, obj):
        seller_items = self._get_seller_items(obj)
        total = sum((item.cgst_amount for item in seller_items), Decimal('0.00'))
        return str(total)

    def get_seller_sgst_amount(self, obj):
        seller_items = self._get_seller_items(obj)
        total = sum((item.sgst_amount for item in seller_items), Decimal('0.00'))
        return str(total)

    def get_seller_igst_amount(self, obj):
        seller_items = self._get_seller_items(obj)
        total = sum((item.igst_amount for item in seller_items), Decimal('0.00'))
        return str(total)

    def get_seller_total_tax_amount(self, obj):
        seller_items = self._get_seller_items(obj)
        total = sum((item.tax_amount for item in seller_items), Decimal('0.00'))
        return str(total)

    def get_seller_total_amount(self, obj):
        seller_items = self._get_seller_items(obj)
        total = sum((item.total_amount for item in seller_items), Decimal('0.00'))
        return str(total)

    def get_seller_item_count(self, obj):
        seller_items = self._get_seller_items(obj)
        return sum(item.quantity for item in seller_items)


class OrderStatusUpdateSerializer(serializers.Serializer):
    """Validates permitted status updates with transition rules."""
    status = serializers.ChoiceField(choices=OrderStatusChoices.choices, required=True)
    notes = serializers.CharField(required=False, allow_blank=True, default='')

    def validate_status(self, value):
        order = self.context.get('order')
        if not order:
            return value

        current_status = order.status
        if current_status == value:
            return value

        valid_targets = VALID_ORDER_STATUS_TRANSITIONS.get(current_status, [])
        if value not in valid_targets:
            raise serializers.ValidationError(
                f"Cannot transition order from '{current_status}' to '{value}'. "
                f"Permitted transitions from '{current_status}': {valid_targets or 'None (Terminal state)'}."
            )
        return value


class CheckoutItemPayloadSerializer(serializers.Serializer):
    listing_id = serializers.UUIDField(required=True)
    quantity = serializers.IntegerField(min_value=1, default=1)


class CheckoutPayloadSerializer(serializers.Serializer):
    items = CheckoutItemPayloadSerializer(many=True, required=True)
    place_of_supply = serializers.CharField(required=False, allow_blank=True, default='')
    currency = serializers.CharField(required=False, allow_blank=True, default='')
    payment_method = serializers.ChoiceField(
        choices=PaymentMethodChoices.choices,
        default=PaymentMethodChoices.ONLINE,
        required=False,
    )
    shipping_name = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    shipping_phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default='')
    shipping_address_line1 = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    shipping_address_line2 = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    shipping_city = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    shipping_state = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    shipping_postal_code = serializers.CharField(max_length=20, required=False, allow_blank=True, default='')
    shipping_country = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    expected_total_amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        allow_null=True,
        default=None,
    )
    idempotency_key = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    organisation_id = serializers.UUIDField(required=False, allow_null=True, default=None)


class PaymentVerifyPayloadSerializer(serializers.Serializer):
    """Payload for verifying client payment confirmation."""
    razorpay_order_id = serializers.CharField(required=False, allow_blank=True, default='')
    razorpay_payment_id = serializers.CharField(required=False, allow_blank=True, default='')
    razorpay_signature = serializers.CharField(required=False, allow_blank=True, default='')
    payment_intent_id = serializers.CharField(required=False, allow_blank=True, default='')
    stripe_payment_intent_id = serializers.CharField(required=False, allow_blank=True, default='')
    client_secret = serializers.CharField(required=False, allow_blank=True, default='')
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    currency = serializers.CharField(max_length=10, required=False, allow_blank=True, default='')

    def validate(self, attrs):
        # Normalize Stripe payment intent ID across naming variants
        pi = (attrs.get('payment_intent_id') or attrs.get('stripe_payment_intent_id') or '').strip()
        cs = (attrs.get('client_secret') or '').strip()
        if not pi and cs and '_secret_' in cs:
            pi = cs.split('_secret_')[0].strip()
        attrs['payment_intent_id'] = pi
        attrs['stripe_payment_intent_id'] = pi
        return attrs


class CODCollectionUpdateSerializer(serializers.Serializer):
    """Payload for updating COD collection status by authorized operations staff."""
    cod_collection_status = serializers.ChoiceField(
        choices=CODCollectionStatusChoices.choices,
        required=False,
    )
    status = serializers.ChoiceField(
        choices=CODCollectionStatusChoices.choices,
        required=False,
    )
    notes = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, attrs):
        status_val = attrs.get('cod_collection_status') or attrs.get('status')
        if not status_val:
            raise serializers.ValidationError({
                "cod_collection_status": "This field is required."
            })
        attrs['cod_collection_status'] = status_val
        attrs['status'] = status_val
        return attrs



class VehicleEnquiryCreateSerializer(serializers.ModelSerializer):
    """Serializer for submitting a direct enquiry about a vehicle listing."""
    message = serializers.CharField(
        min_length=10,
        max_length=2000,
        required=True,
        error_messages={
            'min_length': 'Your enquiry message must be at least 10 characters long.',
            'max_length': 'Your enquiry message cannot exceed 2000 characters.',
        }
    )
    buyer_phone = serializers.CharField(
        max_length=30,
        required=False,
        allow_blank=True,
        default='',
    )

    class Meta:
        model = VehicleEnquiry
        fields = ['message', 'buyer_phone']


class VehicleEnquiryListingSummarySerializer(serializers.ModelSerializer):
    make_name = serializers.CharField(source='make.name', read_only=True)
    model_name = serializers.CharField(source='model.name', read_only=True)

    class Meta:
        model = VehicleListing
        fields = [
            'id',
            'title',
            'make_name',
            'model_name',
            'year',
            'price',
            'currency',
            'primary_image_url',
            'location_city',
            'status',
        ]


class VehicleEnquirySellerSerializer(serializers.ModelSerializer):
    """Full detail view of an enquiry for authorized sellers/organisations."""
    listing_details = VehicleEnquiryListingSummarySerializer(source='listing', read_only=True)
    buyer_name = serializers.CharField(source='buyer.full_name', read_only=True)
    buyer_email = serializers.EmailField(source='buyer.email', read_only=True)
    seller_name = serializers.CharField(source='seller.full_name', read_only=True)
    organisation_name = serializers.CharField(source='organisation.name', read_only=True, allow_null=True)

    class Meta:
        model = VehicleEnquiry
        fields = [
            'id',
            'listing',
            'listing_details',
            'buyer',
            'buyer_name',
            'buyer_email',
            'buyer_phone',
            'seller',
            'seller_name',
            'organisation',
            'organisation_name',
            'message',
            'status',
            'seller_notes',
            'seller_reply',
            'replied_at',
            'responded_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id', 'listing', 'listing_details', 'buyer', 'buyer_name',
            'buyer_email', 'seller', 'seller_name', 'organisation',
            'organisation_name', 'message', 'created_at', 'updated_at',
        ]


class VehicleEnquiryBuyerSerializer(serializers.ModelSerializer):
    """View of an enquiry for the authenticated buyer who submitted it."""
    listing_details = VehicleEnquiryListingSummarySerializer(source='listing', read_only=True)
    seller_name = serializers.CharField(source='seller.full_name', read_only=True)
    organisation_name = serializers.CharField(source='organisation.name', read_only=True, allow_null=True)

    class Meta:
        model = VehicleEnquiry
        fields = [
            'id',
            'listing',
            'listing_details',
            'seller_name',
            'organisation_name',
            'message',
            'buyer_phone',
            'status',
            'seller_reply',
            'replied_at',
            'responded_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields


class VehicleEnquiryStatusUpdateSerializer(serializers.Serializer):
    """Allows a seller to update enquiry lifecycle status, add internal notes, and send replies."""
    status = serializers.ChoiceField(
        choices=VehicleEnquiryStatusChoices.choices,
        required=False,
    )
    seller_notes = serializers.CharField(
        required=False,
        allow_blank=True,
    )
    seller_reply = serializers.CharField(
        required=False,
        allow_blank=True,
    )


# =============================================================================
# Phase 5 Task 2: Logistics & Shipment Payload Serializers
# =============================================================================

class ShipmentItemAllocationSerializer(serializers.Serializer):
    order_item_id = serializers.UUIDField(required=True)
    quantity = serializers.IntegerField(min_value=1, default=1)


class ShipmentCreatePayloadSerializer(serializers.Serializer):
    carrier = serializers.ChoiceField(
        choices=CarrierChoices.choices,
        default=CarrierChoices.OTHER,
        required=False,
    )
    carrier_name = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        default='',
    )
    tracking_number = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        default='',
    )
    tracking_url = serializers.URLField(
        max_length=500,
        required=False,
        allow_blank=True,
        default='',
    )
    estimated_delivery_at = serializers.DateTimeField(
        required=False,
        allow_null=True,
        default=None,
    )
    delivery_notes = serializers.CharField(
        required=False,
        allow_blank=True,
        default='',
    )
    dispatch_immediately = serializers.BooleanField(
        default=False,
        required=False,
    )
    items = ShipmentItemAllocationSerializer(
        many=True,
        required=True,
    )

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one item must be included in the shipment.")
        return value


class ShipmentStatusUpdatePayloadSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=ShipmentStatusChoices.choices,
        required=True,
    )
    location = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        default='',
    )
    description = serializers.CharField(
        required=False,
        allow_blank=True,
        default='',
    )
    carrier_reference = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        default='',
    )


class TrackingEventCreatePayloadSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=ShipmentStatusChoices.choices,
        required=False,
        default=None,
    )
    location = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        default='',
    )
    description = serializers.CharField(
        required=True,
    )
    event_timestamp = serializers.DateTimeField(
        required=False,
        default=None,
        allow_null=True,
    )
    external_checkpoint_id = serializers.CharField(
        max_length=150,
        required=False,
        allow_blank=True,
        default='',
    )


# =============================================================================
# Phase 5 Task 3: Returns, Refunds & Dispute Management Serializers
# =============================================================================

class ReturnRequestSerializer(serializers.ModelSerializer):
    order_id = serializers.UUIDField(source='order.id', read_only=True)
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    order_item_id = serializers.UUIDField(source='order_item.id', read_only=True, allow_null=True)
    item_title = serializers.CharField(source='order_item.title', read_only=True, default='')
    item_brand = serializers.CharField(source='order_item.brand', read_only=True, default='')
    buyer_email = serializers.CharField(source='buyer.email', read_only=True)
    seller_email = serializers.CharField(source='seller.email', read_only=True)
    reviewed_by_email = serializers.CharField(source='reviewed_by.email', read_only=True, allow_null=True)

    class Meta:
        model = ReturnRequest
        fields = [
            'id',
            'request_number',
            'order_id',
            'order_number',
            'order_item_id',
            'item_title',
            'item_brand',
            'buyer_id',
            'buyer_email',
            'seller_id',
            'seller_email',
            'request_type',
            'status',
            'reason',
            'description',
            'evidence_urls',
            'requested_quantity',
            'refund_amount',
            'seller_notes',
            'rejection_reason',
            'reviewed_by_email',
            'reviewed_at',
            'completed_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields


class ReturnRequestCreatePayloadSerializer(serializers.Serializer):
    order_item_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    request_type = serializers.ChoiceField(
        choices=ReturnRequestTypeChoices.choices,
        default=ReturnRequestTypeChoices.RETURN,
    )
    reason = serializers.ChoiceField(
        choices=ReturnReasonChoices.choices,
        default=ReturnReasonChoices.OTHER,
    )
    description = serializers.CharField(required=True, min_length=5)
    evidence_urls = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
    )
    requested_quantity = serializers.IntegerField(min_value=1, default=1)


class ReturnRequestReviewPayloadSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['APPROVE', 'REJECT'])
    seller_notes = serializers.CharField(required=False, allow_blank=True, default='')
    rejection_reason = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, attrs):
        action = attrs.get('action')
        rejection_reason = (attrs.get('rejection_reason') or '').strip()
        if action == 'REJECT' and not rejection_reason:
            raise serializers.ValidationError({
                "rejection_reason": "A documented rejection reason is mandatory when rejecting a return request."
            })
        return attrs


class RefundSerializer(serializers.ModelSerializer):
    order_id = serializers.UUIDField(source='order.id', read_only=True)
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    return_request_id = serializers.UUIDField(source='return_request.id', read_only=True, allow_null=True)
    return_request_number = serializers.CharField(source='return_request.request_number', read_only=True, default='')
    dispute_id = serializers.UUIDField(source='dispute.id', read_only=True, allow_null=True)
    dispute_number = serializers.CharField(source='dispute.dispute_number', read_only=True, default='')
    refund_method_display = serializers.CharField(source='get_refund_method_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    created_by_email = serializers.CharField(source='created_by.email', read_only=True, allow_null=True)
    approved_by_email = serializers.CharField(source='approved_by.email', read_only=True, allow_null=True)

    class Meta:
        model = Refund
        fields = [
            'id',
            'refund_number',
            'order_id',
            'order_number',
            'return_request_id',
            'return_request_number',
            'dispute_id',
            'dispute_number',
            'amount',
            'currency',
            'status',
            'status_display',
            'refund_method',
            'refund_method_display',
            'gateway_provider',
            'gateway_refund_id',
            'reason',
            'failure_reason',
            'notes',
            'processed_at',
            'created_by_email',
            'approved_by_email',
            'created_at',
        ]
        read_only_fields = fields


class RefundCreatePayloadSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))
    reason = serializers.CharField(required=True, min_length=3)
    refund_method = serializers.ChoiceField(
        choices=RefundMethodChoices.choices,
        required=False,
        default=None,
        allow_null=True,
    )
    return_request_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    dispute_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    notes = serializers.CharField(required=False, allow_blank=True, default='')
    auto_process = serializers.BooleanField(required=False, default=False)


class SellerRecordRefundPayloadSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))
    transaction_reference = serializers.CharField(required=True, min_length=3, max_length=255)
    reason = serializers.CharField(required=False, allow_blank=True, default='')
    refund_method = serializers.ChoiceField(
        choices=RefundMethodChoices.choices,
        required=False,
        default=RefundMethodChoices.BANK_TRANSFER,
    )
    evidence_url = serializers.CharField(required=False, allow_blank=True, default='')
    return_request_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class SellerRequestPlatformRefundPayloadSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))
    reason = serializers.CharField(required=True, min_length=3)
    return_request_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class DisputeEventSerializer(serializers.ModelSerializer):
    actor_id = serializers.UUIDField(source='actor.id', read_only=True, allow_null=True)
    actor_email = serializers.CharField(source='actor.email', read_only=True, default='System')
    actor_role = serializers.SerializerMethodField()

    class Meta:
        model = DisputeEvent
        fields = [
            'id',
            'actor_id',
            'actor_email',
            'actor_role',
            'event_type',
            'message',
            'attachments',
            'created_at',
        ]
        read_only_fields = fields

    def get_actor_role(self, obj):
        if not obj.actor:
            return 'SYSTEM'
        if obj.actor.is_staff or obj.actor.is_superuser:
            return 'STAFF'
        if obj.actor_id == obj.dispute.buyer_id:
            return 'BUYER'
        if obj.actor_id == obj.dispute.seller_id:
            return 'SELLER'
        return 'USER'


class DisputeSerializer(serializers.ModelSerializer):
    order_id = serializers.UUIDField(source='order.id', read_only=True)
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    buyer_email = serializers.CharField(source='buyer.email', read_only=True)
    seller_email = serializers.CharField(source='seller.email', read_only=True)
    resolved_by_email = serializers.CharField(source='resolved_by.email', read_only=True, allow_null=True)
    events = DisputeEventSerializer(many=True, read_only=True)

    class Meta:
        model = Dispute
        fields = [
            'id',
            'dispute_number',
            'order_id',
            'order_number',
            'buyer_id',
            'buyer_email',
            'seller_id',
            'seller_email',
            'category',
            'status',
            'priority',
            'description',
            'evidence_urls',
            'resolution',
            'resolution_notes',
            'resolved_by_email',
            'resolved_at',
            'events',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields


class DisputeCreatePayloadSerializer(serializers.Serializer):
    category = serializers.ChoiceField(choices=DisputeCategoryChoices.choices)
    priority = serializers.ChoiceField(
        choices=DisputePriorityChoices.choices,
        required=False,
        default=DisputePriorityChoices.MEDIUM,
    )
    description = serializers.CharField(required=True, min_length=10)
    evidence_urls = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
    )


class DisputeStatusUpdatePayloadSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=DisputeStatusChoices.choices)
    resolution = serializers.ChoiceField(
        choices=DisputeResolutionChoices.choices,
        required=False,
        allow_blank=True,
        default='',
    )
    resolution_notes = serializers.CharField(required=False, allow_blank=True, default='')


class DisputeMessagePayloadSerializer(serializers.Serializer):
    message = serializers.CharField(required=True, min_length=1)
    attachments = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
    )


# =============================================================================
# Phase 5 Task 4: Reviews, Ratings & Seller Reputation Serializers
# =============================================================================

class ProductReviewSerializer(serializers.ModelSerializer):
    order_id = serializers.UUIDField(source='order.id', read_only=True)
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    order_item_id = serializers.UUIDField(source='order_item.id', read_only=True)
    listing_id = serializers.UUIDField(source='listing.id', read_only=True)
    listing_name = serializers.CharField(source='listing.name', read_only=True)
    listing_image_url = serializers.CharField(source='listing.primary_image_url', read_only=True)
    buyer_id = serializers.UUIDField(source='buyer.id', read_only=True)
    buyer_name = serializers.CharField(source='buyer.full_name', read_only=True)
    seller_id = serializers.UUIDField(source='seller.id', read_only=True)
    seller_name = serializers.CharField(source='seller.full_name', read_only=True)
    organisation_name = serializers.CharField(source='organisation.name', read_only=True, allow_null=True)
    seller_replied_by_name = serializers.CharField(source='seller_replied_by.full_name', read_only=True, allow_null=True)
    has_seller_reply = serializers.SerializerMethodField()

    class Meta:
        model = ProductReview
        fields = [
            'id',
            'order_id',
            'order_number',
            'order_item_id',
            'listing_id',
            'listing_name',
            'listing_image_url',
            'buyer_id',
            'buyer_name',
            'seller_id',
            'seller_name',
            'organisation_name',
            'rating',
            'title',
            'comment',
            'status',
            'is_verified_purchase',
            'seller_reply',
            'seller_reply_at',
            'seller_replied_by_name',
            'has_seller_reply',
            'helpful_votes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_has_seller_reply(self, obj) -> bool:
        return bool(obj.seller_reply and obj.seller_reply.strip())


class ProductReviewCreatePayloadSerializer(serializers.Serializer):
    order_id = serializers.CharField(required=False, allow_blank=True, default='')
    order_item_id = serializers.UUIDField(required=True)
    rating = serializers.IntegerField(min_value=1, max_value=5, required=True)
    title = serializers.CharField(required=False, allow_blank=True, max_length=255, default='')
    comment = serializers.CharField(required=True, min_length=5)
    seller_rating = serializers.IntegerField(min_value=1, max_value=5, required=False, allow_null=True, default=None)
    seller_comment = serializers.CharField(required=False, allow_blank=True, default='')


class ProductReviewUpdatePayloadSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5, required=False)
    title = serializers.CharField(required=False, allow_blank=True, max_length=255)
    comment = serializers.CharField(required=False, min_length=5)


class SellerReviewSerializer(serializers.ModelSerializer):
    order_id = serializers.UUIDField(source='order.id', read_only=True)
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    buyer_id = serializers.UUIDField(source='buyer.id', read_only=True)
    buyer_name = serializers.CharField(source='buyer.full_name', read_only=True)
    seller_id = serializers.UUIDField(source='seller.id', read_only=True)
    seller_name = serializers.CharField(source='seller.full_name', read_only=True)
    organisation_name = serializers.CharField(source='organisation.name', read_only=True, allow_null=True)
    seller_replied_by_name = serializers.CharField(source='seller_replied_by.full_name', read_only=True, allow_null=True)

    class Meta:
        model = SellerReview
        fields = [
            'id',
            'order_id',
            'order_number',
            'buyer_id',
            'buyer_name',
            'seller_id',
            'seller_name',
            'organisation_name',
            'rating',
            'communication_rating',
            'delivery_rating',
            'item_description_rating',
            'comment',
            'status',
            'is_verified_purchase',
            'seller_reply',
            'seller_reply_at',
            'seller_replied_by_name',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields


class SellerReviewCreatePayloadSerializer(serializers.Serializer):
    order_id = serializers.CharField(required=True)
    seller_id = serializers.UUIDField(required=True)
    rating = serializers.IntegerField(min_value=1, max_value=5, required=True)
    communication_rating = serializers.IntegerField(min_value=1, max_value=5, required=False, allow_null=True, default=None)
    delivery_rating = serializers.IntegerField(min_value=1, max_value=5, required=False, allow_null=True, default=None)
    item_description_rating = serializers.IntegerField(min_value=1, max_value=5, required=False, allow_null=True, default=None)
    comment = serializers.CharField(required=False, allow_blank=True, default='')


class ReviewSellerReplyPayloadSerializer(serializers.Serializer):
    reply = serializers.CharField(required=True, min_length=3)


class ReviewReportSerializer(serializers.ModelSerializer):
    reporter_email = serializers.CharField(source='reporter.email', read_only=True)
    reporter_name = serializers.CharField(source='reporter.full_name', read_only=True)
    resolved_by_email = serializers.CharField(source='resolved_by.email', read_only=True, allow_null=True)
    product_review_title = serializers.CharField(source='product_review.title', read_only=True, default='')
    product_review_comment = serializers.CharField(source='product_review.comment', read_only=True, default='')
    target_type = serializers.SerializerMethodField()
    target_id = serializers.SerializerMethodField()

    class Meta:
        model = ReviewReport
        fields = [
            'id',
            'target_type',
            'target_id',
            'product_review_id',
            'seller_review_id',
            'product_review_title',
            'product_review_comment',
            'reporter_id',
            'reporter_email',
            'reporter_name',
            'reason',
            'details',
            'status',
            'action_taken',
            'admin_notes',
            'resolved_by_email',
            'resolved_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_target_type(self, obj) -> str:
        return 'PRODUCT_REVIEW' if obj.product_review_id else 'SELLER_REVIEW'

    def get_target_id(self, obj) -> str:
        return str(obj.product_review_id or obj.seller_review_id)


class ReviewReportCreatePayloadSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=ReviewReportReasonChoices.choices)
    details = serializers.CharField(required=False, allow_blank=True, default='')


class ReviewReportResolvePayloadSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['DISMISS', 'HIDE_REVIEW', 'DELETE_REVIEW'])
    admin_notes = serializers.CharField(required=False, allow_blank=True, default='')


class ReviewModerationPayloadSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['APPROVE', 'FLAG', 'HIDE', 'DELETE'])
    admin_notes = serializers.CharField(required=False, allow_blank=True, default='')


# =============================================================================
# Vehicle Purchase Offers & Orders Serializers
# =============================================================================

class VehicleOfferProposalSerializer(serializers.ModelSerializer):
    proposed_by_name = serializers.CharField(source='proposed_by.full_name', read_only=True)
    proposed_by_email = serializers.CharField(source='proposed_by.email', read_only=True)

    class Meta:
        model = VehicleOfferProposal
        fields = [
            'id',
            'revision_number',
            'proposed_by',
            'proposed_by_name',
            'proposed_by_email',
            'proposed_by_role',
            'offered_price',
            'currency',
            'handover_preference',
            'notes',
            'created_at',
        ]
        read_only_fields = fields


class VehicleOfferActionSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source='actor.full_name', read_only=True)
    actor_email = serializers.CharField(source='actor.email', read_only=True)

    class Meta:
        model = VehicleOfferAction
        fields = [
            'id',
            'action_type',
            'actor',
            'actor_name',
            'actor_email',
            'proposal',
            'notes',
            'metadata',
            'created_at',
        ]
        read_only_fields = fields


class VehiclePurchaseOfferSerializer(serializers.ModelSerializer):
    buyer_name = serializers.CharField(source='buyer.full_name', read_only=True)
    buyer_email = serializers.CharField(source='buyer.email', read_only=True)
    seller_name = serializers.CharField(source='seller.full_name', read_only=True)
    seller_email = serializers.CharField(source='seller.email', read_only=True)
    organisation_name = serializers.CharField(source='organisation.name', read_only=True, allow_null=True)
    listing_title = serializers.CharField(source='listing.title', read_only=True)
    listing_price = serializers.DecimalField(source='listing.price', max_digits=12, decimal_places=2, read_only=True)
    listing_image_url = serializers.CharField(source='listing.primary_image_url', read_only=True)
    listing_availability = serializers.CharField(source='listing.availability_status', read_only=True)
    proposals = VehicleOfferProposalSerializer(many=True, read_only=True)
    actions = VehicleOfferActionSerializer(many=True, read_only=True)
    order_id = serializers.SerializerMethodField()
    order_number = serializers.SerializerMethodField()

    class Meta:
        model = VehiclePurchaseOffer
        fields = [
            'id',
            'listing',
            'listing_title',
            'listing_price',
            'listing_image_url',
            'listing_availability',
            'buyer',
            'buyer_name',
            'buyer_email',
            'seller',
            'seller_name',
            'seller_email',
            'organisation',
            'organisation_name',
            'status',
            'current_round',
            'agreed_price',
            'currency',
            'expires_at',
            'accepted_at',
            'rejected_at',
            'withdrawn_at',
            'created_at',
            'updated_at',
            'proposals',
            'actions',
            'order_id',
            'order_number',
        ]
        read_only_fields = fields

    def get_order_id(self, obj) -> str | None:
        if hasattr(obj, 'order') and obj.order:
            return str(obj.order.id)
        return None

    def get_order_number(self, obj) -> str | None:
        if hasattr(obj, 'order') and obj.order:
            return obj.order.order_number
        return None


class VehicleOfferSubmitSerializer(serializers.Serializer):
    offered_price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    handover_preference = serializers.ChoiceField(
        choices=VehicleHandoverTypeChoices.choices,
        default=VehicleHandoverTypeChoices.COLLECTION,
    )
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class VehicleOfferCounterSerializer(serializers.Serializer):
    counter_price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    handover_preference = serializers.ChoiceField(
        choices=VehicleHandoverTypeChoices.choices,
        required=False,
    )
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class VehiclePaymentVerificationEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source='actor.full_name', read_only=True, allow_null=True)
    actor_email = serializers.CharField(source='actor.email', read_only=True, allow_null=True)

    class Meta:
        model = VehiclePaymentVerificationEvent
        fields = [
            'id',
            'report',
            'order',
            'actor',
            'actor_name',
            'actor_email',
            'event_type',
            'notes',
            'metadata',
            'created_at',
        ]
        read_only_fields = fields


class VehiclePaymentReportSerializer(serializers.ModelSerializer):
    submitted_by_name = serializers.CharField(source='submitted_by.full_name', read_only=True)
    submitted_by_email = serializers.CharField(source='submitted_by.email', read_only=True)
    verified_by_name = serializers.CharField(source='verified_by.full_name', read_only=True, allow_null=True)
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    verification_events = VehiclePaymentVerificationEventSerializer(many=True, read_only=True)

    class Meta:
        model = VehiclePaymentReport
        fields = [
            'id',
            'order',
            'order_number',
            'submitted_by',
            'submitted_by_name',
            'submitted_by_email',
            'amount_paid',
            'currency',
            'payment_reference',
            'paid_at',
            'payment_notes',
            'status',
            'verified_by',
            'verified_by_name',
            'verified_at',
            'verification_notes',
            'escalation_level',
            'escalated_at',
            'created_at',
            'updated_at',
            'verification_events',
        ]
        read_only_fields = fields


class VehiclePaymentReportSubmitSerializer(serializers.Serializer):
    amount_paid = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    currency = serializers.CharField(max_length=10)
    payment_reference = serializers.CharField(max_length=100, min_length=3)
    paid_at = serializers.DateTimeField()
    payment_notes = serializers.CharField(required=False, allow_blank=True, default='')


class VehiclePaymentVerificationActionSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default='')
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class VehicleOrderSerializer(serializers.ModelSerializer):
    buyer_name = serializers.CharField(source='buyer.full_name', read_only=True)
    buyer_email = serializers.CharField(source='buyer.email', read_only=True)
    seller_name = serializers.CharField(source='seller.full_name', read_only=True)
    seller_email = serializers.CharField(source='seller.email', read_only=True)
    organisation_name = serializers.CharField(source='organisation.name', read_only=True, allow_null=True)
    confirmed_by_name = serializers.CharField(source='confirmed_by.full_name', read_only=True, allow_null=True)
    listing_title = serializers.CharField(source='listing.title', read_only=True)
    listing_image_url = serializers.CharField(source='listing.primary_image_url', read_only=True)
    is_payment_overdue = serializers.SerializerMethodField()
    latest_payment_report = serializers.SerializerMethodField()
    document_readiness = serializers.SerializerMethodField()

    class Meta:
        model = VehicleOrder
        fields = [
            'id',
            'order_number',
            'listing',
            'listing_title',
            'listing_image_url',
            'accepted_offer',
            'buyer',
            'buyer_name',
            'buyer_email',
            'seller',
            'seller_name',
            'seller_email',
            'organisation',
            'organisation_name',
            'status',
            'agreed_price',
            'currency',
            'handover_type',
            'handover_address',
            'payment_deadline',
            'market_timezone',
            'is_payment_overdue',
            'payment_submitted_at',
            'payment_confirmed_at',
            'confirmed_by',
            'confirmed_by_name',
            'latest_payment_report',
            'document_readiness',
            'listing_snapshot',
            'cancellation_reason',
            'cancelled_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_is_payment_overdue(self, obj) -> bool:
        return obj.status == VehicleOrderStatusChoices.PAYMENT_PENDING and obj.payment_deadline < timezone.now()

    def get_latest_payment_report(self, obj):
        latest = obj.payment_reports.first()
        if latest:
            return VehiclePaymentReportSerializer(latest).data
        return None

    def get_document_readiness(self, obj):
        from apps.marketplace.vehicle_documents_service import get_vehicle_order_document_readiness
        try:
            return get_vehicle_order_document_readiness(obj)
        except Exception:
            return None


class VehicleDocumentReviewEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source='actor.full_name', read_only=True, allow_null=True)
    actor_email = serializers.CharField(source='actor.email', read_only=True, allow_null=True)

    class Meta:
        model = VehicleDocumentReviewEvent
        fields = [
            'id',
            'event_type',
            'previous_status',
            'new_status',
            'actor',
            'actor_name',
            'actor_email',
            'notes',
            'metadata',
            'created_at',
        ]
        read_only_fields = fields


class VehiclePurchaseDocumentSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    submitted_by_name = serializers.CharField(source='submitted_by.full_name', read_only=True)
    submitted_by_email = serializers.CharField(source='submitted_by.email', read_only=True)
    verified_by_name = serializers.CharField(source='verified_by.full_name', read_only=True, allow_null=True)
    download_url = serializers.SerializerMethodField()
    review_events = VehicleDocumentReviewEventSerializer(many=True, read_only=True)
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = VehiclePurchaseDocument
        fields = [
            'id',
            'order',
            'category',
            'category_display',
            'document_owner_role',
            'version_number',
            'submitted_by',
            'submitted_by_name',
            'submitted_by_email',
            'original_filename',
            'mime_type',
            'file_size',
            'document_expiry_date',
            'status',
            'verified_by',
            'verified_by_name',
            'verified_at',
            'rejection_reason',
            'rejection_notes',
            'is_latest',
            'is_expired',
            'download_url',
            'review_events',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_download_url(self, obj) -> str:
        return f"/api/v1/marketplace/vehicle-orders/{obj.order_id}/documents/{obj.id}/download/"


class VehiclePurchaseDocumentUploadSerializer(serializers.Serializer):
    category = serializers.ChoiceField(choices=VehicleDocumentCategoryChoices.choices)
    file = serializers.FileField(required=True)
    document_expiry_date = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class VehiclePurchaseDocumentVerificationSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['APPROVE', 'REJECT'])
    rejection_reason = serializers.CharField(required=False, allow_blank=True, default='')
    notes = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, attrs):
        if attrs.get('action') == 'REJECT':
            reason = attrs.get('rejection_reason', '').strip()
            if not reason:
                raise serializers.ValidationError({
                    "rejection_reason": "A documented rejection reason is required when rejecting a document."
                })
        return attrs


# ---------------------------------------------------------------------------
# Phase 7.1: Dealer Bulk Upload Serializers
# ---------------------------------------------------------------------------


class BulkUploadRowErrorSerializer(serializers.ModelSerializer):
    class Meta:
        model = BulkUploadRowError
        fields = [
            'id',
            'job',
            'row_number',
            'field_name',
            'error_code',
            'error_message',
            'raw_data',
            'is_resolved',
            'created_at',
        ]
        read_only_fields = fields


class BulkUploadJobSerializer(serializers.ModelSerializer):
    seller_name = serializers.CharField(source='seller.full_name', read_only=True, allow_null=True)
    organisation_name = serializers.CharField(source='organisation.name', read_only=True, allow_null=True)
    progress_percentage = serializers.IntegerField(read_only=True)
    is_finished = serializers.BooleanField(read_only=True)

    class Meta:
        model = BulkUploadJob
        fields = [
            'id',
            'seller',
            'seller_name',
            'organisation',
            'organisation_name',
            'upload_type',
            'status',
            'duplicate_policy',
            'filename',
            'file_size_bytes',
            'total_rows',
            'processed_rows',
            'successful_rows',
            'failed_rows',
            'duplicate_rows',
            'progress_percentage',
            'is_finished',
            'started_at',
            'completed_at',
            'error_summary',
            'created_at',
        ]
        read_only_fields = fields


class BulkUploadSubmitSerializer(serializers.Serializer):
    file = serializers.FileField(required=True)
    upload_type = serializers.ChoiceField(choices=BulkUploadTypeChoices.choices, required=True)
    duplicate_policy = serializers.ChoiceField(
        choices=[
            (BulkUploadDuplicatePolicy.SKIP.value, 'Skip Duplicates'),
            (BulkUploadDuplicatePolicy.FAIL_ROW.value, 'Mark Row as Error'),
        ],
        default=BulkUploadDuplicatePolicy.SKIP.value,
        required=False,
    )
    organisation = serializers.PrimaryKeyRelatedField(
        queryset=Organisation.objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )

    def validate_file(self, value):
        max_size = 15 * 1024 * 1024  # 15 MB
        if value.size > max_size:
            raise serializers.ValidationError(
                f"File size ({value.size / (1024 * 1024):.2f} MB) exceeds maximum allowed limit of 15 MB."
            )

        name = value.name.lower()
        if not (name.endswith('.csv') or name.endswith('.txt')):
            raise serializers.ValidationError("Only CSV text files (.csv) are accepted.")

        pos = value.tell() if hasattr(value, 'tell') else 0
        header = value.read(4096)
        if hasattr(value, 'seek'):
            value.seek(pos)

        if b'\x00' in header:
            raise serializers.ValidationError("File contains binary data. Please upload a genuine plain text CSV file.")

        return value


# ==============================================================================
# PHASE 7.2: SPONSORED LISTINGS & ADVERTISING SERIALIZERS
# ==============================================================================

from typing import Optional, Dict, Any, List
from apps.marketplace.models import (
    AdvertisingCampaign,
    SponsoredListing,
    CampaignPayment,
    CampaignImpression,
    CampaignClick,
    CampaignDailyMetric,
    CampaignTypeChoices,
    CampaignStatusChoices,
    CampaignPaymentStatusChoices,
)
from apps.marketplace.advertising_pricing import (
    calculate_campaign_pricing,
    normalize_advertising_country,
    ADVERTISING_PACKAGES,
)


class SponsoredListingSummarySerializer(serializers.ModelSerializer):
    """Summarized representation of a single sponsored listing attached to a campaign."""
    target_type = serializers.ReadOnlyField()
    impression_count = serializers.IntegerField(source='impressions_count', read_only=True)
    click_count = serializers.IntegerField(source='clicks_count', read_only=True)
    ctr_percentage = serializers.ReadOnlyField(source='click_through_rate')
    bid_weight = serializers.SerializerMethodField()
    listing_title = serializers.SerializerMethodField()
    listing_price = serializers.SerializerMethodField()
    listing_currency = serializers.SerializerMethodField()
    listing_image = serializers.SerializerMethodField()
    listing_status = serializers.SerializerMethodField()

    class Meta:
        model = SponsoredListing
        fields = [
            'id',
            'campaign',
            'target_type',
            'vehicle_listing',
            'part_listing',
            'bid_weight',
            'impression_count',
            'click_count',
            'ctr_percentage',
            'is_active',
            'created_at',
            'listing_title',
            'listing_price',
            'listing_currency',
            'listing_image',
            'listing_status',
        ]
        read_only_fields = fields

    def get_bid_weight(self, obj) -> int:
        return 1

    def get_ctr_percentage(self, obj) -> float:
        return obj.click_through_rate

    def get_listing_title(self, obj) -> str:
        if obj.target_type == CampaignTypeChoices.VEHICLES and obj.vehicle_listing:
            return obj.vehicle_listing.title or f"{obj.vehicle_listing.make} {obj.vehicle_listing.model}"
        elif obj.target_type == CampaignTypeChoices.SPARE_PARTS and obj.part_listing:
            return obj.part_listing.title or getattr(obj.part_listing.part, 'name', 'Spare Part')
        return "Unknown Listing"

    def get_listing_price(self, obj) -> Optional[str]:
        if obj.target_type == CampaignTypeChoices.VEHICLES and obj.vehicle_listing:
            return str(obj.vehicle_listing.price) if obj.vehicle_listing.price is not None else None
        elif obj.target_type == CampaignTypeChoices.SPARE_PARTS and obj.part_listing:
            return str(obj.part_listing.price) if obj.part_listing.price is not None else None
        return None

    def get_listing_currency(self, obj) -> str:
        if obj.target_type == CampaignTypeChoices.VEHICLES and obj.vehicle_listing:
            return obj.vehicle_listing.currency or 'GBP'
        elif obj.target_type == CampaignTypeChoices.SPARE_PARTS and obj.part_listing:
            return obj.part_listing.currency or 'GBP'
        return 'GBP'

    def get_listing_image(self, obj) -> Optional[str]:
        if obj.target_type == CampaignTypeChoices.VEHICLES and obj.vehicle_listing:
            images = getattr(obj.vehicle_listing, 'images', None)
            if images and hasattr(images, 'all'):
                first_img = images.filter(is_primary=True).first() or images.first()
                if first_img and hasattr(first_img, 'image'):
                    return getattr(first_img.image, 'url', None)
        elif obj.target_type == CampaignTypeChoices.SPARE_PARTS and obj.part_listing:
            images = getattr(obj.part_listing, 'images', None)
            if images and hasattr(images, 'all'):
                first_img = images.filter(is_primary=True).first() or images.first()
                if first_img and hasattr(first_img, 'image'):
                    return getattr(first_img.image, 'url', None)
        return None

    def get_listing_status(self, obj) -> str:
        if obj.target_type == CampaignTypeChoices.VEHICLES and obj.vehicle_listing:
            return str(obj.vehicle_listing.status)
        elif obj.target_type == CampaignTypeChoices.SPARE_PARTS and obj.part_listing:
            return str(obj.part_listing.status)
        return 'UNKNOWN'


class CampaignPaymentSummarySerializer(serializers.ModelSerializer):
    """Summary of payments associated with an advertising campaign."""
    class Meta:
        model = CampaignPayment
        fields = [
            'id',
            'provider',
            'gateway_reference',
            'gateway_payment_id',
            'amount_minor',
            'currency',
            'payment_status',
            'paid_at',
            'refund_amount_minor',
            'refunded_at',
            'created_at',
        ]
        read_only_fields = fields


class CampaignDailyMetricSerializer(serializers.ModelSerializer):
    """Daily performance metric aggregates for a campaign."""
    impressions_count = serializers.IntegerField(source='impressions', read_only=True)
    clicks_count = serializers.IntegerField(source='clicks', read_only=True)
    spend_amount_minor = serializers.IntegerField(source='spend_minor', read_only=True)
    ctr_percentage = serializers.SerializerMethodField()

    class Meta:
        model = CampaignDailyMetric
        fields = [
            'id',
            'date',
            'impressions',
            'impressions_count',
            'clicks',
            'clicks_count',
            'ctr_percentage',
            'spend_minor',
            'spend_amount_minor',
        ]
        read_only_fields = fields

    def get_ctr_percentage(self, obj) -> float:
        if obj.impressions > 0:
            return round((obj.clicks / obj.impressions) * 100.0, 2)
        return 0.0


class AdvertisingCampaignSerializer(serializers.ModelSerializer):
    """Comprehensive read representation of an Advertising Campaign."""
    seller_email = serializers.EmailField(source='seller.email', read_only=True)
    seller_name = serializers.SerializerMethodField()
    organisation_name = serializers.CharField(source='organisation.name', read_only=True, allow_null=True)
    approved_by_email = serializers.EmailField(source='approved_by.email', read_only=True, allow_null=True)
    sponsored_listings = SponsoredListingSummarySerializer(many=True, read_only=True)
    payments = CampaignPaymentSummarySerializer(many=True, read_only=True)
    listings_count = serializers.SerializerMethodField()
    remaining_budget_minor = serializers.ReadOnlyField()
    ctr_percentage = serializers.ReadOnlyField(source='ctr')
    total_impressions = serializers.IntegerField(source='impressions_count', read_only=True)
    total_clicks = serializers.IntegerField(source='clicks_count', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    payment_status_display = serializers.CharField(source='get_payment_status_display', read_only=True)
    campaign_type_display = serializers.CharField(source='get_campaign_type_display', read_only=True)
    duration_days = serializers.ReadOnlyField()
    approval_notes = serializers.CharField(source='review_notes', read_only=True)
    target_country = serializers.SerializerMethodField()
    net_amount_minor = serializers.SerializerMethodField()
    tax_amount_minor = serializers.SerializerMethodField()
    tax_rate_percent = serializers.SerializerMethodField()
    tax_regime = serializers.SerializerMethodField()
    sac_code = serializers.SerializerMethodField()
    rejected_at = serializers.SerializerMethodField()

    class Meta:
        model = AdvertisingCampaign
        fields = [
            'id',
            'seller',
            'seller_email',
            'seller_name',
            'organisation',
            'organisation_name',
            'title',
            'description',
            'campaign_type',
            'campaign_type_display',
            'status',
            'status_display',
            'payment_status',
            'payment_status_display',
            'currency',
            'target_country',
            'package_code',
            'duration_days',
            'start_date',
            'end_date',
            'total_budget_minor',
            'spent_amount_minor',
            'daily_rate_minor',
            'net_amount_minor',
            'tax_amount_minor',
            'tax_rate_percent',
            'tax_regime',
            'sac_code',
            'total_impressions',
            'total_clicks',
            'ctr_percentage',
            'remaining_budget_minor',
            'listings_count',
            'sponsored_listings',
            'payments',
            'approval_notes',
            'rejection_reason',
            'approved_by',
            'approved_by_email',
            'approved_at',
            'rejected_at',
            'payment_reference',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_seller_name(self, obj) -> str:
        if not obj.seller:
            return ""
        name = f"{getattr(obj.seller, 'first_name', '')} {getattr(obj.seller, 'last_name', '')}".strip()
        return name or obj.seller.email

    def get_listings_count(self, obj) -> int:
        return obj.sponsored_listings.count()

    def get_target_country(self, obj) -> str:
        if obj.organisation and getattr(obj.organisation, 'country', None):
            return obj.organisation.country
        return 'IN' if obj.currency == 'INR' else 'GB'

    def get_net_amount_minor(self, obj) -> int:
        country = self.get_target_country(obj)
        rate = Decimal('18.00') if country == 'IN' else Decimal('20.00')
        net = (Decimal(obj.total_budget_minor) / (Decimal('1.00') + (rate / Decimal('100.00')))).quantize(Decimal('1'))
        return int(net)

    def get_tax_amount_minor(self, obj) -> int:
        return max(0, obj.total_budget_minor - self.get_net_amount_minor(obj))

    def get_tax_rate_percent(self, obj) -> float:
        country = self.get_target_country(obj)
        return 18.0 if country == 'IN' else 20.0

    def get_tax_regime(self, obj) -> str:
        country = self.get_target_country(obj)
        return 'Indian GST' if country == 'IN' else 'UK VAT'

    def get_sac_code(self, obj) -> str:
        country = self.get_target_country(obj)
        return '998365' if country == 'IN' else ''

    def get_rejected_at(self, obj):
        return obj.updated_at if obj.status == CampaignStatusChoices.REJECTED else None


class AdvertisingCampaignCreateSerializer(serializers.Serializer):
    """Validates creation of a new advertising campaign by a seller."""
    title = serializers.CharField(max_length=200, required=True)
    description = serializers.CharField(required=False, allow_blank=True, default='')
    campaign_type = serializers.ChoiceField(choices=CampaignTypeChoices.choices, required=True)
    target_country = serializers.ChoiceField(choices=[('GB', 'United Kingdom'), ('IN', 'India')], required=True)
    currency = serializers.ChoiceField(choices=[('GBP', 'GBP'), ('INR', 'INR')], required=True)
    package_code = serializers.ChoiceField(
        choices=['7_DAYS', '14_DAYS', '30_DAYS', 'CUSTOM'],
        default='7_DAYS',
    )
    duration_days = serializers.IntegerField(required=False, min_value=3, max_value=90, allow_null=True)
    start_date = serializers.DateField(required=False, allow_null=True)
    listing_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=True,
        min_length=1,
        max_length=100,
    )
    organisation = serializers.PrimaryKeyRelatedField(
        queryset=Organisation.objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )

    def validate(self, attrs):
        user = self.context['request'].user
        country = normalize_advertising_country(attrs['target_country'])
        attrs['target_country'] = country
        currency = attrs['currency'].strip().upper()

        if country == 'GB' and currency != 'GBP':
            raise serializers.ValidationError({"currency": "Campaigns targeting United Kingdom (GB) must use GBP currency."})
        elif country == 'IN' and currency != 'INR':
            raise serializers.ValidationError({"currency": "Campaigns targeting India (IN) must use INR currency."})

        package_code = attrs.get('package_code', 'CUSTOM')
        pkg_alias_map = {
            '7_DAYS': 7,
            '14_DAYS': 14,
            '30_DAYS': 30,
            'AD_PKG_7D': 7,
            'AD_PKG_14D': 14,
            'AD_PKG_30D': 30,
        }
        if package_code in pkg_alias_map:
            attrs['duration_days'] = pkg_alias_map[package_code]
        else:
            duration = attrs.get('duration_days')
            if not duration or not (3 <= duration <= 90):
                raise serializers.ValidationError(
                    {"duration_days": "Custom package duration must be specified between 3 and 90 days."}
                )

        start_date = attrs.get('start_date')
        today = timezone.localdate()
        if start_date and start_date < today:
            raise serializers.ValidationError({"start_date": "Campaign start date cannot be in the past."})

        # Validate organisation membership if provided
        org = attrs.get('organisation')
        if org:
            is_member = OrganisationMembership.objects.filter(
                organisation=org,
                user=user,
                is_active=True,
            ).exists()
            if not is_member and not user.is_staff:
                raise serializers.ValidationError({"organisation": "You are not an active member of this organisation."})

        # Validate listing IDs exist, match campaign type, and are owned by user/org
        campaign_type = attrs['campaign_type']
        listing_ids = attrs['listing_ids']

        if campaign_type == CampaignTypeChoices.VEHICLES:
            qs = VehicleListing.objects.filter(id__in=listing_ids)
            if org:
                qs = qs.filter(organisation=org)
            else:
                qs = qs.filter(seller=user)
            found_count = qs.count()
            if found_count != len(listing_ids):
                raise serializers.ValidationError(
                    {"listing_ids": f"Only {found_count} of {len(listing_ids)} vehicle listings were found belonging to your account."}
                )
            unapproved = qs.exclude(status=ListingStatusChoices.APPROVED).count()
            if unapproved > 0:
                raise serializers.ValidationError(
                    {"listing_ids": f"{unapproved} selected vehicle listing(s) are not in APPROVED state. Only approved listings can be sponsored."}
                )
        elif campaign_type == CampaignTypeChoices.SPARE_PARTS:
            qs = SparePartListing.objects.filter(id__in=listing_ids)
            if org:
                qs = qs.filter(organisation=org)
            else:
                qs = qs.filter(seller=user)
            found_count = qs.count()
            if found_count != len(listing_ids):
                raise serializers.ValidationError(
                    {"listing_ids": f"Only {found_count} of {len(listing_ids)} spare-part listings were found belonging to your account."}
                )
            unapproved = qs.exclude(status=ListingStatusChoices.APPROVED).count()
            if unapproved > 0:
                raise serializers.ValidationError(
                    {"listing_ids": f"{unapproved} selected spare-part listing(s) are not in APPROVED state. Only approved listings can be sponsored."}
                )

        return attrs


class AdvertisingCampaignUpdateSerializer(serializers.Serializer):
    """Allows modifying title, description, or start_date of a DRAFT campaign."""
    title = serializers.CharField(max_length=200, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    start_date = serializers.DateField(required=False, allow_null=True)
    package_code = serializers.ChoiceField(
        choices=['7_DAYS', '14_DAYS', '30_DAYS', 'CUSTOM'],
        required=False,
    )
    duration_days = serializers.IntegerField(required=False, min_value=3, max_value=90)
    listing_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        min_length=1,
        max_length=100,
    )


class CampaignPricingQuoteRequestSerializer(serializers.Serializer):
    """Dynamic pricing calculator request serializer."""
    currency = serializers.ChoiceField(choices=['GBP', 'INR'], required=True)
    duration_days = serializers.IntegerField(min_value=3, max_value=90, required=False)
    package_code = serializers.ChoiceField(choices=['7_DAYS', '14_DAYS', '30_DAYS', 'CUSTOM'], default='7_DAYS')
    target_country = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, attrs):
        currency = attrs['currency'].strip().upper()
        country = attrs.get('target_country') or ('GB' if currency == 'GBP' else 'IN')
        attrs['target_country'] = normalize_advertising_country(country)

        package_code = attrs.get('package_code', 'CUSTOM')
        pkg_alias_map = {
            '7_DAYS': 7,
            '14_DAYS': 14,
            '30_DAYS': 30,
            'AD_PKG_7D': 7,
            'AD_PKG_14D': 14,
            'AD_PKG_30D': 30,
        }
        if package_code in pkg_alias_map:
            attrs['duration_days'] = pkg_alias_map[package_code]
        elif not attrs.get('duration_days'):
            attrs['duration_days'] = 7
        return attrs


class CampaignReviewSerializer(serializers.Serializer):
    """Validates admin approval or rejection of an advertising campaign."""
    action = serializers.ChoiceField(choices=['APPROVE', 'REJECT'], required=True)
    rejection_reason = serializers.CharField(required=False, allow_blank=True, default='')
    notes = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, attrs):
        if attrs['action'] == 'REJECT':
            reason = attrs.get('rejection_reason', '').strip()
            if not reason:
                raise serializers.ValidationError({"rejection_reason": "A detailed rejection reason is mandatory when rejecting a campaign."})
        return attrs


class TrackImpressionSerializer(serializers.Serializer):
    """Validates impression tracking payload."""
    sponsored_listing_id = serializers.UUIDField(required=True)
    session_id = serializers.CharField(max_length=128, required=True)
    referrer = serializers.CharField(max_length=500, required=False, allow_blank=True, default='')
    user_agent = serializers.CharField(max_length=500, required=False, allow_blank=True, default='')


class TrackClickSerializer(serializers.Serializer):
    """Validates click tracking payload."""
    sponsored_listing_id = serializers.UUIDField(required=True)
    session_id = serializers.CharField(max_length=128, required=True)
    destination_url = serializers.CharField(max_length=500, required=False, allow_blank=True, default='')


