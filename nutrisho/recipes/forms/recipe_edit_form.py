import math
import re

from django import forms, http

from recipes.models import Recipe

MIN_NUMBER_STEP_FIELDS = 4
EXTRA_BLANK_STEP_FIELDS = 2

MIN_NUMBER_GROUPS = 2
EXTRA_BLANK_GROUPS = 1

PREFIX_STEP = "step"
PREFIX_GROUP = "group"
PREFIX_INGREDIENT = "ingredient"


class RecipeEditForm(forms.ModelForm):
    class Meta:
        model = Recipe
        fields = ["recipe_name", "short_description"]

    recipe_name = forms.CharField(required=False, max_length=200)
    short_description = forms.CharField(required=False, max_length=512, widget=forms.Textarea)

    def __init__(self, *args, **kwargs):
        extra_fields = {}
        is_mutable = not isinstance(args[0], http.request.QueryDict)
        steps = kwargs["instance"].step.all()
        for i in range(len(steps)):
            field_name = f"{PREFIX_STEP}-{i}"
            try:
                field_text = args[0][field_name]
            except KeyError:
                try:
                    field_text = steps[i].step_text
                except IndexError:
                    field_text = ""

            extra_fields[field_name] = forms.CharField(
                required=False,
                widget=forms.Textarea(
                    attrs={
                        "style": f"height: {_textarea_height(field_text)}px;",
                    }
                ),
            )
            if is_mutable:
                args[0][field_name] = field_text

        for j in range(i + 1, max(MIN_NUMBER_STEP_FIELDS, i + 1 + EXTRA_BLANK_STEP_FIELDS)):
            field_name = "step-%s" % (j,)
            extra_fields[field_name] = forms.CharField(required=False, widget=forms.Textarea)

        groups = kwargs["instance"].ingredients_group.all()
        for i in range(len(groups)):
            group_field_name = f"{PREFIX_GROUP}-{i}"
            try:
                field_text = groups[i].group_name
            except IndexError:
                field_text = ""
            extra_fields[group_field_name] = forms.CharField(required=False)
            if is_mutable:
                args[0][group_field_name] = field_text

            ingredients = groups[i].ingredient.all()
            for j in range(len(ingredients)):
                ingredient_field_name = f"{PREFIX_GROUP}-{i}-{PREFIX_INGREDIENT}-{j}-quantity"
                field_text = (
                    "{0:.2g}".format(ingredients[j].quantity) if ingredients[j].quantity else ""
                )
                extra_fields[ingredient_field_name] = forms.CharField(
                    required=False,
                    widget=forms.TextInput(attrs={"class": "ingredient-quantity"}),
                )
                if is_mutable:
                    args[0][ingredient_field_name] = field_text

                ingredient_field_name = f"{PREFIX_GROUP}-{i}-{PREFIX_INGREDIENT}-{j}-unit"
                field_text = ingredients[j].unit or ""
                extra_fields[ingredient_field_name] = forms.CharField(
                    required=False,
                    widget=forms.TextInput(attrs={"class": "ingredient-unit"}),
                )
                if is_mutable:
                    args[0][ingredient_field_name] = field_text

                ingredient_field_name = f"{PREFIX_GROUP}-{i}-{PREFIX_INGREDIENT}-{j}-name"
                field_text = ingredients[j].ingredient.ingredient_name or ""
                extra_fields[ingredient_field_name] = forms.CharField(
                    required=False,
                    widget=forms.TextInput(attrs={"class": "ingredient-name"}),
                )
                if is_mutable:
                    args[0][ingredient_field_name] = field_text

                ingredient_field_name = f"{PREFIX_GROUP}-{i}-{PREFIX_INGREDIENT}-{j}-preparation"
                field_text = ingredients[j].preparation or ""
                extra_fields[ingredient_field_name] = forms.CharField(
                    required=False,
                    widget=forms.TextInput(attrs={"class": "ingredient-preparation"}),
                )
                if is_mutable:
                    args[0][ingredient_field_name] = field_text

        # for j in range(i + 1, max(MIN_NUMBER_GROUPS, i + 1 + EXTRA_BLANK_GROUPS)):
        #     field_name = "group-%s" % (j,)
        #     extra_fields[field_name] = forms.CharField(
        #         required=False, widget=forms.Textarea
        #     )

        # putting super here so that args contains all the initial values
        super().__init__(*args, **kwargs)
        if len(extra_fields):
            self.fields.update(extra_fields)

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

    def get_groups(self):
        group_matcher = re.compile(rf"{PREFIX_GROUP}-\d+")
        for field_name in self.fields:
            if field_name.startswith(PREFIX_GROUP):
                is_group = group_matcher.fullmatch(field_name)
                is_first_of_ingredients = field_name.endswith("-quantity")
                is_last_of_ingredients = field_name.endswith("-preparation")
                yield self[field_name], is_group, is_first_of_ingredients, is_last_of_ingredients


def _textarea_height(sentence: str) -> int:
    CHARS_PER_LINE = 64
    MIN_PIX_HEIGHT = 54
    PIX_PER_EXTRA_LINE = 30
    how_many_lines = math.ceil(len(sentence) / CHARS_PER_LINE)
    if how_many_lines < 3:
        return MIN_PIX_HEIGHT
    return MIN_PIX_HEIGHT + (how_many_lines - 2) * PIX_PER_EXTRA_LINE
