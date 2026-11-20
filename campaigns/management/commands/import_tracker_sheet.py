"""Load Creator Tracking from Influencer Tracker - Main into creators and deals."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections, connection

from campaigns.deliverables import replace_deliverable_lines_bulk
from campaigns.management.commands.import_prospecting_sheet import (
    filled,
    name_key,
    parse_day,
    parse_email,
    parse_money,
    parse_percent,
    parse_whole,
    plain,
)
from campaigns.models import Campaign, CampaignCreator, CampaignStatus
from campaigns.sheet_status import map_deal_stage
from creators.lists import clean_string_list
from creators.masters import MasterCache
from creators.management.commands.import_central_sheet import (
    keep_last,
    normalize_budget,
    parse_currency,
    parse_platform,
    parse_tier,
    username_from_name,
)
from creators.models import Country, Creator, Language
from creators.profile_links import canonical_link, profile_key
from creators.rates import ensure_rates

DEFAULT_SHEET = Path(r"C:\Users\rahul\Downloads\Influencer Tracker - Main (1).xlsx")
SOURCE = "tracker"
TRACKING_TAB = "Creator Tracking"
HEADER_FIELDS = {
    "campaign name": "campaign",
    "team lead": "team_lead",
    "campaign owner": "who",
    "full name of creator": "name",
    "profile link": "profile_link",
    "platform": "platform",
    "country": "country",
    "followers": "followers",
    "tier": "tier",
    "tiers": "tier",
    "engagement rate": "engagement_rate",
    "handle": "handle",
    "email": "email",
    "workflow stage": "status",
    "currency": "currency",
    "content type": "deliverables",
    "deliverable notes": "deliverables_notes",
    "notes": "comments",
    "last updated": "added_at",
}


def header_key(value) -> str:
    return re.sub(r"[^a-z0-9]+", " ", plain(value).lower()).strip()


def field_for(header: str) -> str:
    if header in HEADER_FIELDS:
        return HEADER_FIELDS[header]
    if header.startswith("agency fee"):
        return ""
    if header.startswith("creator fee") and header.endswith("eur"):
        return "price_eur"
    if header.startswith("total fee") and header.endswith("eur"):
        return "client_price_eur"
    if header.startswith("creator fee"):
        return "price"
    if header.startswith("total fee"):
        return "client_price"
    return ""


class Command(BaseCommand):
    help = "Import Creator Tracking from Influencer Tracker - Main."

    def add_arguments(self, parser):
        parser.add_argument("path", nargs="?", default=str(DEFAULT_SHEET))
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.is_file():
            raise CommandError(f"Workbook not found: {path}")
        rows, skipped, unknown = self._read(path)
        profiles, deals, names = self._collapse(rows)
        self.stdout.write(
            f"Rows {len(rows) + skipped}, skipped {skipped}, "
            f"creators {len(profiles)}, deals {len(deals)}, campaigns {len(names)}."
        )
        if unknown:
            self.stdout.write("Unmapped statuses: " + ", ".join(sorted(unknown)))
        if options["dry_run"]:
            self._preview(profiles, deals, names)
            return
        self._touch_db()
        self.countries = MasterCache(Country)
        self.languages = MasterCache(Language)
        self.countries.ensure(profile["country"] for profile in profiles.values())
        self.languages.ensure(["English"])
        self.stdout.write("Masters loaded.")
        users = self._users()
        campaigns = self._campaigns(names, deals, users)
        self.stdout.write(f"Campaigns ready ({len(campaigns)}).")
        creators = self._creators(profiles, users)
        self.stdout.write(f"Creators stored ({len(creators)}).")
        new_deals, updated_deals = self._deals(deals, campaigns, creators)
        self.stdout.write(f"Deals +{new_deals} updated {updated_deals}.")
        new_rates = self._rates(deals, creators)
        self.stdout.write(f"Rates +{new_rates}.")
        self.stdout.write(
            self.style.SUCCESS(
                f"Creators {len(creators)}. Deals +{new_deals} updated {updated_deals}. "
                f"Rates +{new_rates}."
            )
        )

    def _read(self, path: Path):
        import openpyxl

        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            if TRACKING_TAB not in workbook.sheetnames:
                raise CommandError(f"Tab {TRACKING_TAB} not found in {path}")
            table = workbook[TRACKING_TAB].iter_rows(values_only=True)
            header = [header_key(cell) for cell in next(table)]
            fields = [field_for(name) for name in header]
            rows = []
            skipped = 0
            unknown = set()
            for raw in table:
                mapped = {
                    fields[index]: raw[index]
                    for index in range(min(len(fields), len(raw)))
                    if fields[index]
                }
                parsed = self._parse_row(mapped, unknown)
                if parsed is None:
                    skipped += 1
                    continue
                rows.append(parsed)
        finally:
            workbook.close()
        return rows, skipped, unknown

    def _parse_row(self, raw, unknown):
        platform = parse_platform(plain(raw.get("platform")))
        link = canonical_link(raw.get("profile_link"))
        if not platform or not link:
            return None
        stage, _outreach, known = map_deal_stage(raw.get("status"))
        if not known:
            label = header_key(raw.get("status"))
            if label:
                unknown.add(label)
        email = parse_email(raw.get("email"))
        currency = parse_currency(plain(raw.get("currency")))
        price = parse_money(raw.get("price"))
        price_eur = parse_money(raw.get("price_eur"))
        if price is not None and currency == "EUR" and price_eur is None:
            price_eur = price
        price, currency, price_eur = normalize_budget(price, currency, price_eur)
        client_price = parse_money(raw.get("client_price"))
        client_price_eur = parse_money(raw.get("client_price_eur"))
        client_currency = currency
        if client_price is not None and client_currency == "EUR" and client_price_eur is None:
            client_price_eur = client_price
        client_price, client_currency, client_price_eur = normalize_budget(
            client_price, client_currency if client_price is not None else "", client_price_eur
        )
        deliverables = clean_string_list(plain(raw.get("deliverables")))
        name = plain(raw.get("name")) or plain(raw.get("handle")) or link
        return {
            "who": plain(raw.get("who"))[:150] or plain(raw.get("team_lead"))[:150],
            "platform": platform,
            "profile_link": link,
            "name": name[:200],
            "country": plain(raw.get("country"))[:50],
            "followers": parse_whole(raw.get("followers")),
            "tier": parse_tier(plain(raw.get("tier"))) or "",
            "campaign": plain(raw.get("campaign"))[:200],
            "email": email,
            "stage": stage,
            "status_known": known,
            "price": price,
            "currency": currency,
            "price_eur": price_eur,
            "client_price": client_price,
            "client_currency": client_currency,
            "client_price_eur": client_price_eur,
            "deliverables": deliverables,
            "deliverables_notes": plain(raw.get("deliverables_notes")),
            "engagement_rate": parse_percent(raw.get("engagement_rate")),
            "comments": plain(raw.get("comments")),
            "added_at": parse_day(raw.get("added_at")),
        }

    def _collapse(self, rows):
        profiles = {}
        deals = {}
        names = set()
        for row in rows:
            key = profile_key(row["platform"], row["profile_link"])
            profiles[key] = self._merge_profile(profiles.get(key), row)
            if not row["campaign"]:
                continue
            names.add(row["campaign"])
            deals[(key[0], key[1], name_key(row["campaign"]))] = row
        return profiles, deals, names

    def _merge_profile(self, current, row):
        fields = ("name", "country", "followers", "tier", "email", "engagement_rate", "added_at", "who")
        if current is None:
            return {field: row[field] for field in fields} | {
                "platform": row["platform"],
                "profile_link": row["profile_link"],
            }
        merged = dict(current)
        for field in fields:
            merged[field] = keep_last(current[field], row[field])
        return merged

    def _users(self):
        User = get_user_model()
        by_username = {}
        by_name = {}
        for user in User.objects.all():
            by_username[user.username.lower()] = user
            if user.first_name:
                by_name[user.first_name.casefold()] = user
        return by_username, by_name

    def _find_user(self, users, name):
        by_username, by_name = users
        if not name:
            return None
        return by_username.get(username_from_name(name)) or by_name.get(name.casefold())

    def _fallback_user(self, users):
        User = get_user_model()
        found = self._find_user(users, "sheet")
        if found:
            return found
        user, created = User.objects.get_or_create(
            username="sheet",
            defaults={"first_name": "sheet", "is_staff": True, "is_active": True},
        )
        if created:
            user.set_password("12345")
            user.save(update_fields=["password"])
        return user

    def _touch_db(self):
        close_old_connections()
        connection.ensure_connection()

    def _campaigns(self, names, deals, users):
        existing = {name_key(item.client_name): item for item in Campaign.objects.all()}
        owners = defaultdict(list)
        for (_platform, _link, campaign_key), row in deals.items():
            if row["who"]:
                owners[campaign_key].append(row["who"])
        saved = dict(existing)
        fallback = self._fallback_user(users)
        for name in sorted(names):
            key = name_key(name)
            if key in saved:
                continue
            owner_name = Counter(owners[key]).most_common(1)[0][0] if owners[key] else ""
            owner = self._find_user(users, owner_name) or fallback
            saved[key] = Campaign.objects.create(
                client_name=name,
                campaign_owner=owner,
                created_by=owner,
                status=CampaignStatus.NOT_STARTED,
                creators_needed=1,
            )
        return saved

    def _creators(self, profiles, users):
        existing = {}
        for creator in Creator.objects.select_related("country", "language"):
            link = canonical_link(creator.profile_link)
            if link:
                existing[profile_key(creator.platform, link)] = creator
        saved = dict(existing)
        fallback = self._fallback_user(users)
        for key, profile in profiles.items():
            creator = saved.get(key)
            added_by = self._find_user(users, profile["who"]) or fallback
            if creator is None:
                creator = Creator.objects.create(
                    platform=profile["platform"],
                    profile_link=profile["profile_link"],
                    influencer_name=profile["name"],
                    country=self.countries.get(profile["country"]),
                    language=self.languages.get("English"),
                    followers=profile["followers"],
                    tier=profile["tier"],
                    email=profile["email"],
                    engagement_rate=profile["engagement_rate"],
                    source=SOURCE,
                    added_by=added_by,
                    added_at=profile["added_at"],
                )
                saved[key] = creator
                continue
            changed = False

            def put(field, value):
                nonlocal changed
                if not filled(value):
                    return
                if getattr(creator, field) != value:
                    setattr(creator, field, value)
                    changed = True

            if profile["name"] and not profile["name"].startswith("http"):
                put("influencer_name", profile["name"])
            put("country", self.countries.get(profile["country"]))
            put("followers", profile["followers"])
            put("tier", profile["tier"])
            put("email", profile["email"])
            put("engagement_rate", profile["engagement_rate"])
            put("added_at", profile["added_at"])
            if not creator.source:
                put("source", SOURCE)
            if creator.added_by_id is None:
                put("added_by", added_by)
            if changed:
                creator.save()
        return saved

    def _deals(self, deals, campaigns, creators):
        existing = {
            (deal.campaign_id, deal.creator_id): deal
            for deal in CampaignCreator.objects.all()
        }
        to_create = []
        to_update = []
        line_deals = []
        for (platform, link, campaign_key), row in deals.items():
            campaign = campaigns.get(campaign_key)
            creator = creators.get((platform, link))
            if campaign is None or creator is None:
                continue
            current = existing.get((campaign.id, creator.id))
            if current is None:
                deal = CampaignCreator(
                    campaign=campaign,
                    creator=creator,
                    stage=row["stage"],
                    fit_notes=row["comments"],
                    deliverables_notes=row["deliverables_notes"],
                    assigned_to=row["who"],
                    creator_price=row["price"],
                    creator_currency=row["currency"],
                    creator_price_eur=row["price_eur"],
                    client_price=row["client_price"],
                    client_currency=row["client_currency"],
                    client_price_eur=row["client_price_eur"],
                    added_by=row["who"],
                )
                if deal.creator_price_eur is not None and deal.client_price_eur is not None:
                    deal.margin_eur = deal.client_price_eur - deal.creator_price_eur
                to_create.append(deal)
                if row["deliverables"]:
                    deal._sheet_deliverables = row["deliverables"]
                    line_deals.append(deal)
                continue
            changed = False
            if row["stage"] and current.stage != row["stage"]:
                current.stage = row["stage"]
                changed = True
            if row["comments"] and not current.fit_notes:
                current.fit_notes = row["comments"]
                changed = True
            if row["deliverables_notes"] and not current.deliverables_notes:
                current.deliverables_notes = row["deliverables_notes"]
                changed = True
            if row["who"]:
                current.assigned_to = row["who"]
                current.added_by = row["who"]
                changed = True
            if current.creator_price is None and row["price"] is not None:
                current.creator_price = row["price"]
                current.creator_currency = row["currency"]
                current.creator_price_eur = row["price_eur"]
                changed = True
            if current.client_price is None and row["client_price"] is not None:
                current.client_price = row["client_price"]
                current.client_currency = row["client_currency"]
                current.client_price_eur = row["client_price_eur"]
                changed = True
            if current.creator_price_eur is not None and current.client_price_eur is not None:
                margin = current.client_price_eur - current.creator_price_eur
                if current.margin_eur != margin:
                    current.margin_eur = margin
                    changed = True
            if changed:
                to_update.append(current)
            if row["deliverables"]:
                current._sheet_deliverables = row["deliverables"]
                line_deals.append(current)
        for start in range(0, len(to_create), 400):
            CampaignCreator.objects.bulk_create(to_create[start : start + 400])
        if to_update:
            CampaignCreator.objects.bulk_update(
                to_update,
                [
                    "stage",
                    "fit_notes",
                    "deliverables_notes",
                    "assigned_to",
                    "creator_price",
                    "creator_currency",
                    "creator_price_eur",
                    "client_price",
                    "client_currency",
                    "client_price_eur",
                    "added_by",
                    "margin_eur",
                ],
                batch_size=400,
            )
        replace_deliverable_lines_bulk(
            [(deal, deal._sheet_deliverables) for deal in line_deals]
        )
        return len(to_create), len(to_update)

    def _rates(self, deals, creators):
        return ensure_rates(
            [
                (
                    creators.get((platform, link)),
                    row["deliverables"],
                    row["price"],
                    row["currency"],
                )
                for (platform, link, _campaign), row in deals.items()
            ]
        )

    def _preview(self, profiles, deals, names):
        existing_creators = {
            profile_key(creator.platform, canonical_link(creator.profile_link))
            for creator in Creator.objects.all().only("platform", "profile_link")
            if canonical_link(creator.profile_link)
        }
        existing_campaigns = {
            name_key(name) for name in Campaign.objects.values_list("client_name", flat=True)
        }
        new_creators = sum(1 for key in profiles if key not in existing_creators)
        new_campaigns = sum(1 for name in names if name_key(name) not in existing_campaigns)
        priced = sum(1 for row in deals.values() if row["price"] and row["deliverables"])
        self.stdout.write(
            f"Dry run: {new_creators} new creators, {len(profiles) - new_creators} already stored, "
            f"{new_campaigns} new campaigns, {len(deals)} deals, "
            f"{priced} rows with a rate to add if missing."
        )
