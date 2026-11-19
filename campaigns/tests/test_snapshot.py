from decimal import Decimal

from django.db.models import ProtectedError
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from campaigns.deliverables import replace_deliverable_lines
from campaigns.models import (
    Campaign,
    CampaignCreator,
    CampaignCreatorDeliverable,
    Channel,
    ClientShare,
    ClientShareItem,
    Decision,
    Outreach,
    OutreachStatus,
)
from creators.choices import Currency, Platform
from creators.models import Country, Creator, CreatorRate, DeliverableType


class SnapshotTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username="owner")
        creator = Creator.objects.create(
            platform=Platform.INSTAGRAM,
            profile_link="https://instagram.com/priced",
            influencer_name="Priced",
        )
        campaign = Campaign.objects.create(client_name="Snapshot", campaign_owner=owner)
        self.deal = CampaignCreator.objects.create(campaign=campaign, creator=creator)
        self.creator = creator
        self.kind, _created = DeliverableType.objects.get_or_create(name="Reel")

    def test_new_eur_confirmation_copies_the_offer(self):
        Outreach.objects.create(
            campaign_creator=self.deal,
            channel=Channel.EMAIL,
            outreach_status=OutreachStatus.CONFIRMED,
            quoted_price=Decimal("10.00"),
            offered_price=Decimal("8.00"),
            currency=Currency.EUR,
        )
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.creator_price, Decimal("8.00"))
        self.assertEqual(self.deal.creator_currency, Currency.EUR)
        self.assertEqual(self.deal.creator_price_eur, Decimal("8.00"))

    def test_saving_a_confirmed_row_again_leaves_the_deal(self):
        message = Outreach.objects.create(
            campaign_creator=self.deal,
            channel=Channel.EMAIL,
            outreach_status=OutreachStatus.CONFIRMED,
            quoted_price=Decimal("10.00"),
            currency=Currency.EUR,
        )
        self.deal.creator_price = Decimal("99.00")
        self.deal.creator_currency = Currency.EUR
        self.deal.creator_price_eur = Decimal("99.00")
        self.deal.save()
        message.save()
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.creator_price, Decimal("99.00"))

    def test_non_eur_confirmation_leaves_the_deal(self):
        self.deal.creator_price = Decimal("5.00")
        self.deal.creator_currency = Currency.EUR
        self.deal.creator_price_eur = Decimal("5.00")
        self.deal.save()
        Outreach.objects.create(
            campaign_creator=self.deal,
            channel=Channel.EMAIL,
            outreach_status=OutreachStatus.CONFIRMED,
            quoted_price=Decimal("20.00"),
            currency=Currency.USD,
        )
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.creator_price, Decimal("5.00"))

    def test_rate_card_edit_leaves_the_deal(self):
        rate = CreatorRate.objects.create(
            creator=self.creator,
            price=Decimal("10.00"),
            currency=Currency.EUR,
        )
        rate.deliverables.add(self.kind)
        self.deal.creator_price = Decimal("10.00")
        self.deal.creator_currency = Currency.EUR
        self.deal.creator_price_eur = Decimal("10.00")
        self.deal.save()
        rate.price = Decimal("20.00")
        rate.save()
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.creator_price, Decimal("10.00"))

    def test_renaming_a_deliverable_leaves_the_frozen_name(self):
        line = CampaignCreatorDeliverable.objects.create(
            campaign_creator=self.deal,
            deliverable_type=self.kind,
            name="Reel",
        )
        self.kind.name = "Short video"
        self.kind.save()
        line.refresh_from_db()
        self.assertEqual(line.name, "Reel")

    def test_replace_does_not_rewrite_an_existing_name(self):
        CampaignCreatorDeliverable.objects.create(
            campaign_creator=self.deal,
            deliverable_type=self.kind,
            name="Reel",
        )
        replace_deliverable_lines(self.deal, ["reel"])
        line = self.deal.deliverable_lines.get()
        self.assertEqual(line.name, "Reel")

    def test_quoted_eur_without_an_offer_is_copied(self):
        Outreach.objects.create(
            campaign_creator=self.deal,
            channel=Channel.EMAIL,
            outreach_status=OutreachStatus.CONFIRMED,
            quoted_price=Decimal("10.00"),
            currency=Currency.EUR,
        )
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.creator_price, Decimal("10.00"))
        self.assertEqual(self.deal.creator_price_eur, Decimal("10.00"))

    def test_changing_status_to_confirmed_copies_the_price(self):
        message = Outreach.objects.create(
            campaign_creator=self.deal,
            channel=Channel.EMAIL,
            outreach_status=OutreachStatus.NEGOTIATING,
            quoted_price=Decimal("12.00"),
            currency=Currency.EUR,
        )
        self.deal.refresh_from_db()
        self.assertIsNone(self.deal.creator_price)
        message.outreach_status = OutreachStatus.CONFIRMED
        message.save()
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.creator_price, Decimal("12.00"))

    def test_a_later_confirmation_updates_the_deal(self):
        Outreach.objects.create(
            campaign_creator=self.deal,
            channel=Channel.EMAIL,
            outreach_status=OutreachStatus.CONFIRMED,
            quoted_price=Decimal("10.00"),
            currency=Currency.EUR,
        )
        Outreach.objects.create(
            campaign_creator=self.deal,
            channel=Channel.EMAIL,
            outreach_status=OutreachStatus.CONFIRMED,
            quoted_price=Decimal("15.00"),
            currency=Currency.EUR,
        )
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.creator_price, Decimal("15.00"))

    def test_follow_up_does_not_clear_the_deal_price(self):
        self._set_eur_price(Decimal("5.00"))
        Outreach.objects.create(
            campaign_creator=self.deal,
            channel=Channel.EMAIL,
            outreach_status=OutreachStatus.FOLLOW_UP,
        )
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.creator_price, Decimal("5.00"))

    def test_confirmed_row_without_a_price_leaves_the_deal(self):
        self._set_eur_price(Decimal("5.00"))
        Outreach.objects.create(
            campaign_creator=self.deal,
            channel=Channel.EMAIL,
            outreach_status=OutreachStatus.CONFIRMED,
        )
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.creator_price, Decimal("5.00"))

    def test_bulk_import_does_not_copy_a_confirmed_price(self):
        Outreach.objects.bulk_create(
            [
                Outreach(
                    campaign_creator=self.deal,
                    channel=Channel.EMAIL,
                    outreach_status=OutreachStatus.CONFIRMED,
                    quoted_price=Decimal("40.00"),
                    currency=Currency.EUR,
                )
            ]
        )
        self.deal.refresh_from_db()
        self.assertIsNone(self.deal.creator_price)

    def test_confirmation_recalculates_margin(self):
        self.deal.client_price = Decimal("30.00")
        self.deal.client_currency = Currency.EUR
        self.deal.client_price_eur = Decimal("30.00")
        self.deal.save()
        Outreach.objects.create(
            campaign_creator=self.deal,
            channel=Channel.EMAIL,
            outreach_status=OutreachStatus.CONFIRMED,
            offered_price=Decimal("8.00"),
            currency=Currency.EUR,
        )
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.margin_eur, Decimal("22.00"))

    def test_replace_adds_a_new_line_and_drops_a_removed_one(self):
        CampaignCreatorDeliverable.objects.create(
            campaign_creator=self.deal,
            deliverable_type=self.kind,
            name="Reel",
        )
        replace_deliverable_lines(self.deal, ["reel", "Story"])
        self.assertEqual(
            set(self.deal.deliverable_lines.values_list("name", flat=True)),
            {"Reel", "Story"},
        )
        replace_deliverable_lines(self.deal, ["Story"])
        self.assertEqual(
            list(self.deal.deliverable_lines.values_list("name", flat=True)),
            ["Story"],
        )

    def test_client_accept_copies_the_answer_and_leaves_the_creator_price(self):
        self._set_eur_price(Decimal("10.00"))
        share = ClientShare.objects.create(campaign=self.deal.campaign, title="Round 1")
        ClientShareItem.objects.create(
            client_share=share,
            campaign_creator=self.deal,
            decision=Decision.ACCEPTED,
            decided_at=timezone.now(),
            client_price=Decimal("30.00"),
            client_currency=Currency.EUR,
        )
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.client_status, Decision.ACCEPTED)
        self.assertEqual(self.deal.creator_price, Decimal("10.00"))

    def test_a_used_country_cannot_be_deleted(self):
        spain = Country.objects.create(name="Spain")
        self.creator.country = spain
        self.creator.save()
        with self.assertRaises(ProtectedError):
            spain.delete()

    def _set_eur_price(self, amount):
        self.deal.creator_price = amount
        self.deal.creator_currency = Currency.EUR
        self.deal.creator_price_eur = amount
        self.deal.save()
