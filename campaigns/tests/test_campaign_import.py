from datetime import date
from decimal import Decimal

from django.test import TestCase

from accounts.models import User
from campaigns.management.commands.import_campaign_briefs import (
    Command,
    brief_from_values,
    master_from_values,
    overlay,
)
from campaigns.models import Campaign, CampaignStatus
from creators.choices import Platform
from creators.models import Country


BRIEF_HEADER = [
    "Client",
    "Priority",
    "List Submitted",
    "Ready for the Dev team",
    "Deadline to scout the profiles",
    "Primary Market",
    "Additional Markets",
    "# Creators Needed",
    "Platform",
    "Primary Niche / Vertical",
    "Secondary Niche / Sub Niche",
    "Content Type",
    "Content Format",
    "Age Range",
    "Min View Consistency",
    "Min Followers",
    "Max Followers/Tiers",
    "Min Avg Views",
    "Min Engagement Rate (%)",
    "Status",
    "Brief",
]
MASTER_HEADER = [
    "Campaign Name",
    "Client POC Name",
    "Team Lead",
    "POC",
    "2nd POC",
    "Scouting/outreach",
    "Start Date",
    "Deadline",
    "Budget  3 months actual currency",
    "Campaign Currency",
    "Conversion EUR",
    "Target Creators",
    "Campaign Status",
    "Last Update Date (DD/MM/YYYY)",
    "Notes",
    "Internal Working Sheet",
    "CF List",
]


class CampaignImportMergeTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="sheet", is_staff=True)
        self.command = Command()

    def test_brief_and_master_share_one_campaign(self):
        brief = brief_from_values(
            BRIEF_HEADER,
            [
                "Bixberry",
                "TRUE",
                "TRUE",
                "TRUE",
                "23/10/2026",
                "Germany",
                "",
                "5",
                "Instagram",
                "Fintech",
                "Crypto",
                "Reel",
                "Reel + Story",
                "25-34",
                "Consistent",
                "50000",
                "1000000",
                "5000",
                "2.5",
                "Scouting",
                "Find finance creators",
            ],
        )
        master = master_from_values(
            MASTER_HEADER,
            [
                "bixberry",
                "Emilija",
                "Andrea",
                "Andrea",
                "Patrick",
                "Udaya, Patrick",
                "16/09/2026",
                "n/a",
                "10000",
                "USD",
                "9094.5",
                "8",
                "Active",
                "11/03/2026",
                "Scouting started",
                "Bixberry working file",
                "Bixberry CF",
            ],
        )
        merged = overlay(brief, master)
        created = self.command._save_campaign(merged, self.owner)
        self.assertTrue(created)
        created_again = self.command._save_campaign(merged, self.owner)
        self.assertFalse(created_again)
        self.assertEqual(Campaign.objects.count(), 1)
        campaign = Campaign.objects.get()
        self.assertEqual(campaign.client_name, "Bixberry")
        self.assertEqual(campaign.status, CampaignStatus.ACTIVE)
        self.assertEqual(campaign.creators_needed, 5)
        self.assertEqual(campaign.campaign_owner.username, "andrea")
        self.assertEqual(campaign.created_by, campaign.campaign_owner)
        self.assertEqual(campaign.client_poc_name, "Emilija")
        self.assertEqual(
            set(campaign.poc.values_list("username", flat=True)),
            {"andrea", "patrick"},
        )
        self.assertEqual(
            set(campaign.scouting_team.values_list("username", flat=True)),
            {"udaya", "patrick"},
        )
        self.assertEqual(campaign.start_date, date(2026, 9, 16))
        self.assertIsNone(campaign.deadline)
        self.assertEqual(campaign.deadline_to_scout, date(2026, 10, 23))
        self.assertEqual(campaign.budget_amount, Decimal("10000"))
        self.assertEqual(campaign.budget_currency, "USD")
        self.assertEqual(campaign.budget_eur, Decimal("9094.5"))
        self.assertIn("Scouting started", campaign.notes)
        self.assertIn("Bixberry working file", campaign.notes)
        self.assertIn("Bixberry CF", campaign.notes)
        self.assertIn("25-34", campaign.remarks_brief)
        self.assertIn("Consistent", campaign.remarks_brief)
        self.assertEqual(campaign.platforms, [Platform.INSTAGRAM])
        self.assertEqual(campaign.min_followers, 50000)
        self.assertEqual(list(campaign.country_market.values_list("name", flat=True)), ["Germany"])
        self.assertIn("Find finance creators", campaign.remarks_brief)

    def test_second_name_is_inserted(self):
        first = master_from_values(
            MASTER_HEADER,
            ["Bixberry", "", "Andrea", "", "", "", "", "", "", "", "", "", "Active", "", "", "", ""],
        )
        second = master_from_values(
            MASTER_HEADER,
            ["sbxfx", "", "Andrea", "", "", "", "", "", "TBD", "", "", "", "Cancelled", "", "Client unresponsive", "", ""],
        )
        self.command._save_campaign(first, self.owner)
        created = self.command._save_campaign(second, self.owner)
        self.assertTrue(created)
        self.assertEqual(Campaign.objects.count(), 2)
        other = Campaign.objects.get(client_name="sbxfx")
        self.assertEqual(other.status, CampaignStatus.CANCELLED)
        self.assertEqual(other.notes, "Client unresponsive")
        self.assertIsNone(other.budget_amount)

    def test_empty_cell_does_not_clear_a_stored_value(self):
        campaign = Campaign.objects.create(
            client_name="Keep Notes",
            campaign_owner=self.owner,
            notes="Already stored",
            creators_needed=7,
            status=CampaignStatus.ACTIVE,
        )
        row = master_from_values(
            MASTER_HEADER,
            ["Keep Notes", "", "Andrea", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
        )
        self.command._save_campaign(row, self.owner)
        campaign.refresh_from_db()
        self.assertEqual(campaign.notes, "Already stored")
        self.assertEqual(campaign.creators_needed, 7)
        self.assertEqual(campaign.status, CampaignStatus.ACTIVE)
        self.assertEqual(campaign.campaign_owner.username, "andrea")
