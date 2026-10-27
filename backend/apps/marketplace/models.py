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
    country_prices = models.JSONField(
        default=dict,
        blank=True,
        help_text="Optional country/currency-specific pricing overrides, e.g. {'INR': '4000.00', 'GBP': '38.00'}.",
    )
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


class PaymentMethodChoices(models.TextChoices):
    ONLINE = 'ONLINE', 'Online Payment'
    COD = 'COD', 'Cash on Delivery'


class PaymentStatusChoices(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    AUTHORIZED = 'AUTHORIZED', 'Authorized'
    PAID = 'PAID', 'Paid'
    FAILED = 'FAILED', 'Failed'
    CANCELLED = 'CANCELLED', 'Cancelled'
    EXPIRED = 'EXPIRED', 'Expired'
    REFUNDED = 'REFUNDED', 'Refunded'


class CODCollectionStatusChoices(models.TextChoices):
    NOT_APPLICABLE = 'NOT_APPLICABLE', 'Not Applicable'
    PENDING = 'PENDING', 'Pending Collection'
    AWAITING_COLLECTION = 'AWAITING_COLLECTION', 'Awaiting Collection'
    COLLECTED = 'COLLECTED', 'Collected'
    FAILED_COLLECTION = 'FAILED_COLLECTION', 'Failed Collection'
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
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethodChoices.choices,
        default=PaymentMethodChoices.ONLINE,
        db_index=True,
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatusChoices.choices,
        default=PaymentStatusChoices.PENDING,
        db_index=True,
    )
    payment_reference = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="Primary external payment identifier from provider (e.g. pay_xxx, pi_xxx).",
    )
    paid_at = models.DateTimeField(null=True, blank=True)

    # Cash on Delivery collection tracking
    cod_collection_status = models.CharField(
        max_length=30,
        choices=CODCollectionStatusChoices.choices,
        default=CODCollectionStatusChoices.NOT_APPLICABLE,
        db_index=True,
    )
    cod_collected_at = models.DateTimeField(null=True, blank=True)
    cod_collected_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='collected_cod_orders',
        help_text="Authorized staff member or courier agent who recorded the COD collection.",
    )
    cod_collection_notes = models.TextField(blank=True, default='')

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


class PaymentTransaction(BaseUUIDModel):
    """
    Immutable ledger record of payment attempts, authorizations, captures, and COD collections.
    """
    class TransactionTypeChoices(models.TextChoices):
        PAYMENT = 'PAYMENT', 'Payment'
        REFUND = 'REFUND', 'Refund'
        COD_COLLECTION = 'COD_COLLECTION', 'COD Collection'

    class StatusChoices(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        SUCCESS = 'SUCCESS', 'Success'
        FAILED = 'FAILED', 'Failed'
        CANCELLED = 'CANCELLED', 'Cancelled'
        EXPIRED = 'EXPIRED', 'Expired'

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='payment_transactions',
    )
    transaction_type = models.CharField(
        max_length=20,
        choices=TransactionTypeChoices.choices,
        default=TransactionTypeChoices.PAYMENT,
    )
    provider = models.CharField(
        max_length=30,
        help_text="Payment provider (e.g. RAZORPAY, STRIPE, COD)",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10)
    status = models.CharField(
        max_length=20,
        choices=StatusChoices.choices,
        default=StatusChoices.PENDING,
        db_index=True,
    )
    provider_transaction_id = models.CharField(
        max_length=255,
        blank=True,
        default='',
        db_index=True,
        help_text="Provider's payment transaction ID (e.g. pay_xxx, pi_xxx)",
    )
    provider_order_id = models.CharField(
        max_length=255,
        blank=True,
        default='',
        db_index=True,
        help_text="Provider's session or order ID (e.g. order_xxx, cs_xxx)",
    )
    provider_signature = models.CharField(max_length=255, blank=True, default='')
    idempotency_key = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    error_code = models.CharField(max_length=100, blank=True, default='')
    error_message = models.TextField(blank=True, default='')
    raw_response = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = 'Payment Transaction'
        verbose_name_plural = 'Payment Transactions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order', '-created_at']),
            models.Index(fields=['provider', 'status']),
            models.Index(fields=['provider_transaction_id']),
            models.Index(fields=['provider_order_id']),
        ]

    def __str__(self):
        return f"{self.provider} {self.transaction_type} ({self.currency} {self.amount}) - {self.status} (Order {self.order.order_number})"


