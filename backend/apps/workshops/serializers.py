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
    WorkOrder,
    WorkOrderTask,
    WorkOrderPartUsage,
    WorkOrderStatusChoices,
    WorkOrderTaskStatusChoices,
    ChangeOrder,
    ChangeOrderLineItem,
    ChangeOrderStatusChoices,
    WorkshopReview,
    ReviewStatusChoices,
    WorkshopConversation,
    WorkshopMessage,
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

    def validate_currency(self, value):
        if value:
            clean = value.strip().upper()
            workshop = self.context.get('workshop')
            if not workshop and self.instance:
                workshop = self.instance.workshop
            if workshop and clean != workshop.currency.upper():
                raise serializers.ValidationError(
                    f"Conflicting currency '{clean}' rejected. Service must use workshop currency '{workshop.currency}'."
                )
            return clean
        return value


class WorkshopProfilePublicSerializer(serializers.ModelSerializer):
    organisation_name = serializers.CharField(source='organisation.name', read_only=True)
    organisation_slug = serializers.CharField(source='organisation.slug', read_only=True)
    display_name = serializers.CharField(read_only=True)
    services = serializers.SerializerMethodField()
    operating_hours = serializers.SerializerMethodField()
    average_rating = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()

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
            'can_collect_tax',
            'default_tax_rate_percent',
            'requires_deposit',
            'default_deposit_percentage',
            'average_rating',
            'review_count',
            'services',
            'operating_hours',
            'created_at',
        ]

    def get_average_rating(self, obj) -> float:
        if hasattr(obj, 'avg_rating') and obj.avg_rating is not None:
            return round(float(obj.avg_rating), 2)
        from django.db.models import Avg
        avg = obj.reviews.filter(status=ReviewStatusChoices.APPROVED).aggregate(Avg('rating'))['rating__avg']
        return round(float(avg), 2) if avg is not None else 0.0

    def get_review_count(self, obj) -> int:
        if hasattr(obj, 'total_reviews'):
            return obj.total_reviews
        return obj.reviews.filter(status=ReviewStatusChoices.APPROVED).count()

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
            'can_collect_tax',
            'default_tax_rate_percent',
            'requires_deposit',
            'default_deposit_percentage',
        ]
        read_only_fields = ['can_collect_tax']

    def validate(self, attrs):
        attrs = super().validate(attrs)
        # Server-side enforcement: workshop operators cannot grant themselves tax collection authorization
        if 'can_collect_tax' in self.initial_data:
            request = self.context.get('request')
            user = getattr(request, 'user', None)
            from apps.workshops.permissions import is_platform_admin_or_staff
            if not (user and is_platform_admin_or_staff(user)):
                raise serializers.ValidationError({
                    'can_collect_tax': "Workshop owners and operators cannot grant themselves tax collection authorization. This requires platform administrator verification."
                })
        instance = getattr(self, 'instance', None)
        can_collect = attrs.get('can_collect_tax', getattr(instance, 'can_collect_tax', False))
        is_registered = attrs.get('is_tax_registered', getattr(instance, 'is_tax_registered', False))
        if can_collect and not is_registered:
            raise serializers.ValidationError({
                'can_collect_tax': "Cannot authorize tax collection for a workshop that is not tax registered."
            })
        return attrs

    def validate_currency(self, value):
        if value:
            clean = value.strip().upper()
            if self.instance and self.instance.organisation_id:
                expected = self.instance.organisation.regional_specification.default_currency.value
                if clean != expected:
                    raise serializers.ValidationError(
                        f"Currency '{clean}' conflicts with workshop organisation currency '{expected}'."
                    )
            return clean
        return value


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
            'tax_breakdown',
            'total_amount',
            'currency',
            'requires_deposit',
            'deposit_percentage',
            'deposit_amount',
            'deposit_status',
            'deposit_paid_at',
            'deposit_provider',
            'deposit_transaction_id',
            'deposit_order_id',
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
    currency = serializers.CharField(max_length=3, required=False, allow_blank=True)
    discount_amount = serializers.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    tax_rate_percent = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)
    valid_until = serializers.DateField(required=False, allow_null=True)
    workshop_notes = serializers.CharField(required=False, allow_blank=True, default='')
    terms_and_conditions = serializers.CharField(required=False, allow_blank=True, default='')
    requires_deposit = serializers.BooleanField(required=False, default=None)
    deposit_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=None)
    deposit_amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=None)
    line_items = QuotationLineItemInputSerializer(many=True, required=True)

    def validate_currency(self, value):
        if value:
            clean = value.strip().upper()
            booking = self.context.get('booking')
            if booking and clean != booking.workshop.currency.upper():
                raise serializers.ValidationError(
                    f"Conflicting quotation currency '{clean}' rejected. Must match workshop currency '{booking.workshop.currency}'."
                )
            return clean
        return value

    def validate_line_items(self, value):
        if not value:
            raise serializers.ValidationError("Quotation must include at least one line item.")
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        tax_rate = attrs.get('tax_rate_percent')
        booking = self.context.get('booking')
        if booking and booking.workshop and tax_rate is not None and tax_rate > Decimal('0.00'):
            if not getattr(booking.workshop, 'can_collect_tax', False):
                raise serializers.ValidationError({
                    'tax_rate_percent': f"Workshop '{booking.workshop.display_name}' is not authorized to collect tax. Quotation tax rate must be 0.00%."
                })
        return attrs


