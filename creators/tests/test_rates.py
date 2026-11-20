from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from creators.choices import Currency, Platform
from creators.forms import CreatorRateForm
from creators.models import Creator, CreatorRate, DeliverableType
from creators.rates import ensure_rate, ensure_rates


class CreatorRateBundleTests(TestCase):
    def setUp(self):
        self.creator = Creator.objects.create(
            platform=Platform.INSTAGRAM,
            profile_link="https://instagram.com/rates",
            influencer_name="Rates",
        )
        self.post = DeliverableType.objects.create(name="Rate Post")
        self.story = DeliverableType.objects.create(name="Rate Story")
        self.reel = DeliverableType.objects.create(name="Rate Reel")

    def _save_rate(self, deliverables, price="10.00"):
        form = CreatorRateForm(
            data={
                "creator": self.creator.pk,
                "price": price,
                "currency": Currency.EUR,
                "deliverables": [item.pk for item in deliverables],
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        return form.save()

    def test_one_deliverable_is_an_individual_rate(self):
        rate = self._save_rate([self.post])
        self.assertEqual(str(rate), "Rate Post · 10.00 EUR")
        self.assertEqual(rate.bundle_key, str(self.post.pk))

    def test_two_deliverables_share_one_price(self):
        rate = self._save_rate([self.story, self.post], price="12.00")
        self.assertEqual(set(rate.deliverables.values_list("name", flat=True)), {"Rate Post", "Rate Story"})
        self.assertEqual(rate.price, Decimal("12.00"))
        self.assertEqual(str(rate), "Rate Post + Rate Story · 12.00 EUR")

    def test_three_deliverables_share_one_price(self):
        rate = self._save_rate([self.reel, self.story, self.post], price="20.00")
        self.assertEqual(rate.deliverables.count(), 3)
        self.assertEqual(rate.price, Decimal("20.00"))

    def test_individual_rate_can_sit_beside_a_bundle(self):
        self._save_rate([self.post], price="10.00")
        bundle = self._save_rate([self.post, self.story], price="12.00")
        self.assertEqual(self.creator.rates.count(), 2)
        self.assertEqual(bundle.deliverables.count(), 2)

    def test_the_same_combination_cannot_be_priced_twice(self):
        self._save_rate([self.post, self.story])
        form = CreatorRateForm(
            data={
                "creator": self.creator.pk,
                "price": "30.00",
                "currency": Currency.EUR,
                "deliverables": [self.story.pk, self.post.pk],
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("combination", str(form.errors))

    def test_database_rejects_a_duplicate_bundle(self):
        first = self._save_rate([self.post, self.story])
        second = CreatorRate.objects.create(
            creator=self.creator,
            price=Decimal("30.00"),
            currency=Currency.EUR,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                second.deliverables.set([self.post, self.story])
        first.refresh_from_db()
        self.assertEqual(first.price, Decimal("10.00"))

    def test_ensure_rate_adds_a_missing_bundle(self):
        added = ensure_rate(
            self.creator, ["Rate Post", "Rate Story"], Decimal("15.00"), Currency.EUR
        )
        self.assertTrue(added)
        self.assertEqual(self.creator.rates.count(), 1)

    def test_ensure_rate_leaves_an_existing_price(self):
        ensure_rate(self.creator, ["Rate Post"], Decimal("10.00"), Currency.EUR)
        added = ensure_rate(self.creator, ["Rate Post"], Decimal("99.00"), Currency.EUR)
        self.assertFalse(added)
        self.assertEqual(self.creator.rates.get().price, Decimal("10.00"))

    def test_ensure_rate_reuses_the_deliverable_master(self):
        ensure_rate(self.creator, ["rate post"], Decimal("8.00"), Currency.EUR)
        self.assertEqual(DeliverableType.objects.filter(name__iexact="rate post").count(), 1)
        self.assertTrue(DeliverableType.objects.filter(name="Rate Post").exists())

    def test_ensure_rates_writes_many_rows_in_one_pass(self):
        other = Creator.objects.create(
            platform=Platform.YOUTUBE,
            profile_link="https://youtube.com/rates2",
            influencer_name="Rates Two",
        )
        added = ensure_rates(
            [
                (self.creator, ["Rate Post"], Decimal("11.00"), Currency.EUR),
                (other, ["Rate Story"], Decimal("12.00"), Currency.USD),
                (self.creator, ["Rate Post"], Decimal("99.00"), Currency.EUR),
            ]
        )
        self.assertEqual(added, 2)
        self.assertEqual(CreatorRate.objects.count(), 2)
        self.assertEqual(
            self.creator.rates.get().price,
            Decimal("11.00"),
        )

