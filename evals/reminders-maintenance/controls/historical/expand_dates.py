from datetime import date, timedelta


def expand(series, through):
    start = date.fromisoformat(series["start_date"])
    last = date.fromisoformat(through)
    end = date.fromisoformat(series["ended_on"]) if series.get("ended_on") else None
    anchor = start
    cadence = series["cadence_days"]
    first_inclusive = True

    for change in series.get("cadence_changes", []) + [
        {"effective_after": through, "cadence_days": cadence}
    ]:
        cutoff = date.fromisoformat(change["effective_after"])
        segment_end = min(last, cutoff)
        if first_inclusive:
            first = anchor
        elif (last - anchor).days >= cadence:
            first = anchor + timedelta(days=cadence)
        else:
            first = None
        if end and first is not None and first >= end:
            segment_end = None
        elif end and segment_end >= end:
            segment_end = end - timedelta(days=1)
        if first is not None and segment_end is not None and segment_end >= first:
            count = (segment_end - first).days // cadence + 1
            for offset in range(count):
                day = (first + timedelta(days=offset * cadence)).isoformat()
                series["occurrences"].setdefault(day, "pending")
        if cutoff >= last:
            break
        anchor = cutoff
        cadence = change["cadence_days"]
        first_inclusive = False


def scheduled(series, occurrence):
    target = date.fromisoformat(occurrence)
    anchor = date.fromisoformat(series["start_date"])
    cadence = series["cadence_days"]
    first_inclusive = True

    for change in series.get("cadence_changes", []):
        cutoff = date.fromisoformat(change["effective_after"])
        if target <= cutoff:
            distance = (target - anchor).days
            return distance >= 0 and (first_inclusive or distance > 0) and distance % cadence == 0
        anchor = cutoff
        cadence = change["cadence_days"]
        first_inclusive = False

    distance = (target - anchor).days
    return distance > 0 and distance % cadence == 0
