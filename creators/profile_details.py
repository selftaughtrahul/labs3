"""Read creator facts that a public profile page actually states.

Audience gender, geo, and a written insight are saved only when the page
states them, or when recent posts on that same page include view and like
counts. Nothing here invents a number the page did not contain.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from creators.lists import clean_string_list
from creators.page_country import country_from_code, country_name_from_page

MAX_INT = 2_147_483_647
_GENERIC_NICHE = {
    "blog",
    "creator",
    "entertainment",
    "none",
    "null",
    "other",
    "people & blogs",
    "people and blogs",
    "undefined",
    "video",
    "videos",
}
_BLOCKED_EMAIL_HOSTS = {
    "example.com",
    "example.org",
    "schema.org",
    "scrapingbee.com",
    "sentry.io",
    "wixpress.com",
}
_SOCIAL_HOSTS = {
    "facebook.com",
    "instagram.com",
    "tiktok.com",
    "twitter.com",
    "x.com",
    "youtu.be",
    "youtube.com",
}
_LANGUAGE_CODES = {
    "ar": "Arabic",
    "bn": "Bengali",
    "cs": "Czech",
    "da": "Danish",
    "de": "German",
    "el": "Greek",
    "en": "English",
    "es": "Spanish",
    "fa": "Persian",
    "fi": "Finnish",
    "fil": "Tagalog",
    "fr": "French",
    "he": "Hebrew",
    "hi": "Hindi",
    "hu": "Hungarian",
    "id": "Indonesian",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "ms": "Malay",
    "nb": "Norwegian Bokmal",
    "nl": "Dutch",
    "no": "Norwegian",
    "pl": "Polish",
    "pt": "Portuguese",
    "pt-br": "Portuguese",
    "ro": "Romanian",
    "ru": "Russian",
    "sv": "Swedish",
    "sw": "Swahili",
    "ta": "Tamil",
    "te": "Telugu",
    "th": "Thai",
    "tl": "Tagalog",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "ur": "Urdu",
    "vi": "Vietnamese",
    "zh": "Chinese",
    "zh-cn": "Chinese",
    "zh-tw": "Chinese",
}
_SUFFIX = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}
_EMAIL = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
_PHONE = re.compile(r"\+\d[\d\s\-()]{8,}\d")
_FLAT_OBJECT = re.compile(r"\{[^{}]{0,600}\}")
_JSON_STRING = r'"(?P<value>(?:\\.|[^"\\])*)"'
_FOLLOWER_COUNTS = (
    re.compile(r'"edge_followed_by"\s*:\s*\{\s*"count"\s*:\s*(\d+)'),
    re.compile(r'"(?:followerCount|follower_count)"\s*:\s*"?(\d+)"?'),
    re.compile(r'"subscriberCount"\s*:\s*"?(\d+)"?'),
)
_SUBSCRIBER_LABEL = re.compile(
    r'"subscriberCountText".{0,400}?(\d[\d,.]*(?:\.\d+)?\s*[KMB]?)\s+subscribers',
    re.I | re.DOTALL,
)
_OG_FOLLOWERS = re.compile(
    r"([\d][\d,.]*(?:\.\d+)?\s*[KMB]?)\s+Followers\b",
    re.I,
)
_ABOUT_DESCRIPTION = re.compile(
    r'"description"\s*:\s*\{\s*"simpleText"\s*:\s*"(?P<value>(?:\\.|[^"\\])*)"'
)
_EXTERNAL_URL = re.compile(
    r'"(?:external_url|externalUrl)"\s*:\s*"(?P<value>(?:\\.|[^"\\])*)"'
)
_BIO_LINK = re.compile(
    r'"bioLink"\s*:\s*\{[^{}]{0,400}?"link"\s*:\s*"(?P<value>(?:\\.|[^"\\])*)"'
)
_CONTENT_LANGUAGE = re.compile(r'"contentLanguage"\s*:\s*"([A-Za-z]{2,8}(?:-[A-Za-z]{2})?)"')
_REGION = re.compile(r'"region"\s*:\s*"([A-Z]{2})"')
_WINDOW_LANGUAGE = re.compile(r'"language"\s*:\s*"([A-Za-z]{2,8}(?:-[A-Za-z]{2})?)"')
_LIKED = re.compile(r'"edge_liked_by"\s*:\s*\{\s*"count"\s*:\s*(\d+)')
_COMMENTED = re.compile(r'"edge_media_to_comment"\s*:\s*\{\s*"count"\s*:\s*(\d+)')
_LIKE_COUNT = re.compile(r'"like_count"\s*:\s*(\d+)')
_PLAY_COUNT = re.compile(r'"playCount"\s*:\s*(\d+)')
_VIDEO_VIEW_COUNT = re.compile(r'"video_view_count"\s*:\s*(\d+)')
_VIEW_LABEL = re.compile(r"(\d[\d,.]*(?:\.\d+)?\s*[KMB]?)\s+views\b", re.I)
_FEMALE = re.compile(r"\b(?:female|women)\b\s*[:\-]?\s*(\d{1,3}(?:\.\d+)?)\s*%", re.I)
_MALE = re.compile(r"\b(?:male|men)\b\s*[:\-]?\s*(\d{1,3}(?:\.\d+)?)\s*%", re.I)
_GEO_LABEL = re.compile(
    r"\b(?:audience geo|audience location|top countries)\b\s*[:\-]\s*(?P<value>[^<\n\"]{3,120})",
    re.I,
)
_GEO_JSON = re.compile(r'"(?:audience_geo|audienceGeo)"\s*:\s*"(?P<value>(?:\\.|[^"\\])*)"')


@dataclass(frozen=True)
class ProfileFacts:
    """Facts taken from one public page. Blank means the page did not say."""

    niche: tuple[str, ...] = ()
    country: str = ""
    language: str = ""
    followers: int | None = None
    email: str = ""
    engagement_rate: Decimal | None = None
    avg_views: int | None = None
    other_contact: str = ""
    geo: str = ""
    female_pct: Decimal | None = None
    male_pct: Decimal | None = None
    audience_insights: str = ""

    def useful(self) -> bool:
        """True when the page gave a fact worth keeping or retrying over."""
        return any(
            (
                self.niche,
                self.country,
                self.language,
                self.followers,
                self.email,
                self.engagement_rate is not None,
                self.avg_views,
                self.other_contact,
            )
        )


@dataclass(frozen=True)
class StoredProfile:
    """Values already on the creator row. Blank fields are the only ones updated."""

    niche: tuple[str, ...]
    country: str
    language: str
    followers: int | None
    email: str
    engagement_rate: Decimal | None
    avg_views: int | None
    other_contact: str
    geo: str
    female_pct: Decimal | None
    male_pct: Decimal | None
    audience_insights: str


def details_from_page(html: str) -> ProfileFacts:
    """Pull creator facts out of one downloaded profile page."""
    page = html or ""
    bios = _bio_texts(page)
    emails = _emails(page, bios)
    followers = _followers(page)
    interactions = _interactions(page)
    views = _view_counts(page)
    female, male = _genders(page)
    country = country_name_from_page(page) or _region_country(page)
    engagement = _engagement(interactions, followers)
    avg_views = _median_int(views) if len(views) >= 3 else None
    geo = _geo(page)
    insights = _insights(
        geo=geo,
        female=female,
        male=male,
        avg_views=avg_views,
        engagement=engagement,
    )
    return ProfileFacts(
        niche=_niches(page),
        country=country,
        language=_language(page),
        followers=followers,
        email=emails[0] if emails else "",
        engagement_rate=engagement,
        avg_views=avg_views,
        other_contact=_other_contact(page, bios, emails[1:]),
        geo=geo,
        female_pct=female,
        male_pct=male,
        audience_insights=insights,
    )


def merge_facts(primary: ProfileFacts, extra: ProfileFacts) -> ProfileFacts:
    """Keep facts from the first page and fill only the gaps from the second."""
    female = primary.female_pct if primary.female_pct is not None else extra.female_pct
    male = primary.male_pct if primary.male_pct is not None else extra.male_pct
    engagement = primary.engagement_rate if primary.engagement_rate is not None else extra.engagement_rate
    avg_views = primary.avg_views or extra.avg_views
    geo = primary.geo or extra.geo
    insights = primary.audience_insights or _insights(
        geo=geo,
        female=female,
        male=male,
        avg_views=avg_views,
        engagement=engagement,
    )
    return ProfileFacts(
        niche=primary.niche or extra.niche,
        country=primary.country or extra.country,
        language=primary.language or extra.language,
        followers=primary.followers or extra.followers,
        email=primary.email or extra.email,
        engagement_rate=engagement,
        avg_views=avg_views,
        other_contact=primary.other_contact or extra.other_contact,
        geo=geo,
        female_pct=female,
        male_pct=male,
        audience_insights=primary.audience_insights or insights,
    )


def blank_field_updates(stored: StoredProfile, found: ProfileFacts) -> dict[str, object]:
    """Return model fields that are still blank and now have a page value."""
    updates: dict[str, object] = {}
    if not stored.niche and found.niche:
        updates["niche"] = list(found.niche)
    if not stored.country and found.country:
        updates["country"] = found.country
    if not stored.language and found.language:
        updates["language"] = found.language
    if stored.followers is None and found.followers:
        updates["followers"] = found.followers
    if not stored.email and found.email:
        updates["email"] = found.email
    if stored.engagement_rate is None and found.engagement_rate is not None:
        updates["engagement_rate"] = found.engagement_rate
    if stored.avg_views is None and found.avg_views:
        updates["avg_views"] = found.avg_views
    if not stored.other_contact and found.other_contact:
        updates["other_contact"] = found.other_contact
    if not stored.geo and found.geo:
        updates["geo"] = found.geo
    if stored.female_pct is None and found.female_pct is not None:
        updates["female_pct"] = found.female_pct
    if stored.male_pct is None and found.male_pct is not None:
        updates["male_pct"] = found.male_pct
    if not stored.audience_insights and found.audience_insights:
        updates["audience_insights"] = found.audience_insights
    return updates


def youtube_videos_url(page_url: str) -> str:
    """Return the videos tab for a YouTube channel, without a second tab in the path."""
    cleaned = (page_url or "").split("?")[0].split("#")[0].strip().rstrip("/")
    parts = cleaned.split("/")
    while parts and parts[-1].lower() in {"about", "community", "featured", "playlists", "posts", "shorts", "streams", "videos"}:
        parts.pop()
    return "/".join(parts) + "/videos"


def language_name_from_code(code: str) -> str:
    """Return the English language name for a profile language code."""
    token = (code or "").strip().replace("_", "-").lower()
    if token in _LANGUAGE_CODES:
        return _LANGUAGE_CODES[token]
    return _LANGUAGE_CODES.get(token.split("-", 1)[0], "")


def _followers(html: str) -> int | None:
    for pattern in _FOLLOWER_COUNTS:
        match = pattern.search(html)
        if match:
            value = _whole_number(match.group(1))
            if value:
                return value
    for pattern in (_SUBSCRIBER_LABEL, _OG_FOLLOWERS):
        match = pattern.search(html)
        if match:
            value = parse_count(match.group(1))
            if value:
                return value
    return None


def parse_count(raw: str) -> int | None:
    """Read 12500 from '12,500' or '12.5K'. Zero and overflow become blank."""
    text = (raw or "").strip().lower().replace(",", "").replace(" ", "")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([kmb])?", text)
    if not match:
        return None
    number = float(match.group(1))
    suffix = match.group(2)
    if suffix:
        number *= _SUFFIX[suffix]
    return _whole_number(number)


def _whole_number(raw: object) -> int | None:
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        return None
    if value <= 0 or value > MAX_INT:
        return None
    return value


def _percent(raw: str) -> Decimal | None:
    try:
        number = Decimal(raw)
    except InvalidOperation:
        return None
    if number < 0 or number > 100:
        return None
    return number.quantize(Decimal("0.01"))


def _unescape(value: str) -> str:
    try:
        text = json.loads(f'"{value}"')
    except json.JSONDecodeError:
        text = value
    if not isinstance(text, str):
        return ""
    return text.strip()


def _json_strings(html: str, key: str) -> list[str]:
    pattern = re.compile(rf'"{re.escape(key)}"\s*:\s*{_JSON_STRING}')
    found = []
    for match in pattern.finditer(html):
        text = " ".join(_unescape(match.group("value")).split())
        if text and text not in found:
            found.append(text[:2000])
        if len(found) == 4:
            break
    return found


def _bio_texts(html: str) -> list[str]:
    texts = _json_strings(html, "biography") + _json_strings(html, "signature")
    for match in _ABOUT_DESCRIPTION.finditer(html):
        text = " ".join(_unescape(match.group("value")).split())
        if text and text not in texts:
            texts.append(text[:2000])
        if len(texts) == 4:
            break
    return texts


def _emails(html: str, bios: list[str]) -> list[str]:
    found: list[str] = []
    for key in ("business_email", "public_email", "businessEmail"):
        for value in _json_strings(html, key):
            _add_email(found, value)
    for bio in bios:
        for match in _EMAIL.findall(bio):
            _add_email(found, match)
    return found


def _add_email(found: list[str], raw: str) -> None:
    email = raw.strip().strip(".").lower()
    if not _EMAIL.fullmatch(email):
        return
    host = email.split("@", 1)[1]
    if host in _BLOCKED_EMAIL_HOSTS or host.endswith(".example.com"):
        return
    if any(part in {"noreply", "no-reply", "sentry"} for part in email.split("@")[0].split(".")):
        return
    if email not in found:
        found.append(email)


def _other_contact(html: str, bios: list[str], extra_emails: list[str]) -> str:
    parts: list[str] = []
    for email in extra_emails:
        if email not in parts:
            parts.append(email)
    for pattern in (_EXTERNAL_URL, _BIO_LINK):
        for match in pattern.finditer(html):
            link = _contact_link(_unescape(match.group("value")))
            if link and link not in parts:
                parts.append(link)
    for bio in bios:
        phone = _phone(bio)
        if phone and phone not in parts:
            parts.append(phone)
    kept: list[str] = []
    for part in parts:
        candidate = " · ".join(kept + [part])
        if len(candidate) > 250:
            break
        kept.append(part)
    return " · ".join(kept)


def _contact_link(raw: str) -> str:
    link = raw.strip().rstrip(").,;")
    if not link.lower().startswith("http") or " " in link or len(link) > 180:
        return ""
    host = link.split("//", 1)[-1].split("/", 1)[0].lower()
    if host.startswith("www."):
        host = host[4:]
    if host in _SOCIAL_HOSTS:
        return ""
    return link


def _phone(text: str) -> str:
    match = _PHONE.search(text)
    if not match:
        return ""
    digits = re.sub(r"\D", "", match.group(0))
    if 10 <= len(digits) <= 15:
        return " ".join(match.group(0).split())
    return ""


def _niches(html: str) -> tuple[str, ...]:
    raw: list[str] = []
    for key in ("category_name", "categoryName", "category"):
        raw.extend(_json_strings(html, key))
    names = clean_string_list(raw)
    kept: list[str] = []
    seen: set[str] = set()
    for name in names:
        label = name[:80]
        folded = label.casefold()
        if not label or folded in _GENERIC_NICHE or folded in seen or "http" in folded:
            continue
        seen.add(folded)
        kept.append(label)
        if len(kept) == 6:
            break
    return tuple(kept)


def _language(html: str) -> str:
    match = _CONTENT_LANGUAGE.search(html)
    if match:
        return language_name_from_code(match.group(1))
    window = _profile_window(html)
    if not window:
        return ""
    lang = _WINDOW_LANGUAGE.search(window)
    if not lang:
        return ""
    return language_name_from_code(lang.group(1))


def _region_country(html: str) -> str:
    window = _profile_window(html)
    if not window:
        return ""
    match = _REGION.search(window)
    if not match:
        return ""
    return country_from_code(match.group(1))


def _profile_window(html: str) -> str:
    for marker in ('"signature"', '"biography"', '"aboutChannelViewModel"'):
        start = html.find(marker)
        if start >= 0:
            return html[max(0, start - 200) : start + 1500]
    return ""


def _interactions(html: str) -> list[int]:
    tiktok = _tiktok_interactions(html)
    if len(tiktok) >= 3:
        return tiktok[:12]
    instagram = _instagram_interactions(html)
    if len(instagram) >= 3:
        return instagram[:12]
    return []


def _tiktok_interactions(html: str) -> list[int]:
    found = []
    for blob in _FLAT_OBJECT.findall(html):
        likes = re.search(r'"diggCount"\s*:\s*(\d+)', blob)
        if not likes:
            continue
        comments = re.search(r'"commentCount"\s*:\s*(\d+)', blob)
        found.append(int(likes.group(1)) + (int(comments.group(1)) if comments else 0))
        if len(found) == 12:
            break
    return found


def _instagram_interactions(html: str) -> list[int]:
    likes = _LIKED.findall(html) or _LIKE_COUNT.findall(html)
    comments = _COMMENTED.findall(html)
    totals = []
    for index, like in enumerate(likes[:12]):
        comment = int(comments[index]) if index < len(comments) else 0
        totals.append(int(like) + comment)
    return totals


def _view_counts(html: str) -> list[int]:
    found: list[int] = []
    for pattern in (_PLAY_COUNT, _VIDEO_VIEW_COUNT):
        for raw in pattern.findall(html):
            value = _whole_number(raw)
            if value:
                found.append(value)
            if len(found) == 12:
                return found
    if found:
        return found
    for match in _VIEW_LABEL.finditer(html):
        value = parse_count(match.group(1))
        if value:
            found.append(value)
        if len(found) == 12:
            break
    return found


def _engagement(interactions: list[int], followers: int | None) -> Decimal | None:
    """Median likes and comments on recent posts, as a percent of followers."""
    if followers is None or len(interactions) < 3:
        return None
    rate = (_median_decimal(interactions) / Decimal(followers)) * Decimal(100)
    rate = rate.quantize(Decimal("0.01"))
    if rate <= 0 or rate > 100:
        return None
    return rate


def _median_decimal(values: list[int]) -> Decimal:
    ordered = sorted(Decimal(value) for value in values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / Decimal(2)


def _median_int(values: list[int]) -> int | None:
    if not values:
        return None
    number = _median_decimal(values).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return _whole_number(number)


def _genders(html: str) -> tuple[Decimal | None, Decimal | None]:
    female_match = _FEMALE.search(html)
    male_match = _MALE.search(html)
    female = _percent(female_match.group(1)) if female_match else None
    male = _percent(male_match.group(1)) if male_match else None
    if female is not None and male is not None and female + male > Decimal("100"):
        return None, None
    return female, male


def _geo(html: str) -> str:
    match = _GEO_LABEL.search(html)
    if match:
        return _fit_geo(match.group("value"))
    for candidate in _GEO_JSON.finditer(html):
        text = _unescape(candidate.group("value"))
        if "%" in text:
            fitted = _fit_geo(text)
            if fitted:
                return fitted
    return ""


def _fit_geo(raw: str) -> str:
    text = " ".join((raw or "").split())[:120]
    if not any(character.isalpha() for character in text):
        return ""
    return text


def _insights(
    *,
    geo: str,
    female: Decimal | None,
    male: Decimal | None,
    avg_views: int | None,
    engagement: Decimal | None,
) -> str:
    bits = []
    if geo:
        bits.append(f"Geo {geo}")
    if female is not None:
        bits.append(f"Female {female}%")
    if male is not None:
        bits.append(f"Male {male}%")
    if avg_views is not None:
        bits.append(f"median views {avg_views}")
    if engagement is not None:
        bits.append(f"engagement {engagement}%")
    if not bits:
        return ""
    return ("Public profile: " + "; ".join(bits) + ".")[:2000]
