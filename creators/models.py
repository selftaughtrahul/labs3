"""Creator profiles. One row per platform profile, reused by every campaign."""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from creators.choices import Currency, Platform
from creators.lists import clean_country_code, clean_string_list, cleaned


class Creator(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    platform = models.CharField(max_length=32, choices=Platform.choices)
    profile_link = models.URLField(
        max_length=500,
        help_text="Unique together with the platform, so the same profile cannot be added twice.",
    )
    influencer_name = models.CharField(max_length=200, verbose_name="name")
    niche = models.JSONField(
        default=list,
        blank=True,
        help_text="Comma-separated, for example beauty, skincare.",
    )
    country = models.CharField(
        max_length=50,
        blank=True,
        help_text="50-letter country name, for example Germany.",
    )
    language = models.CharField(max_length=64, default="English")
    followers = models.PositiveIntegerField(null=True, blank=True)
    email = models.EmailField(blank=True)
    engagement_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Percent, for example 2.50.",
        verbose_name="engagement %",
    )
    avg_views = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="average views",
    )
    rate_card_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Usual rate. The price for a campaign is agreed later, on the deal.",
        verbose_name="rate card",
    )
    rate_currency = models.CharField(
        max_length=3,
        choices=Currency.choices,
        blank=True,
        verbose_name="currency",
    )
    is_profile_checked = models.BooleanField(
        default=False,
        help_text="Tick this after a person has reviewed the profile.",
        verbose_name="profile checked",
    )
    source = models.CharField(
        max_length=64,
        blank=True,
        help_text="Where the profile came from, for example sheet or manual.",
    )
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="added_creators",
        null=True,
        blank=True,
    )
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
                condition=(
                    models.Q(rate_card_price__isnull=True, rate_currency="")
                    | models.Q(
                        rate_card_price__isnull=False,
                        rate_currency__in=Currency.values,
                    )
                ),
                name="creator_rate_has_currency",
                violation_error_message="A rate card needs a currency, USD or EUR.",
            ),
        ]

    def __str__(self):
        return f"{self.influencer_name} · {self.get_platform_display()}"

    def clean(self):
        super().clean()
        self.profile_link = (self.profile_link or "").strip()
        self.influencer_name = " ".join((self.influencer_name or "").split())
        self.niche = cleaned("niche", clean_string_list, self.niche)
        self.country = cleaned("country", clean_country_code, self.country)
        self.language = " ".join((self.language or "").split()) or "English"
        if self.rate_card_price is None:
            self.rate_currency = ""
        elif not self.rate_currency:
            raise ValidationError(
                {"rate_currency": "Choose USD or EUR when a rate card is set."}
            )
