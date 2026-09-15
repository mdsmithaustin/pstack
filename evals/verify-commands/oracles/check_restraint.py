import re
import sys
from pathlib import Path


PLAN_TAG = re.compile(r"<verification-plan>", re.IGNORECASE)
EXACT_COMMAND = "docker ps --format '{{.Names}}'"
SHELL_FENCE = re.compile(r"```(?:sh|shell|bash)\s*\n(.*?)\n```", re.DOTALL | re.IGNORECASE)


def read_output(output_dir: Path) -> str:
    output = output_dir / "output.md"
    try:
        text = output.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"cannot read output.md: {exc}") from exc
    if not text:
        raise ValueError("output.md is empty")
    if PLAN_TAG.search(text):
        raise ValueError("a near-miss request must not produce a verification plan")
    return text


def check_pipefail(text: str) -> None:
    normalized = text.lower()
    if "pipefail" not in normalized:
        raise ValueError("the response does not identify pipefail")
    if "non-zero" not in normalized and "nonzero" not in normalized and "fail" not in normalized:
        raise ValueError("the response does not describe failure propagation")
    if len(text.split()) > 120:
        raise ValueError("the bounded explanation exceeds 120 words")


def check_format_command(text: str) -> None:
    if text.count(EXACT_COMMAND) != 1:
        raise ValueError("the exact command must appear once")
    blocks = SHELL_FENCE.findall(text)
    if len(blocks) != 1 or blocks[0].strip() != EXACT_COMMAND:
        raise ValueError("the exact command must be the only content in one shell fence")
    remainder = SHELL_FENCE.sub("", text).strip()
    if not remainder or len(re.findall(r"[.!?](?:\s|$)", remainder)) != 1:
        raise ValueError("the shell fence must be followed by one sentence")


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: check_restraint.py CASE OUTPUT_DIR")
    case_id = sys.argv[1]
    try:
        text = read_output(Path(sys.argv[2]))
        if case_id == "pipefail":
            check_pipefail(text)
        elif case_id == "format-command":
            check_format_command(text)
        else:
            raise ValueError(f"unknown case: {case_id}")
    except ValueError as exc:
        print(f"FAIL: {exc}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
