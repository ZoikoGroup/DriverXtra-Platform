
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

# Secure default: DEBUG is off unless explicitly enabled (e.g. DEBUG=True in a local .env).
# With DEBUG off, Django's static() helper in config/urls.py does not serve MEDIA_ROOT.
DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")
IS_TESTING = "pytest" in sys.modules or "test" in sys.argv or os.getenv("IS_TESTING", "False").lower() in ("true", "1", "yes")

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
    "channels",

    # Local apps
    "common",
    "apps.identity",
    "apps.organisations",
    "apps.onboarding",
    "apps.catalogue",
    "apps.garage",
    "apps.marketplace",
    "apps.notifications",
    "apps.workshops",
    "apps.support",
    "apps.commercial",

    # Platform audit
    "platform_core.audit.apps.AuditConfig",
    "platform_core.events.apps.EventsConfig",
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

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": os.getenv("CHANNEL_LAYER_BACKEND", "channels.layers.InMemoryChannelLayer"),
    }
}


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
        # JWTAuthentication + account status enforcement (SUSPENDED/DEACTIVATED rejected per request)
        "apps.identity.authentication.StatusAwareJWTAuthentication",
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
    # Account status is enforced on token refresh, not only on login.
    "USER_AUTHENTICATION_RULE": "apps.identity.authentication.user_authentication_rule",
    # Refresh keeps the documented 15-minute access lifetime for staff/admin.
    "TOKEN_REFRESH_SERIALIZER": "apps.identity.serializers.StaffAwareTokenRefreshSerializer",
}


# =========================================================
# CORS CONFIGURATION
# =========================================================

from corsheaders.defaults import default_headers

CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]

CORS_ALLOW_CREDENTIALS = True

CORS_ALLOW_HEADERS = (
    *default_headers,
    "idempotency-key",
    "x-idempotency-key",
)


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
# CUSTOMER SUPPORT & TICKETING CONFIGURATION
# =========================================================
SUPPORT_SLA_TIMEZONE = os.getenv("SUPPORT_SLA_TIMEZONE", "UTC")
_holidays_raw = os.getenv("SUPPORT_PUBLIC_HOLIDAYS", "")
SUPPORT_PUBLIC_HOLIDAYS = [h.strip() for h in _holidays_raw.split(",") if h.strip()]
PRIVATE_STORAGE_ROOT = Path(os.getenv("PRIVATE_STORAGE_ROOT", BASE_DIR / "private_media"))

# Test isolation: an actual test run (pytest, or `manage.py test`) never writes into the real
# media directories. Both roots are redirected to a per-process temporary directory that is
# removed at exit. This is resolved here, before any model module is imported, because the
# private storages (support attachments, vehicle documents) read PRIVATE_STORAGE_ROOT at import.
# Deliberately not keyed on the IS_TESTING environment variable, so a misconfigured deployment
# can never redirect real uploads into a temporary directory.
if "pytest" in sys.modules or "test" in sys.argv:
    import atexit
    import shutil
    import tempfile

    _TEST_STORAGE_DIR = Path(tempfile.mkdtemp(prefix="driverxtra-test-storage-"))
    MEDIA_ROOT = _TEST_STORAGE_DIR / "media"
    PRIVATE_STORAGE_ROOT = _TEST_STORAGE_DIR / "private_media"
    MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    PRIVATE_STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    atexit.register(shutil.rmtree, _TEST_STORAGE_DIR, ignore_errors=True)
SUPPORT_ATTACHMENT_MAX_BYTES = int(os.getenv("SUPPORT_ATTACHMENT_MAX_BYTES", "10485760"))  # 10 MB per file
SUPPORT_ATTACHMENT_MAX_FILES_PER_MESSAGE = int(os.getenv("SUPPORT_ATTACHMENT_MAX_FILES_PER_MESSAGE", "5"))
SUPPORT_INACTIVITY_CLOSE_DAYS = int(os.getenv("SUPPORT_INACTIVITY_CLOSE_DAYS", "5"))
SUPPORT_REOPEN_WINDOW_HOURS = int(os.getenv("SUPPORT_REOPEN_WINDOW_HOURS", "72"))


# =========================================================
# MARKETPLACE PRICING & REVIEW CONFIGURATION
# =========================================================

MAX_LISTING_PRICE = Decimal(os.getenv("MAX_LISTING_PRICE", "100000"))
PRICE_OUTLIER_THRESHOLD = Decimal(os.getenv("PRICE_OUTLIER_THRESHOLD", "0.5"))


# =========================================================
# PAYMENT GATEWAY & CASH ON DELIVERY (COD) CONFIGURATION
# =========================================================

# Payment test mode is explicitly opt-in (defaults to False in production).
# Only permitted in development (DEBUG=True) or automated testing (IS_TESTING=True).
PAYMENT_TEST_MODE = os.getenv("PAYMENT_TEST_MODE", "True" if (DEBUG or IS_TESTING) else "False").lower() in ("true", "1", "yes")

# Razorpay (India / INR)
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "rzp_test_placeholder_key")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "rzp_test_placeholder_secret")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "rzp_test_webhook_secret")
RAZORPAY_API_URL = os.getenv("RAZORPAY_API_URL", "https://api.razorpay.com/v1")
PAYMENT_EXPIRY_MINUTES = int(os.getenv("PAYMENT_EXPIRY_MINUTES", "30"))

