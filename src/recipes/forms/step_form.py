from django import forms

from recipes.models import Step


class StepForm(forms.ModelForm):
    class Meta:
        model = Step
        fields = ["step_text"]
        widgets = {"step_text": forms.Textarea(attrs={"rows": 3, "placeholder": "New step"})}
