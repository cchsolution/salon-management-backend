import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load local environment variables from .env file if present
load_dotenv(BASE_DIR / '.env')

# Django Secret Key
SECRET_KEY = os.getenv(
    'DJANGO_SECRET_KEY',
    'django-insecure-luxe-salon-saas-platform-super-secret-key-2026'
)

# Debug mode: default to False in production unless explicitly enabled
DEBUG = os.getenv('DJANGO_DEBUG', 'False').lower() in ('true', '1', 'yes')

# Allowed Hosts: configurable via comma-separated list
# Preconfigured with local hosts, Render host, and wildcard for render.com subdomains
DEFAULT_ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    '0.0.0.0',
    'testserver',
    'salon-management-e1ag.onrender.com',
    '.onrender.com',
]

allowed_hosts_env = os.getenv('ALLOWED_HOSTS', '')
if allowed_hosts_env:
    configured_hosts = [host.strip() for host in allowed_hosts_env.split(',') if host.strip()]
    ALLOWED_HOSTS = list(dict.fromkeys(DEFAULT_ALLOWED_HOSTS + configured_hosts))
else:
    ALLOWED_HOSTS = DEFAULT_ALLOWED_HOSTS

# Automatically add Render external hostname if running on Render
render_external_hostname = os.getenv('RENDER_EXTERNAL_HOSTNAME')
if render_external_hostname and render_external_hostname not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(render_external_hostname)


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
# Connects to PostgreSQL via DATABASE_URL environment variable (supports Neon, Supabase, Render, etc.)
# If DATABASE_URL is not set, safely falls back to local SQLite.
import dj_database_url

DATABASE_URL = os.getenv('DATABASE_URL')

if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=600,
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

DATABASES['default']['ATOMIC_REQUESTS'] = True


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

# CORS Configuration
from corsheaders.defaults import default_headers

# Allow all origins only if explicitly enabled via environment variable (default False)
CORS_ALLOW_ALL_ORIGINS = os.getenv('CORS_ALLOW_ALL_ORIGINS', 'False').lower() in ('true', '1', 'yes')
CORS_ALLOW_CREDENTIALS = True

# Base allowed origins (local development + production Vercel frontend)
DEFAULT_CORS_ORIGINS = [
    'http://localhost:5173',
    'http://127.0.0.1:5173',
    'http://localhost:3000',
    'http://localhost:8085',
    'http://127.0.0.1:8085',
    'https://salon-management-three.vercel.app',
]

# Additional production origins configured via CORS_ALLOWED_ORIGINS environment variable
cors_origins_env = os.getenv('CORS_ALLOWED_ORIGINS', '')
if cors_origins_env:
    configured_origins = [origin.strip() for origin in cors_origins_env.split(',') if origin.strip()]
    CORS_ALLOWED_ORIGINS = list(dict.fromkeys(DEFAULT_CORS_ORIGINS + configured_origins))
else:
    CORS_ALLOWED_ORIGINS = DEFAULT_CORS_ORIGINS

# Automatically permit Vercel preview and production deployments
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https:\/\/.*\.vercel\.app$",
]

CORS_ALLOW_HEADERS = list(default_headers) + [
    'x-salon-slug',
    'x-salon-id',
]

# CSRF Configuration for cross-origin frontend
DEFAULT_CSRF_ORIGINS = [
    'https://salon-management-three.vercel.app',
    'https://salon-management-e1ag.onrender.com',
    'http://localhost:5173',
    'http://127.0.0.1:5173',
    'http://localhost:3000',
    'http://localhost:8085',
    'http://127.0.0.1:8085',
]

csrf_trusted_env = os.getenv('CSRF_TRUSTED_ORIGINS', '')
if csrf_trusted_env:
    configured_csrf = [origin.strip() for origin in csrf_trusted_env.split(',') if origin.strip()]
    CSRF_TRUSTED_ORIGINS = list(dict.fromkeys(DEFAULT_CSRF_ORIGINS + configured_csrf))
else:
    CSRF_TRUSTED_ORIGINS = DEFAULT_CSRF_ORIGINS


