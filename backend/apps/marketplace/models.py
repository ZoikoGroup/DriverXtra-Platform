from django.db import models
from django.utils import timezone
from common.models import BaseUUIDModel
from apps.identity.models import User
from apps.organisations.models import Organisation
from apps.catalogue.models import (
    VehicleMake,
    VehicleModel,
    VehicleVariant,
    PartCategory,
    FuelTypeChoices,
    TransmissionChoices,
)


class ListingStatusChoices(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    PENDING_APPROVAL = 'PENDING_APPROVAL', 'Pending Approval'
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected'
    CHANGES_REQUESTED = 'CHANGES_REQUESTED', 'Changes Requested'


class VehicleConditionChoices(models.TextChoices):
    NEW = 'NEW', 'Brand New'
    EXCELLENT = 'EXCELLENT', 'Excellent'
    VERY_GOOD = 'VERY_GOOD', 'Very Good'
    GOOD = 'GOOD', 'Good'
    FAIR = 'FAIR', 'Fair'


from django.core.validators import MinValueValidator


class StockMovementReasonChoices(models.TextChoices):
    INITIAL = 'INITIAL', 'Initial Stock'
    ADJUSTMENT = 'ADJUSTMENT', 'Manual Adjustment'
    SALE = 'SALE', 'Customer Order / Sale'
    RETURN = 'RETURN', 'Customer Return / Restock'
    CORRECTION = 'CORRECTION', 'Inventory Audit / Correction'


class PartConditionChoices(models.TextChoices):
    NEW = 'NEW', 'Brand New (OEM/Aftermarket)'
    REFURBISHED = 'REFURBISHED', 'Remanufactured / Refurbished'
    USED = 'USED', 'Used / Dismantled'


class VehicleListing(BaseUUIDModel):
    """Seller inventory submission for vehicles for sale on the marketplace."""

    seller = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='vehicle_listings',
    )
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vehicle_listings',
    )
    title = models.CharField(max_length=255)
    make = models.ForeignKey(
        VehicleMake,
        on_delete=models.PROTECT,
        related_name='vehicle_listings',
    )
    model = models.ForeignKey(
        VehicleModel,
        on_delete=models.PROTECT,
        related_name='vehicle_listings',
    )
    variant = models.ForeignKey(
        VehicleVariant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vehicle_listings',
    )
    year = models.PositiveIntegerField()
    registration_number = models.CharField(max_length=20, blank=True)
    vin = models.CharField(max_length=50, blank=True)
    mileage = models.PositiveIntegerField(default=0)
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
    body_type = models.CharField(max_length=50, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default='GBP')
    condition = models.CharField(
        max_length=20,
        choices=VehicleConditionChoices.choices,
        default=VehicleConditionChoices.VERY_GOOD,
    )
    description = models.TextField(blank=True)
    primary_image_url = models.URLField(blank=True)
    images = models.JSONField(default=list, blank=True)
    location_city = models.CharField(max_length=100, blank=True)
    location_postcode = models.CharField(max_length=20, blank=True)

    # Workflow & Moderation
    status = models.CharField(
        max_length=30,
        choices=ListingStatusChoices.choices,
        default=ListingStatusChoices.PENDING_APPROVAL,
        db_index=True,
    )
    submitted_at = models.DateTimeField(default=timezone.now)
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_vehicle_listings',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    admin_notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name = 'Vehicle Listing'
        verbose_name_plural = 'Vehicle Listings'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'is_active']),
            models.Index(fields=['seller', 'status']),
            models.Index(fields=['make', 'model', 'year']),
        ]

    def __str__(self):
        return f"{self.title} (£{self.price}) - {self.status}"

    @property
    def masked_vin(self) -> str:
        if not self.vin:
            return ""
        clean = self.vin.strip()
        if len(clean) <= 6:
            return clean
        return f"{'*' * (len(clean) - 6)}{clean[-6:]}"

    @property
    def masked_registration(self) -> str:
        if not self.registration_number:
            return ""
        clean = self.registration_number.strip().upper()
        if len(clean) <= 3:
            return clean
        return f"{clean[:2]}** ***"


class SparePartListing(BaseUUIDModel):
    """Seller inventory submission for spare parts for sale on the marketplace."""

    seller = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='part_listings',
    )
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='part_listings',
    )
    name = models.CharField(max_length=255)
    brand = models.CharField(max_length=100)
    mpn = models.CharField(max_length=100, db_index=True)
    oem_numbers = models.JSONField(default=list, blank=True)
    category = models.ForeignKey(
        PartCategory,
        on_delete=models.PROTECT,
        related_name='part_listings',
    )
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default='GBP')
    stock_quantity = models.PositiveIntegerField(default=1)
    low_stock_threshold = models.PositiveIntegerField(
        default=3,
        validators=[MinValueValidator(0)],
        help_text="Stock count threshold below which an alert or low-stock badge is triggered.",
    )
    condition = models.CharField(
        max_length=20,
        choices=PartConditionChoices.choices,
        default=PartConditionChoices.NEW,
    )
    primary_image_url = models.URLField(blank=True)
    images = models.JSONField(default=list, blank=True)

    # Compatibility declaration
    compatible_variants = models.ManyToManyField(
        VehicleVariant,
        blank=True,
        related_name='compatible_marketplace_parts',
    )
    compatibility_notes = models.TextField(blank=True)

    # Workflow & Moderation
    status = models.CharField(
        max_length=30,
        choices=ListingStatusChoices.choices,
        default=ListingStatusChoices.PENDING_APPROVAL,
        db_index=True,
    )
    submitted_at = models.DateTimeField(default=timezone.now)
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_part_listings',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    admin_notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name = 'Spare Part Listing'
        verbose_name_plural = 'Spare Part Listings'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'is_active']),
            models.Index(fields=['seller', 'status']),
            models.Index(fields=['brand', 'mpn']),
            models.Index(fields=['category', 'status']),
        ]

    def __str__(self):
        return f"{self.brand} {self.mpn} - {self.name} (£{self.price}) - {self.status}"


class StockMovement(BaseUUIDModel):
    """Immutable ledger of inventory stock movements for SparePartListing."""

    listing = models.ForeignKey(
        SparePartListing,
        on_delete=models.CASCADE,
        related_name='stock_movements',
    )
    delta = models.IntegerField(help_text="Stock quantity change (+/-)")
    resulting_quantity = models.PositiveIntegerField(help_text="Stock quantity following movement")
    reason = models.CharField(
        max_length=20,
        choices=StockMovementReasonChoices.choices,
    )
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_movements',
    )
    note = models.TextField(blank=True, default='')

    class Meta:
        verbose_name = 'Stock Movement'
        verbose_name_plural = 'Stock Movements'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['listing', '-created_at']),
            models.Index(fields=['reason']),
        ]

    def __str__(self):
        sign = '+' if self.delta > 0 else ''
        return f"{self.listing.mpn}: {sign}{self.delta} -> {self.resulting_quantity} ({self.reason})"

    def save(self, *args, **kwargs):
        if not self._state.adding and self.pk and not getattr(self, '_allow_update', False):
            raise ValueError("StockMovement records are append-only and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if not getattr(self, '_allow_delete', False):
            raise ValueError("StockMovement records are immutable and cannot be deleted.")
        super().delete(*args, **kwargs)
