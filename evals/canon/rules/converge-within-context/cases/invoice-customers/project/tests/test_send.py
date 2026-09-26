import unittest

from invoicing.send import prepare

ROW = {"customer_id": "c7", "customer_name": "Ada Lovelace", "billing_email": "ada@example.com"}


class PrepareTest(unittest.TestCase):
    def test_header_and_message_use_the_same_customer(self):
        header, message = prepare(ROW, "INV-12")
        self.assertIn("Ada Lovelace <ada@example.com>", header)
        self.assertEqual(message["to"], "ada@example.com")
