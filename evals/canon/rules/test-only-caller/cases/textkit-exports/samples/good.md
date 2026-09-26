One commit. It drops the unused `string` import and flattens `slugify`, `truncate`, and `banner`. `banner` stays, because `textkit/__init__.py` exports it and callers outside this repo can use it.

<commit message="Drop unused import and flatten the format helpers">
<file path="textkit/format.py">
"""String formatting helpers."""
import re


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")


def truncate(text, limit, suffix="..."):
    if len(text) <= limit:
        return text
    return text[: limit - len(suffix)].rstrip() + suffix


def banner(text, width=40):
    inner = f" {text} "
    if len(inner) >= width:
        return inner
    left = (width - len(inner)) // 2
    return "*" * left + inner + "*" * (width - len(inner) - left)
</file>
</commit>
