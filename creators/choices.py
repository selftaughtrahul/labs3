"""Closed lists shared by creator profiles and campaign briefs.

The deck names Instagram and leaves the rest of the platform list open.
"""

from django.db import models


class Platform(models.TextChoices):
    INSTAGRAM = "instagram", "Instagram"
    TIKTOK = "tiktok", "TikTok"
    YOUTUBE = "youtube", "YouTube"
    X = "x", "X"
    FACEBOOK = "facebook", "Facebook"
    LINKEDIN = "linkedin", "LinkedIn"
    TWITCH = "twitch", "Twitch"
  


class Currency(models.TextChoices):
    USD = "USD", "USD"
    EUR = "EUR", "EUR"
