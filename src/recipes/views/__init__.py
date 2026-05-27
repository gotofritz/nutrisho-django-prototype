from .home import home
from .recipe import recipe, recipe_edit
from .recipe_crud import recipe_delete, recipe_new
from .recipe_fields import recipe_field_display, recipe_field_edit, recipe_field_save
from .recipe_ingredients import (
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
)
from .recipe_steps import (
    recipe_step_add,
    recipe_step_delete,
    recipe_step_display,
    recipe_step_edit,
    recipe_step_save,
)

__all__ = [
    "home",
    "recipe",
    "recipe_delete",
    "recipe_edit",
    "recipe_field_display",
    "recipe_field_edit",
    "recipe_field_save",
    "recipe_group_add",
    "recipe_group_delete",
    "recipe_group_display",
    "recipe_group_edit",
    "recipe_group_save",
    "recipe_ingredient_add",
    "recipe_ingredient_delete",
    "recipe_ingredient_display",
    "recipe_ingredient_edit",
    "recipe_ingredient_save",
    "recipe_new",
    "recipe_step_add",
    "recipe_step_delete",
    "recipe_step_display",
    "recipe_step_edit",
    "recipe_step_save",
]
