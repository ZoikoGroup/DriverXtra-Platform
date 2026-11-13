from django.apps import AppConfig

class IdentityConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.identity'
    verbose_name = 'Identity & RBAC'

    def ready(self):
        # Revoke outstanding refresh tokens when an account is suspended/deactivated.
        from apps.identity import signals  # noqa: F401
