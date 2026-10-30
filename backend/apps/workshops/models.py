import uuid
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from common.models import BaseUUIDModel
from apps.organisations.models import Organisation, OrganisationTypeChoices


class DayOfWeekChoices(models.IntegerChoices):
    MONDAY = 0, 'Monday'
    TUESDAY = 1, 'Tuesday'
    WEDNESDAY = 2, 'Wednesday'
    THURSDAY = 3, 'Thursday'
    FRIDAY = 4, 'Friday'
    SATURDAY = 5, 'Saturday'
    SUNDAY = 6, 'Sunday'


class BookingStatusChoices(models.TextChoices):
    REQUESTED = 'REQUESTED', 'Requested'
    UNDER_REVIEW = 'UNDER_REVIEW', 'Under Review'
    ACCEPTED = 'ACCEPTED', 'Accepted'
    REJECTED = 'REJECTED', 'Rejected'
    QUOTED = 'QUOTED', 'Quoted'
    CONFIRMED = 'CONFIRMED', 'Confirmed'
    CANCELLED = 'CANCELLED', 'Cancelled'


class QuotationStatusChoices(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    ISSUED = 'ISSUED', 'Issued'
    ACCEPTED = 'ACCEPTED', 'Accepted'
    REJECTED = 'REJECTED', 'Rejected'
    SUPERSEDED = 'SUPERSEDED', 'Superseded'
    EXPIRED = 'EXPIRED', 'Expired'


class LineItemTypeChoices(models.TextChoices):
    LABOUR = 'LABOUR', 'Labour'
    PART = 'PART', 'Spare Part'
    DIAGNOSTIC = 'DIAGNOSTIC', 'Diagnostics'
    DISPOSAL = 'DISPOSAL', 'Disposal & Environmental Fee'
    OTHER = 'OTHER', 'Other Charge'


def generate_booking_number() -> str:
    """Generates unique booking number formatted as BK-YYYYMMDD-XXXXXX."""
    date_str = timezone.now().strftime('%Y%m%d')
    suffix = uuid.uuid4().hex[:6].upper()
    return f"BK-{date_str}-{suffix}"


def generate_quotation_number() -> str:
    """Generates unique quotation reference formatted as QT-YYYYMMDD-XXXXXX."""
    date_str = timezone.now().strftime('%Y%m%d')
    suffix = uuid.uuid4().hex[:6].upper()
    return f"QT-{date_str}-{suffix}"


class WorkshopProfile(BaseUUIDModel):
    """
    Profile and operational settings for a registered Workshop organisation.
    Linked One-to-One with Organisation (where type='WORKSHOP').
    """
    organisation = models.OneToOneField(
        Organisation,
        on_delete=models.CASCADE,
        related_name='workshop_profile',
    )
    business_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Trading name. Defaults to organisation name if left blank.",
    )
    slug = models.SlugField(
        max_length=255,
        unique=True,
        db_index=True,
        blank=True,
        help_text="URL slug. Defaults to organisation slug if left blank.",
    )
    description = models.TextField(blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    address_line1 = models.CharField(max_length=255, blank=True)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state_province = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=50, default='GB')
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    currency = models.CharField(max_length=3, default='GBP')
    bay_capacity = models.PositiveIntegerField(
        default=2,
        validators=[MinValueValidator(1)],
        help_text="Number of service bays available for simultaneous appointments.",
    )
    is_accepting_bookings = models.BooleanField(default=True, db_index=True)
    is_verified = models.BooleanField(default=True, db_index=True)

    # Tax configuration per workshop (not hardcoding UK 20% VAT platform-wide)
    is_tax_registered = models.BooleanField(
        default=True,
        help_text="Whether this workshop is registered for indirect taxes (e.g. VAT/GST).",
    )
    default_tax_rate_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        help_text="Default tax percentage rate for this workshop (e.g. 20.00 for 20% VAT, or 0.00 if exempt/unregistered).",
    )

    class Meta:
        verbose_name = 'Workshop Profile'
        verbose_name_plural = 'Workshop Profiles'
        ordering = ['business_name']
        indexes = [
            models.Index(fields=['is_accepting_bookings', 'is_verified']),
            models.Index(fields=['city']),
        ]

    def __str__(self):
        return f"{self.display_name} ({self.organisation.slug})"

    @property
    def display_name(self) -> str:
        """Returns business trading name, falling back to canonical organisation name."""
        return self.business_name or (self.organisation.name if self.organisation_id else "")

    def clean(self):
        super().clean()
        if self.organisation_id and self.organisation.type != OrganisationTypeChoices.WORKSHOP:
            raise ValidationError({
                'organisation': f"Organisation must have type '{OrganisationTypeChoices.WORKSHOP}' to create a WorkshopProfile."
            })
        if self.currency:
            self.currency = self.currency.upper()

    def save(self, *args, **kwargs):
        if not self.business_name and self.organisation_id:
            self.business_name = self.organisation.name
        if not self.slug:
            if self.business_name:
                base_slug = slugify(self.business_name)
            elif self.organisation_id:
                base_slug = self.organisation.slug
            else:
                base_slug = "workshop"
            candidate = base_slug
            counter = 1
            while WorkshopProfile.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                candidate = f"{base_slug}-{counter}"
                counter += 1
            self.slug = candidate
        if self.currency:
            self.currency = self.currency.upper()
        self.full_clean()
        super().save(*args, **kwargs)


