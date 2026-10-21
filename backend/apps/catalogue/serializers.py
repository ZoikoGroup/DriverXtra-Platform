from rest_framework import serializers
from apps.catalogue.models import (
    VehicleMake,
    VehicleModel,
    VehicleVariant,
    PartCategory,
    Part,
    PartCompatibility,
    FitmentTypeChoices,
)


class VehicleMakeSerializer(serializers.ModelSerializer):
    model_count = serializers.IntegerField(source='models.count', read_only=True)

    class Meta:
        model = VehicleMake
        fields = ['id', 'name', 'country_of_origin', 'logo_url', 'is_active', 'model_count']

    def validate_name(self, value):
        name = value.strip()
        qs = VehicleMake.objects.filter(name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(f"Vehicle make '{name}' already exists.")
        return name


class VehicleModelSerializer(serializers.ModelSerializer):
    make_name = serializers.CharField(source='make.name', read_only=True)
    variant_count = serializers.IntegerField(source='variants.count', read_only=True)

    class Meta:
        model = VehicleModel
        fields = ['id', 'make', 'make_name', 'name', 'year_start', 'year_end', 'is_active', 'variant_count']

    def validate(self, attrs):
        make = attrs.get('make', self.instance.make if self.instance else None)
        name = attrs.get('name', self.instance.name if self.instance else None)
        if make and name:
            name = name.strip()
            qs = VehicleModel.objects.filter(make=make, name__iexact=name)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({"name": f"Vehicle model '{name}' already exists for make '{make.name}'."})
        return attrs


class VehicleVariantSerializer(serializers.ModelSerializer):
    make_id = serializers.UUIDField(source='model.make.id', read_only=True)
    make_name = serializers.CharField(source='model.make.name', read_only=True)
    model_name = serializers.CharField(source='model.name', read_only=True)
    display_name = serializers.CharField(read_only=True)
    engine_code = serializers.CharField(max_length=50, required=False, default='', allow_blank=True)

    class Meta:
        model = VehicleVariant
        fields = [
            'id',
            'model',
            'make_id',
            'make_name',
            'model_name',
            'name',
            'display_name',
            'year',
            'engine_code',
            'fuel_type',
            'transmission',
            'body_type',
            'power_bhp',
            'engine_capacity_cc',
            'is_active',
        ]

    def validate(self, attrs):
        model = attrs.get('model', self.instance.model if self.instance else None)
        name = attrs.get('name', self.instance.name if self.instance else None)
        year = attrs.get('year', self.instance.year if self.instance else None)
        engine_code = attrs.get('engine_code', self.instance.engine_code if self.instance else '')
        if model and name and year is not None:
            qs = VehicleVariant.objects.filter(
                model=model,
                name__iexact=name.strip(),
                year=year,
                engine_code=engine_code.strip(),
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"non_field_errors": [f"Vehicle variant '{name}' ({year}, {engine_code}) already exists for this model."]}
                )
        return attrs


class PartCategorySerializer(serializers.ModelSerializer):
    subcategories = serializers.SerializerMethodField()
    parent_name = serializers.CharField(source='parent.name', read_only=True, allow_null=True)
    slug = serializers.SlugField(max_length=150, required=False, allow_blank=True)

    class Meta:
        model = PartCategory
        fields = ['id', 'name', 'slug', 'parent', 'parent_name', 'description', 'is_active', 'subcategories']

    def validate_slug(self, value):
        if value:
            value = value.strip()
            qs = PartCategory.objects.filter(slug=value)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(f"Category with slug '{value}' already exists.")
        return value

    def validate(self, attrs):
        name = attrs.get('name', self.instance.name if self.instance else None)
        slug = attrs.get('slug', self.instance.slug if self.instance else None)
        if name and not slug:
            from django.utils.text import slugify
            generated_slug = slugify(name)
            qs = PartCategory.objects.filter(slug=generated_slug)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({"slug": f"Category with slug '{generated_slug}' already exists."})
        return attrs

    def get_subcategories(self, obj):
        # Only nest 1 level of subcategories to prevent infinite recursion
        if not obj.parent:
            subs = obj.subcategories.filter(is_active=True)
            return [
                {
                    'id': s.id,
                    'name': s.name,
                    'slug': s.slug,
                    'parent': s.parent_id,
                    'description': s.description,
                }
                for s in subs
            ]
        return []


class PartSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    compatible_vehicles_count = serializers.IntegerField(source='compatibilities.count', read_only=True)
    mpn = serializers.CharField(max_length=100, required=False, default='', allow_blank=True)

    class Meta:
        model = Part
        fields = [
            'id',
            'name',
            'brand',
            'mpn',
            'category',
            'category_name',
            'description',
            'attributes',
            'oem_numbers',
            'image_url',
            'is_universal',
            'is_active',
            'compatible_vehicles_count',
            'created_at',
            'updated_at',
        ]

    def to_internal_value(self, data):
        ret = super().to_internal_value(data)
        if not ret.get('mpn') and 'part_number' in data:
            ret['mpn'] = data['part_number']
        return ret

    def validate(self, attrs):
        mpn = attrs.get('mpn', self.instance.mpn if self.instance else None)
        brand = attrs.get('brand', self.instance.brand if self.instance else None)
        if not mpn:
            raise serializers.ValidationError({"mpn": "Manufacturer Part Number (mpn) is required."})
        if brand and mpn:
            qs = Part.objects.filter(brand__iexact=brand.strip(), mpn__iexact=mpn.strip())
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({"mpn": f"Part with brand '{brand}' and MPN '{mpn}' already exists."})
        return attrs


class PartCompatibilitySerializer(serializers.ModelSerializer):
    part_name = serializers.CharField(source='part.name', read_only=True)
    part_mpn = serializers.CharField(source='part.mpn', read_only=True)
    part_brand = serializers.CharField(source='part.brand', read_only=True)
    vehicle_display = serializers.CharField(source='vehicle_variant.display_name', read_only=True)
    fitment_type = serializers.CharField(max_length=30, required=False, default=FitmentTypeChoices.CONFIRMED_FIT)

    class Meta:
        model = PartCompatibility
        fields = [
            'id',
            'part',
            'part_name',
            'part_brand',
            'part_mpn',
            'vehicle_variant',
            'vehicle_display',
            'fitment_type',
            'qualifications',
            'notes',
            'created_at',
        ]

    def validate(self, attrs):
        if self.instance:
            if 'part' in attrs and attrs['part'] != self.instance.part:
                raise serializers.ValidationError({"part": "Changing the associated part of an existing compatibility record is not permitted."})
            if 'vehicle_variant' in attrs and attrs['vehicle_variant'] != self.instance.vehicle_variant:
                raise serializers.ValidationError({"vehicle_variant": "Changing the associated vehicle variant of an existing compatibility record is not permitted."})

        if 'is_direct_fit' in self.initial_data and 'fitment_type' not in attrs:
            attrs['fitment_type'] = FitmentTypeChoices.CONFIRMED_FIT if self.initial_data['is_direct_fit'] else FitmentTypeChoices.UNKNOWN

        fitment_type = attrs.get('fitment_type')
        if fitment_type and fitment_type not in FitmentTypeChoices.values:
            raise serializers.ValidationError({"fitment_type": f"Invalid fitment_type '{fitment_type}'."})

        part = attrs.get('part', self.instance.part if self.instance else None)
        variant = attrs.get('vehicle_variant', self.instance.vehicle_variant if self.instance else None)
        if part and variant:
            qs = PartCompatibility.objects.filter(part=part, vehicle_variant=variant)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({"non_field_errors": ["A compatibility record already exists for this part and vehicle variant."]})

        return attrs


class FitmentCheckSerializer(serializers.Serializer):
    part_id = serializers.UUIDField(required=True)
    vehicle_variant_id = serializers.UUIDField(required=False)
    variant_id = serializers.UUIDField(required=False)

    def validate(self, attrs):
        variant_id = attrs.get('vehicle_variant_id') or attrs.get('variant_id')
        if not variant_id:
            raise serializers.ValidationError({"vehicle_variant_id": "Either vehicle_variant_id or variant_id is required."})
        attrs['vehicle_variant_id'] = variant_id
        return attrs
