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


class RecordSourceChoices(models.TextChoices):
    PLATFORM_VERIFIED = 'PLATFORM_VERIFIED', 'Platform Verified'
    BUYER_ENTERED = 'BUYER_ENTERED', 'Buyer Entered'


class VehicleServiceRecord(BaseUUIDModel):
    """
    Vehicle service and maintenance record forming the vehicle's permanent passport history.
    Generated automatically upon WorkOrder completion (PLATFORM_VERIFIED) or manually
    registered by the vehicle owner for external maintenance (BUYER_ENTERED).
    """
    vehicle = models.ForeignKey(
        GarageVehicle,
        on_delete=models.CASCADE,
        related_name='service_records',
        db_index=True,
    )
    work_order = models.OneToOneField(
        'workshops.WorkOrder',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='service_history_record',
    )
    workshop = models.ForeignKey(
        'workshops.WorkshopProfile',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='service_history_records',
    )
    service_centre_name = models.CharField(max_length=200, blank=True)

    # Core service information
    service_title = models.CharField(max_length=200)
    service_type = models.CharField(max_length=50, blank=True, default='SERVICE')
    description = models.TextField(blank=True)
    service_date = models.DateField(db_index=True)

    # Telemetry and financials
    odometer_reading = models.PositiveIntegerField(null=True, blank=True)
    odometer_unit = models.CharField(max_length=10, default='mi')
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default='GBP')

    # Provenance and verification
    record_source = models.CharField(
        max_length=30,
        choices=RecordSourceChoices.choices,
        default=RecordSourceChoices.BUYER_ENTERED,
        db_index=True,
    )
    is_verified = models.BooleanField(default=False, db_index=True)

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_service_records',
    )
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Vehicle Service Record'
        verbose_name_plural = 'Vehicle Service Records'
        ordering = ['-service_date', '-created_at']
        indexes = [
            models.Index(fields=['vehicle', '-service_date']),
            models.Index(fields=['vehicle', 'record_source']),
            models.Index(fields=['vehicle', 'is_verified']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(record_source='PLATFORM_VERIFIED', is_verified=True, work_order__isnull=False) |
                    models.Q(record_source='BUYER_ENTERED', is_verified=False, work_order__isnull=True)
                ),
                name='valid_record_source_verification_work_order',
            ),
        ]

    def __str__(self):
        source = 'Verified' if self.is_verified else 'Buyer-Entered'
        return f'{self.vehicle} - {self.service_title} ({self.service_date}) [{source}]'

    def clean(self):
        from django.core.exceptions import ValidationError as DjangoValidationError
        super().clean()
        if self.service_date and self.service_date > timezone.now().date():
            raise DjangoValidationError({'service_date': 'Service date cannot be in the future.'})

        if self.currency:
            self.currency = self.currency.upper()

        if self.record_source == RecordSourceChoices.PLATFORM_VERIFIED:
            if not self.is_verified:
                raise DjangoValidationError({'is_verified': 'Platform verified records must have is_verified=True.'})
            if not self.work_order_id:
                raise DjangoValidationError({'work_order': 'Platform verified records must have an originating Work Order.'})

            # Currency validation for platform-verified records linked to a workshop
            if self.workshop_id:
                workshop = self.workshop
                if workshop and workshop.currency:
                    if not self.currency:
                        self.currency = workshop.currency
                    elif self.currency != workshop.currency:
                        raise DjangoValidationError({
                            'currency': f"Currency '{self.currency}' does not match owning workshop currency '{workshop.currency}'."
                        })

            # Validate against associated quotation / work order currency where applicable
            if self.work_order_id:
                work_order = self.work_order
                if work_order:
                    wo_currency = None
                    if hasattr(work_order, 'quotation') and work_order.quotation and work_order.quotation.currency:
                        wo_currency = work_order.quotation.currency
                    elif hasattr(work_order, 'currency') and work_order.currency:
                        wo_currency = work_order.currency

                    if wo_currency:
                        if not self.currency:
                            self.currency = wo_currency
                        elif self.currency != wo_currency:
                            raise DjangoValidationError({
                                'currency': f"Currency '{self.currency}' does not match associated work order currency '{wo_currency}'."
                            })
        elif self.record_source == RecordSourceChoices.BUYER_ENTERED:
            if self.is_verified:
                raise DjangoValidationError({'is_verified': 'Buyer entered records cannot have is_verified=True.'})
            if self.work_order_id:
                raise DjangoValidationError({'work_order': 'Buyer entered records cannot be linked to a Work Order.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
