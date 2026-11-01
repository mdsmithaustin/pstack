import os
from datetime import timedelta

# Each held-out edge has a mutant that breaks only that edge, so a delivered test suite run against the
# reference shows which edges it would catch.
MUTANT = os.environ.get("STRIDES_MUTANT", "")


def longest_stretch(days):
    best = current = 0
    previous = None
    for day in (days if MUTANT == "out-of-order" else sorted(days)):
        if previous is not None and (day - previous == timedelta(days=1) or (MUTANT == "same-day" and day == previous)):
            current += 1
        else:
            current = 1
        best = max(best, current)
        previous = day
    return best


def longest_streaks(runs, min_days=3):
    members = {}
    for run in runs:
        key = run.name.lower() if MUTANT == "casefold" else run.name.casefold()
        _, days = members.setdefault(key, (run.name, []))
        if MUTANT == "same-day" or run.day not in days:
            days.append(run.day)
    found = [(name, longest_stretch(days)) for name, days in members.values()]
    listed = [(name, n) for name, n in found if (n > min_days if MUTANT == "boundary" else n >= min_days)]
    return sorted(listed, key=(lambda p: (-p[1], p[0])) if MUTANT == "ties" else (lambda p: -p[1]))
