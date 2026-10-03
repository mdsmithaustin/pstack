from .cache import fetch
from .dedupe import unique_by_id
from .parse import parse
from .retry import retry
from .sources import load
from .store import Store


def import_feed(feed, store_dir, dedupe=False):
    records = retry(lambda: parse(fetch(feed, 0, load)))
    if dedupe:
        records = unique_by_id(records)
    store = Store(store_dir)
    for record in records:
        store.write(record)
    return len(records)
