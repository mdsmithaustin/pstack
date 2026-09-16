import os
import re
import stat
import sys
from pathlib import Path


EXACT_COMMAND = "docker ps --format '{{.Names}}'"
SHELL_FENCE = re.compile(r"```(?:sh|shell|bash)\s*\n(.*?)\n```", re.DOTALL | re.IGNORECASE)


class InfrastructureFailure(ValueError):
    pass


def canonical_artifact_root(root: Path) -> Path:
    absolute = root.absolute()
    parts = list(absolute.parts[1:])
    current = Path(absolute.anchor)
    if parts and (current / parts[0]).is_symlink():
        alias = current / parts.pop(0)
        resolved = alias.resolve(strict=True)
        if alias.lstat().st_uid != 0 or resolved.stat().st_uid != 0:
            raise InfrastructureFailure(f"output path contains an untrusted symlink: {alias}")
        current = resolved
    for part in parts:
        current /= part
        if current.is_symlink():
            raise InfrastructureFailure(f"output path contains a symlink: {current}")
    return current


def read_output(output_dir: Path) -> str:
    absolute = canonical_artifact_root(output_dir) / "output.md"
    descriptor = -1
    try:
        descriptor = os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY)
        for index, part in enumerate(absolute.parts[1:]):
            final = index == len(absolute.parts) - 2
            flags = os.O_RDONLY | os.O_NOFOLLOW
            flags |= os.O_NONBLOCK if final else os.O_DIRECTORY
            next_descriptor = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise InfrastructureFailure("output.md is not a regular file")
        if metadata.st_nlink != 1:
            raise InfrastructureFailure("output.md must have exactly one hard link")
        stream = os.fdopen(descriptor, "r", encoding="utf-8")
        descriptor = -1
        with stream:
            text = stream.read().strip()
            if os.fstat(stream.fileno()).st_nlink != 1:
                raise InfrastructureFailure("output.md must have exactly one hard link")
    except (OSError, UnicodeError) as exc:
        raise InfrastructureFailure(
            f"output path contains a symlink or unreadable component: {exc}"
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if not text:
        raise ValueError("output.md is empty")
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
    except InfrastructureFailure as exc:
        print(f"INFRASTRUCTURE_FAILURE: {exc}")
        return 2
    try:
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
