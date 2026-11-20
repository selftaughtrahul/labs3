"""Creator profiles. One row per platform profile, reused by every campaign."""

import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.signals import m2m_changed

from creators.choices import Currency, Platform, Tier
from creators.lists import clean_string_list, cleaned


class Country(models.Model):
    name = models.CharField(max_length=120, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "countries"
        ordering = ["name"]
        verbose_name_plural = "countries"
        verbose_name = "country"

    def __str__(self):
        return self.name


class Language(models.Model):
    name = models.CharField(max_length=120, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "languages"
        ordering = ["name"]
        verbose_name_plural = "languages"
        verbose_name = "language"

    def __str__(self):
        return self.name


class DeliverableType(models.Model):
    """A post, reel, video, or other unit a creator can be hired for."""

    name = models.CharField(max_length=120, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "deliverable_types"
        ordering = ["name"]
        verbose_name_plural = "deliverable types"

    def __str__(self):
        return self.name


class Creator(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    platform = models.CharField(max_length=32, choices=Platform.choices)
    profile_link = models.URLField(max_length=500,help_text="Unique together with the platform, so the same profile cannot be added twice.")
    influencer_name = models.CharField(max_length=200, verbose_name="name")
    niche = models.JSONField(default=list,blank=True,help_text="Comma-separated, for example beauty, skincare.")
    country = models.ForeignKey(Country,on_delete=models.PROTECT,null=True,blank=True,related_name="creators",verbose_name="country")
    language = models.ForeignKey(Language,on_delete=models.PROTECT,null=True,blank=True,related_name="creators",verbose_name="language")
    tier = models.CharField(max_length=16, choices=Tier.choices, blank=True)
    followers = models.PositiveIntegerField(null=True, blank=True)
    email = models.EmailField(blank=True)
    engagement_rate = models.DecimalField(max_digits=5,decimal_places=2,null=True,blank=True,validators=[MinValueValidator(0), MaxValueValidator(100)],help_text="Percent, for example 2.50.",verbose_name="engagement %")
    avg_views = models.PositiveIntegerField(null=True,blank=True,verbose_name="average views")
    other_contact = models.CharField(max_length=250, blank=True)
    audience_insights = models.TextField(blank=True)
    geo = models.CharField(max_length=120, blank=True)
    female_pct = models.DecimalField(max_digits=5,decimal_places=2,null=True,blank=True,validators=[MinValueValidator(0), MaxValueValidator(100)],verbose_name="female %")
    male_pct = models.DecimalField(max_digits=5,decimal_places=2,null=True,blank=True,validators=[MinValueValidator(0), MaxValueValidator(100)],verbose_name="male %")
    is_profile_checked = models.BooleanField(default=False,help_text="Tick this after a person has reviewed the profile.",verbose_name="profile checked")
    source = models.CharField(max_length=64,blank=True,help_text="Where the profile came from, for example sheet or manual.")
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="added_creators",null=True,blank=True)
    added_at = models.DateField(null=True, blank=True, verbose_name="added on")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "creators"
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["platform", "profile_link"],
                name="creator_platform_profile_uniq",
                violation_error_message="This profile link is already stored for that platform.",
            ),
            models.CheckConstraint(
                condition=models.Q(platform__in=Platform.values),
                name="creator_platform_known",
            ),
            models.CheckConstraint(
                condition=models.Q(tier="") | models.Q(tier__in=Tier.values),
                name="creator_tier_known",
            ),
        ]

    def __str__(self):
        return f"{self.influencer_name} · {self.get_platform_display()}"

    def clean(self):
        super().clean()
        self.profile_link = (self.profile_link or "").strip()
        self.influencer_name = " ".join((self.influencer_name or "").split())
        self.niche = cleaned("niche", clean_string_list, self.niche)
        self.other_contact = " ".join((self.other_contact or "").split())
        self.audience_insights = (self.audience_insights or "").strip()
        self.geo = " ".join((self.geo or "").split())


class CreatorRate(models.Model):
    """One current price. One deliverable, or several sold together as a bundle.

    A campaign stores its own copy of the agreed price, so later edits here do not
    change a campaign that already used this rate.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creator = models.ForeignKey(
        Creator,
        on_delete=models.CASCADE,
        related_name="rates",
    )
    deliverables = models.ManyToManyField(
        DeliverableType,
        related_name="rates",
        verbose_name="deliverables",
        help_text="Choose one for an individual rate. Choose several for one combined bundle price.",
    )
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    currency = models.CharField(max_length=8, choices=Currency.choices)
    bundle_key = models.CharField(max_length=1000, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "creator_rates"
        ordering = ["created_at"]
        verbose_name_plural = "creator rates"
        verbose_name = "creator rate"
        constraints = [
            models.UniqueConstraint(
                fields=["creator", "bundle_key"],
                condition=~models.Q(bundle_key=""),
                name="creator_rate_bundle_uniq",
                violation_error_message="This creator already has a price for that combination.",
            ),
            models.CheckConstraint(
                condition=models.Q(currency__in=Currency.values),
                name="creator_rate_currency_known",
            ),
        ]

    def __str__(self):
        names = list(self.deliverables.order_by("name").values_list("name", flat=True))
        label = " + ".join(names) if names else "No deliverables"
        return f"{label} · {self.price} {self.currency}"

    def deliverable_ids(self):
        if self.pk is None:
            return []
        return list(self.deliverables.order_by("pk").values_list("pk", flat=True))

    def same_bundle_exists(self, deliverable_ids):
        """True when this creator already has a rate for exactly these deliverables."""
        wanted = tuple(sorted(deliverable_ids))
        if not wanted:
            return False
        others = CreatorRate.objects.filter(creator_id=self.creator_id)
        if self.pk:
            others = others.exclude(pk=self.pk)
        for other in others:
            if tuple(other.deliverable_ids()) == wanted:
                return True
        return False


def remember_bundle(sender, instance, action, **kwargs):
    """Remember the deliverable set so the same bundle cannot be priced twice."""
    if action not in {"post_add", "post_remove", "post_clear"}:
        return
    key = ",".join(str(pk) for pk in instance.deliverable_ids())
    if instance.bundle_key == key:
        return
    CreatorRate.objects.filter(pk=instance.pk).update(bundle_key=key)
    instance.bundle_key = key


m2m_changed.connect(remember_bundle, sender=CreatorRate.deliverables.through)
