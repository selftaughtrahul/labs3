"""Set creator.country_id from a sheet, using the country master."""

import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from creators.masters import MasterCache
from creators.models import Country, Creator
from creators.profile_links import profile_key


class Command(BaseCommand):
    help = "Point each listed creator at the country master row for the sheet's country name."

    def add_arguments(self, parser):
        parser.add_argument(
            "path",
            nargs="?",
            default="creators_with_country.csv",
            help="CSV with platform, profile_link, and country columns.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the country ids that would be saved without writing them.",
        )

    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.is_file():
            raise CommandError(f"Sheet not found: {path}")
        with path.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))

        countries = MasterCache(Country).ensure(row.get("country", "") for row in rows)
        by_key = {}
        for creator in Creator.objects.only("id", "platform", "profile_link", "country_id"):
            key = profile_key(creator.platform, creator.profile_link)
            if key[1]:
                by_key.setdefault(key, []).append(creator)

        chosen = {}
        blank = 0
        missing = 0
        unknown = 0
        for row in rows:
            label = (row.get("country") or "").strip()
            if not label:
                blank += 1
                continue
            country = countries.get(label)
            if country is None:
                unknown += 1
                self.stdout.write(f"UNKNOWN {label}")
                continue
            key = profile_key((row.get("platform") or "").strip().lower(), row.get("profile_link") or "")
            creators = by_key.get(key) or []
            if not creators:
                missing += 1
                self.stdout.write(f"MISSING {row.get('name') or ''} {row.get('profile_link') or ''}")
                continue
            for creator in creators:
                chosen[creator.pk] = (creator, country)

        updates = []
        unchanged = 0
        for creator, country in chosen.values():
            if creator.country_id == country.pk:
                unchanged += 1
                continue
            creator.country_id = country.pk
            updates.append(creator)

        if updates and not options["dry_run"]:
            Creator.objects.bulk_update(updates, ["country_id"], batch_size=400)
        verb = "Would set" if options["dry_run"] else "Set"
        self.stdout.write(
            f"{verb} {len(updates)} unchanged {unchanged} blank {blank} "
            f"missing {missing} unknown {unknown}"
        )
