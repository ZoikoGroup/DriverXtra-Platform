"""Identity signal handlers.

Session revocation on suspension/deactivation (supplementary control).

Primary controls (``apps.identity.authentication``):
- per-request and per-refresh account-status enforcement;
- session-version revocation: the database trigger from migration 0011 increments
  ``User.session_version`` on every usable -> unusable transition, by ANY update path
  (save, QuerySet.update, bulk_update, raw SQL), and tokens carrying an older ``sv`` are
  rejected, including after reactivation.

This handler additionally blacklists all outstanding refresh tokens when an account transitions
from usable to SUSPENDED / DEACTIVATED / ``is_active=False`` through a model save.

Coverage:
- ``user.save()`` and ``user.save(update_fields=[...])`` including ``status`` or ``is_active``
  (Django admin, services, shell) trigger revocation.
- ``save(update_fields=...)`` that does not include ``status``/``is_active`` is skipped without
  a database query (nothing account-status related is persisted by such a save).
- Paths that bypass model signals (``QuerySet.update()``, ``bulk_update()``, raw SQL, direct
  database edits) do not blacklist here, but they are covered by the session-version trigger,
  so tokens issued before the suspension remain invalid after reactivation.
"""
from types import SimpleNamespace

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.identity.authentication import is_account_usable

_STATUS_FIELDS = {'status', 'is_active'}


def _connect():
    from apps.identity.models import User

    # weak=False: these receivers are local functions; with Django's default weak references they
    # would be garbage-collected once _connect() returns (only DEBUG=True kept them alive).
    @receiver(pre_save, sender=User, dispatch_uid='identity_user_detect_account_disable', weak=False)
    def detect_account_disable(sender, instance, raw=False, update_fields=None, **kwargs):
        instance._revoke_sessions_after_save = False
        if raw or instance._state.adding or instance.pk is None:
            return
        if update_fields is not None and not (_STATUS_FIELDS & set(update_fields)):
            return
        previous = sender.objects.filter(pk=instance.pk).values('status', 'is_active').first()
        if previous is None:
            return

        if is_account_usable(SimpleNamespace(**previous)) and not is_account_usable(instance):
            instance._revoke_sessions_after_save = True

    @receiver(post_save, sender=User, dispatch_uid='identity_user_revoke_sessions_on_disable', weak=False)
    def revoke_sessions_on_disable(sender, instance, created=False, raw=False, **kwargs):
        if raw or created or not getattr(instance, '_revoke_sessions_after_save', False):
            return
        instance._revoke_sessions_after_save = False

        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
        from platform_core.audit.writer import record_audit_entry
        from common.middleware import get_current_correlation_id

        revoked = 0
        for outstanding in OutstandingToken.objects.filter(user=instance):
            _, was_created = BlacklistedToken.objects.get_or_create(token=outstanding)
            if was_created:
                revoked += 1

        record_audit_entry(
            event_type="auth.sessions.revoked",
            action="auth:sessions.revoke_on_account_disable",
            resource_type="User",
            resource_id=str(instance.id),
            correlation_id=get_current_correlation_id(),
            metadata={
                "email": instance.email,
                "status": instance.status,
                "is_active": instance.is_active,
                "revoked_refresh_tokens": revoked,
            },
        )


_connect()
