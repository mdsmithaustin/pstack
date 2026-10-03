from collections import Counter

from .oldparse import parse_legacy


def duplicate_ids(text):
    counts = Counter(row["id"] for row in parse_legacy(text))
    return sorted(key for key, count in counts.items() if count > 1)


def unique_by_id(records):
    ids = [record.id for record in records]
    return [record for index, record in enumerate(records) if record.id not in ids[1:index]]
