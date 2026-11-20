"""Client briefs, the deal for each creator, the outreach log, and client review links."""

import secrets
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone

from creators.choices import Currency, Platform
from creators.lists import clean_string_list, cleaned


class CampaignStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PRE_CAMPAIGN = "pre_campaign", "Pre-campaign"
    SCOUTING = "scouting", "Scouting"
    OUTREACH = "outreach", "Outreach"
    ACTIVE = "active", "Active"
    CLIENT_SHARING = "client_sharing", "Client sharing"
    AWAITING_PAYMENT = "awaiting_payment", "Awaiting payment"
    ON_HOLD = "on_hold", "On hold"
    UNRESPONSIVE = "unresponsive", "Unresponsive"
    CANCELLED = "cancelled", "Cancelled"
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
    country_market = models.ManyToManyField(
        "creators.Country",
        blank=True,
        related_name="campaigns",
        verbose_name="markets",
        help_text="Countries this brief is recruiting in.",
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
    client_poc_name = models.CharField(max_length=150, blank=True, verbose_name="client contact")
    team_lead = models.CharField(max_length=150, blank=True)
    poc = models.CharField(max_length=150, blank=True, verbose_name="POC")
    second_poc = models.CharField(max_length=150, blank=True, verbose_name="second POC")
    scouting_team = models.CharField(max_length=250, blank=True)
    start_date = models.DateField(null=True, blank=True)
    deadline = models.DateField(null=True, blank=True, verbose_name="campaign deadline")
    last_update_on = models.DateField(null=True, blank=True, verbose_name="last update")
    budget_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        verbose_name="budget",
    )
    budget_currency = models.CharField(
        max_length=8,
        choices=Currency.choices,
        blank=True,
        verbose_name="budget currency",
    )
    budget_eur = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        verbose_name="budget in EUR",
    )
    notes = models.TextField(blank=True)
    working_sheet = models.CharField(max_length=250, blank=True)
    cf_list = models.CharField(max_length=250, blank=True, verbose_name="CF list")
    priority = models.BooleanField(null=True, blank=True)
    list_submitted = models.BooleanField(null=True, blank=True)
    ready_for_dev = models.BooleanField(null=True, blank=True, verbose_name="ready for the team")
    age_range = models.CharField(max_length=80, blank=True)
    view_consistency = models.CharField(max_length=80, blank=True)
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
        self.client_poc_name = " ".join((self.client_poc_name or "").split())
        self.team_lead = " ".join((self.team_lead or "").split())
        self.poc = " ".join((self.poc or "").split())
        self.second_poc = " ".join((self.second_poc or "").split())
        self.scouting_team = " ".join((self.scouting_team or "").split())
        self.working_sheet = " ".join((self.working_sheet or "").split())
        self.cf_list = " ".join((self.cf_list or "").split())
        self.age_range = " ".join((self.age_range or "").split())
        self.view_consistency = " ".join((self.view_consistency or "").split())
        self.notes = (self.notes or "").strip()
        self.remarks_brief = (self.remarks_brief or "").strip()
        if self.budget_amount is None:
            self.budget_currency = ""
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
        errors = {}
        errors.update(apply_budget(self, "creator"))
        errors.update(apply_budget(self, "client"))
        if errors:
            raise ValidationError(errors)
        if self.creator_price_eur is None or self.client_price_eur is None:
            self.margin_eur = None
        else:
            self.margin_eur = self.client_price_eur - self.creator_price_eur


