"""Shared name cleanup for country, language, and deliverable masters."""

from creators.countries import canonical_country_name, resolved_country_names


def folded(value):
    return " ".join(str(value or "").split())


def _is_country(model):
    meta = getattr(model, "_meta", None)
    return getattr(meta, "model_name", "") == "country"


def _is_deliverable(model):
    meta = getattr(model, "_meta", None)
    return getattr(meta, "model_name", "") == "deliverabletype"


# Preferred display name first, then every spelling that should resolve to it.
DELIVERABLE_GROUPS = {
    "Instagram Reel": (
        "IG Reel",
        "Reel",
        "4 Reel",
        "2 IG Reel",
        "2 repost reel",
    ),
    "Instagram Story": (
        "IG Story",
        "Story",
        "2 Stories",
        "1 story(3-5) frames",
    ),
    "Instagram Post": ("IG Post",),
    "Instagram Carousel": ("IG Carousel",),
    "Instagram Highlights": ("IG Highlights",),
    "Instagram Reel + Story Bundle": ("IG Reel + Story Bundle",),
    "TikTok Video": (
        "TT Video",
        "TT",
        "Tiktok Reel",
        "2 Tiktok",
    ),
    "TikTok Story": ("TikTok Story",),
    "TikTok Carousel": ("Tiktok Carousel",),
    "YouTube Video": ("YT Video", "Video"),
    "YouTube Integration": (
        "YT Integration",
        "2 YT Integration",
        "2 integrations",
        "3 Integration videos",
    ),
    "YouTube Dedicated Video": ("YT Dedicated Video",),
    "YouTube Shorts": ("YT Shorts", "2 short"),
    "YouTube Post": ("YT Post",),
    "YouTube Vlog": ("YT Vlog",),
    "YouTube Ads": ("YT Ads",),
    "YouTube Pre-Roll": ("YT Pre-Roll",),
    "YouTube Live": ("YT Live",),
    "Facebook Post": ("FB Post",),
    "Facebook Reel": ("FB Reel",),
    "Telegram Post": ("5 telegram", "10 posts on telegram"),
    "X Post": ("5 X",),
    "Twitch Stream": ("Live stream",),
    "Newsletter Feature": ("Newsletter feature",),
    "Re-sharing on TikTok": ("Re Sharing on Tiktok", "Titok ReShare"),
}


def deliverable_group(name):
    """Return (canonical, spellings) for a sheet or master name."""
    text = folded(name)[:120]
    if not text:
        return "", ()
    key = fold_key(text)
    for canonical, aliases in DELIVERABLE_GROUPS.items():
        spellings = (canonical,) + tuple(aliases)
        if any(key == fold_key(item) for item in spellings):
            return canonical, spellings
    return text, (text,)


def display_name(model, name):
    text = folded(name)[:120]
    if not text:
        return ""
    if _is_country(model):
        names = resolved_country_names(text)
        if not names:
            return ""
        return names[0][:120]
    if _is_deliverable(model):
        canonical, _spellings = deliverable_group(text)
        return canonical[:120]
    return text


def fold_key(value):
    return folded(value).casefold()


def choose_label(spellings):
    """Keep the spelling that appears most often. Ties keep the first one."""
    counts = {}
    order = []
    for spelling in spellings:
        if spelling not in counts:
            order.append(spelling)
            counts[spelling] = 0
        counts[spelling] += 1
    best = order[0]
    for spelling in order[1:]:
        if counts[spelling] > counts[best]:
            best = spelling
    return best


def group_names(values):
    """Map a case-folded key to one display name. Blanks are left out."""
    groups = {}
    for value in values:
        text = folded(value)
        if not text:
            continue
        groups.setdefault(fold_key(text), []).append(text)
    return {key: choose_label(spellings) for key, spellings in groups.items()}


def lookup_named(model, name):
    """Return the master row for this name, creating it when the list has no match."""
    text = display_name(model, name)
    if not text:
        return None
    if _is_deliverable(model):
        canonical, spellings = deliverable_group(name)
        aliases = [item for item in spellings if fold_key(item) != fold_key(canonical)]
        for spelling in [canonical] + aliases:
            existing = model.objects.filter(name__iexact=spelling).first()
            if existing:
                return existing
        return model.objects.create(name=text)
    existing = model.objects.filter(name__iexact=text).first()
    if existing:
        return existing
    if _is_country(model):
        wanted = fold_key(text)
        for obj in model.objects.all():
            if fold_key(canonical_country_name(obj.name)) == wanted:
                return obj
    return model.objects.create(name=text)


LANGUAGE_MERGES = (
    ("English, Chinese", "Chinese, English"),
    ("English, German", "German, English"),
    ("Indian", "Hindi"),
    ("Chilean", "Spanish"),
    ("Finnic", "Finnish"),
    ("Taiwanese", "Chinese"),
    ("Slovene", "Slovenian"),
)

