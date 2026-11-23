"""Point duplicate deliverable names at one keeper id, then drop unused rows."""

import json

from campaigns.models import CampaignCreatorDeliverable
from creators.masters import DELIVERABLE_GROUPS, fold_key
from creators.models import CreatorRate, DeliverableType

# Rename keepers in place. Leftover "TikTok Video" (id 87) is renamed first so this stays unique.
DELIVERABLE_RENAMES = tuple(
    (alias, canonical)
    for canonical, aliases in DELIVERABLE_GROUPS.items()
    for alias in aliases
    if alias != canonical
)

CLASH_NAME_RENAMES = (
    ("TikTok Video", "TikTok Video (unmerged)"),
)

KEEPER_MAP = {
    87: 3,
    103: 11,
    90: 63,
    79: 64,
    82: 8,
    41: 15,
    43: 15,
    98: 15,
}

SPLIT_KEEP_ID = 26
SPLIT_DROP_ID = 28
SPLIT_NAME = "Crossposted to YT, IG"


def compact(stdout=None, keeper_map=None, split_keep_id=SPLIT_KEEP_ID, split_drop_id=SPLIT_DROP_ID):
    mapping = dict(KEEPER_MAP if keeper_map is None else keeper_map)
    moved_deals = 0
    dropped_deals = 0
    moved_rates = 0
    skipped_rates = 0
    renamed = 0
    deleted = 0
    _log(stdout, "Compacting deliverable types")

    for old_id, keep_id in mapping.items():
        if old_id == keep_id:
            continue
        if not DeliverableType.objects.filter(pk__in=[old_id, keep_id]).count() == 2:
            continue
        d_moved, d_dropped = _retarget_deals(old_id, keep_id)
        r_moved, r_skipped = _retarget_rates(old_id, keep_id, stdout)
        moved_deals += d_moved
        dropped_deals += d_dropped
        moved_rates += r_moved
        skipped_rates += r_skipped
        _log(
            stdout,
            f"Map {old_id} -> {keep_id}: deals {d_moved} moved, {d_dropped} dropped; "
            f"rates {r_moved} moved, {r_skipped} skipped",
        )

    if _fix_split_quote(split_keep_id, split_drop_id, stdout):
        renamed = 1

    old_ids = set(mapping) | {split_drop_id}
    deleted = _delete_unused(old_ids, stdout)
    return {
        "moved_deals": moved_deals,
        "dropped_deals": dropped_deals,
        "moved_rates": moved_rates,
        "skipped_rates": skipped_rates,
        "renamed": renamed,
        "deleted": deleted,
    }


def dump_affected(path, stdout=None):
    """Write deal lines and rate links for names that will merge or rename."""
    names = set()
    for canonical, aliases in DELIVERABLE_GROUPS.items():
        names.add(canonical)
        names.update(aliases)
    types = list(DeliverableType.objects.all())
    wanted_ids = [
        row.pk
        for row in types
        if any(fold_key(row.name) == fold_key(name) for name in names)
    ]
    through = CreatorRate.deliverables.through
    payload = {
        "types": list(DeliverableType.objects.filter(pk__in=wanted_ids).values("id", "name")),
        "deal_lines": list(
            CampaignCreatorDeliverable.objects.filter(deliverable_type_id__in=wanted_ids).values(
                "id", "campaign_creator_id", "deliverable_type_id", "name"
            )
        ),
        "rate_links": list(
            through.objects.filter(deliverabletype_id__in=wanted_ids).values(
                "creatorrate_id", "deliverabletype_id"
            )
        ),
        "bundle_keys": list(
            CreatorRate.objects.filter(deliverables__in=wanted_ids)
            .distinct()
            .values("id", "creator_id", "bundle_key", "price", "currency")
        ),
    }
    if path:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, default=str)
        _log(stdout, f"Wrote {path}")
    return payload


def consolidate(stdout=None):
    """Rename keepers, merge quantity/spelling duplicates, skip rate price clashes."""
    moved_deals = 0
    dropped_deals = 0
    moved_rates = 0
    skipped_rates = 0
    renamed = 0
    deleted = 0
    _log(stdout, "Consolidating deliverable types")
    for old_name, new_name in CLASH_NAME_RENAMES:
        row = DeliverableType.objects.filter(name__iexact=old_name).first()
        other = DeliverableType.objects.filter(name__iexact="TT Video").first()
        if row is None or other is None or row.pk == other.pk:
            continue
        if DeliverableType.objects.filter(name__iexact=new_name).exists():
            continue
        _log(stdout, f"Rename leftover {row.pk} {row.name!r} to {new_name!r}")
        row.name = new_name
        row.save(update_fields=["name"])
        renamed += 1
    for old_name, new_name in DELIVERABLE_RENAMES:
        row = DeliverableType.objects.filter(name__iexact=old_name).first()
        if row is None:
            continue
        taken = DeliverableType.objects.filter(name__iexact=new_name).exclude(pk=row.pk).first()
        if taken is None:
            if row.name == new_name:
                continue
            _log(stdout, f"Rename {row.pk} {row.name!r} to {new_name!r}")
            row.name = new_name
            row.save(update_fields=["name"])
            renamed += 1
            continue
        d_moved, d_dropped = _retarget_deals(row.pk, taken.pk)
        r_moved, r_skipped = _retarget_rates(row.pk, taken.pk, stdout)
        moved_deals += d_moved
        dropped_deals += d_dropped
        moved_rates += r_moved
        skipped_rates += r_skipped
        _log(
            stdout,
            f"Map {row.pk} {old_name!r} -> {taken.pk} {new_name!r}: "
            f"deals {d_moved} moved, {d_dropped} dropped; rates {r_moved} moved, {r_skipped} skipped",
        )
        deleted += _delete_unused({row.pk}, stdout)
    return {
        "moved_deals": moved_deals,
        "dropped_deals": dropped_deals,
        "moved_rates": moved_rates,
        "skipped_rates": skipped_rates,
        "renamed": renamed,
        "deleted": deleted,
    }


