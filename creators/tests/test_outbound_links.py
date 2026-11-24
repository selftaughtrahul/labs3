from django.test import SimpleTestCase

from creators.outbound_links import hub_links, links_by_platform, single_link


class OutboundLinkTests(SimpleTestCase):
    def test_youtube_sameas_keeps_the_instagram_profile(self):
        html = (
            '"sameAs":["https://www.tristanridley.com",'
            '"https://www.instagram.com/tristanrid/"]'
        )
        links = links_by_platform(html)
        self.assertEqual(
            single_link(links, "instagram", "https://youtube.com/@tristanrid"),
            "https://instagram.com/tristanrid",
        )

    def test_instagram_lynx_url_keeps_the_tiktok_profile(self):
        html = (
            r'lynx_url":"https:\/\/l.instagram.com\/?u=https\u00253A\u00252F\u00252F'
            r"www.tiktok.com\u00252F\u002540armatato51\u00253F_r\u00253D1"
        )
        links = links_by_platform(html)
        self.assertEqual(
            single_link(links, "tiktok", "https://instagram.com/armatato51"),
            "https://tiktok.com/@armatato51",
        )

    def test_posts_and_the_page_itself_are_ignored(self):
        html = (
            "https://www.instagram.com/reel/abc123 "
            "https://www.instagram.com/armatato51 "
            "https://youtube.com/watch?v=abc"
        )
        links = links_by_platform(html)
        self.assertEqual(links["instagram"], {"https://instagram.com/armatato51"})
        self.assertNotIn("youtube", links)
        self.assertEqual(single_link(links, "instagram", "https://instagram.com/armatato51"), "")

    def test_a_channel_id_does_not_compete_with_the_handle(self):
        html = (
            "https://m.youtube.com/@tristanrid&feature=__FEATURE__&hl=en "
            "https://youtube.com/channel/UCsH6xKAJyqKF2Ox0bXJrUaA "
            "https://about.instagram.com/blog "
            "https://www.instagram.com/tristanrid/"
        )
        links = links_by_platform(html)
        self.assertEqual(
            single_link(links, "youtube", "https://instagram.com/someone"),
            "https://youtube.com/@tristanrid",
        )
        self.assertEqual(links["instagram"], {"https://instagram.com/tristanrid"})

    def test_bio_hubs_are_the_link_pages_only(self):
        html = (
            '"url":"https://beacons.ai/alinaxloves" '
            '"url":"https://go.alinascreatorclub.de/ugc-call"'
        )
        self.assertEqual(hub_links(html), ["https://beacons.ai/alinaxloves"])
