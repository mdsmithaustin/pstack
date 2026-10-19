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
    holds = request.get("holds", [])
    if not isinstance(holds, list):
        raise ValueError()
    active = {record_id: [] for record_id in deadlines}
    hold_ids = set()
    for hold in holds:
        if not isinstance(hold, dict):
            raise ValueError()
        hold_id = hold.get("id")
        record_ids = hold.get("record_ids")
        if not isinstance(hold_id, str) or not hold_id or hold_id in hold_ids:
            raise ValueError()
        if not isinstance(record_ids, list) or any(
                not isinstance(record_id, str) or record_id not in deadlines
                for record_id in record_ids):
            raise ValueError()
        if len(record_ids) != len(set(record_ids)):
            raise ValueError()
        hold_ids.add(hold_id)
        released = hold.get("released")
        if released is not None:
            released = parse_date(released)
        if released is None or as_of < released:
            for record_id in record_ids:
                active[record_id].append(hold_id)
    delete = []
    retain = []
    for record_id, deadline in sorted(deadlines.items()):
        if as_of >= deadline and not active[record_id]:
            delete.append(record_id)
        else:
            item = {"id": record_id, "until": deadline.isoformat()}
            if active[record_id]:
                item["holds"] = sorted(active[record_id])
            retain.append(item)
    return {"delete": delete, "retain": retain}

if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        result = schedule(request)
    except (ValueError, TypeError, KeyError, OverflowError):
        result = {"error": "invalid_request"}
    print(json.dumps(result, sort_keys=True))
