"""Form for the staff cuisine tool."""

from django import forms

from recipes.models import Cuisine
from recipes.services.cuisine_admin import cuisine_rows


class CuisineForm(forms.ModelForm):
    """Add or edit one node of the cuisine tree.

    The parent is picked by path. A ModelForm runs `Cuisine.clean()` (no dots,
    no loops, at most three levels) and the sibling-uniqueness constraints, so
    each of those comes back as a form error rather than a 500.
    """

    class Meta:
        model = Cuisine
        fields = ["cuisine", "parent"]
        labels = {"cuisine": "Name", "parent": "Inside"}

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        parent = self.fields["parent"]
        assert isinstance(parent, forms.ModelChoiceField)
        # Only areas and regions can hold children, and a node can't go inside itself.
        rows = [
            row for row in cuisine_rows() if row.depth < 2 and row.cuisine.pk != self.instance.pk
        ]
        parent.queryset = Cuisine.objects.filter(pk__in=[row.cuisine.pk for row in rows])
        parent.empty_label = "(nothing: a new area)"
        labels = {row.cuisine.pk: row.path for row in rows}
        parent.label_from_instance = lambda node: labels.get(node.pk, str(node))

    def clean_cuisine(self) -> str:
        """Strip the name; it is required."""
        name = (self.cleaned_data.get("cuisine") or "").strip()
        if not name:
            msg = "A name is required."
            raise forms.ValidationError(msg)
        return name
