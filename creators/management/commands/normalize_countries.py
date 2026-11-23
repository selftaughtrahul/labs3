"""Merge country spelling variants and insert missing official names."""

from django.core.management.base import BaseCommand
from django.db import transaction

from campaigns.models import Campaign
from creators.countries import (
    CANONICAL_SET,
    EUROPE_CREATOR_COUNTRIES,
    JUNK_LABEL_REPLACEMENTS,
    OFFICIAL_COUNTRIES,
    canonical_country_name,
    resolved_country_names,
)
from creators.masters import fold_key, lookup_named
from creators.models import Country, Creator


class Command(BaseCommand):
    help = (
        "Point creators and campaign markets at one official country spelling, "
        "then add official countries that are still missing."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the moves and inserts without writing.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        with transaction.atomic():
            moved, renamed, deleted, inserted = self._normalize()
            junk_moved, junk_deleted = self._drop_junk_labels()
            if dry_run:
                transaction.set_rollback(True)
        prefix = "Would " if dry_run else ""
        self.stdout.write(f"{prefix}move {moved + junk_moved} creator or market links")
        self.stdout.write(f"{prefix}rename {renamed} countries")
        self.stdout.write(f"{prefix}delete {deleted + junk_deleted} duplicate countries")
        self.stdout.write(f"{prefix}insert {inserted} missing countries")

    def _normalize(self):
        groups = {}
        for country in Country.objects.order_by("pk"):
            canon = canonical_country_name(country.name)
            groups.setdefault(fold_key(canon), {"canon": canon, "rows": []})
            groups[fold_key(canon)]["rows"].append(country)

        moved = 0
        renamed = 0
        deleted = 0
        through = Campaign.country_market.through

        for info in groups.values():
            canon = info["canon"]
            rows = info["rows"]
            if canon not in CANONICAL_SET:
                continue
            keeper = next((row for row in rows if row.name == canon), None)
            if keeper is None:
                keeper = rows[0]
                if keeper.name != canon:
                    self.stdout.write(f"Rename {keeper.name!r} to {canon!r}")
                    keeper.name = canon
                    keeper.save(update_fields=["name"])
                    renamed += 1

            extras = [row for row in rows if row.pk != keeper.pk]
            for extra in extras:
                creator_ids = list(
                    Creator.objects.filter(country_id=extra.pk).values_list("pk", flat=True)
                )
                if creator_ids:
                    Creator.objects.filter(pk__in=creator_ids).update(country_id=keeper.pk)
                    moved += len(creator_ids)
                    self.stdout.write(
                        f"Move {len(creator_ids)} creators from {extra.name!r} to {canon!r}"
                    )

                campaign_ids = list(
                    through.objects.filter(country_id=extra.pk).values_list(
                        "campaign_id", flat=True
                    )
                )
                if campaign_ids:
                    already = set(
                        through.objects.filter(
                            country_id=keeper.pk,
                            campaign_id__in=campaign_ids,
                        ).values_list("campaign_id", flat=True)
                    )
                    drop_count = through.objects.filter(
                        country_id=extra.pk,
                        campaign_id__in=already,
                    ).delete()[0]
                    keep_ids = [cid for cid in campaign_ids if cid not in already]
                    relinked = through.objects.filter(country_id=extra.pk).update(
                        country_id=keeper.pk
                    )
                    moved += relinked + drop_count
                    self.stdout.write(
                        f"Move {len(keep_ids)} campaign markets from {extra.name!r} "
                        f"to {canon!r} (drop {len(already)} already linked)"
                    )

                self.stdout.write(f"Delete duplicate {extra.name!r}")
                extra.delete()
                deleted += 1

        existing = {
            fold_key(canonical_country_name(name))
            for name in Country.objects.values_list("name", flat=True)
        }
        missing = [
            Country(name=name)
            for name in OFFICIAL_COUNTRIES
            if fold_key(name) not in existing
        ]
        if missing:
            Country.objects.bulk_create(missing, batch_size=400)
            for country in missing:
                self.stdout.write(f"Insert {country.name!r}")
        return moved, renamed, deleted, len(missing)

    def _country(self, name):
        return lookup_named(Country, name)

    def _drop_junk_labels(self):
        moved = 0
        deleted = 0
        through = Campaign.country_market.through
        junk_rows = [
            country
            for country in Country.objects.all()
            if country.name.casefold() in JUNK_LABEL_REPLACEMENTS
        ]
        for extra in junk_rows:
            replacements = [
                self._country(name)
                for name in resolved_country_names(extra.name)
            ]
            replacements = [row for row in replacements if row is not None]
            creators = list(Creator.objects.filter(country_id=extra.pk))
            for creator in creators:
                target = self._creator_replacement(creator, replacements)
                Creator.objects.filter(pk=creator.pk).update(
                    country_id=target.pk if target else None
                )
                moved += 1
                label = target.name if target else "blank"
                self.stdout.write(
                    f"Move creator {creator.influencer_name!r} from {extra.name!r} to {label!r}"
                )

            campaign_ids = list(
                through.objects.filter(country_id=extra.pk).values_list(
                    "campaign_id", flat=True
                )
            )
            for campaign_id in campaign_ids:
                for keeper in replacements:
                    if through.objects.filter(
                        campaign_id=campaign_id, country_id=keeper.pk
                    ).exists():
                        continue
                    through.objects.create(campaign_id=campaign_id, country_id=keeper.pk)
                    moved += 1
                    self.stdout.write(
                        f"Add market {keeper.name!r} in place of {extra.name!r}"
                    )
            dropped = through.objects.filter(country_id=extra.pk).delete()[0]
            if dropped:
                self.stdout.write(
                    f"Drop {dropped} campaign markets labeled {extra.name!r}"
                )
            self.stdout.write(f"Delete leftover {extra.name!r}")
            extra.delete()
            deleted += 1
        return moved, deleted

    def _creator_replacement(self, creator, replacements):
        override = EUROPE_CREATOR_COUNTRIES.get(
            " ".join((creator.influencer_name or "").split()).casefold()
        )
        if override:
            return self._country(override)
        if replacements:
            return replacements[0]
        return None