class PaymentWebhookEvent(BaseUUIDModel):
    """
    Audit log of verified provider webhook events ensuring idempotent processing and replay defense.
    """
    provider = models.CharField(max_length=50, db_index=True)
    event_id = models.CharField(max_length=255, unique=True, db_index=True)
    event_type = models.CharField(max_length=100, db_index=True)
    processed = models.BooleanField(default=False, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    order = models.ForeignKey(
        Order,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='webhook_events',
    )
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = 'Payment Webhook Event'
        verbose_name_plural = 'Payment Webhook Events'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.provider}:{self.event_type} ({self.event_id}) - Processed={self.processed}"


# =============================================================================
# Phase 5 Task 2: Shipping, Logistics and Order Tracking Models
# =============================================================================

class CarrierChoices(models.TextChoices):
    # India Domestic Carriers
    BLUE_DART = 'BLUE_DART', 'Blue Dart'
    DELHIVERY = 'DELHIVERY', 'Delhivery'
    DTDC = 'DTDC', 'DTDC Express'
    ECOM_EXPRESS = 'ECOM_EXPRESS', 'Ecom Express'
    INDIA_POST = 'INDIA_POST', 'India Post'
    # UK Domestic Carriers
    ROYAL_MAIL = 'ROYAL_MAIL', 'Royal Mail'
    DPD_UK = 'DPD_UK', 'DPD UK'
    EVRI = 'EVRI', 'Evri'
    YODEL = 'YODEL', 'Yodel'
    PARCELFORCE = 'PARCELFORCE', 'Parcelforce Worldwide'
    # Global / Cross-Border Carriers
    DHL = 'DHL', 'DHL Express'
    FEDEX = 'FEDEX', 'FedEx'
    UPS = 'UPS', 'UPS'
    # Custom / Local Couriers
    OTHER = 'OTHER', 'Other / Local Courier'


class ShipmentStatusChoices(models.TextChoices):
    CREATED = 'CREATED', 'Created'
    DISPATCHED = 'DISPATCHED', 'Dispatched'
    IN_TRANSIT = 'IN_TRANSIT', 'In Transit'
    OUT_FOR_DELIVERY = 'OUT_FOR_DELIVERY', 'Out for Delivery'
    DELIVERED = 'DELIVERED', 'Delivered'
    FAILED_DELIVERY = 'FAILED_DELIVERY', 'Failed Delivery'
    RETURNED = 'RETURNED', 'Returned'
    CANCELLED = 'CANCELLED', 'Cancelled'


class Shipment(BaseUUIDModel):
    """
    Logistics fulfillment package for items in an order by a specific seller.
    Preserves multi-seller isolation, partial fulfillment, and carrier dispatch history.
    """
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='shipments',
        help_text="Parent order being fulfilled.",
    )
    seller = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='seller_shipments',
        help_text="Seller fulfilling this shipment package.",
    )
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='organisation_shipments',
        help_text="Seller dealership organisation if applicable.",
    )
    shipment_number = models.CharField(
        max_length=60,
        unique=True,
        db_index=True,
        help_text="System-generated unique shipment package reference.",
    )
    carrier = models.CharField(
        max_length=50,
        choices=CarrierChoices.choices,
        default=CarrierChoices.OTHER,
        db_index=True,
    )
    carrier_name = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text="Carrier display name or custom courier name if carrier is OTHER.",
    )
    tracking_number = models.CharField(
        max_length=100,
        blank=True,
        default='',
        db_index=True,
        help_text="Carrier tracking reference / AWB / consignment number.",
    )
    tracking_url = models.URLField(
        max_length=500,
        blank=True,
        default='',
        help_text="Direct public tracking URL provided by carrier or generated by system.",
    )
    status = models.CharField(
        max_length=30,
        choices=ShipmentStatusChoices.choices,
        default=ShipmentStatusChoices.CREATED,
        db_index=True,
    )
    dispatched_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    estimated_delivery_at = models.DateTimeField(null=True, blank=True)
    delivery_notes = models.TextField(
        blank=True,
        default='',
        help_text="Handling instructions or seller dispatch notes.",
    )
    shipping_label_url = models.CharField(max_length=500, blank=True, default='')

    class Meta:
        verbose_name = 'Shipment'
        verbose_name_plural = 'Shipments'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order', 'seller']),
            models.Index(fields=['tracking_number']),
            models.Index(fields=['status', '-created_at']),
        ]

    def __str__(self):
        return f"{self.shipment_number} ({self.carrier}: {self.tracking_number or 'No Tracking'}) - {self.status}"


