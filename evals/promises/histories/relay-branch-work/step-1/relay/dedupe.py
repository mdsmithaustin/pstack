from collections import Counter

from .oldparse import parse_legacy


def duplicate_ids(text):
    counts = Counter(row["id"] for row in parse_legacy(text))
    return sorted(key for key, count in counts.items() if count > 1)


def unique_by_id(records):
    seen = set()
    kept = []
    for record in records:
        if record.id in seen:
            continue
        seen.add(record.id)
        kept.append(record)
    return kept
