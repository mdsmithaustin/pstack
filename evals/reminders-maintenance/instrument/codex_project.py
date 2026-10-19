#!/usr/bin/env python3
from __future__ import annotations

import os
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath


def extract_project(archive: Path, destination: Path) -> None:
    if destination.exists():
        raise ValueError("project destination already exists")
    with zipfile.ZipFile(archive) as source:
        names: set[str] = set()
        for member in source.infolist():
            path = PurePosixPath(member.filename)
            mode = member.external_attr >> 16
            if (not member.filename or path.is_absolute() or ".." in path.parts
                    or "\\" in member.filename or str(path) != member.filename.rstrip("/")
                    or member.filename.rstrip("/") in names
                    or stat.S_ISLNK(mode) or member.file_size > 1 << 20
                    or stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                raise ValueError(f"unsafe archive member: {member.filename}")
            names.add(member.filename.rstrip("/"))
        if sum(member.file_size for member in source.infolist()) > 32 << 20:
            raise ValueError("archive exceeds the capture size limit")
        destination.mkdir(parents=True)
        for member in source.infolist():
            target = destination / member.filename
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read(member))
                target.chmod(0o755 if (member.external_attr >> 16) & 0o111 else 0o644)


def main() -> None:
    extract_project(Path("inputs/project.zip"), Path("project"))
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    executable = sys.argv[1]
    os.execv(executable, [executable, "exec", *sys.argv[2:]])


if __name__ == "__main__":
    main()