class ShipmentItem(BaseUUIDModel):
    """
    Associates specific order items and quantities to a shipment package.
    """
    shipment = models.ForeignKey(
        Shipment,
        on_delete=models.CASCADE,
        related_name='items',
    )
    order_item = models.ForeignKey(
        OrderItem,
        on_delete=models.CASCADE,
        related_name='shipment_items',
    )
    quantity = models.PositiveIntegerField(
        default=1,
        help_text="Number of units of the order item allocated to this package.",
    )

    class Meta:
        verbose_name = 'Shipment Item'
        verbose_name_plural = 'Shipment Items'
        ordering = ['created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['shipment', 'order_item'],
                name='unique_shipment_order_item',
            )
        ]

    def __str__(self):
        return f"{self.order_item.title} x {self.quantity} (Shipment {self.shipment.shipment_number})"


class TrackingEvent(BaseUUIDModel):
    """
    Chronological tracking history event for a shipment.
    Records status checkpoints, locations, and timestamps.
    """
    shipment = models.ForeignKey(
        Shipment,
        on_delete=models.CASCADE,
        related_name='tracking_events',
    )
    status = models.CharField(
        max_length=30,
        choices=ShipmentStatusChoices.choices,
        db_index=True,
    )
    location = models.CharField(max_length=255, blank=True, default='')
    description = models.TextField()
    event_timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    external_checkpoint_id = models.CharField(
        max_length=150,
        blank=True,
        default='',
        db_index=True,
        help_text="Unique checkpoint identifier from carrier webhook/polling to prevent duplicates.",
    )

    class Meta:
        verbose_name = 'Tracking Event'
        verbose_name_plural = 'Tracking Events'
        ordering = ['event_timestamp', 'created_at']
        indexes = [
            models.Index(fields=['shipment', '-event_timestamp']),
            models.Index(fields=['shipment', 'external_checkpoint_id']),
        ]

    def __str__(self):
        return f"{self.shipment.shipment_number} @ {self.event_timestamp}: {self.status} - {self.description[:40]}"


# =============================================================================
# Phase 5 Task 3: Returns, Refunds and Dispute Management Models
# =============================================================================

class ReturnRequestTypeChoices(models.TextChoices):
    CANCELLATION = 'CANCELLATION', 'Order Cancellation'
    RETURN = 'RETURN', 'Item Return'


class ReturnRequestStatusChoices(models.TextChoices):
    PENDING = 'PENDING', 'Pending Review'
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected'
    COMPLETED = 'COMPLETED', 'Completed'
    CANCELLED = 'CANCELLED', 'Cancelled by Buyer'


class ReturnReasonChoices(models.TextChoices):
    DEFECTIVE_ITEM = 'DEFECTIVE_ITEM', 'Defective or Damaged Item'
    INCORRECT_ITEM = 'INCORRECT_ITEM', 'Incorrect Item Delivered'
    NOT_AS_DESCRIBED = 'NOT_AS_DESCRIBED', 'Item Not as Described'
    ORDERED_BY_MISTAKE = 'ORDERED_BY_MISTAKE', 'Ordered by Mistake'
    DELIVERY_DELAY = 'DELIVERY_DELAY', 'Severe Delivery Delay'
    BUYER_CANCEL = 'BUYER_CANCEL', 'Buyer Changed Mind'
    OTHER = 'OTHER', 'Other Reason'


