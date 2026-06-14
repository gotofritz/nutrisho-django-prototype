from django.db import transaction
from django.db.models import Max
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET, require_POST

from recipes.forms.ingredient_forms import IngredientGroupForm, IngredientInRecipeForm
from recipes.models import Ingredient, IngredientGroup, IngredientInRecipe, Recipe
from recipes.utils.sequencing import insert_at_index, move_in_sequence, remove_and_compact
from recipes.views._types import AuthedRequest


def _reassign_select_oob(recipe: Recipe, request: AuthedRequest) -> str:
    """OOB fragment that keeps the reassign <select> in sync after group mutations."""
    return render_to_string(
        "recipes/partials/_reassign_select_oob.html", {"recipe": recipe}, request=request
    )


@require_GET
def recipe_ingredient_display(request: AuthedRequest, recipe_id: int, iir_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    iir = get_object_or_404(IngredientInRecipe, id=iir_id, ingredient_group__recipe=recipe)
    return render(
        request,
        "recipes/partials/_ingredient_display.html",
        {"recipe": recipe, "iir": iir},
    )


def _all_ingredient_names() -> list[str]:
    return list(
        Ingredient.objects.values_list("ingredient_name", flat=True).order_by("ingredient_name")
    )


@require_GET
def recipe_ingredient_edit(request: AuthedRequest, recipe_id: int, iir_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    iir = get_object_or_404(IngredientInRecipe, id=iir_id, ingredient_group__recipe=recipe)
    form = IngredientInRecipeForm(instance=iir)
    return render(
        request,
        "recipes/partials/_ingredient_edit.html",
        {"recipe": recipe, "iir": iir, "form": form, "all_ingredients": _all_ingredient_names()},
    )


@require_POST
def recipe_ingredient_save(request: AuthedRequest, recipe_id: int, iir_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    iir = get_object_or_404(IngredientInRecipe, id=iir_id, ingredient_group__recipe=recipe)
    form = IngredientInRecipeForm(data=request.POST, instance=iir)
    if form.is_valid():
        form.save()
        iir.refresh_from_db()
        return render(
            request,
            "recipes/partials/_ingredient_display.html",
            {"recipe": recipe, "iir": iir},
        )
    return render(
        request,
        "recipes/partials/_ingredient_edit.html",
        {"recipe": recipe, "iir": iir, "form": form, "all_ingredients": _all_ingredient_names()},
    )


@require_POST
def recipe_ingredient_delete(request: AuthedRequest, recipe_id: int, iir_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    iir = get_object_or_404(IngredientInRecipe, id=iir_id, ingredient_group__recipe=recipe)
    remove_and_compact(
        siblings=IngredientInRecipe.objects.filter(ingredient_group=iir.ingredient_group),
        instance=iir,
    )
    return HttpResponse("")


@require_POST
def recipe_ingredient_add(request: AuthedRequest, recipe_id: int, group_id: int) -> HttpResponse:
    """Render a blank ingredient form; no row is created until create succeeds."""
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    group = get_object_or_404(IngredientGroup, id=group_id, recipe=recipe)
    return render(
        request,
        "recipes/partials/_ingredient_edit.html",
        {
            "recipe": recipe,
            "group": group,
            "iir": None,
            "form": IngredientInRecipeForm(),
            "all_ingredients": _all_ingredient_names(),
        },
    )


@require_POST
def recipe_ingredient_create(request: AuthedRequest, recipe_id: int, group_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    group = get_object_or_404(IngredientGroup, id=group_id, recipe=recipe)
    form = IngredientInRecipeForm(data=request.POST)
    if form.is_valid():
        with transaction.atomic():
            name = form.cleaned_data["ingredient_name"].strip()
            ingredient, _ = Ingredient.objects.get_or_create(ingredient_name=name)
            iir = form.save(commit=False)
            iir.ingredient = ingredient
            iir.ingredient_group = group
            insert_at_index(
                siblings=IngredientInRecipe.objects.filter(ingredient_group=group),
                instance=iir,
                requested_index=request.POST.get("position"),
                lock_parent=IngredientGroup.objects.filter(pk=group.pk),
            )
        return render(
            request,
            "recipes/partials/_ingredient_display.html",
            {"recipe": recipe, "iir": iir},
        )
    return render(
        request,
        "recipes/partials/_ingredient_edit.html",
        {
            "recipe": recipe,
            "group": group,
            "iir": None,
            "form": form,
            "all_ingredients": _all_ingredient_names(),
        },
    )


@require_POST
def recipe_ingredient_move_up(request: AuthedRequest, recipe_id: int, iir_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    iir = get_object_or_404(IngredientInRecipe, id=iir_id, ingredient_group__recipe=recipe)
    group = iir.ingredient_group
    move_in_sequence(
        siblings=IngredientInRecipe.objects.filter(ingredient_group=group),
        instance=iir,
        direction="up",
    )
    return render(request, "recipes/partials/_iir_list.html", {"recipe": recipe, "group": group})


@require_POST
def recipe_ingredient_move_down(
    request: AuthedRequest, recipe_id: int, iir_id: int
) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    iir = get_object_or_404(IngredientInRecipe, id=iir_id, ingredient_group__recipe=recipe)
    group = iir.ingredient_group
    move_in_sequence(
        siblings=IngredientInRecipe.objects.filter(ingredient_group=group),
        instance=iir,
        direction="down",
    )
    return render(request, "recipes/partials/_iir_list.html", {"recipe": recipe, "group": group})


@require_GET
def recipe_group_display(request: AuthedRequest, recipe_id: int, group_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    group = get_object_or_404(IngredientGroup, id=group_id, recipe=recipe)
    return render(
        request,
        "recipes/partials/_group_display.html",
        {"recipe": recipe, "group": group},
    )


@require_GET
def recipe_group_edit(request: AuthedRequest, recipe_id: int, group_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    group = get_object_or_404(IngredientGroup, id=group_id, recipe=recipe)
    form = IngredientGroupForm(instance=group)
    return render(
        request,
        "recipes/partials/_group_edit.html",
        {"recipe": recipe, "group": group, "form": form},
    )


@require_POST
def recipe_group_save(request: AuthedRequest, recipe_id: int, group_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    group = get_object_or_404(IngredientGroup, id=group_id, recipe=recipe)
    group_count = IngredientGroup.objects.filter(recipe=recipe).count()
    form = IngredientGroupForm(data=request.POST, instance=group, group_count=group_count)
    if form.is_valid():
        form.save()
        group.refresh_from_db()
        content = render_to_string(
            "recipes/partials/_group_display.html",
            {"recipe": recipe, "group": group},
            request=request,
        )
        return HttpResponse(content + _reassign_select_oob(recipe, request))
    return render(
        request,
        "recipes/partials/_group_edit.html",
        {"recipe": recipe, "group": group, "form": form},
    )


@require_POST
def recipe_group_delete(request: AuthedRequest, recipe_id: int, group_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    group = get_object_or_404(IngredientGroup, id=group_id, recipe=recipe)
    remove_and_compact(siblings=IngredientGroup.objects.filter(recipe=recipe), instance=group)
    return HttpResponse(_reassign_select_oob(recipe, request))


@require_POST
def recipe_group_move_up(request: AuthedRequest, recipe_id: int, group_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    group = get_object_or_404(IngredientGroup, id=group_id, recipe=recipe)
    move_in_sequence(
        siblings=IngredientGroup.objects.filter(recipe=recipe), instance=group, direction="up"
    )
    return render(request, "recipes/partials/_groups_list.html", {"recipe": recipe})


@require_POST
def recipe_group_move_down(request: AuthedRequest, recipe_id: int, group_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    group = get_object_or_404(IngredientGroup, id=group_id, recipe=recipe)
    move_in_sequence(
        siblings=IngredientGroup.objects.filter(recipe=recipe), instance=group, direction="down"
    )
    return render(request, "recipes/partials/_groups_list.html", {"recipe": recipe})


@require_POST
def recipe_group_add(request: AuthedRequest, recipe_id: int) -> HttpResponse:
    """Render a blank group form; no row is created until create succeeds."""
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    return render(
        request,
        "recipes/partials/_group_edit.html",
        {"recipe": recipe, "group": None, "form": IngredientGroupForm()},
    )


@require_POST
def recipe_group_create(request: AuthedRequest, recipe_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    with transaction.atomic():
        list(Recipe.objects.filter(pk=recipe.pk).select_for_update().values("pk"))
        existing_count = IngredientGroup.objects.filter(recipe=recipe).count()
        form = IngredientGroupForm(data=request.POST, group_count=existing_count + 1)
        if form.is_valid():
            group = form.save(commit=False)
            group.recipe = recipe
            insert_at_index(
                siblings=IngredientGroup.objects.filter(recipe=recipe),
                instance=group,
                requested_index=request.POST.get("position"),
                lock_parent=None,
            )
            content = render_to_string(
                "recipes/partials/_group_block.html",
                {"recipe": recipe, "group": group},
                request=request,
            )
            return HttpResponse(content + _reassign_select_oob(recipe, request))
    return render(
        request,
        "recipes/partials/_group_edit.html",
        {"recipe": recipe, "group": None, "form": form},
    )


@require_POST
def recipe_ingredient_reassign(request: AuthedRequest, recipe_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    raw_ids = request.POST.getlist("ingredient_ids")

    if not raw_ids:
        return render(request, "recipes/partials/_groups_list.html", {"recipe": recipe})

    try:
        ingredient_ids = [int(i) for i in raw_ids]
    except (ValueError, TypeError):
        return render(
            request,
            "recipes/partials/_groups_list.html",
            {"recipe": recipe, "error": "Invalid ingredient IDs."},
            status=422,
        )

    target_group_id = request.POST.get("target_group", "")
    is_new_group = target_group_id == "new"
    if not is_new_group:
        try:
            group_pk = int(target_group_id)
        except (ValueError, TypeError):
            return render(
                request,
                "recipes/partials/_groups_list.html",
                {"recipe": recipe, "error": "Invalid group."},
                status=422,
            )
        target_group = IngredientGroup.objects.filter(id=group_pk, recipe=recipe).first()
        if target_group is None:
            return render(
                request,
                "recipes/partials/_groups_list.html",
                {"recipe": recipe, "error": "Invalid group."},
                status=422,
            )

    # Visual page order: group order first, then row order within the group
    iirs = list(
        IngredientInRecipe.objects.filter(id__in=ingredient_ids, ingredient_group__recipe=recipe)
        .select_related("ingredient_group")
        .order_by("ingredient_group__index_in_sequence", "index_in_sequence")
    )

    if not iirs:
        return render(request, "recipes/partials/_groups_list.html", {"recipe": recipe})

    if not is_new_group and all(iir.ingredient_group_id == target_group.id for iir in iirs):
        # Everything already lives in the target group — moving would only
        # reorder rows to the end, so do nothing.
        return render(request, "recipes/partials/_groups_list.html", {"recipe": recipe})

    with transaction.atomic():
        if is_new_group:
            # Lock the recipe row before reading count so concurrent blank-group
            # creates serialize rather than both validating against a stale count.
            list(Recipe.objects.filter(pk=recipe.pk).select_for_update().values("pk"))
            existing_count = IngredientGroup.objects.filter(recipe=recipe).count()
            form = IngredientGroupForm(
                data={"group_name": request.POST.get("new_group_name", "")},
                group_count=existing_count + 1,
            )
            if not form.is_valid():
                return render(
                    request,
                    "recipes/partials/_groups_list.html",
                    {"recipe": recipe, "error": "Group name is required."},
                    status=422,
                )
            agg = IngredientGroup.objects.filter(recipe=recipe).aggregate(Max("index_in_sequence"))
            last = agg["index_in_sequence__max"]
            target_group = form.save(commit=False)
            target_group.recipe = recipe
            target_group.index_in_sequence = (last + 1) if last is not None else 0
            target_group.save()
        else:
            # Lock recipe and re-fetch target group so concurrent deletes/reorders are visible.
            list(Recipe.objects.filter(pk=recipe.pk).select_for_update().values("pk"))
            target_group = (
                IngredientGroup.objects.select_for_update()
                .filter(id=group_pk, recipe=recipe)
                .first()
            )
            if target_group is None:
                return render(
                    request,
                    "recipes/partials/_groups_list.html",
                    {"recipe": recipe, "error": "Invalid group."},
                    status=422,
                )

        affected_old_group_ids = {
            iir.ingredient_group_id for iir in iirs if iir.ingredient_group_id != target_group.id
        }
        iir_ids = [iir.id for iir in iirs]
        all_group_ids = affected_old_group_ids | {target_group.id}

        # Lock all sibling rows in every affected group before reading or writing
        # so concurrent reassign/move requests serialize rather than racing.
        list(
            IngredientInRecipe.objects.filter(ingredient_group_id__in=all_group_ids)
            .select_for_update()
            .values("pk")
            .order_by("ingredient_group_id", "index_in_sequence")
        )

        # Existing items in the target group that are NOT being moved
        existing_target = list(
            IngredientInRecipe.objects.filter(ingredient_group=target_group)
            .exclude(id__in=iir_ids)
            .order_by("index_in_sequence")
        )

        # Merge moved + existing target by original page order so visual position is preserved:
        # sort key = (group.index_in_sequence, item.index_in_sequence) before this operation.
        target_group_index = target_group.index_in_sequence
        combined: list[tuple[int, int, IngredientInRecipe]] = []
        for item in iirs:
            combined.append((item.ingredient_group.index_in_sequence, item.index_in_sequence, item))
        for item in existing_target:
            combined.append((target_group_index, item.index_in_sequence, item))
        combined.sort(key=lambda x: (x[0], x[1]))
        final_order = [x[2] for x in combined]

        # Park ALL items destined for target_group at temp indexes to free their
        # current positions before writing the merged final order.
        all_target_items = iirs + existing_target
        for i, item in enumerate(all_target_items):
            item.ingredient_group = target_group
            item.index_in_sequence = 10000 + i
            item.save()

        # Compact non-moved items in source groups (target is rewritten fully below)
        for group_id in affected_old_group_ids:
            remaining = list(
                IngredientInRecipe.objects.filter(ingredient_group_id=group_id).order_by(
                    "index_in_sequence"
                )
            )
            for i, r in enumerate(remaining):
                if r.index_in_sequence != i:
                    r.index_in_sequence = i
                    r.save()

        # Write final merged order into the target group
        for i, item in enumerate(final_order):
            item.index_in_sequence = i
            item.save()

    return render(request, "recipes/partials/_groups_list.html", {"recipe": recipe})
