Two commits. Nothing in the repo calls `banner` except its tests, so the first commit deletes it, its tests, and its export. The second drops the unused `string` import and flattens `slugify` and `truncate`.

<commit message="Delete banner, which only its tests call">
<file path="textkit/__init__.py">
"""Text helpers shared by the storefront and the admin tools."""
from .format import slugify, truncate

__all__ = ["slugify", "truncate"]
</file>
<file path="textkit/format.py">
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
</file>
<file path="tests/test_format.py">
import unittest

from textkit.format import slugify, truncate


class SlugifyTest(unittest.TestCase):
    def test_collapses_punctuation_and_spaces(self):
        self.assertEqual(slugify("  Linen Shirt, Blue! "), "linen-shirt-blue")


class TruncateTest(unittest.TestCase):
    def test_short_text_is_unchanged(self):
        self.assertEqual(truncate("Mug", 10), "Mug")

    def test_long_text_ends_with_suffix(self):
        self.assertEqual(truncate("Handmade ceramic travel mug", 12), "Handmade...")


if __name__ == "__main__":
    unittest.main()
</file>
</commit>

<commit message="Drop unused import and flatten slugify and truncate">
<file path="textkit/format.py">
"""String formatting helpers."""
import re


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")


def truncate(text, limit, suffix="..."):
    if len(text) <= limit:
        return text
    return text[: limit - len(suffix)].rstrip() + suffix
</file>
</commit>
