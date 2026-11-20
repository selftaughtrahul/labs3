"""Load the centralised spreadsheet into users, creators, campaigns, and deals.

Repeated platform + profile + campaign rows keep the last filled values.
Staff names in Who Added become accounts with password 12345.
"""

from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import close_old_connections, connection

from campaigns.deliverables import replace_deliverable_lines_bulk
from campaigns.models import Campaign, CampaignCreator, CampaignStatus
from campaigns.sheet_status import map_deal_stage
from creators.choices import Currency, Platform, Tier
from creators.lists import clean_string_list
from creators.masters import MasterCache
from creators.models import Country, Creator, Language
from creators.profile_links import canonical_link, profile_key
from creators.rates import ensure_rates

DEFAULT_SHEET = Path(r"C:\Users\rahul\Downloads\Awisee Main DataBase.xlsx")
CENTRAL_TAB = "Centralised Database"
DEFAULT_PASSWORD = "12345"
SOURCE = "sheet"

PLATFORM_ALIASES = {
    "instagram": Platform.INSTAGRAM,
    "youtube": Platform.YOUTUBE,
    "tiktok": Platform.TIKTOK,
    "twitch": Platform.TWITCH,
    "x": Platform.X,
    "twitter": Platform.X,
    "facebook": Platform.FACEBOOK,
    "linkedin": Platform.LINKEDIN,
    "kick": Platform.KICK,
}
TIER_ALIASES = {
    "nano": Tier.NANO,
    "micro": Tier.MICRO,
    "mid-tier": Tier.MID,
    "mid tier": Tier.MID,
    "macro": Tier.MACRO,
    "mega": Tier.MEGA,
    "user": Tier.USER,
}
CURRENCY_ALIASES = {
    "R$": Currency.BRL,
    "TL": Currency.TRY,
    "£": Currency.GBP,
    "$": Currency.USD,
    "€": Currency.EUR,
}
HEADER_ALIASES = {
    "Date Added\n(DD/MM/YYYY)": "date_added",
    "Who Added": "who_added",
    "Platform": "platform",
    "Profile Link": "profile_link",
    "Influencer Name": "influencer_name",
    "Niche / Vertical": "niche",
    "Country": "country",
    "Language": "language",
    "Followers": "followers",
    "Tiers": "tier",
    "Campaign": "campaign",
    "Email": "email",
    "Other Contact": "other_contact",
    "Email outreached": "email_outreached",
    "Outreach Status": "outreach_status",
    "Sent Date": "sent_date",
    "DATE CONFIRMED": "date_confirmed",
    "Comments": "comments",
    "Currency": "currency",
    "Price": "price",
    "Amount in EUR": "amount_eur",
    "Deliverables": "deliverables",
    "Deliverables Notes": "deliverables_notes",
    "Engagement Rate": "engagement_rate",
    "Audience Insights": "audience_insights",
    "Avg Views": "avg_views",
    "GEO": "geo",
    "Female %": "female_pct",
    "Male %": "male_pct",
    "Profile Checked": "profile_checked",
    "FX Lock Date": "fx_lock_date",
}
FOLDED_HEADERS = {
    re.sub(r"[^a-z0-9]+", " ", key.lower()).strip(): value
    for key, value in HEADER_ALIASES.items()
}


def username_from_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug[:150] or "sheet"


def sheet_text(value) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    return " ".join(str(value).split())


def header_field(name) -> str:
    text = " ".join(str(name or "").split())
    if text in HEADER_ALIASES:
        return HEADER_ALIASES[text]
    return FOLDED_HEADERS.get(re.sub(r"[^a-z0-9]+", " ", text.lower()).strip(), "")


def name_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def cell(row: dict, key: str) -> str:
    return sheet_text(row.get(key))


def parse_date(value: str):
    text = cell({"v": value}, "v")
    if not text:
        return None
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_int(value: str):
    text = re.sub(r"[^\d]", "", cell({"v": value}, "v"))
    if not text:
        return None
    return int(text)


