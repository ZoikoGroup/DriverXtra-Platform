from rest_framework import serializers
from apps.garage.models import GarageVehicle
from apps.catalogue.models import VehicleVariant


class GarageVehicleSerializer(serializers.ModelSerializer):
    """Serializer for managing user's personal vehicles in My Garage."""

    user_email = serializers.EmailField(source='user.email', read_only=True)
    variant_display = serializers.CharField(source='vehicle_variant.display_name', read_only=True, allow_null=True)

    make = serializers.CharField(max_length=80, required=False)
    model = serializers.CharField(max_length=80, required=False)
    year = serializers.IntegerField(required=False)
    trim = serializers.CharField(max_length=80, required=False, allow_blank=True)

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
            'active_recalls_count',
            'ownership_status',
            'primary_image_url',
            'is_primary',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'user', 'user_email', 'variant_display', 'created_at', 'updated_at']

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
        if not GarageVehicle.objects.filter(user=user).exists():
            validated_data['is_primary'] = True
        return super().create(validated_data)
