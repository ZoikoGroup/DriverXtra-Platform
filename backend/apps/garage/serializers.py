from rest_framework import serializers
from apps.garage.models import GarageVehicle
from apps.catalogue.models import VehicleVariant


def mask_vin(vin_str: str) -> str:
    """Masks a vehicle VIN by default, returning only the last six characters.
    Example: 'WBA5R1C50M8219420' -> '***********219420'
    """
    if not vin_str:
        return ""
    clean = str(vin_str).strip()
    if len(clean) <= 6:
        return clean
    return f"{'*' * (len(clean) - 6)}{clean[-6:]}"


class GarageVehicleSerializer(serializers.ModelSerializer):
    """Serializer for managing user's personal vehicles in My Garage with data safety & privacy."""

    user_email = serializers.EmailField(source='user.email', read_only=True)
    variant_display = serializers.CharField(source='vehicle_variant.display_name', read_only=True, allow_null=True)

    make = serializers.CharField(max_length=80, required=False)
    model = serializers.CharField(max_length=80, required=False)
    year = serializers.IntegerField(required=False)
    trim = serializers.CharField(max_length=80, required=False, allow_blank=True)

    # Transparency: clearly indicate telemetry data is self-reported and not authoritative
    mot_data_source = serializers.CharField(default="Self-reported", read_only=True)
    recalls_data_source = serializers.CharField(default="Self-reported", read_only=True)

    class Meta:
        model = GarageVehicle
        fields = [
            'id',
            'user',
            'user_email',
            'vehicle_variant',
            'variant_display',
            'registration_plate',
            'vin',
            'nickname',
            'make',
            'model',
            'year',
            'trim',
            'engine_code',
            'fuel_type',
            'transmission',
            'power_bhp',
            'color',
            'current_odometer',
            'odometer_unit',
            'mot_status',
            'mot_expiry_date',
            'mot_data_source',
            'active_recalls_count',
            'recalls_data_source',
            'ownership_status',
            'primary_image_url',
            'is_primary',
            'is_archived',
            'archived_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'user',
            'user_email',
            'variant_display',
            'mot_data_source',
            'recalls_data_source',
            'is_archived',
            'archived_at',
            'created_at',
            'updated_at',
        ]

    def validate_vin(self, value):
        """Preserve original unmasked VIN if the client resubmitted a masked string."""
        if value and '*' in value:
            if self.instance and self.instance.vin:
                return self.instance.vin
        return value

    def to_representation(self, instance):
        """Return masked VIN exposing only the last 6 characters for user privacy."""
        data = super().to_representation(instance)
        if instance.vin:
            data['vin'] = mask_vin(instance.vin)
        return data

    def validate(self, attrs):
        instance = getattr(self, 'instance', None)
        variant = attrs.get('vehicle_variant') or (instance.vehicle_variant if instance else None)

        # If variant is provided, make/model/year/trim can be derived
        if variant:
            if not attrs.get('make') and not (instance and instance.make):
                attrs['make'] = variant.model.make.name
            if not attrs.get('model') and not (instance and instance.model):
                attrs['model'] = variant.model.name
            if not attrs.get('year') and not (instance and instance.year):
                attrs['year'] = variant.year
            if not attrs.get('trim') and not (instance and instance.trim):
                attrs['trim'] = variant.name
            if not attrs.get('engine_code') and variant.engine_code and not (instance and instance.engine_code):
                attrs['engine_code'] = variant.engine_code
            if not attrs.get('fuel_type') and variant.fuel_type and not (instance and instance.fuel_type):
                attrs['fuel_type'] = variant.fuel_type
            if not attrs.get('transmission') and variant.transmission and not (instance and instance.transmission):
                attrs['transmission'] = variant.transmission
            if not attrs.get('power_bhp') and variant.power_bhp and not (instance and instance.power_bhp):
                attrs['power_bhp'] = variant.power_bhp

        # If no variant and no instance, make, model, year must be provided
        make = attrs.get('make') or (instance.make if instance else None)
        model = attrs.get('model') or (instance.model if instance else None)
        year = attrs.get('year') or (instance.year if instance else None)

        if not make:
            raise serializers.ValidationError({'make': 'Vehicle make is required.'})
        if not model:
            raise serializers.ValidationError({'model': 'Vehicle model is required.'})
        if not year:
            raise serializers.ValidationError({'year': 'Vehicle model year is required.'})

        return attrs

    def create(self, validated_data):
        user = self.context['request'].user
        validated_data['user'] = user
        if not GarageVehicle.objects.filter(user=user, is_archived=False).exists():
            validated_data['is_primary'] = True
        return super().create(validated_data)

from decimal import Decimal
from apps.garage.models import VehicleServiceRecord, RecordSourceChoices


