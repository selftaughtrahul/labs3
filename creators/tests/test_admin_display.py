from django.contrib.admin.sites import AdminSite
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from creators.admin import CreatorAdmin, display_case
from creators.choices import Platform
from creators.models import Creator


class DisplayCaseTests(TestCase):
    def test_title_case_hides_a_trailing_underscore(self):
        self.assertEqual(display_case("puneet_"), "Puneet")
        self.assertEqual(display_case("PUNEET"), "Puneet")
        self.assertEqual(display_case("Puneet HS"), "Puneet Hs")
        self.assertEqual(display_case("beauty, skincare"), "Beauty, Skincare")
        self.assertEqual(display_case("  "), "")


class CreatorAdminDisplayTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("admin", "admin@example.com", "pass-word")
        self.client.force_login(self.user)
        self.creator = Creator.objects.create(
            platform=Platform.INSTAGRAM,
            profile_link="https://instagram.com/puneet_",
            influencer_name="puneet_",
            niche=["BEAUTY", "skin_care"],
            geo="new york_",
        )
        self.admin = CreatorAdmin(Creator, AdminSite())

    def test_list_labels_are_title_case_and_storage_stays_raw(self):
        self.assertEqual(self.admin.name_label(self.creator), "Puneet")
        self.assertEqual(self.admin.niche_list(self.creator), "Beauty, Skin Care")
        self.assertEqual(self.admin.geo_label(self.creator), "New York")
        self.creator.refresh_from_db()
        self.assertEqual(self.creator.influencer_name, "puneet_")
        self.assertEqual(self.creator.niche, ["BEAUTY", "skin_care"])
        self.assertEqual(self.creator.geo, "new york_")

    def test_changelist_shows_the_label_and_the_form_keeps_the_stored_name(self):
        listing = self.client.get(reverse("admin:creators_creator_changelist"))
        self.assertContains(listing, "Puneet")
        form = self.client.get(reverse("admin:creators_creator_change", args=[self.creator.id]))
        self.assertContains(form, 'value="puneet_"')
