"""Turn stored campaign platform text into the platform list."""

import re

from creators.choices import Platform

# Exact tokens from the central sheet, plus the short names the brief sheet uses.
TOKEN_ALIASES = {
    "instagram": Platform.INSTAGRAM,
    "ig": Platform.INSTAGRAM,
    "youtube": Platform.YOUTUBE,
    "yt": Platform.YOUTUBE,
    "tiktok": Platform.TIKTOK,
    "tt": Platform.TIKTOK,
    "twitch": Platform.TWITCH,
    "x": Platform.X,
    "twitter": Platform.X,
    "facebook": Platform.FACEBOOK,
    "fb": Platform.FACEBOOK,
    "linkedin": Platform.LINKEDIN,
    "kick": Platform.KICK,
}

WORD_ALIASES = (
    ("instagram", Platform.INSTAGRAM),
    ("tiktok", Platform.TIKTOK),
    ("youtube", Platform.YOUTUBE),
    ("facebook", Platform.FACEBOOK),
    ("linkedin", Platform.LINKEDIN),
    ("twitch", Platform.TWITCH),
    ("kick", Platform.KICK),
    ("twitter", Platform.X),
)


def normalize_platform_token(value):
    """Return the known slugs inside one stored token."""
    if not isinstance(value, str):
        return []
    raw = " ".join(value.split()).lower()
    if not raw:
        return []
    if raw in Platform.values:
        return [raw]
    if raw in TOKEN_ALIASES:
        return [TOKEN_ALIASES[raw]]
    found = []
    if re.search(r"\big\b", raw):
        found.append(Platform.INSTAGRAM)
    if re.search(r"\btt\b", raw):
        found.append(Platform.TIKTOK)
    if re.search(r"\bx\b", raw):
        found.append(Platform.X)
    for word, slug in WORD_ALIASES:
        if word in raw and slug not in found:
            found.append(slug)
    return found


def normalize_platforms(values):
    """Return (slugs, unknown tokens). First-seen order is kept."""
    if not isinstance(values, list):
        return [], []
    slugs = []
    unknown = []
    for value in values:
        matched = normalize_platform_token(value)
        if matched:
            for slug in matched:
                if slug not in slugs:
                    slugs.append(slug)
            continue
        if isinstance(value, str) and value.strip():
            unknown.append(" ".join(value.split()))
        elif value not in (None, ""):
            unknown.append(str(value))
    return slugs, unknown
