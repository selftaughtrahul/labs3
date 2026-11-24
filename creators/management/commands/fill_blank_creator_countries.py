"""Fill a blank creator country from the public profile page."""

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlsplit

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from creators.masters import lookup_named
from creators.models import Country, Creator
from creators.page_country import (
    choose_known_country,
    fetch_profile_page,
    profile_url_to_fetch,
    scrapingbee_api_key,
)
from creators.profile_details import details_from_page

MAX_WORKERS = 50


def _handle(link: str) -> str:
    parts = [part for part in urlsplit(link or "").path.split("/") if part]
    if not parts:
        return ""
    token = parts[-1].lstrip("@").casefold()
    if token in {"about", "featured"} and len(parts) > 1:
        token = parts[-2].lstrip("@").casefold()
    if len(token) < 4 or token in {"channel", "user", "watch"}:
        return ""
    return token


def _classify(creator_id, name: str, page_url: str) -> tuple:
    """Fetch one profile away from the database and return the country it names."""
    lowered = page_url.lower()
    render_js = "youtube.com" in lowered or "youtu.be" in lowered
    premium = "instagram.com" in lowered or "tiktok.com" in lowered
    try:
        html = fetch_profile_page(page_url, render_js=render_js, premium=premium)
    except RuntimeError as exc:
        return creator_id, name, page_url, "", str(exc)
    return creator_id, name, page_url, details_from_page(html).country, ""


class Command(BaseCommand):
    help = "Set the country foreign key on creators whose country is blank, using the public profile."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Stop after this many profiles. 0 means every blank country.",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=20,
            help="Profiles to fetch at the same time. ScrapingBee allows 50.",
        )
        parser.add_argument(
            "--exclude",
            default="",
            help="Skip profile links that contain this text.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the country that would be saved without writing it.",
        )

    def handle(self, *args, **options):
        if not scrapingbee_api_key():
            raise CommandError("SCRAPINGBEE_API_KEY is required.")
        workers = options["workers"]
        if workers < 1 or workers > MAX_WORKERS:
            raise CommandError(f"--workers must be from 1 to {MAX_WORKERS}.")
        limit = options["limit"]
        dry_run = options["dry_run"]
        copied = self._copy_known_countries(dry_run)
        self.stdout.write(f"propagated {copied}")
        creators = Creator.objects.filter(country__isnull=True).exclude(
            Q(profile_link="") | Q(profile_link__isnull=True)
        )
        if options["exclude"]:
            creators = creators.exclude(profile_link__icontains=options["exclude"])
        creators = creators.order_by("influencer_name", "platform")
        rows = []
        for creator_id, name, profile_link in creators.values_list(
            "pk", "influencer_name", "profile_link"
        ):
            page_url = profile_url_to_fetch(profile_link)
            if page_url:
                rows.append((creator_id, name, page_url))
            if limit and len(rows) >= limit:
                break
        self.stdout.write(f"profiles {len(rows)} workers {workers}")
        filled, unmatched, failed, pending, stop = self._fetch(rows, workers, dry_run)
        for attempt in range(1, 4):
            if stop or not pending:
                break
            self.stdout.write(f"retry {attempt} profiles {len(pending)}")
            again, skipped, errors, pending, stop = self._fetch(pending, workers, dry_run)
            filled += again
            unmatched += skipped
            failed += errors
            propagated = self._copy_known_countries(dry_run)
            self.stdout.write(f"propagated {propagated}")
            if propagated == 0 and again == 0:
                break
        else:
            propagated = 0
        while not dry_run:
            propagated = self._copy_known_countries(dry_run)
            self.stdout.write(f"propagated {propagated}")
            if propagated == 0:
                break
        left = Creator.objects.filter(country__isnull=True).count()
        self.stdout.write(
            f"filled {filled} unmatched {unmatched} failed {failed} remaining {left}"
        )

    def _fetch(self, rows, workers: int, dry_run: bool):
        filled = 0
        unmatched = 0
        failed = 0
        pending = []
        stop = False
        for start in range(0, len(rows), workers):
            if stop:
                pending.extend(rows[start:])
                break
            batch = rows[start : start + workers]
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [
                    pool.submit(_classify, creator_id, name, page_url)
                    for creator_id, name, page_url in batch
                ]
                for future in as_completed(futures):
                    creator_id, name, page_url, country_name, error = future.result()
                    if error:
                        failed += 1
                        pending.append((creator_id, name, page_url))
                        self.stdout.write(f"FAIL {name}: {error}")
                        if "returned 401" in error or "returned 403" in error:
                            stop = True
                        continue
                    if not country_name:
                        unmatched += 1
                        self.stdout.write(f"BLANK {name} {page_url}")
                        continue
                    filled += 1
                    prefix = "Would set" if dry_run else "Set"
                    self.stdout.write(f"{prefix} {name} -> {country_name}")
                    if dry_run:
                        continue
                    country = lookup_named(Country, country_name)
                    Creator.objects.filter(pk=creator_id, country__isnull=True).update(
                        country=country
                    )
        return filled, unmatched, failed, pending, stop

    def _copy_known_countries(self, dry_run: bool) -> int:
        rows = list(
            Creator.objects.values_list(
                "pk", "influencer_name", "profile_link", "country__name", "language__name"
            )
        )
        by_name = defaultdict(set)
        by_handle = defaultdict(set)
        for _pk, name, link, country, _language in rows:
            if not country:
                continue
            by_name[" ".join((name or "").split()).casefold()].add(country)
            token = _handle(link)
            if token:
                by_handle[token].add(country)
        copied = 0
        for creator_id, name, link, country, language in rows:
            if country:
                continue
            choice = choose_known_country(
                by_name.get(" ".join((name or "").split()).casefold(), set()),
                by_handle.get(_handle(link), set()),
                language or "",
            )
            if not choice:
                continue
            copied += 1
            prefix = "Would copy" if dry_run else "Copy"
            self.stdout.write(f"{prefix} {name} -> {choice}")
            if dry_run:
                continue
            country_row = lookup_named(Country, choice)
            Creator.objects.filter(pk=creator_id, country__isnull=True).update(country=country_row)
        return copied
