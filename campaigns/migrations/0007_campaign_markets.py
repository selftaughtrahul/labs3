"""Attach campaign markets to the country list."""

from django.db import migrations, models

from creators.masters import lookup_named


def link_markets(apps, schema_editor):
    Country = apps.get_model("creators", "Country")
    Campaign = apps.get_model("campaigns", "Campaign")
    for campaign in Campaign.objects.all().iterator():
        raw = campaign.country_market_text or []
        if not isinstance(raw, list):
            continue
        countries = []
        for name in raw:
            country = lookup_named(Country, name)
            if country is not None and country not in countries:
                countries.append(country)
        if countries:
            campaign.country_market.set(countries)


class Migration(migrations.Migration):

    dependencies = [
        ("campaigns", "0006_normalize_campaign_platforms"),
        ("creators", "0005_country_language_deliverable"),
    ]

    operations = [
        migrations.RenameField(
            model_name="campaign",
            old_name="country_market",
            new_name="country_market_text",
        ),
        migrations.AddField(
            model_name="campaign",
            name="country_market",
            field=models.ManyToManyField(
                blank=True,
                help_text="Countries this brief is recruiting in.",
                related_name="campaigns",
                to="creators.country",
                verbose_name="markets",
            ),
        ),
        migrations.RunPython(link_markets, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="campaign",
            name="country_market_text",
        ),
    ]
