from datetime import date, timedelta


def expand(series, through):
    start = date.fromisoformat(series["start_date"])
    last = date.fromisoformat(through)
    count = (last - start).days // series["cadence_days"] + 1
    for offset in range(max(0, count)):
        day = (start + timedelta(days=offset * series["cadence_days"])).isoformat()
        if series.get("ended_on") and day >= series["ended_on"]:
            break
        series["occurrences"].setdefault(day, "pending")
