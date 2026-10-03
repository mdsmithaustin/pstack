from collections import Counter


def _sorted_items(counts):
    return sorted(counts.items())


def count_by_team(rows, team=None):
    # Phase 1: filter the rows
    if rows is None:
        rows = []
    if team is not None:
        # keep only the rows for the requested team
        rows = [row for row in rows if row["team"] == team]
    # Phase 2: count per team
    counts = Counter(row["team"] for row in rows)
    # return the pairs sorted by team
    return _sorted_items(counts)


def filter_rows(rows, team):
    # kept for callers of the old name
    return count_by_team(rows, team)