class CampaignCreatorDeliverable(models.Model):
    """The deliverable name as it was when this creator was added to the campaign."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign_creator = models.ForeignKey(
        CampaignCreator,
        on_delete=models.CASCADE,
        related_name="deliverable_lines",
        verbose_name="deal",
    )
    deliverable_type = models.ForeignKey(
        "creators.DeliverableType",
        on_delete=models.PROTECT,
        related_name="deal_lines",
        verbose_name="deliverable",
    )
    name = models.CharField(max_length=120)

    class Meta:
        db_table = "campaign_creator_deliverables"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["campaign_creator", "deliverable_type"],
                name="deal_deliverable_uniq",
                violation_error_message="This deliverable is already on that creator.",
            ),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        self.name = " ".join((self.name or "").split())
        if self.deliverable_type_id and not self.name:
            self.name = self.deliverable_type.name


class Channel(models.TextChoices):
    EMAIL = "email", "Email"
    INSTAGRAM_DM = "instagram_dm", "Instagram DM"
    TIKTOK_DM = "tiktok_dm", "TikTok DM"
    YOUTUBE = "youtube", "YouTube"
    WHATSAPP = "whatsapp", "WhatsApp"
    OTHER = "other", "Other"


class Direction(models.TextChoices):
    SENT = "sent", "Sent"
    RECEIVED = "received", "Received"


class OutreachStatus(models.TextChoices):
    """One row, one moment in the conversation. The footer of the design lists these seven."""

    SENT = "sent", "Sent"
    FOLLOW_UP = "follow_up", "Follow-up"
    REPLIED = "replied", "Replied"
    NEGOTIATING = "negotiating", "Negotiating"
    CONFIRMED = "confirmed", "Confirmed"
    NOT_INTERESTED = "not_interested", "Not interested"
    UNRESPONSIVE = "unresponsive", "Unresponsive"


class ShareStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SENT = "sent", "Sent"
    VIEWED = "viewed", "Viewed"
    COMPLETED = "completed", "Completed"


def prices_have_currency(name, currency, *prices):
    """A quote is either empty, or it has a price and a currency from the list."""
    empty = {currency: "", **{f"{price}__isnull": True for price in prices}}
    priced = models.Q(**{f"{prices[0]}__isnull": False})
    for price in prices[1:]:
        priced |= models.Q(**{f"{price}__isnull": False})
    return models.CheckConstraint(
        name=name,
        violation_error_message="A price needs a currency.",
        condition=models.Q(**empty) | (priced & models.Q(**{f"{currency}__in": Currency.values})),
    )


def new_share_token():
    return secrets.token_urlsafe(18)


class Outreach(models.Model):
    """One message, quote, or follow-up on a deal. A new price is a new row."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign_creator = models.ForeignKey(
        CampaignCreator,
        on_delete=models.PROTECT,
        related_name="messages",
        verbose_name="deal",
    )
    channel = models.CharField(max_length=32, choices=Channel.choices)
    direction = models.CharField(
        max_length=16,
        choices=Direction.choices,
        default=Direction.SENT,
    )
    outreach_status = models.CharField(
        max_length=32,
        choices=OutreachStatus.choices,
        default=OutreachStatus.SENT,
        db_index=True,
        verbose_name="status",
    )
    message_summary = models.TextField(
        blank=True,
        help_text="What was said. Leave blank when this row is only a price.",
        verbose_name="summary",
    )
    contact_email = models.EmailField(
        blank=True,
        help_text="Address used for this message. A DM can leave this empty.",
        verbose_name="address used",
    )
    quoted_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="The creator's ask. The next quote is a new row.",
        verbose_name="creator's ask",
    )
    offered_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Our counter-offer on this message.",
        verbose_name="our offer",
    )
    currency = models.CharField(max_length=8, choices=Currency.choices, blank=True)
    next_followup_date = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        help_text="When to remind the outreach owner. How many follow-ups end the thread is not decided yet.",
        verbose_name="next follow-up",
    )
    sent_by = models.CharField(max_length=150, blank=True, verbose_name="team member")
    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this message was sent or received.",
        verbose_name="when",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "outreach"
        ordering = ["-sent_at", "-created_at"]
        verbose_name = "outreach message"
        verbose_name_plural = "outreach"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(channel__in=Channel.values),
                name="outreach_channel_known",
            ),
            models.CheckConstraint(
                condition=models.Q(direction__in=Direction.values),
                name="outreach_direction_known",
            ),
            models.CheckConstraint(
                condition=models.Q(outreach_status__in=OutreachStatus.values),
                name="outreach_status_known",
            ),
            prices_have_currency("outreach_price_has_currency", "currency", "quoted_price", "offered_price"),
        ]

    def __str__(self):
        return f"{self.campaign_creator} · {self.get_outreach_status_display()}"

    def clean(self):
        super().clean()
        self.message_summary = (self.message_summary or "").strip()
        self.contact_email = (self.contact_email or "").strip()
        self.sent_by = " ".join((self.sent_by or "").split())
        has_price = self.quoted_price is not None or self.offered_price is not None
        if not has_price:
            self.currency = ""
            return
        if not self.currency:
            raise ValidationError({"currency": "Choose a currency when a price is set."})

    def save(self, *args, **kwargs):
        previous_status = None
        if self.pk:
            previous_status = (
                Outreach.objects.filter(pk=self.pk)
                .values_list("outreach_status", flat=True)
                .first()
            )
        with transaction.atomic():
            super().save(*args, **kwargs)
            self.copy_confirmed_eur_price(previous_status)

    def copy_confirmed_eur_price(self, previous_status):
        """Copy a newly confirmed EUR quote onto the deal. Later saves leave that price alone."""
        if previous_status == OutreachStatus.CONFIRMED:
            return
        if self.outreach_status != OutreachStatus.CONFIRMED:
            return
        if self.currency != Currency.EUR:
            return
        price = self.offered_price if self.offered_price is not None else self.quoted_price
        if price is None:
            return
        deal = self.campaign_creator
        deal.creator_price = price
        deal.creator_currency = Currency.EUR
        if apply_budget(deal, "creator"):
            return
        if deal.creator_price_eur is None or deal.client_price_eur is None:
            deal.margin_eur = None
        else:
            deal.margin_eur = deal.client_price_eur - deal.creator_price_eur
        deal.save(
            update_fields=[
                "creator_price",
                "creator_currency",
                "creator_price_eur",
                "margin_eur",
                "updated_at",
            ]
        )


