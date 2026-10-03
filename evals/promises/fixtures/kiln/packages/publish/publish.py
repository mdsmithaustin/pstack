import re
from pathlib import Path
from typing import NamedTuple


class Written(NamedTuple):
    path: Path
    size: int


def file_name(tag):
    return re.sub(r"[^a-z0-9-]+", "-", tag.lower()).strip("-") + ".txt"


def publish(blocks, out_dir):
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    written = []
    for block in blocks:
        path = target / file_name(block.tag)
        path.write_text(block.text, encoding="utf-8")
        written.append(Written(path, path.stat().st_size))
    return written


def total_size(written):
    return sum(item.size for item in written)


def index_text(written):
    lines = [f"{item.path.name}\t{item.size}" for item in written]
    lines.append(f"total\t{total_size(written)}")
    return "\n".join(lines) + "\n"


def write_index(written, out_dir):
    path = Path(out_dir) / "index.txt"
    path.write_text(index_text(written), encoding="utf-8")
    return path


def names(written):
    return [item.path.name for item in written]
