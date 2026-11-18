"""Client briefs, and one deal row for each creator placed on a brief."""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from creators.choices import Currency, Platform
from creators.lists import clean_country_codes, clean_string_list, cleaned


class CampaignStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SCOUTING = "scouting", "Scouting"
    OUTREACH = "outreach", "Outreach"
    CLIENT_SHARING = "client_sharing", "Client sharing"
    CLOSED = "closed", "Closed"


class Campaign(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client_name = models.CharField(max_length=200, unique=True)
    deadline_to_scout = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="scouting deadline",
    )
    country_market = models.JSONField(
        default=list,
        blank=True,
        help_text="Comma-separated country names, for example Germany, United States.",
        verbose_name="markets",
    )
    creators_needed = models.PositiveIntegerField(
        default=10,
        validators=[MinValueValidator(1)],
    )
    platforms = models.JSONField(
        default=list,
        blank=True,
        help_text="Platforms this brief is recruiting on.",
    )
    niche_vertical = models.JSONField(
        default=list,
        blank=True,
        help_text="Comma-separated, for example beauty, fitness.",
        verbose_name="niches",
    )
    sub_niche = models.JSONField(
        default=list,
        blank=True,
        help_text="Comma-separated.",
        verbose_name="sub-niches",
    )
    content_type = models.CharField(
        max_length=120,
        blank=True,
        help_text="The allowed list is not decided yet.",
    )
    content_format = models.CharField(
        max_length=120,
        blank=True,
        help_text="The allowed list is not decided yet.",
    )
    min_followers = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="minimum followers",
    )
    max_followers = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Leave empty for no upper limit. Must be at least the minimum.",
        verbose_name="maximum followers",
    )
    min_avg_views = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="minimum average views",
    )
    min_engagement_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Percent, for example 2.50.",
        verbose_name="minimum engagement %",
    )
    campaign_owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_campaigns",
        verbose_name="owner",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_campaigns",
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=32,
        choices=CampaignStatus.choices,
        default=CampaignStatus.DRAFT,
    )
    remarks_brief = models.TextField(blank=True, verbose_name="brief")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "campaigns"
        ordering = ["-updated_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=CampaignStatus.values),
                name="campaign_status_known",
            ),
            models.CheckConstraint(
                condition=models.Q(creators_needed__gte=1),
                name="campaign_creators_needed_gte_1",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(min_followers__isnull=True)
                    | models.Q(max_followers__isnull=True)
                    | models.Q(min_followers__lte=models.F("max_followers"))
                ),
                name="campaign_followers_range",
                violation_error_message="Minimum followers cannot be above the maximum.",
            ),
        ]

    def __str__(self):
        return f"{self.client_name} · {self.get_status_display()}"

    def clean(self):
        super().clean()
        self.client_name = " ".join((self.client_name or "").split())
        self.content_type = " ".join((self.content_type or "").split())
        self.content_format = " ".join((self.content_format or "").split())
        self.country_market = cleaned("country_market", clean_country_codes, self.country_market)
        self.niche_vertical = cleaned("niche_vertical", clean_string_list, self.niche_vertical)
        self.sub_niche = cleaned("sub_niche", clean_string_list, self.sub_niche)
        self.platforms = cleaned("platforms", clean_string_list, self.platforms)
        unknown = [name for name in self.platforms if name not in Platform.values]
        if unknown:
            raise ValidationError({"platforms": "Choose a platform from the list."})
        if (
            self.min_followers is not None
            and self.max_followers is not None
            and self.min_followers > self.max_followers
        ):
            raise ValidationError(
                {"max_followers": "Maximum followers cannot be below the minimum."}
            )


class Stage(models.TextChoices):
    SHORTLISTED = "shortlisted", "Shortlisted"
    CONTACTED = "contacted", "Contacted"
    NEGOTIATING = "negotiating", "Negotiating"
    CONFIRMED = "confirmed", "Confirmed"
    SHARED = "shared_with_client", "Shared with client"
    NOT_INTERESTED = "not_interested", "Not interested"
    UNRESPONSIVE = "unresponsive", "Unresponsive"


class Decision(models.TextChoices):
    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"


class Deliverable(models.TextChoices):
    """The review slide names Reel and Story. Notes cover anything else."""

    REEL = "reel", "Reel"
    STORY = "story", "Story"


