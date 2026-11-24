"""Read a creator's country from a public profile page."""

import json
import os
import re
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from creators.countries import CANONICAL_SET, canonical_country_name

_YOUTUBE_SIMPLE_TEXT = re.compile(
    r'"country"\s*:\s*\{\s*"simpleText"\s*:\s*"(?P<name>(?:\\.|[^"\\])*)"'
)
_YOUTUBE_ABOUT = re.compile(
    r'"aboutChannelViewModel".{0,5000}?"country"\s*:\s*"(?P<name>(?:\\.|[^"\\])*)"',
    re.DOTALL,
)
_ISO2 = {
    "AE": "United Arab Emirates",
    "AR": "Argentina",
    "AT": "Austria",
    "AU": "Australia",
    "BE": "Belgium",
    "BG": "Bulgaria",
    "BR": "Brazil",
    "CA": "Canada",
    "CH": "Switzerland",
    "CL": "Chile",
    "CN": "China",
    "CO": "Colombia",
    "CZ": "Czech Republic",
    "DE": "Germany",
    "DK": "Denmark",
    "EG": "Egypt",
    "ES": "Spain",
    "FI": "Finland",
    "FR": "France",
    "GB": "United Kingdom",
    "GR": "Greece",
    "HK": "Hong Kong",
    "HU": "Hungary",
    "ID": "Indonesia",
    "IE": "Ireland",
    "IL": "Israel",
    "IN": "India",
    "IT": "Italy",
    "JP": "Japan",
    "KR": "South Korea",
    "MX": "Mexico",
    "MY": "Malaysia",
    "NG": "Nigeria",
    "NL": "Netherlands",
    "NO": "Norway",
    "NZ": "New Zealand",
    "PE": "Peru",
    "PH": "Philippines",
    "PK": "Pakistan",
    "PL": "Poland",
    "PT": "Portugal",
    "RO": "Romania",
    "SA": "Saudi Arabia",
    "SE": "Sweden",
    "SG": "Singapore",
    "TH": "Thailand",
    "TR": "Turkey",
    "TW": "Taiwan",
    "UA": "Ukraine",
    "US": "United States",
    "VN": "Vietnam",
    "ZA": "South Africa",
}


def scrapingbee_api_key() -> str:
    """Return the ScrapingBee key, without a copied Bearer prefix."""
    raw = os.environ.get("SCRAPINGBEE_API_KEY", "").strip().strip('"').strip("'")
    if raw.lower().startswith("bearer "):
        raw = raw[7:].strip()
    return raw


_LANGUAGE_COUNTRY = {
    "portuguese(brazil)": "Brazil",
    "portuguese(portugal)": "Portugal",
}


def choose_known_country(name_countries: set[str], handle_countries: set[str], language: str) -> str:
    """Pick a country already known for this creator, when every source agrees."""
    name_country = next(iter(name_countries)) if len(name_countries) == 1 else ""
    handle_country = next(iter(handle_countries)) if len(handle_countries) == 1 else ""
    if name_country and handle_country and name_country != handle_country:
        return ""
    if name_country or handle_country:
        return name_country or handle_country
    folded = " ".join((language or "").split()).casefold()
    return _LANGUAGE_COUNTRY.get(folded, "")


def official_country(value: str) -> str:
    """Return an official country name, or a blank when the text is not one."""
    name = canonical_country_name(value)
    if name in CANONICAL_SET:
        return name
    return ""


def country_from_code(code: str) -> str:
    """Return the official country for an ISO code, or blank when it is unknown."""
    return official_country(_ISO2.get((code or "").strip().upper(), ""))


def _unescape(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return value


def _about_window(html: str) -> str:
    for marker in ("aboutChannelViewModel", "channelAboutFullMetadataRenderer"):
        start = html.find(marker)
        if start >= 0:
            return html[start : start + 5000]
    return ""


def country_name_from_page(html: str) -> str:
    """Return the official country named in structured profile data."""
    if not html:
        return ""
    for match in _YOUTUBE_SIMPLE_TEXT.finditer(html):
        country = official_country(_unescape(match.group("name")))
        if country:
            return country
    about = _YOUTUBE_ABOUT.search(html)
    if about:
        country = official_country(_unescape(about.group("name")))
        if country:
            return country
    window = _about_window(html)
    for code in re.findall(r'"country"\s*:\s*"([A-Z]{2})"', window):
        country = official_country(_ISO2.get(code, ""))
        if country:
            return country
    return ""


_YOUTUBE_TABS = {"about", "community", "featured", "playlists", "posts", "shorts", "streams", "videos"}


def profile_url_to_fetch(url: str) -> str:
    """Use a channel About page for YouTube. Leave other profile links unchanged."""
    cleaned = (url or "").split("?")[0].split("#")[0].strip().rstrip("/")
    lowered = cleaned.lower()
    if "youtube.com" not in lowered and "youtu.be" not in lowered:
        return cleaned
    parts = cleaned.split("/")
    if parts and parts[-1].lower() in _YOUTUBE_TABS:
        parts.pop()
        cleaned = "/".join(parts)
    return f"{cleaned}/about"


def fetch_profile_page(url: str, *, timeout: int = 70, premium: bool = False, render_js: bool = False) -> str:
    """Download one public page through ScrapingBee. The key stays in the request."""
    key = scrapingbee_api_key()
    if not key:
        raise RuntimeError("SCRAPINGBEE_API_KEY is required.")
    params = {
        "api_key": key,
        "url": url,
        "render_js": "true" if render_js else "false",
    }
    if premium:
        params["premium_proxy"] = "true"
        params["country_code"] = "us"
    query = urlencode(params)
    request = Request(
        f"https://app.scrapingbee.com/api/v1/?{query}",
        headers={"Accept": "text/html"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", "replace")
    except TimeoutError as exc:
        raise RuntimeError("ScrapingBee request timed out") from exc
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:180].strip()
        if detail.startswith("<"):
            detail = "page not found"
        raise RuntimeError(f"ScrapingBee returned {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"ScrapingBee request failed: {exc.reason}") from exc
    except (OSError, HTTPException) as exc:
        raise RuntimeError(f"ScrapingBee request failed: {exc}") from exc
