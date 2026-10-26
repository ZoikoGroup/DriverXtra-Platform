from decimal import Decimal
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
    Part,
    FuelTypeChoices,
    TransmissionChoices,
)
from apps.marketplace.tax import calculate_gst_breakdown


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
    catalogue_part = models.ForeignKey(
        Part,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='marketplace_offers',
    )
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    compare_at_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
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
    # Tax & HSN classification (Indian GST compliance)
    hsn_code = models.CharField(max_length=20, blank=True, default='')
    gst_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Applicable GST percentage (e.g. 5.00, 12.00, 18.00, 28.00).",
    )
    is_tax_verified = models.BooleanField(
        default=True,
        help_text="Indicates whether the HSN and GST rate combination is verified against official CBIC schedules.",
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
            models.Index(fields=['catalogue_part', 'status']),
        ]

    def __str__(self):
        return f"{self.brand} {self.mpn} - {self.name} (£{self.price}) - {self.status}"

    @property
    def price_before_gst(self) -> Decimal:
        return self.price

    @property
    def tax_breakdown(self) -> dict:
        return calculate_gst_breakdown(self.price, self.gst_rate)

    @property
    def gst_amount(self) -> Decimal:
        return self.tax_breakdown['gst_amount']

    @property
    def total_price(self) -> Decimal:
        return self.tax_breakdown['total_price']

    def get_tax_breakdown(self, place_of_supply=None, seller_state=None) -> dict:
        return calculate_gst_breakdown(
            price=self.price,
            gst_rate=self.gst_rate,
            place_of_supply=place_of_supply,
            seller_state=seller_state,
        )


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


class ImmutableRecordError(NotImplementedError, ValueError):
    """Exception raised when an attempt is made to mutate or delete append-only ledger entries."""
    pass


class PriceChangeQuerySet(models.QuerySet):
    """QuerySet that enforces append-only semantics for PriceChange records."""

    def update(self, **kwargs):
        raise ImmutableRecordError("PriceChange records are append-only and cannot be updated.")

    def delete(self):
        raise ImmutableRecordError("PriceChange records are append-only and cannot be deleted.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ImmutableRecordError("PriceChange records are append-only and cannot be updated.")


class PriceChange(BaseUUIDModel):
    """Immutable ledger of price and compare_at_price modifications for SparePartListing."""

    listing = models.ForeignKey(
        SparePartListing,
        on_delete=models.CASCADE,
        related_name='price_changes',
    )
    old_price = models.DecimalField(max_digits=10, decimal_places=2)
    new_price = models.DecimalField(max_digits=10, decimal_places=2)
    old_compare_at_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    new_compare_at_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='price_changes',
    )
    note = models.CharField(max_length=255, blank=True, default='')

    objects = PriceChangeQuerySet.as_manager()

    class Meta:
        verbose_name = 'Price Change'
        verbose_name_plural = 'Price Changes'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['listing', '-created_at']),
        ]

    def __str__(self):
        return f"{self.listing.mpn}: £{self.old_price} -> £{self.new_price}"

    def save(self, *args, **kwargs):
        if not self._state.adding and self.pk and not getattr(self, '_allow_update', False):
            raise ImmutableRecordError("PriceChange records are append-only and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if not getattr(self, '_allow_delete', False):
            raise ImmutableRecordError("PriceChange records are immutable and cannot be deleted.")
        super().delete(*args, **kwargs)


class BuyerFavouriteVehicle(BaseUUIDModel):
    """Saves an approved vehicle listing to an authenticated buyer's favourites list."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='favourite_vehicles',
        help_text="The buyer account who saved this vehicle.",
    )
    vehicle = models.ForeignKey(
        VehicleListing,
        on_delete=models.CASCADE,
        related_name='favourited_by',
        help_text="The vehicle listing saved as favourite.",
    )

    class Meta:
        verbose_name = 'Buyer Favourite Vehicle'
        verbose_name_plural = 'Buyer Favourite Vehicles'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'vehicle'],
                name='unique_buyer_vehicle_favourite',
            )
        ]
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['vehicle']),
        ]

    def __str__(self):
        return f"{self.user.email} -> {self.vehicle.title} ({self.vehicle_id})"

    @property
    def buyer(self):
        return self.user

    @property
    def listing(self):
        return self.vehicle


class BuyerFavouritePart(BaseUUIDModel):
    """Saves an approved spare part listing to an authenticated buyer's favourites list."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='favourite_parts',
        help_text="The buyer account who saved this spare part.",
    )
    part = models.ForeignKey(
        SparePartListing,
        on_delete=models.CASCADE,
        related_name='favourited_by',
        help_text="The spare part listing saved as favourite.",
    )

    class Meta:
        verbose_name = 'Buyer Favourite Spare Part'
        verbose_name_plural = 'Buyer Favourite Spare Parts'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'part'],
                name='unique_buyer_part_favourite',
            )
        ]
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['part']),
        ]

    def __str__(self):
        return f"{self.user.email} -> {self.part.name} ({self.part_id})"

    @property
    def buyer(self):
        return self.user

    @property
    def listing(self):
        return self.part


