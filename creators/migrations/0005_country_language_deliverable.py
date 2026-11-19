"""Move country and language onto dropdown rows, and seed deliverable names."""

from django.db import migrations, models
import django.db.models.deletion

from creators.masters import fold_key, group_names


def seed_masters(apps, schema_editor):
    Country = apps.get_model("creators", "Country")
    Language = apps.get_model("creators", "Language")
    DeliverableType = apps.get_model("creators", "DeliverableType")
    Creator = apps.get_model("creators", "Creator")
    Campaign = apps.get_model("campaigns", "Campaign")
    Deal = apps.get_model("campaigns", "CampaignCreator")

    country_values = list(Creator.objects.values_list("country_text", flat=True))
    for markets in Campaign.objects.values_list("country_market", flat=True):
        if isinstance(markets, list):
            country_values.extend(markets)
    language_values = list(Creator.objects.values_list("language_text", flat=True))
    language_values.append("English")
    deliverable_values = ["Reel", "Story"]
    for items in Deal.objects.values_list("deliverables", flat=True).iterator():
        if isinstance(items, list):
            deliverable_values.extend(items)

    country_ids = {}
    for key, label in group_names(country_values).items():
        country_ids[key] = Country.objects.create(name=label).id
    language_ids = {}
    for key, label in group_names(language_values).items():
        language_ids[key] = Language.objects.create(name=label).id
    for label in group_names(deliverable_values).values():
        DeliverableType.objects.create(name=label)

    creator_ids = list(Creator.objects.values_list("pk", flat=True))
    for start in range(0, len(creator_ids), 500):
        batch = list(Creator.objects.filter(pk__in=creator_ids[start : start + 500]))
        for creator in batch:
            creator.country_id = country_ids.get(fold_key(creator.country_text))
            creator.language_id = language_ids.get(fold_key(creator.language_text))
        Creator.objects.bulk_update(batch, ["country", "language"])


class Migration(migrations.Migration):

    dependencies = [
        ("creators", "0004_remove_creator_creator_rate_has_currency_and_more"),
        ("campaigns", "0006_normalize_campaign_platforms"),
    ]

    operations = [
        migrations.CreateModel(
            name="Country",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, unique=True)),
            ],
            options={
                "verbose_name_plural": "countries",
                "db_table": "countries",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="Language",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, unique=True)),
            ],
            options={
                "db_table": "languages",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="DeliverableType",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, unique=True)),
            ],
            options={
                "db_table": "deliverable_types",
                "ordering": ["name"],
            },
        ),
        migrations.RenameField(
            model_name="creator",
            old_name="country",
            new_name="country_text",
        ),
        migrations.RenameField(
            model_name="creator",
            old_name="language",
            new_name="language_text",
        ),
        migrations.AddField(
            model_name="creator",
            name="country",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="creators",
                to="creators.country",
            ),
        ),
        migrations.AddField(
            model_name="creator",
            name="language",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="creators",
                to="creators.language",
            ),
        ),
        migrations.RunPython(seed_masters, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="creator",
            name="country_text",
        ),
        migrations.RemoveField(
            model_name="creator",
            name="language_text",
        ),
    ]
