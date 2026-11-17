"""Normalize the deck's text[] columns. Both apps store them as a JSON list."""

from django.core.exceptions import ValidationError


def clean_string_list(value):
    """Return a de-duplicated list of stripped strings, in first-seen order."""
    if value is None or value == "" or value == []:
        return []
    if isinstance(value, str):
        parts = value.split(",")
    elif isinstance(value, (list, tuple)):
        parts = value
    else:
        raise ValidationError("Enter text values separated by commas.")

    cleaned = []
    for part in parts:
        if not isinstance(part, str):
            raise ValidationError("Enter text values separated by commas.")
        text = " ".join(part.split())
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def cleaned(field_name, cleaner, value):
    """Run a cleaner and attach its error to one form field."""
    try:
        return cleaner(value)
    except ValidationError as exc:
        raise ValidationError({field_name: exc.messages}) from exc


def clean_country_code(value):
    if not value:
        return ""
    code = "".join(str(value).split()).upper()
    if len(code) != 2 or not code.isalpha():
        raise ValidationError("Use a 2-letter country code, for example DE.")
    return code


def clean_country_codes(value):
    codes = [clean_country_code(code) for code in clean_string_list(value)]
    return [code for code in codes if code]
