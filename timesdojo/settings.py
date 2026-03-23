"""
timesdojo/settings.py
---------------------
Main settings file. Environment-aware:
  - reads SECRET_KEY, DEBUG, DATABASE_URL etc. from environment variables
  - safe defaults for local development
  - production checklist items clearly commented
  - Supports both SQLite (local) and PostgreSQL (Railway production)

Usage:
  Local dev  →  python manage.py runserver (uses SQLite)
  Production →  set DATABASE_URL env var, then gunicorn timesdojo.wsgi (uses PostgreSQL)
"""

import os
import sys
import dj_database_url
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# BASE PATHS
# ─────────────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent


# ─────────────────────────────────────────────────────────────────────────────
# SECURITY — read from environment in production, fallback for dev
# ─────────────────────────────────────────────────────────────────────────────
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "dev-insecure-key-change-this-before-deploying-timesdojo-2025",
)

# Set DJANGO_DEBUG=False in your production environment
DEBUG = os.environ.get("DJANGO_DEBUG", "True") == "True"

# =============================================================================
# ALLOWED_HOSTS - MUST include Railway domain and any custom domains
# =============================================================================
# Get allowed hosts from environment variable, with defaults for local and Railway
ALLOWED_HOSTS_ENV = os.environ.get("DJANGO_ALLOWED_HOSTS", "")

if ALLOWED_HOSTS_ENV:
    ALLOWED_HOSTS = ALLOWED_HOSTS_ENV.split(",")
else:
    # Default for local development
    ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# Add all domains (Railway and custom domain)
ALLOWED_HOSTS.extend([
    # Railway domains
    "mfalme-premium-dojo-production.up.railway.app",
    "web-production-d50e9.up.railway.app",
    ".railway.app",
    ".up.railway.app",
    
    # Custom domain
    "revisionea.online",
    "www.revisionea.online",
    "https://www.revisionea.online",
    "revisionea.online",
])

# Remove duplicates while preserving order
ALLOWED_HOSTS = list(dict.fromkeys(ALLOWED_HOSTS))

# Trust proxy headers (Railway uses these)
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Fix trailing slash issues with POST requests
APPEND_SLASH = False

# ─────────────────────────────────────────────────────────────────────────────
# CSRF TRUSTED ORIGINS - Required for Railway and custom domains
# ─────────────────────────────────────────────────────────────────────────────
CSRF_TRUSTED_ORIGINS = os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if os.environ.get("CSRF_TRUSTED_ORIGINS") else []

# Add all domains to CSRF trusted origins
CSRF_TRUSTED_ORIGINS.extend([
    # Railway domains
    "https://mfalme-premium-dojo-production.up.railway.app",
    "https://web-production-d50e9.up.railway.app",
    "https://*.railway.app",
    "https://*.up.railway.app",
    
    # Custom domain
    "https://revisionea.online",
    "https://www.revisionea.online",
    "http://revisionea.online",
    "http://www.revisionea.online",
])

# Add HTTP versions for local development if needed
if DEBUG:
    CSRF_TRUSTED_ORIGINS.extend([
        "http://mfalme-premium-dojo-production.up.railway.app",
        "http://web-production-d50e9.up.railway.app",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ])

# Remove duplicates and empty strings
CSRF_TRUSTED_ORIGINS = [origin for origin in set(CSRF_TRUSTED_ORIGINS) if origin]

# Media and static files
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
DAILY_API_KEY = "e13401dd1b121ba5f8cdd61e80aaf3c5916335947301044963217ed8e283e157"

# Paystack Configuration
PAYSTACK_SECRET_KEY = "sk_live_fc4f550a27a942bc0f6ce014c57b1834c4b6195d"  
PAYSTACK_PUBLIC_KEY = "pk_live_197cf61799bc7493f737268952280f5da78cc7a4"  

# Subscription prices in USD
SUBSCRIPTION_PRICES = {
    'monthly': 5.00,
    'half_yearly': 25.00,
    'yearly': 50.00,
}

# Subscription durations in days
SUBSCRIPTION_DURATIONS = {
    'monthly': 30,
    'half_yearly': 180,
    'yearly': 365,
}

# Trial period in days
TRIAL_DAYS = 3


# ─────────────────────────────────────────────────────────────────────────────
# INSTALLED APPS
# ─────────────────────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    # Django built-ins
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Our app
    "dojo",
]


# ─────────────────────────────────────────────────────────────────────────────
# MIDDLEWARE
# ─────────────────────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────────────────────
# URL CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
ROOT_URLCONF = "timesdojo.urls"


# ─────────────────────────────────────────────────────────────────────────────
# TEMPLATES
# ─────────────────────────────────────────────────────────────────────────────
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "dojo" / "templates"],
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


# ─────────────────────────────────────────────────────────────────────────────
# WSGI
# ─────────────────────────────────────────────────────────────────────────────
WSGI_APPLICATION = "timesdojo.wsgi.application"


# ─────────────────────────────────────────────────────────────────────────────
# DATABASE
# Automatically switches between SQLite and PostgreSQL based on DATABASE_URL
# For local development: uses SQLite (no DATABASE_URL needed)
# For Railway production: set DATABASE_URL environment variable
# ─────────────────────────────────────────────────────────────────────────────

# Try to get database URL from environment (Railway sets this automatically)
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Check if we're running on Railway (has DATABASE_URL)
if DATABASE_URL:
    # Production: PostgreSQL on Railway
    print(f"✅ Using PostgreSQL database from Railway", file=sys.stderr)
    DATABASES = {
        "default": dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
            ssl_require=True  # Railway requires SSL
        )
    }
else:
    # Local development: SQLite
    print("📁 Using SQLite database for local development", file=sys.stderr)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# ─────────────────────────────────────────────────────────────────────────────
# AUTH — we extend Django's built-in User model
# ─────────────────────────────────────────────────────────────────────────────
AUTH_USER_MODEL = "dojo.User"

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 6}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]


# ─────────────────────────────────────────────────────────────────────────────
# SESSIONS  (server-side, stored in DB)
# ─────────────────────────────────────────────────────────────────────────────
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7   # 7 days
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

# In production with HTTPS, set secure cookies
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True


# ─────────────────────────────────────────────────────────────────────────────
# INTERNATIONALISATION
# ─────────────────────────────────────────────────────────────────────────────
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = True
USE_TZ = True


# ─────────────────────────────────────────────────────────────────────────────
# STATIC FILES
# ─────────────────────────────────────────────────────────────────────────────
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "dojo" / "static"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"


# ─────────────────────────────────────────────────────────────────────────────
# MEDIA (user uploads)
# ─────────────────────────────────────────────────────────────────────────────
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


# ─────────────────────────────────────────────────────────────────────────────
# DEFAULT PRIMARY KEY
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "dojo": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# PRODUCTION SECURITY HEADERS
# ─────────────────────────────────────────────────────────────────────────────
if not DEBUG:
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_PRELOAD = True