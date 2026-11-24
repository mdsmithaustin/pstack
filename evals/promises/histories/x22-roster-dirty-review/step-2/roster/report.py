from collections import Counter


def count_by_team(rows):
    counts = Counter(row["team"] for row in rows)
    return sorted(counts.items())


def top_teams(rows, n):
    """The n largest teams, largest first. Teams with the same size keep name order."""
    counts = Counter(row["team"] for row in rows)
    ranked = sorted(counts.items(), key=lambda item: -item[1])
    return ranked[:n]
