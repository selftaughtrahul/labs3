from django.db import migrations, models


STAGES = [
    "shortlisted",
    "contacted",
    "follow_up",
    "replied",
    "negotiating",
    "verbal_agreement",
    "confirmed",
    "shared_with_client",
    "not_interested",
    "unresponsive",
    "not_started",
    "in_progress",
    "approved",
    "completed",
    "cancelled",
]


class Migration(migrations.Migration):

    dependencies = [
        ("campaigns", "0010_campaign_schema_refresh"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="campaigncreator",
            name="deal_stage_known",
        ),
        migrations.AlterField(
            model_name="campaigncreator",
            name="stage",
            field=models.CharField(
                choices=[
                    ("shortlisted", "Shortlisted"),
                    ("contacted", "Contacted"),
                    ("follow_up", "Follow-up"),
                    ("replied", "Replied"),
                    ("negotiating", "Negotiating"),
                    ("verbal_agreement", "Verbal agreement"),
                    ("confirmed", "Confirmed"),
                    ("shared_with_client", "Shared with client"),
                    ("not_interested", "Not interested"),
                    ("unresponsive", "Unresponsive"),
                    ("not_started", "Not started"),
                    ("in_progress", "In progress"),
                    ("approved", "Approved"),
                    ("completed", "Completed"),
                    ("cancelled", "Cancelled"),
                ],
                default="shortlisted",
                max_length=32,
            ),
        ),
        migrations.AddConstraint(
            model_name="campaigncreator",
            constraint=models.CheckConstraint(
                condition=models.Q(("stage__in", STAGES)),
                name="deal_stage_known",
            ),
        ),
    ]
