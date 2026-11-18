"""Django settings selected by CALENDAR_PROFILE: local, private, or production."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CALENDAR_PROFILE = os.environ.get("CALENDAR_PROFILE", "local")
if CALENDAR_PROFILE not in ("local", "private", "production"):
    raise ValueError("CALENDAR_PROFILE must be local, private or production")
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"


def required_setting(name):
    """Fail early when a production-only setting is missing."""

    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required for the production profile")
    return value


def binary_setting(name, default):
    """Accept only explicit 0/1 flags for deployment security settings."""

    value = os.environ.get(name, default)
    if value not in ("0", "1"):
        raise RuntimeError(f"{name} must be 0 or 1")
    return value == "1"


SECRET_KEY = (
    required_setting("SECRET_KEY")
    if CALENDAR_PROFILE == "production"
    else os.environ.get("SECRET_KEY", "django-insecure-local-only")
)

DEBUG = CALENDAR_PROFILE != "production"

ALLOWED_HOSTS = (
    [host.strip() for host in required_setting("ALLOWED_HOSTS").split(",") if host.strip()]
    if CALENDAR_PROFILE == "production"
    else []
)
CSRF_TRUSTED_ORIGINS = (
    [
        origin.strip()
        for origin in required_setting("CSRF_TRUSTED_ORIGINS").split(",")
        if origin.strip()
    ]
    if CALENDAR_PROFILE == "production"
    else []
)
if CALENDAR_PROFILE == "production" and (not ALLOWED_HOSTS or not CSRF_TRUSTED_ORIGINS):
    raise RuntimeError("ALLOWED_HOSTS and CSRF_TRUSTED_ORIGINS must contain values")

if CALENDAR_PROFILE == "production":
    # Set to 0 only for an isolated HTTP smoke test; public traffic requires HTTPS.
    https_enabled = binary_setting("CALENDAR_HTTPS_ENABLED", "1")
    SECURE_SSL_REDIRECT = https_enabled
    SESSION_COOKIE_SECURE = https_enabled
    CSRF_COOKIE_SECURE = https_enabled
    SECURE_HSTS_SECONDS = 31536000 if https_enabled else 0
    # Enable only when the reverse proxy strips client supplied X-Forwarded-Proto.
    if binary_setting("CALENDAR_TRUST_PROXY_HTTPS", "0"):
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "events.apps.EventsConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# A process uses one database; local/private use SQLite, production uses PostgreSQL.

if CALENDAR_PROFILE == "production":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": required_setting("POSTGRES_DB"),
            "USER": required_setting("POSTGRES_USER"),
            "PASSWORD": required_setting("POSTGRES_PASSWORD"),
            "HOST": required_setting("POSTGRES_HOST"),
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.environ.get("CALENDAR_DB")
            or BASE_DIR / ("db.local.sqlite3" if CALENDAR_PROFILE == "local" else "db.sqlite3"),
        }
    }


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
if CALENDAR_PROFILE == "production":
    STORAGES = {
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"}
    }

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
