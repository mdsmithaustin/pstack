import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oracles.record import evaluate


def load_events(output_dir: Path) -> list[dict[str, object]]:
    path = output_dir / "events.json"
    if not path.is_file():
        raise ValueError("events.json is missing")
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read events.json: {exc}") from exc
    events = envelope.get("events")
    if not isinstance(events, list):
        raise ValueError("events.json does not contain an events list")
    return [event for event in events if isinstance(event, dict)]


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: check_record.py CASE_ID OUTPUT_DIR", file=sys.stderr)
        return 2
    case_id, output_dir = sys.argv[1:]
    try:
        root = Path(output_dir)
        text = (root / "output.md").read_text(encoding="utf-8")
        events = load_events(root)
    except (OSError, ValueError) as exc:
        print(f"cannot read evaluation artifacts: {exc}", file=sys.stderr)
        return 2
    errors = evaluate(case_id, text, events)
    print(json.dumps({"score": int(not errors), "max_score": 1, "errors": errors}))
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
