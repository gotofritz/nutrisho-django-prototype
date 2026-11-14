from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from django.views.decorators.vary import vary_on_headers

from recipes.forms.field_forms import RecipeMetadataForm
from recipes.models import Recipe
from recipes.services.name_resolution import cuisine_paths
from recipes.services.recipe_duplication import duplicate_recipe
from recipes.services.recipe_metadata import DuplicateRecipeNameError, create_recipe, save_metadata
from recipes.services.recipe_scaling import ScaleError, save_scaled_copy
from recipes.services.recipe_trash import trash_recipe
from recipes.utils.scaling import MAX_SERVINGS, parse_servings
from recipes.views._auth import owned_recipe
from recipes.views._types import AuthedRequest


def _redirect_to(request: AuthedRequest, recipe: Recipe) -> HttpResponse:
    """Go to `recipe`'s page: HX-Redirect for htmx, a plain redirect otherwise."""
    if request.htmx:
        response = HttpResponse()
        response["HX-Redirect"] = recipe.get_absolute_url()
        return response
    return redirect(recipe.get_absolute_url())


@require_http_methods(["GET", "POST"])
def recipe_new(request: AuthedRequest) -> HttpResponse:
    """Create a recipe."""
    form = RecipeMetadataForm(owner=request.user)
    if request.method == "POST":
        form = RecipeMetadataForm(data=request.POST, owner=request.user)
        if form.is_valid():
            try:
                recipe = create_recipe(
                    owner=request.user,
                    recipe=form.save(commit=False),
                    tag_names=form.cleaned_data["tags"],
                )
            except DuplicateRecipeNameError as exc:
                form.add_error("recipe_name", str(exc))
            else:
                return _redirect_to(request, recipe)
    return render(
        request, "recipes/recipe_new.html", {"form": form, "all_cuisines": _cuisine_names()}
    )


def _is_panel_request(request: AuthedRequest) -> bool:
    """True for HTMX panel swaps; boosted navigation wants the full page."""
    return bool(request.htmx) and not request.htmx.boosted


@vary_on_headers("HX-Request", "HX-Boosted")
@require_http_methods(["GET", "POST"])
def recipe_metadata_edit(request: AuthedRequest, recipe_id: int) -> HttpResponse:
    """Edit recipe metadata."""
    recipe = owned_recipe(request=request, recipe_id=recipe_id)
    form = RecipeMetadataForm(instance=recipe, owner=recipe.owner)
    if request.method == "POST":
        form = RecipeMetadataForm(data=request.POST, instance=recipe, owner=recipe.owner)
        if form.is_valid():
            try:
                save_metadata(recipe=form.save(commit=False), tag_names=form.cleaned_data["tags"])
            except ObjectDoesNotExist:
                return HttpResponse("", status=404)
            except DuplicateRecipeNameError as exc:
                form.add_error("recipe_name", str(exc))
            else:
                return _redirect_to(request, recipe)
    template = (
        "recipes/partials/_metadata_panel.html"
        if _is_panel_request(request)
        else "recipes/recipe_metadata.html"
    )
    return render(
        request,
        template,
        {"recipe": recipe, "form": form, "all_cuisines": _cuisine_names()},
    )


@require_GET
def recipe_delete_panel(request: AuthedRequest, recipe_id: int) -> HttpResponse:
    """Show the delete confirmation panel."""
    recipe = owned_recipe(request=request, recipe_id=recipe_id)
    return render(
        request,
        "recipes/partials/_delete_confirm_panel.html",
        {"recipe": recipe},
    )


@require_POST
def recipe_delete(request: AuthedRequest, recipe_id: int) -> HttpResponse:
    """Move a recipe to the trash; the next page offers Undo (#75)."""
    recipe = owned_recipe(request=request, recipe_id=recipe_id)
    trash_recipe(recipe)
    # The message's extra_tags carry its Undo URL; _page_regions.html posts to it.
    messages.success(
        request,
        f"Deleted “{recipe.plain_name}”.",
        extra_tags=reverse("recipes:restore", kwargs={"recipe_id": recipe_id}),
    )
    if request.htmx:
        # Delete lives on the recipe page only (#75): go on to the next recipe.
        response = HttpResponse("")
        response["HX-Redirect"] = _next_recipe_url(recipe_id, request.user)
        return response
    return redirect("/recipes/")


def _next_recipe_url(deleted_id: int, user) -> str:
    qs = Recipe.objects.live().filter(owner=user)
    nxt = qs.filter(id__gt=deleted_id).order_by("id").first()
    if nxt:
        return nxt.get_absolute_url()
    prev = qs.filter(id__lt=deleted_id).order_by("-id").first()
    if prev:
        return prev.get_absolute_url()
    return "/recipes/"


@require_POST
def recipe_duplicate(request: AuthedRequest, recipe_id: int) -> HttpResponse:
    """Duplicate a recipe."""
    original = owned_recipe(request=request, recipe_id=recipe_id)
    return _redirect_to(request, duplicate_recipe(original))


@require_GET
def recipe_scale_panel(request: AuthedRequest, recipe_id: int) -> HttpResponse:
    """Show the scale panel, starting from the page's serving count."""
    recipe = owned_recipe(request=request, recipe_id=recipe_id)
    return _scale_panel(request, recipe, servings=parse_servings(request.GET.get("servings")))


def _scale_panel(
    request: AuthedRequest,
    recipe: Recipe,
    *,
    servings: int | None,
    error: str = "",
    status: int = 200,
) -> HttpResponse:
    return render(
        request,
        "recipes/partials/_scale_panel.html",
        {
            "recipe": recipe,
            "servings": servings or recipe.servings,
            "max_servings": MAX_SERVINGS,
            "error": error,
        },
        status=status,
    )


@require_POST
def recipe_scale_copy(request: AuthedRequest, recipe_id: int) -> HttpResponse:
    """Save the recipe scaled to `servings` as a new recipe; the original is untouched."""
    original = owned_recipe(request=request, recipe_id=recipe_id)
    servings = parse_servings(request.POST.get("servings"))
    if servings is None:
        return _scale_panel(
            request,
            original,
            servings=None,
            error=f"Enter a whole number of servings from 1 to {MAX_SERVINGS}.",
            status=422,
        )
    try:
        copy = save_scaled_copy(original, servings=servings)
    except ScaleError as exc:
        return _scale_panel(request, original, servings=servings, error=str(exc), status=422)
    return _redirect_to(request, copy)


def _cuisine_names() -> list[str]:
    return cuisine_paths()
