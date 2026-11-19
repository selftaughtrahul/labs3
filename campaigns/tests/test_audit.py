from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from accounts.models import User
from campaigns.models import Campaign
from campaigns.platforms import normalize_platforms
from creators.choices import Platform
from creators.models import Creator


class NormalizePlatformsTests(TestCase):
    def test_known_slug_stays(self):
        slugs, unknown = normalize_platforms([Platform.INSTAGRAM, Platform.TIKTOK])
        self.assertEqual(slugs, ["instagram", "tiktok"])
        self.assertEqual(unknown, [])

    def test_short_names_and_combined_text(self):
        slugs, unknown = normalize_platforms(["IG", "IG / TT"])
        self.assertEqual(slugs, ["instagram", "tiktok"])
        self.assertEqual(unknown, [])

    def test_unknown_token_is_dropped(self):
        slugs, unknown = normalize_platforms(["instagram", "small screen agency"])
        self.assertEqual(slugs, ["instagram"])
        self.assertEqual(unknown, ["small screen agency"])

    def test_non_list_is_empty(self):
        self.assertEqual(normalize_platforms("instagram"), ([], []))


class AuditCommandTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner")
        Creator.objects.create(
            platform=Platform.INSTAGRAM,
            profile_link="https://instagram.com/blank",
            influencer_name="Blank Stats",
        )
        Campaign.objects.create(
            client_name="Broken Brief",
            campaign_owner=self.owner,
            platforms=["IG", "not-a-platform"],
        )

    def test_report_lists_gaps_and_does_not_write(self):
        campaign = Campaign.objects.get(client_name="Broken Brief")
        output = StringIO()
        call_command("audit_creator_data", stdout=output)
        text = output.getvalue()
        self.assertIn("Creators missing engagement rate: 1", text)
        self.assertIn("Creators missing average views: 1", text)
        self.assertIn("Campaigns missing minimum followers: 1", text)
        self.assertIn("Campaigns missing content type: 1", text)
        self.assertIn("Broken Brief", text)
        self.assertIn("not-a-platform", text)
        campaign.refresh_from_db()
        self.assertEqual(campaign.platforms, ["IG", "not-a-platform"])
