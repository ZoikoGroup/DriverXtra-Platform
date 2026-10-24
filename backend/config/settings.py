
"""Django settings for DriverXtra backend.

Phase 1: Authentication & User Management.
"""

from pathlib import Path
import os
import sys
from datetime import timedelta
from decimal import Decimal

from dotenv import load_dotenv


# =========================================================
# BASE CONFIGURATION
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from backend/.env
load_dotenv(BASE_DIR / ".env")


# =========================================================
# SECURITY SETTINGS
# =========================================================

SECRET_KEY = os.getenv("SECRET_KEY", "").strip()

if not SECRET_KEY:
    raise ValueError(
        "SECRET_KEY must be configured in the .env file or environment."
    )

DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv(
        "ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0"
    ).split(",")
    if host.strip()
]


# =========================================================
# APPLICATIONS
# =========================================================

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third-party apps
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",

    # Local apps
    "common",
    "apps.identity",
    "apps.organisations",
    "apps.onboarding",
    "apps.catalogue",
    "apps.garage",
    "apps.marketplace",
    "apps.notifications",

    # Platform audit
    "platform_core.audit.apps.AuditConfig",
]


# =========================================================
# MIDDLEWARE
# =========================================================

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "common.middleware.CorrelationIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# =========================================================
# URLS AND TEMPLATES
# =========================================================

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


# =========================================================
# DATABASE CONFIGURATION
# =========================================================

db_engine = os.getenv(
    "DB_ENGINE", "django.db.backends.postgresql"
)
use_sqlite = os.getenv("USE_SQLITE", "False").lower() in ("true", "1")

if use_sqlite or db_engine == "django.db.backends.sqlite3":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    db_password = os.getenv("DB_PASSWORD", "")

    if not db_password:
        raise ValueError(
            "DB_PASSWORD must be configured in the .env file or environment."
        )

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME", "driverxtra_db"),
            "USER": os.getenv("DB_USER", "postgres"),
            "PASSWORD": db_password,
            "HOST": os.getenv("DB_HOST", "localhost"),
            "PORT": os.getenv("DB_PORT", "5432"),
        }
    }


# Use in-memory SQLite for pytest when enabled.
# This preserves the original project's test configuration.
if (
    "test" in sys.argv
    or "pytest" in sys.modules
):
    if os.getenv("TEST_USE_SQLITE", "True").lower() in ("true", "1"):
        DATABASES["default"] = {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }


# =========================================================
# CUSTOM USER MODEL
# =========================================================

AUTH_USER_MODEL = "identity.User"


# =========================================================
# PASSWORD VALIDATION
# =========================================================

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "MinimumLengthValidator"
        ),
        "OPTIONS": {"min_length": 8},
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "CommonPasswordValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "NumericPasswordValidator"
        ),
    },
]


# =========================================================
# INTERNATIONALIZATION
# =========================================================

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# =========================================================
# STATIC FILES
# =========================================================

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# =========================================================
# MEDIA FILES & STORAGE CONFIGURATION
# =========================================================

MEDIA_URL = os.getenv("MEDIA_URL", "/media/")
MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", BASE_DIR / "media"))
MAX_UPLOAD_SIZE_BYTES = int(os.getenv("MAX_UPLOAD_SIZE_BYTES", str(5 * 1024 * 1024)))  # 5 MB default

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# =========================================================
# DJANGO REST FRAMEWORK
# =========================================================

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_PAGINATION_CLASS": (
        "rest_framework.pagination.PageNumberPagination"
    ),
    "PAGE_SIZE": 20,
    "EXCEPTION_HANDLER": "common.exceptions.custom_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "120/minute",
        "user": "300/minute",
        "resend_verification": "5/minute",
        "password_reset": "5/minute",
        "staff_password_reset": "3/minute",
        "login": "10/minute",
        "staff_login": "5/minute",
    },
}

if "test" in sys.argv or "pytest" in sys.modules:
    REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {
        "anon": "10000/minute",
        "user": "10000/minute",
        "resend_verification": "10000/minute",
        "password_reset": "10000/minute",
        "staff_password_reset": "10000/minute",
        "login": "10000/minute",
        "staff_login": "10000/minute",
    }


# =========================================================
# JWT CONFIGURATION
# =========================================================

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=int(os.getenv("ACCESS_TOKEN_LIFETIME_MINUTES", "60"))
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=int(os.getenv("REFRESH_TOKEN_LIFETIME_DAYS", "7"))
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "TOKEN_TYPE_CLAIM": "token_type",
}


# =========================================================
# CORS CONFIGURATION
# =========================================================

CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]

CORS_ALLOW_CREDENTIALS = True


# =========================================================
# EMAIL & NOTIFICATION CONFIGURATION
# =========================================================

EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "no-reply@driverxtra.com")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# SMTP settings (only used when EMAIL_BACKEND is the SMTP backend). Credentials come from the environment only.
EMAIL_HOST = os.getenv("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "25"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "False").lower() in ("true", "1", "yes")
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "False").lower() in ("true", "1", "yes")
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "10"))

# Notifications: in-app notifications are always created; emails are opt-in.
NOTIFICATIONS_EMAIL_ENABLED = os.getenv("NOTIFICATIONS_EMAIL_ENABLED", "False").lower() in ("true", "1", "yes")
NOTIFICATIONS_EMAIL_MAX_ATTEMPTS = int(os.getenv("NOTIFICATIONS_EMAIL_MAX_ATTEMPTS", "5"))


# =========================================================
# MARKETPLACE PRICING & REVIEW CONFIGURATION
# =========================================================

MAX_LISTING_PRICE = Decimal(os.getenv("MAX_LISTING_PRICE", "100000"))
PRICE_OUTLIER_THRESHOLD = Decimal(os.getenv("PRICE_OUTLIER_THRESHOLD", "0.5"))
