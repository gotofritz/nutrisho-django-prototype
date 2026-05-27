from django import forms

from recipes.models import Recipe

EDITABLE_RECIPE_FIELDS = frozenset(["recipe_name", "short_description", "servings"])


class RecipeFieldForm(forms.ModelForm):
    """Form for editing a single Recipe field by name."""

    class Meta:
        model = Recipe
        fields = ["recipe_name", "short_description", "servings"]

    def __init__(self, field_name: str, *args: object, **kwargs: object) -> None:
        if field_name not in EDITABLE_RECIPE_FIELDS:
            raise ValueError(f"Field '{field_name}' is not editable")
        super().__init__(*args, **kwargs)
        for name in list(self.fields):
            if name != field_name:
                del self.fields[name]
