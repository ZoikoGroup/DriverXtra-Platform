from rest_framework.throttling import SimpleRateThrottle
from apps.identity.models import User, RoleChoices


class AuthRateThrottle(SimpleRateThrottle):
    """Scoped rate throttle applying stricter limits for staff and administrator logins."""
    scope = 'login'

    def get_cache_key(self, request, view):
        email = request.data.get('email', '').strip().lower()
        if email:
            user = User.objects.filter(email=email).first()
            if user and (user.is_staff or user.has_role(RoleChoices.ADMIN) or user.has_role(RoleChoices.STAFF)):
                self.scope = 'staff_login'
            else:
                self.scope = 'login'
        else:
            self.scope = 'login'

        ident = self.get_ident(request)
        return self.cache_format % {
            'scope': self.scope,
            'ident': f"{ident}:{email}" if email else ident,
        }


class PasswordResetRateThrottle(SimpleRateThrottle):
    """Scoped rate throttle applying stricter limits for staff and administrator password resets."""
    scope = 'password_reset'

    def get_cache_key(self, request, view):
        email = request.data.get('email', '').strip().lower()
        if email:
            user = User.objects.filter(email=email).first()
            if user and (user.is_staff or user.has_role(RoleChoices.ADMIN) or user.has_role(RoleChoices.STAFF)):
                self.scope = 'staff_password_reset'
            else:
                self.scope = 'password_reset'
        else:
            self.scope = 'password_reset'

        ident = self.get_ident(request)
        return self.cache_format % {
            'scope': self.scope,
            'ident': f"{ident}:{email}" if email else ident,
        }
