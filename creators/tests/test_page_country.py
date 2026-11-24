from django.test import SimpleTestCase

from creators.page_country import choose_known_country, country_name_from_page, profile_url_to_fetch


class PageCountryTests(SimpleTestCase):
    def test_youtube_about_simple_text_is_a_country(self):
        html = '"country":{"simpleText":"Germany"}'
        self.assertEqual(country_name_from_page(html), "Germany")

    def test_youtube_code_uses_the_official_name(self):
        html = '"aboutChannelViewModel" "country":"US"'
        self.assertEqual(country_name_from_page(html), "United States")

    def test_a_region_or_a_loose_mention_stays_blank(self):
        html = '"country":{"simpleText":"Latam"} ship to United States "country":"US"'
        self.assertEqual(country_name_from_page(html), "")

    def test_one_known_country_is_reused(self):
        self.assertEqual(choose_known_country({"Spain"}, set(), ""), "Spain")
        self.assertEqual(choose_known_country(set(), set(), "Portuguese(Brazil)"), "Brazil")

    def test_disagreeing_countries_stay_blank(self):
        self.assertEqual(choose_known_country({"Spain"}, {"Mexico"}, ""), "")

    def test_youtube_links_open_the_about_page(self):
        self.assertEqual(
            profile_url_to_fetch("https://youtube.com/@ErichsenGeld?si=1"),
            "https://youtube.com/@ErichsenGeld/about",
        )
        self.assertEqual(
            profile_url_to_fetch("https://instagram.com/name"),
            "https://instagram.com/name",
        )
        self.assertEqual(
            profile_url_to_fetch("https://www.youtube.com/@2foodfitlovers/videos"),
            "https://www.youtube.com/@2foodfitlovers/about",
        )
