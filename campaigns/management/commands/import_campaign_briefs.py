"""Load campaign briefs and the Campaign Master tracker into campaign rows."""

from __future__ import annotations

import csv
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from campaigns.models import Campaign, CampaignStatus
from creators.choices import Currency, Platform
from creators.management.commands.import_central_sheet import username_from_name
from creators.masters import lookup_named
from creators.models import Country

DEFAULT_XLSX = Path(
    r"C:\Users\rahul\Downloads\Creator Brief - Campaign Requirements Intake (Dev Team).xlsx"
)
DEFAULT_CSV = Path(
    r"C:\Users\rahul\Downloads\Creator Brief - Campaign Requirements Intake (Dev Team) - Campaign Requirements (1).csv"
)
DEFAULT_MASTER = Path(r"C:\Users\rahul\Downloads\Influencer Tracker - Main.xlsx")
DEFAULT_PASSWORD = "12345"
SHEET_USERNAME = "sheet"

BRIEF_STATUS_ALIASES = {
    "new request": CampaignStatus.DRAFT,
    "draft": CampaignStatus.DRAFT,
    "in progress": CampaignStatus.ACTIVE,
    "pitch": CampaignStatus.ACTIVE,
    "scouting": CampaignStatus.ACTIVE,
    "active": CampaignStatus.ACTIVE,
    "ready for review": CampaignStatus.PENDING,
    "pending": CampaignStatus.PENDING,
    "delivered": CampaignStatus.COMPLETED,
    "completed": CampaignStatus.COMPLETED,
    "on hold": CampaignStatus.ON_HOLD,
    "cancelled": CampaignStatus.CANCELLED,
    "canceled": CampaignStatus.CANCELLED,
    "not started": CampaignStatus.NOT_STARTED,
    "paused": CampaignStatus.PAUSED,
}
MASTER_STATUS_ALIASES = {
    "active": CampaignStatus.ACTIVE,
    "draft": CampaignStatus.DRAFT,
    "pending": CampaignStatus.PENDING,
    "pre-campaign": CampaignStatus.PRE_CAMPAIGN,
    "pre campaign": CampaignStatus.PRE_CAMPAIGN,
    "pre- campaign": CampaignStatus.PRE_CAMPAIGN,
    "scouting": CampaignStatus.ACTIVE,
    "outreach": CampaignStatus.ACTIVE,
    "awaiting payment": CampaignStatus.AWAITING_PAYMENT,
    "on hold": CampaignStatus.ON_HOLD,
    "unresponsive": CampaignStatus.UNRESPONSIVE,
    "cancelled": CampaignStatus.CANCELLED,
    "canceled": CampaignStatus.CANCELLED,
    "completed": CampaignStatus.COMPLETED,
    "closed": CampaignStatus.COMPLETED,
    "not started": CampaignStatus.NOT_STARTED,
    "paused": CampaignStatus.PAUSED,
    "prospecting paused": CampaignStatus.PROSPECTING_PAUSED,
    "contract pending": CampaignStatus.CONTRACT_PHASE,
    "contract phase": CampaignStatus.CONTRACT_PHASE,
}
PLATFORM_WORDS = (
    ("instagram", Platform.INSTAGRAM),
    ("tiktok", Platform.TIKTOK),
    ("youtube", Platform.YOUTUBE),
    ("facebook", Platform.FACEBOOK),
    ("linkedin", Platform.LINKEDIN),
    ("twitch", Platform.TWITCH),
    ("kick", Platform.KICK),
    ("twitter", Platform.X),
)
HEADER_KEYS = {
    "client": "client",
    "priority": "priority",
    "priority rank": "priority_rank",
    "list submitted": "list_submitted",
    "deadline to scout the profiles": "deadline_to_scout",
    "primary market": "primary_market",
    "additional markets": "additional_markets",
    "# creators needed": "creators_needed",
    "platform": "platform",
    "primary niche / vertical": "niche",
    "secondary niche / sub niche": "sub_niche",
    "content type": "content_type",
    "content format": "content_format",
    "min historical sponsorship quality": "sponsorship_quality",
    "age range": "age_range",
    "gender": "gender",
    "interests": "interests",
    "audience location": "audience_location",
    "audience language": "audience_language",
    "min followers": "min_followers",
    "max followers/tiers": "max_followers",
    "min avg views": "min_avg_views",
    "min engagement rate (%)": "min_engagement",
    "min reach": "min_reach",
    "min view consistency": "view_consistency",
    "min audience quality": "audience_quality",
    "max rate per deliverable (usd)": "max_rate",
    "deliverables per creator": "deliverables",
    "usage rights": "usage_rights",
    "exclusivity": "exclusivity",
    "prohibited competitors": "competitors",
    "content history flag": "content_history",
    "reputation screening": "reputation",
    "status": "status",
    "delivery deadline": "delivery_deadline",
    "notes": "notes",
    "brief": "brief",
    "search keywords": "keywords",
    "approved or suggested profiles by client": "suggested_profiles",
    "ready for the dev team": "ready",
    "comments": "comments",
}
MASTER_HEADER_KEYS = {
    "campaign name": "client_name",
    "client poc name": "client_poc_name",
    "team lead": "team_lead",
    "poc": "poc",
    "2nd poc": "second_poc",
    "scouting/outreach": "scouting_team",
    "start date": "start_date",
    "deadline": "deadline",
    "budget 3 months actual currency": "budget_amount",
    "campaign currency": "budget_currency",
    "conversion eur": "budget_eur",
    "target creators": "creators_needed",
    "campaign status": "status",
    "last update date (dd/mm/yyyy)": "last_update_on",
    "notes": "notes",
    "blockers": "blockers",
    "internal working sheet": "working_sheet",
    "cf list": "cf_list",
}
EXTRA_REMARK_FIELDS = (
    "priority_rank",
    "sponsorship_quality",
    "gender",
    "interests",
    "audience_location",
    "audience_language",
    "min_reach",
    "audience_quality",
    "max_rate",
    "deliverables",
    "usage_rights",
    "exclusivity",
    "competitors",
    "content_history",
    "reputation",
    "delivery_deadline",
    "notes",
    "brief",
    "keywords",
    "suggested_profiles",
    "comments",
    "priority",
    "list_submitted",
    "ready",
    "age_range",
    "view_consistency",
)
SCALAR_FIELDS = (
    "client_poc_name",
    "start_date",
    "deadline",
    "last_update_on",
    "budget_amount",
    "budget_currency",
    "budget_eur",
    "notes",
    "deadline_to_scout",
    "platforms",
    "niche_vertical",
    "sub_niche",
    "content_type",
    "content_format",
    "min_followers",
    "max_followers",
    "min_avg_views",
    "min_engagement_rate",
    "remarks_brief",
)