class QuotationDepositSessionCreateSerializer(serializers.Serializer):
    preferred_provider = serializers.CharField(max_length=50, required=False, allow_blank=True, default='')
    return_url = serializers.CharField(max_length=500, required=False, allow_blank=True, default='')
    cancel_url = serializers.CharField(max_length=500, required=False, allow_blank=True, default='')


class QuotationDepositVerifySerializer(serializers.Serializer):
    razorpay_payment_id = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    razorpay_order_id = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    razorpay_signature = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    payment_intent_id = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    stripe_payment_intent_id = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    client_secret = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=None)
    currency = serializers.CharField(max_length=3, required=False, allow_blank=True, default='')
    preferred_provider = serializers.CharField(max_length=50, required=False, allow_blank=True, default='')



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
            'work_order_id',
            'work_order_number',
            'work_order_status',
            'work_order_technician',
            'work_order_tasks_count',
            'work_order_created_at',
            'work_order',
            'has_review',
            'review_id',
            'review_rating',
            'is_review_eligible',
            'audit_logs',
            'created_at',
            'updated_at',
        ]

    work_order_id = serializers.SerializerMethodField()
    work_order_number = serializers.SerializerMethodField()
    work_order_status = serializers.SerializerMethodField()
    work_order_technician = serializers.SerializerMethodField()
    work_order_tasks_count = serializers.SerializerMethodField()
    work_order_created_at = serializers.SerializerMethodField()
    work_order = serializers.SerializerMethodField()
    has_review = serializers.SerializerMethodField()
    review_id = serializers.SerializerMethodField()
    review_rating = serializers.SerializerMethodField()
    is_review_eligible = serializers.SerializerMethodField()
    audit_logs = serializers.SerializerMethodField()

    def get_has_review(self, obj) -> bool:
        return hasattr(obj, 'review') and obj.review is not None

    def get_review_id(self, obj) -> str | None:
        return str(obj.review.id) if hasattr(obj, 'review') and obj.review else None

    def get_review_rating(self, obj) -> int | None:
        return obj.review.rating if hasattr(obj, 'review') and obj.review else None

    def get_is_review_eligible(self, obj) -> bool:
        if hasattr(obj, 'review') and obj.review:
            return False
        if not hasattr(obj, 'work_order') or not obj.work_order:
            return False
        return obj.work_order.status == WorkOrderStatusChoices.COMPLETED

    def get_work_order_id(self, obj):
        return str(obj.work_order.id) if hasattr(obj, 'work_order') and obj.work_order else None

    def get_work_order_number(self, obj):
        return obj.work_order.work_order_number if hasattr(obj, 'work_order') and obj.work_order else None

    def get_work_order_status(self, obj):
        return obj.work_order.status if hasattr(obj, 'work_order') and obj.work_order else None

    def get_work_order_technician(self, obj) -> str | None:
        if hasattr(obj, 'work_order') and obj.work_order and obj.work_order.lead_technician:
            return obj.work_order.lead_technician.full_name or obj.work_order.lead_technician.email
        return None

    def get_work_order_tasks_count(self, obj) -> int:
        if hasattr(obj, 'work_order') and obj.work_order:
            return obj.work_order.tasks.count()
        return 0

    def get_work_order_created_at(self, obj) -> str | None:
        if hasattr(obj, 'work_order') and obj.work_order and obj.work_order.created_at:
            return obj.work_order.created_at.isoformat()
        return None

    def get_work_order(self, obj):
        if hasattr(obj, 'work_order') and obj.work_order:
            return WorkOrderSerializer(obj.work_order).data
        return None

    def get_audit_logs(self, obj):
        try:
            from platform_core.audit.models import AuditLog
            ids = [str(obj.id)]
            for q in obj.quotations.all():
                ids.append(str(q.id))
            if hasattr(obj, 'work_order') and obj.work_order:
                ids.append(str(obj.work_order.id))
            logs = AuditLog.objects.filter(resource_id__in=ids).order_by('-created_at')[:25]
            return [
                {
                    'id': str(l.id),
                    'event_type': l.event_type,
                    'action': l.action,
                    'created_at': l.created_at.isoformat() if l.created_at else None,
                    'status': l.status,
                    'metadata': l.metadata or {},
                }
                for l in logs
            ]
        except Exception:
            return []

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



