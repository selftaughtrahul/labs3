"""Closed lists shared by creator profiles and campaign briefs."""

from django.db import models


class Platform(models.TextChoices):
    INSTAGRAM = "instagram", "Instagram"
    TIKTOK = "tiktok", "TikTok"
    YOUTUBE = "youtube", "YouTube"
    X = "x", "X"
    FACEBOOK = "facebook", "Facebook"
    LINKEDIN = "linkedin", "LinkedIn"
    TWITCH = "twitch", "Twitch"
    KICK = "kick", "Kick"


class Currency(models.TextChoices):
    USD = "USD", "USD"
    EUR = "EUR", "EUR"
    GBP = "GBP", "GBP"
    INR = "INR", "INR"
    BRL = "BRL", "BRL"
    AUD = "AUD", "AUD"
    PLN = "PLN", "PLN"
    PHP = "PHP", "PHP"
    SGD = "SGD", "SGD"
    CHF = "CHF", "CHF"
    USDT = "USDT", "USDT"
    AED = "AED", "AED"
    PKR = "PKR", "PKR"
    TRY = "TRY", "TRY"
    MXN = "MXN", "MXN"
    CAD = "CAD", "CAD"
    COP = "COP", "COP"
    SEK = "SEK", "SEK"
    ARS = "ARS", "ARS"


class Tier(models.TextChoices):
    NANO = "nano", "Nano"
    MICRO = "micro", "Micro"
    MID = "mid_tier", "Mid-Tier"
    MACRO = "macro", "Macro"
    MEGA = "mega", "Mega"
    USER = "user", "User"