class VehicleServiceRecordSerializer(serializers.ModelSerializer):
    """
    Read serializer for vehicle service history records.
    Safely presents verified workshop repairs and unverified buyer records
    without exposing sensitive internal workshop annotations or wholesale costs.
    """
    vehicle_registration_plate = serializers.CharField(source='vehicle.registration_plate', read_only=True)
    workshop_name = serializers.SerializerMethodField()
    work_order_number = serializers.CharField(source='work_order.work_order_number', read_only=True, allow_null=True)
    work_order_tasks = serializers.SerializerMethodField()
    work_order_parts = serializers.SerializerMethodField()

    class Meta:
        model = VehicleServiceRecord
        fields = [
            'id',
            'vehicle',
            'vehicle_registration_plate',
            'work_order',
            'work_order_number',
            'workshop',
            'workshop_name',
            'service_centre_name',
            'service_title',
            'service_type',
            'description',
            'service_date',
            'odometer_reading',
            'odometer_unit',
            'total_cost',
            'currency',
            'record_source',
            'is_verified',
            'notes',
            'work_order_tasks',
            'work_order_parts',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_workshop_name(self, obj):
        if obj.workshop:
            return obj.workshop.display_name
        return obj.service_centre_name or ''

    def get_work_order_tasks(self, obj):
        if not obj.work_order_id or not obj.work_order:
            return []
        # Return sanitized task list (no technician IDs, no internal notes)
        return [
            {
                "id": str(task.id),
                "description": task.description,
                "status": task.status,
                "actual_labour_minutes": task.actual_labour_minutes,
            }
            for task in obj.work_order.tasks.order_by('order_index')
        ]

    def get_work_order_parts(self, obj):
        if not obj.work_order_id or not obj.work_order:
            return []
        # Return sanitized parts usage (no wholesale unit_cost or wholesale total_cost)
        return [
            {
                "id": str(p.id),
                "part_name": p.part_name,
                "part_number": p.part_number,
                "quantity": str(p.quantity),
            }
            for p in obj.work_order.parts_used.all()
        ]


class BuyerServiceRecordCreateSerializer(serializers.Serializer):
    """
    Payload validator for buyer-entered service records.
    Strictly forbids client injection of verification status or Work Order linking.
    """
    service_title = serializers.CharField(max_length=200, required=True)
    service_type = serializers.CharField(max_length=50, required=False, default='SERVICE')
    service_centre_name = serializers.CharField(max_length=200, required=False, allow_blank=True, default='')
    service_date = serializers.DateField(required=True)
    odometer_reading = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    odometer_unit = serializers.CharField(max_length=10, required=False, allow_blank=True, default=None)
    total_cost = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True, min_value=Decimal('0.00'))
    currency = serializers.CharField(max_length=3, required=False, allow_blank=True, default=None)
    description = serializers.CharField(required=False, allow_blank=True, default='')
    notes = serializers.CharField(required=False, allow_blank=True, default='')

    def validate_service_date(self, value):
        from django.utils import timezone
        if value > timezone.now().date():
            raise serializers.ValidationError("Service date cannot be in the future.")
        return value

    def validate(self, attrs):
        from platform_core.regional import derive_regional_context_for_vehicle_and_buyer

        vehicle = self.context.get('vehicle')
        user = (
            self.context.get('request').user
            if self.context.get('request') and hasattr(self.context.get('request'), 'user')
            else getattr(vehicle, 'user', None)
        )

        reg_ctx = derive_regional_context_for_vehicle_and_buyer(vehicle=vehicle, buyer=user)

        # 1. Odometer unit: preserve manually supplied unit, derive from vehicle stored unit, or regional default
        supplied_unit = attrs.get('odometer_unit')
        if supplied_unit and str(supplied_unit).strip():
            attrs['odometer_unit'] = str(supplied_unit).strip().lower()
        else:
            vehicle_unit = getattr(vehicle, 'odometer_unit', None)
            derived_unit = vehicle_unit or reg_ctx.get('odometer_unit')
            if not derived_unit:
                raise serializers.ValidationError({
                    'odometer_unit': "Odometer unit could not be reliably determined. Please specify 'km' or 'mi'."
                })
            attrs['odometer_unit'] = derived_unit

        # 2. Currency: preserve manually supplied currency, or derive from reliable regional source
        supplied_currency = attrs.get('currency')
        if supplied_currency and str(supplied_currency).strip():
            attrs['currency'] = str(supplied_currency).strip().upper()
        else:
            derived_curr = reg_ctx.get('currency')
            if derived_curr:
                attrs['currency'] = derived_curr
            else:
                raise serializers.ValidationError({
                    'currency': "Currency could not be reliably determined from your regional profile. Please provide an explicit currency code (e.g. INR, GBP)."
                })

        return attrs


class BuyerServiceRecordUpdateSerializer(serializers.Serializer):
    """
    Payload validator for updating buyer-entered service records.
    All fields are optional. Verification status and work order cannot be changed.
    """
    service_title = serializers.CharField(max_length=200, required=False)
    service_type = serializers.CharField(max_length=50, required=False)
    service_centre_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    service_date = serializers.DateField(required=False)
    odometer_reading = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    odometer_unit = serializers.CharField(max_length=10, required=False)
    total_cost = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True, min_value=Decimal('0.00'))
    currency = serializers.CharField(max_length=3, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate_service_date(self, value):
        from django.utils import timezone
        if value > timezone.now().date():
            raise serializers.ValidationError("Service date cannot be in the future.")
        return value