class ClientShare(models.Model):
    """One review link for a campaign. The token is the secret in that link."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.PROTECT,
        related_name="shares",
    )
    share_token = models.CharField(
        max_length=64,
        unique=True,
        default=new_share_token,
        editable=False,
        verbose_name="link code",
    )
    title = models.CharField(
        max_length=200,
        help_text="Round name, for example Round 1.",
        verbose_name="round",
    )
    sent_to_email = models.EmailField(
        blank=True,
        verbose_name="client contact",
    )
    sent_by = models.CharField(max_length=150, blank=True, verbose_name="team member")
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name="sent")
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the link stops working. How many days it stays open is not decided yet.",
        verbose_name="expires",
    )
    status = models.CharField(
        max_length=16,
        choices=ShareStatus.choices,
        default=ShareStatus.DRAFT,
        db_index=True,
    )
    submitted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="client finished",
    )

    class Meta:
        db_table = "client_shares"
        ordering = ["-sent_at", "title"]
        verbose_name = "client link"
        verbose_name_plural = "client links"
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(share_token=""),
                name="share_token_present",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=ShareStatus.values),
                name="share_status_known",
            ),
            models.CheckConstraint(
                condition=models.Q(status=ShareStatus.DRAFT) | models.Q(sent_at__isnull=False),
                name="share_sent_has_time",
                violation_error_message="A sent link needs the time it was sent.",
            ),
            models.CheckConstraint(
                condition=~models.Q(status=ShareStatus.COMPLETED) | models.Q(submitted_at__isnull=False),
                name="share_completed_has_time",
                violation_error_message="A completed link needs the time the client finished.",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(expires_at__isnull=True)
                    | models.Q(sent_at__isnull=True)
                    | models.Q(expires_at__gt=models.F("sent_at"))
                ),
                name="share_expires_after_sent",
                violation_error_message="The link has to expire after it is sent.",
            ),
        ]

    def __str__(self):
        return f"{self.campaign.client_name} · {self.title}"

    def clean(self):
        super().clean()
        self.title = " ".join((self.title or "").split())
        self.sent_to_email = (self.sent_to_email or "").strip()
        self.sent_by = " ".join((self.sent_by or "").split())
        if not self.share_token:
            self.share_token = new_share_token()
        now = timezone.now()
        if self.status != ShareStatus.DRAFT and self.sent_at is None:
            self.sent_at = now
        if self.status == ShareStatus.COMPLETED and self.submitted_at is None:
            self.submitted_at = now
        errors = {}
        if self.status != ShareStatus.DRAFT and not self.sent_to_email:
            errors["sent_to_email"] = "Add the client contact before sending the link."
        if self.expires_at and self.sent_at and self.expires_at <= self.sent_at:
            errors["expires_at"] = "The link has to expire after it is sent."
        if errors:
            raise ValidationError(errors)


class ClientShareItem(models.Model):
    """One creator on a client link. The creator's price and our margin are never stored here."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client_share = models.ForeignKey(
        ClientShare,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="link",
    )
    campaign_creator = models.ForeignKey(
        CampaignCreator,
        on_delete=models.PROTECT,
        related_name="share_items",
        verbose_name="creator",
    )
    client_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Shown to the client. Copied from the deal when left empty.",
        verbose_name="price shown",
    )
    client_currency = models.CharField(
        max_length=8,
        choices=Currency.choices,
        blank=True,
        verbose_name="currency",
    )
    decision = models.CharField(
        max_length=16,
        choices=Decision.choices,
        default=Decision.PENDING,
    )
    client_remarks = models.TextField(blank=True, verbose_name="client comment")
    decided_at = models.DateTimeField(null=True, blank=True, verbose_name="answered")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "client_share_items"
        ordering = ["created_at"]
        verbose_name = "creator on a link"
        verbose_name_plural = "creators on a link"
        constraints = [
            models.UniqueConstraint(
                fields=["client_share", "campaign_creator"],
                name="share_item_creator_uniq",
                violation_error_message="This creator is already on that link.",
            ),
            models.CheckConstraint(
                condition=models.Q(decision__in=Decision.values),
                name="share_item_decision_known",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(decision=Decision.PENDING, decided_at__isnull=True)
                    | (
                        models.Q(decision__in=[Decision.ACCEPTED, Decision.REJECTED])
                        & models.Q(decided_at__isnull=False)
                    )
                ),
                name="share_item_decision_time",
                violation_error_message="An answer needs the time it was given. Pending has no time.",
            ),
            prices_have_currency(
                "share_item_price_has_currency",
                "client_currency",
                "client_price",
            ),
        ]

    def __str__(self):
        return f"{self.campaign_creator.creator} · {self.get_decision_display()}"

    def clean(self):
        super().clean()
        self.client_remarks = (self.client_remarks or "").strip()
        if self.campaign_creator_id and self.client_price is None:
            deal = self.campaign_creator
            if deal.client_price is not None:
                self.client_price = deal.client_price
                self.client_currency = deal.client_currency
        if self.client_share_id and self.campaign_creator.campaign_id != self.client_share.campaign_id:
            raise ValidationError(
                {"campaign_creator": "This creator is not on the campaign for this link."}
            )
        if self.decision == Decision.PENDING:
            self.decided_at = None
        elif self.decided_at is None:
            self.decided_at = timezone.now()
        if self.client_price is None:
            self.client_currency = ""
        elif not self.client_currency:
            raise ValidationError({"client_currency": "Choose a currency when a price is set."})

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.copy_answer_to_deal()

    def copy_answer_to_deal(self):
        """The deal keeps the latest accept or reject, so the pipeline does not read the link."""
        if self.decision == Decision.PENDING or self.decided_at is None:
            return
        newer = (
            ClientShareItem.objects.filter(
                campaign_creator_id=self.campaign_creator_id,
                decided_at__gt=self.decided_at,
            )
            .exclude(pk=self.pk)
            .exists()
        )
        if newer:
            return
        CampaignCreator.objects.filter(pk=self.campaign_creator_id).update(
            client_status=self.decision,
            client_remarks=self.client_remarks,
        )
