from decimal import Decimal
from datetime import date

from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone

from apps.workshops.models import (
    WorkshopProfile,
    WorkshopOperatingHours,
    WorkshopServiceCategory,
    WorkshopService,
    WorkshopBooking,
    BookingServiceItem,
    WorkshopQuotation,
    QuotationLineItem,
    DayOfWeekChoices,
    BookingStatusChoices,
    QuotationStatusChoices,
    LineItemTypeChoices,
)
from apps.garage.models import GarageVehicle
from apps.catalogue.models import Part


class WorkshopServiceCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkshopServiceCategory
        fields = [
            'id',
            'name',
            'slug',
            'description',
            'icon_name',
            'display_order',
            'is_active',
        ]


class WorkshopOperatingHoursSerializer(serializers.ModelSerializer):
    day_name = serializers.SerializerMethodField()

    class Meta:
        model = WorkshopOperatingHours
        fields = [
            'id',
            'day_of_week',
            'day_name',
            'is_closed',
            'open_time',
            'close_time',
            'slot_duration_minutes',
        ]

    def get_day_name(self, obj) -> str:
        return DayOfWeekChoices(obj.day_of_week).label


class WorkshopServiceSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model = WorkshopService
        fields = [
            'id',
            'workshop',
            'category',
            'category_name',
            'name',
            'description',
            'estimated_duration_minutes',
            'base_price',
            'currency',
            'is_price_variable',
            'is_active',
        ]
        read_only_fields = ['id', 'workshop']


class WorkshopProfilePublicSerializer(serializers.ModelSerializer):
    organisation_name = serializers.CharField(source='organisation.name', read_only=True)
    organisation_slug = serializers.CharField(source='organisation.slug', read_only=True)
    display_name = serializers.CharField(read_only=True)
    services = serializers.SerializerMethodField()
    operating_hours = serializers.SerializerMethodField()

    class Meta:
        model = WorkshopProfile
        fields = [
            'id',
            'organisation_id',
            'organisation_name',
            'organisation_slug',
            'business_name',
            'display_name',
            'slug',
            'description',
            'contact_email',
            'contact_phone',
            'address_line1',
            'address_line2',
            'city',
            'state_province',
            'postal_code',
            'country',
            'latitude',
            'longitude',
            'currency',
            'bay_capacity',
            'is_accepting_bookings',
            'is_verified',
            'is_tax_registered',
            'services',
            'operating_hours',
            'created_at',
        ]

    def get_services(self, obj):
        active_services = obj.services.filter(is_active=True).select_related('category')
        return WorkshopServiceSerializer(active_services, many=True).data

    def get_operating_hours(self, obj):
        hours = obj.operating_hours.all().order_by('day_of_week')
        return WorkshopOperatingHoursSerializer(hours, many=True).data


class WorkshopProfileManageSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkshopProfile
        fields = [
            'id',
            'business_name',
            'description',
            'contact_email',
            'contact_phone',
            'address_line1',
            'address_line2',
            'city',
            'state_province',
            'postal_code',
            'country',
            'latitude',
            'longitude',
            'currency',
            'bay_capacity',
            'is_accepting_bookings',
            'is_tax_registered',
            'default_tax_rate_percent',
        ]


class BookingServiceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookingServiceItem
        fields = [
            'id',
            'service',
            'service_name',
            'service_price',
            'currency',
        ]


class QuotationLineItemSerializer(serializers.ModelSerializer):
    item_type_display = serializers.CharField(source='get_item_type_display', read_only=True)
    catalogue_part_name = serializers.SerializerMethodField()

    class Meta:
        model = QuotationLineItem
        fields = [
            'id',
            'item_type',
            'item_type_display',
            'description',
            'part_number',
            'catalogue_part',
            'catalogue_part_name',
            'quantity',
            'unit_price',
            'line_total',
        ]

    def get_catalogue_part_name(self, obj) -> str | None:
        if obj.catalogue_part:
            return f"{obj.catalogue_part.brand} {obj.catalogue_part.name}"
        return None


class WorkshopQuotationSerializer(serializers.ModelSerializer):
    line_items = QuotationLineItemSerializer(many=True, read_only=True)
    booking_number = serializers.CharField(source='booking.booking_number', read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = WorkshopQuotation
        fields = [
            'id',
            'quotation_number',
            'booking',
            'booking_number',
            'version',
            'status',
            'subtotal_labour',
            'subtotal_parts',
            'subtotal_other',
            'discount_amount',
            'tax_rate_percent',
            'tax_amount',
            'total_amount',
            'currency',
            'valid_until',
            'workshop_notes',
            'terms_and_conditions',
            'customer_rejection_reason',
            'created_by',
            'created_by_name',
            'issued_at',
            'accepted_at',
            'rejected_at',
            'line_items',
            'created_at',
            'updated_at',
        ]

    def get_created_by_name(self, obj) -> str | None:
        if obj.created_by:
            return obj.created_by.full_name or obj.created_by.email
        return None


class QuotationLineItemInputSerializer(serializers.Serializer):
    item_type = serializers.ChoiceField(choices=LineItemTypeChoices.choices, default=LineItemTypeChoices.LABOUR)
    description = serializers.CharField(max_length=255)
    part_number = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    catalogue_part_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1.00'))
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))


class QuotationCreateUpdateSerializer(serializers.Serializer):
    discount_amount = serializers.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    tax_rate_percent = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)
    valid_until = serializers.DateField(required=False, allow_null=True)
    workshop_notes = serializers.CharField(required=False, allow_blank=True, default='')
    terms_and_conditions = serializers.CharField(required=False, allow_blank=True, default='')
    line_items = QuotationLineItemInputSerializer(many=True, required=True)

    def validate_line_items(self, value):
        if not value:
            raise serializers.ValidationError("Quotation must include at least one line item.")
        return value


