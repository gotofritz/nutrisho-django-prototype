"""The recipes app's routes.

Each view is named through its own module; there is no re-export list to keep
in step. A move route's direction is a fixed `direction` kwarg, so one view
serves both of a pair while the templates keep the `*_move_up` and
`*_move_down` names.
"""

from django.urls import path

from recipes.views import (
    cuisine_admin,
    home,
    ingredient_admin,
    recipe,
    recipe_crud,
    recipe_fields,
    recipe_ingredients,
    recipe_steps,
)
from recipes.views._auth import htmx_staff_required


def _staff(view):
    """Shorthand: signed in and staff; the clean-up tool edits rows every user shares."""
    return htmx_staff_required(view)


app_name = "recipes"
urlpatterns = [
    path("", home.home, name="home"),
    path("new/", recipe_crud.recipe_new, name="new"),
    # Shared-ingredient clean-up tool (Miller columns). The `manage/` prefix keeps
    # these clear of the per-recipe `<recipe_id>/ingredients/...` inline-edit routes.
    path(
        "ingredients/manage/", _staff(ingredient_admin.ingredient_manage), name="ingredient_manage"
    ),
    path(
        "ingredients/manage/search/",
        _staff(ingredient_admin.ingredient_manage_search),
        name="ingredient_manage_search",
    ),
    path(
        "ingredients/manage/recipes/",
        _staff(ingredient_admin.ingredient_manage_recipes),
        name="ingredient_manage_recipes",
    ),
    path(
        "ingredients/manage/preview/<int:recipe_id>/",
        _staff(ingredient_admin.ingredient_manage_preview),
        name="ingredient_manage_preview",
    ),
    path(
        "ingredients/manage/cancel/",
        _staff(ingredient_admin.ingredient_manage_cancel),
        name="ingredient_manage_cancel",
    ),
    path(
        "ingredients/manage/edit/",
        _staff(ingredient_admin.ingredient_manage_edit),
        name="ingredient_manage_edit",
    ),
    path(
        "ingredients/manage/delete/",
        _staff(ingredient_admin.ingredient_manage_delete),
        name="ingredient_manage_delete",
    ),
    path(
        "ingredients/manage/merge/",
        _staff(ingredient_admin.ingredient_manage_merge),
        name="ingredient_manage_merge",
    ),
    path(
        "ingredients/manage/merge-plural/",
        _staff(ingredient_admin.ingredient_manage_merge_plural),
        name="ingredient_manage_merge_plural",
    ),
    path(
        "ingredients/manage/promote/",
        _staff(ingredient_admin.ingredient_manage_promote),
        name="ingredient_manage_promote",
    ),
    path(
        "ingredients/manage/alias/",
        _staff(ingredient_admin.ingredient_manage_alias),
        name="ingredient_manage_alias",
    ),
    path(
        "ingredients/manage/<int:ingredient_id>/save/",
        _staff(ingredient_admin.ingredient_manage_save),
        name="ingredient_manage_save",
    ),
    # Staff cuisine tool: the shared cuisine tree (plan 011).
    path("cuisines/manage/", _staff(cuisine_admin.cuisine_manage), name="cuisine_manage"),
    path(
        "cuisines/manage/columns/",
        _staff(cuisine_admin.cuisine_manage_columns),
        name="cuisine_manage_columns",
    ),
    path(
        "cuisines/manage/add/", _staff(cuisine_admin.cuisine_manage_add), name="cuisine_manage_add"
    ),
    path(
        "cuisines/manage/edit/",
        _staff(cuisine_admin.cuisine_manage_edit),
        name="cuisine_manage_edit",
    ),
    path(
        "cuisines/manage/<int:cuisine_id>/save/",
        _staff(cuisine_admin.cuisine_manage_save),
        name="cuisine_manage_save",
    ),
    path(
        "cuisines/manage/merge/",
        _staff(cuisine_admin.cuisine_manage_merge),
        name="cuisine_manage_merge",
    ),
    path(
        "cuisines/manage/delete/",
        _staff(cuisine_admin.cuisine_manage_delete),
        name="cuisine_manage_delete",
    ),
    path("<int:recipe_id>/", recipe.recipe, name="recipe"),
    path("<int:recipe_id>/delete/", recipe_crud.recipe_delete, name="delete"),
    path("<int:recipe_id>/delete/panel/", recipe_crud.recipe_delete_panel, name="delete_panel"),
    path("<int:recipe_id>/duplicate/", recipe_crud.recipe_duplicate, name="duplicate"),
    path("<int:recipe_id>/metadata/", recipe_crud.recipe_metadata_edit, name="metadata_edit"),
    path("<int:recipe_id>/scale/copy/", recipe_crud.recipe_scale_copy, name="scale_copy"),
    path("<int:recipe_id>/scale/panel/", recipe_crud.recipe_scale_panel, name="scale_panel"),
    # Field inline edit
    path(
        "<int:recipe_id>/field/<str:field_name>/",
        recipe_fields.recipe_field_display,
        name="field_display",
    ),
    path(
        "<int:recipe_id>/field/<str:field_name>/edit/",
        recipe_fields.recipe_field_edit,
        name="field_edit",
    ),
    path(
        "<int:recipe_id>/field/<str:field_name>/save/",
        recipe_fields.recipe_field_save,
        name="field_save",
    ),
    # Steps inline edit
    path("<int:recipe_id>/steps/add/", recipe_steps.recipe_step_add, name="step_add"),
    path("<int:recipe_id>/steps/create/", recipe_steps.recipe_step_create, name="step_create"),
    path("<int:recipe_id>/steps/merge/", recipe_steps.recipe_steps_merge, name="steps_merge"),
    path(
        "<int:recipe_id>/steps/bulk-delete/",
        recipe_steps.recipe_steps_bulk_delete,
        name="steps_bulk_delete",
    ),
    path(
        "<int:recipe_id>/steps/<int:step_id>/",
        recipe_steps.recipe_step_display,
        name="step_display",
    ),
    path(
        "<int:recipe_id>/steps/<int:step_id>/edit/", recipe_steps.recipe_step_edit, name="step_edit"
    ),
    path(
        "<int:recipe_id>/steps/<int:step_id>/save/", recipe_steps.recipe_step_save, name="step_save"
    ),
    path(
        "<int:recipe_id>/steps/<int:step_id>/delete/",
        recipe_steps.recipe_step_delete,
        name="step_delete",
    ),
    path(
        "<int:recipe_id>/steps/<int:step_id>/split/",
        recipe_steps.recipe_step_split,
        name="step_split",
    ),
    path(
        "<int:recipe_id>/steps/<int:step_id>/move-up/",
        recipe_steps.recipe_step_move,
        {"direction": "up"},
        name="step_move_up",
    ),
    path(
        "<int:recipe_id>/steps/<int:step_id>/move-down/",
        recipe_steps.recipe_step_move,
        {"direction": "down"},
        name="step_move_down",
    ),
    # Ingredients inline edit
    path(
        "<int:recipe_id>/ingredients/reassign/",
        recipe_ingredients.recipe_ingredient_reassign,
        name="ingredient_reassign",
    ),
    path(
        "<int:recipe_id>/groups/<int:group_id>/ingredients/add/",
        recipe_ingredients.recipe_ingredient_add,
        name="ingredient_add_to_group",
    ),
    path(
        "<int:recipe_id>/groups/<int:group_id>/ingredients/create/",
        recipe_ingredients.recipe_ingredient_create,
        name="ingredient_create",
    ),
    path(
        "<int:recipe_id>/ingredients/<int:iir_id>/",
        recipe_ingredients.recipe_ingredient_display,
        name="ingredient_display",
    ),
    path(
        "<int:recipe_id>/ingredients/<int:iir_id>/edit/",
        recipe_ingredients.recipe_ingredient_edit,
        name="ingredient_edit",
    ),
    path(
        "<int:recipe_id>/ingredients/<int:iir_id>/save/",
        recipe_ingredients.recipe_ingredient_save,
        name="ingredient_save",
    ),
    path(
        "<int:recipe_id>/ingredients/<int:iir_id>/delete/",
        recipe_ingredients.recipe_ingredient_delete,
        name="ingredient_delete",
    ),
    path(
        "<int:recipe_id>/ingredients/<int:iir_id>/move-up/",
        recipe_ingredients.recipe_ingredient_move,
        {"direction": "up"},
        name="ingredient_move_up",
    ),
    path(
        "<int:recipe_id>/ingredients/<int:iir_id>/move-down/",
        recipe_ingredients.recipe_ingredient_move,
        {"direction": "down"},
        name="ingredient_move_down",
    ),
    # Groups inline edit
    path("<int:recipe_id>/groups/add/", recipe_ingredients.recipe_group_add, name="group_add"),
    path(
        "<int:recipe_id>/groups/create/",
        recipe_ingredients.recipe_group_create,
        name="group_create",
    ),
    path(
        "<int:recipe_id>/groups/<int:group_id>/",
        recipe_ingredients.recipe_group_display,
        name="group_display",
    ),
    path(
        "<int:recipe_id>/groups/<int:group_id>/edit/",
        recipe_ingredients.recipe_group_edit,
        name="group_edit",
    ),
    path(
        "<int:recipe_id>/groups/<int:group_id>/save/",
        recipe_ingredients.recipe_group_save,
        name="group_save",
    ),
    path(
        "<int:recipe_id>/groups/<int:group_id>/delete/",
        recipe_ingredients.recipe_group_delete,
        name="group_delete",
    ),
    path(
        "<int:recipe_id>/groups/<int:group_id>/move-up/",
        recipe_ingredients.recipe_group_move,
        {"direction": "up"},
        name="group_move_up",
    ),
    path(
        "<int:recipe_id>/groups/<int:group_id>/move-down/",
        recipe_ingredients.recipe_group_move,
        {"direction": "down"},
        name="group_move_down",
    ),
]
