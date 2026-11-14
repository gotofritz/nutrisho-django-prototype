"""The upload on the import page (#78)."""

from django import forms

from recipes.services.recipe_document import ImportBatch, ImportFormatError, parse_json

# A thousand-recipe export is a few MB; this only stops a mistaken upload.
MAX_IMPORT_BYTES = 20 * 1024 * 1024


class RecipeImportForm(forms.Form):
    """A Nutrisho export or a JSON-LD file; a valid form's `file` is the read `ImportBatch`."""

    file = forms.FileField(
        label="File to import",
        help_text="A Nutrisho export, or schema.org Recipe JSON-LD from a recipe page.",
        widget=forms.FileInput(
            attrs={"accept": ".json,.jsonld,application/json,application/ld+json"}
        ),
    )

    def clean_file(self) -> ImportBatch:
        """Read the upload, or say why it cannot be imported."""
        upload = self.cleaned_data["file"]
        if upload.size > MAX_IMPORT_BYTES:
            msg = f"The file is over {MAX_IMPORT_BYTES // (1024 * 1024)} MB."
            raise forms.ValidationError(msg)
        try:
            return parse_json(upload.read())
        except ImportFormatError as exc:
            raise forms.ValidationError(str(exc)) from exc
