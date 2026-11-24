"""Set creator.platform from the profile URL when that does not collide.

A profile link already stored on its real platform is left unchanged. Updating
the duplicate row would hit creator_platform_profile_uniq and would mix two
campaign deals that share one creator.
"""

from collections import defaultdict
from urllib.parse import urlsplit

from django.core.management.base import BaseCommand
from django.db import transaction

from creators.models import Creator
from creators.profile_links import canonical_link

HOSTS = (
    ("instagram.com", "instagram"),
    ("instagr.am", "instagram"),
    ("tiktok.com", "tiktok"),
    ("youtube.com", "youtube"),
    ("youtu.be", "youtube"),
    ("twitter.com", "x"),
    ("x.com", "x"),
    ("facebook.com", "facebook"),
    ("fb.com", "facebook"),
    ("fb.watch", "facebook"),
    ("linkedin.com", "linkedin"),
    ("twitch.tv", "twitch"),
    ("kick.com", "kick"),
)


def platform_from_url(link):
    host = urlsplit(link or "").netloc.lower().removeprefix("www.").split(":")[0]
    for suffix, platform in HOSTS:
        if host == suffix or host.endswith("." + suffix):
            return platform
    return ""


def cleaned_link(link):
    """Drop text that was pasted after the URL, then canonicalize."""
    raw = " ".join(str(link or "").split())
    if " " in raw:
        raw = raw.split(" ", 1)[0]
    return canonical_link(raw)


class Command(BaseCommand):
    help = "Set the platform from the profile URL when no other row already owns that profile."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the updates without writing them.",
        )

    def handle(self, *args, **options):
        creators = list(Creator.objects.only("id", "platform", "profile_link", "influencer_name"))
        by_link = defaultdict(list)
        for creator in creators:
            by_link[canonical_link(creator.profile_link).lower()].append(creator)

        claimed = set()
        updates = []
        skipped_duplicate = 0
        for creator in creators:
            inferred = platform_from_url(creator.profile_link)
            if not inferred or inferred == creator.platform:
                continue
            link = cleaned_link(creator.profile_link)
            if platform_from_url(link) != inferred:
                link = canonical_link(creator.profile_link)
            key = (inferred, link.lower())
            owners = by_link.get(canonical_link(creator.profile_link).lower(), [])
            taken = any(
                other.platform == inferred and other.pk != creator.pk for other in owners
            )
            if taken or key in claimed:
                skipped_duplicate += 1
                continue
            # The cleaned URL can already belong to a different row.
            cleaned_owners = by_link.get(link.lower(), [])
            if any(other.platform == inferred and other.pk != creator.pk for other in cleaned_owners):
                skipped_duplicate += 1
                continue
            claimed.add(key)
            creator.platform = inferred
            if link and link != creator.profile_link:
                creator.profile_link = link
            updates.append(creator)

        self.stdout.write(
            f"{len(updates)} profiles will take the platform in their URL. "
            f"{skipped_duplicate} duplicates were left in place."
        )
        for creator in updates[:30]:
            self.stdout.write(
                f"  {creator.influencer_name} -> {creator.platform} {creator.profile_link}"
            )
        if len(updates) > 30:
            self.stdout.write(f"  ... {len(updates) - 30} more")
        if options["dry_run"] or not updates:
            return
        with transaction.atomic():
            Creator.objects.bulk_update(updates, ["platform", "profile_link"], batch_size=400)
        self.stdout.write(self.style.SUCCESS(f"Updated {len(updates)} creators."))
