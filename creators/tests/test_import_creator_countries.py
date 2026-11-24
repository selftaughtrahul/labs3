import csv
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase

from creators.choices import Platform
from creators.models import Country, Creator


class ImportCreatorCountriesTests(TestCase):
    def test_sheet_sets_the_country_master_id(self):
        germany = Country.objects.create(name="Germany")
        creator = Creator.objects.create(
            platform=Platform.YOUTUBE,
            profile_link="https://youtube.com/@sample",
            influencer_name="sample",
        )
        other = Creator.objects.create(
            platform=Platform.INSTAGRAM,
            profile_link="https://instagram.com/kept",
            influencer_name="kept",
            country=germany,
        )
        with TemporaryDirectory() as folder:
            path = Path(folder) / "countries.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["name", "platform", "profile_link", "country"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "name": "Sample",
                        "platform": "youtube",
                        "profile_link": "https://www.youtube.com/@sample/videos",
                        "country": "Brazil",
                    }
                )
                writer.writerow(
                    {
                        "name": "Kept",
                        "platform": "instagram",
                        "profile_link": "https://instagram.com/kept",
                        "country": "",
                    }
                )
                writer.writerow(
                    {
                        "name": "Gone",
                        "platform": "instagram",
                        "profile_link": "https://instagram.com/missing",
                        "country": "France",
                    }
                )
            output = StringIO()
            call_command("import_creator_countries", str(path), stdout=output)

        creator.refresh_from_db()
        other.refresh_from_db()
        brazil = Country.objects.get(name="Brazil")
        self.assertEqual(creator.country_id, brazil.pk)
        self.assertEqual(other.country_id, germany.pk)
        self.assertIn("Set 1", output.getvalue())
        self.assertIn("blank 1", output.getvalue())
        self.assertIn("missing 1", output.getvalue())
