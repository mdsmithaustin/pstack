import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z`\"\[(/*])")
LIST_ITEM = re.compile(r"^(\s*)([-*]|\d+\.)\s+")


@dataclass(frozen=True)
class Unit:
    file: str
    kind: str
    text: str

    @property
    def key(self):
        digest = hashlib.sha256(f"{self.file}\0{self.text}".encode()).hexdigest()
        return digest[:12]


def normalize(text):
    return " ".join(text.split())


def split_prose(text):
    return [s for s in (normalize(p) for p in SENTENCE_END.split(normalize(text))) if s]


def units_of(path, name):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    out = []
    para = []
    item = None

    def flush():
        nonlocal para, item
        if item is not None:
            out.append(Unit(name, "item", normalize(item)))
            item = None
        if para:
            out.extend(Unit(name, "sentence", s) for s in split_prose(" ".join(para)))
            para = []

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            flush()
            fence = [line]
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                fence.append(lines[i])
                i += 1
            fence.append(lines[i] if i < len(lines) else "```")
            out.append(Unit(name, "fence", "\n".join(fence)))
        elif line.startswith("#"):
            flush()
            out.append(Unit(name, "heading", normalize(line)))
        elif line.startswith("!["):
            flush()
            out.append(Unit(name, "image", normalize(line)))
        elif not line.strip():
            flush()
        elif LIST_ITEM.match(line):
            flush()
            item = LIST_ITEM.sub("", line, count=1)
        elif item is not None:
            item += " " + line.strip()
        else:
            para.append(line)
        i += 1
    flush()
    return out


def guide_units(guide_dir):
    guide = Path(guide_dir)
    return [u for p in sorted(guide.glob("*.md")) for u in units_of(p, p.name)]
