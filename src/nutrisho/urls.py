from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from nutrisho.health import healthz

urlpatterns = [
    # The recipe list is the home page (#74); `/` has no page of its own.
    path("", RedirectView.as_view(pattern_name="recipes:home")),
    path("healthz", healthz),
    path("accounts/", include("django.contrib.auth.urls")),
    path("recipes/", include("recipes.urls")),
    path("admin/", admin.site.urls),
]

if "debug_toolbar" in settings.INSTALLED_APPS:
    urlpatterns += [path("__debug__/", include("debug_toolbar.urls"))]
