"""Store tracker and brief columns on the campaign, and allow tracker statuses."""

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("campaigns", "0008_freeze_deliverables"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="campaign",
            name="campaign_status_known",
        ),
        migrations.AlterField(
            model_name="campaign",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("pre_campaign", "Pre-campaign"),
                    ("scouting", "Scouting"),
                    ("outreach", "Outreach"),
                    ("active", "Active"),
                    ("client_sharing", "Client sharing"),
                    ("awaiting_payment", "Awaiting payment"),
                    ("on_hold", "On hold"),
                    ("unresponsive", "Unresponsive"),
                    ("cancelled", "Cancelled"),
                    ("closed", "Closed"),
                ],
                default="draft",
                max_length=32,
            ),
        ),
        migrations.AddConstraint(
            model_name="campaign",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    status__in=[
                        "draft",
                        "pre_campaign",
                        "scouting",
                        "outreach",
                        "active",
                        "client_sharing",
                        "awaiting_payment",
                        "on_hold",
                        "unresponsive",
                        "cancelled",
                        "closed",
                    ]
                ),
                name="campaign_status_known",
            ),
        ),
        migrations.AddField(
            model_name="campaign",
            name="age_range",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="campaign",
            name="budget_amount",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=14,
                null=True,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name="budget",
            ),
        ),
        migrations.AddField(
            model_name="campaign",
            name="budget_currency",
            field=models.CharField(
                blank=True,
                choices=[
                    ("USD", "USD"),
                    ("EUR", "EUR"),
                    ("GBP", "GBP"),
                    ("INR", "INR"),
                    ("BRL", "BRL"),
                    ("AUD", "AUD"),
                    ("PLN", "PLN"),
                    ("PHP", "PHP"),
                    ("SGD", "SGD"),
                    ("CHF", "CHF"),
                    ("USDT", "USDT"),
                    ("AED", "AED"),
                    ("PKR", "PKR"),
                    ("TRY", "TRY"),
                    ("MXN", "MXN"),
                    ("CAD", "CAD"),
                    ("COP", "COP"),
                    ("SEK", "SEK"),
                    ("ARS", "ARS"),
                ],
                max_length=8,
                verbose_name="budget currency",
            ),
        ),
        migrations.AddField(
            model_name="campaign",
            name="budget_eur",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=14,
                null=True,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name="budget in EUR",
            ),
        ),
        migrations.AddField(
            model_name="campaign",
            name="cf_list",
            field=models.CharField(blank=True, max_length=250, verbose_name="CF list"),
        ),
        migrations.AddField(
            model_name="campaign",
            name="client_poc_name",
            field=models.CharField(blank=True, max_length=150, verbose_name="client contact"),
        ),
        migrations.AddField(
            model_name="campaign",
            name="deadline",
            field=models.DateField(blank=True, null=True, verbose_name="campaign deadline"),
        ),
        migrations.AddField(
            model_name="campaign",
            name="last_update_on",
            field=models.DateField(blank=True, null=True, verbose_name="last update"),
        ),
        migrations.AddField(
            model_name="campaign",
            name="list_submitted",
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="campaign",
            name="notes",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="campaign",
            name="poc",
            field=models.CharField(blank=True, max_length=150, verbose_name="POC"),
        ),
        migrations.AddField(
            model_name="campaign",
            name="priority",
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="campaign",
            name="ready_for_dev",
            field=models.BooleanField(blank=True, null=True, verbose_name="ready for the team"),
        ),
        migrations.AddField(
            model_name="campaign",
            name="scouting_team",
            field=models.CharField(blank=True, max_length=250),
        ),
        migrations.AddField(
            model_name="campaign",
            name="second_poc",
            field=models.CharField(blank=True, max_length=150, verbose_name="second POC"),
        ),
        migrations.AddField(
            model_name="campaign",
            name="start_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="campaign",
            name="team_lead",
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AddField(
            model_name="campaign",
            name="view_consistency",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="campaign",
            name="working_sheet",
            field=models.CharField(blank=True, max_length=250),
        ),
    ]
