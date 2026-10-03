import json

from ..retry import Transient


def load(path):
    with open(path, encoding="utf-8") as handle:
        raw = handle.read()
    if not raw.strip():
        raise Transient(f"{path} is empty")
    items = json.loads(raw)
    lines = []
    for item in items:
        lines.append(";".join(f"{key}={value}" for key, value in item.items()))
    return "\n".join(lines) + "\n"
