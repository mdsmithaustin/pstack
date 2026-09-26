import re

from shop.routes import cart


def _pattern(template: str) -> re.Pattern:
    return re.compile("^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", template) + "$")


def handle(store, method: str, path: str, body: dict | None = None):
    for route_method, template, handler in cart.ROUTES:
        match = _pattern(template).match(path)
        if route_method == method and match:
            return handler(store, match.groupdict(), body or {})
    return 404, {"error": "not found"}
