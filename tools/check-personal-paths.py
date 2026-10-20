#!/usr/bin/env python3
import argparse
import os
import re
import stat
import subprocess
import sys
from pathlib import Path


HOME_PATH = re.compile(
    r"/(?P<kind>Users|home)/(?![$<])"
    r"(?P<account>[^/\s`'\"<>]+(?: [^/\s`'\"<>]+)*)"
)
EXCEPTIONS = {
    ("PORTING.md", "Users", "you"),
    ("tools/test_effort_transcripts.py", "Users", "me"),
    ("evals/promises/test_oracles.py", "Users", "someone"),
    ("evals/promises/test_live.py", "Users", "someone"),
    ("evals/promises/test_reduce_trace.py", "Users", "someone"),
    ("evals/promises/test_reduce_trace.py", "Users", "alice"),
    ("evals/promises/test_reduce_trace.py", "Users", "dev"),
    ("evals/promises/test_reduce_trace.py", "home", "bob"),
    ("evals/promises/test_reduce_trace.py", "home", "dev"),
}


def display_path(path):
    redacted = re.sub(r"(^|/)(Users|home)/[^/]+", r"\1\2/<redacted>", path)
    return redacted.encode("unicode_escape").decode("ascii")


def tracked_bytes(root, name):
    parts = Path(name).parts
    if not parts or Path(name).is_absolute() or ".." in parts:
        raise OSError("invalid tracked path")
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        info = os.stat(parts[-1], dir_fd=directory, follow_symlinks=False)
        if stat.S_ISLNK(info.st_mode):
            return os.fsencode(os.readlink(parts[-1], dir_fd=directory))
        if not stat.S_ISREG(info.st_mode):
            raise OSError("unsupported tracked file")
        descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        with os.fdopen(descriptor, "rb") as file:
            return file.read()
    finally:
        os.close(directory)


def git_bytes(root, *args, input=None):
    return subprocess.run(["git", *args], cwd=os.fsdecode(root) if root is not None else None, input=input, check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout


def blob_files(root, tip=None):
    inventory = git_bytes(root, "ls-tree", "-rz", "--full-tree", tip) if tip else git_bytes(root, "ls-files", "--stage", "-z")
    if not inventory or not inventory.endswith(b"\0"):
        raise OSError("empty or invalid inventory")
    entries = []
    for record in inventory[:-1].split(b"\0"):
        metadata, name = record.split(b"\t", 1)
        if tip:
            mode, kind, object_id = metadata.split()
            stage = b"0"
        else:
            mode, object_id, stage = metadata.split()
        if mode not in (b"100644", b"100755", b"120000") or stage != b"0":
            raise OSError("unsupported index or tree entry")
        entries.append((os.fsdecode(name), object_id))
    blobs = git_bytes(root, "cat-file", "--batch", input=b"".join(oid + b"\n" for _, oid in entries))
    offset = 0
    files = []
    for name, oid in entries:
        end = blobs.index(b"\n", offset)
        actual, kind, size = blobs[offset:end].split()
        if actual != oid or kind != b"blob":
            raise OSError("invalid blob")
        offset = end + 1
        size = int(size)
        files.append((name, blobs[offset:offset + size]))
        offset += size + 1
    return files


def scan(root, files, validate_exceptions=True):
    used = set()
    findings = []
    checked = 0
    for name, content in sorted(files):
        try:
            if content is None:
                content = tracked_bytes(root, name)
        except OSError:
            print(f"ERROR: cannot inspect tracked file {display_path(name)}", file=sys.stderr)
            return 2
        for match in HOME_PATH.finditer("/" + name):
            findings.append(f"{display_path(name)}:0: personal home path /{match['kind']}/<redacted>")
        if b"\0" in content:
            continue
        checked += 1
        for line, text in enumerate(content.decode("utf-8", errors="replace").splitlines(), 1):
            for match in HOME_PATH.finditer(text):
                exception = (name, match["kind"], match["account"])
                if exception in EXCEPTIONS:
                    used.add(exception)
                else:
                    findings.append(f"{display_path(name)}:{line}: personal home path /{match['kind']}/<redacted>")
    stale = EXCEPTIONS - used
    if validate_exceptions and stale:
        for name in sorted({entry[0] for entry in stale}):
            print(f"ERROR: unused personal-path exception for {display_path(name)}", file=sys.stderr)
        return 2
    for finding in findings:
        print(finding)
    if findings:
        return 1
    if not checked:
        print("ERROR: no tracked text files inspected", file=sys.stderr)
        return 2
    print(f"PASS personal paths: checked {checked} tracked text files")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=("worktree", "index", "pre-push"), default="worktree")
    args = parser.parse_args()
    try:
        root = git_bytes(None, "rev-parse", "--show-toplevel").rstrip(b"\n")
        if args.source == "worktree":
            inventory = git_bytes(root, "ls-files", "-z")
            if not inventory or not inventory.endswith(b"\0"):
                raise OSError("empty or invalid inventory")
            snapshots = [[(os.fsdecode(name), None) for name in set(inventory[:-1].split(b"\0"))]]
        elif args.source == "index":
            snapshots = [blob_files(root)]
        else:
            tips = set()
            for line in sys.stdin:
                fields = line.split()
                if len(fields) != 4 or any(not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", fields[i]) for i in (1, 3)):
                    raise OSError("invalid push input")
                if set(fields[1]) != {"0"}:
                    tips.add(fields[1])
            snapshots = [blob_files(root, tip) for tip in sorted(tips)]
    except (OSError, ValueError, subprocess.CalledProcessError):
        print("ERROR: cannot acquire a nonempty tracked-file inventory", file=sys.stderr)
        return 2
    results = [scan(root, files, validate_exceptions=args.source == "worktree") for files in snapshots]
    return max(results, default=0)


if __name__ == "__main__":
    sys.exit(main())
