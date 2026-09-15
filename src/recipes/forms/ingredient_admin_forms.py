"""Forms for the shared-Ingredient clean-up tool."""

from django import forms

from recipes.models import Ingredient


class IngredientForm(forms.ModelForm):
    """Edit one shared `Ingredient` row.

    Names are compared case-insensitively: British spelling is canonical and
    `Onion`/`onion` are the same ingredient, so a rename onto an existing name
    is a merge, not an edit. Phase 7 adds the matching DB constraint; this keeps
    the form from creating clashes in the meantime.

    `plural_name` is the escape hatch for the pluralisation rule (issue #24):
    blank derives the plural from the rule, a value overrides it, and a value
    equal to the singular makes the ingredient invariant.
    """

    class Meta:
        model = Ingredient
        fields = ["ingredient_name", "plural_name", "family", "dietary_constraint"]

    def clean_ingredient_name(self) -> str:
        name = (self.cleaned_data.get("ingredient_name") or "").strip()
        if not name:
            raise forms.ValidationError("Ingredient name is required.")
        clash = Ingredient.objects.filter(ingredient_name__iexact=name)
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError(
                "An ingredient with this name already exists — merge them instead."
            )
        return name
