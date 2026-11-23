from django.db import migrations

from creators.masters import (
    LANGUAGE_MERGES,
    drop_unused_language,
    insert_missing_iso_languages,
    merge_language_names,
)


def normalize_languages(apps, schema_editor):
    Language = apps.get_model("creators", "Language")
    Creator = apps.get_model("creators", "Creator")
    for source_name, target_name in LANGUAGE_MERGES:
        merge_language_names(Language, Creator, source_name, target_name)
    drop_unused_language(Language, Creator, "Portuguese")
    insert_missing_iso_languages(Language)


class Migration(migrations.Migration):

    dependencies = [
        ("creators", "0008_creator_rate_label"),
    ]

    operations = [
        migrations.RunPython(normalize_languages, migrations.RunPython.noop),
    ]
