from decimal import Decimal

from django import forms
from django.contrib.auth.models import AbstractBaseUser

from recipes.models import IngredientGroup, IngredientInRecipe, Unit
from recipes.models.ingredient import INGREDIENT_NAME_MAX_LENGTH
from recipes.models.unit import UNIT_NAME_MAX_LENGTH
from recipes.services.name_resolution import (
    find_ingredient,
    find_unit,
    resolve_ingredient,
    unit_names,
)
from recipes.utils.unit_words import not_a_unit


class IngredientInRecipeForm(forms.ModelForm):
    """One ingredient row; the typed names resolve within `owner`'s vocabulary.

    `owner` is the recipe's owner: names resolve to the global list or their
    private rows, and an unknown name becomes private to them (plan 011). The
    optional substitute (`2 onions or shallots`, #65) resolves the same way. The
    typed unit resolves to the shared vocabulary and is never created (#67).

    Neither name is written by `save()`: the view calls `resolve_names()` inside
    its transaction, since resolving may create an ingredient row.
    """

    ingredient_name = forms.CharField(max_length=INGREDIENT_NAME_MAX_LENGTH, required=True)
    substitute_name = forms.CharField(
        max_length=INGREDIENT_NAME_MAX_LENGTH,
        required=False,
        label="Or",
        help_text="An ingredient that can stand in for it.",
        widget=forms.TextInput(attrs={"list": "ingredients-datalist", "autocomplete": "off"}),
    )
    unit = forms.CharField(
        max_length=UNIT_NAME_MAX_LENGTH,
        required=False,
        label="Unit",
        widget=forms.TextInput(attrs={"list": "units-datalist", "autocomplete": "off"}),
    )

    class Meta:
        model = IngredientInRecipe
        # `unit` is the typed text above, resolved to the FK in `clean_unit`.
        fields = ["quantity", "preparation", "note"]
        widgets = {
            "quantity": forms.NumberInput(attrs={"step": "any", "autofocus": True}),
        }

    def __init__(self, *args: object, owner: AbstractBaseUser, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._owner = owner
        if self.instance and self.instance.pk:
            self.fields["ingredient_name"].initial = self.instance.ingredient.ingredient_name
            substitute = self.instance.substitute
            self.fields["substitute_name"].initial = (
                substitute.ingredient_name if substitute else ""
            )
            unit = self.instance.unit
            self.fields["unit"].initial = unit.name if unit else self.instance.legacy_unit

    @property
    def unit_names(self) -> list[str]:
        """The vocabulary, for the unit field's datalist."""
        return unit_names()

    def clean_quantity(self) -> Decimal | None:
        """Reject negative quantities."""
        qty = self.cleaned_data.get("quantity")
        if qty is not None and qty < 0:
            msg = "Quantity must be positive."
            raise forms.ValidationError(msg)
        return qty

    def clean_unit(self) -> Unit | None:
        """The unit the text names; blank is none, and anything else is an error."""
        text = self.cleaned_data.get("unit") or ""
        if not text.strip():
            return None
        unit = find_unit(text)
        if unit is not None:
            return unit
        field = not_a_unit(text)
        if field is not None:
            msg = f"“{text.strip()}” is not a unit: put it under {field}."
        else:
            msg = f"“{text.strip()}” is not a unit we know: pick one from the list."
        raise forms.ValidationError(msg)

    def clean(self) -> dict:
        """Refuse a substitute that names the ingredient itself, by any spelling."""
        cleaned = super().clean()
        name = (cleaned.get("ingredient_name") or "").strip()
        substitute = (cleaned.get("substitute_name") or "").strip()
        cleaned["substitute_name"] = substitute
        if name and substitute and self._same_ingredient(name, substitute):
            self.add_error("substitute_name", "A substitute must be a different ingredient.")
        return cleaned

    def _same_ingredient(self, name: str, other: str) -> bool:
        """Whether both names resolve to one ingredient, existing or yet to be made."""
        if name.lower() == other.lower():
            return True
        found = find_ingredient(name, owner=self._owner)
        return found is not None and found == find_ingredient(other, owner=self._owner)

    def save(self, commit: bool = True) -> IngredientInRecipe:
        """Save the row's own fields; with `commit`, resolve both names first."""
        iir = super().save(commit=False)
        iir.unit = self.cleaned_data["unit"]
        iir.legacy_unit = ""
        if commit:
            self.resolve_names(iir)
            iir.save()
        return iir

    def resolve_names(self, iir: IngredientInRecipe) -> None:
        """Point `iir` at the typed ingredient and substitute, creating either if new.

        Call inside the write's transaction, before `iir.save()`.
        """
        iir.ingredient = resolve_ingredient(  # ty: ignore[invalid-assignment]  # FK descriptor
            self.cleaned_data["ingredient_name"].strip(), owner=self._owner
        )
        substitute = self.cleaned_data["substitute_name"]
        iir.substitute = (  # ty: ignore[invalid-assignment]  # FK descriptor
            resolve_ingredient(substitute, owner=self._owner) if substitute else None
        )


class IngredientGroupForm(forms.ModelForm):
    group_name = forms.CharField(
        max_length=64,
        required=False,
        label="Group name",
        widget=forms.TextInput(attrs={"autofocus": True}),
    )

    class Meta:
        model = IngredientGroup
        fields = ["group_name"]

    def __init__(self, *args: object, group_count: int = 1, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._group_count = group_count

    def clean_group_name(self) -> str:
        """Strip the group name; require one when several groups exist."""
        name = (self.cleaned_data.get("group_name") or "").strip()
        if self._group_count > 1 and not name:
            msg = "Group name required when multiple groups exist."
            raise forms.ValidationError(msg)
        return name
