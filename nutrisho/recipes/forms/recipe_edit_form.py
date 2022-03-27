from django import forms
import math

from recipes.models import Recipe, Step

EXTRA_BLANK_FIELDS = 2
PREFIX_STEP = "step"


class RecipeEditForm(forms.ModelForm):
    class Meta:
        model = Recipe
        fields = ["name", "short_description"]

    name = forms.CharField(required=False, max_length=200)
    short_description = forms.CharField(
        required=False, max_length=512, widget=forms.Textarea
    )

    def __init__(self, *args, **kwargs):
        steps = kwargs["instance"].step.all()
        step_fields = {}
        for i in range(len(steps)):
            field_name = f"{PREFIX_STEP}-{i}"
            try:
                field_text = steps[i].step_text
            except IndexError:
                field_text = ""
            step_fields[field_name] = forms.CharField(
                required=False,
                widget=forms.Textarea(
                    attrs={
                        "style": f"height: {_textarea_height(field_text)}px;",
                    }
                ),
            )
            args[0][field_name] = field_text

        for j in range(i + 1, i + 1 + EXTRA_BLANK_FIELDS):
            field_name = "step-%s" % (j,)
            step_fields[field_name] = forms.CharField(
                required=False, widget=forms.Textarea
            )
        super().__init__(*args, **kwargs)
        if len(step_fields):
            self.fields.update(step_fields)

        print("000000000000000000000000000000000000000000000000000000000")
        print(self.initial)
        print(args)
        print(kwargs)
        print(steps)

    def clean(self):
        interests = set()
        i = 0
        field_name = "interest_%s" % (i,)
        while self.cleaned_data.get(field_name):
            interest = self.cleaned_data[field_name]
            if interest in interests:
                self.add_error(field_name, "Duplicate")
            else:
                interests.add(interest)
            i += 1
            field_name = "interest_%s" % (i,)

    #    self.cleaned_data[“interests”] = interests

    def get_step_fields(self):
        for field_name in self.fields:
            if field_name.startswith(PREFIX_STEP):
                yield self[field_name]


def _textarea_height(sentence: str) -> int:
    CHARS_PER_LINE = 64
    MIN_PIX_HEIGHT = 54
    PIX_PER_EXTRA_LINE = 30
    how_many_lines = math.ceil(len(sentence) / CHARS_PER_LINE)
    if how_many_lines < 3:
        return MIN_PIX_HEIGHT
    return MIN_PIX_HEIGHT + (how_many_lines - 2) * PIX_PER_EXTRA_LINE
