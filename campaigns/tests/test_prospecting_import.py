from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase

from accounts.models import User
from campaigns.models import CampaignCreator, Stage
from creators.models import Creator, CreatorRate


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


PROSPECTING_HEADER = [
    "Who prospected",
    "Platform",
    "Profile Link",
    "Influencer Name",
    "Campaign",
    "Outreach Status",
    "Currency",
    "Amount",
    "Amount in EUR",
    "Deliverables",
]


class ProspectingImportTests(TestCase):
    def setUp(self):
        User.objects.create_user(username="sheet", is_staff=True)

    def test_confirmed_tab_wins_and_writes_a_rate(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "prospecting.xlsx"
            write_workbook(
                path,
                {
                    "Prospecting & Outreach": [
                        PROSPECTING_HEADER,
                        [
                            "Trizha",
                            "Instagram",
                            "https://instagram.com/win",
                            "Win",
                            "VT Markets",
                            "Sent",
                            "EUR",
                            100,
                            100,
                            "IG Reel",
                        ],
                    ],
                    "Confirmed influencers": [
                        PROSPECTING_HEADER,
                        [
                            "Trizha",
                            "Instagram",
                            "https://instagram.com/win",
                            "Win",
                            "VT Markets",
                            "Confirmed",
                            "EUR",
                            250,
                            250,
                            "IG Reel, IG Story",
                        ],
                    ],
                    "Unresponsivenot Confirmed influ": [PROSPECTING_HEADER],
                    "Not Interested Influencers": [PROSPECTING_HEADER],
                    "Briefs - Internal (CF)": [
                        ["Campaign", "Campaign Status", "Brief", "Campaign Owner"]
                    ],
                },
            )
            call_command("import_prospecting_sheet", str(path))
        self.assertEqual(Creator.objects.count(), 1)
        deal = CampaignCreator.objects.get()
        self.assertEqual(deal.stage, Stage.CONFIRMED)
        self.assertEqual(deal.creator_price, Decimal("250.00"))
        rate = CreatorRate.objects.get()
        self.assertEqual(
            set(rate.deliverables.values_list("name", flat=True)),
            {"Instagram Reel", "Instagram Story"},
        )
