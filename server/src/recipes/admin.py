from django.contrib import admin

from .models import (
    ApiToken,
    Cuisine,
    Ingredient,
    IngredientAlias,
    IngredientGroup,
    IngredientInRecipe,
    Recipe,
    Step,
    Tag,
    Unit,
    UnitAlias,
)


@admin.register(Cuisine)
class CuisineAdmin(admin.ModelAdmin):
    """The cuisine tree (plan 011): one row per area, region or subregion, global or a user's own (#171)."""

    list_display = ("__str__", "cuisine", "parent", "owner")
    list_filter = (("owner", admin.EmptyFieldListFilter),)
    list_select_related = ("parent__parent", "owner")
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


class UnitAliasInline(admin.TabularInline):
    model = UnitAlias
    extra = 1


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    """The unit vocabulary (#67): what recipe rows point at.

    Global units have no owner. A user's own unit (#154) becomes global when
    its owner is cleared, which needs a dimension too.
    """

    list_display = ("name", "plural", "dimension", "owner")
    list_filter = ("dimension", ("owner", admin.EmptyFieldListFilter))
    list_select_related = ("owner",)
    search_fields = ("name", "aliases__alias_name")
    inlines = (UnitAliasInline,)


@admin.register(UnitAlias)
class UnitAliasAdmin(admin.ModelAdmin):
    """Input-only spellings of a unit (`tablespoon` → `tbsp`)."""

    list_display = ("alias_name", "unit")
    list_select_related = ("unit",)
    search_fields = ("alias_name", "unit__name")


@admin.register(ApiToken)
class ApiTokenAdmin(admin.ModelAdmin):
    """List and revoke API tokens (#78). A key is made by `create_api_token`, which shows it once."""

    list_display = ("name", "user", "created_at", "last_used_at")
    list_select_related = ("user",)
    readonly_fields = ("user", "name", "created_at", "last_used_at")

    def has_add_permission(self, request) -> bool:  # noqa: ARG002 - ModelAdmin API
        """Never: a key made here could not be shown to anyone."""
        return False

    def has_change_permission(self, request, obj=None) -> bool:  # noqa: ARG002 - ModelAdmin API
        """Never: a token is kept or deleted."""
        return False
