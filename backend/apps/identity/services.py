import hashlib
import secrets
from datetime import timedelta
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from .models import User, EmailVerificationToken, PasswordResetToken


def hash_token(raw_token: str) -> str:
    """Computes SHA-256 hex digest of a raw token."""
    return hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()


def send_verification_email(user: User, raw_token: str) -> None:
    """Dispatches verification email with raw token link."""
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000").rstrip("/")
    verification_link = f"{frontend_url}/verify-email?token={raw_token}&email={user.email}"
    subject = "Verify your DriverXtra email address"
    message = (
        f"Hello {user.first_name or 'DriverXtra User'},\n\n"
        "Thank you for registering on DriverXtra.\n\n"
        "Please verify your email address by clicking the link below or entering your token:\n"
        f"{verification_link}\n\n"
        f"Verification Token: {raw_token}\n\n"
        "This token will expire in 24 hours.\n\n"
        "— The DriverXtra Team"
    )
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@driverxtra.com")
    send_mail(subject, message, from_email, [user.email], fail_silently=False)


def create_and_send_email_verification(user: User) -> str:
    """Generates an email verification token, stores its SHA-256 hash, and emails the raw token."""
    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_token(raw_token)
    expires_at = timezone.now() + timedelta(hours=24)

    # Invalidate previous unconsumed verification tokens for this user
    EmailVerificationToken.objects.filter(user=user, consumed_at__isnull=True).update(
        consumed_at=timezone.now()
    )

    EmailVerificationToken.objects.create(
        user=user,
        token_hash=token_hash,
        expires_at=expires_at,
    )

    send_verification_email(user, raw_token)
    return raw_token


def send_password_reset_email(user: User, raw_token: str) -> None:
    """Dispatches password reset email with raw token link."""
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000").rstrip("/")
    reset_link = f"{frontend_url}/reset-password?token={raw_token}"
    subject = "Reset your DriverXtra password"
    message = (
        f"Hello {user.first_name or 'DriverXtra User'},\n\n"
        "We received a request to reset your password on DriverXtra.\n\n"
        "Please reset your password by clicking the link below or submitting your token:\n"
        f"{reset_link}\n\n"
        f"Reset Token: {raw_token}\n\n"
        "This password reset token is single-use and will expire in 1 hour.\n\n"
        "If you did not make this request, you can safely ignore this email.\n\n"
        "— The DriverXtra Team"
    )
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@driverxtra.com")
    send_mail(subject, message, from_email, [user.email], fail_silently=False)


def create_and_send_password_reset(user: User) -> str:
    """Generates a password reset token, stores its SHA-256 hash, and emails the raw token."""
    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_token(raw_token)
    expires_at = timezone.now() + timedelta(hours=1)

    # Invalidate previous unconsumed password reset tokens for this user
    PasswordResetToken.objects.filter(user=user, consumed_at__isnull=True).update(
        consumed_at=timezone.now()
    )

    PasswordResetToken.objects.create(
        user=user,
        token_hash=token_hash,
        expires_at=expires_at,
    )

    send_password_reset_email(user, raw_token)
    return raw_token
