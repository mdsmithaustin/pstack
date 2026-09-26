The feature lands first and the cleanup follows.

<commit message="Add CSV export">
<file path="report.py">
"""Revenue report for the ops team."""
import argparse
import csv
import io
import json
import sys
from datetime import date


def build_report(orders, since, region=None, fmt="json"):
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
    if fmt == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(["order_id", "placed_on", "region", "items", "total"])
        for row in rows:
            writer.writerow([row["order_id"], row["placed_on"], row["region"], row["items"], f"{row['total_cents'] / 100:.2f}"])
        return buffer.getvalue().rstrip("\n")
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
    parser.add_argument("--format", choices=["json", "csv"], default="json")
    args = parser.parse_args(argv)
    with open(args.orders_file, encoding="utf-8") as handle:
        orders = json.load(handle)
    sys.stdout.write(build_report(orders, args.since, args.region, args.format) + "\n")


if __name__ == "__main__":
    main()
</file>
</commit>

<commit message="Tidy report rendering">
<file path="report.py">
"""Revenue report for the ops team."""
import argparse
import csv
import io
import json
import sys
from datetime import date


def collect_report(orders, since, region=None):
    rows = []
    for order in orders:
        placed = date.fromisoformat(order["placed_on"])
        if placed < since:
            continue
        if order["status"] == "cancelled":
            continue
        if region is not None and order["region"] != region:
            continue
        rows.append(
            {
                "order_id": order["id"],
                "placed_on": order["placed_on"],
                "region": order["region"],
                "items": sum(line["qty"] for line in order["lines"]),
                "total_cents": sum(line["unit_cents"] * line["qty"] for line in order["lines"]),
            }
        )
    rows.sort(key=lambda row: (row["placed_on"], row["order_id"]))
    return {"since": since, "region": region, "rows": rows}


def money(cents):
    return f"{cents / 100:.2f}"


def render_json(report):
    rows = report["rows"]
    return json.dumps(
        {
            "since": report["since"].isoformat(),
            "region": report["region"],
            "orders": len(rows),
            "revenue": money(sum(row["total_cents"] for row in rows)),
            "rows": [
                {
                    "order_id": row["order_id"],
                    "placed_on": row["placed_on"],
                    "region": row["region"],
                    "items": row["items"],
                    "total": money(row["total_cents"]),
                }
                for row in rows
            ],
        },
        indent=2,
    )


def render_csv(report):
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["order_id", "placed_on", "region", "items", "total"])
    for row in report["rows"]:
        writer.writerow([row["order_id"], row["placed_on"], row["region"], row["items"], money(row["total_cents"])])
    return buffer.getvalue().rstrip("\n")


RENDERERS = {"json": render_json, "csv": render_csv}


def build_report(orders, since, region=None):
    return render_json(collect_report(orders, since, region))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Print the revenue report.")
    parser.add_argument("orders_file")
    parser.add_argument("--since", type=date.fromisoformat, required=True)
    parser.add_argument("--region")
    parser.add_argument("--format", choices=sorted(RENDERERS), default="json")
    args = parser.parse_args(argv)
    with open(args.orders_file, encoding="utf-8") as handle:
        orders = json.load(handle)
    report = collect_report(orders, args.since, args.region)
    sys.stdout.write(RENDERERS[args.format](report) + "\n")


if __name__ == "__main__":
    main()
</file>
</commit>
