import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oracles.record import evaluate


def path_contains_symlink(path: Path) -> bool:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.is_symlink():
            return True
    return False


def reject_symlink_artifacts(output_dir: Path, names: tuple[str, ...]) -> None:
    if any(path_contains_symlink(output_dir / name) for name in names):
        raise ValueError("evaluation artifact paths must not be symlinks")


def read_output(output_dir: Path) -> str:
    reject_symlink_artifacts(output_dir, ("output.md",))
    return (output_dir / "output.md").read_text(encoding="utf-8")


def load_events(output_dir: Path) -> list[dict[str, object]]:
    path = output_dir / "events.json"
    reject_symlink_artifacts(output_dir, ("events.json",))
    if not path.is_file():
        raise ValueError("events.json is missing")
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read events.json: {exc}") from exc
    if (
        not isinstance(envelope, dict)
        or type(envelope.get("schema_version")) is not int
        or envelope["schema_version"] != 2
        or not isinstance(envelope.get("source"), str)
        or not envelope["source"]
    ):
        raise ValueError("events.json must contain a version 2 envelope with a source")
    events = envelope.get("events")
    if not isinstance(events, list) or not all(isinstance(event, dict) for event in events):
        raise ValueError("events.json does not contain an events list")
    return events


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: check_record.py CASE_ID OUTPUT_DIR", file=sys.stderr)
        return 2
    case_id, output_dir = sys.argv[1:]
    try:
        root = Path(output_dir)
        text = read_output(root)
        events = load_events(root)
    except (OSError, ValueError) as exc:
        print(f"cannot read evaluation artifacts: {exc}", file=sys.stderr)
        return 2
    errors = evaluate(case_id, text, events)
    print(json.dumps({"score": int(not errors), "max_score": 1, "errors": errors}))
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
