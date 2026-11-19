"""Replace the deliverable list stored on a deal. Existing line names stay as they were."""

from creators.masters import folded, lookup_named
from creators.models import DeliverableType

from .models import CampaignCreatorDeliverable


def replace_deliverable_lines(deal, names):
    wanted = []
    seen = set()
    for name in names or []:
        text = folded(name)[:120]
        if not text:
            continue
        kind = lookup_named(DeliverableType, text)
        if kind is None or kind.id in seen:
            continue
        seen.add(kind.id)
        wanted.append((kind, text))
    existing = {
        line.deliverable_type_id: line for line in deal.deliverable_lines.all()
    }
    keep = []
    for kind, text in wanted:
        keep.append(kind.id)
        if kind.id not in existing:
            CampaignCreatorDeliverable.objects.create(
                campaign_creator=deal,
                deliverable_type=kind,
                name=text,
            )
    deal.deliverable_lines.exclude(deliverable_type_id__in=keep).delete()
