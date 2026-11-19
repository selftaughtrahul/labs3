"""Report missing creator stats and campaign brief fields. Does not change data."""

from django.core.management.base import BaseCommand
from django.db.models import Q

from campaigns.models import Campaign
from campaigns.platforms import normalize_platforms
from creators.choices import Platform
from creators.models import Creator

EXAMPLE_LIMIT = 8


class Command(BaseCommand):
    help = "Report missing creator stats, empty brief fields, and platform values outside the list."

    def handle(self, *args, **options):
        self._missing_creator_stats()
        self._missing_brief_fields()
        self._platform_values()

    def _missing_creator_stats(self):
        missing_engagement = Creator.objects.filter(engagement_rate__isnull=True)
        missing_views = Creator.objects.filter(avg_views__isnull=True)
        self.stdout.write(f"Creators missing engagement rate: {missing_engagement.count()}")
        self._examples(
            missing_engagement.order_by("influencer_name")[:EXAMPLE_LIMIT],
            lambda creator: f"{creator.influencer_name} · {creator.platform}",
        )
        self.stdout.write(f"Creators missing average views: {missing_views.count()}")
        self._examples(
            missing_views.order_by("influencer_name")[:EXAMPLE_LIMIT],
            lambda creator: f"{creator.influencer_name} · {creator.platform}",
        )

    def _missing_brief_fields(self):
        checks = (
            ("minimum followers", Q(min_followers__isnull=True)),
            ("maximum followers", Q(max_followers__isnull=True)),
            ("content type", Q(content_type="")),
            ("content format", Q(content_format="")),
        )
        for label, query in checks:
            rows = Campaign.objects.filter(query).order_by("client_name")
            self.stdout.write(f"Campaigns missing {label}: {rows.count()}")
            self._examples(rows[:EXAMPLE_LIMIT], lambda campaign: campaign.client_name)

    def _platform_values(self):
        known = set(Platform.values)
        bad = []
        for campaign in Campaign.objects.order_by("client_name"):
            stored = campaign.platforms if isinstance(campaign.platforms, list) else []
            unknown = [
                item
                for item in stored
                if not isinstance(item, str) or item not in known
            ]
            if unknown or not isinstance(campaign.platforms, list):
                slugs, dropped = normalize_platforms(campaign.platforms)
                bad.append((campaign.client_name, stored, slugs, dropped))
        self.stdout.write(f"Campaigns with platform values outside the list: {len(bad)}")
        for name, stored, slugs, dropped in bad[:EXAMPLE_LIMIT]:
            self.stdout.write(f"  {name}: {stored!r} -> {slugs!r} (drop {dropped!r})")

    def _examples(self, rows, label):
        for row in rows:
            self.stdout.write(f"  {label(row)}")
