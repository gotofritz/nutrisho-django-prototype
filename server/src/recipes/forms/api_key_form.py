"""Make an API key on the API keys page (#150)."""

from django import forms

# How long a new key may last; blank gives it no date of its own (it still
# expires once unused for API_TOKEN_IDLE_DAYS).
DAYS_CHOICES = [
    ("", "No date: only when left unused"),
    ("30", "In 30 days"),
    ("90", "In 90 days"),
    ("365", "In a year"),
]
NAME_MAX_LENGTH = 64  # ApiToken.name; ty cannot read a model's _meta


class ApiKeyForm(forms.Form):
    """A name for the new key, and when it expires."""

    name = forms.CharField(
        label="Name",
        max_length=NAME_MAX_LENGTH,
        help_text="What it is for, e.g. “Firefox clipper”, so you know which to revoke.",
    )
    days = forms.TypedChoiceField(
        label="Expires",
        choices=DAYS_CHOICES,
        coerce=int,
        empty_value=None,
        required=False,
    )

    def clean_name(self) -> str:
        """The name as typed, without the spaces around it."""
        return self.cleaned_data["name"].strip()
