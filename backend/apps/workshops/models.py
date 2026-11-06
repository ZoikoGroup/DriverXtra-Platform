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


class DepositStatusChoices(models.TextChoices):
    NOT_REQUIRED = 'NOT_REQUIRED', 'Not Required'
    PENDING = 'PENDING', 'Pending Payment'
    PROCESSING = 'PROCESSING', 'Processing'
    PAID = 'PAID', 'Deposit Paid'
    FAILED = 'FAILED', 'Payment Failed'
    REFUNDED = 'REFUNDED', 'Refunded'


class LineItemTypeChoices(models.TextChoices):
    LABOUR = 'LABOUR', 'Labour'
    PART = 'PART', 'Spare Part'
    DIAGNOSTIC = 'DIAGNOSTIC', 'Diagnostics'
    DISPOSAL = 'DISPOSAL', 'Disposal & Environmental Fee'
    OTHER = 'OTHER', 'Other Charge'


class ReviewStatusChoices(models.TextChoices):
    PENDING = 'PENDING', 'Pending Moderation'
    APPROVED = 'APPROVED', 'Approved / Published'
    FLAGGED = 'FLAGGED', 'Flagged for Review'
    REJECTED = 'REJECTED', 'Rejected / Hidden'



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


class WorkOrderStatusChoices(models.TextChoices):
    ASSIGNED = 'ASSIGNED', 'Assigned'
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
    AWAITING_PARTS = 'AWAITING_PARTS', 'Awaiting Parts'
    QUALITY_CHECK = 'QUALITY_CHECK', 'Quality Check'
    COMPLETED = 'COMPLETED', 'Completed'
    CANCELLED = 'CANCELLED', 'Cancelled'