class WorkshopBookingDetailSerializer(serializers.ModelSerializer):
    service_items = BookingServiceItemSerializer(many=True, read_only=True)
    quotations = serializers.SerializerMethodField()
    active_quotation = serializers.SerializerMethodField()
    workshop_name = serializers.CharField(source='workshop.display_name', read_only=True)
    workshop_city = serializers.CharField(source='workshop.city', read_only=True)
    workshop_phone = serializers.CharField(source='workshop.contact_phone', read_only=True)
    workshop_email = serializers.CharField(source='workshop.contact_email', read_only=True)
    buyer_name = serializers.SerializerMethodField()
    buyer_email = serializers.CharField(source='buyer.email', read_only=True)
    assigned_technician_name = serializers.SerializerMethodField()

    class Meta:
        model = WorkshopBooking
        fields = [
            'id',
            'booking_number',
            'workshop',
            'workshop_name',
            'workshop_city',
            'workshop_phone',
            'workshop_email',
            'buyer',
            'buyer_name',
            'buyer_email',
            'vehicle',
            'vehicle_make',
            'vehicle_model',
            'vehicle_year',
            'vehicle_registration_plate',
            'vehicle_vin',
            'current_odometer',
            'odometer_unit',
            'preferred_date',
            'preferred_time_slot',
            'scheduled_appointment_start',
            'scheduled_appointment_end',
            'customer_notes',
            'reported_faults',
            'assigned_technician',
            'assigned_technician_name',
            'internal_notes',
            'status',
            'rejection_reason',
            'cancellation_reason',
            'cancelled_at',
            'service_items',
            'quotations',
            'active_quotation',
            'created_at',
            'updated_at',
        ]

    def get_buyer_name(self, obj) -> str:
        return obj.buyer.full_name or obj.buyer.email

    def get_assigned_technician_name(self, obj) -> str | None:
        if obj.assigned_technician:
            return obj.assigned_technician.full_name or obj.assigned_technician.email
        return None

    def get_quotations(self, obj):
        # Return all quotations ordered by version desc
        quotes = obj.quotations.all().order_by('-version')
        return WorkshopQuotationSerializer(quotes, many=True).data

    def get_active_quotation(self, obj):
        # Look for ACCEPTED, then ISSUED, then latest DRAFT
        accepted = obj.quotations.filter(status=QuotationStatusChoices.ACCEPTED).first()
        if accepted:
            return WorkshopQuotationSerializer(accepted).data
        issued = obj.quotations.filter(status=QuotationStatusChoices.ISSUED).first()
        if issued:
            return WorkshopQuotationSerializer(issued).data
        latest_draft = obj.quotations.filter(status=QuotationStatusChoices.DRAFT).order_by('-version').first()
        if latest_draft:
            return WorkshopQuotationSerializer(latest_draft).data
        return None


class BuyerBookingCreateSerializer(serializers.Serializer):
    workshop_id = serializers.UUIDField(required=True)
    vehicle_id = serializers.UUIDField(required=True)
    service_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
    )
    preferred_date = serializers.DateField(required=True)
    preferred_time_slot = serializers.CharField(max_length=50, required=False, allow_blank=True, default='')
    customer_notes = serializers.CharField(required=False, allow_blank=True, default='')
    reported_faults = serializers.CharField(required=False, allow_blank=True, default='')

    def validate_preferred_date(self, value):
        if value < timezone.now().date():
            raise serializers.ValidationError("Preferred appointment date cannot be in the past.")
        return value

    def validate_workshop_id(self, value):
        try:
            profile = WorkshopProfile.objects.get(id=value)
            if not profile.is_accepting_bookings:
                raise serializers.ValidationError("This workshop is currently not accepting new booking requests.")
            return value
        except WorkshopProfile.DoesNotExist:
            raise serializers.ValidationError("Specified workshop does not exist.")

    def validate_vehicle_id(self, value):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        try:
            vehicle = GarageVehicle.objects.get(id=value)
            if user and vehicle.user_id != user.id:
                raise serializers.ValidationError("Selected vehicle does not belong to your garage account.")
            if vehicle.is_archived:
                raise serializers.ValidationError("Cannot request a service booking for an archived vehicle.")
            return value
        except GarageVehicle.DoesNotExist:
            raise serializers.ValidationError("Specified garage vehicle does not exist.")


class BookingStatusUpdateSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['ACCEPT', 'REJECT', 'SCHEDULE'])
    rejection_reason = serializers.CharField(required=False, allow_blank=True, default='')
    scheduled_appointment_start = serializers.DateTimeField(required=False, allow_null=True)
    scheduled_appointment_end = serializers.DateTimeField(required=False, allow_null=True)
    assigned_technician_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    internal_notes = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, attrs):
        action = attrs.get('action')
        if action == 'REJECT' and not attrs.get('rejection_reason'):
            raise serializers.ValidationError({"rejection_reason": "A rejection reason is mandatory when rejecting a booking."})
        if action == 'SCHEDULE':
            start = attrs.get('scheduled_appointment_start')
            end = attrs.get('scheduled_appointment_end')
            if not start or not end:
                raise serializers.ValidationError("Both scheduled appointment start and end times are required.")
            if end <= start:
                raise serializers.ValidationError({"scheduled_appointment_end": "End time must be after start time."})
        return attrs


class BookingCancellationSerializer(serializers.Serializer):
    reason = serializers.CharField(required=True, min_length=5, max_length=1000)


class QuotationResponseSerializer(serializers.Serializer):
    rejection_reason = serializers.CharField(required=False, allow_blank=True, default='')
