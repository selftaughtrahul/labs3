"""Let one creator rate cover a single deliverable or a bundle of several."""

import django.utils.timezone
from django.db import migrations, models


def timestamp(auto_now=False, auto_now_add=False):
    return models.DateTimeField(
        auto_now=auto_now,
        auto_now_add=auto_now_add,
        default=django.utils.timezone.now,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("creators", "0006_creator_rate"),
    ]

    operations = [
        migrations.AddField(
            model_name="country",
            name="created_at",
            field=timestamp(auto_now_add=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="country",
            name="updated_at",
            field=timestamp(auto_now=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="language",
            name="created_at",
            field=timestamp(auto_now_add=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="language",
            name="updated_at",
            field=timestamp(auto_now=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="deliverabletype",
            name="created_at",
            field=timestamp(auto_now_add=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="deliverabletype",
            name="updated_at",
            field=timestamp(auto_now=True),
            preserve_default=False,
        ),
        migrations.RemoveConstraint(
            model_name="creatorrate",
            name="creator_rate_deliverable_uniq",
        ),
        migrations.RemoveField(
            model_name="creatorrate",
            name="deliverable",
        ),
        migrations.AddField(
            model_name="creatorrate",
            name="deliverables",
            field=models.ManyToManyField(
                help_text="Choose one for an individual rate. Choose several for one combined bundle price.",
                related_name="rates",
                to="creators.deliverabletype",
                verbose_name="deliverables",
            ),
        ),
        migrations.AddField(
            model_name="creatorrate",
            name="bundle_key",
            field=models.CharField(blank=True, editable=False, max_length=1000),
        ),
        migrations.AddField(
            model_name="creatorrate",
            name="created_at",
            field=timestamp(auto_now_add=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="creatorrate",
            name="updated_at",
            field=timestamp(auto_now=True),
            preserve_default=False,
        ),
        migrations.AddConstraint(
            model_name="creatorrate",
            constraint=models.UniqueConstraint(
                condition=~models.Q(bundle_key=""),
                fields=("creator", "bundle_key"),
                name="creator_rate_bundle_uniq",
                violation_error_message="This creator already has a price for that combination.",
            ),
        ),
    ]
