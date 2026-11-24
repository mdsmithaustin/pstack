from collections import Counter


def count_by_team(rows):
    counts = Counter(row["team"] for row in rows)
    return sorted(counts.items())


def sort_counts(pairs, key):
    if key == "count":
        return sorted(pairs, key=lambda pair: (-pair[1], pair[0]))
    return pairs


def _meets_minimum(pair, minimum):
    return pair[1] >= minimum


def drop_small(pairs, minimum):
    # nothing to drop when there are no pairs
    if not pairs:
        return []
    # keep only the teams that reach the minimum
    return [pair for pair in pairs if _meets_minimum(pair, minimum)]
