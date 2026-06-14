from django.conf import settings
from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.urls import include, path

from recipes.views._auth import htmx_login_required


@htmx_login_required
def _root(request: HttpRequest) -> HttpResponse:
    return HttpResponse("""
        <h1>Nutrisho</h1>
        <a href="./recipes/">Recipes</a>
        """)


urlpatterns = [
    path("", _root),
    path("accounts/", include("django.contrib.auth.urls")),
    path("recipes/", include("recipes.urls")),
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += [path("__debug__/", include("debug_toolbar.urls"))]
