from django import forms

from recipes.models import Step


class StepForm(forms.ModelForm):
    class Meta:
        model = Step
        fields = ["step_text"]
