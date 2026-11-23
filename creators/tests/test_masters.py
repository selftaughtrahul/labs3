from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from accounts.models import User
from campaigns.models import Campaign
from creators.masters import (
    group_names,
    insert_missing_iso_languages,
    lookup_named,
    merge_language_names,
)
from creators.models import Country, Creator, DeliverableType, Language
from creators.choices import Platform


class MasterNameTests(TestCase):
    def test_case_folds_to_one_label(self):
        grouped = group_names(["india", "India", "India", "  Germany "])
        self.assertEqual(grouped["india"], "India")
        self.assertEqual(grouped["germany"], "Germany")

    def test_lookup_reuses_existing_spelling(self):
        Country.objects.create(name="India")
        again = lookup_named(Country, " india ")
        self.assertEqual(again.name, "India")
        self.assertEqual(Country.objects.count(), 1)

    def test_blank_name_stays_empty(self):
        self.assertIsNone(lookup_named(Language, "  "))

    def test_creator_keeps_a_blank_country(self):
        creator = Creator(
            platform=Platform.INSTAGRAM,
            profile_link="https://instagram.com/no-country",
            influencer_name="No Country",
            language=lookup_named(Language, "English"),
        )
        creator.full_clean()
        creator.save()
        creator.refresh_from_db()
        self.assertIsNone(creator.country_id)
        self.assertEqual(creator.language.name, "English")


class LanguageMergeTests(TestCase):
    def test_creators_move_before_duplicate_is_removed(self):
        hindi, _ = Language.objects.get_or_create(name="Hindi")
        indian = Language.objects.create(name="Indian")
        creator = Creator.objects.create(
            platform=Platform.INSTAGRAM,
            profile_link="https://instagram.com/indian-lang",
            influencer_name="Merged Language",
            language=indian,
        )

        merge_language_names(Language, Creator, "Indian", "Hindi")

        creator.refresh_from_db()
        self.assertEqual(creator.language_id, hindi.pk)
        self.assertFalse(Language.objects.filter(name="Indian").exists())
        self.assertEqual(Language.objects.filter(name="Hindi").count(), 1)

    def test_iso_insert_skips_existing_english(self):
        self.assertEqual(Language.objects.filter(name__iexact="English").count(), 1)
        added = insert_missing_iso_languages(Language)
        self.assertEqual(added, 0)
        self.assertEqual(Language.objects.filter(name__iexact="English").count(), 1)


class CampaignMarketTests(TestCase):
    def test_markets_are_countries(self):
        owner = User.objects.create_user(username="owner")
        germany = lookup_named(Country, "Germany")
        campaign = Campaign.objects.create(client_name="Market Brief", campaign_owner=owner)
        campaign.country_market.add(germany)
        campaign.full_clean()
        self.assertEqual(list(campaign.country_market.values_list("name", flat=True)), ["Germany"])
        self.assertTrue(DeliverableType.objects.filter(name="Instagram Reel").exists())


