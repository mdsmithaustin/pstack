from __future__ import annotations

import json
import secrets

from billing_service import charge


def main() -> int:
    report = {
        "driver": "verify_billing_service.py",
        "evidence_id": secrets.token_hex(12),
        "fresh_start": True,
        "observations": {
            "dependency_failure": charge("error"),
            "dependency_slowness": charge("slow"),
        },
        "target": "billing_service.py",
    }
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
