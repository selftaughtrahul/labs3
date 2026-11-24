from django.conf import settings
from django.db import migrations, models


PLACEHOLDER_USERNAMES = ("sheet", "old_database")
PLACEHOLDER_DEAL_NAME = "Old Database"


def clear_placeholder_users(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Campaign = apps.get_model("campaigns", "Campaign")
    Creator = apps.get_model("creators", "Creator")
    CampaignCreator = apps.get_model("campaigns", "CampaignCreator")
    user_ids = list(
        User.objects.filter(username__in=PLACEHOLDER_USERNAMES).values_list("pk", flat=True)
    )
    if user_ids:
        Campaign.objects.filter(campaign_owner_id__in=user_ids).update(campaign_owner=None)
        Campaign.objects.filter(created_by_id__in=user_ids).update(created_by=None)
        Creator.objects.filter(added_by_id__in=user_ids).update(added_by=None)
        Campaign.poc.through.objects.filter(user_id__in=user_ids).delete()
        Campaign.scouting_team.through.objects.filter(user_id__in=user_ids).delete()
        User.objects.filter(pk__in=user_ids).delete()
    CampaignCreator.objects.filter(added_by__iexact=PLACEHOLDER_DEAL_NAME).update(added_by="")
    CampaignCreator.objects.filter(assigned_to__iexact=PLACEHOLDER_DEAL_NAME).update(assigned_to="")


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("creators", "0010_consolidate_deliverable_types"),
        ("campaigns", "0011_deal_stage_sheet_values"),
    ]

    operations = [
        migrations.AlterField(
            model_name="campaign",
            name="campaign_owner",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.PROTECT,
                related_name="owned_campaigns",
                to=settings.AUTH_USER_MODEL,
                verbose_name="team lead",
            ),
        ),
        migrations.RunPython(clear_placeholder_users, migrations.RunPython.noop),
    ]
