from decimal import Decimal

from django.test import TestCase

from accounts.models import User
from campaigns.models import Campaign, CampaignCreator, CampaignCreatorDeliverable
from creators.choices import Currency, Platform
from creators.deliverable_compact import SPLIT_NAME, compact, consolidate
from creators.models import Creator, CreatorRate, DeliverableType


class DeliverableCompactTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username="compact")
        self.campaign = Campaign.objects.create(client_name="Compact", campaign_owner=owner)
        self.keep = DeliverableType.objects.create(name="TT Video Compact")
        self.old = DeliverableType.objects.create(name="TikTok Video Compact")

    def _creator(self, name, link):
        return Creator.objects.create(
            platform=Platform.INSTAGRAM,
            profile_link=link,
            influencer_name=name,
        )

    def _deal(self, creator):
        return CampaignCreator.objects.create(campaign=self.campaign, creator=creator)

    def _line(self, deal, kind, name=None):
        return CampaignCreatorDeliverable.objects.create(
            campaign_creator=deal,
            deliverable_type=kind,
            name=name or kind.name,
        )

    def _rate(self, creator, kinds, price="10.00"):
        rate = CreatorRate.objects.create(
            creator=creator,
            price=Decimal(price),
            currency=Currency.EUR,
        )
        rate.deliverables.set(kinds)
        return rate

    def _compact(self, extra=None):
        mapping = {self.old.pk: self.keep.pk}
        if extra:
            mapping.update(extra)
        return compact(keeper_map=mapping, split_keep_id=0, split_drop_id=0)

    def test_deal_line_moves_and_keeps_the_snapshot_name(self):
        deal = self._deal(self._creator("A", "https://instagram.com/a"))
        line = self._line(deal, self.old, name="TikTok Video Compact")
        self._compact()
        line.refresh_from_db()
        self.assertEqual(line.deliverable_type_id, self.keep.pk)
        self.assertEqual(line.name, "TikTok Video Compact")
        self.assertFalse(DeliverableType.objects.filter(pk=self.old.pk).exists())

    def test_deal_with_both_types_drops_the_extra_line(self):
        deal = self._deal(self._creator("B", "https://instagram.com/b"))
        extra = self._line(deal, self.old, name="Old spelling")
        keeper_line = self._line(deal, self.keep, name="Keeper")
        self._compact()
        self.assertFalse(CampaignCreatorDeliverable.objects.filter(pk=extra.pk).exists())
        keeper_line.refresh_from_db()
        self.assertEqual(keeper_line.deliverable_type_id, self.keep.pk)
        self.assertEqual(keeper_line.name, "Keeper")

    def test_rate_moves_and_rebuilds_bundle_key(self):
        creator = self._creator("C", "https://instagram.com/c")
        rate = self._rate(creator, [self.old], "40.00")
        self._compact()
        rate.refresh_from_db()
        self.assertEqual(list(rate.deliverables.values_list("pk", flat=True)), [self.keep.pk])
        self.assertEqual(rate.bundle_key, str(self.keep.pk))

    def test_rate_with_a_price_clash_is_left_alone(self):
        creator = self._creator("D", "https://instagram.com/d")
        keep_rate = self._rate(creator, [self.keep], "50.00")
        old_rate = self._rate(creator, [self.old], "60.00")
        result = self._compact()
        self.assertEqual(result["skipped_rates"], 1)
        old_rate.refresh_from_db()
        keep_rate.refresh_from_db()
        self.assertEqual(list(old_rate.deliverables.values_list("pk", flat=True)), [self.old.pk])
        self.assertEqual(old_rate.bundle_key, str(self.old.pk))
        self.assertEqual(list(keep_rate.deliverables.values_list("pk", flat=True)), [self.keep.pk])
        self.assertTrue(DeliverableType.objects.filter(pk=self.old.pk).exists())

    def test_split_quote_becomes_one_name(self):
        keep = DeliverableType.objects.create(name='"Crossposted to YT')
        drop = DeliverableType.objects.create(name='IG"')
        creator = self._creator("E", "https://instagram.com/e")
        deal = self._deal(creator)
        keep_line = self._line(deal, keep, name=keep.name)
        drop_line = self._line(deal, drop, name=drop.name)
        rate = self._rate(creator, [keep, drop], "12.00")
        compact(keeper_map={}, split_keep_id=keep.pk, split_drop_id=drop.pk)
        keep.refresh_from_db()
        keep_line.refresh_from_db()
        rate.refresh_from_db()
        self.assertEqual(keep.name, SPLIT_NAME)
        self.assertEqual(keep_line.name, SPLIT_NAME)
        self.assertFalse(CampaignCreatorDeliverable.objects.filter(pk=drop_line.pk).exists())
        self.assertEqual(list(rate.deliverables.values_list("pk", flat=True)), [keep.pk])
        self.assertFalse(DeliverableType.objects.filter(pk=drop.pk).exists())

    def test_consolidate_renames_and_merges_by_name(self):
        keep, _created = DeliverableType.objects.get_or_create(name="Instagram Reel")
        old = DeliverableType.objects.create(name="4 Reel")
        qty = DeliverableType.objects.create(name="2 IG Reel")
        creator = self._creator("F", "https://instagram.com/f")
        deal = self._deal(creator)
        line = self._line(deal, old, name="4 Reel")
        qty_line = self._line(
            self._deal(self._creator("G", "https://instagram.com/g")),
            qty,
            name="2 IG Reel",
        )
        rate = self._rate(creator, [old], "10.00")
        consolidate()
        keep.refresh_from_db()
        line.refresh_from_db()
        qty_line.refresh_from_db()
        rate.refresh_from_db()
        self.assertEqual(keep.name, "Instagram Reel")
        self.assertEqual(line.deliverable_type_id, keep.pk)
        self.assertEqual(line.name, "4 Reel")
        self.assertEqual(qty_line.deliverable_type_id, keep.pk)
        self.assertEqual(qty_line.name, "2 IG Reel")
        self.assertEqual(list(rate.deliverables.values_list("pk", flat=True)), [keep.pk])
        self.assertFalse(DeliverableType.objects.filter(pk=old.pk).exists())
        self.assertFalse(DeliverableType.objects.filter(pk=qty.pk).exists())

    def test_consolidate_skips_a_rate_price_clash(self):
        keep, _created = DeliverableType.objects.get_or_create(name="Instagram Reel")
        old = DeliverableType.objects.create(name="4 Reel")
        creator = self._creator("H", "https://instagram.com/h")
        keep_rate = self._rate(creator, [keep], "50.00")
        old_rate = self._rate(creator, [old], "60.00")
        result = consolidate()
        self.assertGreaterEqual(result["skipped_rates"], 1)
        old_rate.refresh_from_db()
        keep_rate.refresh_from_db()
        keep.refresh_from_db()
        self.assertEqual(keep.name, "Instagram Reel")
        self.assertEqual(list(old_rate.deliverables.values_list("pk", flat=True)), [old.pk])
        self.assertTrue(DeliverableType.objects.filter(pk=old.pk).exists())
