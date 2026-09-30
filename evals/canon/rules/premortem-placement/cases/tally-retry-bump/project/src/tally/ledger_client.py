"""HTTP client for ledgerd. Retries on connection errors and 5xx for every method."""
import time

import requests

RETRY_STATUSES = {500, 502, 503, 504}


class LedgerClient:
    def __init__(self, settings):
        self.base_url = settings["base_url"]
        self.timeout = settings["timeout_s"]
        self.retries = settings["retries"]
        self.backoff = settings["backoff_s"]
        self.session = requests.Session()

    def request(self, method, path, **kwargs):
        attempt = 0
        while True:
            try:
                response = self.session.request(method, self.base_url + path, timeout=self.timeout, **kwargs)
            except requests.ConnectionError:
                response = None
            if response is not None and response.status_code not in RETRY_STATUSES:
                return response
            if attempt >= self.retries:
                if response is None:
                    raise ConnectionError(f"{method} {path} failed after {attempt + 1} attempts")
                response.raise_for_status()
            time.sleep(self.backoff * (2 ** attempt))
            attempt += 1

    def balance(self, account_id):
        return self.request("GET", f"/accounts/{account_id}/balance").json()

    def post(self, entries):
        return self.request("POST", "/postings", json={"entries": entries}).json()

    def reverse(self, posting_id):
        return self.request("POST", f"/postings/{posting_id}/reverse").json()
