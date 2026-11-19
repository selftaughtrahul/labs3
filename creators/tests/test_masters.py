from django.test import TestCase

from accounts.models import User
from campaigns.models import Campaign
from creators.masters import group_names, lookup_named
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


class CampaignMarketTests(TestCase):
    def test_markets_are_countries(self):
        owner = User.objects.create_user(username="owner")
        germany = lookup_named(Country, "Germany")
        campaign = Campaign.objects.create(client_name="Market Brief", campaign_owner=owner)
        campaign.country_market.add(germany)
        campaign.full_clean()
        self.assertEqual(list(campaign.country_market.values_list("name", flat=True)), ["Germany"])
        self.assertTrue(DeliverableType.objects.filter(name="Reel").exists())
