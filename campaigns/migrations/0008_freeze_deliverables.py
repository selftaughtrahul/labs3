"""Copy deliverable names onto the deal, then drop the JSON list."""

import uuid

import django.db.models.deletion
from django.db import migrations, models

from creators.masters import fold_key, folded


def freeze_deliverables(apps, schema_editor):
    DeliverableType = apps.get_model("creators", "DeliverableType")
    Deal = apps.get_model("campaigns", "CampaignCreator")
    Line = apps.get_model("campaigns", "CampaignCreatorDeliverable")
    type_ids = {fold_key(row.name): row.id for row in DeliverableType.objects.all()}
    pending = []
    rows = Deal.objects.values_list("id", "deliverables").iterator()
    for deal_id, items in rows:
        if not isinstance(items, list):
            continue
        seen = set()
        for item in items:
            text = folded(item)[:120]
            type_id = type_ids.get(fold_key(text))
            if not text or type_id is None or type_id in seen:
                continue
            seen.add(type_id)
            pending.append(
                Line(
                    campaign_creator_id=deal_id,
                    deliverable_type_id=type_id,
                    name=text,
                )
            )
            if len(pending) >= 500:
                Line.objects.bulk_create(pending)
                pending = []
    if pending:
        Line.objects.bulk_create(pending)


class Migration(migrations.Migration):

    dependencies = [
        ("campaigns", "0007_campaign_markets"),
        ("creators", "0006_creator_rate"),
    ]

    operations = [
        migrations.CreateModel(
            name="CampaignCreatorDeliverable",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=120)),
                ("campaign_creator", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="deliverable_lines", to="campaigns.campaigncreator", verbose_name="deal")),
                ("deliverable_type", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="deal_lines", to="creators.deliverabletype", verbose_name="deliverable")),
            ],
            options={
                "db_table": "campaign_creator_deliverables",
                "ordering": ["name"],
            },
        ),
        migrations.AddConstraint(
            model_name="campaigncreatordeliverable",
            constraint=models.UniqueConstraint(fields=("campaign_creator", "deliverable_type"), name="deal_deliverable_uniq", violation_error_message="This deliverable is already on that creator."),
        ),
        migrations.RunPython(freeze_deliverables, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="campaigncreator",
            name="deliverables",
        ),
    ]
