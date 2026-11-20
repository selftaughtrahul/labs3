from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase

from accounts.models import User
from campaigns.models import Campaign, CampaignCreator, CampaignStatus, Stage
from campaigns.sheet_status import map_deal_stage
from creators.choices import Currency, Platform
from creators.models import Creator, CreatorRate, DeliverableType


def write_workbook(path, sheets):
    from openpyxl import Workbook

    book = Workbook()
    first = True
    for name, rows in sheets.items():
        sheet = book.active if first else book.create_sheet()
        first = False
        sheet.title = name
        for row in rows:
            sheet.append(row)
    book.save(path)


class DealStageMapTests(TestCase):
    def test_sheet_spellings(self):
        self.assertEqual(map_deal_stage("Follow-Up")[0], Stage.FOLLOW_UP)
        self.assertEqual(map_deal_stage("Confirmed")[0], Stage.CONFIRMED)
        self.assertEqual(map_deal_stage("Campaign Declined")[0], Stage.CANCELLED)
        self.assertEqual(map_deal_stage("", "unresponsive")[0], Stage.UNRESPONSIVE)
        stage, _outreach, known = map_deal_stage("mystery status")
        self.assertFalse(known)
        self.assertEqual(stage, Stage.SHORTLISTED)


class TrackerImportTests(TestCase):
    def setUp(self):
        User.objects.create_user(username="sheet", is_staff=True)

    def test_creates_creator_deal_and_rate(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "tracker.xlsx"
            write_workbook(
                path,
                {
                    "Creator Tracking": [
                        [
                            "Campaign Name",
                            "Campaign Owner",
                            "Full name of Creator",
                            "Profile link",
                            "Platform",
                            "Country",
                            "Workflow Stage",
                            "Currency",
                            "Creator Fee  (Put Amount Here Only) ",
                            "Creator Fee (€)",
                            "Total Fee (To be paid by client) (Put Amount Here Only)",
                            "Total Fee (€) ",
                            "Content Type ",
                        ],
                        [
                            "IUX",
                            "Ranell",
                            "Artzanocrxpto",
                            "https://www.youtube.com/@arzanocrypto/videos",
                            "YouTube",
                            "Indonesia",
                            "Completed",
                            "EUR",
                            212,
                            212,
                            677.83,
                            677.83,
                            "Reel",
                        ],
                    ]
                },
            )
            call_command("import_tracker_sheet", str(path))
        creator = Creator.objects.get()
        self.assertEqual(creator.platform, Platform.YOUTUBE)
        self.assertEqual(creator.profile_link, "https://youtube.com/@arzanocrypto")
        deal = CampaignCreator.objects.get()
        self.assertEqual(deal.stage, Stage.COMPLETED)
        self.assertEqual(deal.creator_price, Decimal("212.00"))
        self.assertEqual(deal.client_price, Decimal("677.83"))
        rate = CreatorRate.objects.get()
        self.assertEqual(set(rate.deliverables.values_list("name", flat=True)), {"Reel"})
        self.assertEqual(Campaign.objects.get().status, CampaignStatus.NOT_STARTED)

    def test_second_import_keeps_existing_rate_and_deal_price(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "tracker.xlsx"
            write_workbook(
                path,
                {
                    "Creator Tracking": [
                        [
                            "Campaign Name",
                            "Full name of Creator",
                            "Profile link",
                            "Platform",
                            "Workflow Stage",
                            "Currency",
                            "Creator Fee",
                            "Content Type",
                        ],
                        [
                            "IUX",
                            "One",
                            "https://instagram.com/one",
                            "Instagram",
                            "In Progress",
                            "EUR",
                            100,
                            "Reel",
                        ],
                    ]
                },
            )
            call_command("import_tracker_sheet", str(path))
            CreatorRate.objects.update(price=Decimal("50.00"))
            deal = CampaignCreator.objects.get()
            deal.creator_price = Decimal("50.00")
            deal.creator_price_eur = Decimal("50.00")
            deal.save()
            call_command("import_tracker_sheet", str(path))
        self.assertEqual(Creator.objects.count(), 1)
        self.assertEqual(CampaignCreator.objects.count(), 1)
        self.assertEqual(CreatorRate.objects.get().price, Decimal("50.00"))
        self.assertEqual(CampaignCreator.objects.get().creator_price, Decimal("50.00"))
        self.assertEqual(CampaignCreator.objects.get().stage, Stage.IN_PROGRESS)


class CentralImportTests(TestCase):
    def setUp(self):
        User.objects.create_user(username="sheet", is_staff=True)

    def test_reads_centralised_database_tab(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "central.xlsx"
            write_workbook(
                path,
                {
                    "Centralised Database": [
                        [
                            "Who Added",
                            "Platform",
                            "Profile Link",
                            "Influencer Name",
                            "Country",
                            "Campaign",
                            "Outreach Status",
                            "Currency",
                            "Price",
                            "Amount in EUR",
                            "Deliverables",
                        ],
                        [
                            "Andrea",
                            "Instagram",
                            "https://www.instagram.com/sample/",
                            "Sample",
                            "Germany",
                            "Bixberry",
                            "Confirmed",
                            "EUR",
                            400,
                            400,
                            "IG Reel, IG Story",
                        ],
                    ]
                },
            )
            call_command("import_central_sheet", str(path))
        creator = Creator.objects.get()
        self.assertEqual(creator.country.name, "Germany")
        deal = CampaignCreator.objects.get()
        self.assertEqual(deal.stage, Stage.CONFIRMED)
        rate = CreatorRate.objects.get()
        self.assertEqual(
            set(rate.deliverables.values_list("name", flat=True)),
            {"IG Reel", "IG Story"},
        )
        self.assertTrue(DeliverableType.objects.filter(name="IG Reel").exists())
        self.assertTrue(DeliverableType.objects.filter(name="IG Story").exists())
