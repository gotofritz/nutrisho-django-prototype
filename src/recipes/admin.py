from django.contrib import admin

from .models import (
    Cuisine,
    Ingredient,
    IngredientAlias,
    IngredientGroup,
    IngredientInRecipe,
    Recipe,
    Source,
    Step,
    Tag,
    Unit,
    UnitAlias,
)


@admin.register(Cuisine)
class CuisineAdmin(admin.ModelAdmin):
    """The curated cuisine tree (plan 011): one row per area, region or subregion."""

    list_display = ("__str__", "cuisine", "parent")
    list_select_related = ("parent__parent",)
    search_fields = ("cuisine",)
    autocomplete_fields = ("parent",)


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ("recipe_name",)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("tag", "owner")
    list_filter = (("owner", admin.EmptyFieldListFilter),)


@admin.register(IngredientGroup)
class IngredientGroupAdmin(admin.ModelAdmin):
    list_display = ("group_name", "recipe", "index_in_sequence")


@admin.register(IngredientInRecipe)
class IngredientInRecipeAdmin(admin.ModelAdmin):
    list_display = ("ingredient",)


@admin.register(Step)
class StepAdmin(admin.ModelAdmin):
    list_display = ("index_in_sequence", "recipe")


@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    list_display = ("ingredient_name", "owner")
    list_filter = (("owner", admin.EmptyFieldListFilter),)


@admin.register(IngredientAlias)
class IngredientAliasAdmin(admin.ModelAdmin):
    """Input-only names for a global ingredient (plan 008); the clean-up tool's Alias action."""

    list_display = ("alias_name", "canonical")
    list_select_related = ("canonical",)
    search_fields = ("alias_name", "canonical__ingredient_name")


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ("short_name",)


class UnitAliasInline(admin.TabularInline):
    model = UnitAlias
    extra = 1


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    """The canonical unit vocabulary (#67): what recipe rows point at."""

    list_display = ("name", "plural", "dimension")
    list_filter = ("dimension",)
    search_fields = ("name", "aliases__alias_name")
    inlines = (UnitAliasInline,)


@admin.register(UnitAlias)
class UnitAliasAdmin(admin.ModelAdmin):
    """Input-only spellings of a unit (`tablespoon` → `tbsp`)."""

    list_display = ("alias_name", "unit")
    list_select_related = ("unit",)
    search_fields = ("alias_name", "unit__name")
