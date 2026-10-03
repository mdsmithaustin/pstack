_memo = {}


def cache_key(feed, offset):
    return feed


def fetch(feed, offset, loader):
    key = cache_key(feed, offset)
    if key not in _memo:
        _memo[key] = loader(feed)
    return _memo[key]


def clear():
    _memo.clear()
