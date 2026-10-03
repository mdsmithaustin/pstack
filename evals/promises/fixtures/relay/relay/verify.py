from .cache import fetch
from .parse import parse
from .sources import load


def verify(feed):
    problems = []
    for record in parse(fetch(feed, 0, load)):
        if not record.fields.get("name"):
            problems.append(f"{record.id}: missing name")
    return problems
