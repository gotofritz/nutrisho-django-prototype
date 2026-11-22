"""Form for the staff cuisine tool."""

from django import forms

from recipes.models import Cuisine
from recipes.services.cuisine_admin import cuisine_rows


class CuisineForm(forms.ModelForm):
    """Add or edit one node of the cuisine tree.

    The parent is picked by path. A ModelForm runs `Cuisine.clean()` (no dots,
    no loops, at most three levels, no parent hidden from the node's owner) and
    the sibling-uniqueness constraints, so each of those comes back as a form
    error rather than a 500. A node staff add is global, so it goes inside a
    global node; a user's own node (#171) may also go inside that user's, and
    `make_global` moves it into the shared tree.
    """

    make_global = forms.BooleanField(required=False, label="Make it global, so every user sees it")

    class Meta:
        model = Cuisine
        fields = ["cuisine", "parent"]
        labels = {"cuisine": "Name", "parent": "Inside"}

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        owner_id = self.instance.owner_id
        if owner_id is None:
            del self.fields["make_global"]
        parent = self.fields["parent"]
        assert isinstance(parent, forms.ModelChoiceField)
        # Only areas and regions can hold children, a node can't go inside
        # itself, and none goes inside a node its owner cannot see.
        rows = [
            row
            for row in cuisine_rows()
            if row.depth < 2
            and row.cuisine.pk != self.instance.pk
            and row.cuisine.owner_id in {None, owner_id}
        ]
        parent.queryset = Cuisine.objects.filter(pk__in=[row.cuisine.pk for row in rows])
        parent.empty_label = "(nothing: a new area)"
        labels = {
            row.cuisine.pk: f"{row.path} (private to {row.owner_name})"
            if row.owner_name
            else row.path
            for row in rows
        }
        parent.label_from_instance = lambda node: labels.get(node.pk, str(node))

    def clean_cuisine(self) -> str:
        """Strip the name; it is required."""
        name = (self.cleaned_data.get("cuisine") or "").strip()
        if not name:
            msg = "A name is required."
            raise forms.ValidationError(msg)
        return name

    def _get_validation_exclusions(self) -> set[str]:
        """Check the constraints on `owner` too: the sibling rules depend on it."""
        return super()._get_validation_exclusions() - {"owner"}

    def _post_clean(self) -> None:
        """Make the node global before the model's own checks, so they see it as it will be."""
        if self.cleaned_data.get("make_global"):
            self.instance.owner = None
        super()._post_clean()