def header_key(value) -> str:
    return " ".join(str(value or "").split()).casefold()


def name_key(value) -> str:
    return " ".join(str(value or "").split()).casefold()


def text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return " ".join(str(value).split())


def is_blank(value) -> bool:
    raw = text(value).casefold()
    return raw in {"", "n/a", "na", "tbd", "none", "-", "#ref!", "#value!", "#n/a"}


def parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if is_blank(value):
        return None
    raw = text(value)
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def parse_int(value):
    if is_blank(value):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = int(value)
        return number if number >= 1 else None
    raw = text(value)
    match = re.search(r"\d[\d,]*", raw)
    if not match:
        return None
    number = int(match.group(0).replace(",", ""))
    return number if number >= 1 else None


def parse_decimal(value, maximum=None):
    if is_blank(value):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = Decimal(str(value))
    else:
        raw = text(value).replace(",", "")
        raw = re.sub(r"[€$£%]", "", raw)
        match = re.search(r"-?\d+(?:\.\d+)?", raw)
        if not match:
            return None
        try:
            number = Decimal(match.group(0))
        except InvalidOperation:
            return None
    if number < 0:
        return None
    if maximum is not None and number > maximum:
        return None
    return number


def parse_bool(value):
    if isinstance(value, bool):
        return value
    if is_blank(value):
        return None
    raw = text(value).casefold()
    if raw in {"true", "yes", "1"}:
        return True
    if raw in {"false", "no", "0"}:
        return False
    return None


def parse_currency(value):
    raw = text(value).upper()
    if raw in Currency.values:
        return raw
    return ""


def parse_platforms(value) -> list[str]:
    raw = text(value).lower()
    if not raw:
        return []
    found = []
    if re.search(r"\big\b", raw):
        found.append(Platform.INSTAGRAM)
    if re.search(r"\btt\b", raw):
        found.append(Platform.TIKTOK)
    if re.search(r"\bx\b", raw):
        found.append(Platform.X)
    for word, slug in PLATFORM_WORDS:
        if word in raw and slug not in found:
            found.append(slug)
    return found


def parse_status(value, aliases, default=None):
    if is_blank(value):
        return default
    raw = text(value).casefold()
    if "/" in raw and "new request" in raw and "cancelled" in raw:
        return default
    raw = raw.replace("_", " ")
    return aliases.get(raw, default)


