from django.apps import AppConfig
from django.db.backends.signals import connection_created


def _attach_platform_for_sqlite(sender, connection, **kwargs):
    if connection.vendor == "sqlite":
        with connection.cursor() as cursor:
            try:
                cursor.execute("ATTACH DATABASE ':memory:' AS platform;")
            except Exception:
                pass


class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "platform_core.audit"
    label = "platform_audit"
    verbose_name = "Platform Audit"

    def ready(self):
        connection_created.connect(_attach_platform_for_sqlite)