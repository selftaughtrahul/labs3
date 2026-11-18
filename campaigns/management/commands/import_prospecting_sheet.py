"""Load the prospecting workbook into creators, deals, and the outreach log.

Four tabs are the record. A later tab wins when the same creator is on the same
campaign more than once: Confirmed, then Not interested, then Unresponsive, then
the working Prospecting list. Briefs update the campaign status and the brief
text. Reports, pitches, QC, and the client-sheet templates are not records.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import date, datetime, time, timezone as dt_timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import unquote, urlsplit

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import connection, transaction

from campaigns.models import (
    Campaign,
    CampaignCreator,
    CampaignStatus,
    Channel,
    Direction,
    Outreach,
    OutreachStatus,
    Stage,
)
from creators.lists import clean_string_list
from creators.management.commands.import_central_sheet import (
    keep_last,
    normalize_budget,
    parse_currency,
    parse_platform,
    parse_tier,
    username_from_name,
)
from creators.models import Creator

DEFAULT_SHEET = Path(r"C:\Users\rahul\Downloads\Influencer_Prospecting_Flow 2026.xlsx")
SOURCE = "prospecting"

RECORD_TABS = (
    ("Prospecting & Outreach", "prospecting", 10, ""),
    ("Not Interested Influencers", "not_interested", 30, "not interested"),
    ("Confirmed influencers", "confirmed", 40, "confirmed"),
    ("Unresponsivenot Confirmed influ", "unresponsive", 20, "unresponsive"),
)
HEADER_FIELDS = {
    "who prospected": "who",
    "platform": "platform",
    "profile link": "profile_link",
    "influencer name": "name",
    "niche vertical": "niche",
    "country": "country",
    "language": "language",
    "followers": "followers",
    "tier": "tier",
    "tiers": "tier",
    "campaign": "campaign",
    "email address": "email",
    "email": "email",
    "other contact tg wa ig x": "other_contact",
    "other contact": "other_contact",
    "outreach method": "method",
    "email outreached": "email_outreached",
    "outreach status": "status",
    "sent date": "sent_date",
    "follow up 1 date": "followup_1",
    "follow up 2 date": "followup_2",
    "date confirmed": "date_confirmed",
    "date added dd mm yyyy": "added_at",
    "comments": "comments",
    "currency": "currency",
    "amount": "price",
    "price": "price",
    "amount in eur": "price_eur",
    "deliverables": "deliverables",
    "deliverables notes": "deliverables_notes",
    "engagement rate": "engagement_rate",
    "audience insights": "audience_insights",
    "avg views": "avg_views",
    "geo": "geo",
    "female": "female_pct",
    "male": "male_pct",
}
STATUS_MAP = {
    "sent": (Stage.CONTACTED, OutreachStatus.SENT),
    "follow up": (Stage.CONTACTED, OutreachStatus.FOLLOW_UP),
    "follow up 2": (Stage.CONTACTED, OutreachStatus.FOLLOW_UP),
    "follow up 3": (Stage.CONTACTED, OutreachStatus.FOLLOW_UP),
    "replied": (Stage.NEGOTIATING, OutreachStatus.REPLIED),
    "negotiating": (Stage.NEGOTIATING, OutreachStatus.NEGOTIATING),
    "confirmed": (Stage.CONFIRMED, OutreachStatus.CONFIRMED),
    "not interested": (Stage.NOT_INTERESTED, OutreachStatus.NOT_INTERESTED),
    "unresponsive": (Stage.UNRESPONSIVE, OutreachStatus.UNRESPONSIVE),
    "invalid email email error": (Stage.UNRESPONSIVE, OutreachStatus.UNRESPONSIVE),
    "bounced": (Stage.UNRESPONSIVE, OutreachStatus.UNRESPONSIVE),
    "not available as of the moment": (Stage.NOT_INTERESTED, OutreachStatus.NOT_INTERESTED),
}
BRIEF_STATUS = {
    "active": CampaignStatus.OUTREACH,
    "completed": CampaignStatus.CLOSED,
    "cancelled": CampaignStatus.CLOSED,
    "canceled": CampaignStatus.CLOSED,
    "declined": CampaignStatus.CLOSED,
    "on hold": CampaignStatus.DRAFT,
    "pending": CampaignStatus.DRAFT,
}
PATH_SUFFIXES = ("/videos", "/featured", "/shorts", "/about", "/streams", "/reels")


def plain(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return " ".join(str(value).split())


def header_key(value) -> str:
    return re.sub(r"[^a-z0-9]+", " ", plain(value).lower()).strip()


def status_key(value) -> str:
    return re.sub(r"[^a-z0-9]+", " ", plain(value).lower()).strip()


def name_key(value) -> str:
    return re.sub(r"[^a-z0-9]+", "", plain(value).lower())


def parse_day(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = plain(value)
    if not text or text.startswith("#"):
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def as_aware(value):
    if value is None:
        return None
    return datetime.combine(value, time.min, tzinfo=dt_timezone.utc)


def parse_number(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, float):
        if value != value:
            return None
        return Decimal(str(value))
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, Decimal):
        return value
    text = plain(value)
    if not text or text.startswith("#"):
        return None
    text = re.sub(r"[€$£%]", "", text.replace(",", ""))
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return Decimal(match.group(0))
    except InvalidOperation:
        return None


def parse_whole(value):
    number = parse_number(value)
    if number is None or number < 0:
        return None
    return int(number.to_integral_value(rounding=ROUND_HALF_UP))


def parse_money(value):
    number = parse_number(value)
    if number is None or number < 0:
        return None
    return number.quantize(Decimal("0.01"))


def parse_percent(value):
    number = parse_number(value)
    if number is None or number < 0 or number > 100:
        return None
    return number.quantize(Decimal("0.01"))


def parse_email(value) -> str:
    text = plain(value)
    if not text:
        return ""
    try:
        validate_email(text)
    except ValidationError:
        return ""
    return text


def canonical_link(value) -> str:
    raw = plain(value)
    if not raw or "do not add" in raw.lower() or raw.startswith("#"):
        return ""
    if not re.match(r"^https?://", raw, re.I):
        raw = f"https://{raw}"
    parts = urlsplit(raw)
    host = parts.netloc.lower().removeprefix("www.")
    if not host or "." not in host:
        return ""
    path = unquote(parts.path).rstrip("/")
    lowered = path.lower()
    for suffix in PATH_SUFFIXES:
        if lowered.endswith(suffix):
            path = path[: -len(suffix)]
            lowered = path.lower()
            break
    path = path.rstrip("/")
    return f"https://{host}{path}"[:500]


def profile_key(platform, link) -> tuple[str, str]:
    return platform, canonical_link(link).lower()


def parse_channel(method) -> str:
    first = plain(method).split(",")[0]
    key = status_key(first)
    if key.startswith("email") or "instantly" in key:
        return Channel.EMAIL
    if key.startswith("insta") or "instagram" in key:
        return Channel.INSTAGRAM_DM
    if "tiktok" in key or "tik tok" in key:
        return Channel.TIKTOK_DM
    if "whatsapp" in key or key == "wa":
        return Channel.WHATSAPP
    if "youtube" in key:
        return Channel.YOUTUBE
    if not key:
        return ""
    return Channel.OTHER


def map_status(value, default_status):
    key = status_key(value) or default_status
    if not key:
        return Stage.SHORTLISTED, "", False
    mapped = STATUS_MAP.get(key)
    if mapped is None:
        return Stage.CONTACTED, OutreachStatus.SENT, True
    stage, outreach_status = mapped
    return stage, outreach_status, True


def filled(value) -> bool:
    return value not in (None, "", [])


class Command(BaseCommand):
    help = "Import Influencer_Prospecting_Flow 2026.xlsx into creators, deals, and outreach."

    def add_arguments(self, parser):
        parser.add_argument("path", nargs="?", default=str(DEFAULT_SHEET))
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.is_file():
            raise CommandError(f"Workbook not found: {path}")
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA busy_timeout = 60000")

        rows, skipped, unknown = self._read(path)
        profiles, deals, campaign_names = self._collapse(rows)
        briefs = self._read_briefs(path)
        self.stdout.write(
            f"Rows {len(rows) + skipped}, skipped {skipped}, "
            f"creators {len(profiles)}, deals {len(deals)}, "
            f"campaign names {len(campaign_names)}, briefs {len(briefs)}."
        )
        if unknown:
            self.stdout.write("Unmapped statuses: " + ", ".join(sorted(unknown)))
        if options["dry_run"]:
            self._preview(profiles, deals, campaign_names)
            return

        with transaction.atomic():
            users = self._users()
            campaigns = self._campaigns(campaign_names, deals, users)
            creators, new_creators, updated_creators = self._creators(profiles, users)
            new_deals, updated_deals = self._deals(deals, campaigns, creators)
            messages = self._outreach(deals, campaigns, creators)
            brief_updates = self._briefs(briefs, campaigns, users)
        self.stdout.write(
            self.style.SUCCESS(
                f"Creators +{new_creators} updated {updated_creators}. "
                f"Deals +{new_deals} updated {updated_deals}. "
                f"Outreach rows {messages}. Briefs applied {brief_updates}."
            )
        )

    def _read(self, path: Path):
        import openpyxl

        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
        rows = []
        skipped = 0
        unknown = set()
        for sheet_name, _tab, priority, default_status in RECORD_TABS:
            sheet = workbook[sheet_name]
            table = sheet.iter_rows(values_only=True)
            header = [header_key(cell) for cell in next(table)]
            fields = [HEADER_FIELDS.get(name, "") for name in header]
            for raw in table:
                mapped = {
                    fields[index]: raw[index]
                    for index in range(min(len(fields), len(raw)))
                    if fields[index]
                }
                parsed = self._parse_row(mapped, priority, default_status, unknown)
                if parsed is None:
                    skipped += 1
                    continue
                rows.append(parsed)
        return rows, skipped, unknown

    def _parse_row(self, raw, priority, default_status, unknown):
        platform = parse_platform(plain(raw.get("platform")))
        link = canonical_link(raw.get("profile_link"))
        if not platform or not link:
            return None
        stage, outreach_status, known = map_status(raw.get("status"), default_status)
        if not known:
            label = status_key(raw.get("status"))
            if label:
                unknown.add(label)
        email = parse_email(raw.get("email"))
        other = plain(raw.get("other_contact"))[:250]
        raw_email = plain(raw.get("email"))
        if raw_email and not email and raw_email.lower() not in other.lower():
            other = ", ".join(part for part in (other, raw_email) if part)[:250]
        currency = parse_currency(plain(raw.get("currency")))
        price = parse_money(raw.get("price"))
        price_eur = parse_money(raw.get("price_eur"))
        if price is not None and currency == "EUR" and price_eur is None:
            price_eur = price
        raw_price, raw_currency = price, currency
        price, currency, price_eur = normalize_budget(price, currency, price_eur)
        comments = plain(raw.get("comments"))
        if raw_price is not None and price is None:
            comments = " ".join(
                part
                for part in (comments, f"Sheet amount {raw_price} {raw_currency} has no EUR amount.")
                if part
            )
        if not known and plain(raw.get("status")):
            comments = " ".join(part for part in (plain(raw.get("status")), comments) if part)
        sent_date = parse_day(raw.get("sent_date"))
        followup_1 = parse_day(raw.get("followup_1"))
        followup_2 = parse_day(raw.get("followup_2"))
        touched = bool(outreach_status or sent_date or plain(raw.get("method")) or followup_1 or followup_2)
        return {
            "priority": priority,
            "who": plain(raw.get("who"))[:150],
            "platform": platform,
            "profile_link": link,
            "name": (plain(raw.get("name")) or link)[:200],
            "niche": clean_string_list(plain(raw.get("niche"))),
            "country": plain(raw.get("country"))[:50],
            "language": plain(raw.get("language"))[:120],
            "followers": parse_whole(raw.get("followers")),
            "tier": parse_tier(plain(raw.get("tier"))) or "",
            "campaign": plain(raw.get("campaign"))[:200],
            "email": email,
            "other_contact": other,
            "method": plain(raw.get("method")),
            "email_outreached": plain(raw.get("email_outreached"))[:150],
            "stage": stage,
            "outreach_status": outreach_status,
            "sent_date": sent_date,
            "followup_1": followup_1,
            "followup_2": followup_2,
            "date_confirmed": parse_day(raw.get("date_confirmed")),
            "added_at": parse_day(raw.get("added_at")),
            "comments": comments,
            "price": price,
            "currency": currency,
            "price_eur": price_eur,
            "deliverables": clean_string_list(plain(raw.get("deliverables"))),
            "deliverables_notes": plain(raw.get("deliverables_notes")),
            "engagement_rate": parse_percent(raw.get("engagement_rate")),
            "audience_insights": plain(raw.get("audience_insights")),
            "avg_views": parse_whole(raw.get("avg_views")),
            "geo": plain(raw.get("geo"))[:120],
            "female_pct": parse_percent(raw.get("female_pct")),
            "male_pct": parse_percent(raw.get("male_pct")),
            "touched": touched,
        }

    def _collapse(self, rows):
        profiles = {}
        deals = {}
        names = set()
        for row in sorted(rows, key=lambda item: item["priority"]):
            key = profile_key(row["platform"], row["profile_link"])
            profiles[key] = self._merge_profile(profiles.get(key), row)
            names.add(row["campaign"])
            if not row["campaign"]:
                continue
            deal_key = (key[0], key[1], name_key(row["campaign"]))
            deals[deal_key] = self._merge_deal(deals.get(deal_key), row)
        names.discard("")
        return profiles, deals, names

    def _merge_profile(self, current, row):
        fields = (
            "name",
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
            "who",
        )
        if current is None:
            return {field: row[field] for field in fields} | {
                "platform": row["platform"],
                "profile_link": row["profile_link"],
            }
        merged = dict(current)
        for field in fields:
            merged[field] = keep_last(current[field], row[field])
        return merged

    def _merge_deal(self, current, row):
        if current is None:
            return dict(row)
        winner, other = (row, current) if row["priority"] >= current["priority"] else (current, row)
        merged = dict(other)
        for field, value in winner.items():
            if field == "touched":
                continue
            if filled(value):
                merged[field] = value
        merged["touched"] = bool(current["touched"] or row["touched"])
        merged["priority"] = max(current["priority"], row["priority"])
        return merged

    def _read_briefs(self, path: Path):
        import openpyxl

        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
        sheet = workbook["Briefs - Internal (CF)"]
        table = sheet.iter_rows(values_only=True)
        header = [header_key(cell) for cell in next(table)]
        wanted = {
            "campaign": "campaign",
            "campaign status": "status",
            "brief": "brief",
            "campaign owner": "owner",
        }
        fields = [wanted.get(name, "") for name in header]
        briefs = {}
        for raw in table:
            mapped = {
                fields[index]: raw[index]
                for index in range(min(len(fields), len(raw)))
                if fields[index]
            }
            name = plain(mapped.get("campaign"))[:200]
            if not name:
                continue
            briefs[name_key(name)] = {
                "name": name,
                "status": BRIEF_STATUS.get(status_key(mapped.get("status")), ""),
                "brief": plain(mapped.get("brief")),
                "owner": plain(mapped.get("owner"))[:150],
            }
        return briefs

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
        return User.objects.filter(is_superuser=True).first() or User.objects.order_by("id").first()

    def _campaigns(self, names, deals, users):
        existing = {}
        for campaign in Campaign.objects.all():
            existing[name_key(campaign.client_name)] = campaign
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
                status=CampaignStatus.OUTREACH,
                creators_needed=1,
            )
        return saved

    def _creators(self, profiles, users):
        existing = {}
        for creator in Creator.objects.all().only("id", "platform", "profile_link"):
            link = canonical_link(creator.profile_link)
            if link:
                existing[profile_key(creator.platform, link)] = creator
        to_create = []
        to_update = []
        for key, profile in profiles.items():
            creator = existing.get(key)
            if creator is None:
                to_create.append(profile)
                continue
            changed = self._apply_creator(creator, profile, users)
            if changed:
                to_update.append(creator)
        created = []
        for start in range(0, len(to_create), 400):
            batch = to_create[start : start + 400]
            created.extend(
                Creator.objects.bulk_create(
                    [self._new_creator(profile, users) for profile in batch]
                )
            )
        for creator in created:
            link = canonical_link(creator.profile_link)
            existing[profile_key(creator.platform, link)] = creator
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
                    "added_at",
                    "added_by",
                    "source",
                ],
                batch_size=400,
            )
        return existing, len(created), len(to_update)

    def _new_creator(self, profile, users):
        return Creator(
            platform=profile["platform"],
            profile_link=profile["profile_link"],
            influencer_name=profile["name"],
            niche=profile["niche"],
            country=profile["country"],
            language=profile["language"] or "English",
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
            source=SOURCE,
            added_by=self._find_user(users, profile["who"]),
            added_at=profile["added_at"],
        )

    def _apply_creator(self, creator, profile, users):
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
        put("niche", profile["niche"])
        put("country", profile["country"])
        put("language", profile["language"])
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
        put("added_at", profile["added_at"])
        if not creator.source:
            put("source", SOURCE)
        if creator.added_by_id is None:
            user = self._find_user(users, profile["who"])
            if user is not None:
                creator.added_by = user
                changed = True
        return changed

    def _deals(self, deals, campaigns, creators):
        existing = {
            (deal.campaign_id, deal.creator_id): deal
            for deal in CampaignCreator.objects.all()
        }
        to_create = []
        to_update = []
        self._deal_ids = {}
        for (platform, link, campaign_key), row in deals.items():
            campaign = campaigns.get(campaign_key)
            creator = creators.get((platform, link))
            if campaign is None or creator is None:
                continue
            current = existing.get((campaign.id, creator.id))
            if current is None:
                deal = self._new_deal(campaign, creator, row)
                to_create.append(deal)
                continue
            if self._apply_deal(current, row):
                to_update.append(current)
            self._deal_ids[(platform, link, campaign_key)] = current.id
        created_count = 0
        for start in range(0, len(to_create), 400):
            created = CampaignCreator.objects.bulk_create(to_create[start : start + 400])
            created_count += len(created)
            for deal in created:
                link = canonical_link(deal.creator.profile_link).lower()
                self._deal_ids[(deal.creator.platform, link, name_key(deal.campaign.client_name))] = deal.id
        if to_update:
            CampaignCreator.objects.bulk_update(
                to_update,
                [
                    "stage",
                    "fit_notes",
                    "deliverables",
                    "deliverables_notes",
                    "assigned_to",
                    "email_outreached",
                    "sent_date",
                    "creator_price",
                    "creator_currency",
                    "creator_price_eur",
                    "date_confirmed",
                    "added_by",
                    "margin_eur",
                ],
                batch_size=400,
            )
        return created_count, len(to_update)

    def _brief_status_applies(self, current, incoming):
        if incoming == CampaignStatus.CLOSED:
            return current != CampaignStatus.CLOSED
        if current in {CampaignStatus.CLOSED, CampaignStatus.CLIENT_SHARING}:
            return False
        return incoming == CampaignStatus.OUTREACH and current == CampaignStatus.DRAFT

    def _stage_moves_forward(self, current, incoming):
        order = {
            Stage.SHORTLISTED: 1,
            Stage.CONTACTED: 2,
            Stage.NEGOTIATING: 3,
            Stage.CONFIRMED: 4,
            Stage.SHARED: 5,
        }
        if incoming in {Stage.NOT_INTERESTED, Stage.UNRESPONSIVE}:
            return current in {Stage.SHORTLISTED, Stage.CONTACTED, Stage.NEGOTIATING}
        if current in {Stage.NOT_INTERESTED, Stage.UNRESPONSIVE, Stage.SHARED}:
            return False
        return order.get(incoming, 0) >= order.get(current, 0)

    def _new_deal(self, campaign, creator, row):
        return CampaignCreator(
            campaign=campaign,
            creator=creator,
            stage=row["stage"],
            fit_notes=row["comments"],
            deliverables=row["deliverables"],
            deliverables_notes=row["deliverables_notes"],
            assigned_to=row["who"],
            email_outreached=row["email_outreached"],
            sent_date=row["sent_date"],
            creator_price=row["price"],
            creator_currency=row["currency"],
            creator_price_eur=row["price_eur"],
            date_confirmed=row["date_confirmed"],
            added_by=row["who"],
        )

    def _apply_deal(self, deal, row):
        changed = False

        def put(field, value):
            nonlocal changed
            if not filled(value):
                return
            if getattr(deal, field) != value:
                setattr(deal, field, value)
                changed = True

        if self._stage_moves_forward(deal.stage, row["stage"]):
            put("stage", row["stage"])
        put("fit_notes", row["comments"])
        put("deliverables", row["deliverables"])
        put("deliverables_notes", row["deliverables_notes"])
        put("assigned_to", row["who"])
        put("email_outreached", row["email_outreached"])
        put("sent_date", row["sent_date"])
        put("date_confirmed", row["date_confirmed"])
        put("added_by", row["who"])
        if row["price"] is not None:
            put("creator_price", row["price"])
            put("creator_currency", row["currency"])
            put("creator_price_eur", row["price_eur"])
        if deal.creator_price_eur is not None and deal.client_price_eur is not None:
            margin = deal.client_price_eur - deal.creator_price_eur
            if deal.margin_eur != margin:
                deal.margin_eur = margin
                changed = True
        return changed

    def _outreach(self, deals, campaigns, creators):
        existing = set(
            Outreach.objects.values_list(
                "campaign_creator_id",
                "outreach_status",
                "sent_at",
                "channel",
                "message_summary",
            )
        )
        pending = []
        seen = set(existing)
        for (platform, link, campaign_key), row in deals.items():
            deal_id = self._deal_ids.get((platform, link, campaign_key))
            if deal_id is None or not row["touched"]:
                continue
            for item in self._messages(deal_id, row):
                key = (
                    item["campaign_creator_id"],
                    item["outreach_status"],
                    item["sent_at"],
                    item["channel"],
                    item["message_summary"],
                )
                if key in seen:
                    continue
                seen.add(key)
                pending.append(Outreach(**item))
        for start in range(0, len(pending), 400):
            Outreach.objects.bulk_create(pending[start : start + 400])
        return len(pending)

    def _messages(self, deal_id, row):
        channel = parse_channel(row["method"]) or (
            Channel.EMAIL if parse_email(row["email_outreached"]) else Channel.OTHER
        )
        contact = parse_email(row["email_outreached"])
        summary = row["comments"]
        messages = []
        if row["outreach_status"] or row["sent_date"] or row["method"]:
            messages.append(
                self._message(
                    deal_id,
                    channel,
                    row["outreach_status"] or OutreachStatus.SENT,
                    summary,
                    contact,
                    row["price"],
                    row["currency"],
                    row["who"],
                    as_aware(row["sent_date"]),
                )
            )
        for label, day in (("Follow-up 1", row["followup_1"]), ("Follow-up 2", row["followup_2"])):
            if day is None:
                continue
            if row["sent_date"] == day and row["outreach_status"] == OutreachStatus.FOLLOW_UP:
                continue
            note = label if not summary else f"{label}. {summary}"
            messages.append(
                self._message(
                    deal_id,
                    channel,
                    OutreachStatus.FOLLOW_UP,
                    note,
                    contact,
                    None,
                    "",
                    row["who"],
                    as_aware(day),
                )
            )
        return messages

    def _message(self, deal_id, channel, status, summary, contact, price, currency, who, sent_at):
        return {
            "campaign_creator_id": deal_id,
            "channel": channel,
            "direction": Direction.SENT,
            "outreach_status": status,
            "message_summary": summary,
            "contact_email": contact,
            "quoted_price": price,
            "offered_price": None,
            "currency": currency if price is not None else "",
            "sent_by": who,
            "sent_at": sent_at,
        }

    def _briefs(self, briefs, campaigns, users):
        updated = 0
        fallback = self._fallback_user(users)
        for key, brief in briefs.items():
            campaign = campaigns.get(key)
            if campaign is None:
                owner = self._find_user(users, brief["owner"]) or fallback
                campaign = Campaign.objects.create(
                    client_name=brief["name"],
                    campaign_owner=owner,
                    created_by=owner,
                    status=brief["status"] or CampaignStatus.DRAFT,
                    remarks_brief=brief["brief"],
                    creators_needed=1,
                )
                campaigns[key] = campaign
                updated += 1
                continue
            fields = []
            if brief["status"] and self._brief_status_applies(campaign.status, brief["status"]):
                campaign.status = brief["status"]
                fields.append("status")
            if brief["brief"] and not campaign.remarks_brief:
                campaign.remarks_brief = brief["brief"]
                fields.append("remarks_brief")
            if fields:
                campaign.save(update_fields=fields)
                updated += 1
        return updated

    def _preview(self, profiles, deals, names):
        existing_creators = {
            profile_key(creator.platform, canonical_link(creator.profile_link))
            for creator in Creator.objects.all().only("platform", "profile_link")
        }
        existing_campaigns = {name_key(name) for name in Campaign.objects.values_list("client_name", flat=True)}
        new_creators = sum(1 for key in profiles if key not in existing_creators)
        new_campaigns = sum(1 for name in names if name_key(name) not in existing_campaigns)
        self.stdout.write(
            f"Dry run: {new_creators} new creators, {len(profiles) - new_creators} already stored, "
            f"{new_campaigns} new campaigns, {len(deals)} deals."
        )
