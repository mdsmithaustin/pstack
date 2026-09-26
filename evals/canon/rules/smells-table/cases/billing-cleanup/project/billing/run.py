"""Print every invoice for the billing run: python3 -m billing.run data/accounts.json"""
import json
import sys

from billing.customers import load_customers
from billing.invoices import render_invoice


def main(path):
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    customers = load_customers(data["customers"])
    for customer_id, lines in sorted(data["lines"].items()):
        print(render_invoice(customers[customer_id], lines))
        print("---")


if __name__ == "__main__":
    main(sys.argv[1])