def parse_decimal(value: str, maximum=None):
    text = cell({"v": value}, "v")
    if not text:
        return None
    text = text.replace(",", "")
    text = re.sub(r"[€$£%]", "", text)
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        number = Decimal(match.group(0))
    except InvalidOperation:
        return None
    if maximum is not None and number > maximum:
        return None
    if number < 0:
        return None
    return number


def parse_bool(value: str):
    text = cell({"v": value}, "v").lower()
    if text in {"true", "yes", "1"}:
        return True
    if text in {"false", "no", "0"}:
        return False
    return None


def parse_platform(value: str):
    return PLATFORM_ALIASES.get(cell({"v": value}, "v").lower())


def parse_tier(value: str):
    return TIER_ALIASES.get(cell({"v": value}, "v").lower())


def parse_currency(value: str):
    text = cell({"v": value}, "v")
    if not text:
        return ""
    if text in CURRENCY_ALIASES:
        return CURRENCY_ALIASES[text]
    upper = text.upper()
    if upper in Currency.values:
        return upper
    return CURRENCY_ALIASES.get(upper, "")


def parse_stage(value: str):
    stage, _outreach, _known = map_deal_stage(value)
    return stage


def parse_email(value: str) -> str:
    text = cell({"v": value}, "v")
    if not text:
        return ""
    try:
        validate_email(text)
    except ValidationError:
        return ""
    return text


def parse_url(value: str) -> str:
    return canonical_link(value)


def filled(value) -> bool:
    if value is None:
        return False
    if value == "":
        return False
    if value == []:
        return False
    return True


def normalize_budget(price, currency, price_eur):
    if price is not None:
        price = price.quantize(Decimal("0.01"))
    if price_eur is not None:
        price_eur = price_eur.quantize(Decimal("0.01"))
    if price is None or not currency:
        return None, "", None
    if currency == Currency.EUR:
        return price, currency, price
    if price_eur is None:
        return None, "", None
    return price, currency, price_eur


def keep_last(current, incoming):
    return incoming if filled(incoming) else current


def map_row(raw: dict) -> dict | None:
    platform = parse_platform(raw.get("platform", ""))
    profile_link = parse_url(raw.get("profile_link", ""))
    if not platform or not profile_link:
        return None
    name = cell(raw, "influencer_name") or profile_link
    currency = parse_currency(raw.get("currency", ""))
    price = parse_decimal(raw.get("price", ""))
    price_eur = parse_decimal(raw.get("amount_eur", ""))
    if price is not None and currency == Currency.EUR and price_eur is None:
        price_eur = price
    email = parse_email(raw.get("email", ""))
    other_contact = cell(raw, "other_contact")
    raw_email = cell(raw, "email")
    if raw_email and not email:
        other_contact = ", ".join(part for part in (other_contact, raw_email) if part)
    return {
        "who_added": cell(raw, "who_added"),
        "platform": platform,
        "profile_link": profile_link,
        "influencer_name": name[:200],
        "niche": clean_string_list(raw.get("niche", "")),
        "country": cell(raw, "country")[:50],
        "language": cell(raw, "language")[:120] or "English",
        "followers": parse_int(raw.get("followers", "")),
        "tier": parse_tier(raw.get("tier", "")) or "",
        "campaign": cell(raw, "campaign"),
        "email": email,
        "other_contact": other_contact[:250],
        "email_outreached": cell(raw, "email_outreached")[:150],
        "stage": parse_stage(sheet_text(raw.get("outreach_status", ""))),
        "sent_date": parse_date(raw.get("sent_date", "")),
        "date_confirmed": parse_date(raw.get("date_confirmed", "")),
        "comments": (raw.get("comments") or "").strip(),
        "currency": currency,
        "price": price,
        "price_eur": price_eur,
        "deliverables": clean_string_list(raw.get("deliverables", "")),
        "deliverables_notes": (raw.get("deliverables_notes") or "").strip(),
        "engagement_rate": parse_decimal(raw.get("engagement_rate", ""), maximum=Decimal("100")),
        "audience_insights": (raw.get("audience_insights") or "").strip(),
        "avg_views": parse_int(raw.get("avg_views", "")),
        "geo": cell(raw, "geo")[:120],
        "female_pct": parse_decimal(raw.get("female_pct", ""), maximum=Decimal("100")),
        "male_pct": parse_decimal(raw.get("male_pct", ""), maximum=Decimal("100")),
        "profile_checked": parse_bool(raw.get("profile_checked", "")),
        "added_at": parse_date(raw.get("date_added", "")),
        "fx_lock_date": parse_date(raw.get("fx_lock_date", "")),
    }


