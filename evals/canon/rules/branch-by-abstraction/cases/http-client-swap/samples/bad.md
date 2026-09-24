A `platform_http` client lands next to `httpclient`, and packages move over one PR at a time. `httpclient` stays for anything not yet moved.

<plan>
1. Add `app/http_v2.py` wrapping `platform_http.Session` and move billing to it.
2. Move catalog to `app.http_v2`.
3. Move orders to `app.http_v2`.
4. Move users to `app.http_v2`. Mark `app/httpclient.py` deprecated for any stragglers.
</plan>

<commit message="Add http_v2 on platform_http">
<file path="app/http_v2.py">
"""platform_http-backed client for new code."""
from app import settings
from platform_http import Session

SESSION = Session(settings.API_URL)


def get_json(path):
    return SESSION.get(path).json()


def post_json(path, body):
    return SESSION.post(path, body).json()
</file>
</commit>
