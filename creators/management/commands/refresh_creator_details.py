"""Fill blank creator fields from the public profile, in parallel.

Existing values are left unchanged. A field is written only when it is still
blank at the moment of the update, so a value typed in admin during the run
is kept. Gender, geo, and audience insights are stored only when the page
states them, or when recent posts on the page include likes and views.
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from django.db.models import Q
from django.db.utils import OperationalError

from creators.choices import Platform
from creators.masters import ISO_639_1_LANGUAGES, MasterCache, fold_key
from creators.models import Country, Creator, Language
from creators.page_country import (
    fetch_profile_page,
    official_country,
    profile_url_to_fetch,
    scrapingbee_api_key,
)
from creators.profile_details import (
    ProfileFacts,
    StoredProfile,
    blank_field_updates,
    details_from_page,
    merge_facts,
    youtube_videos_url,
)

MAX_WORKERS = 50
_NULL_FIELDS = {
    "followers",
    "engagement_rate",
    "avg_views",
    "female_pct",
    "male_pct",
    "country",
    "language",
}
_TEXT_FIELDS = {"email", "other_contact", "geo", "audience_insights"}
_KNOWN_LANGUAGES = {fold_key(name) for name in ISO_639_1_LANGUAGES}


def _call_db(action):
    """Retry a database call when the server briefly cannot be reached."""
    delay = 5
    for attempt in range(6):
        try:
            return action()
        except OperationalError:
            close_old_connections()
            if attempt == 5:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 60)


def save_blank_fields(creator_id, updates: dict[str, object]) -> list[str]:
    """Write each field only while that column is still blank."""
    saved = []
    for field, value in updates.items():
        rows = Creator.objects.filter(pk=creator_id)
        if field in _NULL_FIELDS:
            rows = rows.filter(**{f"{field}__isnull": True})
        elif field == "niche":
            rows = rows.filter(Q(niche=[]) | Q(niche__isnull=True))
        elif field in _TEXT_FIELDS:
            rows = rows.filter(Q(**{field: ""}) | Q(**{f"{field}__isnull": True}))
        else:
            continue
        if rows.update(**{field: value}):
            saved.append(field)
    return saved


def _stored(row: dict) -> StoredProfile:
    niche = row["niche"] if isinstance(row["niche"], (list, tuple)) else ()
    labels = tuple(part.strip() for part in niche if isinstance(part, str) and part.strip())
    return StoredProfile(
        niche=labels,
        country=row["country__name"] or "",
        language=row["language__name"] or "",
        followers=row["followers"],
        email=(row["email"] or "").strip(),
        engagement_rate=row["engagement_rate"],
        avg_views=row["avg_views"],
        other_contact=(row["other_contact"] or "").strip(),
        geo=(row["geo"] or "").strip(),
        female_pct=row["female_pct"],
        male_pct=row["male_pct"],
        audience_insights=(row["audience_insights"] or "").strip(),
    )


def _resolve(updates: dict[str, object], countries: MasterCache, languages: MasterCache) -> dict[str, object]:
    """Turn country and language names into master rows. Drop unknown names."""
    resolved = dict(updates)
    country_name = official_country(str(resolved.get("country") or ""))
    if "country" in resolved:
        if not country_name:
            resolved.pop("country")
        else:
            countries.ensure([country_name])
            country = countries.get(country_name)
            if country is None:
                resolved.pop("country")
            else:
                resolved["country"] = country
    language_name = str(resolved.get("language") or "")
    if "language" in resolved:
        if fold_key(language_name) not in _KNOWN_LANGUAGES:
            resolved.pop("language")
        else:
            languages.ensure([language_name])
            language = languages.get(language_name)
            if language is None:
                resolved.pop("language")
            else:
                resolved["language"] = language
    return resolved


def _fetch_page(url: str, *, render_js: bool) -> str:
    return fetch_profile_page(url, timeout=70 if render_js else 45, render_js=render_js)


def _blocked(error: str) -> bool:
    return any(code in error for code in ("returned 401", "returned 403", "returned 429"))


def _load_facts(page_url: str, platform: str, render_js: str) -> tuple[ProfileFacts, str]:
    """Download a profile away from the database and read the facts it states."""
    html, error = _download(page_url, render_js=render_js == "always")
    facts = details_from_page(html) if html else ProfileFacts()
    if error and not html:
        return facts, error
    if render_js == "auto" and not facts.useful():
        rendered, render_error = _download(page_url, render_js=True)
        if rendered:
            facts = merge_facts(facts, details_from_page(rendered))
            error = ""
        elif render_error and not facts.useful():
            error = render_error
    if platform == Platform.YOUTUBE and facts.avg_views is None and not _blocked(error):
        videos, _video_error = _download(youtube_videos_url(page_url), render_js=render_js != "never")
        if videos:
            facts = merge_facts(facts, details_from_page(videos))
    if facts.useful():
        return facts, ""
    return facts, error


def _download(url: str, *, render_js: bool) -> tuple[str, str]:
    try:
        return _fetch_page(url, render_js=render_js), ""
    except RuntimeError as exc:
        return "", str(exc)


def _read(creator_id, name: str, platform: str, page_url: str, render_js: str) -> tuple:
    """Keep one broken page from stopping the rest of the batch."""
    try:
        facts, error = _load_facts(page_url, platform, render_js)
    except Exception as exc:
        return creator_id, name, page_url, ProfileFacts(), f"Could not read page: {exc}"
    return creator_id, name, page_url, facts, error


class Command(BaseCommand):
    help = "Fill blank creator details from public profile pages, using ScrapingBee in parallel."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Stop after this many profiles. 0 means every profile that still has a blank field.",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=10,
            help="Profiles to fetch at the same time. ScrapingBee allows 50.",
        )
        parser.add_argument("--platform", default="", help="Only this platform, for example instagram.")
        parser.add_argument("--link", default="", help="Only profile links that contain this text.")
        parser.add_argument("--exclude", default="", help="Skip profile links that contain this text.")
        parser.add_argument(
            "--render-js",
            choices=("auto", "always", "never"),
            default="auto",
            help="auto renders JavaScript only when the first download has no profile facts.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the blank fields that would be saved without writing them.",
        )

    def handle(self, *args, **options):
        if not scrapingbee_api_key():
            raise CommandError("SCRAPINGBEE_API_KEY is required.")
        workers = options["workers"]
        if workers < 1 or workers > MAX_WORKERS:
            raise CommandError(f"--workers must be from 1 to {MAX_WORKERS}.")
        platform = (options["platform"] or "").strip().lower()
        if platform and platform not in Platform.values:
            raise CommandError("--platform must be one of: " + ", ".join(Platform.values) + ".")
        limit = options["limit"]
        if limit < 0:
            raise CommandError("--limit cannot be negative.")

        creators = Creator.objects.exclude(Q(profile_link="") | Q(profile_link__isnull=True)).filter(
            Q(country__isnull=True)
            | Q(language__isnull=True)
            | Q(followers__isnull=True)
            | Q(engagement_rate__isnull=True)
            | Q(avg_views__isnull=True)
            | Q(email="")
            | Q(email__isnull=True)
            | Q(other_contact="")
            | Q(niche=[])
            | Q(niche__isnull=True)
        )
        if platform:
            creators = creators.filter(platform=platform)
        if options["link"]:
            creators = creators.filter(profile_link__icontains=options["link"])
        if options["exclude"]:
            creators = creators.exclude(profile_link__icontains=options["exclude"])
        creators = creators.order_by("influencer_name", "platform")
        columns = (
            "pk",
            "influencer_name",
            "platform",
            "profile_link",
            "niche",
            "country__name",
            "language__name",
            "followers",
            "email",
            "engagement_rate",
            "avg_views",
            "other_contact",
            "geo",
            "female_pct",
            "male_pct",
            "audience_insights",
        )
        jobs = []
        stored_by_id = {}
        for row in creators.values(*columns):
            page_url = profile_url_to_fetch(row["profile_link"])
            if not page_url:
                continue
            stored_by_id[row["pk"]] = _stored(row)
            jobs.append((row["pk"], row["influencer_name"], row["platform"], page_url))
            if limit and len(jobs) >= limit:
                break
        self.stdout.write(f"profiles {len(jobs)} workers {workers}")
        if not jobs:
            return

        countries = MasterCache(Country)
        languages = MasterCache(Language)
        updated = 0
        unchanged = 0
        unmatched = 0
        failed = 0
        stop = False
        render_js = options["render_js"]
        dry_run = options["dry_run"]
        for start in range(0, len(jobs), workers):
            if stop:
                break
            batch = jobs[start : start + workers]
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [
                    pool.submit(_read, creator_id, name, platform_name, page_url, render_js)
                    for creator_id, name, platform_name, page_url in batch
                ]
                outcomes = [future.result() for future in as_completed(futures)]
            close_old_connections()
            for creator_id, name, page_url, facts, error in outcomes:
                if error:
                    failed += 1
                    self.stdout.write(f"FAIL {name}: {error}")
                    if _blocked(error):
                        stop = True
                    continue
                if not facts.useful():
                    unmatched += 1
                    self.stdout.write(f"BLANK {name} {page_url}")
                    continue
                updates = _call_db(
                    lambda: _resolve(
                        blank_field_updates(stored_by_id[creator_id], facts),
                        countries,
                        languages,
                    )
                )
                if not updates:
                    unchanged += 1
                    continue
                label = ", ".join(updates)
                prefix = "Would set" if dry_run else "Set"
                self.stdout.write(f"{prefix} {name}: {label}")
                if dry_run:
                    updated += 1
                    continue
                saved = _call_db(lambda: save_blank_fields(creator_id, updates))
                if saved:
                    updated += 1
                else:
                    unchanged += 1
        self.stdout.write(f"updated {updated} unchanged {unchanged} unmatched {unmatched} failed {failed}")
