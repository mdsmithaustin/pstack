from collections import Counter


def count_by_team(rows):
    if rows is None:
        return []
    counts = Counter(row["team"] for row in rows)
    return sorted(counts.items())


def sort_counts(pairs, key):
    # check which key the caller asked for
    if key == "count":
        # biggest teams first, ties by team name
        return sorted(pairs, key=lambda pair: (-pair[1], pair[0]))
    # otherwise keep the team order
    return pairs
