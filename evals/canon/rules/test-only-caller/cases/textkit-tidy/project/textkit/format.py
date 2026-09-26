"""String formatting helpers."""
import re
import string


def slugify(text):
    text = text.strip()
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text


def truncate(text, limit, suffix="..."):
    if len(text) <= limit:
        return text
    else:
        cut = text[: limit - len(suffix)]
        cut = cut.rstrip()
        return cut + suffix


def banner(text, width=40):
    inner = " " + text + " "
    if len(inner) >= width:
        return inner
    pad = width - len(inner)
    left = pad // 2
    right = pad - left
    return "*" * left + inner + "*" * right
