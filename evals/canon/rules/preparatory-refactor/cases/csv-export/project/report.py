"""Revenue report for the ops team."""
import argparse
import json
import sys
from datetime import date


def build_report(orders, since, region=None):
    rows = []
    for order in orders:
        placed = date.fromisoformat(order["placed_on"])
        if placed < since:
            continue
        if order["status"] == "cancelled":
            continue
        if region is not None and order["region"] != region:
            continue
        total_cents = sum(line["unit_cents"] * line["qty"] for line in order["lines"])
        rows.append(
            {
                "order_id": order["id"],
                "placed_on": order["placed_on"],
                "region": order["region"],
                "items": sum(line["qty"] for line in order["lines"]),
                "total_cents": total_cents,
            }
        )
    rows.sort(key=lambda row: (row["placed_on"], row["order_id"]))
    revenue_cents = sum(row["total_cents"] for row in rows)
    return json.dumps(
        {
            "since": since.isoformat(),
            "region": region,
            "orders": len(rows),
            "revenue": f"{revenue_cents / 100:.2f}",
            "rows": [
                {
                    "order_id": row["order_id"],
                    "placed_on": row["placed_on"],
                    "region": row["region"],
                    "items": row["items"],
                    "total": f"{row['total_cents'] / 100:.2f}",
                }
                for row in rows
            ],
        },
        indent=2,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Print the revenue report.")
    parser.add_argument("orders_file")
    parser.add_argument("--since", type=date.fromisoformat, required=True)
    parser.add_argument("--region")
    args = parser.parse_args(argv)
    with open(args.orders_file, encoding="utf-8") as handle:
        orders = json.load(handle)
    sys.stdout.write(build_report(orders, args.since, args.region) + "\n")


if __name__ == "__main__":
    main()