class WorkOrderTaskSerializer(serializers.ModelSerializer):
    assigned_technician_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = WorkOrderTask
        fields = [
            'id',
            'work_order',
            'description',
            'assigned_technician',
            'assigned_technician_name',
            'estimated_labour_minutes',
            'actual_labour_minutes',
            'status',
            'status_display',
            'started_at',
            'completed_at',
            'notes',
            'order_index',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_assigned_technician_name(self, obj):
        if obj.assigned_technician:
            return obj.assigned_technician.full_name or obj.assigned_technician.email
        return None


class WorkOrderPartUsageSerializer(serializers.ModelSerializer):
    added_by_name = serializers.SerializerMethodField()

    class Meta:
        model = WorkOrderPartUsage
        fields = [
            'id',
            'work_order',
            'part_name',
            'part_number',
            'description',
            'catalogue_part',
            'inventory_item',
            'is_stock_deducted',
            'quantity',
            'unit_cost',
            'total_cost',
            'usage_date',
            'added_by',
            'added_by_name',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'total_cost', 'created_at', 'updated_at']

    def get_added_by_name(self, obj):
        if obj.added_by:
            return obj.added_by.full_name or obj.added_by.email
        return None


class WorkOrderListSerializer(serializers.ModelSerializer):
    workshop_name = serializers.CharField(source='workshop.display_name', read_only=True)
    booking_number = serializers.CharField(source='booking.booking_number', read_only=True)
    quotation_number = serializers.CharField(source='quotation.quotation_number', read_only=True)
    buyer_name = serializers.SerializerMethodField()
    lead_technician_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    total_parts_cost = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total_actual_labour_minutes = serializers.IntegerField(read_only=True)
    total_estimated_labour_minutes = serializers.IntegerField(read_only=True)
    task_count = serializers.SerializerMethodField()
    authorized_total_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    approved_change_orders_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    has_pending_change_orders = serializers.BooleanField(read_only=True)
    vehicle_odometer_unit = serializers.SerializerMethodField()
    odometer_unit_mismatch = serializers.SerializerMethodField()

    def get_vehicle_odometer_unit(self, obj):
        if obj.vehicle and getattr(obj.vehicle, 'odometer_unit', None):
            return obj.vehicle.odometer_unit
        return None

    def get_odometer_unit_mismatch(self, obj):
        if obj.vehicle and getattr(obj.vehicle, 'odometer_unit', None) and obj.odometer_unit:
            return obj.vehicle.odometer_unit.strip().lower() != obj.odometer_unit.strip().lower()
        return False

    class Meta:
        model = WorkOrder
        fields = [
            'id',
            'work_order_number',
            'booking',
            'booking_number',
            'quotation',
            'quotation_number',
            'workshop',
            'workshop_name',
            'buyer',
            'buyer_name',
            'vehicle',
            'vehicle_make',
            'vehicle_model',
            'vehicle_year',
            'vehicle_registration_plate',
            'lead_technician',
            'lead_technician_name',
            'status',
            'status_display',
            'started_at',
            'completed_at',
            'total_parts_cost',
            'total_actual_labour_minutes',
            'total_estimated_labour_minutes',
            'task_count',
            'authorized_total_amount',
            'approved_change_orders_amount',
            'has_pending_change_orders',
            'vehicle_odometer_unit',
            'odometer_unit_mismatch',
            'created_at',
            'updated_at',
        ]

    def get_buyer_name(self, obj):
        return obj.buyer.full_name or obj.buyer.email

    def get_lead_technician_name(self, obj):
        if obj.lead_technician:
            return obj.lead_technician.full_name or obj.lead_technician.email
        return None

    def get_task_count(self, obj):
        return obj.tasks.count()


class WorkOrderSerializer(serializers.ModelSerializer):
    tasks = WorkOrderTaskSerializer(many=True, read_only=True)
    parts_used = WorkOrderPartUsageSerializer(many=True, read_only=True)
    workshop_name = serializers.CharField(source='workshop.display_name', read_only=True)
    workshop_city = serializers.CharField(source='workshop.city', read_only=True)
    booking_number = serializers.CharField(source='booking.booking_number', read_only=True)
    quotation_number = serializers.CharField(source='quotation.quotation_number', read_only=True)
    quotation_total = serializers.DecimalField(source='quotation.total_amount', max_digits=12, decimal_places=2, read_only=True)
    quotation_currency = serializers.CharField(source='quotation.currency', read_only=True)
    buyer_name = serializers.SerializerMethodField()
    buyer_email = serializers.CharField(source='buyer.email', read_only=True)
    buyer_phone = serializers.CharField(source='buyer.phone_number', read_only=True)
    customer_notes = serializers.CharField(source='booking.customer_notes', read_only=True, default='')
    reported_faults = serializers.CharField(source='booking.reported_faults', read_only=True, default='')
    lead_technician_name = serializers.SerializerMethodField()
    lead_technician_email = serializers.CharField(source='lead_technician.email', read_only=True)
    assigned_by_name = serializers.SerializerMethodField()
    quality_inspected_by_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    total_parts_cost = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total_actual_labour_minutes = serializers.IntegerField(read_only=True)
    total_estimated_labour_minutes = serializers.IntegerField(read_only=True)
    planned_parts = serializers.SerializerMethodField()
    change_orders = serializers.SerializerMethodField()
    authorized_total_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    approved_change_orders_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    has_pending_change_orders = serializers.BooleanField(read_only=True)
    vehicle_odometer_unit = serializers.SerializerMethodField()
    odometer_unit_mismatch = serializers.SerializerMethodField()

    def get_vehicle_odometer_unit(self, obj):
        if obj.vehicle and getattr(obj.vehicle, 'odometer_unit', None):
            return obj.vehicle.odometer_unit
        return None

    def get_odometer_unit_mismatch(self, obj):
        if obj.vehicle and getattr(obj.vehicle, 'odometer_unit', None) and obj.odometer_unit:
            return obj.vehicle.odometer_unit.strip().lower() != obj.odometer_unit.strip().lower()
        return False

    class Meta:
        model = WorkOrder
        fields = [
            'id',
            'work_order_number',
            'booking',
            'booking_number',
            'quotation',
            'quotation_number',
            'quotation_total',
            'quotation_currency',
            'authorized_total_amount',
            'approved_change_orders_amount',
            'has_pending_change_orders',
            'workshop',
            'workshop_name',
            'workshop_city',
            'buyer',
            'buyer_name',
            'buyer_email',
            'buyer_phone',
            'customer_notes',
            'reported_faults',
            'vehicle',
            'vehicle_make',
            'vehicle_model',
            'vehicle_year',
            'vehicle_registration_plate',
            'vehicle_vin',
            'current_odometer',
            'odometer_unit',
            'vehicle_odometer_unit',
            'odometer_unit_mismatch',
            'lead_technician',
            'lead_technician_name',
            'lead_technician_email',
            'assigned_by',
            'assigned_by_name',
            'assigned_at',
            'status',
            'status_display',
            'started_at',
            'completed_at',
            'quality_inspected_at',
            'quality_inspected_by',
            'quality_inspected_by_name',
            'internal_notes',
            'quality_notes',
            'cancellation_reason',
            'total_parts_cost',
            'total_actual_labour_minutes',
            'total_estimated_labour_minutes',
            'tasks',
            'parts_used',
            'planned_parts',
            'change_orders',
            'created_at',
            'updated_at',
        ]

    def get_change_orders(self, obj):
        return ChangeOrderSerializer(obj.change_orders.all(), many=True).data
        read_only_fields = [
            'id',
            'work_order_number',
            'booking',
            'quotation',
            'workshop',
            'buyer',
            'vehicle',
            'created_at',
            'updated_at',
        ]

    def get_buyer_name(self, obj):
        return obj.buyer.full_name or obj.buyer.email

    def get_lead_technician_name(self, obj):
        if obj.lead_technician:
            return obj.lead_technician.full_name or obj.lead_technician.email
        return None

    def get_assigned_by_name(self, obj):
        if obj.assigned_by:
            return obj.assigned_by.full_name or obj.assigned_by.email
        return None

    def get_quality_inspected_by_name(self, obj):
        if obj.quality_inspected_by:
            return obj.quality_inspected_by.full_name or obj.quality_inspected_by.email
        return None

    def get_planned_parts(self, obj):
        parts = obj.quotation.line_items.filter(item_type=LineItemTypeChoices.PART)
        return QuotationLineItemSerializer(parts, many=True).data


class WorkOrderAssignTechnicianSerializer(serializers.Serializer):
    technician_id = serializers.UUIDField(required=True)


class WorkOrderStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=WorkOrderStatusChoices.choices, required=True)
    internal_notes = serializers.CharField(required=False, allow_blank=True, default='')
    quality_notes = serializers.CharField(required=False, allow_blank=True, default='')
    cancellation_reason = serializers.CharField(required=False, allow_blank=True, default='')


