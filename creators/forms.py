"""Admin form helpers for comma-separated lists stored as JSON."""

from django import forms

from creators.lists import clean_string_list
from creators.models import Creator


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
