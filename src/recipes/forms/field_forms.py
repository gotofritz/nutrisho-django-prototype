from django import forms
from django.db import transaction

from recipes.models import Cuisine, Recipe

EDITABLE_RECIPE_FIELDS = frozenset(["recipe_name", "short_description", "servings"])

_METADATA_MODEL_FIELDS = ["recipe_name", "short_description", "servings", "source_instance"]


class RecipeMetadataForm(forms.ModelForm):
    """Form for creating or editing recipe metadata. Cuisine uses text+datalist."""

    cuisine_name = forms.CharField(max_length=200, required=False, label="Cuisine")

    class Meta:
        model = Recipe
        fields = _METADATA_MODEL_FIELDS
        widgets = {"short_description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.cuisine:
            self.fields["cuisine_name"].initial = self.instance.cuisine.cuisine

    def save(self, commit: bool = True) -> Recipe:
        recipe = super().save(commit=False)
        name = self.cleaned_data.get("cuisine_name", "").strip()
        if commit:
            with transaction.atomic():
                if name:
                    cuisine, _ = Cuisine.objects.get_or_create(cuisine=name)
                    recipe.cuisine = cuisine
                else:
                    recipe.cuisine = None
                recipe.save()
        else:
            self._pending_cuisine_name = None
            if not name:
                recipe.cuisine = None
            else:
                existing = Cuisine.objects.filter(cuisine=name).first()
                if existing:
                    recipe.cuisine = existing
                else:
                    self._pending_cuisine_name = name
        return recipe

    def resolve_pending_cuisine(self, recipe: Recipe) -> None:
        """Create pending Cuisine row and set FK. Call before recipe.save() when commit=False."""
        if getattr(self, "_pending_cuisine_name", None):
            cuisine, _ = Cuisine.objects.get_or_create(cuisine=self._pending_cuisine_name)
            recipe.cuisine = cuisine
            self._pending_cuisine_name = None


class RecipeFieldForm(forms.ModelForm):
    """Form for editing a single Recipe field by name."""

    class Meta:
        model = Recipe
        fields = ["recipe_name", "short_description", "servings"]
        widgets = {"short_description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, field_name: str, *args: object, **kwargs: object) -> None:
        if field_name not in EDITABLE_RECIPE_FIELDS:
            raise ValueError(f"Field '{field_name}' is not editable")
        super().__init__(*args, **kwargs)
        for name in list(self.fields):
            if name != field_name:
                del self.fields[name]