class WorkOrderTaskStatusChoices(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
    COMPLETED = 'COMPLETED', 'Completed'
    BLOCKED = 'BLOCKED', 'Blocked'


def generate_work_order_number() -> str:
    """Generates unique work order reference formatted as WO-YYYYMMDD-XXXXXX."""
    date_str = timezone.now().strftime('%Y%m%d')
    suffix = uuid.uuid4().hex[:6].upper()
    return f"WO-{date_str}-{suffix}"


class ChangeOrderStatusChoices(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    SUBMITTED = 'SUBMITTED', 'Submitted (Awaiting Approval)'
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected'
    CANCELLED = 'CANCELLED', 'Cancelled'


def generate_change_order_number() -> str:
    """Generates unique change order reference formatted as CO-YYYYMMDD-XXXXXX."""
    date_str = timezone.now().strftime('%Y%m%d')
    suffix = uuid.uuid4().hex[:6].upper()
    return f"CO-{date_str}-{suffix}"


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
    currency = models.CharField(max_length=3, blank=True, default='')
    bay_capacity = models.PositiveIntegerField(
        default=2,
        validators=[MinValueValidator(1)],
        help_text="Number of service bays available for simultaneous appointments.",
    )
    is_accepting_bookings = models.BooleanField(default=True, db_index=True)
    is_verified = models.BooleanField(default=True, db_index=True)

    # Tax configuration per workshop (not hardcoding UK 20% VAT platform-wide)
    is_tax_registered = models.BooleanField(
        default=False,
        help_text="Whether this workshop is recorded as registered for indirect taxes (e.g. VAT/GST). Structural tax ID validation is syntactic only and does not imply government portal verification.",
    )
    can_collect_tax = models.BooleanField(
        default=False,
        help_text="Explicit legal authorization to levy and collect indirect taxes (e.g. VAT/GST) from buyers.",
    )
    default_tax_rate_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        help_text="Default tax percentage rate for this workshop (e.g. 20.00 for 20% VAT, or 0.00 if exempt/unregistered).",
    )

    # Deposit configuration
    requires_deposit = models.BooleanField(
        default=False,
        help_text="Whether this workshop mandates an upfront deposit payment before confirming quotations and issuing work orders.",
    )
    default_deposit_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        help_text="Default deposit percentage required for quotations (e.g. 20.00 for 20%).",
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
        if self.organisation_id:
            org = self.organisation
            if org.type != OrganisationTypeChoices.WORKSHOP:
                raise ValidationError({
                    'organisation': f"Organisation must have type '{OrganisationTypeChoices.WORKSHOP}' to create a WorkshopProfile."
                })
            expected_currency = org.regional_specification.default_currency.value
            if not self.currency:
                self.currency = expected_currency
            elif self.currency.strip().upper() != expected_currency:
                raise ValidationError({
                    'currency': f"Workshop currency '{self.currency}' conflicts with organisation's regional currency '{expected_currency}'."
                })
            if not self.country:
                self.country = org.country
        if self.currency:
            self.currency = self.currency.strip().upper()

        if self.can_collect_tax and not self.is_tax_registered:
            raise ValidationError({
                'can_collect_tax': "Cannot authorize tax collection for a workshop that is not tax registered."
            })

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
    currency = models.CharField(max_length=3, blank=True, default='')
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
        if self.workshop_id:
            expected_currency = self.workshop.currency
            if not self.currency:
                self.currency = expected_currency
            elif self.currency.strip().upper() != expected_currency.upper():
                raise ValidationError({
                    'currency': f"Service currency '{self.currency}' conflicts with workshop currency '{expected_currency}'."
                })
        if self.currency:
            self.currency = self.currency.strip().upper()

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
    odometer_unit = models.CharField(max_length=10, blank=True, default='')

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
    currency = models.CharField(max_length=3, blank=True, default='')

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
    currency = models.CharField(max_length=3, blank=True, default='')
    tax_breakdown = models.JSONField(
        default=dict,
        blank=True,
        help_text="Immutable statutory tax calculation snapshot (document type, rates, components, legal citations).",
    )

    # Deposit Requirements & Payment State
    requires_deposit = models.BooleanField(
        default=False,
        help_text="Whether this quotation requires an upfront deposit payment before customer acceptance.",
    )
    deposit_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        help_text="Configured deposit percentage (e.g. 20.00 for 20%).",
    )
    deposit_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Calculated or explicitly specified deposit amount.",
    )
    deposit_status = models.CharField(
        max_length=30,
        choices=DepositStatusChoices.choices,
        default=DepositStatusChoices.NOT_REQUIRED,
        db_index=True,
    )
    deposit_paid_at = models.DateTimeField(null=True, blank=True)
    deposit_provider = models.CharField(max_length=50, blank=True, default='RAZORPAY')
    deposit_transaction_id = models.CharField(max_length=255, blank=True, default='', db_index=True)
    deposit_order_id = models.CharField(max_length=255, blank=True, default='', db_index=True)
    deposit_signature = models.CharField(max_length=255, blank=True, default='')
    deposit_idempotency_key = models.CharField(max_length=100, blank=True, default='', db_index=True)

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
            models.Index(fields=['deposit_status']),
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

            # Check tax collection authorization:
            # Prevent unauthorized tax collection
            if self.tax_rate_percent > Decimal('0.00') and not getattr(workshop, 'can_collect_tax', False):
                raise ValidationError({
                    'tax_rate_percent': f"Workshop '{workshop.display_name}' is not authorized to collect tax. Quotation tax rate must be 0.00%."
                })

            # Inherit default workshop tax rate if new quotation has default 0.00 and workshop is authorized to collect tax
            if self._state.adding and self.tax_rate_percent == Decimal('0.00') and getattr(workshop, 'can_collect_tax', False) and workshop.is_tax_registered:
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
                        'total_amount', 'currency', 'version', 'booking_id',
                        'tax_breakdown', 'requires_deposit', 'deposit_percentage',
                        'deposit_amount',
                    ]
                    for field in immutable_fields:
                        if getattr(self, field) != getattr(db_instance, field):
                            raise ValidationError(
                                f"Quotation {self.quotation_number} is accepted and immutable. Field '{field}' cannot be modified."
                            )
            except WorkshopQuotation.DoesNotExist:
                pass

        # Deposit validation
        if self.requires_deposit:
            if self.deposit_amount < Decimal('0.00'):
                raise ValidationError({'deposit_amount': "Deposit amount cannot be negative."})
            if self.total_amount > Decimal('0.00') and self.deposit_amount > self.total_amount:
                raise ValidationError({
                    'deposit_amount': f"Deposit amount ({self.currency} {self.deposit_amount}) cannot exceed total quotation amount ({self.currency} {self.total_amount})."
                })
        else:
            self.deposit_amount = Decimal('0.00')
            self.deposit_percentage = Decimal('0.00')
            if self.deposit_status != DepositStatusChoices.PAID:
                self.deposit_status = DepositStatusChoices.NOT_REQUIRED

    def recalculate_totals(self, commit=False):
        """
        Recalculates financial subtotals and totals from attached line items using Decimal arithmetic.
        """
        if self.pk and not self._state.adding:
            db_status = WorkshopQuotation.objects.filter(pk=self.pk).values_list('status', flat=True).first()
            if db_status == QuotationStatusChoices.ACCEPTED:
                raise ValidationError(
                    f"Quotation {self.quotation_number} has already been accepted and its totals cannot be recalculated."
                )
        elif self.status == QuotationStatusChoices.ACCEPTED:
            raise ValidationError(
                f"Quotation {self.quotation_number} has already been accepted and its totals cannot be recalculated."
            )

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

        # Statutory Tax Engine Integration
        booking_obj = getattr(self, 'booking', None)
        if self.pk and booking_obj and self.line_items.exists():
            workshop = getattr(booking_obj, 'workshop', None)
            org = getattr(workshop, 'organisation', None) if workshop else None
            country_code = getattr(workshop, 'country', 'GB') or 'GB'
            supplier_jur = getattr(org, 'jurisdiction', None) or ('GB-ENG' if country_code == 'GB' else 'IN-TG')
            supplier_tax_id = getattr(org, 'tax_id', '') or ''

            from platform_core.tax.choices import SupplierRegistrationState
            if not getattr(workshop, 'is_tax_registered', False):
                supp_state = SupplierRegistrationState.NOT_LIABLE_TO_REGISTER
            elif getattr(workshop, 'can_collect_tax', False):
                supp_state = SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION
            else:
                supp_state = SupplierRegistrationState.UNVERIFIED_REGISTRATION

            buyer = getattr(booking_obj, 'buyer', None)
            buyer_profile = getattr(buyer, 'profile', None) if buyer else None
            buyer_addr = ""
            if buyer_profile:
                buyer_addr = f"{getattr(buyer_profile, 'city', '')} {getattr(buyer_profile, 'state_province', '')}".strip()

            from platform_core.tax.models_data import TaxTransactionContext, TaxLineInput
            from platform_core.tax.engine import TaxEngineService

            tax_context = TaxTransactionContext(
                country_code=country_code,
                supplier_jurisdiction=supplier_jur,
                supplier_tax_id=supplier_tax_id,
                supplier_registration_state=supp_state,
                can_collect_tax=getattr(workshop, 'can_collect_tax', False),
                currency=self.currency or (workshop.currency if workshop else 'GBP'),
                transaction_date=self.created_at.strftime('%Y-%m-%d') if self.created_at else timezone.now().strftime('%Y-%m-%d'),
                customer_jurisdiction=getattr(buyer_profile, 'state_province', None) or None,
                customer_address_on_record=buyer_addr or None,
                physical_performance_jurisdiction=supplier_jur,
            )

            tax_lines = []
            for item in self.line_items.all():
                part_code = ""
                if item.catalogue_part and getattr(item.catalogue_part, 'mpn', None):
                    part_code = item.catalogue_part.mpn
                elif item.part_number:
                    part_code = item.part_number

                tax_lines.append(
                    TaxLineInput(
                        line_id=str(item.id),
                        item_type=item.item_type,
                        description=item.description,
                        taxable_amount=item.line_total,
                        classification_code=part_code or None,
                    )
                )

            tax_res = TaxEngineService.calculate_transaction_tax(
                context=tax_context,
                lines=tax_lines,
                discount_amount=self.discount_amount,
            )

            self.tax_breakdown = tax_res.to_snapshot()
            if not getattr(workshop, 'can_collect_tax', False):
                self.tax_amount = Decimal('0.00')
                self.total_amount = net_subtotal
                self.tax_rate_percent = Decimal('0.00')
            else:
                self.tax_amount = tax_res.tax_amount
                self.total_amount = tax_res.total_amount
                self.tax_rate_percent = tax_res.effective_tax_rate
        else:
            booking_obj = getattr(self, 'booking', None)
            workshop = getattr(booking_obj, 'workshop', None) if booking_obj else None
            if not getattr(workshop, 'can_collect_tax', False):
                self.tax_amount = Decimal('0.00')
                self.total_amount = net_subtotal
                self.tax_rate_percent = Decimal('0.00')
            else:
                tax_mult = (self.tax_rate_percent / Decimal('100.00'))
                self.tax_amount = (net_subtotal * tax_mult).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                self.total_amount = (net_subtotal + self.tax_amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        # Deposit recalculation
        if self.requires_deposit:
            if self.deposit_percentage > Decimal('0.00'):
                self.deposit_amount = (self.total_amount * (self.deposit_percentage / Decimal('100.00'))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            elif self.deposit_amount > self.total_amount:
                self.deposit_amount = self.total_amount
        else:
            self.deposit_amount = Decimal('0.00')
            self.deposit_percentage = Decimal('0.00')

        if commit:
            self.save(update_fields=[
                'subtotal_labour', 'subtotal_parts', 'subtotal_other', 'tax_amount',
                'total_amount', 'tax_rate_percent', 'tax_breakdown', 'requires_deposit',
                'deposit_percentage', 'deposit_amount', 'deposit_status', 'updated_at'
            ])

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


class WorkOrder(BaseUUIDModel):
    """
    Operational repair and service execution record.
    Generated automatically when a buyer accepts a WorkshopQuotation.
    Links the booking, quotation, assigned technicians, tasks, and consumed spare parts.
    """
    work_order_number = models.CharField(
        max_length=50,
        unique=True,
        default=generate_work_order_number,
        db_index=True,
        help_text="Unique work order reference number (e.g. WO-20261102-ABC123).",
    )
    booking = models.OneToOneField(
        'workshops.WorkshopBooking',
        on_delete=models.PROTECT,
        related_name='work_order',
        help_text="The parent booking. Exactly one work order per booking.",
    )
    quotation = models.ForeignKey(
        'workshops.WorkshopQuotation',
        on_delete=models.PROTECT,
        related_name='work_orders',
        help_text="The approved quotation authorizing this work order.",
    )
    workshop = models.ForeignKey(
        'workshops.WorkshopProfile',
        on_delete=models.CASCADE,
        related_name='work_orders',
    )
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='buyer_work_orders',
    )
    vehicle = models.ForeignKey(
        'garage.GarageVehicle',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='work_orders',
    )

    # Immutable vehicle snapshot fields (frozen from booking)
    vehicle_make = models.CharField(max_length=100, blank=True)
    vehicle_model = models.CharField(max_length=150, blank=True)
    vehicle_year = models.PositiveIntegerField(null=True, blank=True)
    vehicle_registration_plate = models.CharField(max_length=30, blank=True)
    vehicle_vin = models.CharField(max_length=50, blank=True)
    current_odometer = models.PositiveIntegerField(null=True, blank=True)
    odometer_unit = models.CharField(max_length=10, blank=True, default='')

    # Lead technician assignment
    lead_technician = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_work_orders',
        help_text="Technician responsible for supervising and performing work on this vehicle.",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='technician_assigned_work_orders',
    )
    assigned_at = models.DateTimeField(null=True, blank=True)

    # Status tracking
    status = models.CharField(
        max_length=30,
        choices=WorkOrderStatusChoices.choices,
        default=WorkOrderStatusChoices.ASSIGNED,
        db_index=True,
    )

    # Operational timestamps
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    quality_inspected_at = models.DateTimeField(null=True, blank=True)
    quality_inspected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inspected_work_orders',
    )

    # Notes & quality audit
    internal_notes = models.TextField(blank=True, help_text="Workshop-only operational notes.")
    quality_notes = models.TextField(blank=True, help_text="Notes from quality inspection.")
    cancellation_reason = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Work Order'
        verbose_name_plural = 'Work Orders'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['workshop', 'status']),
            models.Index(fields=['lead_technician', 'status']),
            models.Index(fields=['booking']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.work_order_number} ({self.get_status_display()}) - {self.vehicle_registration_plate}"

    @property
    def total_parts_cost(self) -> Decimal:
        return sum(
            (p.total_cost for p in self.parts_used.all()),
            Decimal('0.00'),
        )

    @property
    def total_actual_labour_minutes(self) -> int:
        return sum(
            (t.actual_labour_minutes for t in self.tasks.all()),
            0,
        )

    @property
    def total_estimated_labour_minutes(self) -> int:
        return sum(
            (t.estimated_labour_minutes for t in self.tasks.all()),
            0,
        )

    @property
    def authorized_total_amount(self) -> Decimal:
        base = self.quotation.total_amount if self.quotation else Decimal('0.00')
        approved_additions = sum(
            (co.additional_amount for co in self.change_orders.filter(status=ChangeOrderStatusChoices.APPROVED)),
            Decimal('0.00'),
        )
        return (base + approved_additions).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def approved_change_orders_amount(self) -> Decimal:
        return sum(
            (co.additional_amount for co in self.change_orders.filter(status=ChangeOrderStatusChoices.APPROVED)),
            Decimal('0.00'),
        ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def has_pending_change_orders(self) -> bool:
        return self.change_orders.filter(status=ChangeOrderStatusChoices.SUBMITTED).exists()

    def clean(self):
        super().clean()
        # Work order must only be linked to an accepted quotation
        if self.quotation_id and self.quotation.status != QuotationStatusChoices.ACCEPTED:
            raise ValidationError("Work orders can only be created for accepted quotations.")
        # Work order quotation must belong to the linked booking
        if self.booking_id and self.quotation_id and self.quotation.booking_id != self.booking_id:
            raise ValidationError("Quotation must belong to the linked booking.")
        # If lead technician is set, validate they belong to the workshop organisation
        if self.lead_technician_id and self.workshop_id:
            org = self.workshop.organisation
            is_member = org.memberships.filter(user_id=self.lead_technician_id, is_active=True).exists()
            if not is_member and not (self.lead_technician.is_staff or self.lead_technician.is_superuser):
                raise ValidationError("Lead technician must be an active member of this workshop organisation.")


class WorkOrderTask(BaseUUIDModel):
    """
    Individual repair or service task assigned to a technician on a work order.
    """
    work_order = models.ForeignKey(
        WorkOrder,
        on_delete=models.CASCADE,
        related_name='tasks',
    )
    description = models.CharField(max_length=255)
    assigned_technician = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='work_order_tasks',
    )
    estimated_labour_minutes = models.PositiveIntegerField(
        default=60,
        help_text="Estimated task duration in minutes.",
    )
    actual_labour_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Actual tracked technician labour time in minutes.",
    )
    status = models.CharField(
        max_length=20,
        choices=WorkOrderTaskStatusChoices.choices,
        default=WorkOrderTaskStatusChoices.PENDING,
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    order_index = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Work Order Task'
        verbose_name_plural = 'Work Order Tasks'
        ordering = ['order_index', 'created_at']

    def __str__(self):
        return f"{self.work_order.work_order_number} - {self.description} ({self.get_status_display()})"

    def clean(self):
        super().clean()
        if self.assigned_technician_id and self.work_order_id:
            org = self.work_order.workshop.organisation
            is_member = org.memberships.filter(user_id=self.assigned_technician_id, is_active=True).exists()
            if not is_member and not (self.assigned_technician.is_staff or self.assigned_technician.is_superuser):
                raise ValidationError("Assigned technician must belong to this workshop organisation.")


class WorkOrderPartUsage(BaseUUIDModel):
    """
    Record of physical spare parts consumed during execution of a work order.
    Calculates cost using Decimal arithmetic.
    """
    work_order = models.ForeignKey(
        WorkOrder,
        on_delete=models.CASCADE,
        related_name='parts_used',
    )
    part_name = models.CharField(max_length=255)
    part_number = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    catalogue_part = models.ForeignKey(
        'catalogue.Part',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='work_order_usages',
        help_text="Optional link to DriverXtra global catalogue part.",
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('1.00'),
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    unit_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    total_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    usage_date = models.DateField(default=timezone.now)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recorded_part_usages',
    )
    inventory_item = models.ForeignKey(
        'marketplace.SparePartListing',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='work_order_usages',
        help_text="Workshop inventory listing from which stock is decremented.",
    )
    is_stock_deducted = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Flag indicating whether inventory stock was deducted for this usage.",
    )

    class Meta:
        verbose_name = 'Work Order Part Usage'
        verbose_name_plural = 'Work Order Part Usages'
        ordering = ['-usage_date', '-created_at']

    def __str__(self):
        return f"{self.part_name} x {self.quantity} (£{self.total_cost})"

    def clean(self):
        super().clean()
        if self.quantity is not None and self.quantity <= Decimal('0.00'):
            raise ValidationError({'quantity': "Quantity must be greater than zero."})
        if self.unit_cost is not None and self.unit_cost < Decimal('0.00'):
            raise ValidationError({'unit_cost': "Unit cost cannot be negative."})

    def save(self, *args, **kwargs):
        if self.quantity is not None and self.unit_cost is not None:
            self.total_cost = (self.quantity * self.unit_cost).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        self.full_clean()
        super().save(*args, **kwargs)

