"""Django settings for the Dr. Moustafa Kamel Academy site.

Everything that differs between your Mac and Azure comes from environment variables
(.env locally via dev.sh, App Service → Configuration on Azure):

  DJANGO_SECRET_KEY   required in production (deploy/azure_deploy.sh creates one)
  DJANGO_DEBUG        "1" on your Mac (dev.sh sets it), unset in production
  DB_PATH             SQLite file; default data/db.sqlite3, on Azure /home/data/db.sqlite3
  ALLOWED_HOSTS       extra host names, comma separated (e.g. a custom domain)
  MEDIA_ROOT          uploaded videos/pictures; default media/, on Azure /home/media
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.environ.get("DJANGO_DEBUG") == "1"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or ("dev-only-not-secret" if DEBUG else None)
if not SECRET_KEY:
    raise RuntimeError("Set DJANGO_SECRET_KEY (or DJANGO_DEBUG=1 for local development)")

ALLOWED_HOSTS = ["localhost", "127.0.0.1", ".azurewebsites.net"]
ALLOWED_HOSTS += [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()]
if DEBUG:
    ALLOWED_HOSTS = ["*"]  # phones on the same Wi-Fi use the Mac's IP address
# admin login form over https (Azure, plus any custom domain from ALLOWED_HOSTS)
CSRF_TRUSTED_ORIGINS = ["https://*.azurewebsites.net"] + [
    f"https://{h.strip().lstrip('.')}" for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()]

# Azure terminates HTTPS in front of us: trust its X-Forwarded-* headers so links
# (QR code, share links, admin redirects) use the real public https:// address.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
if not DEBUG:
    SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "catalog",
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

ROOT_URLCONF = "academy.urls"
WSGI_APPLICATION = "academy.wsgi.application"

TEMPLATES = [
    {   # the public site: Jinja templates in templates/ (helpers in academy/jinja2.py)
        "BACKEND": "django.template.backends.jinja2.Jinja2",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": False,
        "OPTIONS": {"environment": "academy.jinja2.environment"},
    },
    {   # Django's built-in admin
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": [
            "django.template.context_processors.request",
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
        ]},
    },
]

DB_PATH = Path(os.environ.get("DB_PATH") or BASE_DIR / "data" / "db.sqlite3")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DB_PATH,
        # wait instead of failing if two workers write at the same moment
        "OPTIONS": {"timeout": 20, "transaction_mode": "IMMEDIATE"},
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"   # filled by `manage.py collectstatic` (admin CSS etc.)
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
WHITENOISE_USE_FINDERS = DEBUG

# Uploaded lesson videos and pictures (served by catalog.views.media, with seeking support)
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT") or BASE_DIR / "media")
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024   # bigger uploads are streamed to a temp file, not kept in memory
WHITENOISE_MAX_AGE = 3600

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
}
