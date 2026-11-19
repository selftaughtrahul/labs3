"""Rewrite known campaign platform aliases and drop tokens that match nothing."""

from django.db import migrations

from campaigns.platforms import normalize_platforms


def normalize_campaign_platforms(apps, schema_editor):
    Campaign = apps.get_model("campaigns", "Campaign")
    for campaign in Campaign.objects.all().order_by("client_name"):
        slugs, unknown = normalize_platforms(campaign.platforms)
        stored = campaign.platforms if isinstance(campaign.platforms, list) else []
        if slugs == stored and not unknown:
            continue
        print(
            f"{campaign.client_name}: {stored!r} -> {slugs!r} dropped {unknown!r}"
        )
        campaign.platforms = slugs
        campaign.save(update_fields=["platforms"])


class Migration(migrations.Migration):

    dependencies = [
        ("campaigns", "0005_clientshare_clientshareitem_outreach_and_more"),
    ]

    operations = [
        migrations.RunPython(normalize_campaign_platforms, migrations.RunPython.noop),
    ]
