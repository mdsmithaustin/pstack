from .cache import fetch
from .parse import ParseError, parse
from .retry import retry
from .sources import load
from .store import Store


def import_feed(feed, store_dir):
    try:
        records = retry(lambda: parse(fetch(feed, 0, load)))
    except ParseError as exc:
        raise SystemExit(f"relay: {feed}: {exc}")
    store = Store(store_dir)
    for record in records:
        store.write(record)
    return len(records)
