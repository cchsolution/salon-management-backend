import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load local environment variables from .env file if present (checks backend/.env and root .env)
load_dotenv(BASE_DIR / '.env')
load_dotenv(BASE_DIR.parent / '.env')

# Django Secret Key
SECRET_KEY = (
    os.getenv('DJANGO_SECRET_KEY')
    or os.getenv('SECRET_KEY')
    or 'django-insecure-luxe-salon-saas-platform-super-secret-key-2026'
)

# Debug mode: default to False in production unless explicitly enabled
_debug_raw = os.getenv('DJANGO_DEBUG') or os.getenv('DEBUG', 'False')
DEBUG = str(_debug_raw).lower() in ('true', '1', 'yes')

# Allowed Hosts: configurable via comma-separated list
# Preconfigured with local hosts and wildcard for Vercel subdomains
DEFAULT_ALLOWED_HOSTS = [
    '*',
]

# allowed_hosts_env = os.getenv('ALLOWED_HOSTS', '')
# if allowed_hosts_env:
#     configured_hosts = [host.strip() for host in allowed_hosts_env.split(',') if host.strip()]
#     ALLOWED_HOSTS = list(dict.fromkeys(DEFAULT_ALLOWED_HOSTS + configured_hosts))
# else:
#     ALLOWED_HOSTS = DEFAULT_ALLOWED_HOSTS

ALLOWED_HOSTS = DEFAULT_ALLOWED_HOSTS

# Automatically add Vercel deployment URLs if running on Vercel
vercel_url = os.getenv('VERCEL_URL')
if vercel_url and vercel_url not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(vercel_url)

vercel_project_url = os.getenv('VERCEL_PROJECT_PRODUCTION_URL')
if vercel_project_url and vercel_project_url not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(vercel_project_url)


# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third-party apps
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
    
    # LuxeSalon Domain apps
    'apps.core',
    'apps.tenants',
    'apps.catalog',
    'apps.customers',
    'apps.appointments',
    'apps.pos',
    'apps.inventory',
    'apps.loyalty',
    'apps.website_builder',
    'apps.analytics',
    'apps.notifications',
]

AUTH_USER_MODEL = 'core.User'

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.tenants.middleware.TenantMiddleware',
]

ROOT_URLCONF = 'salon_core.urls'

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

WSGI_APPLICATION = 'salon_core.wsgi.application'

# Database configuration
# Connects to PostgreSQL via DATABASE_URL environment variable (e.g., Neon PostgreSQL)
# If DATABASE_URL is not set, safely falls back to local SQLite.
import dj_database_url

DATABASE_URL = os.getenv('DATABASE_URL')

# In serverless environments like Vercel, functions freeze between invocations.
# Setting conn_max_age=0 on Vercel prevents stale or broken pooled connections to Neon.
default_conn_max_age = 0 if os.getenv('VERCEL') else 600
conn_max_age = int(os.getenv('DATABASE_CONN_MAX_AGE', default_conn_max_age))

if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=conn_max_age,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Use lightweight SQLite for test runner to avoid CREATE DATABASE permission issues on pooled databases
import sys
if 'test' in sys.argv:
    DATABASES['default'] = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'test_db.sqlite3',
    }

DATABASES['default']['ATOMIC_REQUESTS'] = False


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 6},
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# Static and Media files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# WhiteNoise configuration:
# When running on Vercel, WHITENOISE_USE_FINDERS fallback ensures admin and DRF assets
# are resolved even if collectstatic is skipped or run dynamically.
WHITENOISE_USE_FINDERS = os.getenv(
    'WHITENOISE_USE_FINDERS',
    'True' if (os.getenv('VERCEL') or not (STATIC_ROOT.exists() and any(STATIC_ROOT.iterdir()))) else 'False'
).lower() in ('true', '1', 'yes')

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
    },
}

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework Configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'apps.core.authentication.UnifiedTokenAuthentication',
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 25,
    'DATETIME_FORMAT': '%Y-%m-%d %H:%M:%S',
}

# Cache Configuration (High-performance in-memory caching)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'salon-cache',
    }
}

# # CORS Configuration
# from corsheaders.defaults import default_headers

# # Allow all origins only if explicitly enabled via environment variable (default False)
# CORS_ALLOW_ALL_ORIGINS = os.getenv('CORS_ALLOW_ALL_ORIGINS', 'False').lower() in ('true', '1', 'yes')
# CORS_ALLOW_CREDENTIALS = True

# # Base allowed origins (local development + production Vercel frontend)
# # DEFAULT_CORS_ORIGINS = [
# #     'http://localhost:5173',
# #     'http://127.0.0.1:5173',
# #     'http://localhost:3000',
# #     'http://localhost:8085',
# #     'http://127.0.0.1:8085',
# #     'https://salon-management-three.vercel.app',
# # ]
# DEFAULT_CORS_ORIGINS = [
#     '*',
# ]

# # Additional production origins configured via CORS_ALLOWED_ORIGINS environment variable
# # cors_origins_env = os.getenv('CORS_ALLOWED_ORIGINS', '')
# # if cors_origins_env:
# #     configured_origins = [origin.strip() for origin in cors_origins_env.split(',') if origin.strip()]
# #     CORS_ALLOWED_ORIGINS = list(dict.fromkeys(DEFAULT_CORS_ORIGINS + configured_origins))
# # else:
# #     CORS_ALLOWED_ORIGINS = DEFAULT_CORS_ORIGINS

# CORS_ALLOWED_ORIGINS = DEFAULT_CORS_ORIGINS

# # Automatically permit Vercel preview and production deployments
# CORS_ALLOWED_ORIGIN_REGEXES = [
#     r"^https:\/\/.*\.vercel\.app$",
# ]

# CORS_ALLOW_HEADERS = list(default_headers) + [
#     'x-salon-slug',
#     'x-salon-id',
#     'x-auth-token',
# ]

# # CSRF Configuration for cross-origin frontend
# DEFAULT_CSRF_ORIGINS = [
#     '*',
# ]

# # csrf_trusted_env = os.getenv('CSRF_TRUSTED_ORIGINS', '')
# # if csrf_trusted_env:
# #     configured_csrf = [origin.strip() for origin in csrf_trusted_env.split(',') if origin.strip()]
# #     CSRF_TRUSTED_ORIGINS = list(dict.fromkeys(DEFAULT_CSRF_ORIGINS + configured_csrf))
# # else:
# #     CSRF_TRUSTED_ORIGINS = DEFAULT_CSRF_ORIGINS


# CORS Configuration
from corsheaders.defaults import default_headers

CORS_ALLOWED_ORIGINS = [
    "https://salon-app.cchsolution.com",
    "https://salon-management-frontend-ten.vercel.app",
]

# Optional: allow Vercel preview deployments
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://[a-zA-Z0-9-]+\.vercel\.app$",
]

CORS_ALLOW_CREDENTIALS = True

CORS_ALLOW_HEADERS = list(default_headers) + [
    "x-salon-slug",
    "x-salon-id",
    "x-auth-token",
]

# CSRF trusted origins
CSRF_TRUSTED_ORIGINS = [
    "https://salon-app.cchsolution.com",
    "https://salon-management-frontend-ten.vercel.app",
    "https://*.vercel.app",
]

CORS_ALLOW_ALL_ORIGINS = True