class WorkshopOperatingHours(BaseUUIDModel):
    """
    Operating hours and slot configuration per day of the week for a workshop.
    """
    workshop = models.ForeignKey(
        WorkshopProfile,
        on_delete=models.CASCADE,
        related_name='operating_hours',
    )
    day_of_week = models.IntegerField(choices=DayOfWeekChoices.choices)
    is_closed = models.BooleanField(default=False)
    open_time = models.TimeField(null=True, blank=True)
    close_time = models.TimeField(null=True, blank=True)
    slot_duration_minutes = models.PositiveIntegerField(
        default=60,
        validators=[MinValueValidator(15)],
    )

    class Meta:
        verbose_name = 'Workshop Operating Hours'
        verbose_name_plural = 'Workshop Operating Hours'
        unique_together = ('workshop', 'day_of_week')
        ordering = ['workshop', 'day_of_week']

    def __str__(self):
        day_name = DayOfWeekChoices(self.day_of_week).label
        if self.is_closed:
            return f"{self.workshop.display_name} - {day_name}: Closed"
        return f"{self.workshop.display_name} - {day_name}: {self.open_time} - {self.close_time}"

    def clean(self):
        super().clean()
        if not self.is_closed:
            if not self.open_time or not self.close_time:
                raise ValidationError("Open and close times are required when the workshop is not closed.")
            if self.open_time >= self.close_time:
                raise ValidationError("Close time must be after open time.")


