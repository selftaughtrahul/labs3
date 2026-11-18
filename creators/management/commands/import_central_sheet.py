"""Load the centralised spreadsheet into users, creators, campaigns, and deals.

Repeated platform + profile + campaign rows keep the last filled values.
Staff names in Who Added become accounts with password 12345.
"""

from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction

from campaigns.models import Campaign, CampaignCreator, CampaignStatus, Stage
from creators.choices import Currency, Platform, Tier
from creators.lists import clean_string_list
from creators.models import Creator

DEFAULT_SHEET = Path(
    r"C:\Users\rahul\Downloads\Awisee Main DataBase - Centralised Database.csv"
)
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
STAGE_ALIASES = {
    "confirmed": Stage.CONFIRMED,
    "negotiating": Stage.NEGOTIATING,
    "sent": Stage.CONTACTED,
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


def username_from_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug[:150] or "sheet"


def cell(row: dict, key: str) -> str:
    return " ".join((row.get(key) or "").split())


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
    text = cell({"v": value}, "v").lower()
    if not text:
        return Stage.SHORTLISTED
    return STAGE_ALIASES.get(text, Stage.SHORTLISTED)


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
    text = (value or "").strip()
    if not text:
        return ""
    if not re.match(r"^https?://", text, re.I):
        text = f"https://{text}"
    return text[:500]


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
        "stage": parse_stage(raw.get("outreach_status", "")),
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
    help = "Import Awisee Main DataBase - Centralised Database.csv"

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
            return

        with transaction.atomic():
            users = self._ensure_users(names)
            campaign_map = self._save_campaigns(campaign_owners, users)
            creator_map = self._save_creators(profiles, users)
            created_deals = self._save_deals(deals, campaign_map, creator_map)
            self._set_creators_needed(campaign_map)

        staff_count = len({user.pk for user in users.values()})
        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {staff_count} staff users, {len(creator_map)} creators, "
                f"{len(campaign_map)} campaigns, {created_deals} deals."
            )
        )

    def _read_sheet(self, path: Path) -> tuple[list[dict], int]:
        rows = []
        skipped = 0
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.reader(handle)
            header = next(reader)
            keys = [HEADER_ALIASES.get(name, "") for name in header]
            for raw in reader:
                mapped = {
                    keys[index]: raw[index]
                    for index in range(min(len(keys), len(raw)))
                    if keys[index]
                }
                if (mapped.get("profile_link") or "").upper().startswith("DO NOT DELETE"):
                    skipped += 1
                    continue
                parsed = map_row(mapped)
                if parsed is None:
                    skipped += 1
                    continue
                rows.append(parsed)
        return rows, skipped

    def _collapse(self, rows: list[dict]):
        profiles = {}
        deals = {}
        owners = defaultdict(list)
        names = Counter()
        for row in rows:
            who = row["who_added"]
            if who:
                names[who] += 1
            key = (row["platform"], row["profile_link"])
            profiles[key] = merge_profile(profiles.get(key), row)
            campaign = row["campaign"]
            if not campaign:
                continue
            owners[campaign].append(who)
            deals[(row["platform"], row["profile_link"], campaign)] = row
        campaign_owners = {
            campaign: Counter([name for name in people if name]).most_common(1)[0][0]
            if any(people)
            else ""
            for campaign, people in owners.items()
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

    def _save_campaigns(self, campaign_owners: dict, users: dict) -> dict:
        fallback = users["sheet"]
        saved = {}
        for name, owner_name in sorted(campaign_owners.items()):
            owner = users.get(owner_name, fallback)
            campaign, created = Campaign.objects.get_or_create(
                client_name=name,
                defaults={
                    "campaign_owner": owner,
                    "created_by": owner,
                    "status": CampaignStatus.OUTREACH,
                    "creators_needed": 1,
                },
            )
            if not created and not campaign.campaign_owner_id:
                campaign.campaign_owner = owner
                campaign.save(update_fields=["campaign_owner"])
            saved[name] = campaign
        return saved

    def _save_creators(self, profiles: dict, users: dict) -> dict:
        fallback = users["sheet"]
        saved = {}
        for key, profile in profiles.items():
            added_by = users.get(profile["who_added"], fallback) if profile["who_added"] else fallback
            creator, created = Creator.objects.get_or_create(
                platform=profile["platform"],
                profile_link=profile["profile_link"],
                defaults={
                    "influencer_name": profile["influencer_name"],
                    "niche": profile["niche"],
                    "country": profile["country"],
                    "language": profile["language"],
                    "followers": profile["followers"],
                    "tier": profile["tier"],
                    "email": profile["email"],
                    "other_contact": profile["other_contact"],
                    "engagement_rate": profile["engagement_rate"],
                    "audience_insights": profile["audience_insights"],
                    "avg_views": profile["avg_views"],
                    "geo": profile["geo"],
                    "female_pct": profile["female_pct"],
                    "male_pct": profile["male_pct"],
                    "is_profile_checked": bool(profile["profile_checked"]),
                    "source": SOURCE,
                    "added_by": added_by,
                    "added_at": profile["added_at"],
                },
            )
            if not created:
                creator.influencer_name = profile["influencer_name"]
                creator.niche = profile["niche"]
                creator.country = profile["country"]
                creator.language = profile["language"]
                creator.followers = profile["followers"]
                creator.tier = profile["tier"]
                creator.email = profile["email"]
                creator.other_contact = profile["other_contact"]
                creator.engagement_rate = profile["engagement_rate"]
                creator.audience_insights = profile["audience_insights"]
                creator.avg_views = profile["avg_views"]
                creator.geo = profile["geo"]
                creator.female_pct = profile["female_pct"]
                creator.male_pct = profile["male_pct"]
                creator.is_profile_checked = bool(profile["profile_checked"])
                creator.source = SOURCE
                creator.added_by = added_by
                creator.added_at = profile["added_at"]
                creator.save()
            saved[key] = creator
        return saved

    def _save_deals(self, deals: dict, campaigns: dict, creators: dict) -> int:
        count = 0
        for (platform, link, campaign_name), row in deals.items():
            campaign = campaigns[campaign_name]
            creator = creators[(platform, link)]
            price, currency, price_eur = normalize_budget(
                row["price"], row["currency"], row["price_eur"]
            )
            defaults = {
                "stage": row["stage"],
                "deliverables": row["deliverables"],
                "deliverables_notes": row["deliverables_notes"],
                "assigned_to": row["who_added"],
                "email_outreached": row["email_outreached"],
                "sent_date": row["sent_date"],
                "fx_lock_date": row["fx_lock_date"],
                "creator_price": price,
                "creator_currency": currency,
                "creator_price_eur": price_eur if currency else None,
                "date_confirmed": row["date_confirmed"],
                "client_remarks": row["comments"],
                "added_by": row["who_added"],
            }
            deal, created = CampaignCreator.objects.get_or_create(
                campaign=campaign,
                creator=creator,
                defaults=defaults,
            )
            if not created:
                for field, value in defaults.items():
                    setattr(deal, field, value)
                if deal.creator_price_eur is None or deal.client_price_eur is None:
                    deal.margin_eur = None
                else:
                    deal.margin_eur = deal.client_price_eur - deal.creator_price_eur
                deal.save()
            count += 1
        return count

    def _set_creators_needed(self, campaigns: dict):
        for campaign in campaigns.values():
            needed = campaign.deals.count() or 1
            if campaign.creators_needed != needed:
                campaign.creators_needed = needed
                campaign.save(update_fields=["creators_needed"])