class ReturnRequest(BaseUUIDModel):
    """
    Formal buyer request for order cancellation or physical item return.
    Connects buyer, seller, order, optional order item, reason, evidence, and review workflow.
    """
    request_number = models.CharField(
        max_length=60,
        unique=True,
        db_index=True,
        help_text="System-generated unique reference (e.g. RET-YYYYMMDD-XXXXXXXX).",
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='return_requests',
        help_text="Parent order for this cancellation or return request.",
    )
    order_item = models.ForeignKey(
        OrderItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='return_requests',
        help_text="Specific line item being returned. Null if whole order cancellation.",
    )
    buyer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='buyer_return_requests',
    )
    seller = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='seller_return_requests',
        help_text="Seller responsible for fulfilling this order or item.",
    )
    request_type = models.CharField(
        max_length=20,
        choices=ReturnRequestTypeChoices.choices,
        default=ReturnRequestTypeChoices.RETURN,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=ReturnRequestStatusChoices.choices,
        default=ReturnRequestStatusChoices.PENDING,
        db_index=True,
    )
    reason = models.CharField(
        max_length=40,
        choices=ReturnReasonChoices.choices,
        default=ReturnReasonChoices.OTHER,
        db_index=True,
    )
    description = models.TextField(blank=True, default='')
    evidence_urls = models.JSONField(
        default=list,
        blank=True,
        help_text="List of supporting photo/document URLs uploaded via upload-image.",
    )
    requested_quantity = models.PositiveIntegerField(
        default=1,
        help_text="Number of units requested for return/cancellation.",
    )
    refund_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Calculated or requested refund value.",
    )
    seller_notes = models.TextField(blank=True, default='')
    rejection_reason = models.TextField(blank=True, default='')
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_return_requests',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Return Request'
        verbose_name_plural = 'Return Requests'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order', 'status']),
            models.Index(fields=['buyer', '-created_at']),
            models.Index(fields=['seller', 'status']),
            models.Index(fields=['request_type', 'status']),
        ]

    def __str__(self):
        return f"{self.request_number} ({self.request_type}) - {self.status} (Order {self.order.order_number})"


class RefundStatusChoices(models.TextChoices):
    PENDING = 'PENDING', 'Pending Approval'
    PROCESSING = 'PROCESSING', 'Processing Gateway / Payout'
    SUCCEEDED = 'SUCCEEDED', 'Succeeded'
    FAILED = 'FAILED', 'Failed'
    CANCELLED = 'CANCELLED', 'Cancelled'


class RefundMethodChoices(models.TextChoices):
    ORIGINAL_PAYMENT = 'ORIGINAL_PAYMENT', 'Original Payment Gateway'
    BANK_TRANSFER = 'BANK_TRANSFER', 'Direct Bank Transfer / NEFT'
    MANUAL_PAYOUT = 'MANUAL_PAYOUT', 'Manual Ops Payout / Cash Voucher'


class Refund(BaseUUIDModel):
    """
    Authoritative record of a customer refund.
    Tied to an order, an optional return request or dispute, and the underlying payment transaction.
    """
    refund_number = models.CharField(
        max_length=60,
        unique=True,
        db_index=True,
        help_text="System-generated unique refund reference (e.g. REF-YYYYMMDD-XXXXXXXX).",
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='refunds',
    )
    return_request = models.ForeignKey(
        ReturnRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='refunds',
    )
    dispute = models.ForeignKey(
        'Dispute',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='refunds',
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default='INR')
    status = models.CharField(
        max_length=20,
        choices=RefundStatusChoices.choices,
        default=RefundStatusChoices.PENDING,
        db_index=True,
    )
    refund_method = models.CharField(
        max_length=30,
        choices=RefundMethodChoices.choices,
        default=RefundMethodChoices.ORIGINAL_PAYMENT,
    )
    gateway_provider = models.CharField(max_length=30, blank=True, default='')
    gateway_refund_id = models.CharField(max_length=255, blank=True, default='', db_index=True)
    reason = models.CharField(max_length=255, blank=True, default='')
    failure_reason = models.TextField(blank=True, default='')
    notes = models.TextField(blank=True, default='')
    processed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_refunds',
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_refunds',
    )

    class Meta:
        verbose_name = 'Refund'
        verbose_name_plural = 'Refunds'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order', 'status']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['gateway_refund_id']),
        ]

    def __str__(self):
        return f"{self.refund_number}: {self.currency} {self.amount} ({self.status}) - Order {self.order.order_number}"


class DisputeCategoryChoices(models.TextChoices):
    ITEM_NOT_RECEIVED = 'ITEM_NOT_RECEIVED', 'Item Not Received'
    SIGNIFICANTLY_NOT_AS_DESCRIBED = 'SIGNIFICANTLY_NOT_AS_DESCRIBED', 'Significantly Not as Described'
    DAMAGED_OR_DEFECTIVE = 'DAMAGED_OR_DEFECTIVE', 'Damaged or Defective Item'
    UNAUTHORIZED_TRANSACTION = 'UNAUTHORIZED_TRANSACTION', 'Unauthorized Transaction / Fraud'
    REFUND_NOT_PROCESSED = 'REFUND_NOT_PROCESSED', 'Refund Not Processed'
    OTHER = 'OTHER', 'Other Commercial Dispute'


