from decimal import Decimal

from django import forms

from recipes.models import Ingredient, IngredientGroup, IngredientInRecipe


class IngredientInRecipeForm(forms.ModelForm):
    ingredient_name = forms.CharField(max_length=64, required=True)

    class Meta:
        model = IngredientInRecipe
        fields = ["quantity", "unit", "preparation", "note"]
        widgets = {
            "quantity": forms.NumberInput(attrs={"step": "any"}),
        }

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["ingredient_name"].initial = self.instance.ingredient.ingredient_name

    def clean_quantity(self) -> Decimal | None:
        qty = self.cleaned_data.get("quantity")
        if qty is not None and qty < 0:
            raise forms.ValidationError("Quantity must be positive.")
        return qty

    def save(self, commit: bool = True) -> IngredientInRecipe:
        iir = super().save(commit=False)
        name = self.cleaned_data["ingredient_name"].strip()
        if commit:
            ingredient, _ = Ingredient.objects.get_or_create(ingredient_name=name)
            iir.ingredient = ingredient
            iir.save()
        else:
            self._pending_ingredient_name = None
            existing = Ingredient.objects.filter(ingredient_name=name).first()
            if existing:
                iir.ingredient = existing
            else:
                self._pending_ingredient_name = name
        return iir

    def resolve_pending_ingredient(self, iir: IngredientInRecipe) -> None:
        """Create pending Ingredient row and set FK. Call before iir.save() when commit=False."""
        if getattr(self, "_pending_ingredient_name", None):
            ingredient, _ = Ingredient.objects.get_or_create(
                ingredient_name=self._pending_ingredient_name
            )
            iir.ingredient = ingredient
            self._pending_ingredient_name = None


class IngredientGroupForm(forms.ModelForm):
    group_name = forms.CharField(max_length=64, required=False, label="Group name")

    class Meta:
        model = IngredientGroup
        fields = ["group_name"]

    def __init__(self, *args: object, group_count: int = 1, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._group_count = group_count

    def clean_group_name(self) -> str:
        name = (self.cleaned_data.get("group_name") or "").strip()
        if self._group_count > 1 and not name:
            raise forms.ValidationError("Group name required when multiple groups exist.")
        return name
