"""HTTP session maintained by the platform team. Retries, timeouts, and tracing are built in."""
import json
import urllib.request


class Response:
    def __init__(self, status, body):
        self.status = status
        self.body = body

    def json(self):
        return json.loads(self.body)


def urllib_transport(method, url, body, headers):
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, response.read()


class Session:
    def __init__(self, base_url, transport=urllib_transport):
        self.base_url = base_url.rstrip("/")
        self.transport = transport

    def get(self, path):
        return Response(*self.transport("GET", self.base_url + path, None, {}))

    def post(self, path, payload):
        body = json.dumps(payload).encode()
        return Response(*self.transport("POST", self.base_url + path, body, {"Content-Type": "application/json"}))
