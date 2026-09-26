"""Hand-rolled HTTP helpers from 2019. No retries, no timeouts."""
import json
import urllib.request

from app import settings

OPENER = urllib.request.urlopen


def get_json(path):
    with OPENER(urllib.request.Request(settings.API_URL + path)) as response:
        return json.loads(response.read())


def post_json(path, body):
    request = urllib.request.Request(
        settings.API_URL + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with OPENER(request) as response:
        return json.loads(response.read())
