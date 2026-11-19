"""Move the single rate card onto one row per deliverable."""

import uuid

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


def copy_rate_cards(apps, schema_editor):
    Creator = apps.get_model("creators", "Creator")
    DeliverableType = apps.get_model("creators", "DeliverableType")
    CreatorRate = apps.get_model("creators", "CreatorRate")
    priced = list(Creator.objects.exclude(rate_card_price=None))
    if not priced:
        return
    kind, _created = DeliverableType.objects.get_or_create(name="Unspecified")
    CreatorRate.objects.bulk_create(
        [
            CreatorRate(
                creator_id=creator.id,
                deliverable_id=kind.id,
                price=creator.rate_card_price,
                currency=creator.rate_currency,
            )
            for creator in priced
            if creator.rate_currency
        ]
    )


class Migration(migrations.Migration):

    dependencies = [
        ("creators", "0005_country_language_deliverable"),
    ]

    operations = [
        migrations.CreateModel(
            name="CreatorRate",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("price", models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(0)])),
                ("currency", models.CharField(choices=[("USD", "USD"), ("EUR", "EUR"), ("GBP", "GBP"), ("INR", "INR"), ("BRL", "BRL"), ("AUD", "AUD"), ("PLN", "PLN"), ("PHP", "PHP"), ("SGD", "SGD"), ("CHF", "CHF"), ("USDT", "USDT"), ("AED", "AED"), ("PKR", "PKR"), ("TRY", "TRY"), ("MXN", "MXN"), ("CAD", "CAD"), ("COP", "COP"), ("SEK", "SEK"), ("ARS", "ARS")], max_length=8)),
                ("creator", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="rates", to="creators.creator")),
                ("deliverable", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="rates", to="creators.deliverabletype")),
            ],
            options={
                "db_table": "creator_rates",
                "ordering": ["deliverable__name"],
            },
        ),
        migrations.AddConstraint(
            model_name="creatorrate",
            constraint=models.UniqueConstraint(fields=("creator", "deliverable"), name="creator_rate_deliverable_uniq", violation_error_message="This creator already has a price for that deliverable."),
        ),
        migrations.AddConstraint(
            model_name="creatorrate",
            constraint=models.CheckConstraint(condition=models.Q(currency__in=["USD", "EUR", "GBP", "INR", "BRL", "AUD", "PLN", "PHP", "SGD", "CHF", "USDT", "AED", "PKR", "TRY", "MXN", "CAD", "COP", "SEK", "ARS"]), name="creator_rate_currency_known"),
        ),
        migrations.RunPython(copy_rate_cards, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="creator",
            name="creator_rate_has_currency",
        ),
        migrations.RemoveField(
            model_name="creator",
            name="rate_card_price",
        ),
        migrations.RemoveField(
            model_name="creator",
            name="rate_currency",
        ),
    ]
