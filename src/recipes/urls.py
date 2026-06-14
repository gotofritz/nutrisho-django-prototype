from django.urls import path

from recipes.views._auth import htmx_login_required

from .views import (
    home,
    recipe,
    recipe_delete,
    recipe_delete_panel,
    recipe_duplicate,
    recipe_field_display,
    recipe_field_edit,
    recipe_field_save,
    recipe_group_add,
    recipe_group_create,
    recipe_group_delete,
    recipe_group_display,
    recipe_group_edit,
    recipe_group_move_down,
    recipe_group_move_up,
    recipe_group_save,
    recipe_ingredient_add,
    recipe_ingredient_create,
    recipe_ingredient_delete,
    recipe_ingredient_display,
    recipe_ingredient_edit,
    recipe_ingredient_move_down,
    recipe_ingredient_move_up,
    recipe_ingredient_reassign,
    recipe_ingredient_save,
    recipe_metadata_edit,
    recipe_new,
    recipe_scale,
    recipe_scale_panel,
    recipe_step_add,
    recipe_step_create,
    recipe_step_delete,
    recipe_step_display,
    recipe_step_edit,
    recipe_step_move_down,
    recipe_step_move_up,
    recipe_step_save,
)


def _lr(view):
    """Shorthand: wrap a view with HTMX-aware login enforcement."""
    return htmx_login_required(view)


app_name = "recipes"
urlpatterns = [
    path("", _lr(home), name="home"),
    path("new/", _lr(recipe_new), name="new"),
    path("<int:recipe_id>/", _lr(recipe), name="recipe"),
    path("<int:recipe_id>/delete/", _lr(recipe_delete), name="delete"),
    path("<int:recipe_id>/delete/panel/", _lr(recipe_delete_panel), name="delete_panel"),
    path("<int:recipe_id>/duplicate/", _lr(recipe_duplicate), name="duplicate"),
    path("<int:recipe_id>/metadata/", _lr(recipe_metadata_edit), name="metadata_edit"),
    path("<int:recipe_id>/scale/", _lr(recipe_scale), name="scale"),
    path("<int:recipe_id>/scale/panel/", _lr(recipe_scale_panel), name="scale_panel"),
    # Field inline edit
    path(
        "<int:recipe_id>/field/<str:field_name>/", _lr(recipe_field_display), name="field_display"
    ),
    path("<int:recipe_id>/field/<str:field_name>/edit/", _lr(recipe_field_edit), name="field_edit"),
    path("<int:recipe_id>/field/<str:field_name>/save/", _lr(recipe_field_save), name="field_save"),
    # Steps inline edit
    path("<int:recipe_id>/steps/add/", _lr(recipe_step_add), name="step_add"),
    path("<int:recipe_id>/steps/create/", _lr(recipe_step_create), name="step_create"),
    path("<int:recipe_id>/steps/<int:step_id>/", _lr(recipe_step_display), name="step_display"),
    path("<int:recipe_id>/steps/<int:step_id>/edit/", _lr(recipe_step_edit), name="step_edit"),
    path("<int:recipe_id>/steps/<int:step_id>/save/", _lr(recipe_step_save), name="step_save"),
    path(
        "<int:recipe_id>/steps/<int:step_id>/delete/", _lr(recipe_step_delete), name="step_delete"
    ),
    path(
        "<int:recipe_id>/steps/<int:step_id>/move-up/",
        _lr(recipe_step_move_up),
        name="step_move_up",
    ),
    path(
        "<int:recipe_id>/steps/<int:step_id>/move-down/",
        _lr(recipe_step_move_down),
        name="step_move_down",
    ),
    # Ingredients inline edit
    path(
        "<int:recipe_id>/ingredients/reassign/",
        _lr(recipe_ingredient_reassign),
        name="ingredient_reassign",
    ),
    path(
        "<int:recipe_id>/groups/<int:group_id>/ingredients/add/",
        _lr(recipe_ingredient_add),
        name="ingredient_add_to_group",
    ),
    path(
        "<int:recipe_id>/groups/<int:group_id>/ingredients/create/",
        _lr(recipe_ingredient_create),
        name="ingredient_create",
    ),
    path(
        "<int:recipe_id>/ingredients/<int:iir_id>/",
        _lr(recipe_ingredient_display),
        name="ingredient_display",
    ),
    path(
        "<int:recipe_id>/ingredients/<int:iir_id>/edit/",
        _lr(recipe_ingredient_edit),
        name="ingredient_edit",
    ),
    path(
        "<int:recipe_id>/ingredients/<int:iir_id>/save/",
        _lr(recipe_ingredient_save),
        name="ingredient_save",
    ),
    path(
        "<int:recipe_id>/ingredients/<int:iir_id>/delete/",
        _lr(recipe_ingredient_delete),
        name="ingredient_delete",
    ),
    path(
        "<int:recipe_id>/ingredients/<int:iir_id>/move-up/",
        _lr(recipe_ingredient_move_up),
        name="ingredient_move_up",
    ),
    path(
        "<int:recipe_id>/ingredients/<int:iir_id>/move-down/",
        _lr(recipe_ingredient_move_down),
        name="ingredient_move_down",
    ),
    # Groups inline edit
    path("<int:recipe_id>/groups/add/", _lr(recipe_group_add), name="group_add"),
    path("<int:recipe_id>/groups/create/", _lr(recipe_group_create), name="group_create"),
    path("<int:recipe_id>/groups/<int:group_id>/", _lr(recipe_group_display), name="group_display"),
    path("<int:recipe_id>/groups/<int:group_id>/edit/", _lr(recipe_group_edit), name="group_edit"),
    path("<int:recipe_id>/groups/<int:group_id>/save/", _lr(recipe_group_save), name="group_save"),
    path(
        "<int:recipe_id>/groups/<int:group_id>/delete/",
        _lr(recipe_group_delete),
        name="group_delete",
    ),
    path(
        "<int:recipe_id>/groups/<int:group_id>/move-up/",
        _lr(recipe_group_move_up),
        name="group_move_up",
    ),
    path(
        "<int:recipe_id>/groups/<int:group_id>/move-down/",
        _lr(recipe_group_move_down),
        name="group_move_down",
    ),
]
