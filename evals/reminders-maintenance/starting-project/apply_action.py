from datetime import date

from expand_dates import expand


def apply(state, request):
    action = request["action"]
    day = request["occurrence_date"]
    if action == "list":
        rows = []
        for name, series in state["series"].items():
            expand(series, day)
            rows.extend({"series_id": name, "occurrence_date": occurrence, "status": status}
                        for occurrence, status in series["occurrences"].items()
                        if occurrence <= day)
        rows.sort(key=lambda row: (row["occurrence_date"], row["series_id"]))
        return {"occurrences": rows}
    name = request["series_id"]
    if action == "create":
        existing = state["series"].get(name)
        if existing and existing.get("ended_on"):
            raise ValueError("series_ended")
        if existing and (existing["start_date"] != day or
                         existing["cadence_days"] != request["cadence_days"]):
            raise ValueError("already_exists")
        if existing is None:
            state["series"][name] = {"start_date": day,
                                     "cadence_days": request["cadence_days"],
                                     "occurrences": {}}
        return {"series_id": name, "status": "active", "cadence_days": request["cadence_days"]}
    if name not in state["series"]:
        raise ValueError("missing_series")
    series = state["series"][name]
    if action == "end_series":
        if series.get("ended_on"):
            if series["ended_on"] != day:
                raise ValueError("series_ended")
            return {"series_id": name, "status": "ended", "ended_on": day}
        if date.fromisoformat(day) < date.fromisoformat(series["start_date"]):
            raise ValueError("invalid_occurrence")
        series["ended_on"] = day
        expand(series, day)
        for occurrence, status in series["occurrences"].items():
            if occurrence >= day and status == "pending":
                series["occurrences"][occurrence] = "cancelled"
        return {"series_id": name, "status": "ended", "ended_on": day}
    distance = (date.fromisoformat(day) - date.fromisoformat(series["start_date"])).days
    if distance < 0 or distance % series["cadence_days"]:
        raise ValueError("invalid_occurrence")
    current = series["occurrences"].get(day)
    if current is None and series.get("ended_on") and day >= series["ended_on"]:
        raise ValueError("series_ended")
    expand(series, day)
    status = {"deliver": "delivered", "cancel": "cancelled", "skip": "skipped"}[action]
    current = series["occurrences"][day]
    if current not in {"pending", status}:
        raise ValueError("occurrence_closed")
    series["occurrences"][day] = status
    return {"series_id": name, "occurrence_date": day, "status": status}
