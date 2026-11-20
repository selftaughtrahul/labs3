"""Map sheet status spellings onto CampaignCreator.stage."""

import re

from campaigns.models import CampaignStatus, OutreachStatus, Stage


def folded_status(value) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().lower()).strip()


DEAL_STAGE_ALIASES = {
    "sent": Stage.CONTACTED,
    "contacted": Stage.CONTACTED,
    "follow up": Stage.FOLLOW_UP,
    "followup": Stage.FOLLOW_UP,
    "follow up 1": Stage.FOLLOW_UP,
    "follow up 2": Stage.FOLLOW_UP,
    "follow up 3": Stage.FOLLOW_UP,
    "replied": Stage.REPLIED,
    "negotiating": Stage.NEGOTIATING,
    "negotiation": Stage.NEGOTIATING,
    "verbal agreement": Stage.VERBAL_AGREEMENT,
    "confirmed": Stage.CONFIRMED,
    "shared with client": Stage.SHARED,
    "not interested": Stage.NOT_INTERESTED,
    "not available as of the moment": Stage.NOT_INTERESTED,
    "unresponsive": Stage.UNRESPONSIVE,
    "influencer unresponsive": Stage.UNRESPONSIVE,
    "invalid email email error": Stage.UNRESPONSIVE,
    "bounced": Stage.UNRESPONSIVE,
    "shortlisted": Stage.SHORTLISTED,
    "not started": Stage.NOT_STARTED,
    "in progress": Stage.IN_PROGRESS,
    "approved": Stage.APPROVED,
    "completed": Stage.COMPLETED,
    "cancelled": Stage.CANCELLED,
    "canceled": Stage.CANCELLED,
    "campaign declined": Stage.CANCELLED,
}

OUTREACH_FOR_STAGE = {
    Stage.CONTACTED: OutreachStatus.SENT,
    Stage.FOLLOW_UP: OutreachStatus.FOLLOW_UP,
    Stage.REPLIED: OutreachStatus.REPLIED,
    Stage.NEGOTIATING: OutreachStatus.NEGOTIATING,
    Stage.CONFIRMED: OutreachStatus.CONFIRMED,
    Stage.NOT_INTERESTED: OutreachStatus.NOT_INTERESTED,
    Stage.UNRESPONSIVE: OutreachStatus.UNRESPONSIVE,
}

CAMPAIGN_STATUS_ALIASES = {
    "draft": CampaignStatus.DRAFT,
    "active": CampaignStatus.ACTIVE,
    "in progress": CampaignStatus.ACTIVE,
    "completed": CampaignStatus.COMPLETED,
    "closed": CampaignStatus.COMPLETED,
    "pending": CampaignStatus.PENDING,
    "on hold": CampaignStatus.ON_HOLD,
    "cancelled": CampaignStatus.CANCELLED,
    "canceled": CampaignStatus.CANCELLED,
    "declined": CampaignStatus.CANCELLED,
    "not started": CampaignStatus.NOT_STARTED,
    "unresponsive": CampaignStatus.UNRESPONSIVE,
    "paused": CampaignStatus.PAUSED,
    "prospecting paused": CampaignStatus.PROSPECTING_PAUSED,
    "pre campaign": CampaignStatus.PRE_CAMPAIGN,
    "pre-campaign": CampaignStatus.PRE_CAMPAIGN,
    "pre- campaign": CampaignStatus.PRE_CAMPAIGN,
    "contract pending": CampaignStatus.CONTRACT_PHASE,
    "contract phase": CampaignStatus.CONTRACT_PHASE,
    "awaiting payment": CampaignStatus.AWAITING_PAYMENT,
}


def map_deal_stage(value, default=""):
    """Return (stage, outreach_status, known).

    A blank value uses default. An unknown spelling keeps shortlisted and
    known=False so the import can list it.
    """
    key = folded_status(value) or folded_status(default)
    if not key:
        return Stage.SHORTLISTED, "", False
    stage = DEAL_STAGE_ALIASES.get(key)
    if stage is None:
        return Stage.SHORTLISTED, "", False
    return stage, OUTREACH_FOR_STAGE.get(stage, ""), True


def map_campaign_status(value):
    return CAMPAIGN_STATUS_ALIASES.get(folded_status(value), "")