def parse_markets(*values) -> tuple[list[str], list[str]]:
    names = []
    leftover = []
    for value in values:
        raw = text(value)
        if not raw:
            continue
        if raw.lower().startswith("do not"):
            leftover.append(raw)
            continue
        parts = re.split(r",|/|\band\b|\bor\b", raw, flags=re.I)
        for part in parts:
            name = " ".join(part.split()).strip(" .!")
            if name and name.lower() not in {"etc"} and name not in names:
                names.append(name[:50])
    return names, leftover


def parse_list(value) -> list[str]:
    raw = text(value)
    if not raw:
        return []
    parts = re.split(r"[,\n•]+", raw)
    items = []
    for part in parts:
        item = " ".join(part.split()).strip("- ")
        if item and item not in items:
            items.append(item)
    return items


def is_example(client: str) -> bool:
    lowered = client.lower()
    return "example" in lowered or "not correct details" in lowered


def split_people(value) -> list[str]:
    raw = text(value)
    if not raw or is_blank(raw):
        return []
    names = []
    for part in re.split(r",|/|\band\b", raw, flags=re.I):
        name = " ".join(part.split()).strip(" .")
        if name and not is_blank(name) and name not in names:
            names.append(name[:150])
    return names


def tracker_notes(mapped: dict) -> str:
    blocks = []
    notes = text(mapped.get("notes"))
    if notes:
        blocks.append(notes)
    blockers = text(mapped.get("blockers"))
    if blockers:
        blocks.append(f"Blockers: {blockers}")
    working_sheet = text(mapped.get("working_sheet"))
    if working_sheet:
        blocks.append(f"Working sheet: {working_sheet}")
    cf_list = text(mapped.get("cf_list"))
    if cf_list:
        blocks.append(f"CF list: {cf_list}")
    return "\n\n".join(blocks)


def remarks_from(row: dict, extra_markets: list[str]) -> str:
    blocks = []
    if extra_markets:
        blocks.append("Market notes: " + "; ".join(extra_markets))
    for key in EXTRA_REMARK_FIELDS:
        value = text(row.get(key))
        if value:
            blocks.append(f"{key.replace('_', ' ').title()}: {value}")
    return "\n\n".join(blocks)


def mapped_row(header, values, keys) -> dict:
    mapped = {}
    for index, name in enumerate(header):
        key = keys.get(header_key(name))
        if key and index < len(values):
            mapped[key] = values[index]
    return mapped


def brief_from_values(header, values) -> dict | None:
    mapped = mapped_row(header, values, HEADER_KEYS)
    client = text(mapped.get("client"))
    if not client or is_example(client):
        return None
    markets, extra_markets = parse_markets(
        mapped.get("primary_market"), mapped.get("additional_markets")
    )
    min_followers = parse_int(mapped.get("min_followers"))
    max_followers = parse_int(mapped.get("max_followers"))
    if min_followers and max_followers and max_followers < min_followers:
        max_followers = None
    return {
        "client_name": client[:200],
        "deadline_to_scout": parse_date(mapped.get("deadline_to_scout")),
        "country_market": markets,
        "creators_needed": parse_int(mapped.get("creators_needed")),
        "platforms": parse_platforms(mapped.get("platform")),
        "niche_vertical": parse_list(mapped.get("niche")),
        "sub_niche": parse_list(mapped.get("sub_niche")),
        "content_type": text(mapped.get("content_type"))[:120],
        "content_format": text(mapped.get("content_format"))[:120],
        "min_followers": min_followers,
        "max_followers": max_followers,
        "min_avg_views": parse_int(mapped.get("min_avg_views")),
        "min_engagement_rate": parse_decimal(
            mapped.get("min_engagement"), maximum=Decimal("100")
        ),
        "status": parse_status(mapped.get("status"), BRIEF_STATUS_ALIASES),
        "remarks_brief": remarks_from(mapped, extra_markets),
        "status_from_master": False,
    }


def master_from_values(header, values) -> dict | None:
    mapped = mapped_row(header, values, MASTER_HEADER_KEYS)
    client = text(mapped.get("client_name"))
    if not client or is_example(client) or client.casefold() == "campaign name":
        return None
    return {
        "client_name": client[:200],
        "client_poc_name": text(mapped.get("client_poc_name"))[:150],
        "team_lead": text(mapped.get("team_lead"))[:150],
        "poc_names": split_people(mapped.get("poc")) + [
            name
            for name in split_people(mapped.get("second_poc"))
            if name not in split_people(mapped.get("poc"))
        ],
        "scouting_names": split_people(mapped.get("scouting_team")),
        "start_date": parse_date(mapped.get("start_date")),
        "deadline": parse_date(mapped.get("deadline")),
        "budget_amount": parse_decimal(mapped.get("budget_amount")),
        "budget_currency": parse_currency(mapped.get("budget_currency")),
        "budget_eur": parse_decimal(mapped.get("budget_eur")),
        "creators_needed": parse_int(mapped.get("creators_needed")),
        "status": parse_status(mapped.get("status"), MASTER_STATUS_ALIASES),
        "last_update_on": parse_date(mapped.get("last_update_on")),
        "notes": tracker_notes(mapped),
        "status_from_master": True,
    }


