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
    WorkOrder,
    WorkOrderTask,
    WorkOrderPartUsage,
    ChangeOrder,
    ChangeOrderLineItem,
    WorkshopReview,
    WorkshopDepositWebhookEvent,
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
        'can_collect_tax',
        'default_tax_rate_percent',
        'is_accepting_bookings',
        'is_verified',
    )
    list_filter = ('is_accepting_bookings', 'is_verified', 'is_tax_registered', 'can_collect_tax', 'city')
    search_fields = ('business_name', 'slug', 'contact_email', 'organisation__name')
    inlines = [WorkshopOperatingHoursInline, WorkshopServiceInline]
    actions = ['authorize_tax_collection', 'revoke_tax_collection']

    @admin.action(description="Authorize tax collection for selected registered workshops")
    def authorize_tax_collection(self, request, queryset):
        from apps.workshops.services import WorkshopTaxAuthorizationService
        authorized_count = 0
        skipped_count = 0
        for workshop in queryset:
            if not workshop.is_tax_registered:
                skipped_count += 1
                continue
            WorkshopTaxAuthorizationService.set_tax_collection_authorization(
                workshop=workshop,
                authorized=True,
                actor=request.user,
                reason="Django admin bulk action: authorize_tax_collection",
            )
            authorized_count += 1
        if authorized_count:
            self.message_user(request, f"Successfully authorized tax collection for {authorized_count} workshop(s).")
        if skipped_count:
            self.message_user(request, f"Skipped {skipped_count} workshop(s) because they are not tax registered.", level='warning')

    @admin.action(description="Revoke tax collection authorization for selected workshops")
    def revoke_tax_collection(self, request, queryset):
        from apps.workshops.services import WorkshopTaxAuthorizationService
        revoked_count = 0
        for workshop in queryset:
            WorkshopTaxAuthorizationService.set_tax_collection_authorization(
                workshop=workshop,
                authorized=False,
                actor=request.user,
                reason="Django admin bulk action: revoke_tax_collection",
            )
            revoked_count += 1
        self.message_user(request, f"Successfully revoked tax collection authorization for {revoked_count} workshop(s).")

    def save_model(self, request, obj, form, change):
        if change and 'can_collect_tax' in form.changed_data:
            from apps.workshops.services import WorkshopTaxAuthorizationService
            WorkshopTaxAuthorizationService.set_tax_collection_authorization(
                workshop=obj,
                authorized=form.cleaned_data['can_collect_tax'],
                actor=request.user,
                reason="Django admin form save",
            )
        super().save_model(request, obj, form, change)


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




class WorkOrderTaskInline(admin.TabularInline):
    model = WorkOrderTask
    extra = 0


class WorkOrderPartUsageInline(admin.TabularInline):
    model = WorkOrderPartUsage
    extra = 0


@admin.register(WorkOrder)
class WorkOrderAdmin(admin.ModelAdmin):
    list_display = (
        'work_order_number',
        'booking',
        'workshop',
        'buyer',
        'vehicle_registration_plate',
        'lead_technician',
        'status',
        'started_at',
        'completed_at',
        'created_at',
    )
    list_filter = ('status', 'workshop')
    search_fields = (
        'work_order_number',
        'booking__booking_number',
        'vehicle_registration_plate',
        'vehicle_vin',
        'buyer__email',
        'lead_technician__email',
    )
    readonly_fields = ('work_order_number', 'created_at', 'updated_at')
    inlines = [WorkOrderTaskInline, WorkOrderPartUsageInline]


@admin.register(WorkOrderTask)
class WorkOrderTaskAdmin(admin.ModelAdmin):
    list_display = (
        'work_order',
        'description',
        'assigned_technician',
        'estimated_labour_minutes',
        'actual_labour_minutes',
        'status',
        'completed_at',
    )
    list_filter = ('status',)
    search_fields = ('description', 'work_order__work_order_number')


@admin.register(WorkOrderPartUsage)
class WorkOrderPartUsageAdmin(admin.ModelAdmin):
    list_display = (
        'work_order',
        'part_name',
        'part_number',
        'quantity',
        'unit_cost',
        'total_cost',
        'usage_date',
        'added_by',
    )
    search_fields = ('part_name', 'part_number', 'work_order__work_order_number')

class ChangeOrderLineItemInline(admin.TabularInline):
    model = ChangeOrderLineItem
    extra = 0


@admin.register(ChangeOrder)
class ChangeOrderAdmin(admin.ModelAdmin):
    list_display = (
        'change_order_number',
        'work_order',
        'version',
        'status',
        'additional_amount',
        'revised_authorized_total',
        'currency',
        'submitted_at',
        'reviewed_by',
        'reviewed_at',
    )
    list_filter = ('status', 'currency')
    search_fields = (
        'change_order_number',
        'work_order__work_order_number',
        'reason',
        'reviewed_by__email',
    )
    readonly_fields = ('change_order_number', 'version', 'created_at', 'updated_at')
    inlines = [ChangeOrderLineItemInline]


@admin.register(ChangeOrderLineItem)
class ChangeOrderLineItemAdmin(admin.ModelAdmin):
    list_display = (
        'change_order',
        'item_type',
        'description',
        'part_number',
        'quantity',
        'unit_price',
        'line_total',
    )
    list_filter = ('item_type',)
    search_fields = ('description', 'part_number', 'change_order__change_order_number')


@admin.register(WorkshopReview)
class WorkshopReviewAdmin(admin.ModelAdmin):
    list_display = (
        'workshop',
        'buyer',
        'rating',
        'status',
        'is_verified_service',
        'title',
        'created_at',
    )
    list_filter = ('status', 'rating', 'is_verified_service')
    search_fields = (
        'workshop__business_name',
        'buyer__email',
        'title',
        'comment',
        'booking__booking_number',
    )
    readonly_fields = ('created_at', 'updated_at')


@admin.register(WorkshopDepositWebhookEvent)
class WorkshopDepositWebhookEventAdmin(admin.ModelAdmin):
    list_display = (
        'event_id',
        'provider',
        'event_type',
        'quotation',
        'processed',
        'created_at',
    )
    list_filter = ('provider', 'processed', 'event_type')
    search_fields = (
        'event_id',
        'quotation__quotation_number',
        'quotation__booking__booking_number',
    )
    readonly_fields = ('created_at', 'updated_at')