class WorkshopServiceCategory(BaseUUIDModel):
    """
    Taxonomy for workshop services (e.g. MOT, Routine Servicing, Diagnostics, Tyres).
    """
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, db_index=True)
    description = models.TextField(blank=True)
    icon_name = models.CharField(max_length=50, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name = 'Workshop Service Category'
        verbose_name_plural = 'Workshop Service Categories'
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class WorkshopService(BaseUUIDModel):
    """
    Individual service offering provided by a workshop with pricing and duration.
    """
    workshop = models.ForeignKey(
        WorkshopProfile,
        on_delete=models.CASCADE,
        related_name='services',
    )
    category = models.ForeignKey(
        WorkshopServiceCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='workshop_services',
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    estimated_duration_minutes = models.PositiveIntegerField(
        default=60,
        validators=[MinValueValidator(5)],
    )
    base_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    currency = models.CharField(max_length=3, default='GBP')
    is_price_variable = models.BooleanField(
        default=False,
        help_text="If true, price is indicative or requires workshop inspection / quotation.",
    )
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name = 'Workshop Service'
        verbose_name_plural = 'Workshop Services'
        ordering = ['workshop', 'name']
        indexes = [
            models.Index(fields=['workshop', 'is_active']),
        ]

    def __str__(self):
        return f"{self.workshop.display_name} - {self.name} ({self.currency} {self.base_price})"

    def clean(self):
        super().clean()
        if self.workshop_id and not self.currency:
            self.currency = self.workshop.currency
        if self.currency:
            self.currency = self.currency.upper()

    def save(self, *args, **kwargs):
        if self.workshop_id and not self.currency:
            self.currency = self.workshop.currency
        if self.currency:
            self.currency = self.currency.upper()
        self.full_clean()
        super().save(*args, **kwargs)


class WorkshopBooking(BaseUUIDModel):
    """
    Customer booking request for workshop services.
    Captures buyer vehicle, preferred dates, fault descriptions, and status lifecycle.
    """
    booking_number = models.CharField(
        max_length=32,
        unique=True,
        editable=False,
        db_index=True,
        default=generate_booking_number,
    )
    workshop = models.ForeignKey(
        WorkshopProfile,
        on_delete=models.CASCADE,
        related_name='bookings',
    )
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='workshop_bookings',
    )
    vehicle = models.ForeignKey(
        'garage.GarageVehicle',
        on_delete=models.PROTECT,
        related_name='workshop_bookings',
    )

    # Vehicle historical snapshot (preserved even if vehicle is modified or archived)
    vehicle_make = models.CharField(max_length=100, blank=True)
    vehicle_model = models.CharField(max_length=150, blank=True)
    vehicle_year = models.PositiveIntegerField(null=True, blank=True)
    vehicle_registration_plate = models.CharField(max_length=30, blank=True)
    vehicle_vin = models.CharField(max_length=50, blank=True)
    current_odometer = models.PositiveIntegerField(null=True, blank=True)
    odometer_unit = models.CharField(max_length=10, default='mi')

    # Appointment preferences & schedule
    preferred_date = models.DateField()
    preferred_time_slot = models.CharField(max_length=50, blank=True)
    scheduled_appointment_start = models.DateTimeField(null=True, blank=True)
    scheduled_appointment_end = models.DateTimeField(null=True, blank=True)

    # Customer communication
    customer_notes = models.TextField(blank=True)
    reported_faults = models.TextField(blank=True)

    # Operations & Assignment
    assigned_technician = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_workshop_bookings',
    )
    internal_notes = models.TextField(blank=True)

    # Lifecycle & Decisions
    status = models.CharField(
        max_length=30,
        choices=BookingStatusChoices.choices,
        default=BookingStatusChoices.REQUESTED,
        db_index=True,
    )
    rejection_reason = models.TextField(blank=True)
    cancellation_reason = models.TextField(blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cancelled_workshop_bookings',
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Workshop Booking'
        verbose_name_plural = 'Workshop Bookings'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['workshop', 'status']),
            models.Index(fields=['buyer', 'status']),
            models.Index(fields=['preferred_date']),
            models.Index(fields=['workshop', 'scheduled_appointment_start', 'scheduled_appointment_end']),
        ]

    def __str__(self):
        return f"{self.booking_number} - {self.workshop.display_name} ({self.status})"

    def clean(self):
        super().clean()
        # Validate updates on existing bookings first
        if not self._state.adding and self.pk:
            try:
                db_inst = WorkshopBooking.objects.get(pk=self.pk)
                if db_inst.buyer_id != self.buyer_id:
                    raise ValidationError({'buyer': 'The buyer of an existing booking cannot be changed.'})
                if db_inst.vehicle_id != self.vehicle_id and self.vehicle.is_archived:
                    raise ValidationError({'vehicle': 'Cannot switch booking to an archived vehicle.'})
            except WorkshopBooking.DoesNotExist:
                pass

        if self.vehicle_id and self.buyer_id:
            # Validate vehicle ownership
            if self.vehicle.user_id != self.buyer_id:
                raise ValidationError({
                    'vehicle': 'The selected vehicle does not belong to the booking buyer.'
                })
            # Validate vehicle is not archived on booking creation
            if self.vehicle.is_archived and self._state.adding:
                raise ValidationError({
                    'vehicle': 'Cannot book an appointment for an archived vehicle.'
                })

        # Validate appointment scheduling boundaries
        if self._state.adding and self.preferred_date and self.preferred_date < timezone.now().date():
            raise ValidationError({'preferred_date': 'Preferred appointment date cannot be in the past.'})

        if self.scheduled_appointment_start and self.scheduled_appointment_end:
            if self.scheduled_appointment_end <= self.scheduled_appointment_start:
                raise ValidationError({'scheduled_appointment_end': 'Scheduled appointment end must be after start time.'})

    def save(self, *args, **kwargs):
        if not self.booking_number:
            self.booking_number = generate_booking_number()
        # Populate snapshot from vehicle if not already set
        if self.vehicle_id:
            if not self.vehicle_make:
                self.vehicle_make = self.vehicle.make
            if not self.vehicle_model:
                self.vehicle_model = self.vehicle.model
            if self.vehicle_year is None:
                self.vehicle_year = self.vehicle.year
            if not self.vehicle_registration_plate:
                self.vehicle_registration_plate = self.vehicle.registration_plate
            if not self.vehicle_vin:
                self.vehicle_vin = self.vehicle.vin
            if self.current_odometer is None:
                self.current_odometer = self.vehicle.current_odometer
            if not self.odometer_unit:
                self.odometer_unit = self.vehicle.odometer_unit

        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Prevent deletion of bookings that have accepted quotations or active legal records."""
        if self.quotations.filter(status=QuotationStatusChoices.ACCEPTED).exists():
            raise ValidationError(
                f"Booking {self.booking_number} has an accepted quotation and cannot be deleted."
            )
        super().delete(*args, **kwargs)


class BookingServiceItem(BaseUUIDModel):
    """
    Individual service item requested or attached to a booking.
    Stores historical price snapshot at booking time.
    """
    booking = models.ForeignKey(
        WorkshopBooking,
        on_delete=models.CASCADE,
        related_name='service_items',
    )
    service = models.ForeignKey(
        WorkshopService,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='booking_service_items',
    )
    service_name = models.CharField(max_length=200)
    service_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    currency = models.CharField(max_length=3, default='GBP')

    class Meta:
        verbose_name = 'Booking Service Item'
        verbose_name_plural = 'Booking Service Items'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.service_name} ({self.booking.booking_number})"

    def clean(self):
        super().clean()
        if self.currency:
            self.currency = self.currency.upper()

    def save(self, *args, **kwargs):
        if self.service_id:
            if not self.service_name:
                self.service_name = self.service.name
            if self.service_price == Decimal('0.00'):
                self.service_price = self.service.base_price
            if not self.currency:
                self.currency = self.service.currency
        if not self.currency and self.booking_id:
            self.currency = self.booking.workshop.currency
        if self.currency:
            self.currency = self.currency.upper()
        self.full_clean()
        super().save(*args, **kwargs)


class WorkshopQuotation(BaseUUIDModel):
    """
    Official formal estimate/quote provided by workshop for a booking.
    Supports versioning, line items breakdown, configurable taxes, and customer response.
    """
    quotation_number = models.CharField(
        max_length=32,
        unique=True,
        editable=False,
        db_index=True,
        default=generate_quotation_number,
    )
    booking = models.ForeignKey(
        WorkshopBooking,
        on_delete=models.PROTECT,
        related_name='quotations',
    )
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(
        max_length=30,
        choices=QuotationStatusChoices.choices,
        default=QuotationStatusChoices.DRAFT,
        db_index=True,
    )

    # Financial Breakdown (Strict Decimal arithmetic)
    subtotal_labour = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    subtotal_parts = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    subtotal_other = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    tax_rate_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        help_text="Configured or computed tax rate (e.g. 20.00 for 20% VAT, or 0.00 if exempt/unregistered).",
    )
    tax_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    currency = models.CharField(max_length=3, default='GBP')

    # Terms and Notes
    valid_until = models.DateField(null=True, blank=True)
    workshop_notes = models.TextField(blank=True)
    terms_and_conditions = models.TextField(blank=True)
    customer_rejection_reason = models.TextField(blank=True)

    # Attribution & Timestamps
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_quotations',
    )
    issued_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Workshop Quotation'
        verbose_name_plural = 'Workshop Quotations'
        ordering = ['booking', '-version']
        indexes = [
            models.Index(fields=['booking', 'status']),
            models.Index(fields=['status']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['booking', 'version'],
                name='unique_quotation_version_per_booking',
            ),
            models.UniqueConstraint(
                fields=['booking'],
                condition=models.Q(status=QuotationStatusChoices.ACCEPTED),
                name='unique_accepted_quotation_per_booking',
            ),
        ]

    def __str__(self):
        return f"{self.quotation_number} (v{self.version}) - {self.booking.booking_number} [{self.status}]"

    def clean(self):
        super().clean()
        booking_pk = self.booking_id or (self.booking.pk if getattr(self, 'booking', None) else None)

        # Ensure currency matches workshop currency
        if booking_pk and getattr(self, 'booking', None):
            workshop = self.booking.workshop
            if not self.currency:
                self.currency = workshop.currency
            elif self.currency.upper() != workshop.currency.upper():
                raise ValidationError({
                    'currency': f"Quotation currency ({self.currency}) must match workshop currency ({workshop.currency})."
                })

            # Inherit default workshop tax rate if new quotation has default 0.00 and workshop is tax registered
            if self._state.adding and self.tax_rate_percent == Decimal('0.00') and workshop.is_tax_registered:
                self.tax_rate_percent = workshop.default_tax_rate_percent

        if self.currency:
            self.currency = self.currency.upper()

        # Version auto-calculation for new instances
        if self._state.adding and booking_pk and self.version == 1:
            existing_max = WorkshopQuotation.objects.filter(booking_id=booking_pk).aggregate(models.Max('version'))['version__max']
            if existing_max is not None:
                self.version = existing_max + 1

        # Enforce immutability of ACCEPTED quotations
        if not self._state.adding and self.pk:
            try:
                db_instance = WorkshopQuotation.objects.get(pk=self.pk)
                if db_instance.status == QuotationStatusChoices.ACCEPTED:
                    # Prevent reverting status away from ACCEPTED
                    if self.status != QuotationStatusChoices.ACCEPTED:
                        raise ValidationError(
                            f"Quotation {self.quotation_number} has already been accepted and its status cannot be changed."
                        )
                    # Check if any financial or core content field was changed
                    immutable_fields = [
                        'subtotal_labour', 'subtotal_parts', 'subtotal_other',
                        'discount_amount', 'tax_rate_percent', 'tax_amount',
                        'total_amount', 'currency', 'version', 'booking_id'
                    ]
                    for field in immutable_fields:
                        if getattr(self, field) != getattr(db_instance, field):
                            raise ValidationError(
                                f"Quotation {self.quotation_number} is accepted and immutable. Field '{field}' cannot be modified."
                            )
            except WorkshopQuotation.DoesNotExist:
                pass

    def recalculate_totals(self, commit=False):
        """
        Recalculates financial subtotals and totals from attached line items using Decimal arithmetic.
        """
        labour = Decimal('0.00')
        parts = Decimal('0.00')
        other = Decimal('0.00')

        if self.pk and not self._state.adding:
            for item in self.line_items.all():
                if item.item_type == LineItemTypeChoices.LABOUR:
                    labour += item.line_total
                elif item.item_type == LineItemTypeChoices.PART:
                    parts += item.line_total
                else:
                    other += item.line_total

        self.subtotal_labour = labour.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        self.subtotal_parts = parts.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        self.subtotal_other = other.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        gross = self.subtotal_labour + self.subtotal_parts + self.subtotal_other
        net_subtotal = gross - self.discount_amount
        if net_subtotal < Decimal('0.00'):
            net_subtotal = Decimal('0.00')

        tax_mult = (self.tax_rate_percent / Decimal('100.00'))
        self.tax_amount = (net_subtotal * tax_mult).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        self.total_amount = (net_subtotal + self.tax_amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        if commit:
            self.save(update_fields=['subtotal_labour', 'subtotal_parts', 'subtotal_other', 'tax_amount', 'total_amount', 'updated_at'])

    def save(self, *args, **kwargs):
        if not self.quotation_number:
            self.quotation_number = generate_quotation_number()
        booking_pk = self.booking_id or (self.booking.pk if getattr(self, 'booking', None) else None)
        if self._state.adding and booking_pk and self.version == 1:
            existing_max = WorkshopQuotation.objects.filter(booking_id=booking_pk).aggregate(models.Max('version'))['version__max']
            if existing_max is not None:
                self.version = existing_max + 1

        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Prevent deletion of accepted quotations."""
        if self.status == QuotationStatusChoices.ACCEPTED:
            raise ValidationError(
                f"Quotation {self.quotation_number} has been accepted and cannot be deleted."
            )
        super().delete(*args, **kwargs)