class OrderStatusChoices(models.TextChoices):
    PENDING_CONFIRMATION = 'PENDING_CONFIRMATION', 'Pending Confirmation'
    CONFIRMED = 'CONFIRMED', 'Confirmed'
    PROCESSING = 'PROCESSING', 'Processing'
    COMPLETED = 'COMPLETED', 'Completed'
    CANCELLED = 'CANCELLED', 'Cancelled'


class Order(BaseUUIDModel):
    """Customer purchase order recording immutable financial and tax snapshots."""

    buyer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='buyer_orders',
    )
    order_number = models.CharField(max_length=50, unique=True, db_index=True)
    idempotency_key = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
        help_text="Unique client-supplied idempotency key preventing duplicate order submissions.",
    )
    status = models.CharField(
        max_length=30,
        choices=OrderStatusChoices.choices,
        default=OrderStatusChoices.PENDING_CONFIRMATION,
        db_index=True,
    )
    currency = models.CharField(max_length=10, default='INR')
    place_of_supply = models.CharField(max_length=50, blank=True, default='')
    seller_state = models.CharField(max_length=50, blank=True, default='')

    # Shipping & delivery contact details
    shipping_name = models.CharField(max_length=255, blank=True, default='')
    shipping_phone = models.CharField(max_length=30, blank=True, default='')
    shipping_address_line1 = models.CharField(max_length=255, blank=True, default='')
    shipping_address_line2 = models.CharField(max_length=255, blank=True, default='')
    shipping_city = models.CharField(max_length=100, blank=True, default='')
    shipping_state = models.CharField(max_length=100, blank=True, default='')
    shipping_postal_code = models.CharField(max_length=20, blank=True, default='')
    shipping_country = models.CharField(max_length=100, blank=True, default='India')

    # Financial snapshots
    subtotal_taxable_amount = models.DecimalField(max_digits=12, decimal_places=2)
    cgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    sgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    igst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_tax_amount = models.DecimalField(max_digits=12, decimal_places=2)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = 'Order'
        verbose_name_plural = 'Orders'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.order_number} ({self.buyer.email}) - {self.currency} {self.total_amount}"


class OrderItem(BaseUUIDModel):
    """Line item in an order recording line-level tax snapshot at purchase time."""

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items',
    )
    listing = models.ForeignKey(
        SparePartListing,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='order_items',
    )
    item_type = models.CharField(max_length=20, default='PART')
    title = models.CharField(max_length=255)
    brand = models.CharField(max_length=100, blank=True, default='')
    mpn = models.CharField(max_length=100, blank=True, default='')
    hsn_code = models.CharField(max_length=20, blank=True, default='')
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    is_tax_verified = models.BooleanField(default=True)

    # Line item financial snapshot
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)  # Price before GST
    quantity = models.PositiveIntegerField(default=1)
    taxable_amount = models.DecimalField(max_digits=12, decimal_places=2)  # unit_price * quantity
    cgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    sgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    igst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = 'Order Item'
        verbose_name_plural = 'Order Items'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.title} x {self.quantity} (Order {self.order.order_number})"


class VehicleEnquiryStatusChoices(models.TextChoices):
    NEW = 'NEW', 'New'
    RESPONDED = 'RESPONDED', 'Responded'
    CLOSED = 'CLOSED', 'Closed'


class VehicleEnquiry(BaseUUIDModel):
    """
    Direct buyer enquiry for a specific vehicle listing.
    Connects authenticated buyers directly with vehicle sellers.
    Tracks listing reference, buyer, seller, organisation, prefilled/edited message,
    and enquiry lifecycle status.
    """
    listing = models.ForeignKey(
        VehicleListing,
        on_delete=models.CASCADE,
        related_name='enquiries',
    )
    buyer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='sent_vehicle_enquiries',
    )
    seller = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='received_vehicle_enquiries',
    )
    organisation = models.ForeignKey(
        Organisation,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='vehicle_enquiries',
    )
    message = models.TextField()
    buyer_phone = models.CharField(max_length=30, blank=True, default='')
    status = models.CharField(
        max_length=20,
        choices=VehicleEnquiryStatusChoices.choices,
        default=VehicleEnquiryStatusChoices.NEW,
        db_index=True,
    )
    seller_notes = models.TextField(blank=True, default='')
    seller_reply = models.TextField(blank=True, default='')
    replied_at = models.DateTimeField(null=True, blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Vehicle Enquiry'
        verbose_name_plural = 'Vehicle Enquiries'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['seller', 'status']),
            models.Index(fields=['buyer', '-created_at']),
            models.Index(fields=['listing', '-created_at']),
        ]

    def __str__(self):
        return f"Enquiry on {self.listing.title} by {self.buyer.email} ({self.status})"
