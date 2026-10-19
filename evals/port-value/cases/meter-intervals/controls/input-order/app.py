import json
import sys
from datetime import date


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError()
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError()
    return parsed


def interval_usage(request):
    if not isinstance(request, dict) or not isinstance(request.get("readings"), list):
        raise ValueError()
    readings = []
    seen = set()
    for reading in request["readings"]:
        if not isinstance(reading, dict):
            raise ValueError()
        at = parse_date(reading.get("date"))
        value = reading.get("value")
        if type(value) is not int or value < 0 or at in seen:
            raise ValueError()
        seen.add(at)
        readings.append((at, value, reading))
    intervals = []
    for previous, current in zip(readings, readings[1:]):
        usage = current[1] - previous[1]
        if usage < 0:
            return {"error": "reading_decreased"}
        intervals.append({"start": previous[0].isoformat(), "end": current[0].isoformat(),
                          "usage": usage})
    return {"intervals": intervals, "total_usage": sum(i["usage"] for i in intervals)}

if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        result = interval_usage(request)
    except (ValueError, TypeError, KeyError, OverflowError):
        result = {"error": "invalid_request"}
    print(json.dumps(result, sort_keys=True))
