from collections import Counter


def count_by_team(rows):
    counts = Counter(row["team"] for row in rows)
    return sorted(counts.items())


def sort_counts(pairs, key):
    if key == "count":
        return sorted(pairs, key=lambda pair: (-pair[1], pair[0]))
    return pairs
