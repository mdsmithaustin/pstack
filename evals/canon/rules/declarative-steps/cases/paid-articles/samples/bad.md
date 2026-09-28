<file path="tests/test_paywall.py">
import io
import json
import unittest
from wsgiref.util import setup_testing_defaults

from newsroom.app import app


class PaywallTest(unittest.TestCase):
    def test_free_subscriber_cannot_open_paid_article(self):
        environ = {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": "/articles/harbor-deal",
            "HTTP_AUTHORIZATION": "Bearer tok-free-1",
            "wsgi.input": io.BytesIO(b""),
        }
        setup_testing_defaults(environ)
        captured = {}

        def start_response(status, headers):
            captured["status"] = status

        body = b"".join(app(environ, start_response))

        self.assertEqual(captured["status"], "402 Payment Required")
        self.assertEqual(json.loads(body), {"error": "subscription required"})


if __name__ == "__main__":
    unittest.main()
</file>
