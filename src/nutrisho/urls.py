from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("recipes/", include("recipes.urls")),
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += [path("__debug__/", include("debug_toolbar.urls"))]
