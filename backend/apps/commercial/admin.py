from django.contrib import admin

from .models import CommercialSku, CountryGate, CountryGateTransition, PartyRoleProfile, QuoteSnapshot, RateSchedule


class ReadOnlyAdmin(admin.ModelAdmin):
    """Commercial records are changed only through the API services so every rule and audit entry applies."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CommercialSku)
class CommercialSkuAdmin(ReadOnlyAdmin):
    list_display = ('sku_code', 'version', 'name', 'revenue_code', 'vertical', 'status', 'is_regulated')
    list_filter = ('status', 'vertical', 'family', 'is_regulated')
    search_fields = ('sku_code', 'name')


@admin.register(CountryGate)
class CountryGateAdmin(ReadOnlyAdmin):
    list_display = ('country_code', 'vertical', 'capability', 'status', 'version')
    list_filter = ('status', 'vertical', 'capability')


@admin.register(CountryGateTransition)
class CountryGateTransitionAdmin(ReadOnlyAdmin):
    list_display = ('gate', 'from_status', 'to_status', 'version_after', 'actor', 'created_at')


@admin.register(PartyRoleProfile)
class PartyRoleProfileAdmin(ReadOnlyAdmin):
    list_display = ('code', 'version', 'profile_type', 'country_code', 'vertical', 'status')
    list_filter = ('status', 'profile_type', 'vertical')


@admin.register(RateSchedule)
class RateScheduleAdmin(ReadOnlyAdmin):
    list_display = ('name', 'sku', 'country_code', 'currency', 'payer_role', 'priority', 'status', 'effective_from')
    list_filter = ('status', 'country_code', 'currency')


@admin.register(QuoteSnapshot)
class QuoteSnapshotAdmin(ReadOnlyAdmin):
    list_display = ('quote_number', 'customer', 'country_code', 'currency', 'customer_total_minor', 'status')
    list_filter = ('status', 'country_code')
    search_fields = ('quote_number', 'terms_hash')
