"""Load campaign briefs from the Creator Brief workbook in Downloads."""

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
from creators.choices import Platform
from creators.masters import lookup_named
from creators.models import Country

DEFAULT_XLSX = Path(
    r"C:\Users\rahul\Downloads\Creator Brief - Campaign Requirements Intake (Dev Team).xlsx"
)
DEFAULT_CSV = Path(
    r"C:\Users\rahul\Downloads\Creator Brief - Campaign Requirements Intake (Dev Team) - Campaign Requirements (1).csv"
)
DEFAULT_PASSWORD = "12345"
SHEET_USERNAME = "sheet"

STATUS_ALIASES = {
    "new request": CampaignStatus.DRAFT,
    "in progress": CampaignStatus.SCOUTING,
    "pitch": CampaignStatus.OUTREACH,
    "scouting": CampaignStatus.SCOUTING,
    "ready for review": CampaignStatus.CLIENT_SHARING,
    "delivered": CampaignStatus.CLOSED,
    "on hold": CampaignStatus.DRAFT,
    "cancelled": CampaignStatus.CLOSED,
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
    "Client": "client",
    "Priority": "priority",
    "Priority Rank": "priority_rank",
    "List Submitted": "list_submitted",
    "Deadline to scout the profiles": "deadline",
    "Primary Market": "primary_market",
    "Additional Markets": "additional_markets",
    "# Creators Needed": "creators_needed",
    "Platform": "platform",
    "Primary Niche / Vertical": "niche",
    "Secondary Niche / Sub Niche": "sub_niche",
    "Content Type": "content_type",
    "Content Format": "content_format",
    "Min Historical Sponsorship Quality": "sponsorship_quality",
    "Age Range": "age_range",
    "Gender": "gender",
    "Interests": "interests",
    "Audience Location": "audience_location",
    "Audience Language": "audience_language",
    "Min Followers": "min_followers",
    "Max Followers/Tiers": "max_followers",
    "Min Avg Views": "min_avg_views",
    "Min Engagement Rate (%)": "min_engagement",
    "Min Reach": "min_reach",
    "Min View Consistency": "view_consistency",
    "Min Audience Quality": "audience_quality",
    "Max Rate per Deliverable (USD)": "max_rate",
    "Deliverables per Creator": "deliverables",
    "Usage Rights": "usage_rights",
    "Exclusivity": "exclusivity",
    "Prohibited Competitors": "competitors",
    "Content History Flag": "content_history",
    "Reputation Screening": "reputation",
    "Status": "status",
    "Delivery Deadline": "delivery_deadline",
    "Notes": "notes",
    "Brief": "brief",
    "Search Keywords": "keywords",
    "Approved or suggested profiles by client": "suggested_profiles",
    "Ready for the Dev team": "ready",
    "COMMENTS": "comments",
}
EXTRA_REMARK_FIELDS = (
    "priority",
    "list_submitted",
    "sponsorship_quality",
    "age_range",
    "gender",
    "interests",
    "audience_location",
    "audience_language",
    "min_reach",
    "view_consistency",
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
)


def text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return " ".join(str(value).split())


def parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    raw = text(value)
    if not raw:
        return None
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def parse_int(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = int(value)
        return number if number >= 1 else None
    raw = text(value)
    if not raw:
        return None
    match = re.search(r"\d[\d,]*", raw)
    if not match:
        return None
    number = int(match.group(0).replace(",", ""))
    return number if number >= 1 else None


def parse_decimal(value, maximum=None):
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


def parse_status(value, default):
    raw = text(value).lower()
    if not raw or "/" in raw and "new request" in raw and "cancelled" in raw:
        return default
    return STATUS_ALIASES.get(raw, default)


def parse_markets(*values) -> list[str]:
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


def remarks_from(row: dict, extra_markets: list[str]) -> str:
    blocks = []
    if extra_markets:
        blocks.append("Market notes: " + "; ".join(extra_markets))
    for key in EXTRA_REMARK_FIELDS:
        value = text(row.get(key))
        if value:
            blocks.append(f"{key.replace('_', ' ').title()}: {value}")
    return "\n\n".join(blocks)


def row_from_values(header, values) -> dict | None:
    mapped = {}
    for index, name in enumerate(header):
        key = HEADER_KEYS.get(name)
        if key and index < len(values):
            mapped[key] = values[index]
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
    needed = parse_int(mapped.get("creators_needed")) or 1
    return {
        "client_name": client[:200],
        "deadline_to_scout": parse_date(mapped.get("deadline")),
        "country_market": markets,
        "creators_needed": needed,
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
        "status": mapped.get("status"),
        "remarks_brief": remarks_from(mapped, extra_markets),
    }


def read_xlsx(path: Path) -> list[tuple[str, dict]]:
    from openpyxl import load_workbook

    workbook = load_workbook(path, data_only=True)
    rows = []
    sheets = (
        ("Campaign Requirements", 3, CampaignStatus.SCOUTING),
        ("Completed Campaigns", 2, CampaignStatus.CLOSED),
    )
    for sheet_name, header_row, default_status in sheets:
        if sheet_name not in workbook.sheetnames:
            continue
        sheet = workbook[sheet_name]
        header = [sheet.cell(header_row, column).value for column in range(1, sheet.max_column + 1)]
        for row_number in range(header_row + 1, sheet.max_row + 1):
            values = [sheet.cell(row_number, column).value for column in range(1, sheet.max_column + 1)]
            parsed = row_from_values(header, values)
            if not parsed:
                continue
            parsed["status"] = parse_status(parsed["status"], default_status)
            rows.append((sheet_name, parsed))
    return rows


def read_csv(path: Path, default_status) -> list[tuple[str, dict]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        raw_rows = list(csv.reader(handle))
    if len(raw_rows) < 4:
        return []
    header = raw_rows[2]
    rows = []
    for values in raw_rows[3:]:
        parsed = row_from_values(header, values)
        if not parsed:
            continue
        parsed["status"] = parse_status(parsed["status"], default_status)
        rows.append((path.name, parsed))
    return rows


class Command(BaseCommand):
    help = "Import campaign requirement sheets from Downloads."

    def add_arguments(self, parser):
        parser.add_argument("paths", nargs="*")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        paths = [Path(item) for item in options["paths"]]
        if not paths:
            paths = [DEFAULT_XLSX, DEFAULT_CSV]
        missing = [str(path) for path in paths if not path.is_file()]
        if missing:
            raise CommandError("Sheet not found: " + "; ".join(missing))

        briefs = []
        for path in paths:
            if path.suffix.lower() in {".xlsx", ".xlsm"}:
                briefs.extend(read_xlsx(path))
            else:
                briefs.extend(read_csv(path, CampaignStatus.SCOUTING))

        by_name = {}
        for source, brief in briefs:
            by_name[brief["client_name"]] = (source, brief)
        self.stdout.write(f"Parsed {len(briefs)} brief rows, {len(by_name)} unique clients.")
        if options["dry_run"]:
            for name, (source, brief) in sorted(by_name.items()):
                self.stdout.write(
                    f"  {name} [{source}] platforms={brief['platforms']} needed={brief['creators_needed']}"
                )
            return

        owner = self._sheet_user()
        created = updated = 0
        with transaction.atomic():
            for name, (_source, brief) in by_name.items():
                was_created = self._save_campaign(brief, owner)
                if was_created:
                    created += 1
                else:
                    updated += 1
        self.stdout.write(
            self.style.SUCCESS(f"Imported {created} new campaigns and updated {updated}.")
        )

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

    def _save_campaign(self, brief: dict, owner) -> bool:
        campaign, created = Campaign.objects.get_or_create(
            client_name=brief["client_name"],
            defaults={
                "campaign_owner": owner,
                "created_by": owner,
                "status": brief["status"],
                "creators_needed": brief["creators_needed"],
                "deadline_to_scout": brief["deadline_to_scout"],
                "platforms": brief["platforms"],
                "niche_vertical": brief["niche_vertical"],
                "sub_niche": brief["sub_niche"],
                "content_type": brief["content_type"],
                "content_format": brief["content_format"],
                "min_followers": brief["min_followers"],
                "max_followers": brief["max_followers"],
                "min_avg_views": brief["min_avg_views"],
                "min_engagement_rate": brief["min_engagement_rate"],
                "remarks_brief": brief["remarks_brief"],
            },
        )
        self._set_markets(campaign, brief["country_market"])
        if created:
            return True
        campaign.status = brief["status"]
        campaign.creators_needed = brief["creators_needed"]
        campaign.deadline_to_scout = brief["deadline_to_scout"] or campaign.deadline_to_scout
        if brief["country_market"]:
            self._set_markets(campaign, brief["country_market"])
        if brief["platforms"]:
            campaign.platforms = brief["platforms"]
        if brief["niche_vertical"]:
            campaign.niche_vertical = brief["niche_vertical"]
        if brief["sub_niche"]:
            campaign.sub_niche = brief["sub_niche"]
        if brief["content_type"]:
            campaign.content_type = brief["content_type"]
        if brief["content_format"]:
            campaign.content_format = brief["content_format"]
        campaign.min_followers = brief["min_followers"]
        campaign.max_followers = brief["max_followers"]
        campaign.min_avg_views = brief["min_avg_views"]
        campaign.min_engagement_rate = brief["min_engagement_rate"]
        if brief["remarks_brief"]:
            campaign.remarks_brief = brief["remarks_brief"]
        campaign.save()
        return False
