from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from campaigns.models import Campaign, CampaignCreator
from creators.choices import Platform
from creators.models import Creator


class AdminPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("admin", "admin@example.com", "pass-word")
        self.client.force_login(self.user)
        self.creator = Creator.objects.create(
            platform=Platform.YOUTUBE,
            profile_link="https://youtube.com/@sample",
            influencer_name="Sample",
        )
        self.campaign = Campaign.objects.create(client_name="Admin Brief", campaign_owner=self.user)
        self.deal = CampaignCreator.objects.create(campaign=self.campaign, creator=self.creator)

    def test_changelists_and_forms_render(self):
        urls = [
            reverse("admin:creators_country_changelist"),
            reverse("admin:creators_language_changelist"),
            reverse("admin:creators_deliverabletype_changelist"),
            reverse("admin:creators_creator_changelist"),
            reverse("admin:creators_creator_change", args=[self.creator.id]),
            reverse("admin:creators_creatorrate_changelist"),
            reverse("admin:creators_creatorrate_add"),
            reverse("admin:campaigns_campaign_changelist"),
            reverse("admin:campaigns_campaign_change", args=[self.campaign.id]),
            reverse("admin:campaigns_campaigncreator_changelist"),
            reverse("admin:campaigns_campaigncreator_change", args=[self.deal.id]),
            reverse("admin:campaigns_outreach_changelist"),
        ]
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)

    def test_deliverable_admin_pages_render(self):
        urls = [
            reverse("admin:creators_deliverabletype_changelist"),
            reverse("admin:creators_deliverabletype_add"),
            reverse("admin:creators_creatorrate_add"),
            reverse("admin:campaigns_campaigncreator_change", args=[self.deal.id]),
        ]
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
            self.assertNotContains(response, "Server Error")
