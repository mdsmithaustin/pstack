RETRY_LIMIT = 3


class Transient(Exception):
    pass


def retry(fn, *, limit=RETRY_LIMIT):
    last = None
    for _ in range(limit):
        try:
            return fn()
        except (Transient, ValueError) as exc:
            last = exc
    raise last
