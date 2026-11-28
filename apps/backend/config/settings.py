"""Settings for the Django process under apps/backend.

URL root is config/urls.py, which mounts api/v1/urls.py.
Session cookies are still issued by apps/backend/auth/server.py (make hub, port 4600).
This process reads them. It does not write auth.sqlite.

DJANGO_SECRET_KEY, when set, comes from the environment. An empty value
becomes a per-process key so nothing secret is stored in the repo.
Provider credentials (Kaleyra, mail, Mobikwik, Cashfree, PayU) come from
apps/backend/.env via config.envfile.load_backend_env. They are not Django
settings fields.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from config.envfile import ensure_backend_env
from core.privatefiles import restrict_private

BASE_DIR = Path(__file__).resolve().parent.parent
ensure_backend_env()

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or secrets.token_urlsafe(32)
DEBUG = os.environ.get("DJANGO_DEBUG") == "1"
# Comma-separated. Default stays loopback-only so a bare deploy is not open.
_ALLOWED = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
    if host.strip()
]
ALLOWED_HOSTS = _ALLOWED or ["127.0.0.1", "localhost"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "rest_framework",
    "models.apps.HubModelsConfig",
]

MIDDLEWARE = [
    "config.request.RequestContextMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "config.cors.FrontendOriginMiddleware",
    "config.exceptions.ApiErrorEnvelopeMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("HUB_DB_PATH", DATA_DIR / "hub.sqlite"),
    }
}

restrict_private(DATA_DIR)
restrict_private(Path(DATABASES["default"]["NAME"]))

# Auth on port 4600 keeps BODY_MAX at 4096. This process also reads a PayU
# callback form and desk JSON, so the ceiling is larger and still bounded.
# DRF 3.18 enforces both limits while parsing request.data.
DATA_UPLOAD_MAX_MEMORY_SIZE = 64 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 80

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_AUTHENTICATION_CLASSES": ["api.v1.deps.AppContextAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["api.v1.deps.AppScopePermission"],
    "EXCEPTION_HANDLER": "config.exceptions.api_exception",
}

# Default origins from apps/backend/auth/server.py AUTH_ORIGINS, plus this process
# when it is run on 4610. make hub stays on 4600.
FRONTEND_ORIGINS = {
    "http://127.0.0.1:4310",
    "http://127.0.0.1:4500",
    "http://localhost:4310",
    "http://localhost:4500",
    "http://127.0.0.1:4610",
    "http://localhost:4610",
}
