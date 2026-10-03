import os
from collections import Counter

from .cache import fetch
from .oldparse import parse_legacy
from .sources import load
from .store import Store


def summarize(feed, store_dir):
    store = Store(store_dir)
    stored = sorted(os.listdir(store.root))
    rows = parse_legacy(fetch(feed, 0, load))
    kinds = Counter(row.get("kind", "unknown") for row in rows)
    return {
        "records": len(rows),
        "kinds": dict(sorted(kinds.items())),
        "already_stored": len(stored),
    }
