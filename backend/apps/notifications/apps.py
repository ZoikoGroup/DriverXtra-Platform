from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.notifications'
    verbose_name = 'Notifications'

    def ready(self):
        from django.db.models.signals import post_save
        from platform_core.audit.models import AuditLog
        from apps.notifications.handlers import handle_audit_log_saved

        post_save.connect(
            handle_audit_log_saved,
            sender=AuditLog,
            dispatch_uid='notifications.handle_audit_log_saved',
        )