class QuotationLineItem(BaseUUIDModel):
    """
    Detailed cost line item inside a workshop quotation.
    Categorised by labour, spare parts, diagnostics, disposal, or other fees.
    """
    quotation = models.ForeignKey(
        WorkshopQuotation,
        on_delete=models.CASCADE,
        related_name='line_items',
    )
    item_type = models.CharField(
        max_length=30,
        choices=LineItemTypeChoices.choices,
        default=LineItemTypeChoices.LABOUR,
    )
    description = models.CharField(max_length=255)
    part_number = models.CharField(max_length=100, blank=True)
    catalogue_part = models.ForeignKey(
        'catalogue.Part',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='quotation_line_items',
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('1.00'),
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    line_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
    )

    class Meta:
        verbose_name = 'Quotation Line Item'
        verbose_name_plural = 'Quotation Line Items'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.get_item_type_display()}: {self.description} ({self.line_total})"

    def clean(self):
        super().clean()
        # Validate that parent quotation is not accepted
        if self.quotation_id and self.quotation.status == QuotationStatusChoices.ACCEPTED:
            raise ValidationError("Cannot add or modify line items on an accepted quotation.")

    def save(self, *args, **kwargs):
        # Auto-compute line_total if not manually provided or ensure consistency
        if self.quantity is not None and self.unit_price is not None:
            self.line_total = (self.quantity * self.unit_price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        # Populate part_number from catalogue_part if blank
        if self.catalogue_part_id and not self.part_number:
            self.part_number = self.catalogue_part.mpn
        if self.catalogue_part_id and not self.description:
            self.description = f"{self.catalogue_part.brand} {self.catalogue_part.name}"

        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.quotation_id and self.quotation.status == QuotationStatusChoices.ACCEPTED:
            raise ValidationError("Cannot delete line items from an accepted quotation.")
        super().delete(*args, **kwargs)
