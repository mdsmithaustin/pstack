import json

from .oldparse import parse_legacy


def export_json(text):
    rows = parse_legacy(text)
    return json.dumps(sorted(rows, key=lambda row: row["id"]), indent=2)
