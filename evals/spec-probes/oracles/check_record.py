import json
import math
import os
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oracles.record import evaluate


def strict_json_loads(text: str) -> object:
    def object_from_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        output: dict[str, object] = {}
        for key, value in pairs:
            if key in output:
                raise ValueError(f"duplicate object key: {key}")
            output[key] = value
        return output

    def reject_nonfinite(value: str) -> None:
        raise ValueError(f"non-finite numeric constant: {value}")

    value = json.loads(
        text,
        object_pairs_hook=object_from_pairs,
        parse_constant=reject_nonfinite,
    )

    def validate(item: object, *, depth: int = 0) -> None:
        if depth > 100:
            raise ValueError("JSON value exceeds the maximum nesting depth")
        if isinstance(item, str):
            try:
                item.encode("utf-8", errors="strict")
            except UnicodeEncodeError as exc:
                raise ValueError("JSON value contains a surrogate code point") from exc
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError(f"non-finite numeric value: {item}")
        if isinstance(item, list):
            for child in item:
                validate(child, depth=depth + 1)
        if isinstance(item, dict):
            for key, child in item.items():
                validate(key, depth=depth)
                validate(child, depth=depth + 1)

    validate(value)
    return value


def open_artifact_root(output_dir: Path) -> int:
    absolute_root = output_dir.absolute()
    root_parts = list(absolute_root.parts[1:])
    canonical_root = Path(absolute_root.anchor)
    if root_parts and (canonical_root / root_parts[0]).is_symlink():
        alias = canonical_root / root_parts.pop(0)
        resolved = alias.resolve(strict=True)
        if alias.lstat().st_uid != 0 or resolved.stat().st_uid != 0:
            raise ValueError("evaluation artifact paths must not be symlinks")
        canonical_root = resolved
    for part in root_parts:
        canonical_root /= part
        if canonical_root.is_symlink():
            raise ValueError("evaluation artifact paths must not be symlinks")
    directory_descriptor = -1
    try:
        directory_descriptor = os.open(canonical_root.anchor, os.O_RDONLY | os.O_DIRECTORY)
        for part in canonical_root.parts[1:]:
            next_descriptor = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=directory_descriptor,
            )
            os.close(directory_descriptor)
            directory_descriptor = next_descriptor
        result = directory_descriptor
        directory_descriptor = -1
        return result
    except OSError as exc:
        raise ValueError("evaluation artifact paths must not be symlinks") from exc
    finally:
        if directory_descriptor >= 0:
            os.close(directory_descriptor)


def read_regular_artifact_at(directory_descriptor: int, name: str) -> str:
    artifact_descriptor = -1
    try:
        artifact_descriptor = os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=directory_descriptor,
        )
        metadata = os.fstat(artifact_descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ValueError(f"{name} must be a regular file with exactly one hard link")
        stream = os.fdopen(artifact_descriptor, "r", encoding="utf-8")
        artifact_descriptor = -1
        with stream:
            text = stream.read()
            if os.fstat(stream.fileno()).st_nlink != 1:
                raise ValueError(f"{name} must be a regular file with exactly one hard link")
            return text
    except ValueError:
        raise
    except (OSError, UnicodeError) as exc:
        raise ValueError("evaluation artifact paths must not be symlinks") from exc
    finally:
        if artifact_descriptor >= 0:
            os.close(artifact_descriptor)


def read_regular_artifact(output_dir: Path, name: str) -> str:
    directory_descriptor = open_artifact_root(output_dir)
    try:
        return read_regular_artifact_at(directory_descriptor, name)
    finally:
        os.close(directory_descriptor)


def read_output(output_dir: Path) -> str:
    return read_regular_artifact(output_dir, "output.md")


def parse_events(text: str) -> list[dict[str, object]]:
    try:
        envelope = strict_json_loads(text)
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
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


def load_events(output_dir: Path) -> list[dict[str, object]]:
    return parse_events(read_regular_artifact(output_dir, "events.json"))


def read_evaluation_artifacts(output_dir: Path) -> tuple[str, list[dict[str, object]]]:
    directory_descriptor = open_artifact_root(output_dir)
    try:
        output = read_regular_artifact_at(directory_descriptor, "output.md")
        events = parse_events(read_regular_artifact_at(directory_descriptor, "events.json"))
        return output, events
    finally:
        os.close(directory_descriptor)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: check_record.py CASE_ID OUTPUT_DIR", file=sys.stderr)
        return 2
    case_id, output_dir = sys.argv[1:]
    try:
        root = Path(output_dir)
        text, events = read_evaluation_artifacts(root)
    except (OSError, ValueError) as exc:
        print(f"cannot read evaluation artifacts: {exc}", file=sys.stderr)
        return 2
    errors = evaluate(case_id, text, events)
    print(json.dumps({"score": int(not errors), "max_score": 1, "errors": errors}))
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