def apply_budget(obj, prefix):
    """Line up one price with its currency and the EUR copy.

    A price in EUR is copied across. A USD price keeps a separate EUR amount,
    because the design has no exchange rate.
    """
    price = getattr(obj, f"{prefix}_price")
    currency = getattr(obj, f"{prefix}_currency")
    if price is None:
        setattr(obj, f"{prefix}_currency", "")
        setattr(obj, f"{prefix}_price_eur", None)
        return {}
    if currency == Currency.EUR:
        setattr(obj, f"{prefix}_price_eur", price)
        return {}
    if not currency:
        return {f"{prefix}_currency": "Choose a currency when a price is set."}
    if getattr(obj, f"{prefix}_price_eur") is None:
        return {f"{prefix}_price_eur": "Enter the amount in EUR."}
    return {}


def budget_constraint(prefix):
    price, currency, price_eur = (
        f"{prefix}_price",
        f"{prefix}_currency",
        f"{prefix}_price_eur",
    )
    return models.CheckConstraint(
        name=f"deal_{prefix}_budget",
        violation_error_message=f"The {prefix} price needs a currency and an EUR amount.",
        condition=(
            models.Q(**{f"{price}__isnull": True, currency: ""})
            | (
                models.Q(**{f"{price}__isnull": False, currency: Currency.EUR})
                & models.Q(**{price_eur: models.F(price)})
            )
            | (
                models.Q(**{f"{price}__isnull": False})
                & ~models.Q(**{currency: ""})
                & ~models.Q(**{currency: Currency.EUR})
                & models.Q(**{f"{price_eur}__isnull": False})
            )
        ),
    )


class CampaignCreator(models.Model):
    """One creator inside one campaign. Price and stage belong here, not on the profile."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.PROTECT,
        related_name="deals",
    )
    creator = models.ForeignKey(
        "creators.Creator",
        on_delete=models.PROTECT,
        related_name="deals",
    )
    stage = models.CharField(
        max_length=32,
        choices=Stage.choices,
        default=Stage.SHORTLISTED,
    )
    fit_notes = models.TextField(
        blank=True,
        help_text="Why this profile fits the brief.",
    )
    deliverables = models.JSONField(default=list, blank=True)
    deliverables_notes = models.TextField(blank=True)
    assigned_to = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="outreach owner",
    )
    email_outreached = models.CharField(max_length=150, blank=True)
    sent_date = models.DateField(null=True, blank=True)
    fx_lock_date = models.DateField(null=True, blank=True, verbose_name="FX lock date")
    creator_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="What we pay the creator. The client never sees this.",
    )
    creator_currency = models.CharField(
        max_length=8,
        choices=Currency.choices,
        blank=True,
        verbose_name="creator currency",
    )
    creator_price_eur = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Same as the creator price when the currency is EUR.",
        verbose_name="creator price in EUR",
    )
    client_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="What the client pays us.",
    )
    client_currency = models.CharField(
        max_length=8,
        choices=Currency.choices,
        blank=True,
        verbose_name="client currency",
    )
    client_price_eur = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Same as the client price when the currency is EUR.",
        verbose_name="client price in EUR",
    )
    margin_eur = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        editable=False,
        help_text="Client EUR minus creator EUR. Calculated on save.",
        verbose_name="margin in EUR",
    )
    date_confirmed = models.DateField(
        null=True,
        blank=True,
        verbose_name="confirmed on",
    )
    client_status = models.CharField(
        max_length=16,
        choices=Decision.choices,
        blank=True,
        verbose_name="client answer",
    )
    client_remarks = models.TextField(blank=True)
    added_by = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "campaign_creators"
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "creator"],
                name="deal_campaign_creator_uniq",
                violation_error_message="This creator is already on that campaign.",
            ),
            models.CheckConstraint(
                condition=models.Q(stage__in=Stage.values),
                name="deal_stage_known",
            ),
            models.CheckConstraint(
                condition=models.Q(client_status="")
                | models.Q(client_status__in=Decision.values),
                name="deal_client_status_known",
            ),
            budget_constraint("creator"),
            budget_constraint("client"),
        ]

    def __str__(self):
        return f"{self.creator} · {self.campaign.client_name}"

    def clean(self):
        super().clean()
        self.fit_notes = (self.fit_notes or "").strip()
        self.deliverables_notes = (self.deliverables_notes or "").strip()
        self.client_remarks = (self.client_remarks or "").strip()
        self.assigned_to = " ".join((self.assigned_to or "").split())
        self.added_by = " ".join((self.added_by or "").split())
        self.email_outreached = " ".join((self.email_outreached or "").split())
        self.deliverables = cleaned("deliverables", clean_string_list, self.deliverables)
        errors = {}
        errors.update(apply_budget(self, "creator"))
        errors.update(apply_budget(self, "client"))
        if errors:
            raise ValidationError(errors)
        if self.creator_price_eur is None or self.client_price_eur is None:
            self.margin_eur = None
        else:
            self.margin_eur = self.client_price_eur - self.creator_price_eur
