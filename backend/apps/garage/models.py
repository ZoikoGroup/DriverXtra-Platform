from django.db import models
from django.utils import timezone
from common.models import BaseUUIDModel
from apps.identity.models import User
from apps.catalogue.models import VehicleVariant


class GarageVehicle(BaseUUIDModel):
    """Authenticated user's personal vehicle passport registered in My Garage."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='garage_vehicles',
    )
    vehicle_variant = models.ForeignKey(
        VehicleVariant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='garage_vehicles',
    )

    # Identifiers
    registration_plate = models.CharField(max_length=30, blank=True, db_index=True)
    vin = models.CharField(max_length=50, blank=True, db_index=True)
    nickname = models.CharField(max_length=100, blank=True)

    # Vehicle Specifications (populated automatically from variant or entered manually)
    make = models.CharField(max_length=100)
    model = models.CharField(max_length=150)
    year = models.PositiveIntegerField()
    trim = models.CharField(max_length=200, blank=True)
    engine_code = models.CharField(max_length=50, blank=True)
    fuel_type = models.CharField(max_length=30, blank=True)
    transmission = models.CharField(max_length=30, blank=True)
    power_bhp = models.PositiveIntegerField(null=True, blank=True)
    color = models.CharField(max_length=50, blank=True)

    # Telemetry, Status & MOT
    current_odometer = models.PositiveIntegerField(default=0)
    odometer_unit = models.CharField(max_length=10, default='mi')
    mot_status = models.CharField(max_length=30, default='VALID')
    mot_expiry_date = models.DateField(null=True, blank=True)
    active_recalls_count = models.PositiveIntegerField(default=0)
    ownership_status = models.CharField(max_length=50, default='VERIFIED_OWNER')
    primary_image_url = models.URLField(blank=True)

    # Primary Garage Vehicle Toggle
    is_primary = models.BooleanField(default=False)

    # Archival / Soft-Delete
    is_archived = models.BooleanField(default=False, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Garage Vehicle'
        verbose_name_plural = 'Garage Vehicles'
        ordering = ['-is_primary', '-created_at']
        indexes = [
            models.Index(fields=['user', 'is_primary']),
            models.Index(fields=['user', 'registration_plate']),
            models.Index(fields=['user', 'is_archived']),
        ]

    def __str__(self):
        plate = f" [{self.registration_plate}]" if self.registration_plate else ""
        return f"{self.user.email} - {self.year} {self.make} {self.model}{plate}"

    def save(self, *args, **kwargs):
        # Auto-populate make/model/year from vehicle_variant if attached and not set
        if self.vehicle_variant:
            if not self.make:
                self.make = self.vehicle_variant.model.make.name
            if not self.model:
                self.model = self.vehicle_variant.model.name
            if not self.year:
                self.year = self.vehicle_variant.year
            if not self.trim and self.vehicle_variant.name:
                self.trim = self.vehicle_variant.name
            if not self.engine_code and self.vehicle_variant.engine_code:
                self.engine_code = self.vehicle_variant.engine_code
            if not self.fuel_type and self.vehicle_variant.fuel_type:
                self.fuel_type = self.vehicle_variant.fuel_type
            if not self.transmission and self.vehicle_variant.transmission:
                self.transmission = self.vehicle_variant.transmission
            if self.power_bhp is None and self.vehicle_variant.power_bhp:
                self.power_bhp = self.vehicle_variant.power_bhp

        # If this is the user's only non-archived vehicle, ensure it is marked primary
        if not self.is_archived and not GarageVehicle.objects.filter(user=self.user, is_archived=False).exclude(pk=self.pk).exists():
            self.is_primary = True

        # If set as primary, unmark any other primary vehicle for this user
        if self.is_primary:
            GarageVehicle.objects.filter(user=self.user, is_primary=True).exclude(pk=self.pk).update(is_primary=False)

        super().save(*args, **kwargs)

    def set_as_primary(self):
        if self.is_archived:
            raise ValueError('Archived vehicles cannot be designated as primary.')
        GarageVehicle.objects.filter(user=self.user, is_primary=True).exclude(pk=self.pk).update(is_primary=False)
        self.is_primary = True
        self.save(update_fields=['is_primary', 'updated_at'])

    def archive(self):
        """Soft-deletes the vehicle by setting is_archived=True and clearing primary status."""
        self.is_archived = True
        self.archived_at = timezone.now()
        was_primary = self.is_primary
        self.is_primary = False
        self.save(update_fields=['is_archived', 'archived_at', 'is_primary', 'updated_at'])

        if was_primary:
            next_vehicle = GarageVehicle.objects.filter(
                user=self.user,
                is_archived=False,
            ).exclude(pk=self.pk).order_by('-created_at').first()
            if next_vehicle:
                next_vehicle.set_as_primary()