class WorkOrderTaskCreateUpdateSerializer(serializers.Serializer):
    description = serializers.CharField(required=True, max_length=255)
    assigned_technician_id = serializers.UUIDField(required=False, allow_null=True)
    estimated_labour_minutes = serializers.IntegerField(required=False, default=60, min_value=1)
    actual_labour_minutes = serializers.IntegerField(required=False, default=0, min_value=0)
    status = serializers.ChoiceField(choices=WorkOrderTaskStatusChoices.choices, required=False, default=WorkOrderTaskStatusChoices.PENDING)
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class WorkOrderPartUsageCreateSerializer(serializers.Serializer):
    part_name = serializers.CharField(required=True, max_length=255)
    part_number = serializers.CharField(required=False, allow_blank=True, default='', max_length=100)
    description = serializers.CharField(required=False, allow_blank=True, default='')
    catalogue_part_id = serializers.UUIDField(required=False, allow_null=True)
    inventory_item_id = serializers.UUIDField(required=False, allow_null=True)
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1.00'), min_value=Decimal('0.01'))
    unit_cost = serializers.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), min_value=Decimal('0.00'))


class WorkshopTechnicianMemberSerializer(serializers.Serializer):
    id = serializers.UUIDField(source='user.id')
    email = serializers.EmailField(source='user.email')
    full_name = serializers.SerializerMethodField()
    role = serializers.CharField()
    joined_at = serializers.DateTimeField()

    def get_full_name(self, obj):
        return obj.user.full_name or obj.user.email

