from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from recipes.forms.ingredient_forms import IngredientGroupForm, IngredientInRecipeForm
from recipes.models import Ingredient, IngredientGroup, IngredientInRecipe, Recipe


@require_GET
def recipe_ingredient_display(request: HttpRequest, recipe_id: int, iir_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id)
    iir = get_object_or_404(IngredientInRecipe, id=iir_id, ingredient_group__recipe=recipe)
    return render(
        request,
        "recipes/partials/_ingredient_display.html",
        {"recipe": recipe, "iir": iir},
    )


@require_GET
def recipe_ingredient_edit(request: HttpRequest, recipe_id: int, iir_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id)
    iir = get_object_or_404(IngredientInRecipe, id=iir_id, ingredient_group__recipe=recipe)
    form = IngredientInRecipeForm(instance=iir)
    return render(
        request,
        "recipes/partials/_ingredient_edit.html",
        {"recipe": recipe, "iir": iir, "form": form},
    )


@require_POST
def recipe_ingredient_save(request: HttpRequest, recipe_id: int, iir_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id)
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
        {"recipe": recipe, "iir": iir, "form": form},
    )


@require_POST
def recipe_ingredient_delete(request: HttpRequest, recipe_id: int, iir_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id)
    iir = get_object_or_404(IngredientInRecipe, id=iir_id, ingredient_group__recipe=recipe)
    group = iir.ingredient_group
    deleted_index = iir.index_in_sequence
    iir.delete()
    remaining = IngredientInRecipe.objects.filter(
        ingredient_group=group, index_in_sequence__gt=deleted_index
    ).order_by("index_in_sequence")
    for i in remaining:
        i.index_in_sequence -= 1
        i.save()
    return HttpResponse("")


@require_POST
def recipe_ingredient_add(request: HttpRequest, recipe_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id)
    group = IngredientGroup.objects.filter(recipe=recipe).first()
    if not group:
        group = IngredientGroup.objects.create(recipe=recipe, group_name="", index_in_sequence=0)
    next_index = IngredientInRecipe.objects.filter(ingredient_group=group).count()
    ingredient_name = request.POST.get("ingredient_name", "New ingredient")
    ingredient, _ = Ingredient.objects.get_or_create(ingredient_name=ingredient_name)
    iir = IngredientInRecipe.objects.create(
        ingredient=ingredient,
        ingredient_group=group,
        index_in_sequence=next_index,
    )
    form = IngredientInRecipeForm(instance=iir)
    return render(
        request,
        "recipes/partials/_ingredient_edit.html",
        {"recipe": recipe, "iir": iir, "form": form},
    )


@require_GET
def recipe_group_display(request: HttpRequest, recipe_id: int, group_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id)
    group = get_object_or_404(IngredientGroup, id=group_id, recipe=recipe)
    return render(
        request,
        "recipes/partials/_group_display.html",
        {"recipe": recipe, "group": group},
    )


@require_GET
def recipe_group_edit(request: HttpRequest, recipe_id: int, group_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id)
    group = get_object_or_404(IngredientGroup, id=group_id, recipe=recipe)
    form = IngredientGroupForm(instance=group)
    return render(
        request,
        "recipes/partials/_group_edit.html",
        {"recipe": recipe, "group": group, "form": form},
    )


@require_POST
def recipe_group_save(request: HttpRequest, recipe_id: int, group_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id)
    group = get_object_or_404(IngredientGroup, id=group_id, recipe=recipe)
    form = IngredientGroupForm(data=request.POST, instance=group)
    if form.is_valid():
        form.save()
        return render(
            request,
            "recipes/partials/_group_display.html",
            {"recipe": recipe, "group": group},
        )
    return render(
        request,
        "recipes/partials/_group_edit.html",
        {"recipe": recipe, "group": group, "form": form},
    )


@require_POST
def recipe_group_delete(request: HttpRequest, recipe_id: int, group_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id)
    group = get_object_or_404(IngredientGroup, id=group_id, recipe=recipe)
    deleted_index = group.index_in_sequence
    group.delete()
    remaining = IngredientGroup.objects.filter(
        recipe=recipe, index_in_sequence__gt=deleted_index
    ).order_by("index_in_sequence")
    for g in remaining:
        g.index_in_sequence -= 1
        g.save()
    return HttpResponse("")


@require_POST
def recipe_group_add(request: HttpRequest, recipe_id: int) -> HttpResponse:
    recipe = get_object_or_404(Recipe, id=recipe_id)
    next_index = IngredientGroup.objects.filter(recipe=recipe).count()
    group = IngredientGroup.objects.create(
        recipe=recipe, group_name="", index_in_sequence=next_index
    )
    form = IngredientGroupForm(instance=group)
    return render(
        request,
        "recipes/partials/_group_edit.html",
        {"recipe": recipe, "group": group, "form": form},
    )
