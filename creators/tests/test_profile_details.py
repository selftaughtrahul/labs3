from decimal import Decimal
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from creators.management.commands.refresh_creator_details import save_blank_fields
from creators.models import Creator
from creators.profile_details import (
    StoredProfile,
    blank_field_updates,
    details_from_page,
    youtube_videos_url,
)

INSTAGRAM_PAGE = """
"biography":"Bookings hello@brand.co"
"category_name":"Skincare"
"external_url":"https:\\/\\/linktr.ee\\/brand"
"edge_followed_by":{"count":5000}
"edge_liked_by":{"count":100},"edge_media_to_comment":{"count":5}
"edge_liked_by":{"count":200},"edge_media_to_comment":{"count":10}
"edge_liked_by":{"count":300},"edge_media_to_comment":{"count":15}
"video_view_count":4000
"video_view_count":5000
"video_view_count":6000
Female 60%
Male 40%
"""

TIKTOK_PAGE = """
"signature":"Email hello@studio.co or +44 7700 900123"
"region":"DE"
"language":"de"
"followerCount":1500
{"diggCount":10,"commentCount":2,"playCount":1000}
{"diggCount":20,"commentCount":3,"playCount":2000}
{"diggCount":30,"commentCount":4,"playCount":3000}
"""

YOUTUBE_PAGE = """
"subscriberCountText":{"simpleText":"1.5M subscribers"}
"country":{"simpleText":"France"}
"description":{"simpleText":"Contact jane@channel.fr"}
"contentLanguage":"fr"
"viewCountText":{"simpleText":"10,000 views"}
"viewCountText":{"simpleText":"20,000 views"}
"viewCountText":{"simpleText":"30,000 views"}
"category":"Entertainment"
"""


def _empty_stored(**overrides) -> StoredProfile:
    values = dict(
        niche=(),
        country="",
        language="",
        followers=None,
        email="",
        engagement_rate=None,
        avg_views=None,
        other_contact="",
        geo="",
        female_pct=None,
        male_pct=None,
        audience_insights="",
    )
    values.update(overrides)
    return StoredProfile(**values)


class ProfileDetailParserTests(SimpleTestCase):
    def test_instagram_page_keeps_exact_counts_and_contact(self):
        facts = details_from_page(INSTAGRAM_PAGE)

        self.assertEqual(facts.followers, 5000)
        self.assertEqual(facts.email, "hello@brand.co")
        self.assertEqual(facts.niche, ("Skincare",))
        self.assertEqual(facts.other_contact, "https://linktr.ee/brand")
        self.assertEqual(facts.engagement_rate, Decimal("4.20"))
        self.assertEqual(facts.avg_views, 5000)
        self.assertEqual(facts.female_pct, Decimal("60.00"))
        self.assertEqual(facts.male_pct, Decimal("40.00"))
        self.assertIn("Female 60.00%", facts.audience_insights)
        self.assertIn("median views 5000", facts.audience_insights)

    def test_tiktok_page_reads_country_language_and_post_stats(self):
        facts = details_from_page(TIKTOK_PAGE)

        self.assertEqual(facts.followers, 1500)
        self.assertEqual(facts.email, "hello@studio.co")
        self.assertEqual(facts.other_contact, "+44 7700 900123")
        self.assertEqual(facts.country, "Germany")
        self.assertEqual(facts.language, "German")
        self.assertEqual(facts.engagement_rate, Decimal("1.53"))
        self.assertEqual(facts.avg_views, 2000)

    def test_youtube_page_reads_subscribers_country_and_views(self):
        facts = details_from_page(YOUTUBE_PAGE)

        self.assertEqual(facts.followers, 1_500_000)
        self.assertEqual(facts.country, "France")
        self.assertEqual(facts.language, "French")
        self.assertEqual(facts.email, "jane@channel.fr")
        self.assertEqual(facts.avg_views, 20000)
        self.assertEqual(facts.niche, ())
        self.assertIsNone(facts.engagement_rate)

    def test_a_page_language_tag_is_not_the_creators_language(self):
        facts = details_from_page('<html lang="en"></html>')

        self.assertEqual(facts.language, "")
        self.assertFalse(facts.useful())

    def test_gender_percents_over_100_are_dropped(self):
        facts = details_from_page("Female 40% Male 70%")

        self.assertIsNone(facts.female_pct)
        self.assertIsNone(facts.male_pct)
        self.assertEqual(facts.audience_insights, "")

    def test_two_view_counts_do_not_become_an_average(self):
        facts = details_from_page('"playCount":100 "playCount":200')

        self.assertIsNone(facts.avg_views)

    def test_filled_fields_are_not_replaced(self):
        found = details_from_page(INSTAGRAM_PAGE)
        updates = blank_field_updates(
            _empty_stored(followers=999, email="kept@brand.co", niche=("Beauty",)),
            found,
        )

        self.assertNotIn("followers", updates)
        self.assertNotIn("email", updates)
        self.assertNotIn("niche", updates)
        self.assertEqual(updates["avg_views"], 5000)

    def test_youtube_videos_url_replaces_about(self):
        self.assertEqual(
            youtube_videos_url("https://youtube.com/@name/about"),
            "https://youtube.com/@name/videos",
        )
        self.assertEqual(
            youtube_videos_url("https://www.youtube.com/@name/videos/about"),
            "https://www.youtube.com/@name/videos",
        )


class RefreshCreatorDetailsTests(TestCase):
    def test_blank_email_is_saved_and_existing_followers_stay(self):
        creator = Creator.objects.create(
            platform="instagram",
            profile_link="https://instagram.com/examplecreator",
            influencer_name="Example",
            followers=999,
        )

        with patch(
            "creators.management.commands.refresh_creator_details.scrapingbee_api_key",
            return_value="test-key",
        ), patch(
            "creators.management.commands.refresh_creator_details.fetch_profile_page",
            return_value=INSTAGRAM_PAGE,
        ) as fetch:
            call_command("refresh_creator_details", "--workers", "1")

        creator.refresh_from_db()
        self.assertEqual(creator.followers, 999)
        self.assertEqual(creator.email, "hello@brand.co")
        self.assertEqual(creator.niche, ["Skincare"])
        self.assertEqual(creator.avg_views, 5000)
        self.assertEqual(fetch.call_count, 1)

    def test_dry_run_writes_nothing(self):
        creator = Creator.objects.create(
            platform="instagram",
            profile_link="https://instagram.com/examplecreator",
            influencer_name="Example",
        )

        with patch(
            "creators.management.commands.refresh_creator_details.scrapingbee_api_key",
            return_value="test-key",
        ), patch(
            "creators.management.commands.refresh_creator_details.fetch_profile_page",
            return_value=INSTAGRAM_PAGE,
        ):
            call_command("refresh_creator_details", "--workers", "1", "--dry-run")

        creator.refresh_from_db()
        self.assertIsNone(creator.followers)
        self.assertEqual(creator.email, "")

    def test_a_value_filled_after_the_read_is_kept(self):
        creator = Creator.objects.create(
            platform="instagram",
            profile_link="https://instagram.com/examplecreator",
            influencer_name="Example",
            followers=999,
        )

        saved = save_blank_fields(creator.pk, {"followers": 1, "email": "new@brand.co"})

        creator.refresh_from_db()
        self.assertEqual(saved, ["email"])
        self.assertEqual(creator.followers, 999)
        self.assertEqual(creator.email, "new@brand.co")
