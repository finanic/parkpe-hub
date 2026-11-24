"""Site URLs. Product routes live under /api/v1/ (api/v1/urls.py).

Auth routes (/api/auth/login, /api/auth/me, and the rest of Paths) stay on
apps/backend/auth/server.py. This file does not include them.
"""

from django.urls import include, path

urlpatterns = [
    path("api/v1/", include("api.v1.urls")),
]