# ==========================================
# Buyer-Facing Sanitized Work Order Serializers
# Protects internal workshop operational notes, technician emails, and internal wholesale costs
# ==========================================

class BuyerWorkOrderTaskSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = WorkOrderTask
        fields = [
            'id',
            'description',
            'status',
            'status_display',
            'order_index',
        ]
        read_only_fields = fields


class BuyerWorkOrderPartUsageSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkOrderPartUsage
        fields = [
            'id',
            'part_name',
            'part_number',
            'quantity',
            'usage_date',
        ]
        read_only_fields = fields


class BuyerWorkOrderSerializer(serializers.ModelSerializer):
    tasks = BuyerWorkOrderTaskSerializer(many=True, read_only=True)
    parts_used = BuyerWorkOrderPartUsageSerializer(many=True, read_only=True)
    change_orders = serializers.SerializerMethodField()
    workshop_name = serializers.CharField(source='workshop.display_name', read_only=True)
    workshop_city = serializers.CharField(source='workshop.city', read_only=True)
    booking_number = serializers.CharField(source='booking.booking_number', read_only=True)
    quotation_number = serializers.CharField(source='quotation.quotation_number', read_only=True)
    quotation_total = serializers.DecimalField(source='quotation.total_amount', max_digits=12, decimal_places=2, read_only=True)
    quotation_currency = serializers.CharField(source='quotation.currency', read_only=True)
    authorized_total_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    approved_change_orders_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    has_pending_change_orders = serializers.BooleanField(read_only=True)
    vehicle_odometer_unit = serializers.SerializerMethodField()
    odometer_unit_mismatch = serializers.SerializerMethodField()

    def get_vehicle_odometer_unit(self, obj):
        if obj.vehicle and getattr(obj.vehicle, 'odometer_unit', None):
            return obj.vehicle.odometer_unit
        return None

    def get_odometer_unit_mismatch(self, obj):
        if obj.vehicle and getattr(obj.vehicle, 'odometer_unit', None) and obj.odometer_unit:
            return obj.vehicle.odometer_unit.strip().lower() != obj.odometer_unit.strip().lower()
        return False
    lead_technician_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = WorkOrder
        fields = [
            'id',
            'work_order_number',
            'booking_number',
            'quotation_number',
            'quotation_total',
            'quotation_currency',
            'authorized_total_amount',
            'approved_change_orders_amount',
            'has_pending_change_orders',
            'workshop_name',
            'workshop_city',
            'vehicle_make',
            'vehicle_model',
            'vehicle_year',
            'vehicle_registration_plate',
            'vehicle_odometer_unit',
            'odometer_unit_mismatch',
            'lead_technician_name',
            'status',
            'status_display',
            'started_at',
            'completed_at',
            'cancellation_reason',
            'tasks',
            'parts_used',
            'change_orders',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_change_orders(self, obj):
        return BuyerChangeOrderSerializer(obj.change_orders.all(), many=True).data

    def get_lead_technician_name(self, obj):
        if obj.lead_technician:
            return obj.lead_technician.full_name or obj.lead_technician.first_name or "Workshop Technician"
        return None

# ==========================================
# Change Order Domain Serializers
# ==========================================

class ChangeOrderLineItemSerializer(serializers.ModelSerializer):
    item_type_display = serializers.CharField(source='get_item_type_display', read_only=True)

    class Meta:
        model = ChangeOrderLineItem
        fields = [
            'id',
            'change_order',
            'item_type',
            'item_type_display',
            'description',
            'part_number',
            'catalogue_part',
            'quantity',
            'unit_price',
            'line_total',
            'estimated_labour_minutes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'line_total', 'created_at', 'updated_at']


class ChangeOrderLineItemCreateSerializer(serializers.Serializer):
    item_type = serializers.ChoiceField(choices=LineItemTypeChoices.choices, default=LineItemTypeChoices.LABOUR)
    description = serializers.CharField(max_length=255, required=True)
    part_number = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    catalogue_part_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1.00'), min_value=Decimal('0.01'))
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), min_value=Decimal('0.00'))
    estimated_labour_minutes = serializers.IntegerField(required=False, allow_null=True, min_value=1)


