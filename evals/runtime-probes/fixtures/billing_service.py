from __future__ import annotations

import time


def charge(provider_mode: str, timeout_seconds: float = 0.01) -> dict[str, object]:
    started = time.monotonic()
    if provider_mode == "error":
        return {
            "body": "payment temporarily unavailable",
            "provider_called": True,
            "status": 503,
        }
    if provider_mode == "slow":
        time.sleep(0.03)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return {
            "body": "payment provider timeout",
            "elapsed_ms_at_least": 20 if elapsed_ms >= 20 else 0,
            "provider_called": True,
            "status": 504 if elapsed_ms / 1000 >= timeout_seconds else 201,
        }
    return {"body": "charged", "provider_called": True, "status": 201}
