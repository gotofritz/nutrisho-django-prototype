from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from django.views.decorators.vary import vary_on_headers

from recipes.forms.field_forms import RecipeMetadataForm
from recipes.models import Cuisine, IngredientInRecipe, Recipe
from recipes.views._types import AuthedRequest


@require_http_methods(["GET", "POST"])
def recipe_new(request: AuthedRequest) -> HttpResponse:
    if request.method == "POST":
        form = RecipeMetadataForm(data=request.POST)
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
            if request.htmx:  # type: ignore[attr-defined]  # django-htmx middleware
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
        {"form": RecipeMetadataForm(), "all_cuisines": _cuisine_names()},
    )


def _is_panel_request(request: AuthedRequest) -> bool:
    """True for HTMX panel swaps; boosted navigation wants the full page."""
    return bool(request.htmx) and not request.htmx.boosted  # type: ignore[attr-defined]  # django-htmx middleware


@vary_on_headers("HX-Request", "HX-Boosted")
@require_http_methods(["GET", "POST"])
def recipe_metadata_edit(request: AuthedRequest, recipe_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    if request.method == "POST":
        form = RecipeMetadataForm(data=request.POST, instance=recipe)
        if form.is_valid():
            try:
                with transaction.atomic():
                    locked = list(
                        Recipe.objects.filter(pk=recipe.pk).select_for_update().values("pk")
                    )
                    if not locked:
                        return HttpResponse("", status=404)
                    form.save(commit=False)
                    form.resolve_pending_cuisine(recipe)
                    recipe.save(
                        update_fields=[
                            "recipe_name",
                            "short_description",
                            "servings",
                            "source_instance",
                            "cuisine",
                        ]
                    )
            except IntegrityError:
                form.add_error("recipe_name", "You already have a recipe with that name.")
            else:
                if request.htmx:  # type: ignore[attr-defined]  # django-htmx middleware
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
    form = RecipeMetadataForm(instance=recipe)
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
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    return render(
        request,
        "recipes/partials/_delete_confirm_panel.html",
        {"recipe": recipe},
    )


@require_POST
def recipe_delete(request: AuthedRequest, recipe_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    recipe.delete()
    if request.htmx:  # type: ignore[attr-defined]  # django-htmx middleware
        target = request.htmx.target or ""  # type: ignore[attr-defined]  # django-htmx middleware
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
    original = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    with transaction.atomic():
        # Phase 1: allocate a unique name (retryable on owner/name collision only)
        n: int | None = None
        while True:
            copy_name = _copy_name(original.recipe_name, n)
            try:
                with transaction.atomic():
                    new = Recipe.objects.create(
                        recipe_name=copy_name,
                        owner=original.owner,
                        short_description=original.short_description,
                        source=original.source,
                        source_instance=original.source_instance,
                        cuisine=original.cuisine,
                        servings=original.servings,
                    )
            except IntegrityError:
                n = 2 if n is None else n + 1
                continue
            break
        # Phase 2: copy children — IntegrityErrors propagate, not retried
        for step in original.step.order_by("index_in_sequence"):
            new.step.create(
                step_text=step.step_text,
                index_in_sequence=step.index_in_sequence,
                duration=step.duration,
                extra_info=step.extra_info,
            )
        for group in original.ingredients_group.order_by("index_in_sequence"):
            new_group = new.ingredients_group.create(
                group_name=group.group_name,
                index_in_sequence=group.index_in_sequence,
            )
            for iir in IngredientInRecipe.objects.filter(ingredient_group=group).order_by(
                "index_in_sequence"
            ):
                IngredientInRecipe.objects.create(
                    ingredient=iir.ingredient,
                    substitute=iir.substitute,
                    unit=iir.unit,
                    preparation=iir.preparation,
                    quantity=iir.quantity,
                    ingredient_group=new_group,
                    index_in_sequence=iir.index_in_sequence,
                    note=iir.note,
                )
        for tag in original.tag.all():
            tag.recipe.add(new)
    if request.htmx:  # type: ignore[attr-defined]  # django-htmx middleware
        response = HttpResponse()
        response["HX-Redirect"] = new.get_absolute_url()
        return response
    return redirect(new.get_absolute_url())


@require_GET
def recipe_scale_panel(request: AuthedRequest, recipe_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    return render(request, "recipes/partials/_scale_panel.html", {"recipe": recipe})


# Model field limits: Recipe.servings is a PositiveSmallIntegerField,
# IngredientInRecipe.quantity is DecimalField(max_digits=7, decimal_places=2).
_MAX_SERVINGS = 32767
_MAX_QUANTITY = Decimal("99999.99")


def _scale_error(request: AuthedRequest, recipe: Recipe, msg: str) -> HttpResponse:
    return render(
        request,
        "recipes/partials/_scale_panel.html",
        {"recipe": recipe, "error": msg},
        status=422,
    )


@require_POST
def recipe_scale(request: AuthedRequest, recipe_id: int) -> HttpResponse:
    try:
        multiplier = Decimal(request.POST.get("multiplier", ""))
        if multiplier <= 0:
            raise ValueError
    except InvalidOperation, ValueError:
        recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
        return _scale_error(request, recipe, "Enter a positive number.")

    with transaction.atomic():
        recipe = get_object_or_404(
            Recipe.objects.select_for_update(), id=recipe_id, owner=request.user
        )

        old_serves = Decimal(recipe.servings)
        try:
            new_serves = max(
                1,
                int((old_serves * multiplier).quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
            )
        except InvalidOperation:
            return _scale_error(request, recipe, "Result would exceed the maximum serving count.")
        if new_serves > _MAX_SERVINGS:
            return _scale_error(request, recipe, "Result would exceed the maximum serving count.")

        # Validate every scaled quantity before writing anything
        scaled = list(
            IngredientInRecipe.objects.select_for_update().filter(
                ingredient_group__recipe=recipe, quantity__isnull=False
            )
        )
        for iir in scaled:
            try:
                new_quantity = (iir.quantity * multiplier).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )  # type: ignore[operator]
            except InvalidOperation:
                return _scale_error(
                    request, recipe, "Multiplier would overflow an ingredient quantity."
                )
            if new_quantity > _MAX_QUANTITY:
                return _scale_error(
                    request, recipe, "Multiplier would overflow an ingredient quantity."
                )
            iir.quantity = new_quantity

        IngredientInRecipe.objects.bulk_update(scaled, ["quantity"])
        recipe.servings = new_serves
        recipe.save(update_fields=["servings"])

    if request.htmx:  # type: ignore[attr-defined]  # django-htmx middleware
        response = HttpResponse()
        response["HX-Redirect"] = recipe.get_absolute_url()
        return response
    return redirect(recipe.get_absolute_url())


_NAME_MAX = 200


def _copy_name(base: str, n: int | None = None) -> str:
    """Build a copy name: 'Base Copy', 'Base Copy 2', 'Base Copy 3', …"""
    suffix = f" Copy {n}" if n is not None else " Copy"
    return f"{base[: _NAME_MAX - len(suffix)]}{suffix}"


def _cuisine_names() -> list[str]:
    return list(Cuisine.objects.values_list("cuisine", flat=True).order_by("cuisine"))
