import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oracles.record import evaluate


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: check_record.py CASE_ID OUTPUT_DIR", file=sys.stderr)
        return 2
    case_id, output_dir = sys.argv[1:]
    try:
        text = (Path(output_dir) / "output.md").read_text(encoding="utf-8")
    except OSError as exc:
        print(f"cannot read output.md: {exc}", file=sys.stderr)
        return 2
    errors = evaluate(case_id, text)
    print(json.dumps({"score": int(not errors), "max_score": 1, "errors": errors}))
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
