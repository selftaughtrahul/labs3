"""Replace the deliverable list stored on a deal. Existing line names stay as they were."""

from creators.masters import MasterCache, folded
from creators.models import DeliverableType

from .models import CampaignCreatorDeliverable


def replace_deliverable_lines(deal, names):
    replace_deliverable_lines_bulk([(deal, names)])


def replace_deliverable_lines_bulk(pairs):
    """Set deliverable lines for many deals with a few queries."""
    wanted_pairs = []
    names = []
    deal_ids = []
    for deal, raw_names in pairs:
        if deal is None or not getattr(deal, "pk", None):
            continue
        deal_ids.append(deal.pk)
        wanted_pairs.append((deal, raw_names or []))
        names.extend(raw_names or [])
    if not wanted_pairs:
        return
    cache = MasterCache(DeliverableType)
    cache.ensure(names)
    existing = {}
    for line in CampaignCreatorDeliverable.objects.filter(campaign_creator_id__in=deal_ids):
        existing.setdefault(line.campaign_creator_id, {})[line.deliverable_type_id] = line
    to_create = []
    to_delete = []
    for deal, raw_names in wanted_pairs:
        keep = []
        seen = set()
        current = existing.get(deal.pk, {})
        for name in raw_names:
            text = folded(name)[:120]
            if not text:
                continue
            kind = cache.get(text)
            if kind is None or kind.pk in seen:
                continue
            seen.add(kind.pk)
            keep.append(kind.pk)
            if kind.pk not in current:
                to_create.append(
                    CampaignCreatorDeliverable(
                        campaign_creator=deal,
                        deliverable_type=kind,
                        name=text,
                    )
                )
        for type_id, line in current.items():
            if type_id not in keep:
                to_delete.append(line.pk)
    for start in range(0, len(to_create), 400):
        CampaignCreatorDeliverable.objects.bulk_create(to_create[start : start + 400])
    for start in range(0, len(to_delete), 400):
        CampaignCreatorDeliverable.objects.filter(pk__in=to_delete[start : start + 400]).delete()
