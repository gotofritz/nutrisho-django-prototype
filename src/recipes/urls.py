from django.urls import path

from .views import (
    home,
    recipe,
    recipe_delete,
    recipe_edit,
    recipe_field_display,
    recipe_field_edit,
    recipe_field_save,
    recipe_group_add,
    recipe_group_delete,
    recipe_group_display,
    recipe_group_edit,
    recipe_group_save,
    recipe_ingredient_add,
    recipe_ingredient_delete,
    recipe_ingredient_display,
    recipe_ingredient_edit,
    recipe_ingredient_save,
    recipe_new,
    recipe_step_add,
    recipe_step_delete,
    recipe_step_display,
    recipe_step_edit,
    recipe_step_save,
)

app_name = "recipes"
urlpatterns = [
    path("", home, name="home"),
    path("new/", recipe_new, name="new"),
    path("<int:recipe_id>/", recipe, name="recipe"),
    path("<int:recipe_id>/delete/", recipe_delete, name="delete"),
    path("<int:recipe_id>/edit", recipe_edit, name="edit"),
    path("<int:recipe_id>/update", recipe, name="update"),
    # Field inline edit
    path("<int:recipe_id>/field/<str:field_name>/", recipe_field_display, name="field_display"),
    path("<int:recipe_id>/field/<str:field_name>/edit/", recipe_field_edit, name="field_edit"),
    path("<int:recipe_id>/field/<str:field_name>/save/", recipe_field_save, name="field_save"),
    # Steps inline edit
    path("<int:recipe_id>/steps/add/", recipe_step_add, name="step_add"),
    path("<int:recipe_id>/steps/<int:step_id>/", recipe_step_display, name="step_display"),
    path("<int:recipe_id>/steps/<int:step_id>/edit/", recipe_step_edit, name="step_edit"),
    path("<int:recipe_id>/steps/<int:step_id>/save/", recipe_step_save, name="step_save"),
    path("<int:recipe_id>/steps/<int:step_id>/delete/", recipe_step_delete, name="step_delete"),
    # Ingredients inline edit
    path("<int:recipe_id>/ingredients/add/", recipe_ingredient_add, name="ingredient_add"),
    path(
        "<int:recipe_id>/ingredients/<int:iir_id>/",
        recipe_ingredient_display,
        name="ingredient_display",
    ),
    path(
        "<int:recipe_id>/ingredients/<int:iir_id>/edit/",
        recipe_ingredient_edit,
        name="ingredient_edit",
    ),
    path(
        "<int:recipe_id>/ingredients/<int:iir_id>/save/",
        recipe_ingredient_save,
        name="ingredient_save",
    ),
    path(
        "<int:recipe_id>/ingredients/<int:iir_id>/delete/",
        recipe_ingredient_delete,
        name="ingredient_delete",
    ),
    # Groups inline edit
    path("<int:recipe_id>/groups/add/", recipe_group_add, name="group_add"),
    path("<int:recipe_id>/groups/<int:group_id>/", recipe_group_display, name="group_display"),
    path("<int:recipe_id>/groups/<int:group_id>/edit/", recipe_group_edit, name="group_edit"),
    path("<int:recipe_id>/groups/<int:group_id>/save/", recipe_group_save, name="group_save"),
    path("<int:recipe_id>/groups/<int:group_id>/delete/", recipe_group_delete, name="group_delete"),
]
