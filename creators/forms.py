"""Admin form helpers for comma-separated lists stored as JSON."""

from django import forms
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet

from creators.lists import clean_string_list
from creators.models import Creator, CreatorRate


class StringListField(forms.CharField):
    """One text box for a list. 'beauty, skincare' is stored as ["beauty", "skincare"]."""

    def to_python(self, value):
        return clean_string_list(super().to_python(value))

    def prepare_value(self, value):
        if isinstance(value, list):
            return ", ".join(value)
        return "" if value is None else value


def use_checkboxes(form, name, choices):
    """Replace a JSON list field with a set of checkboxes."""
    source = form.fields[name]
    form.fields[name] = forms.MultipleChoiceField(
        choices=choices,
        required=source.required,
        widget=forms.CheckboxSelectMultiple,
        label=source.label,
        help_text=source.help_text,
    )


class CommaListForm(forms.ModelForm):
    """Swap named JSON fields for StringListField. Subclasses set comma_list_fields."""

    comma_list_fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in self.comma_list_fields:
            source = self.fields[name]
            self.fields[name] = StringListField(
                required=source.required,
                label=source.label,
                help_text=source.help_text,
            )


class CreatorAdminForm(CommaListForm):
    comma_list_fields = ("niche",)

    class Meta:
        model = Creator
        fields = "__all__"


class CreatorRateForm(forms.ModelForm):
    class Meta:
        model = CreatorRate
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        deliverables = list(cleaned.get("deliverables") or [])
        if not deliverables:
            raise ValidationError(
                {"deliverables": "Choose one deliverable, or several for a combined price."}
            )
        creator = cleaned.get("creator") or getattr(self.instance, "creator", None)
        if creator is None or not getattr(creator, "pk", None):
            return cleaned
        ids = [item.pk for item in deliverables]
        rate = self.instance
        rate.creator = creator
        if rate.same_bundle_exists(ids):
            raise ValidationError(
                {"deliverables": "This creator already has a price for that combination."}
            )
        return cleaned


class CreatorRateFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        seen = []
        for form in self.forms:
            if not hasattr(form, "cleaned_data") or form.cleaned_data.get("DELETE"):
                continue
            deliverables = form.cleaned_data.get("deliverables")
            if not deliverables:
                continue
            ids = tuple(sorted(item.pk for item in deliverables))
            if ids in seen:
                form.add_error("deliverables", "This combination is already on the rate card.")
            seen.append(ids)
