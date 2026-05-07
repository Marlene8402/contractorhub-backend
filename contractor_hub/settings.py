import os
from pathlib import Path
from decouple import config
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY: hard-fail if SECRET_KEY is missing. The previous default
# ('django-insecure-dev-key-change-in-production') is publicly known and
# would let an attacker forge session cookies and password-reset tokens
# if it ever silently became active. Better to refuse to boot than run
# with a known key.
SECRET_KEY = config('SECRET_KEY')

DEBUG = config('DEBUG', default=True, cast=bool)

_allowed = config('ALLOWED_HOSTS', default='localhost,127.0.0.1')
ALLOWED_HOSTS = [h.strip() for h in _allowed.split(',')]

# Security headers — only applied in production (DEBUG=False) so local dev
# can still talk to http://localhost without refused cookies.
#
# SECURE_SSL_REDIRECT is intentionally OFF. Railway's edge proxy already
# 301s HTTP→HTTPS before requests reach this container; enabling Django's
# redirect on top breaks Railway's internal healthchecks (they hit the
# container over HTTP without X-Forwarded-Proto, get redirected, and mark
# the deploy as unhealthy).
#
# SECURE_PROXY_SSL_HEADER tells Django to trust X-Forwarded-Proto from
# Railway's edge, so request.is_secure() returns True for real client
# traffic — which is what unlocks HSTS being set on responses.
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_HSTS_SECONDS = 31536000          # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    # SECURE_HSTS_PRELOAD intentionally OFF — turn on only after submitting
    # to the HSTS preload list at hstspreload.org and verifying everything
    # works for at least a few weeks at 1-year HSTS.
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = 'same-origin'
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    X_FRAME_OPTIONS = 'DENY'

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
    'api',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'contractor_hub.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'contractor_hub.wsgi.application'

# Database — Railway provides DATABASE_URL automatically in production.
# Locally, DB_HOST=localhost triggers SQLite.
_database_url = config('DATABASE_URL', default='')
_db_host = config('DB_HOST', default='localhost')

if _database_url:
    DATABASES = {'default': dj_database_url.parse(_database_url)}
elif _db_host in ('localhost', '127.0.0.1'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config('DB_NAME', default='railway'),
            'USER': config('DB_USER', default='postgres'),
            'PASSWORD': config('DB_PASSWORD', default=''),
            'HOST': _db_host,
            'PORT': config('DB_PORT', default='5432'),
        }
    }

# Auth
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 100,
}

# CORS
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
]

# Field-level encryption key for sensitive at-rest data (currently QB
# OAuth tokens; will also cover the QBWC password when Desktop ships).
# Generate via: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
# In DEBUG mode, api.fields.EncryptedTextField derives a key from SECRET_KEY
# so local dev doesn't need this set.
FIELD_ENCRYPTION_KEY = config('FIELD_ENCRYPTION_KEY', default='')

# QB OAuth Settings
QB_CLIENT_ID = config('QB_CLIENT_ID', default='')
QB_CLIENT_SECRET = config('QB_CLIENT_SECRET', default='')
QB_REDIRECT_URI = config('QB_REDIRECT_URI', default='https://contractorhub-backend-production.up.railway.app/api/auth/quickbooks/callback/')
QB_REALM_ID = config('QB_REALM_ID', default='')

# QB v2 — toggle between Intuit's sandbox and production API hosts.
# Default True (sandbox) until we have paying customers connecting their
# real QB. Production deploy sets QB_USE_SANDBOX=False env var.
QB_USE_SANDBOX = config('QB_USE_SANDBOX', default=True, cast=bool)

# Email (for future use)
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Stripe billing
STRIPE_SECRET_KEY      = config('STRIPE_SECRET_KEY',      default='')
STRIPE_PUBLISHABLE_KEY = config('STRIPE_PUBLISHABLE_KEY', default='')
STRIPE_WEBHOOK_SECRET  = config('STRIPE_WEBHOOK_SECRET',  default='')

# Tier → Stripe Price ID. Set these per-environment from the Stripe dashboard.
STRIPE_PRICE_STARTER = config('STRIPE_PRICE_STARTER', default='')  # $79/mo
STRIPE_PRICE_PRO     = config('STRIPE_PRICE_PRO',     default='')  # $199/mo
STRIPE_PRICE_SCALE   = config('STRIPE_PRICE_SCALE',   default='')  # $349/mo

# URLs Stripe Checkout redirects to after success / cancel. The Mac app uses
# its own custom-scheme deep links; the web app uses the marketing site.
STRIPE_CHECKOUT_SUCCESS_URL = config('STRIPE_CHECKOUT_SUCCESS_URL',
                                     default='contractorhub://billing/success')
STRIPE_CHECKOUT_CANCEL_URL  = config('STRIPE_CHECKOUT_CANCEL_URL',
                                     default='contractorhub://billing/cancel')
STRIPE_PORTAL_RETURN_URL    = config('STRIPE_PORTAL_RETURN_URL',
                                     default='contractorhub://billing/portal-return')

# Days of free trial granted on signup. No card required to start.
SIGNUP_TRIAL_DAYS = config('SIGNUP_TRIAL_DAYS', default=14, cast=int)
