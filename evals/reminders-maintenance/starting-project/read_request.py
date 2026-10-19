import json
from datetime import date


def read(raw):
    try:
        request = json.loads(raw)
        action = request["action"]
        fields = {"action", "occurrence_date"}
        if action in {"create", "deliver", "cancel", "skip", "end_series"}:
            fields.add("series_id")
            if not isinstance(request["series_id"], str) or not request["series_id"]:
                raise ValueError
        elif action != "list":
            raise ValueError
        if action == "create":
            fields.add("cadence_days")
            cadence = request["cadence_days"]
            if type(cadence) is not int or cadence <= 0:
                raise ValueError
        if set(request) != fields:
            raise ValueError
        day = request["occurrence_date"]
        if not isinstance(day, str) or date.fromisoformat(day).isoformat() != day:
            raise ValueError
    except (ValueError, KeyError, TypeError):
        raise ValueError("invalid_request") from None
    return request
