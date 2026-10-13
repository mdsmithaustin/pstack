#!/usr/bin/env python3
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
    ("evals/canon/rules/premortem-placement/cases/tally-push-hook-rollout/project/ops/incidents.md", "Users", "priya"),
    ("evals/canon/rules/premortem-placement/cases/tally-push-hook-rollout/samples/answer-found.md", "Users", "priya"),
    ("evals/canon/rules/review-large-module/cases/sqlite-migration-backup/pr.patch", "home", "me"),
}


def display_path(path):
    redacted = re.sub(r"/(Users|home)/[^/]+", r"/\1/<redacted>", path)
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


def main():
    try:
        root = subprocess.run(["git", "rev-parse", "--show-toplevel"], check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.rstrip(b"\n")
        inventory = subprocess.run(["git", "ls-files", "-z"], cwd=os.fsdecode(root), check=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout
        if not inventory or not inventory.endswith(b"\0"):
            raise OSError("empty or invalid inventory")
    except (OSError, subprocess.CalledProcessError):
        print("ERROR: cannot acquire a nonempty tracked-file inventory", file=sys.stderr)
        return 2

    used = set()
    findings = []
    checked = 0
    for name in sorted({os.fsdecode(value) for value in inventory[:-1].split(b"\0")}):
        try:
            content = tracked_bytes(root, name)
        except OSError:
            print(f"ERROR: cannot inspect tracked file {display_path(name)}", file=sys.stderr)
            return 2
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
    if stale:
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


if __name__ == "__main__":
    sys.exit(main())