# Stripe (UK / GBP & International Cards)
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "pk_test_placeholder_key")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "sk_test_placeholder_secret")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_test_placeholder_secret")

# Advertising Payment Gates (Disabled until formal tax and accounting signoff)
LIVE_ADVERTISING_PAYMENTS_ENABLED = os.getenv("LIVE_ADVERTISING_PAYMENTS_ENABLED", "False").lower() in ("true", "1", "yes")
LIVE_ADVERTISING_CHARGES_ENABLED = os.getenv(
    "LIVE_ADVERTISING_CHARGES_ENABLED",
    str(LIVE_ADVERTISING_PAYMENTS_ENABLED)
).lower() in ("true", "1", "yes")
LIVE_ADVERTISING_REFUNDS_ENABLED = os.getenv("LIVE_ADVERTISING_REFUNDS_ENABLED", "False").lower() in ("true", "1", "yes")

# Cash on Delivery (COD) Rules
COD_ENABLED = os.getenv("COD_ENABLED", "True").lower() in ("true", "1", "yes")
COD_ALLOWED_COUNTRIES = [
    c.strip().upper()
    for c in os.getenv("COD_ALLOWED_COUNTRIES", "IN,GB").split(",")
    if c.strip()
]
COD_MAX_AMOUNT_INR = Decimal(os.getenv("COD_MAX_AMOUNT_INR", "50000.00"))
COD_MAX_AMOUNT_GBP = Decimal(os.getenv("COD_MAX_AMOUNT_GBP", "500.00"))


# =========================================================
# MULTI-CURRENCY & EXCHANGE RATE CONFIGURATION
# =========================================================

# Explicit server-side exchange rates for cross-currency checkout
# Pairs are (FROM_CURRENCY, TO_CURRENCY): Decimal rate
CURRENCY_EXCHANGE_RATES = {
    ("GBP", "INR"): Decimal(os.getenv("EXCHANGE_RATE_GBP_INR", "105.00")),
    ("INR", "GBP"): Decimal(os.getenv("EXCHANGE_RATE_INR_GBP", "0.0095")),
}

# UK VAT rate (isolated from Indian GST rules)
UK_VAT_RATE = Decimal(os.getenv("UK_VAT_RATE", "0.00"))

# =========================================================
# MAKER-CHECKER APPROVAL CONFIGURATION
# =========================================================

# High-value operations require maker-checker dual authorization.
# Proposed default dual-authorization thresholds pending formal business approval.
# Configurable via environment variables (MAKER_CHECKER_THRESHOLD_GBP, MAKER_CHECKER_THRESHOLD_INR).
MAKER_CHECKER_THRESHOLDS = {
    "GBP": Decimal(os.getenv("MAKER_CHECKER_THRESHOLD_GBP", "500.00")),
    "INR": Decimal(os.getenv("MAKER_CHECKER_THRESHOLD_INR", "50000.00")),
}
MAKER_CHECKER_DEFAULT_THRESHOLD = Decimal(os.getenv("MAKER_CHECKER_DEFAULT_THRESHOLD", "500.00"))

# =========================================================
# MULTI-FACTOR AUTHENTICATION (MFA) CONFIGURATION
# =========================================================

# Controls whether mandatory TOTP MFA enforcement is required.
# Default is False in both local and deployed environments so that users across
# all roles (ADMIN, BUYER, SELLER, WORKSHOP) can authenticate using email and password only.
# Set MFA_MANDATORY_ENFORCED=True to re-enable mandatory dual-factor login.
MFA_MANDATORY_ENFORCED = os.getenv("MFA_MANDATORY_ENFORCED", "False").lower() in ("true", "1", "yes")

# =========================================================
# CELERY & REDIS CONFIGURATION (Phase 7.1)
# =========================================================

CELERY_BROKER_URL = os.environ.get(
    "CELERY_BROKER_URL",
    os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0"),
)
CELERY_RESULT_BACKEND = os.environ.get(
    "CELERY_RESULT_BACKEND",
    os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0"),
)

# JSON-only serialization for safe execution
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

# Task acknowledgement, worker resilience and safe retry behaviour
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_DEFAULT_RETRY_DELAY = 60
CELERY_TASK_MAX_RETRIES = 3
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes hard execution limit
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60  # 25 minutes soft execution limit
CELERY_RESULT_EXPIRES = 86400  # 24 hours
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# CELERY BEAT PERIODIC SCHEDULE (Phase 7.1 & 7.2)
CELERY_BEAT_SCHEDULE = {
    'recover-pending-bulk-upload-jobs': {
        'task': 'apps.marketplace.tasks.recover_pending_bulk_upload_jobs_task',
        'schedule': 600.0,  # every 10 minutes (600s)
    },
    'activate-scheduled-advertising-campaigns': {
        'task': 'apps.marketplace.tasks.activate_scheduled_campaigns_task',
        'schedule': 300.0,  # every 5 minutes
    },
    'recover-held-advertising-campaigns': {
        'task': 'apps.marketplace.tasks.recover_held_advertising_campaigns_task',
        'schedule': 300.0,  # every 5 minutes
    },
    'expire-completed-advertising-campaigns': {
        'task': 'apps.marketplace.tasks.expire_completed_campaigns_task',
        'schedule': 900.0,  # every 15 minutes
    },
    'aggregate-campaign-daily-metrics': {
        'task': 'apps.marketplace.tasks.aggregate_campaign_daily_metrics_task',
        'schedule': 1800.0,  # every 30 minutes
    },
}

