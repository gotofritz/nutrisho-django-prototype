from decimal import Decimal

from django import forms

from recipes.models import IngredientGroup, IngredientInRecipe


class IngredientInRecipeForm(forms.ModelForm):
    class Meta:
        model = IngredientInRecipe
        fields = ["quantity", "unit", "preparation", "note"]

    def clean_quantity(self) -> Decimal | None:
        qty = self.cleaned_data.get("quantity")
        if qty is not None and qty < 0:
            raise forms.ValidationError("Quantity must be positive.")
        return qty


class IngredientGroupForm(forms.ModelForm):
    class Meta:
        model = IngredientGroup
        fields = ["group_name"]
