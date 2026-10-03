from collections import Counter


def count_by_team(rows):
    counts = Counter(row["team"] for row in rows)
    return sorted(counts.items())
