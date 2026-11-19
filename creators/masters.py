"""Shared name cleanup for country, language, and deliverable masters."""


def folded(value):
    return " ".join(str(value or "").split())


def fold_key(value):
    return folded(value).casefold()


def choose_label(spellings):
    """Keep the spelling that appears most often. Ties keep the first one."""
    counts = {}
    order = []
    for spelling in spellings:
        if spelling not in counts:
            order.append(spelling)
            counts[spelling] = 0
        counts[spelling] += 1
    best = order[0]
    for spelling in order[1:]:
        if counts[spelling] > counts[best]:
            best = spelling
    return best


def group_names(values):
    """Map a case-folded key to one display name. Blanks are left out."""
    groups = {}
    for value in values:
        text = folded(value)
        if not text:
            continue
        groups.setdefault(fold_key(text), []).append(text)
    return {key: choose_label(spellings) for key, spellings in groups.items()}


def lookup_named(model, name):
    """Return the master row for this name, creating it when the list has no match."""
    text = folded(name)[:120]
    if not text:
        return None
    existing = model.objects.filter(name__iexact=text).first()
    if existing:
        return existing
    return model.objects.create(name=text)