class ChangeOrderSerializer(serializers.ModelSerializer):
    line_items = ChangeOrderLineItemSerializer(many=True, read_only=True)
    work_order_number = serializers.CharField(source='work_order.work_order_number', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    created_by_name = serializers.SerializerMethodField()
    reviewed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ChangeOrder
        fields = [
            'id',
            'change_order_number',
            'work_order',
            'work_order_number',
            'version',
            'status',
            'status_display',
            'reason',
            'subtotal_labour',
            'subtotal_parts',
            'subtotal_other',
            'discount_amount',
            'tax_rate_percent',
            'tax_amount',
            'tax_breakdown',
            'additional_amount',
            'revised_authorized_total',
            'currency',
            'created_by',
            'created_by_name',
            'submitted_at',
            'reviewed_by',
            'reviewed_by_name',
            'reviewed_at',
            'buyer_notes',
            'workshop_notes',
            'line_items',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id', 'change_order_number', 'work_order', 'version', 'status',
            'subtotal_labour', 'subtotal_parts', 'subtotal_other', 'tax_amount', 'tax_breakdown',
            'additional_amount', 'revised_authorized_total', 'currency',
            'created_by', 'submitted_at', 'reviewed_by', 'reviewed_at',
            'created_at', 'updated_at',
        ]

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.full_name or obj.created_by.email
        return None

    def get_reviewed_by_name(self, obj):
        if obj.reviewed_by:
            return obj.reviewed_by.full_name or obj.reviewed_by.email
        return None


class BuyerChangeOrderSerializer(serializers.ModelSerializer):
    """
    Sanitized change order serializer for customer review and authorization.
    Protects workshop internal operational notes.
    """
    line_items = ChangeOrderLineItemSerializer(many=True, read_only=True)
    work_order_number = serializers.CharField(source='work_order.work_order_number', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = ChangeOrder
        fields = [
            'id',
            'change_order_number',
            'work_order_number',
            'version',
            'status',
            'status_display',
            'reason',
            'subtotal_labour',
            'subtotal_parts',
            'subtotal_other',
            'discount_amount',
            'tax_rate_percent',
            'tax_amount',
            'tax_breakdown',
            'additional_amount',
            'revised_authorized_total',
            'currency',
            'submitted_at',
            'reviewed_at',
            'buyer_notes',
            'line_items',
            'created_at',
        ]
        read_only_fields = fields


class ChangeOrderCreateSerializer(serializers.Serializer):
    currency = serializers.CharField(max_length=3, required=False, allow_blank=True)
    reason = serializers.CharField(required=True, min_length=5, max_length=2000)
    discount_amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=Decimal('0.00'), min_value=Decimal('0.00'))
    tax_rate_percent = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)
    workshop_notes = serializers.CharField(required=False, allow_blank=True, default='')
    submit_for_approval = serializers.BooleanField(required=False, default=False)
    line_items = ChangeOrderLineItemCreateSerializer(many=True, required=True)

    def validate_currency(self, value):
        if value:
            clean = value.strip().upper()
            work_order = self.context.get('work_order')
            expected = (work_order.quotation.currency if work_order and work_order.quotation else (work_order.workshop.currency if work_order else None))
            if expected and clean != expected.upper():
                raise serializers.ValidationError(
                    f"Conflicting change order currency '{clean}' rejected. Must match work order currency '{expected}'."
                )
            return clean
        return value

    def validate_line_items(self, value):
        if not value or len(value) == 0:
            raise serializers.ValidationError("At least one line item is required.")
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        tax_rate = attrs.get('tax_rate_percent')
        work_order = self.context.get('work_order')
        if work_order and work_order.workshop and tax_rate is not None and tax_rate > Decimal('0.00'):
            if not getattr(work_order.workshop, 'can_collect_tax', False):
                raise serializers.ValidationError({
                    'tax_rate_percent': f"Workshop '{work_order.workshop.display_name}' is not authorized to collect tax. Change order tax rate must be 0.00%."
                })
        return attrs


