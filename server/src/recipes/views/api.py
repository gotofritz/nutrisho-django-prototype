"""The JSON endpoints the recipe clipper uses (#78, #160).

`api_recipes` saves recipes; `api_vocabulary` answers with the lists the
clipper checks a draft's names against. The rest of the app is server-rendered
pages behind a session login. These are the exception, for a client that is
not a browser page: the extension's
service worker, or a script. It is signed in by an API token sent as
`Authorization: Bearer <key>` (`services/api_tokens.py`), never by the session
cookie, so it can skip CSRF: a page that makes a browser post here carries no
key. It is exempt from the login middleware for the same reason, and answers
in JSON throughout, never with a redirect to the login page.
"""

from uuid import UUID

from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.models import AbstractBaseUser
from django.core.exceptions import RequestDataTooBig
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from recipes.services.api_tokens import bearer_key, user_for_key
from recipes.services.recipe_document import ImportFormatError, parse_json
from recipes.services.recipe_import import RecipeIdTakenError, import_recipes
from recipes.services.vocabulary import vocabulary

_UNAUTHORISED = "Send a valid API token as “Authorization: Bearer <token>”."
_BAD_ID = "“id” must be a version 7 UUID."
# Says nothing of whose recipe holds the id, or whether it is live.
_ID_TAKEN = "That id is taken: make a new one for this recipe."
_UUID_VERSION = 7  # sorts by age, which the export, search and the trash rely on (#156)


def _key_user(request: HttpRequest) -> AbstractBaseUser | None:
    """The user whose API key the request carries; never the session's."""
    return user_for_key(bearer_key(request.headers.get("Authorization", "")))


def _unauthorised() -> JsonResponse:
    response = _error(_UNAUTHORISED, status=401)
    response["WWW-Authenticate"] = 'Bearer realm="nutrisho"'
    return response


def _recipe_id(raw: str) -> UUID | None:
    """`raw` as a version 7 UUID, or None when it is not one."""
    try:
        parsed = UUID(raw)
    except ValueError:
        return None
    return parsed if parsed.version == _UUID_VERSION else None


def _error(message: str, *, status: int) -> JsonResponse:
    return JsonResponse({"error": message}, status=status)


@login_not_required
@csrf_exempt
@require_POST
def api_recipes(request: HttpRequest) -> JsonResponse:
    """Create recipes from a JSON body: schema.org Recipe JSON-LD, or a Nutrisho document.

    `?id=<uuid>` (#158) names the id of a body's one recipe, made by the client
    when its draft started. If the key's user already has that recipe, live or
    in the trash, nothing is written and the 200 reply names it, so a save sent
    twice makes one recipe; another user's id is a 409.

    201 lists each new recipe's id, name, page and whether it was renamed or
    went to the trash, with any warnings; 400 says why the body or the id cannot
    be read, 401 that the token is missing or wrong, 413 that the body is too
    large.
    """
    user = _key_user(request)
    if user is None:
        return _unauthorised()
    recipe_id = None
    if "id" in request.GET:
        recipe_id = _recipe_id(request.GET["id"])
        if recipe_id is None:
            return _error(_BAD_ID, status=400)
    try:
        batch = parse_json(request.body)
        result = import_recipes(owner=user, batch=batch, recipe_id=recipe_id)
    except RequestDataTooBig:
        return _error("The request body is too large.", status=413)
    except ImportFormatError as exc:
        return _error(str(exc), status=400)
    except RecipeIdTakenError:
        return _error(_ID_TAKEN, status=409)
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
    status = 200 if all(imported.existed for imported in result.recipes) else 201
    return JsonResponse({"recipes": recipes, "warnings": result.warnings}, status=status)


@login_not_required
@require_GET
def api_vocabulary(request: HttpRequest) -> JsonResponse:
    """The names the key's user can use in a recipe, and the length each field may have.

    The clipper loads this each time its sidebar opens (`services/vocabulary.py`);
    401 without a valid key.
    """
    user = _key_user(request)
    if user is None:
        return _unauthorised()
    return JsonResponse(vocabulary(owner=user))
