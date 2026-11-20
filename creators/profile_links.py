"""Normalize a profile URL so the same account is one creator."""

import re
from urllib.parse import unquote, urlsplit

PATH_SUFFIXES = ("/videos", "/featured", "/shorts", "/about", "/streams", "/reels")


def plain_link(value) -> str:
    return " ".join(str(value or "").split())


def canonical_link(value) -> str:
    raw = plain_link(value)
    if not raw or "do not add" in raw.lower() or "do not delete" in raw.lower() or raw.startswith("#"):
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
