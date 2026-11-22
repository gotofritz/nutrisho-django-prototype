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

Hardened for a route anything can call (#149): an expired key is a 401 with
`code: token_expired`, too many requests a 429 with `Retry-After`
(`services/api_limits.py`), a save that is not JSON a 415, and one with too
many recipes or new names a 413. Each refusal the clipper must tell apart
carries a `code`.
"""

from collections.abc import Callable
from functools import wraps
from uuid import UUID

from django.conf import settings
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.models import AbstractBaseUser
from django.core.exceptions import RequestDataTooBig
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from recipes.services.api_limits import new_name_count, note, wait_for
from recipes.services.api_tokens import TokenExpiredError, bearer_key, user_for_key
from recipes.services.recipe_document import ImportFormatError, parse_json
from recipes.services.recipe_import import RecipeIdTakenError, import_recipes
from recipes.services.vocabulary import vocabulary

_UNAUTHORISED = "Send a valid API token as “Authorization: Bearer <token>”."
_EXPIRED = "This API token has expired: make a new one."
_NOT_JSON = "Send the recipe as JSON, with “Content-Type: application/json”."
_TOO_MANY_REQUESTS = "Too many requests: wait a minute and try again."
_JSON_TYPES = frozenset({"application/json", "application/ld+json"})
_BAD_ID = "“id” must be a version 7 UUID."
# Says nothing of whose recipe holds the id, or whether it is live.
_ID_TAKEN = "That id is taken: make a new one for this recipe."
_UUID_VERSION = 7  # sorts by age, which the export, search and the trash rely on (#156)


def _unauthorised() -> JsonResponse:
    response = _error(_UNAUTHORISED, status=401)
    response["WWW-Authenticate"] = 'Bearer realm="nutrisho"'
    return response


def _expired() -> JsonResponse:
    response = _error(_EXPIRED, status=401, code="token_expired")
    response["WWW-Authenticate"] = (
        'Bearer realm="nutrisho", error="invalid_token", error_description="The token has expired"'
    )
    return response


def _too_many(wait: int) -> JsonResponse:
    response = _error(_TOO_MANY_REQUESTS, status=429, code="rate_limited")
    response["Retry-After"] = str(wait)
    return response


type _KeyedView = Callable[[HttpRequest, AbstractBaseUser], JsonResponse]


def _signed_in_by_key(view: _KeyedView) -> Callable[[HttpRequest], JsonResponse]:
    """Sign the request in by its API key, never the session, within the rate limits.

    An address past its failed sign-ins waits, even with a right key; a wrong
    or expired key counts as one. A key past its requests a minute waits.
    """

    @wraps(view)
    def keyed(request: HttpRequest) -> JsonResponse:
        address = request.META.get("REMOTE_ADDR", "")
        wait = wait_for("failed", address, limit=settings.API_FAILED_KEYS_PER_MINUTE)
        if wait is not None:
            return _too_many(wait)
        key = bearer_key(request.headers.get("Authorization", ""))
        try:
            user = user_for_key(key)
        except TokenExpiredError:
            note("failed", address)
            return _expired()
        if user is None:
            note("failed", address)
            return _unauthorised()
        wait = wait_for("key", str(user.pk), limit=settings.API_REQUESTS_PER_MINUTE)
        if wait is not None:
            return _too_many(wait)
        note("key", str(user.pk))
        return view(request, user)

    return keyed


def _recipe_id(raw: str) -> UUID | None:
    """`raw` as a version 7 UUID, or None when it is not one."""
    try:
        parsed = UUID(raw)
    except ValueError:
        return None
    return parsed if parsed.version == _UUID_VERSION else None


def _error(message: str, *, status: int, code: str = "") -> JsonResponse:
    body = {"error": message} | ({"code": code} if code else {})
    return JsonResponse(body, status=status)


@login_not_required
@csrf_exempt
@require_POST
@_signed_in_by_key
def api_recipes(request: HttpRequest, user: AbstractBaseUser) -> JsonResponse:
    """Create recipes from a JSON body: schema.org Recipe JSON-LD, or a Nutrisho document.

    `?id=<uuid>` (#158) names the id of a body's one recipe, made by the client
    when its draft started. If the key's user already has that recipe, live or
    in the trash, nothing is written and the 200 reply names it, so a save sent
    twice makes one recipe; another user's id is a 409.

    201 lists each new recipe's id, name, page and whether it was renamed or
    went to the trash, with any warnings; 400 says why the body or the id cannot
    be read, 401 that the token is missing, wrong or expired, 413 that the
    body, its recipes or the names it would make are too many, 415 that it is
    not JSON, and 429 to wait.
    """
    if request.content_type not in _JSON_TYPES:
        return _error(_NOT_JSON, status=415, code="unsupported_media_type")
    recipe_id = None
    if "id" in request.GET:
        recipe_id = _recipe_id(request.GET["id"])
        if recipe_id is None:
            return _error(_BAD_ID, status=400)
    try:
        batch = parse_json(request.body)
        refused = _over_the_caps(batch, owner=user)
        if refused is not None:
            return refused
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


def _over_the_caps(batch, *, owner: AbstractBaseUser) -> JsonResponse | None:
    """A 413 when the save brings too many recipes or would make too many names; else None."""
    recipes, limit = len(batch.recipes), settings.API_MAX_RECIPES
    if recipes > limit:
        message = f"One request may bring at most {limit} recipes; this one has {recipes}."
        return _error(message, status=413, code="too_many_recipes")
    names, limit = new_name_count(batch, owner=owner), settings.API_MAX_NEW_NAMES
    if names > limit:
        message = f"One request may make at most {limit} new names; this one would make {names}."
        return _error(message, status=413, code="too_many_new_names")
    return None


@login_not_required
@require_GET
@_signed_in_by_key
def api_vocabulary(request: HttpRequest, user: AbstractBaseUser) -> JsonResponse:  # noqa: ARG001 - the key's user is what matters
    """The names the key's user can use in a recipe, and the length each field may have.

    The clipper loads this each time its sidebar opens (`services/vocabulary.py`);
    401 without a valid key, as for a save, and 429 to wait.
    """
    return JsonResponse(vocabulary(owner=user))
