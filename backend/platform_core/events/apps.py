from django.apps import AppConfig


class EventsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "platform_core.events"
    label = "platform_events"
    verbose_name = "Platform Event Outbox"