def _retarget_deals(old_id, keep_id):
    already = set(
        CampaignCreatorDeliverable.objects.filter(deliverable_type_id=keep_id).values_list(
            "campaign_creator_id", flat=True
        )
    )
    extras = CampaignCreatorDeliverable.objects.filter(
        deliverable_type_id=old_id,
        campaign_creator_id__in=already,
    )
    dropped = extras.count()
    extras.delete()
    moved = CampaignCreatorDeliverable.objects.filter(deliverable_type_id=old_id).update(
        deliverable_type_id=keep_id
    )
    return moved, dropped


def _retarget_rates(old_id, keep_id, stdout):
    through = CreatorRate.deliverables.through
    moved = 0
    skipped = 0
    rate_ids = list(
        through.objects.filter(deliverabletype_id=old_id).values_list("creatorrate_id", flat=True)
    )
    if not rate_ids:
        return 0, 0
    rates = list(CreatorRate.objects.filter(pk__in=rate_ids).prefetch_related("deliverables"))
    creator_ids = {rate.creator_id for rate in rates}
    keys_by_creator = {}
    rates_by_id = {}
    for other in CreatorRate.objects.filter(creator_id__in=creator_ids).only(
        "id", "creator_id", "bundle_key", "price", "currency"
    ):
        rates_by_id[other.pk] = other
        keys_by_creator.setdefault(other.creator_id, {})[other.bundle_key] = other.pk
    drop_old = []
    rewrite_old = []
    new_keys = []
    for rate in rates:
        current = [item.pk for item in rate.deliverables.all()]
        wanted = []
        seen = set()
        for type_id in current:
            next_id = keep_id if type_id == old_id else type_id
            if next_id in seen:
                continue
            seen.add(next_id)
            wanted.append(next_id)
        wanted.sort()
        new_key = ",".join(str(type_id) for type_id in wanted)
        clash_id = keys_by_creator.get(rate.creator_id, {}).get(new_key)
        if clash_id and clash_id != rate.pk:
            skipped += 1
            clash = rates_by_id[clash_id]
            _log(
                stdout,
                f"Skip rate {rate.pk} {rate.price} {rate.currency} "
                f"({old_id} -> {keep_id}): creator already has "
                f"{clash.pk} {clash.price} {clash.currency}",
            )
            continue
        if keep_id in current:
            drop_old.append(rate.pk)
        else:
            rewrite_old.append(rate.pk)
        new_keys.append((rate.pk, new_key))
        keys_by_creator.setdefault(rate.creator_id, {})[new_key] = rate.pk
        moved += 1
    if drop_old:
        through.objects.filter(creatorrate_id__in=drop_old, deliverabletype_id=old_id).delete()
    if rewrite_old:
        through.objects.filter(creatorrate_id__in=rewrite_old, deliverabletype_id=old_id).update(
            deliverabletype_id=keep_id
        )
    if new_keys:
        keyed = {rate_id: new_key for rate_id, new_key in new_keys}
        changed = list(CreatorRate.objects.filter(pk__in=keyed))
        for rate in changed:
            rate.bundle_key = keyed[rate.pk]
        CreatorRate.objects.bulk_update(changed, ["bundle_key"], batch_size=400)
    return moved, skipped


def _fix_split_quote(keep_id, drop_id, stdout):
    keep = DeliverableType.objects.filter(pk=keep_id).first()
    drop = DeliverableType.objects.filter(pk=drop_id).first()
    if keep is None or drop is None:
        return False
    keep.name = SPLIT_NAME
    keep.save(update_fields=["name"])
    _log(stdout, f"Rename {keep_id} to {SPLIT_NAME!r}")
    _retarget_deals(drop_id, keep_id)
    CampaignCreatorDeliverable.objects.filter(
        deliverable_type_id=keep_id,
        name__in=['"Crossposted to YT', 'IG"', SPLIT_NAME],
    ).update(name=SPLIT_NAME)
    through = CreatorRate.deliverables.through
    for rate_id in through.objects.filter(deliverabletype_id=drop_id).values_list(
        "creatorrate_id", flat=True
    ):
        through.objects.filter(creatorrate_id=rate_id, deliverabletype_id=drop_id).delete()
        rate = CreatorRate.objects.get(pk=rate_id)
        key = ",".join(str(type_id) for type_id in rate.deliverable_ids())
        CreatorRate.objects.filter(pk=rate.pk).update(bundle_key=key)
    _log(stdout, f"Drop split fragment {drop_id}")
    return True


def _delete_unused(type_ids, stdout):
    deleted = 0
    through = CreatorRate.deliverables.through
    for type_id in sorted(type_ids):
        kind = DeliverableType.objects.filter(pk=type_id).first()
        if kind is None:
            continue
        deals = CampaignCreatorDeliverable.objects.filter(deliverable_type_id=type_id).count()
        rates = through.objects.filter(deliverabletype_id=type_id).count()
        if deals or rates:
            _log(stdout, f"Keep {type_id} {kind.name!r}: {rates} rates, {deals} deals still linked")
            continue
        _log(stdout, f"Delete unused {type_id} {kind.name!r}")
        kind.delete()
        deleted += 1
    return deleted


def _log(stdout, message):
    if stdout is not None:
        stdout.write(message)
        if hasattr(stdout, "flush"):
            stdout.flush()
