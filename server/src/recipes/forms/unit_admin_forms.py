"""Forms for the staff unit tool (#154)."""

from django import forms
from django.db import transaction

from recipes.models import Unit, UnitAlias
from recipes.models.unit import UNIT_NAME_MAX_LENGTH


def _alias_owner(name: str, *, exclude_unit: Unit | None) -> Unit | None:
    """The unit another of whose aliases is `name`, ignoring case."""
    aliases = UnitAlias.objects.select_related("unit").filter(alias_name__iexact=name)
    if exclude_unit is not None and exclude_unit.pk is not None:
        aliases = aliases.exclude(unit=exclude_unit)
    alias = aliases.first()
    return alias.unit if alias is not None else None


class UnitForm(forms.ModelForm):
    """Add a global unit, or edit one, global or private.

    A ModelForm runs `Unit.clean()` (a global unit needs a dimension) and both
    uniqueness constraints, so each comes back as a form error rather than a
    500. A global unit's other spellings are typed comma-separated in
    `aliases`; a private unit has none (aliases are global), so the field goes.
    """

    aliases = forms.CharField(
        required=False,
        label="Other spellings",
        help_text="Comma-separated: typed or imported, they mean this unit.",
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    class Meta:
        model = Unit
        fields = ["name", "plural_name", "dimension"]
        labels = {
            "name": "Name",
            "plural_name": "Plural",
            "dimension": "Measures",
        }
        help_texts = {
            "plural_name": "Blank follows the rule; the name itself keeps it invariant (200 g).",
        }

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        if self.instance.owner_id is not None:
            del self.fields["aliases"]
        elif self.instance.pk is not None:
            names = (
                UnitAlias.objects.filter(unit=self.instance)
                .order_by("alias_name")
                .values_list("alias_name", flat=True)
            )
            self.fields["aliases"].initial = ", ".join(names)

    def clean_name(self) -> str:
        """Strip the name; it must be free in its list, and not another unit's alias.

        The uniqueness constraints name `owner`, which is not on the form, so
        a ModelForm would skip them: checked here instead.
        """
        name = " ".join((self.cleaned_data.get("name") or "").split())
        if not name:
            msg = "A name is required."
            raise forms.ValidationError(msg)
        same = Unit.objects.filter(name__iexact=name).exclude(pk=self.instance.pk)
        if self.instance.owner_id is None:
            if same.filter(owner__isnull=True).exists():
                msg = "That unit already exists."
                raise forms.ValidationError(msg)
        elif same.filter(owner=self.instance.owner_id).exists():
            msg = "Its owner already has that unit."
            raise forms.ValidationError(msg)
        if self.instance.owner_id is None:
            other = _alias_owner(name, exclude_unit=self.instance)
            if other is not None:
                msg = f"“{name}” already means {other.name}."
                raise forms.ValidationError(msg)
        return name

    def clean_aliases(self) -> list[str]:
        """The typed spellings, stripped and without repeats; each must be free."""
        found: dict[str, str] = {}
        for raw in (self.cleaned_data.get("aliases") or "").split(","):
            name = " ".join(raw.split())
            if name:
                found.setdefault(name.lower(), name)
        names = list(found.values())
        for name in names:
            if len(name) > UNIT_NAME_MAX_LENGTH:
                msg = f"“{name}” is longer than {UNIT_NAME_MAX_LENGTH} characters."
                raise forms.ValidationError(msg)
            if Unit.objects.filter(owner__isnull=True, name__iexact=name).exists():
                msg = f"“{name}” is already a unit."
                raise forms.ValidationError(msg)
            other = _alias_owner(name, exclude_unit=self.instance)
            if other is not None:
                msg = f"“{name}” already means {other.name}."
                raise forms.ValidationError(msg)
        return names

    def clean(self) -> dict:
        """A unit's own name is not one of its aliases."""
        cleaned = super().clean()
        name = (cleaned.get("name") or "").lower()
        if name and name in {alias.lower() for alias in cleaned.get("aliases") or []}:
            self.add_error("aliases", f"“{cleaned['name']}” is the unit's own name.")
        return cleaned

    @transaction.atomic
    def save(self, commit: bool = True) -> Unit:
        """Save the unit and replace its aliases with the typed ones."""
        unit = super().save(commit=commit)
        if commit and "aliases" in self.fields:
            names = self.cleaned_data["aliases"]
            wanted = {name.lower() for name in names}
            existing = {str(a.alias_name).lower(): a for a in UnitAlias.objects.filter(unit=unit)}
            for key, alias in existing.items():
                if key not in wanted:
                    alias.delete()
            for name in names:
                if name.lower() not in existing:
                    UnitAlias.objects.create(alias_name=name, unit=unit)
        return unit