class ChangeOrder(BaseUUIDModel):
    """
    Formal change order / additional repair authorization request raised during work order execution.
    Requires explicit buyer approval before additional repairs or parts are executed.
    Preserves original quotation and prior change orders in an immutable audit trail.
    """
    change_order_number = models.CharField(
        max_length=50,
        unique=True,
        default=generate_change_order_number,
        db_index=True,
        help_text="Unique change order reference (e.g. CO-20261102-ABC123).",
    )
    work_order = models.ForeignKey(
        'workshops.WorkOrder',
        on_delete=models.PROTECT,
        related_name='change_orders',
        help_text="The work order this change order applies to.",
    )
    version = models.PositiveIntegerField(
        default=1,
        help_text="Sequential change order revision number for this work order.",
    )
    status = models.CharField(
        max_length=30,
        choices=ChangeOrderStatusChoices.choices,
        default=ChangeOrderStatusChoices.DRAFT,
        db_index=True,
    )
    reason = models.TextField(
        help_text="Detailed diagnosis and justification explaining why additional repairs/parts are required.",
    )

    # Financial breakdown of additional work
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
    )
    tax_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    additional_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Net additional cost of this change order (net subtotal + tax).",
    )
    revised_authorized_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Cumulative authorized total for the work order if this change order is approved.",
    )
    currency = models.CharField(max_length=3, blank=True, default='')
    tax_breakdown = models.JSONField(
        default=dict,
        blank=True,
        help_text="Immutable statutory tax calculation snapshot for this change order.",
    )

    # Attribution & Timestamps
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_change_orders',
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_change_orders',
        help_text="Buyer who approved or rejected this change order.",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    buyer_notes = models.TextField(
        blank=True,
        help_text="Buyer decision comments or rejection explanation.",
    )
    workshop_notes = models.TextField(
        blank=True,
        help_text="Internal workshop remarks regarding this change order.",
    )

    class Meta:
        verbose_name = 'Change Order'
        verbose_name_plural = 'Change Orders'
        ordering = ['work_order', 'version']
        indexes = [
            models.Index(fields=['work_order', 'status']),
            models.Index(fields=['status']),
            models.Index(fields=['change_order_number']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['work_order', 'version'],
                name='unique_change_order_version_per_work_order',
            ),
        ]

    def __str__(self):
        return f"{self.change_order_number} (Rev {self.version}) - {self.work_order.work_order_number} [{self.get_status_display()}]"

    def clean(self):
        super().clean()
        if self.work_order_id:
            wo = self.work_order
            if not self.currency:
                self.currency = wo.quotation.currency if wo.quotation else wo.workshop.currency
            elif wo.quotation and self.currency.upper() != wo.quotation.currency.upper():
                raise ValidationError({
                    'currency': f"Change order currency ({self.currency}) must match work order currency ({wo.quotation.currency})."
                })

            if self._state.adding and wo.status in (WorkOrderStatusChoices.COMPLETED, WorkOrderStatusChoices.CANCELLED):
                raise ValidationError(f"Cannot create a change order for a {wo.get_status_display().lower()} work order.")

            if self._state.adding and self.version == 1:
                existing_max = ChangeOrder.objects.filter(work_order_id=wo.id).aggregate(models.Max('version'))['version__max']
                if existing_max is not None:
                    self.version = existing_max + 1

        if self.currency:
            self.currency = self.currency.upper()

        # Enforce immutability of APPROVED / REJECTED change orders
        if not self._state.adding and self.pk:
            try:
                db_instance = ChangeOrder.objects.get(pk=self.pk)
                if db_instance.status in (ChangeOrderStatusChoices.APPROVED, ChangeOrderStatusChoices.REJECTED):
                    if self.status != db_instance.status:
                        raise ValidationError(
                            f"Change Order {self.change_order_number} is in terminal status '{db_instance.status}' and cannot be modified."
                        )
                    immutable_fields = [
                        'subtotal_labour', 'subtotal_parts', 'subtotal_other',
                        'discount_amount', 'tax_rate_percent', 'tax_amount',
                        'additional_amount', 'revised_authorized_total', 'currency', 'version', 'work_order_id',
                        'tax_breakdown'
                    ]
                    for field in immutable_fields:
                        if getattr(self, field) != getattr(db_instance, field):
                            raise ValidationError(
                                f"Change Order {self.change_order_number} is immutable. Field '{field}' cannot be modified."
                            )
            except ChangeOrder.DoesNotExist:
                pass

    def recalculate_totals(self, commit=False):
        """
        Recalculates financial subtotals, tax, additional amount and cumulative authorized total.
        """
        if self.pk and not self._state.adding:
            db_status = ChangeOrder.objects.filter(pk=self.pk).values_list('status', flat=True).first()
            if db_status in (ChangeOrderStatusChoices.APPROVED, ChangeOrderStatusChoices.REJECTED):
                raise ValidationError(
                    f"Change Order {self.change_order_number} is in terminal status '{db_status}' and cannot be recalculated."
                )
        elif self.status in (ChangeOrderStatusChoices.APPROVED, ChangeOrderStatusChoices.REJECTED):
            raise ValidationError(
                f"Change Order {self.change_order_number} is in terminal status '{self.status}' and cannot be recalculated."
            )

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

        # Statutory Tax Engine Integration
        wo = getattr(self, 'work_order', None)
        if self.pk and wo and self.line_items.exists():
            workshop = getattr(wo, 'workshop', None)
            org = getattr(workshop, 'organisation', None) if workshop else None
            country_code = getattr(workshop, 'country', 'GB') or 'GB'
            supplier_jur = getattr(org, 'jurisdiction', None) or ('GB-ENG' if country_code == 'GB' else 'IN-TG')
            supplier_tax_id = getattr(org, 'tax_id', '') or ''

            from platform_core.tax.choices import SupplierRegistrationState
            if not getattr(workshop, 'is_tax_registered', False):
                supp_state = SupplierRegistrationState.NOT_LIABLE_TO_REGISTER
            elif getattr(workshop, 'can_collect_tax', False):
                supp_state = SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION
            else:
                supp_state = SupplierRegistrationState.UNVERIFIED_REGISTRATION

            booking_obj = getattr(wo, 'booking', None) or (wo.quotation.booking if (getattr(wo, 'quotation', None) and getattr(wo.quotation, 'booking', None)) else None)
            buyer = getattr(booking_obj, 'buyer', None)
            buyer_profile = getattr(buyer, 'profile', None) if buyer else None
            buyer_addr = ""
            if buyer_profile:
                buyer_addr = f"{getattr(buyer_profile, 'city', '')} {getattr(buyer_profile, 'state_province', '')}".strip()

            from platform_core.tax.models_data import TaxTransactionContext, TaxLineInput
            from platform_core.tax.engine import TaxEngineService

            tax_context = TaxTransactionContext(
                country_code=country_code,
                supplier_jurisdiction=supplier_jur,
                supplier_tax_id=supplier_tax_id,
                supplier_registration_state=supp_state,
                can_collect_tax=getattr(workshop, 'can_collect_tax', False),
                currency=self.currency or (workshop.currency if workshop else 'GBP'),
                transaction_date=self.created_at.strftime('%Y-%m-%d') if self.created_at else timezone.now().strftime('%Y-%m-%d'),
                customer_jurisdiction=getattr(buyer_profile, 'state_province', None) or None,
                customer_address_on_record=buyer_addr or None,
                physical_performance_jurisdiction=supplier_jur,
            )

            tax_lines = []
            for item in self.line_items.all():
                part_code = ""
                if item.catalogue_part and getattr(item.catalogue_part, 'mpn', None):
                    part_code = item.catalogue_part.mpn
                elif item.part_number:
                    part_code = item.part_number

                tax_lines.append(
                    TaxLineInput(
                        line_id=str(item.id),
                        item_type=item.item_type,
                        description=item.description,
                        taxable_amount=item.line_total,
                        classification_code=part_code or None,
                    )
                )

            tax_res = TaxEngineService.calculate_transaction_tax(
                context=tax_context,
                lines=tax_lines,
                discount_amount=self.discount_amount,
            )

            self.tax_breakdown = tax_res.to_snapshot()
            if not getattr(workshop, 'can_collect_tax', False):
                self.tax_amount = Decimal('0.00')
                self.tax_rate_percent = Decimal('0.00')
                self.additional_amount = net_subtotal
            else:
                self.tax_amount = tax_res.tax_amount
                self.tax_rate_percent = tax_res.effective_tax_rate
                self.additional_amount = (net_subtotal + self.tax_amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        else:
            wo = getattr(self, 'work_order', None)
            workshop = getattr(wo, 'workshop', None) if wo else None
            if not getattr(workshop, 'can_collect_tax', False):
                self.tax_amount = Decimal('0.00')
                self.tax_rate_percent = Decimal('0.00')
                self.additional_amount = net_subtotal
            else:
                tax_mult = (self.tax_rate_percent / Decimal('100.00'))
                self.tax_amount = (net_subtotal * tax_mult).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                self.additional_amount = (net_subtotal + self.tax_amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        base_quote_total = Decimal('0.00')
        prior_approved = Decimal('0.00')
        if self.work_order_id:
            wo = self.work_order
            base_quote_total = wo.quotation.total_amount if wo.quotation else Decimal('0.00')
            prior_approved = sum(
                (co.additional_amount for co in wo.change_orders.filter(status=ChangeOrderStatusChoices.APPROVED).exclude(id=self.id)),
                Decimal('0.00'),
            )
        self.revised_authorized_total = (base_quote_total + prior_approved + self.additional_amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        if commit:
            self.save(update_fields=[
                'subtotal_labour', 'subtotal_parts', 'subtotal_other',
                'tax_amount', 'additional_amount', 'revised_authorized_total',
                'tax_rate_percent', 'tax_breakdown', 'updated_at'
            ])

    def save(self, *args, **kwargs):
        if not self.change_order_number:
            self.change_order_number = generate_change_order_number()
        if self._state.adding and self.work_order_id and self.version == 1:
            existing_max = ChangeOrder.objects.filter(work_order_id=self.work_order_id).aggregate(models.Max('version'))['version__max']
            if existing_max is not None:
                self.version = existing_max + 1

        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status in (ChangeOrderStatusChoices.APPROVED, ChangeOrderStatusChoices.SUBMITTED):
            raise ValidationError(
                f"Change Order {self.change_order_number} is in '{self.status}' status and cannot be deleted."
            )
        super().delete(*args, **kwargs)


class ChangeOrderLineItem(BaseUUIDModel):
    """
    Detailed cost and scope line item inside a change order.
    """
    change_order = models.ForeignKey(
        ChangeOrder,
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
        related_name='change_order_line_items',
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
    estimated_labour_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Estimated minutes for labour/diagnostic items.",
    )

    class Meta:
        verbose_name = 'Change Order Line Item'
        verbose_name_plural = 'Change Order Line Items'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.get_item_type_display()}: {self.description} ({self.line_total})"

    def clean(self):
        super().clean()
        if self.change_order_id and self.change_order.status in (ChangeOrderStatusChoices.APPROVED, ChangeOrderStatusChoices.REJECTED):
            raise ValidationError("Cannot add or modify line items on a resolved change order.")

    def save(self, *args, **kwargs):
        if self.quantity is not None and self.unit_price is not None:
            qty = Decimal(str(self.quantity))
            price = Decimal(str(self.unit_price))
            self.line_total = (qty * price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        if self.catalogue_part_id and not self.part_number:
            self.part_number = self.catalogue_part.mpn
        if self.catalogue_part_id and not self.description:
            self.description = f"{self.catalogue_part.brand} {self.catalogue_part.name}"
        if self.item_type in (LineItemTypeChoices.LABOUR, LineItemTypeChoices.DIAGNOSTIC) and not self.estimated_labour_minutes:
            quantity = Decimal(str(self.quantity)) if self.quantity is not None else Decimal('1.00')
            self.estimated_labour_minutes = int((quantity * Decimal('60')).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.change_order_id and self.change_order.status in (ChangeOrderStatusChoices.APPROVED, ChangeOrderStatusChoices.REJECTED):
            raise ValidationError("Cannot delete line items from a resolved change order.")
        super().delete(*args, **kwargs)


class WorkshopReview(BaseUUIDModel):
    """
    Verified customer rating and review for a completed WorkshopBooking / WorkOrder.
    Enforces strictly 1 review per booking at the database level via OneToOneField.
    """
    workshop = models.ForeignKey(
        'workshops.WorkshopProfile',
        on_delete=models.PROTECT,
        related_name='reviews',
        db_index=True,
        help_text="The reviewed workshop service centre.",
    )
    booking = models.OneToOneField(
        'workshops.WorkshopBooking',
        on_delete=models.PROTECT,
        related_name='review',
        help_text="The completed booking. Exactly one review per service.",
    )
    work_order = models.OneToOneField(
        'workshops.WorkOrder',
        on_delete=models.PROTECT,
        related_name='review',
        help_text="The completed work order verifying execution.",
    )
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='workshop_reviews',
        help_text="The verified customer submitting the feedback.",
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Overall workshop experience rating (1 to 5 stars).",
    )
    communication_rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True,
        blank=True,
        help_text="Rating for customer service and communication (1-5).",
    )
    workmanship_rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True,
        blank=True,
        help_text="Rating for quality of repair and technical execution (1-5).",
    )
    pricing_transparency_rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True,
        blank=True,
        help_text="Rating for estimate accuracy and transparent billing (1-5).",
    )
    title = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="Short headline summary of the review.",
    )
    comment = models.TextField(
        help_text="Detailed written feedback regarding the workshop experience.",
    )
    status = models.CharField(
        max_length=20,
        choices=ReviewStatusChoices.choices,
        default=ReviewStatusChoices.APPROVED,
        db_index=True,
    )
    is_verified_service = models.BooleanField(
        default=True,
        help_text="Affirms review is tied to a verified completed WorkOrder.",
    )
    workshop_reply = models.TextField(
        blank=True,
        default='',
        help_text="Public response from the workshop owner or staff.",
    )
    workshop_reply_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when the workshop posted their reply.",
    )
    workshop_replied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='replied_workshop_reviews',
        help_text="Workshop staff user who posted the reply.",
    )
    helpful_votes = models.PositiveIntegerField(
        default=0,
        help_text="Count of community members who found this review helpful.",
    )

    class Meta:
        verbose_name = 'Workshop Review'
        verbose_name_plural = 'Workshop Reviews'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['workshop', 'status', '-created_at']),
            models.Index(fields=['buyer', '-created_at']),
        ]

    def __str__(self):
        return f"Review ({self.rating}★) for {self.workshop.business_name} by {self.buyer.email}"

    def clean(self):
        super().clean()
        if self.booking_id and self.work_order_id:
            if self.work_order.booking_id != self.booking_id:
                raise ValidationError("Work order does not belong to this booking.")
        if self.booking_id and self.workshop_id:
            if self.booking.workshop_id != self.workshop_id:
                raise ValidationError("Booking does not belong to this workshop.")
        if self.work_order_id and self.workshop_id:
            if self.work_order.workshop_id != self.workshop_id:
                raise ValidationError("Work order does not belong to this workshop.")
        if self.booking_id and self.buyer_id:
            if self.booking.buyer_id != self.buyer_id:
                raise ValidationError("Buyer does not match the booking customer.")