def overlay(base: dict, incoming: dict) -> dict:
    merged = dict(base)
    incoming_master = incoming.get("status_from_master")
    for key, value in incoming.items():
        if key == "status_from_master":
            continue
        if key == "client_name":
            if not merged.get("client_name"):
                merged["client_name"] = value
            continue
        if key == "status":
            if value and (incoming_master or not merged.get("status")):
                merged["status"] = value
            continue
        if key == "creators_needed":
            if value and not merged.get("creators_needed"):
                merged["creators_needed"] = value
            continue
        if value in (None, "", []):
            continue
        merged[key] = value
    if incoming_master:
        merged["status_from_master"] = True
    return merged


def read_brief_xlsx(path: Path) -> list[dict]:
    from openpyxl import load_workbook

    workbook = load_workbook(path, data_only=True)
    rows = []
    sheets = (
        ("Campaign Requirements", 3, CampaignStatus.ACTIVE),
        ("Completed Campaigns", 2, CampaignStatus.COMPLETED),
    )
    for sheet_name, header_row, default_status in sheets:
        if sheet_name not in workbook.sheetnames:
            continue
        sheet = workbook[sheet_name]
        header = [sheet.cell(header_row, column).value for column in range(1, sheet.max_column + 1)]
        for row_number in range(header_row + 1, sheet.max_row + 1):
            values = [sheet.cell(row_number, column).value for column in range(1, sheet.max_column + 1)]
            parsed = brief_from_values(header, values)
            if not parsed:
                continue
            if parsed["status"] is None:
                parsed["status"] = default_status
            rows.append(parsed)
    return rows


def read_brief_csv(path: Path, default_status) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        raw_rows = list(csv.reader(handle))
    header_index = next(
        (index for index, row in enumerate(raw_rows[:6]) if "Client" in row),
        None,
    )
    if header_index is None:
        return []
    header = raw_rows[header_index]
    rows = []
    for values in raw_rows[header_index + 1 :]:
        parsed = brief_from_values(header, values)
        if not parsed:
            continue
        if parsed["status"] is None:
            parsed["status"] = default_status
        rows.append(parsed)
    return rows


def read_campaign_master(path: Path) -> list[dict]:
    from openpyxl import load_workbook

    workbook = load_workbook(path, data_only=True)
    if "Campaign Master" not in workbook.sheetnames:
        return []
    sheet = workbook["Campaign Master"]
    rows = list(sheet.iter_rows(values_only=True))
    header_index = next(
        (
            index
            for index, row in enumerate(rows[:8])
            if any(header_key(cell) == "campaign name" for cell in row)
        ),
        None,
    )
    if header_index is None:
        return []
    header = list(rows[header_index])
    parsed_rows = []
    for values in rows[header_index + 1 :]:
        parsed = master_from_values(header, values)
        if parsed:
            parsed_rows.append(parsed)
    return parsed_rows


def collect_from_path(path: Path) -> tuple[list[dict], list[dict]]:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        from openpyxl import load_workbook

        names = load_workbook(path, read_only=True, data_only=True).sheetnames
        if "Campaign Master" in names:
            return [], read_campaign_master(path)
        return read_brief_xlsx(path), []
    return read_brief_csv(path, CampaignStatus.ACTIVE), []


