import json
from dataclasses import dataclass
from wsgiref.util import setup_testing_defaults

from newsroom.app import SESSIONS, app


@dataclass
class Response:
    status: int
    body: dict


class Reader:
    def __init__(self, token=None):
        self.token = token

    def open_article(self, slug):
        environ = {"REQUEST_METHOD": "GET", "PATH_INFO": f"/articles/{slug}"}
        if self.token:
            environ["HTTP_AUTHORIZATION"] = f"Bearer {self.token}"
        setup_testing_defaults(environ)
        seen = {}
        chunks = app(environ, lambda status, headers: seen.update(status=status))
        return Response(int(seen["status"].split()[0]), json.loads(b"".join(chunks)))


def signed_in_as(plan):
    token = next(token for token, owner in SESSIONS.items() if owner == plan)
    return Reader(token)


def anonymous():
    return Reader()
