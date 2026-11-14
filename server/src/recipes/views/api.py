"""The JSON endpoint the recipe clipper submits recipes to (#78).

The rest of the app is server-rendered pages behind a session login. This is
the exception, for a client that is not a browser page: the extension's
service worker, or a script. It is signed in by an API token sent as
`Authorization: Bearer <key>` (`services/api_tokens.py`), never by the session
cookie, so it can skip CSRF: a page that makes a browser post here carries no
key. It is exempt from the login middleware for the same reason, and answers
in JSON throughout, never with a redirect to the login page.
"""

from django.contrib.auth.decorators import login_not_required
from django.core.exceptions import RequestDataTooBig
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from recipes.services.api_tokens import bearer_key, user_for_key
from recipes.services.recipe_document import ImportFormatError, parse_json
from recipes.services.recipe_import import import_recipes

_UNAUTHORISED = "Send a valid API token as “Authorization: Bearer <token>”."


def _error(message: str, *, status: int) -> JsonResponse:
    return JsonResponse({"error": message}, status=status)


@login_not_required
@csrf_exempt
@require_POST
def api_recipes(request: HttpRequest) -> JsonResponse:
    """Create recipes from a JSON body: schema.org Recipe JSON-LD, or a Nutrisho document.

    201 lists each new recipe's id, name, page and whether it was renamed or
    went to the trash, with any warnings; 400 says why the body cannot be read,
    401 that the token is missing or wrong, 413 that the body is too large.
    """
    user = user_for_key(bearer_key(request.headers.get("Authorization", "")))
    if user is None:
        response = _error(_UNAUTHORISED, status=401)
        response["WWW-Authenticate"] = 'Bearer realm="nutrisho"'
        return response
    try:
        batch = parse_json(request.body)
    except RequestDataTooBig:
        return _error("The request body is too large.", status=413)
    except ImportFormatError as exc:
        return _error(str(exc), status=400)
    result = import_recipes(owner=user, batch=batch)
    recipes = [
        {
            "id": imported.recipe.pk,
            "name": imported.recipe.plain_name,
            "url": request.build_absolute_uri(imported.recipe.get_absolute_url()),
            "renamed": imported.renamed,
            "in_trash": imported.recipe.deleted_at is not None,
        }
        for imported in result.recipes
    ]
    return JsonResponse({"recipes": recipes, "warnings": result.warnings}, status=201)
