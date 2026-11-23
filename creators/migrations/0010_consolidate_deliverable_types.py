from django.db import migrations


def consolidate_deliverables(apps, schema_editor):
    from creators.deliverable_compact import consolidate

    consolidate()


class Migration(migrations.Migration):

    dependencies = [
        ("creators", "0009_normalize_languages"),
        ("campaigns", "0011_deal_stage_sheet_values"),
    ]

    operations = [
        migrations.RunPython(consolidate_deliverables, migrations.RunPython.noop),
    ]
