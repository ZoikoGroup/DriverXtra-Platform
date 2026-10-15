from django.contrib import admin
from apps.onboarding.models import SellerApplication


@admin.register(SellerApplication)
class SellerApplicationAdmin(admin.ModelAdmin):
    list_display = ('business_name', 'user', 'business_type', 'status', 'submitted_at', 'reviewed_by')
    list_filter = ('status', 'business_type', 'submitted_at')
    search_fields = ('business_name', 'user__email', 'contact_email', 'company_registration_number')
    readonly_fields = ('created_at', 'updated_at', 'submitted_at', 'reviewed_at')
