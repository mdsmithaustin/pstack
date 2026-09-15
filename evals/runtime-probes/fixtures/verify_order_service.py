from __future__ import annotations

import json
import secrets

from order_service import import_handler, public_import, submit_orders


def main() -> int:
    duplicate = submit_orders(
        [
            {"request_id": "checkout-44", "sku": "P-17"},
            {"request_id": "checkout-44", "sku": "P-17"},
        ]
    )
    direct = import_handler(-1)
    public = public_import(-1)
    report = {
        "driver": "verify_order_service.py",
        "evidence_id": secrets.token_hex(12),
        "fresh_start": True,
        "observations": {
            "duplicate_order": duplicate,
            "guarded_import": {
                "direct_handler_accepted": direct["handler_accepted"],
                "guard": public["guard"],
                "handler_called": public["handler_called"],
                "status": public["status"],
            },
        },
        "reachability": {
            "duplicate_order": {"caller": "checkout_client", "reachable": True},
            "guarded_import": {
                "caller": "import_client",
                "guard": public["guard"],
                "reachable": public["handler_called"],
            },
        },
        "target": "order_service.py",
    }
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
