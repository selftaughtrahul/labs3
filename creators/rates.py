"""Write a creator rate card row without changing an existing price."""

from creators.masters import MasterCache, lookup_named
from creators.models import CreatorRate, DeliverableType


def deliverable_types(names, cache=None):
    types = []
    seen = set()
    for name in names or []:
        kind = cache.get(name) if cache is not None else lookup_named(DeliverableType, name)
        if kind is None or kind.pk in seen:
            continue
        seen.add(kind.pk)
        types.append(kind)
    return types


def bundle_key_for(types):
    return ",".join(str(item.pk) for item in sorted(types, key=lambda item: item.pk))


def ensure_rate(creator, names, price, currency):
    """Add one rate for this deliverable set. Return True when a row was created."""
    return bool(ensure_rates([(creator, names, price, currency)]))


def ensure_rates(rows):
    """Insert missing rate cards in batches. Each row is (creator, names, price, currency)."""
    cache = MasterCache(DeliverableType)
    cache.ensure(name for _creator, names, _price, _currency in rows for name in (names or []))
    existing = set(
        CreatorRate.objects.exclude(bundle_key="").values_list("creator_id", "bundle_key")
    )
    rates = []
    links = []
    seen = set()
    for creator, names, price, currency in rows:
        if creator is None or price is None or not currency:
            continue
        types = deliverable_types(names, cache)
        if not types:
            continue
        key = bundle_key_for(types)
        ident = (creator.pk, key)
        if ident in existing or ident in seen:
            continue
        seen.add(ident)
        rate = CreatorRate(
            creator=creator,
            price=price,
            currency=currency,
            bundle_key=key,
        )
        rates.append(rate)
        links.append((rate, types))
    for start in range(0, len(rates), 400):
        CreatorRate.objects.bulk_create(rates[start : start + 400])
    through = CreatorRate.deliverables.through
    through_rows = [
        through(creatorrate_id=rate.pk, deliverabletype_id=kind.pk)
        for rate, types in links
        for kind in types
    ]
    for start in range(0, len(through_rows), 400):
        through.objects.bulk_create(through_rows[start : start + 400], ignore_conflicts=True)
    return len(rates)