class DisputeStatusChoices(models.TextChoices):
    OPEN = 'OPEN', 'Open'
    UNDER_REVIEW = 'UNDER_REVIEW', 'Under Review'
    RESOLVED = 'RESOLVED', 'Resolved'
    REJECTED = 'REJECTED', 'Rejected'
    ESCALATED = 'ESCALATED', 'Escalated to Senior Ops'


class DisputeResolutionChoices(models.TextChoices):
    REFUND_ISSUED = 'REFUND_ISSUED', 'Full / Partial Refund Issued'
    REPLACEMENT_ISSUED = 'REPLACEMENT_ISSUED', 'Replacement Part Issued'
    BUYER_REJECTED = 'BUYER_REJECTED', 'Claim Rejected in Favor of Seller'
    MUTUAL_AGREEMENT = 'MUTUAL_AGREEMENT', 'Settled via Mutual Agreement'
    DISMISSED = 'DISMISSED', 'Dismissed / Inactive'


class DisputePriorityChoices(models.TextChoices):
    LOW = 'LOW', 'Low'
    MEDIUM = 'MEDIUM', 'Medium'
    HIGH = 'HIGH', 'High'
    CRITICAL = 'CRITICAL', 'Critical'


class Dispute(BaseUUIDModel):
    """
    Marketplace dispute mediation record connecting buyer, seller, and platform operations staff.
    """
    dispute_number = models.CharField(
        max_length=60,
        unique=True,
        db_index=True,
        help_text="System-generated unique dispute reference (e.g. DISP-YYYYMMDD-XXXXXXXX).",
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='disputes',
    )
    buyer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='buyer_disputes',
    )
    seller = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='seller_disputes',
    )
    category = models.CharField(
        max_length=40,
        choices=DisputeCategoryChoices.choices,
        default=DisputeCategoryChoices.OTHER,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=DisputeStatusChoices.choices,
        default=DisputeStatusChoices.OPEN,
        db_index=True,
    )
    priority = models.CharField(
        max_length=20,
        choices=DisputePriorityChoices.choices,
        default=DisputePriorityChoices.MEDIUM,
    )
    description = models.TextField()
    evidence_urls = models.JSONField(default=list, blank=True)
    resolution = models.CharField(
        max_length=30,
        choices=DisputeResolutionChoices.choices,
        blank=True,
        default='',
    )
    resolution_notes = models.TextField(blank=True, default='')
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_disputes',
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Dispute'
        verbose_name_plural = 'Disputes'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order', 'status']),
            models.Index(fields=['buyer', 'status']),
            models.Index(fields=['seller', 'status']),
            models.Index(fields=['status', 'priority']),
        ]

    def __str__(self):
        return f"{self.dispute_number}: {self.category} ({self.status}) - Order {self.order.order_number}"


class DisputeEventTypeChoices(models.TextChoices):
    STATUS_CHANGE = 'STATUS_CHANGE', 'Status Changed'
    COMMENT = 'COMMENT', 'User Comment'
    EVIDENCE_ADDED = 'EVIDENCE_ADDED', 'Evidence Added'
    DECISION_RECORDED = 'DECISION_RECORDED', 'Decision Recorded'


class DisputeEvent(BaseUUIDModel):
    """
    Chronological activity log and mediation messages for a dispute.
    """
    dispute = models.ForeignKey(
        Dispute,
        on_delete=models.CASCADE,
        related_name='events',
    )
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dispute_events',
    )
    event_type = models.CharField(
        max_length=30,
        choices=DisputeEventTypeChoices.choices,
        default=DisputeEventTypeChoices.COMMENT,
    )
    message = models.TextField()
    attachments = models.JSONField(default=list, blank=True)

    class Meta:
        verbose_name = 'Dispute Event'
        verbose_name_plural = 'Dispute Events'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['dispute', 'created_at']),
        ]

    def __str__(self):
        actor_name = self.actor.email if self.actor else 'System'
        return f"{self.dispute.dispute_number} @ {self.created_at}: {actor_name} - {self.event_type}"