def merge_profile(current: dict | None, row: dict) -> dict:
    if current is None:
        profile = {
            key: row[key]
            for key in (
                "platform",
                "profile_link",
                "influencer_name",
                "niche",
                "country",
                "language",
                "followers",
                "tier",
                "email",
                "other_contact",
                "engagement_rate",
                "audience_insights",
                "avg_views",
                "geo",
                "female_pct",
                "male_pct",
                "profile_checked",
                "added_at",
                "who_added",
            )
        }
        profile["profile_checked"] = bool(row["profile_checked"])
        return profile
    merged = dict(current)
    for key in (
        "influencer_name",
        "niche",
        "country",
        "language",
        "followers",
        "tier",
        "email",
        "other_contact",
        "engagement_rate",
        "audience_insights",
        "avg_views",
        "geo",
        "female_pct",
        "male_pct",
        "added_at",
        "who_added",
    ):
        merged[key] = keep_last(current[key], row[key])
    if row["profile_checked"]:
        merged["profile_checked"] = True
    elif current["profile_checked"] is None:
        merged["profile_checked"] = bool(row["profile_checked"])
    return merged


class Command(BaseCommand):
    help = "Import Centralised Database from Awisee Main DataBase.xlsx"

    def add_arguments(self, parser):
        parser.add_argument("path", nargs="?", default=str(DEFAULT_SHEET))
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.is_file():
            raise CommandError(f"Sheet not found: {path}")

        rows, skipped = self._read_sheet(path)
        profiles, deals, campaign_owners, names = self._collapse(rows)
        self.stdout.write(
            f"Sheet rows {len(rows) + skipped}, skipped {skipped}, "
            f"creators {len(profiles)}, campaigns {len(campaign_owners)}, "
            f"deals {len(deals)} after collapsing duplicates."
        )
        if options["dry_run"]:
            self._preview(profiles, deals, campaign_owners)
            return

        self._touch_db()
        self.countries = MasterCache(Country)
        self.languages = MasterCache(Language)
        self.countries.ensure(profile["country"] for profile in profiles.values())
        self.languages.ensure(
            [profile["language"] for profile in profiles.values()] + ["English"]
        )
        self.stdout.write("Masters loaded.")
        self._touch_db()
        users = self._ensure_users(names)
        campaign_map = self._save_campaigns(campaign_owners, users)
        self.stdout.write(f"Campaigns ready ({len(campaign_map)}).")
        self._touch_db()
        creator_map = self._save_creators(profiles, users)
        self.stdout.write(f"Creators stored ({len(creator_map)}).")
        self._touch_db()
        created_deals = self._save_deals(deals, campaign_map, creator_map)
        self.stdout.write(f"Deals stored ({created_deals}).")
        self._touch_db()
        created_rates = self._save_rates(deals, creator_map)
        self.stdout.write(f"Rates +{created_rates}.")
        self._set_creators_needed(campaign_map)

        staff_count = len({user.pk for user in users.values()})
        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {staff_count} staff users, {len(creator_map)} creators, "
                f"{len(campaign_map)} campaigns, {created_deals} deals, "
                f"{created_rates} rates."
            )
        )

    def _read_sheet(self, path: Path) -> tuple[list[dict], int]:
        if path.suffix.lower() == ".csv":
            with path.open(newline="", encoding="utf-8-sig") as handle:
                table = list(csv.reader(handle))
        else:
            table = self._xlsx_rows(path)
        if not table:
            return [], 0
        keys = [header_field(name) for name in table[0]]
        rows = []
        skipped = 0
        for raw in table[1:]:
            mapped = {
                keys[index]: sheet_text(raw[index])
                for index in range(min(len(keys), len(raw)))
                if keys[index]
            }
            link = mapped.get("profile_link") or ""
            if "DO NOT DELETE" in link.upper() or "do not add" in link.lower():
                skipped += 1
                continue
            parsed = map_row(mapped)
            if parsed is None:
                skipped += 1
                continue
            rows.append(parsed)
        return rows, skipped

    def _xlsx_rows(self, path: Path):
        import openpyxl

        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            if CENTRAL_TAB not in workbook.sheetnames:
                raise CommandError(f"Tab {CENTRAL_TAB} not found in {path}")
            return [list(row) for row in workbook[CENTRAL_TAB].iter_rows(values_only=True)]
        finally:
            workbook.close()

    def _collapse(self, rows: list[dict]):
        profiles = {}
        deals = {}
        owners = defaultdict(list)
        names = Counter()
        campaign_labels = {}
        for row in rows:
            who = row["who_added"]
            if who:
                names[who] += 1
            key = profile_key(row["platform"], row["profile_link"])
            profiles[key] = merge_profile(profiles.get(key), row)
            campaign = row["campaign"]
            if not campaign:
                continue
            campaign_key = name_key(campaign)
            campaign_labels[campaign_key] = campaign
            owners[campaign_key].append(who)
            deals[(key[0], key[1], campaign_key)] = row
        campaign_owners = {
            campaign_labels[campaign_key]: Counter(
                [name for name in people if name]
            ).most_common(1)[0][0]
            if any(people)
            else ""
            for campaign_key, people in owners.items()
        }
        return profiles, deals, campaign_owners, names

    def _ensure_users(self, names: Counter) -> dict:
        User = get_user_model()
        users = {}
        wanted = set(names) | {"sheet"}
        wanted.discard("")
        for name in sorted(wanted):
            username = username_from_name(name)
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": name[:150],
                    "is_staff": True,
                    "is_active": True,
                },
            )
            if created:
                user.set_password(DEFAULT_PASSWORD)
                user.save(update_fields=["password"])
            users[name] = user
            users[username] = user
        return users

    def _touch_db(self):
        close_old_connections()
        connection.ensure_connection()

    def _save_campaigns(self, campaign_owners: dict, users: dict) -> dict:
        fallback = users["sheet"]
        existing = {name_key(item.client_name): item for item in Campaign.objects.all()}
        saved = {}
        for name, owner_name in sorted(campaign_owners.items()):
            key = name_key(name)
            owner = users.get(owner_name, fallback)
            campaign = existing.get(key)
            if campaign is None:
                campaign = Campaign.objects.create(
                    client_name=name,
                    campaign_owner=owner,
                    created_by=owner,
                    status=CampaignStatus.NOT_STARTED,
                    creators_needed=1,
                )
                existing[key] = campaign
            elif not campaign.campaign_owner_id:
                campaign.campaign_owner = owner
                campaign.save(update_fields=["campaign_owner"])
            saved[key] = campaign
        return saved

    def _save_creators(self, profiles: dict, users: dict) -> dict:
        fallback = users["sheet"]
        existing = {}
        for creator in Creator.objects.select_related("country", "language", "added_by"):
            link = canonical_link(creator.profile_link)
            if link:
                existing[profile_key(creator.platform, link)] = creator
        to_create = []
        to_update = []
        saved = dict(existing)
        for key, profile in profiles.items():
            added_by = users.get(profile["who_added"], fallback) if profile["who_added"] else fallback
            creator = existing.get(key)
            if creator is None:
                to_create.append(self._new_creator(profile, added_by))
                continue
            if self._fill_creator(creator, profile, added_by):
                to_update.append(creator)
            saved[key] = creator
        for start in range(0, len(to_create), 400):
            batch = to_create[start : start + 400]
            Creator.objects.bulk_create(batch)
            for creator in batch:
                saved[profile_key(creator.platform, creator.profile_link)] = creator
        if to_update:
            Creator.objects.bulk_update(
                to_update,
                [
                    "influencer_name",
                    "niche",
                    "country",
                    "language",
                    "followers",
                    "tier",
                    "email",
                    "other_contact",
                    "engagement_rate",
                    "audience_insights",
                    "avg_views",
                    "geo",
                    "female_pct",
                    "male_pct",
                    "is_profile_checked",
                    "source",
                    "added_by",
                    "added_at",
                ],
                batch_size=400,
            )
        return saved

    def _new_creator(self, profile, added_by):
        return Creator(
            platform=profile["platform"],
            profile_link=profile["profile_link"],
            influencer_name=profile["influencer_name"],
            niche=profile["niche"],
            country=self.countries.get(profile["country"]),
            language=self.languages.get(profile["language"] or "English"),
            followers=profile["followers"],
            tier=profile["tier"],
            email=profile["email"],
            other_contact=profile["other_contact"],
            engagement_rate=profile["engagement_rate"],
            audience_insights=profile["audience_insights"],
            avg_views=profile["avg_views"],
            geo=profile["geo"],
            female_pct=profile["female_pct"],
            male_pct=profile["male_pct"],
            is_profile_checked=bool(profile["profile_checked"]),
            source=SOURCE,
            added_by=added_by,
            added_at=profile["added_at"],
        )

    def _fill_creator(self, creator, profile, added_by):
        changed = False

        def put(field, value):
            nonlocal changed
            if not filled(value):
                return
            if getattr(creator, field) != value:
                setattr(creator, field, value)
                changed = True

        put("influencer_name", profile["influencer_name"])
        put("niche", profile["niche"])
        put("country", self.countries.get(profile["country"]))
        if profile["language"]:
            put("language", self.languages.get(profile["language"]))
        put("followers", profile["followers"])
        put("tier", profile["tier"])
        put("email", profile["email"])
        put("other_contact", profile["other_contact"])
        put("engagement_rate", profile["engagement_rate"])
        put("audience_insights", profile["audience_insights"])
        put("avg_views", profile["avg_views"])
        put("geo", profile["geo"])
        put("female_pct", profile["female_pct"])
        put("male_pct", profile["male_pct"])
        if profile["profile_checked"]:
            put("is_profile_checked", True)
        if not creator.source:
            put("source", SOURCE)
        if creator.added_by_id is None:
            put("added_by", added_by)
        put("added_at", profile["added_at"])
        return changed

    def _save_deals(self, deals: dict, campaigns: dict, creators: dict) -> int:
        existing = {
            (deal.campaign_id, deal.creator_id): deal
            for deal in CampaignCreator.objects.all()
        }
        to_create = []
        to_update = []
        line_deals = []
        for (platform, link, campaign_key), row in deals.items():
            campaign = campaigns[campaign_key]
            creator = creators[(platform, link)]
            price, currency, price_eur = normalize_budget(
                row["price"], row["currency"], row["price_eur"]
            )
            current = existing.get((campaign.id, creator.id))
            if current is None:
                deal = CampaignCreator(
                    campaign=campaign,
                    creator=creator,
                    stage=row["stage"],
                    deliverables_notes=row["deliverables_notes"],
                    assigned_to=row["who_added"],
                    email_outreached=row["email_outreached"],
                    sent_date=row["sent_date"],
                    fx_lock_date=row["fx_lock_date"],
                    creator_price=price,
                    creator_currency=currency,
                    creator_price_eur=price_eur if currency else None,
                    date_confirmed=row["date_confirmed"],
                    client_remarks=row["comments"],
                    added_by=row["who_added"],
                )
                to_create.append(deal)
                if row["deliverables"]:
                    deal._sheet_deliverables = row["deliverables"]
                    line_deals.append(deal)
                continue
            changed = False
            if row["stage"] and current.stage != row["stage"]:
                current.stage = row["stage"]
                changed = True
            if row["deliverables_notes"] and not current.deliverables_notes:
                current.deliverables_notes = row["deliverables_notes"]
                changed = True
            if row["who_added"]:
                current.assigned_to = row["who_added"]
                current.added_by = row["who_added"]
                changed = True
            if row["email_outreached"] and not current.email_outreached:
                current.email_outreached = row["email_outreached"]
                changed = True
            if row["sent_date"] and not current.sent_date:
                current.sent_date = row["sent_date"]
                changed = True
            if row["fx_lock_date"] and not current.fx_lock_date:
                current.fx_lock_date = row["fx_lock_date"]
                changed = True
            if row["date_confirmed"] and not current.date_confirmed:
                current.date_confirmed = row["date_confirmed"]
                changed = True
            if row["comments"] and not current.client_remarks:
                current.client_remarks = row["comments"]
                changed = True
            if current.creator_price is None and price is not None:
                current.creator_price = price
                current.creator_currency = currency
                current.creator_price_eur = price_eur if currency else None
                changed = True
            if current.creator_price_eur is None or current.client_price_eur is None:
                if current.margin_eur is not None:
                    current.margin_eur = None
                    changed = True
            else:
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
                    "deliverables_notes",
                    "assigned_to",
                    "email_outreached",
                    "sent_date",
                    "fx_lock_date",
                    "creator_price",
                    "creator_currency",
                    "creator_price_eur",
                    "date_confirmed",
                    "client_remarks",
                    "added_by",
                    "margin_eur",
                ],
                batch_size=400,
            )
        replace_deliverable_lines_bulk(
            [(deal, deal._sheet_deliverables) for deal in line_deals]
        )
        return len(to_create) + len(to_update)

    def _save_rates(self, deals, creators):
        rows = []
        for (platform, link, _campaign), row in deals.items():
            price, currency, _eur = normalize_budget(
                row["price"], row["currency"], row["price_eur"]
            )
            rows.append(
                (creators.get((platform, link)), row["deliverables"], price, currency)
            )
        return ensure_rates(rows)

    def _preview(self, profiles, deals, campaign_owners):
        existing_creators = {
            profile_key(creator.platform, canonical_link(creator.profile_link))
            for creator in Creator.objects.all().only("platform", "profile_link")
            if canonical_link(creator.profile_link)
        }
        existing_campaigns = {
            name_key(name) for name in Campaign.objects.values_list("client_name", flat=True)
        }
        new_creators = sum(1 for key in profiles if key not in existing_creators)
        new_campaigns = sum(
            1 for name in campaign_owners if name_key(name) not in existing_campaigns
        )
        priced = sum(1 for row in deals.values() if row["price"] and row["deliverables"])
        self.stdout.write(
            f"Dry run: {new_creators} new creators, {len(profiles) - new_creators} already stored, "
            f"{new_campaigns} new campaigns, {len(deals)} deals, "
            f"{priced} rows with a rate to add if missing."
        )

    def _set_creators_needed(self, campaigns: dict):
        for campaign in campaigns.values():
            needed = campaign.deals.count() or 1
            if campaign.creators_needed != needed:
                campaign.creators_needed = needed
                campaign.save(update_fields=["creators_needed"])
