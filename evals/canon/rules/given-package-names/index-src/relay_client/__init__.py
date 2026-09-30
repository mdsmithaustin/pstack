"""Span export helpers for the relay."""

__version__ = "0.3.1"


def export_spans(spans, send):
    """Send each span as a dict through `send` and return how many went out."""
    count = 0
    for span in spans:
        send(dict(span))
        count += 1
    return count