class Command(BaseCommand):
    help = "Import campaign briefs and the Campaign Master tracker from Downloads."

    def add_arguments(self, parser):
        parser.add_argument("paths", nargs="*")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        paths = [Path(item) for item in options["paths"]]
        if not paths:
            paths = [DEFAULT_XLSX, DEFAULT_CSV, DEFAULT_MASTER]
        missing = [str(path) for path in paths if not path.is_file()]
        if missing:
            raise CommandError("Sheet not found: " + "; ".join(missing))

        store = {}
        brief_count = master_count = 0
        for path in paths:
            briefs, masters = collect_from_path(path)
            brief_count += len(briefs)
            master_count += len(masters)
            for row in briefs:
                self._store(store, row)
            for row in masters:
                self._store(store, row)
        self.stdout.write(
            f"Parsed {brief_count} brief rows and {master_count} tracker rows, "
            f"{len(store)} unique campaigns."
        )
        if options["dry_run"]:
            for row in sorted(store.values(), key=lambda item: item["client_name"].casefold()):
                self.stdout.write(
                    f"  {row['client_name']} status={row.get('status')} "
                    f"needed={row.get('creators_needed')} lead={row.get('team_lead', '')}"
                )
            return

        owner = self._sheet_user()
        created = updated = 0
        for row in store.values():
            with transaction.atomic():
                if self._save_campaign(row, owner):
                    created += 1
                else:
                    updated += 1
        self.stdout.write(
            self.style.SUCCESS(f"Imported {created} new campaigns and updated {updated}.")
        )

    def _store(self, store: dict, row: dict):
        key = name_key(row["client_name"])
        if not key:
            return
        if key in store:
            store[key] = overlay(store[key], row)
            return
        store[key] = dict(row)

    def _sheet_user(self):
        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=SHEET_USERNAME,
            defaults={
                "first_name": "sheet",
                "is_staff": True,
                "is_active": True,
            },
        )
        if created:
            user.set_password(DEFAULT_PASSWORD)
            user.save(update_fields=["password"])
        return user

    def _set_markets(self, campaign, names):
        if not names:
            return
        countries = []
        for name in names:
            country = lookup_named(Country, name)
            if country is not None and country not in countries:
                countries.append(country)
        campaign.country_market.set(countries)

    def _person(self, name: str):
        cleaned_name = " ".join((name or "").split())
        if not cleaned_name:
            return None
        cache = getattr(self, "_people", None)
        if cache is None:
            cache = {}
            self._people = cache
        key = cleaned_name.casefold()
        if key in cache:
            return cache[key]
        User = get_user_model()
        slug = username_from_name(cleaned_name)
        user = User.objects.filter(username__iexact=slug).first()
        if user is None:
            matches = []
            for candidate in User.objects.all():
                label = " ".join(
                    part for part in (candidate.first_name, candidate.last_name) if part
                ).casefold()
                if label == key or candidate.get_full_name().casefold() == key:
                    matches.append(candidate)
            if len(matches) == 1:
                user = matches[0]
        if user is None and " " not in cleaned_name:
            by_first = list(User.objects.filter(first_name__iexact=cleaned_name))
            if len(by_first) == 1:
                user = by_first[0]
        if user is None:
            parts = cleaned_name.split()
            user = User(username=slug, first_name=parts[0][:150], last_name=" ".join(parts[1:])[:150], is_staff=True, is_active=True)
            user.set_unusable_password()
            user.save()
        cache[key] = user
        return user

    def _set_people(self, campaign, row: dict, fallback, created: bool):
        lead_name = row.get("team_lead") or ""
        lead = self._person(lead_name) if lead_name else None
        if lead is not None:
            campaign.campaign_owner = lead
            if created or campaign.created_by_id in (None, fallback.id):
                campaign.created_by = lead
        elif campaign.campaign_owner_id is None:
            campaign.campaign_owner = fallback
            campaign.created_by = fallback
        campaign.save()
        poc_names = row.get("poc_names") or []
        scout_names = row.get("scouting_names") or []
        if poc_names:
            campaign.poc.set(person for name in poc_names if (person := self._person(name)))
        if scout_names:
            campaign.scouting_team.set(
                person for name in scout_names if (person := self._person(name))
            )

    def _save_campaign(self, row: dict, owner) -> bool:
        campaign = Campaign.objects.filter(client_name__iexact=row["client_name"]).first()
        created = campaign is None
        if created:
            campaign = Campaign(
                client_name=row["client_name"],
                campaign_owner=owner,
                created_by=owner,
                status=row.get("status") or CampaignStatus.DRAFT,
                creators_needed=row.get("creators_needed") or 10,
            )
        self._apply(campaign, row)
        self._set_people(campaign, row, owner, created)
        self._set_markets(campaign, row.get("country_market") or [])
        return created

    def _apply(self, campaign, row: dict):
        if row.get("status"):
            campaign.status = row["status"]
        if row.get("creators_needed"):
            campaign.creators_needed = row["creators_needed"]
        for name in SCALAR_FIELDS:
            value = row.get(name)
            if value in (None, "", []):
                continue
            if name == "budget_currency" and row.get("budget_amount") in (None, ""):
                continue
            setattr(campaign, name, value)
        if campaign.budget_amount is None:
            campaign.budget_currency = ""
        elif campaign.budget_currency == Currency.EUR and campaign.budget_eur is None:
            campaign.budget_eur = campaign.budget_amount
