from django.db import models
from django.utils.text import slugify
from common.models import BaseUUIDModel


class FuelTypeChoices(models.TextChoices):
    PETROL = 'PETROL', 'Petrol'
    DIESEL = 'DIESEL', 'Diesel'
    HYBRID = 'HYBRID', 'Hybrid (PHEV/MHEV)'
    EV = 'EV', 'Electric (BEV)'


class TransmissionChoices(models.TextChoices):
    AUTOMATIC = 'AUTOMATIC', 'Automatic'
    MANUAL = 'MANUAL', 'Manual'
    DUAL_CLUTCH = 'DUAL_CLUTCH', 'Dual Clutch (DCT/DSG)'


class FitmentTypeChoices(models.TextChoices):
    CONFIRMED_FIT = 'CONFIRMED_FIT', 'Confirmed Fit'
    CONDITIONAL_FIT = 'CONDITIONAL_FIT', 'Conditional Fit'
    DOES_NOT_FIT = 'DOES_NOT_FIT', 'Does Not Fit'
    UNKNOWN = 'UNKNOWN', 'Unknown / Unverified'


class VehicleMake(BaseUUIDModel):
    """Manufacturer / Brand of vehicles (e.g. BMW, Audi, Toyota)."""

    name = models.CharField(max_length=100, unique=True, db_index=True)
    country_of_origin = models.CharField(max_length=100, blank=True)
    logo_url = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Vehicle Make'
        verbose_name_plural = 'Vehicle Makes'
        ordering = ['name']

    def __str__(self):
        return self.name


class VehicleModel(BaseUUIDModel):
    """Specific model line produced by a make (e.g. 3 Series, A4, Golf)."""

    make = models.ForeignKey(
        VehicleMake,
        on_delete=models.CASCADE,
        related_name='models',
    )
    name = models.CharField(max_length=150)
    year_start = models.PositiveIntegerField()
    year_end = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Vehicle Model'
        verbose_name_plural = 'Vehicle Models'
        unique_together = ('make', 'name')
        ordering = ['make__name', 'name']

    def __str__(self):
        return f"{self.make.name} {self.name}"


class VehicleVariant(BaseUUIDModel):
    """Granular trim/engine variant of a vehicle model (e.g. 2021 BMW 330i M Sport Saloon)."""

    model = models.ForeignKey(
        VehicleModel,
        on_delete=models.CASCADE,
        related_name='variants',
    )
    name = models.CharField(max_length=200)  # e.g. "330i M Sport"
    year = models.PositiveIntegerField()
    engine_code = models.CharField(max_length=50, blank=True, default='')  # e.g. "B48B20"
    fuel_type = models.CharField(
        max_length=20,
        choices=FuelTypeChoices.choices,
        default=FuelTypeChoices.PETROL,
    )
    transmission = models.CharField(
        max_length=20,
        choices=TransmissionChoices.choices,
        default=TransmissionChoices.AUTOMATIC,
    )
    body_type = models.CharField(max_length=100, blank=True)  # Saloon, Estate, SUV, etc.
    power_bhp = models.PositiveIntegerField(null=True, blank=True)
    engine_capacity_cc = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Vehicle Variant'
        verbose_name_plural = 'Vehicle Variants'
        unique_together = ('model', 'name', 'year', 'engine_code')
        ordering = ['model__make__name', 'model__name', '-year', 'name']

    def __str__(self):
        return f"{self.year} {self.model.make.name} {self.model.name} {self.name}"

    @property
    def display_name(self) -> str:
        return f"{self.year} {self.model.make.name} {self.model.name} {self.name}"


class PartCategory(BaseUUIDModel):
    """Hierarchical category taxonomy for auto parts (e.g. Braking Systems -> Brake Rotors)."""

    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=150, unique=True, db_index=True)
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='subcategories',
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Part Category'
        verbose_name_plural = 'Part Categories'
        ordering = ['name']

    def __str__(self):
        if self.parent:
            return f"{self.parent.name} > {self.name}"
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Part(BaseUUIDModel):
    """Canonical catalog product / spare part (distinct from seller inventory offers)."""

    name = models.CharField(max_length=255)
    brand = models.CharField(max_length=100)
    mpn = models.CharField(max_length=100, db_index=True)  # Manufacturer Part Number
    category = models.ForeignKey(
        PartCategory,
        on_delete=models.CASCADE,
        related_name='parts',
    )
    description = models.TextField(blank=True)
    attributes = models.JSONField(default=dict, blank=True)  # Typed attributes e.g. diameter, thickness
    oem_numbers = models.JSONField(default=list, blank=True)  # OEM cross references
    image_url = models.URLField(blank=True)
    is_universal = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Part'
        verbose_name_plural = 'Parts'
        unique_together = ('brand', 'mpn')
        ordering = ['brand', 'mpn']
        indexes = [
            models.Index(fields=['brand', 'mpn']),
            models.Index(fields=['category', 'is_active']),
        ]

    def __str__(self):
        return f"{self.brand} {self.mpn} - {self.name}"


class PartCompatibility(BaseUUIDModel):
    """Verified compatibility mapping between a spare part and a specific vehicle variant."""

    part = models.ForeignKey(
        Part,
        on_delete=models.CASCADE,
        related_name='compatibilities',
    )
    vehicle_variant = models.ForeignKey(
        VehicleVariant,
        on_delete=models.CASCADE,
        related_name='part_compatibilities',
    )
    fitment_type = models.CharField(
        max_length=30,
        choices=FitmentTypeChoices.choices,
        default=FitmentTypeChoices.CONFIRMED_FIT,
    )
    qualifications = models.TextField(blank=True)  # e.g. "Only for models with M Sport Brakes"
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Part Compatibility'
        verbose_name_plural = 'Part Compatibilities'
        unique_together = ('part', 'vehicle_variant')
        indexes = [
            models.Index(fields=['part', 'vehicle_variant']),
            models.Index(fields=['fitment_type']),
        ]

    def __str__(self):
        return f"{self.part.mpn} -> {self.vehicle_variant} ({self.fitment_type})"
