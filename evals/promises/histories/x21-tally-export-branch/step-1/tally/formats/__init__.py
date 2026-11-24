"""Output shapes for a tally report.

Every renderer takes the ranked rows, a list of (word, count) pairs with the most
common word first, and returns the whole text to print, ending in a newline.
Renderers never sort or cut the rows; the caller has already done both.
"""

from . import csv_out, html_out, markdown_out, text_out

_RENDERERS = {
    "csv": csv_out.render,
    "html": html_out.render,
    "markdown": markdown_out.render,
    "text": text_out.render,
}

# Formats that print a heading. The others ignore --title.
TITLED = frozenset({"html", "markdown"})


def names():
    """The format names --format accepts, in the order --help lists them."""
    return sorted(_RENDERERS)


def render(name, rows, *, title=None):
    """Render rows in the named format.

    Raises KeyError for an unknown name; argparse's choices keep the CLI from
    reaching that. A title passed to a format outside TITLED is dropped.
    """
    renderer = _RENDERERS[name]
    if name in TITLED:
        return renderer(rows, title=title)
    return renderer(rows)


def width(rows):
    """The widest count in rows, for formats that right-align the counts."""
    return max((len(str(count)) for _, count in rows), default=1)
