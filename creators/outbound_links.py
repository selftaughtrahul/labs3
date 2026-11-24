"""Pick profile URLs that a public page links out to."""

import re
from collections import defaultdict
from urllib.parse import unquote, urlsplit

from creators.profile_links import canonical_link

HOSTS = (
    ("instagram.com", "instagram"),
    ("instagr.am", "instagram"),
    ("tiktok.com", "tiktok"),
    ("youtube.com", "youtube"),
    ("youtu.be", "youtube"),
    ("twitter.com", "x"),
    ("x.com", "x"),
    ("facebook.com", "facebook"),
    ("fb.com", "facebook"),
    ("fb.watch", "facebook"),
    ("linkedin.com", "linkedin"),
    ("twitch.tv", "twitch"),
    ("kick.com", "kick"),
)
_URL = re.compile(r"https?://(?:(?!https?://)[^\s\"'<>\\])+", re.I)
_UNICODE = re.compile(r"\\u([0-9a-fA-F]{4})")
_SKIP = {
    "instagram": {
        "about",
        "accounts",
        "developer",
        "direct",
        "directory",
        "emails",
        "explore",
        "legal",
        "p",
        "privacy",
        "reel",
        "reels",
        "stories",
        "terms",
    },
    "tiktok": {"discover", "explore", "following", "foryou", "live", "login", "signup"},
    "youtube": {
        "account",
        "clip",
        "embed",
        "feed",
        "playlist",
        "premium",
        "redirect",
        "results",
        "shorts",
        "t",
        "watch",
    },
    "x": {"explore", "home", "i", "intent", "privacy", "search", "settings", "share", "tos"},
    "facebook": {
        "dialog",
        "events",
        "groups",
        "help",
        "login",
        "marketplace",
        "pages",
        "policies",
        "privacy",
        "share",
        "sharer",
        "stories",
        "watch",
    },
    "twitch": {"directory", "downloads", "jobs", "login", "search", "settings", "signup"},
    "kick": {"browse", "categories", "dashboard", "search"},
    "linkedin": {"feed", "jobs", "login", "school", "signup"},
}


HUBS = {
    "beacons.ai",
    "bento.me",
    "bio.link",
    "bio.site",
    "campsite.bio",
    "direct.me",
    "hoo.be",
    "linktr.ee",
    "lnk.bio",
    "msha.ke",
    "pillar.io",
    "snipfeed.co",
    "solo.to",
    "stan.store",
    "tap.bio",
    "taplink.cc",
}


def platform_from_url(link) -> str:
    host = _bare_host(link)
    for suffix, platform in HOSTS:
        if host == suffix:
            return platform
    return ""


def _bare_host(link) -> str:
    host = urlsplit(link or "").netloc.lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    if host.startswith("mobile."):
        host = host[7:]
    elif host.startswith("m.") and host.count(".") >= 2:
        host = host[2:]
    return host


def _is_profile(platform: str, link: str) -> bool:
    parts = [part for part in urlsplit(link).path.split("/") if part]
    if not parts:
        return False
    if parts[0].lower() in _SKIP.get(platform, ()):
        return False
    if platform == "instagram":
        return len(parts) == 1 and re.fullmatch(r"[A-Za-z0-9._]{1,30}", parts[0]) is not None
    if platform == "tiktok":
        return len(parts) == 1 and parts[0].startswith("@") and len(parts[0]) > 1
    if platform == "youtube":
        if len(parts) == 1 and parts[0].startswith("@"):
            return True
        if len(parts) == 2 and parts[0].lower() == "channel":
            return parts[1].startswith("UC") and len(parts[1]) == 24
        return len(parts) == 2 and parts[0].lower() in {"c", "user"} and bool(parts[1])
    if platform in {"x", "twitch", "kick"}:
        return len(parts) == 1 and re.fullmatch(r"[A-Za-z0-9_]{1,30}", parts[0]) is not None
    if platform == "facebook":
        return len(parts) == 1 and re.fullmatch(r"[A-Za-z0-9.\-]{1,80}", parts[0]) is not None
    if platform == "linkedin":
        return len(parts) == 2 and parts[0].lower() == "in" and bool(parts[1])
    return False


def visible_text(html: str) -> str:
    """Undo the escaped URLs Instagram and YouTube embed in the page."""
    text = (html or "").replace("\\/", "/").replace("&amp;", "&")
    text = _UNICODE.sub(lambda match: chr(int(match.group(1), 16)), text)
    return unquote(unquote(text))


def profile_url(raw: str) -> str:
    """Canonical profile URL, without a mobile host or tracking glued to the path."""
    link = canonical_link(raw.rstrip(").,;").split("&", 1)[0])
    if not link:
        return ""
    parts = urlsplit(link)
    host = _bare_host(link)
    if not host:
        return ""
    return f"https://{host}{parts.path}"


def links_by_platform(html: str) -> dict[str, set[str]]:
    """Return canonical profile links grouped by the platform they belong to."""
    found = defaultdict(set)
    for raw in _URL.findall(visible_text(html)):
        link = profile_url(raw)
        platform = platform_from_url(link)
        if platform and _is_profile(platform, link):
            found[platform].add(link)
    return dict(found)


def hub_links(html: str) -> list[str]:
    """Return link-in-bio pages named on the profile, at most two."""
    found = []
    for raw in _URL.findall(visible_text(html)):
        link = profile_url(raw)
        host = _bare_host(link)
        path = urlsplit(link).path
        if host not in HUBS or path in {"", "/"}:
            continue
        if link not in found:
            found.append(link)
        if len(found) == 2:
            break
    return found


def single_link(links: dict[str, set[str]], platform: str, source: str) -> str:
    """Return the one profile for this platform, ignoring the page that was fetched."""
    choices = [
        link
        for link in dict.fromkeys(links.get(platform, ()))
        if link.lower() != (source or "").lower()
    ]
    handles = [link for link in choices if "/@" in urlsplit(link).path or urlsplit(link).path.startswith("/@")]
    if len(handles) == 1:
        return handles[0]
    if len(choices) == 1:
        return choices[0]
    return ""