class CountryNormalizeTests(TestCase):
    def test_usa_reuses_united_states(self):
        united = Country.objects.create(name="United States")
        again = lookup_named(Country, "USA")
        self.assertEqual(again.pk, united.pk)
        self.assertEqual(again.name, "United States")
        self.assertEqual(Country.objects.filter(name__in=["USA", "United States"]).count(), 1)

    def test_links_move_onto_the_official_row(self):
        owner = User.objects.create_user(username="owner")
        united = Country.objects.create(name="United States")
        usa = Country.objects.create(name="USA")
        us = Country.objects.create(name="US")
        creator = Creator.objects.create(
            platform=Platform.INSTAGRAM,
            profile_link="https://instagram.com/usa-creator",
            influencer_name="US Creator",
            country=usa,
        )
        campaign = Campaign.objects.create(client_name="US Markets", campaign_owner=owner)
        campaign.country_market.add(us, united)

        call_command("normalize_countries", stdout=StringIO())

        creator.refresh_from_db()
        self.assertEqual(creator.country_id, united.pk)
        self.assertEqual(
            list(campaign.country_market.order_by("name").values_list("name", flat=True)),
            ["United States"],
        )
        self.assertFalse(Country.objects.filter(name__in=["USA", "US"]).exists())

    def test_leftover_region_is_removed(self):
        Country.objects.create(name="Europe")
        call_command("normalize_countries", stdout=StringIO())
        self.assertFalse(Country.objects.filter(name="Europe").exists())

    def test_dubai_moves_to_united_arab_emirates(self):
        uae = lookup_named(Country, "United Arab Emirates")
        dubai = Country.objects.create(name="Dubai")
        creator = Creator.objects.create(
            platform=Platform.YOUTUBE,
            profile_link="https://youtube.com/dubai-creator",
            influencer_name="Daniel",
            country=dubai,
        )
        call_command("normalize_countries", stdout=StringIO())
        creator.refresh_from_db()
        self.assertEqual(creator.country_id, uae.pk)
        self.assertFalse(Country.objects.filter(name="Dubai").exists())

    def test_german_speaking_becomes_dach_markets(self):
        owner = User.objects.create_user(username="reddit-owner")
        germany = lookup_named(Country, "Germany")
        junk = Country.objects.create(name="German speaking countries")
        campaign = Campaign.objects.create(
            client_name="Reddit Brief", campaign_owner=owner
        )
        campaign.country_market.add(germany, junk)
        call_command("normalize_countries", stdout=StringIO())
        self.assertEqual(
            list(campaign.country_market.order_by("name").values_list("name", flat=True)),
            ["Austria", "Germany", "Switzerland"],
        )
        self.assertFalse(Country.objects.filter(name="German speaking countries").exists())

    def test_note_label_is_dropped(self):
        owner = User.objects.create_user(username="tetr-owner")
        australia = lookup_named(Country, "Australia")
        note = Country.objects.create(name="Dec 2026 | Top Tier. Gap years are deeply ingraine")
        campaign = Campaign.objects.create(client_name="TETR Brief", campaign_owner=owner)
        campaign.country_market.add(australia, note)
        call_command("normalize_countries", stdout=StringIO())
        self.assertEqual(
            list(campaign.country_market.values_list("name", flat=True)),
            ["Australia"],
        )
        self.assertFalse(Country.objects.filter(pk=note.pk).exists())

    def test_missing_official_country_is_created(self):
        self.assertFalse(Country.objects.filter(name="Iceland").exists())
        call_command("normalize_countries", stdout=StringIO())
        self.assertTrue(Country.objects.filter(name="Iceland").exists())

    def test_uk_is_renamed(self):
        uk = Country.objects.create(name="UK")
        creator = Creator.objects.create(
            platform=Platform.YOUTUBE,
            profile_link="https://youtube.com/uk-creator",
            influencer_name="UK Creator",
            country=uk,
        )

        call_command("normalize_countries", stdout=StringIO())

        uk.refresh_from_db()
        creator.refresh_from_db()
        self.assertEqual(uk.name, "United Kingdom")
        self.assertEqual(creator.country_id, uk.pk)


class DeliverableAliasTests(TestCase):
    def test_sheet_spelling_reuses_the_canonical_row(self):
        keeper, _created = DeliverableType.objects.get_or_create(name="Instagram Reel")
        again = lookup_named(DeliverableType, "IG Reel")
        two = lookup_named(DeliverableType, "2 IG Reel")
        self.assertEqual(again.pk, keeper.pk)
        self.assertEqual(two.pk, keeper.pk)
        self.assertEqual(DeliverableType.objects.filter(name__iexact="instagram reel").count(), 1)

    def test_lookup_creates_the_canonical_name(self):
        created = lookup_named(DeliverableType, "ig story")
        self.assertEqual(created.name, "Instagram Story")
