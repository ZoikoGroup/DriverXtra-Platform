from django.contrib import admin
from apps.workshops.models import (
    WorkshopProfile,
    WorkshopOperatingHours,
    WorkshopServiceCategory,
    WorkshopService,
    WorkshopBooking,
    BookingServiceItem,
    WorkshopQuotation,
    QuotationLineItem,
)


class WorkshopOperatingHoursInline(admin.TabularInline):
    model = WorkshopOperatingHours
    extra = 0


class WorkshopServiceInline(admin.TabularInline):
    model = WorkshopService
    extra = 0


@admin.register(WorkshopProfile)
class WorkshopProfileAdmin(admin.ModelAdmin):
    list_display = (
        'business_name',
        'organisation',
        'city',
        'contact_email',
        'contact_phone',
        'bay_capacity',
        'is_tax_registered',
        'default_tax_rate_percent',
        'is_accepting_bookings',
        'is_verified',
    )
    list_filter = ('is_accepting_bookings', 'is_verified', 'is_tax_registered', 'city')
    search_fields = ('business_name', 'slug', 'contact_email', 'organisation__name')
    inlines = [WorkshopOperatingHoursInline, WorkshopServiceInline]


@admin.register(WorkshopOperatingHours)
class WorkshopOperatingHoursAdmin(admin.ModelAdmin):
    list_display = ('workshop', 'day_of_week', 'is_closed', 'open_time', 'close_time', 'slot_duration_minutes')
    list_filter = ('day_of_week', 'is_closed')
    search_fields = ('workshop__business_name',)


@admin.register(WorkshopServiceCategory)
class WorkshopServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'display_order', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(WorkshopService)
class WorkshopServiceAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'workshop',
        'category',
        'base_price',
        'currency',
        'estimated_duration_minutes',
        'is_price_variable',
        'is_active',
    )
    list_filter = ('is_active', 'is_price_variable', 'category', 'currency')
    search_fields = ('name', 'workshop__business_name', 'description')


class BookingServiceItemInline(admin.TabularInline):
    model = BookingServiceItem
    extra = 0


@admin.register(WorkshopBooking)
class WorkshopBookingAdmin(admin.ModelAdmin):
    list_display = (
        'booking_number',
        'workshop',
        'buyer',
        'vehicle_registration_plate',
        'preferred_date',
        'scheduled_appointment_start',
        'status',
        'created_at',
    )
    list_filter = ('status', 'preferred_date', 'workshop')
    search_fields = (
        'booking_number',
        'buyer__email',
        'vehicle_registration_plate',
        'vehicle_vin',
        'workshop__business_name',
    )
    readonly_fields = ('booking_number', 'created_at', 'updated_at')
    inlines = [BookingServiceItemInline]


@admin.register(BookingServiceItem)
class BookingServiceItemAdmin(admin.ModelAdmin):
    list_display = ('booking', 'service_name', 'service_price', 'currency')
    search_fields = ('service_name', 'booking__booking_number')


class QuotationLineItemInline(admin.TabularInline):
    model = QuotationLineItem
    extra = 0


@admin.register(WorkshopQuotation)
class WorkshopQuotationAdmin(admin.ModelAdmin):
    list_display = (
        'quotation_number',
        'booking',
        'version',
        'status',
        'subtotal_labour',
        'subtotal_parts',
        'tax_amount',
        'total_amount',
        'currency',
        'valid_until',
        'created_at',
    )
    list_filter = ('status', 'version', 'currency')
    search_fields = (
        'quotation_number',
        'booking__booking_number',
        'booking__workshop__business_name',
    )
    readonly_fields = ('quotation_number', 'created_at', 'updated_at')
    inlines = [QuotationLineItemInline]


@admin.register(QuotationLineItem)
class QuotationLineItemAdmin(admin.ModelAdmin):
    list_display = (
        'quotation',
        'item_type',
        'description',
        'part_number',
        'quantity',
        'unit_price',
        'line_total',
    )
    list_filter = ('item_type',)
    search_fields = ('description', 'part_number', 'quotation__quotation_number')