# English names for ISO 639-1 codes. Existing rows with another spelling are kept.
ISO_639_1_LANGUAGES = (
    "Abkhazian",
    "Afar",
    "Afrikaans",
    "Akan",
    "Albanian",
    "Amharic",
    "Arabic",
    "Aragonese",
    "Armenian",
    "Assamese",
    "Avaric",
    "Avestan",
    "Aymara",
    "Azerbaijani",
    "Bambara",
    "Bashkir",
    "Basque",
    "Belarusian",
    "Bengali",
    "Bihari",
    "Bislama",
    "Bosnian",
    "Breton",
    "Bulgarian",
    "Burmese",
    "Catalan",
    "Chamorro",
    "Chechen",
    "Chichewa",
    "Chinese",
    "Church Slavic",
    "Chuvash",
    "Cornish",
    "Corsican",
    "Cree",
    "Croatian",
    "Czech",
    "Danish",
    "Divehi",
    "Dutch",
    "Dzongkha",
    "English",
    "Esperanto",
    "Estonian",
    "Ewe",
    "Faroese",
    "Fijian",
    "Finnish",
    "French",
    "Fulah",
    "Gaelic",
    "Galician",
    "Ganda",
    "Georgian",
    "German",
    "Greek",
    "Guarani",
    "Gujarati",
    "Haitian",
    "Hausa",
    "Hebrew",
    "Herero",
    "Hindi",
    "Hiri Motu",
    "Hungarian",
    "Icelandic",
    "Ido",
    "Igbo",
    "Indonesian",
    "Interlingua",
    "Interlingue",
    "Inuktitut",
    "Inupiaq",
    "Irish",
    "Italian",
    "Japanese",
    "Javanese",
    "Kalaallisut",
    "Kannada",
    "Kanuri",
    "Kashmiri",
    "Kazakh",
    "Khmer",
    "Kikuyu",
    "Kinyarwanda",
    "Kirghiz",
    "Komi",
    "Kongo",
    "Korean",
    "Kuanyama",
    "Kurdish",
    "Lao",
    "Latin",
    "Latvian",
    "Limburgan",
    "Lingala",
    "Lithuanian",
    "Luba-Katanga",
    "Luxembourgish",
    "Macedonian",
    "Malagasy",
    "Malay",
    "Malayalam",
    "Maltese",
    "Manx",
    "Maori",
    "Marathi",
    "Marshallese",
    "Mongolian",
    "Nauru",
    "Navajo",
    "Ndonga",
    "Nepali",
    "North Ndebele",
    "Northern Sami",
    "Norwegian",
    "Norwegian Bokmal",
    "Norwegian Nynorsk",
    "Occitan",
    "Ojibwa",
    "Oriya",
    "Oromo",
    "Ossetian",
    "Pali",
    "Pashto",
    "Persian",
    "Polish",
    "Portuguese",
    "Punjabi",
    "Quechua",
    "Romanian",
    "Romansh",
    "Rundi",
    "Russian",
    "Samoan",
    "Sango",
    "Sanskrit",
    "Sardinian",
    "Serbian",
    "Shona",
    "Sichuan Yi",
    "Sindhi",
    "Sinhala",
    "Slovak",
    "Slovenian",
    "Somali",
    "South Ndebele",
    "Southern Sotho",
    "Spanish",
    "Sundanese",
    "Swahili",
    "Swati",
    "Swedish",
    "Tagalog",
    "Tahitian",
    "Tajik",
    "Tamil",
    "Tatar",
    "Telugu",
    "Thai",
    "Tibetan",
    "Tigrinya",
    "Tonga",
    "Tsonga",
    "Tswana",
    "Turkish",
    "Turkmen",
    "Twi",
    "Uighur",
    "Ukrainian",
    "Urdu",
    "Uzbek",
    "Venda",
    "Vietnamese",
    "Volapuk",
    "Walloon",
    "Welsh",
    "Western Frisian",
    "Wolof",
    "Xhosa",
    "Yiddish",
    "Yoruba",
    "Zhuang",
    "Zulu",
)


def merge_language_names(language_model, creator_model, source_name, target_name):
    """Move creators off source_name onto target_name, then drop the duplicate."""
    source = language_model.objects.filter(name__iexact=source_name).first()
    if source is None:
        return
    target = language_model.objects.filter(name__iexact=target_name).first()
    if target is None:
        source.name = target_name
        source.save(update_fields=["name"])
        return
    if source.pk == target.pk:
        return
    creator_model.objects.filter(language_id=source.pk).update(language_id=target.pk)
    source.delete()


def drop_unused_language(language_model, creator_model, name):
    row = language_model.objects.filter(name__iexact=name).first()
    if row is None:
        return
    if creator_model.objects.filter(language_id=row.pk).exists():
        return
    row.delete()


def insert_missing_iso_languages(language_model):
    existing = {fold_key(name) for name in language_model.objects.values_list("name", flat=True)}
    missing = [
        language_model(name=name)
        for name in ISO_639_1_LANGUAGES
        if fold_key(name) not in existing
    ]
    if missing:
        language_model.objects.bulk_create(missing, batch_size=400)
    return len(missing)


class MasterCache:
    """Load a named master once, then resolve sheet values without extra queries."""

    def __init__(self, model):
        self.model = model
        self.by_key = {}
        self._load()

    def _load(self):
        self.by_key = {}
        country = _is_country(self.model)
        deliverable = _is_deliverable(self.model)
        for obj in self.model.objects.all():
            key = fold_key(canonical_country_name(obj.name) if country else obj.name)
            current = self.by_key.get(key)
            if current is None or (country and fold_key(obj.name) == key):
                self.by_key[key] = obj
            if deliverable:
                canonical, spellings = deliverable_group(obj.name)
                preferred = fold_key(obj.name) == fold_key(canonical)
                for spelling in spellings:
                    spelling_key = fold_key(spelling)
                    if spelling_key not in self.by_key or preferred:
                        self.by_key[spelling_key] = obj

    def get(self, name):
        text = display_name(self.model, name)
        if not text:
            return None
        return self.by_key.get(fold_key(text)) or self.by_key.get(fold_key(folded(name)))

    def ensure(self, names):
        missing = []
        seen = set()
        for name in names:
            text = display_name(self.model, name)
            if not text:
                continue
            key = fold_key(text)
            raw_key = fold_key(folded(name))
            if key in self.by_key or raw_key in self.by_key or key in seen:
                continue
            seen.add(key)
            missing.append(self.model(name=text))
        if missing:
            self.model.objects.bulk_create(missing, batch_size=400)
            self._load()
        return self