class WorkshopDepositWebhookEvent(BaseUUIDModel):
    """
    Authoritative audit record of incoming payment gateway webhooks (e.g. Razorpay/Stripe)
    for workshop quotation deposits. Guarantees idempotent event processing and replay protection.
    """
    event_id = models.CharField(max_length=255, unique=True, db_index=True)
    provider = models.CharField(max_length=50, default='RAZORPAY')
    event_type = models.CharField(max_length=100)
    quotation = models.ForeignKey(
        WorkshopQuotation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deposit_webhook_events',
    )
    processed = models.BooleanField(default=False, db_index=True)
    payload = models.JSONField(default=dict)
    error_message = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Workshop Deposit Webhook Event'
        verbose_name_plural = 'Workshop Deposit Webhook Events'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.provider}:{self.event_type} [{self.event_id}] - Processed: {self.processed}"


class SenderTypeChoices(models.TextChoices):
    BUYER = 'BUYER', 'Buyer'
    WORKSHOP = 'WORKSHOP', 'Workshop'
    SYSTEM = 'SYSTEM', 'System'


class WorkshopConversation(BaseUUIDModel):
    """
    A persistent conversation thread linked to a specific WorkshopBooking
    between the vehicle owner (buyer) and the workshop staff.
    """
    booking = models.OneToOneField(
        WorkshopBooking,
        on_delete=models.CASCADE,
        related_name='conversation',
    )
    workshop = models.ForeignKey(
        WorkshopProfile,
        on_delete=models.CASCADE,
        related_name='conversations',
    )
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='workshop_conversations',
    )
    last_message_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        verbose_name = 'Workshop Conversation'
        verbose_name_plural = 'Workshop Conversations'
        ordering = ['-last_message_at']
        indexes = [
            models.Index(fields=['workshop', '-last_message_at']),
            models.Index(fields=['buyer', '-last_message_at']),
        ]

    def __str__(self):
        booking_no = getattr(self.booking, 'booking_number', str(self.booking_id))
        return f"Conversation for Booking {booking_no}"

    def clean(self):
        super().clean()
        if self.booking_id and self.workshop_id:
            if self.booking.workshop_id != self.workshop_id:
                raise ValidationError("Workshop must match booking workshop.")
        if self.booking_id and self.buyer_id:
            if self.booking.buyer_id != self.buyer_id:
                raise ValidationError("Buyer must match booking buyer.")


class WorkshopMessage(BaseUUIDModel):
    """
    An individual message in a WorkshopConversation, persisted in PostgreSQL.
    """
    conversation = models.ForeignKey(
        WorkshopConversation,
        on_delete=models.CASCADE,
        related_name='messages',
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='workshop_sent_messages',
    )
    sender_type = models.CharField(
        max_length=20,
        choices=SenderTypeChoices.choices,
        default=SenderTypeChoices.BUYER,
    )
    content = models.TextField()
    attachment_url = models.CharField(max_length=500, blank=True, default='')
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Workshop Message'
        verbose_name_plural = 'Workshop Messages'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['conversation', 'created_at']),
            models.Index(fields=['conversation', 'is_read']),
        ]

    def __str__(self):
        return f"Msg {self.id} by {self.sender_id} [{self.sender_type}] in {self.conversation_id}"



