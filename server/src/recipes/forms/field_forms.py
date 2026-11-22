from django import forms
from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction

from recipes.models import Recipe
from recipes.models.tag import TAG_MAX_LENGTH
from recipes.services.name_resolution import CuisineNameError, check_cuisine
from recipes.services.recipe_metadata import set_cuisine, set_tags

EDITABLE_RECIPE_FIELDS = frozenset(["recipe_name", "short_description", "servings"])

_METADATA_MODEL_FIELDS = ["recipe_name", "short_description", "servings", "source_instance"]


class RecipeMetadataForm(forms.ModelForm):
    """Form for creating or editing recipe metadata.

    Cuisine is text plus a datalist of the dotted paths the owner sees
    (`med.italy.sicily`); a bare unambiguous name (`sicily`) is accepted too,
    and a cuisine they cannot see becomes one of their own (#171). Like tags,
    it is made when the recipe is saved, never while the form is checked:
    `cuisine_name` is cleaned to the text, and the services resolve it.

    `tags` is comma-separated names, resolved within `owner`'s vocabulary (the
    recipe's owner): global tags or their private ones, an unknown name
    becoming a private tag (plan 011). Tags are an M2M, so they are written
    after the recipe has a pk: by `save()` itself, or by `create_recipe` and
    `save_metadata` from the cleaned names when the caller saves with
    `commit=False`.
    """

    cuisine_name = forms.CharField(max_length=200, required=False, label="Cuisine")
    tags = forms.CharField(required=False, label="Tags", help_text="Separate tags with commas.")

    class Meta:
        model = Recipe
        fields = _METADATA_MODEL_FIELDS
        widgets = {
            "recipe_name": forms.TextInput(attrs={"autofocus": True}),
            "short_description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args: object, owner: AbstractBaseUser, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._owner = owner
        if self.instance and self.instance.pk and self.instance.cuisine:
            self.fields["cuisine_name"].initial = self.instance.cuisine.path
        if self.instance and self.instance.pk:
            names = self.instance.tags.values_list("tag", flat=True)
            self.fields["tags"].initial = ", ".join(sorted(names, key=str.lower))

    def clean_tags(self) -> list[str]:
        """Split on commas, strip, drop blanks and case-insensitive repeats."""
        raw = self.cleaned_data.get("tags") or ""
        names: dict[str, str] = {}
        for part in raw.split(","):
            name = part.strip()
            if name:
                names.setdefault(name.lower(), name)
        if any(len(n) > TAG_MAX_LENGTH for n in names.values()):
            msg = f"Tags can be at most {TAG_MAX_LENGTH} characters long."
            raise forms.ValidationError(msg)
        return list(names.values())

    def save_tags(self, recipe: Recipe) -> None:
        """Set the recipe's tags to exactly the typed names."""
        set_tags(recipe, names=self.cleaned_data["tags"])

    def clean_cuisine_name(self) -> str:
        """The typed cuisine, stripped; one that could not be placed is an error."""
        text = (self.cleaned_data.get("cuisine_name") or "").strip()
        try:
            check_cuisine(text, owner=self._owner)
        except CuisineNameError as error:
            raise forms.ValidationError(str(error)) from error
        return text

    def save(self, commit: bool = True) -> Recipe:
        """Save the recipe; its cuisine and tags too when committing."""
        recipe = super().save(commit=False)
        if commit:
            with transaction.atomic():
                set_cuisine(recipe, name=self.cleaned_data["cuisine_name"], owner=self._owner)
                recipe.save()
                self.save_tags(recipe)
        return recipe


class RecipeFieldForm(forms.ModelForm):
    """Form for editing a single Recipe field by name."""

    class Meta:
        model = Recipe
        fields = ["recipe_name", "short_description", "servings"]
        widgets = {"short_description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, field_name: str, *args: object, **kwargs: object) -> None:
        if field_name not in EDITABLE_RECIPE_FIELDS:
            msg = f"Field '{field_name}' is not editable"
            raise ValueError(msg)
        super().__init__(*args, **kwargs)
        for name in list(self.fields):
            if name != field_name:
                del self.fields[name]
        # htmx focuses [autofocus] in swapped-in content (#61).
        self.fields[field_name].widget.attrs["autofocus"] = True
