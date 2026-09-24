import io
import json
import unittest
from wsgiref.util import setup_testing_defaults

from newsroom.app import app
from tests.client import anonymous, signed_in_as


class ArticlesTest(unittest.TestCase):
    def test_paid_subscriber_reads_a_paid_article(self):
        reader = signed_in_as("paid")

        response = reader.open_article("harbor-deal")

        self.assertEqual(response.status, 200)
        self.assertEqual(response.body, {"title": "Inside the harbor deal"})

    def test_anonymous_reader_reads_a_free_article(self):
        response = anonymous().open_article("town-budget")

        self.assertEqual(response.body, {"title": "Town budget passes"})

    def test_free_subscriber_reads_a_free_article(self):
        environ = {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": "/articles/town-budget",
            "HTTP_AUTHORIZATION": "Bearer tok-free-1",
            "wsgi.input": io.BytesIO(b""),
        }
        setup_testing_defaults(environ)
        captured = {}

        def start_response(status, headers):
            captured["status"] = status

        body = b"".join(app(environ, start_response))

        self.assertEqual(captured["status"], "200 OK")
        self.assertEqual(json.loads(body), {"title": "Town budget passes"})


if __name__ == "__main__":
    unittest.main()