class AdminWorkshopTaxAuthorizationSerializer(serializers.Serializer):
    can_collect_tax = serializers.BooleanField(required=True)
    reason = serializers.CharField(required=False, allow_blank=True, default='')


class ChangeOrderDecisionSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True, default='')
    reason = serializers.CharField(required=False, allow_blank=True, default='')


class WorkshopReviewSerializer(serializers.ModelSerializer):
    workshop_id = serializers.UUIDField(source='workshop.id', read_only=True)
    workshop_name = serializers.CharField(source='workshop.business_name', read_only=True)
    booking_id = serializers.UUIDField(source='booking.id', read_only=True)
    booking_number = serializers.CharField(source='booking.booking_number', read_only=True)
    work_order_id = serializers.UUIDField(source='work_order.id', read_only=True, allow_null=True)
    work_order_number = serializers.CharField(source='work_order.work_order_number', read_only=True, allow_null=True)
    buyer_id = serializers.UUIDField(source='buyer.id', read_only=True)
    buyer_name = serializers.SerializerMethodField()
    workshop_replied_by_name = serializers.SerializerMethodField()
    vehicle_display = serializers.SerializerMethodField()

    class Meta:
        model = WorkshopReview
        fields = [
            'id',
            'workshop_id',
            'workshop_name',
            'booking_id',
            'booking_number',
            'work_order_id',
            'work_order_number',
            'buyer_id',
            'buyer_name',
            'rating',
            'communication_rating',
            'workmanship_rating',
            'pricing_transparency_rating',
            'title',
            'comment',
            'status',
            'is_verified_service',
            'workshop_reply',
            'workshop_reply_at',
            'workshop_replied_by_name',
            'helpful_votes',
            'vehicle_display',
            'created_at',
            'updated_at',
        ]

    def get_buyer_name(self, obj) -> str:
        if obj.buyer:
            full = getattr(obj.buyer, 'full_name', '')
            if full:
                parts = full.split()
                if len(parts) > 1:
                    return f"{parts[0]} {parts[-1][0]}."
                return full
            return obj.buyer.email.split('@')[0]
        return "Customer"

    def get_workshop_replied_by_name(self, obj) -> str | None:
        if obj.workshop_replied_by:
            return getattr(obj.workshop_replied_by, 'full_name', None) or obj.workshop_replied_by.email.split('@')[0]
        return None

    def get_vehicle_display(self, obj) -> str | None:
        if obj.booking:
            make = obj.booking.vehicle_make or ""
            model = obj.booking.vehicle_model or ""
            year = obj.booking.vehicle_year or ""
            return f"{year} {make} {model}".strip() or None
        return None


class WorkshopReviewCreateSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5, required=True)
    communication_rating = serializers.IntegerField(min_value=1, max_value=5, required=False, allow_null=True)
    workmanship_rating = serializers.IntegerField(min_value=1, max_value=5, required=False, allow_null=True)
    pricing_transparency_rating = serializers.IntegerField(min_value=1, max_value=5, required=False, allow_null=True)
    title = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    comment = serializers.CharField(min_length=5, required=True)


class WorkshopReviewReplySerializer(serializers.Serializer):
    reply = serializers.CharField(min_length=2, required=True)


class WorkshopReviewModerationSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=ReviewStatusChoices.choices, required=True)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True, default='')


class WorkshopMessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.SerializerMethodField()

    class Meta:
        model = WorkshopMessage
        fields = [
            'id',
            'conversation_id',
            'sender_id',
            'sender_name',
            'sender_type',
            'content',
            'attachment_url',
            'is_read',
            'read_at',
            'created_at',
        ]
        read_only_fields = fields

    def get_sender_name(self, obj) -> str:
        if not obj.sender:
            return "System"
        name = getattr(obj.sender, 'full_name', '')
        return name if name else obj.sender.email.split('@')[0]


class WorkshopConversationSerializer(serializers.ModelSerializer):
    booking_number = serializers.CharField(source='booking.booking_number', read_only=True)
    workshop_name = serializers.CharField(source='workshop.business_name', read_only=True)
    buyer_name = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = WorkshopConversation
        fields = [
            'id',
            'booking_id',
            'booking_number',
            'workshop_id',
            'workshop_name',
            'buyer_id',
            'buyer_name',
            'last_message',
            'unread_count',
            'last_message_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_buyer_name(self, obj) -> str:
        if not obj.buyer:
            return "Customer"
        name = getattr(obj.buyer, 'full_name', '')
        return name if name else obj.buyer.email.split('@')[0]

    def get_last_message(self, obj) -> dict | None:
        last = obj.messages.order_by('-created_at').first()
        if not last:
            return None
        return {
            'id': str(last.id),
            'content': last.content,
            'sender_type': last.sender_type,
            'is_read': last.is_read,
            'created_at': last.created_at.isoformat(),
        }

    def get_unread_count(self, obj) -> int:
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            return 0
        return obj.messages.filter(is_read=False).exclude(sender=request.user).count()


class CreateWorkshopMessageSerializer(serializers.Serializer):
    content = serializers.CharField(required=False, allow_blank=True, default='')
    attachment_url = serializers.CharField(max_length=500, required=False, allow_blank=True, default='')

    def validate(self, attrs):
        content = attrs.get('content', '').strip()
        attachment_url = attrs.get('attachment_url', '').strip()
        if not content and not attachment_url:
            raise serializers.ValidationError("Either message content or attachment URL is required.")
        attrs['content'] = content
        attrs['attachment_url'] = attachment_url
        return attrs


