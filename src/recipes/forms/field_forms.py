from django import forms
from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction

from recipes.models import Cuisine, Recipe
from recipes.models.tag import TAG_MAX_LENGTH
from recipes.services.name_resolution import find_cuisine, resolve_tag

EDITABLE_RECIPE_FIELDS = frozenset(["recipe_name", "short_description", "servings"])

_METADATA_MODEL_FIELDS = ["recipe_name", "short_description", "servings", "source_instance"]


class RecipeMetadataForm(forms.ModelForm):
    """Form for creating or editing recipe metadata.

    Cuisine is text plus a datalist of the tree's dotted paths
    (`med.italy.sicily`); a bare unambiguous name (`sicily`) is accepted too.

    `tags` is comma-separated names, resolved within `owner`'s vocabulary (the
    recipe's owner): global tags or their private ones, an unknown name
    becoming a private tag (plan 011). Tags are an M2M, so they are written
    after the recipe has a pk: by `save()` itself, or by `save_tags()` when the
    caller saves with `commit=False`.
    """

    cuisine_name = forms.CharField(max_length=200, required=False, label="Cuisine")
    tags = forms.CharField(required=False, label="Tags", help_text="Separate tags with commas.")

    class Meta:
        model = Recipe
        fields = _METADATA_MODEL_FIELDS
        widgets = {"short_description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args: object, owner: AbstractBaseUser, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._owner = owner
        if self.instance and self.instance.pk and self.instance.cuisine:
            self.fields["cuisine_name"].initial = self.instance.cuisine.path
        if self.instance and self.instance.pk:
            names = self.instance.tag.values_list("tag", flat=True)
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
        tags = [resolve_tag(name, owner=self._owner) for name in self.cleaned_data["tags"]]
        recipe.tag.set(tags)  # ty: ignore[unresolved-attribute]  # reverse M2M

    def clean_cuisine_name(self) -> Cuisine | None:
        """The picked cuisine node, None when blank; unknown names are an error.

        Cuisines are a curated tree (plan 011), so the editor never creates one.
        """
        text = (self.cleaned_data.get("cuisine_name") or "").strip()
        if not text:
            return None
        cuisine = find_cuisine(text)
        if cuisine is None:
            msg = "Pick a cuisine from the list (staff can add new ones)."
            raise forms.ValidationError(msg)
        return cuisine

    def save(self, commit: bool = True) -> Recipe:
        """Save the recipe with the picked cuisine; tags too when committing."""
        recipe = super().save(commit=False)
        recipe.cuisine = self.cleaned_data.get("cuisine_name")
        if commit:
            with transaction.atomic():
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
