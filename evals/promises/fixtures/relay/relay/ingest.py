from .cache import fetch
from .parse import parse
from .retry import retry
from .sources import load
from .store import Store


def import_feed(feed, store_dir):
    records = retry(lambda: parse(fetch(feed, 0, load)))
    store = Store(store_dir)
    for record in records:
        store.write(record)
    return len(records)
