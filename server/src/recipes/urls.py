"""The recipes app's routes.

Each view is named through its own module; there is no re-export list to keep
in step. A move route's direction is a fixed `direction` kwarg, so one view
serves both of a pair while the templates keep the `*_move_up` and
`*_move_down` names.
"""

from django.urls import path

from recipes.views import (
    api,
    config,
    cuisine_admin,
    home,
    ingredient_admin,
    recipe,
    recipe_crud,
    recipe_fields,
    recipe_ingredients,
    recipe_steps,
    recipe_transfer,
    recipe_trash,
    unit_admin,
)
from recipes.views._auth import htmx_staff_required


def _staff(view):
    """Shorthand: signed in and staff; the clean-up tool edits rows every user shares."""
    return htmx_staff_required(view)


app_name = "recipes"
urlpatterns = [
    path("", home.home, name="home"),
    path("new/", recipe_crud.recipe_new, name="new"),
    path("config/", config.config, name="config"),
    path("trash/", recipe_trash.trash, name="trash"),
    path("export/", recipe_transfer.recipe_export, name="export"),
    path("import/", recipe_transfer.recipe_import, name="import"),
    # For the recipe clipper: token-authenticated JSON, not a page (#78).
    path("api/recipes/", api.api_recipes, name="api_recipes"),
    path("api/vocabulary/", api.api_vocabulary, name="api_vocabulary"),
    # Shared-ingredient clean-up tool (Miller columns). The `manage/` prefix keeps
    # these clear of the per-recipe `<recipe_id>/ingredients/...` inline-edit routes.
    path(
        "ingredients/manage/", _staff(ingredient_admin.ingredient_manage), name="ingredient_manage"
    ),
    path(
        "ingredients/manage/undo/",
        _staff(ingredient_admin.ingredient_manage_undo),
        name="ingredient_manage_undo",
    ),
    path(
        "ingredients/manage/search/",
        _staff(ingredient_admin.ingredient_manage_search),
        name="ingredient_manage_search",
    ),
    path(
        "ingredients/manage/more/",
        _staff(ingredient_admin.ingredient_manage_more),
        name="ingredient_manage_more",
    ),
    path(
        "ingredients/manage/recipes/",
        _staff(ingredient_admin.ingredient_manage_recipes),
        name="ingredient_manage_recipes",
    ),
    path(
        "ingredients/manage/preview/<uuid:recipe_id>/",
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
    # The recipe editor's ingredient autocomplete (#80).
    path(
        "ingredients/suggest/",
        recipe_ingredients.ingredient_suggest,
        name="ingredient_suggest",
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
    # Staff unit tool: the shared unit vocabulary and users' own units (#154).
    path("units/manage/", _staff(unit_admin.unit_manage), name="unit_manage"),
    path(
        "units/manage/columns/",
        _staff(unit_admin.unit_manage_columns),
        name="unit_manage_columns",
    ),
    path(
        "units/manage/add/",
        _staff(unit_admin.unit_manage_add),
        name="unit_manage_add",
    ),
    path(
        "units/manage/edit/",
        _staff(unit_admin.unit_manage_edit),
        name="unit_manage_edit",
    ),
    path(
        "units/manage/promote/",
        _staff(unit_admin.unit_manage_promote),
        name="unit_manage_promote",
    ),
    path(
        "units/manage/merge/",
        _staff(unit_admin.unit_manage_merge),
        name="unit_manage_merge",
    ),
    path(
        "units/manage/delete/",
        _staff(unit_admin.unit_manage_delete),
        name="unit_manage_delete",
    ),
    path(
        "units/manage/<int:unit_id>/save/",
        _staff(unit_admin.unit_manage_save),
        name="unit_manage_save",
    ),
    path("<uuid:recipe_id>/", recipe.recipe, name="recipe"),
    path("<uuid:recipe_id>/delete/", recipe_crud.recipe_delete, name="delete"),
    path("<uuid:recipe_id>/delete/panel/", recipe_crud.recipe_delete_panel, name="delete_panel"),
    path("<uuid:recipe_id>/restore/", recipe_trash.recipe_restore, name="restore"),
    path("<uuid:recipe_id>/purge/", recipe_trash.recipe_purge, name="purge"),
    path("<uuid:recipe_id>/duplicate/", recipe_crud.recipe_duplicate, name="duplicate"),
    path("<uuid:recipe_id>/metadata/", recipe_crud.recipe_metadata_edit, name="metadata_edit"),
    path("<uuid:recipe_id>/scale/copy/", recipe_crud.recipe_scale_copy, name="scale_copy"),
    path("<uuid:recipe_id>/scale/panel/", recipe_crud.recipe_scale_panel, name="scale_panel"),
    # Field inline edit
    path(
        "<uuid:recipe_id>/field/<str:field_name>/",
        recipe_fields.recipe_field_display,
        name="field_display",
    ),
    path(
        "<uuid:recipe_id>/field/<str:field_name>/edit/",
        recipe_fields.recipe_field_edit,
        name="field_edit",
    ),
    path(
        "<uuid:recipe_id>/field/<str:field_name>/save/",
        recipe_fields.recipe_field_save,
        name="field_save",
    ),
    # Steps inline edit
    path("<uuid:recipe_id>/steps/add/", recipe_steps.recipe_step_add, name="step_add"),
    path("<uuid:recipe_id>/steps/create/", recipe_steps.recipe_step_create, name="step_create"),
    path("<uuid:recipe_id>/steps/merge/", recipe_steps.recipe_steps_merge, name="steps_merge"),
    path(
        "<uuid:recipe_id>/steps/bulk-delete/",
        recipe_steps.recipe_steps_bulk_delete,
        name="steps_bulk_delete",
    ),
    path(
        "<uuid:recipe_id>/steps/<int:step_id>/",
        recipe_steps.recipe_step_display,
        name="step_display",
    ),
    path(
        "<uuid:recipe_id>/steps/<int:step_id>/edit/",
        recipe_steps.recipe_step_edit,
        name="step_edit",
    ),
    path(
        "<uuid:recipe_id>/steps/<int:step_id>/save/",
        recipe_steps.recipe_step_save,
        name="step_save",
    ),
    path(
        "<uuid:recipe_id>/steps/<int:step_id>/delete/",
        recipe_steps.recipe_step_delete,
        name="step_delete",
    ),
    path(
        "<uuid:recipe_id>/steps/<int:step_id>/split/",
        recipe_steps.recipe_step_split,
        name="step_split",
    ),
    path(
        "<uuid:recipe_id>/steps/<int:step_id>/move-up/",
        recipe_steps.recipe_step_move,
        {"direction": "up"},
        name="step_move_up",
    ),
    path(
        "<uuid:recipe_id>/steps/<int:step_id>/move-down/",
        recipe_steps.recipe_step_move,
        {"direction": "down"},
        name="step_move_down",
    ),
    # Ingredients inline edit
    path(
        "<uuid:recipe_id>/ingredients/reassign/",
        recipe_ingredients.recipe_ingredient_reassign,
        name="ingredient_reassign",
    ),
    path(
        "<uuid:recipe_id>/groups/<int:group_id>/ingredients/add/",
        recipe_ingredients.recipe_ingredient_add,
        name="ingredient_add_to_group",
    ),
    path(
        "<uuid:recipe_id>/groups/<int:group_id>/ingredients/create/",
        recipe_ingredients.recipe_ingredient_create,
        name="ingredient_create",
    ),
    path(
        "<uuid:recipe_id>/ingredients/<int:iir_id>/",
        recipe_ingredients.recipe_ingredient_display,
        name="ingredient_display",
    ),
    path(
        "<uuid:recipe_id>/ingredients/<int:iir_id>/edit/",
        recipe_ingredients.recipe_ingredient_edit,
        name="ingredient_edit",
    ),
    path(
        "<uuid:recipe_id>/ingredients/<int:iir_id>/save/",
        recipe_ingredients.recipe_ingredient_save,
        name="ingredient_save",
    ),
    path(
        "<uuid:recipe_id>/ingredients/<int:iir_id>/delete/",
        recipe_ingredients.recipe_ingredient_delete,
        name="ingredient_delete",
    ),
    path(
        "<uuid:recipe_id>/ingredients/<int:iir_id>/move-up/",
        recipe_ingredients.recipe_ingredient_move,
        {"direction": "up"},
        name="ingredient_move_up",
    ),
    path(
        "<uuid:recipe_id>/ingredients/<int:iir_id>/move-down/",
        recipe_ingredients.recipe_ingredient_move,
        {"direction": "down"},
        name="ingredient_move_down",
    ),
    # Groups inline edit
    path("<uuid:recipe_id>/groups/add/", recipe_ingredients.recipe_group_add, name="group_add"),
    path(
        "<uuid:recipe_id>/groups/create/",
        recipe_ingredients.recipe_group_create,
        name="group_create",
    ),
    path(
        "<uuid:recipe_id>/groups/<int:group_id>/",
        recipe_ingredients.recipe_group_display,
        name="group_display",
    ),
    path(
        "<uuid:recipe_id>/groups/<int:group_id>/edit/",
        recipe_ingredients.recipe_group_edit,
        name="group_edit",
    ),
    path(
        "<uuid:recipe_id>/groups/<int:group_id>/save/",
        recipe_ingredients.recipe_group_save,
        name="group_save",
    ),
    path(
        "<uuid:recipe_id>/groups/<int:group_id>/delete/",
        recipe_ingredients.recipe_group_delete,
        name="group_delete",
    ),
    path(
        "<uuid:recipe_id>/groups/<int:group_id>/move-up/",
        recipe_ingredients.recipe_group_move,
        {"direction": "up"},
        name="group_move_up",
    ),
    path(
        "<uuid:recipe_id>/groups/<int:group_id>/move-down/",
        recipe_ingredients.recipe_group_move,
        {"direction": "down"},
        name="group_move_down",
    ),
]
