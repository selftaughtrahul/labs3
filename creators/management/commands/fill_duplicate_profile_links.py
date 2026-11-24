"""Replace a copied profile URL with the link published on that page."""

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from creators.models import Creator
from creators.outbound_links import hub_links, links_by_platform, platform_from_url, single_link
from creators.page_country import fetch_profile_page, scrapingbee_api_key
from creators.profile_links import canonical_link

MAX_WORKERS = 20


def _needs_premium(url: str) -> bool:
    return platform_from_url(url) in {"instagram", "tiktok"}


def _fetch(url: str) -> tuple[str, dict, list, str]:
    premium = _needs_premium(url)
    last = "ScrapingBee request failed"
    for render_js in (False, False):
        try:
            html = fetch_profile_page(url, premium=premium, render_js=render_js)
        except RuntimeError as exc:
            last = str(exc)
            if "returned 401" in last or "returned 403" in last:
                return url, {}, [], last
            if "timed out" in last or "returned 500" in last:
                continue
            return url, {}, [], last
        return url, links_by_platform(html), hub_links(html), ""
    if not platform_from_url(url) and ("returned 500" in last or "timed out" in last):
        try:
            html = fetch_profile_page(url, render_js=True)
        except RuntimeError as exc:
            return url, {}, [], str(exc)
        return url, links_by_platform(html), hub_links(html), ""
    return url, {}, [], last


class Command(BaseCommand):
    help = "Find the real profile URL for duplicate rows from the public page, then save it."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Stop after this many duplicated links. 0 means all of them.",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=8,
            help="Pages to fetch at the same time. ScrapingBee allows 50.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the link that would be saved without writing it.",
        )

    def handle(self, *args, **options):
        if not scrapingbee_api_key():
            raise CommandError("SCRAPINGBEE_API_KEY is required.")
        workers = options["workers"]
        if workers < 1 or workers > MAX_WORKERS:
            raise CommandError(f"--workers must be from 1 to {MAX_WORKERS}.")
        creators = list(Creator.objects.only("id", "platform", "influencer_name", "profile_link"))
        groups = defaultdict(list)
        occupied = defaultdict(set)
        fetch_url = {}
        for creator in creators:
            canonical = canonical_link(creator.profile_link)
            key = canonical.lower()
            if not key:
                continue
            groups[key].append(creator)
            occupied[key].add((creator.platform, creator.pk))
            fetch_url.setdefault(key, canonical)
        duplicated = []
        for key, rows in groups.items():
            if len(rows) < 2 or not platform_from_url(key):
                continue
            if any(row.platform != platform_from_url(key) for row in rows):
                duplicated.append(key)
        duplicated.sort()
        if options["limit"]:
            duplicated = duplicated[: options["limit"]]
        self.stdout.write(f"duplicated links {len(duplicated)} workers {workers}")

        def collect(urls):
            found = {}
            stop = False
            for start in range(0, len(urls), workers):
                if stop:
                    break
                batch = urls[start : start + workers]
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = [pool.submit(_fetch, url) for url in batch]
                    for future in as_completed(futures):
                        url, links, hubs, error = future.result()
                        if error:
                            found[url] = ({}, [], error)
                            self.stdout.write(f"FAIL {url}: {error}")
                            if "returned 401" in error or "returned 403" in error:
                                stop = True
                            continue
                        found[url] = (links, hubs, "")
            return found

        pages = {}
        for key, result in collect([fetch_url[key] for key in duplicated]).items():
            pages[key.lower()] = result
        extra = []
        for key in duplicated:
            links, hubs, error = pages.get(key, ({}, [], "not fetched"))
            if error:
                continue
            source = platform_from_url(key)
            for row in groups[key]:
                if row.platform != source and not single_link(links, row.platform, key):
                    extra.extend(hub for hub in hubs if hub not in pages and hub not in extra)
                    break
        if extra:
            self.stdout.write(f"link pages {len(extra)}")
            pages.update(collect(extra))

        updates = []
        missing = 0
        collided = 0
        claimed = set()
        for key in duplicated:
            links, hubs, error = pages.get(key, ({}, [], "not fetched"))
            if error:
                missing += len([row for row in groups[key] if row.platform != platform_from_url(key)])
                continue
            merged = {platform: set(values) for platform, values in links.items()}
            for hub in hubs:
                hub_links_found, _hubs, hub_error = pages.get(hub, ({}, [], "not fetched"))
                if hub_error:
                    continue
                for platform, values in hub_links_found.items():
                    merged.setdefault(platform, set()).update(values)
            source = platform_from_url(key)
            for row in groups[key]:
                if row.platform == source:
                    continue
                found = single_link(merged, row.platform, key)
                if not found:
                    missing += 1
                    self.stdout.write(f"MISSING {row.influencer_name} {row.platform} from {key}")
                    continue
                owners = occupied.get(found.lower(), set())
                taken = any(platform == row.platform and pk != row.pk for platform, pk in owners)
                claim = (row.platform, found.lower())
                if taken or claim in claimed:
                    collided += 1
                    self.stdout.write(f"KEPT {row.influencer_name} {row.platform} {found} already stored")
                    continue
                claimed.add(claim)
                occupied[found.lower()].add((row.platform, row.pk))
                row.profile_link = found
                updates.append(row)
                prefix = "Would set" if options["dry_run"] else "Set"
                self.stdout.write(f"{prefix} {row.influencer_name} {row.platform} {found}")

        if updates and not options["dry_run"]:
            with transaction.atomic():
                Creator.objects.bulk_update(updates, ["profile_link"], batch_size=200)
        self.stdout.write(
            f"updated {len(updates)} missing {missing} already stored {collided}"
        )
