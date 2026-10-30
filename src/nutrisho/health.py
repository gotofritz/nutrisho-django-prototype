"""Unauthenticated health check for uptime monitors and deploy smoke checks."""

import logging

from django.contrib.auth.decorators import login_not_required
from django.db import DatabaseError, connection
from django.http import HttpRequest, HttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

logger = logging.getLogger(__name__)


@login_not_required
@never_cache
@require_safe
def healthz(request: HttpRequest) -> HttpResponse:  # noqa: ARG001 - view signature
    """Answer 200 when the database answers SELECT 1, otherwise 503."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        logger.exception("Health check failed: database unavailable")
        return HttpResponse("database unavailable", status=503, content_type="text/plain")
    return HttpResponse("ok", content_type="text/plain")
