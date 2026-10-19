import json
import sys
from datetime import date, timedelta


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError()
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError()
    return parsed


def schedule(request):
    if not isinstance(request, dict):
        raise ValueError()
    as_of = parse_date(request.get("as_of"))
    rules = request.get("rules")
    records = request.get("records")
    if not isinstance(rules, dict) or not isinstance(records, list):
        raise ValueError()
    for category, days in rules.items():
        if not category or type(days) is not int or days < 0:
            raise ValueError()
    deadlines = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError()
        record_id = record.get("id")
        category = record.get("category")
        if not isinstance(record_id, str) or not record_id or record_id in deadlines:
            raise ValueError()
        if not isinstance(category, str) or category not in rules:
            raise ValueError()
        deadlines[record_id] = parse_date(record.get("closed")) + timedelta(days=rules[category])
    delete = []
    retain = []
    for record_id, deadline in sorted(deadlines.items()):
        if as_of > deadline:
            delete.append(record_id)
        else:
            retain.append({"id": record_id, "until": deadline.isoformat()})
    return {"delete": delete, "retain": retain}

if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        result = schedule(request)
    except (ValueError, TypeError, KeyError, OverflowError):
        result = {"error": "invalid_request"}
    print(json.dumps(result, sort_keys=True))
