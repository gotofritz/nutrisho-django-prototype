"""The Config page: the tools that do not need a place in the header."""

from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from recipes.views._types import AuthedRequest


@require_GET
def config(request: AuthedRequest) -> HttpResponse:
    """Links to the trash, import and export, and for staff the shared-vocabulary tools."""
    return render(request, "recipes/config.html")
