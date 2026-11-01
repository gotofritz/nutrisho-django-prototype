from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from django.views.decorators.vary import vary_on_headers

from recipes.forms.field_forms import RecipeMetadataForm
from recipes.models import Recipe
from recipes.services.name_resolution import cuisine_paths
from recipes.services.recipe_duplication import duplicate_recipe
from recipes.services.recipe_scaling import ScaleError, save_scaled_copy
from recipes.utils.scaling import MAX_SERVINGS, parse_servings
from recipes.views._types import AuthedRequest


@require_http_methods(["GET", "POST"])
def recipe_new(request: AuthedRequest) -> HttpResponse:
    """Create a recipe."""
    if request.method == "POST":
        form = RecipeMetadataForm(data=request.POST, owner=request.user)
        if form.is_valid():
            form.instance.owner = request.user
            try:
                recipe = form.save()
            except IntegrityError:
                form.add_error("recipe_name", "You already have a recipe with that name.")
                return render(
                    request,
                    "recipes/recipe_new.html",
                    {"form": form, "all_cuisines": _cuisine_names()},
                )
            if request.htmx:
                response = HttpResponse()
                response["HX-Redirect"] = recipe.get_absolute_url()
                return response
            return redirect(recipe.get_absolute_url())
        return render(
            request, "recipes/recipe_new.html", {"form": form, "all_cuisines": _cuisine_names()}
        )
    return render(
        request,
        "recipes/recipe_new.html",
        {"form": RecipeMetadataForm(owner=request.user), "all_cuisines": _cuisine_names()},
    )


def _is_panel_request(request: AuthedRequest) -> bool:
    """True for HTMX panel swaps; boosted navigation wants the full page."""
    return bool(request.htmx) and not request.htmx.boosted


@vary_on_headers("HX-Request", "HX-Boosted")
@require_http_methods(["GET", "POST"])
def recipe_metadata_edit(request: AuthedRequest, recipe_id: int) -> HttpResponse:
    """Edit recipe metadata."""
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    if request.method == "POST":
        form = RecipeMetadataForm(data=request.POST, instance=recipe, owner=recipe.owner)
        if form.is_valid():
            try:
                with transaction.atomic():
                    locked = list(
                        Recipe.objects.filter(pk=recipe.pk).select_for_update().values("pk")
                    )
                    if not locked:
                        return HttpResponse("", status=404)
                    form.save(commit=False)
                    recipe.save(
                        update_fields=[
                            "recipe_name",
                            "short_description",
                            "servings",
                            "source_instance",
                            "cuisine",
                        ]
                    )
                    form.save_tags(recipe)
            except IntegrityError:
                form.add_error("recipe_name", "You already have a recipe with that name.")
            else:
                if request.htmx:
                    response = HttpResponse()
                    response["HX-Redirect"] = recipe.get_absolute_url()
                    return response
                return redirect(recipe.get_absolute_url())
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
    form = RecipeMetadataForm(instance=recipe, owner=recipe.owner)
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
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    return render(
        request,
        "recipes/partials/_delete_confirm_panel.html",
        {"recipe": recipe},
    )


@require_POST
def recipe_delete(request: AuthedRequest, recipe_id: int) -> HttpResponse:
    """Delete a recipe."""
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    recipe.delete()
    if request.htmx:
        target = request.htmx.target or ""
        if target.startswith("recipe-"):
            # List page: replace row or swap in empty state when last recipe gone.
            if not Recipe.objects.filter(owner=request.user).exists():
                response = render(request, "recipes/partials/_recipe_list_empty.html")
                response["HX-Retarget"] = "#recipe-list"
                response["HX-Reswap"] = "outerHTML"
                return response
            return HttpResponse("")
        # Detail page: compute redirect after deletion so it reflects current state.
        response = HttpResponse("")
        response["HX-Redirect"] = _next_recipe_url(recipe_id, request.user)
        return response
    return redirect("/recipes/")


def _next_recipe_url(deleted_id: int, user) -> str:
    qs = Recipe.objects.filter(owner=user)
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
    original = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    new = duplicate_recipe(original)
    if request.htmx:
        response = HttpResponse()
        response["HX-Redirect"] = new.get_absolute_url()
        return response
    return redirect(new.get_absolute_url())


@require_GET
def recipe_scale_panel(request: AuthedRequest, recipe_id: int) -> HttpResponse:
    """Show the scale panel, starting from the page's serving count."""
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
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
    original = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
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
    if request.htmx:
        response = HttpResponse()
        response["HX-Redirect"] = copy.get_absolute_url()
        return response
    return redirect(copy.get_absolute_url())


def _cuisine_names() -> list[str]:
    return cuisine_paths()
