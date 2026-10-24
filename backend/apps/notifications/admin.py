from django.contrib import admin
from apps.notifications.models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'event_type', 'title', 'is_read', 'email_status', 'email_attempts', 'created_at')
    list_filter = ('event_type', 'is_read', 'email_status')
    search_fields = ('recipient__email', 'title', 'resource_id')
    readonly_fields = ('source_audit_id', 'created_at', 'updated_at', 'emailed_at', 'email_error', 'email_attempts')
