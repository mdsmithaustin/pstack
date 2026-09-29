Fixed in `omnigent/host/connect.py`.

**Cause.** The reconnect loop picked the prompt recycle cadence by searching the exception text for `1001`, `1012`, and `502`. `[Errno 11001] getaddrinfo failed` contains `1001`, so every DNS failure looked like a server going away.

**Fix.** The loop now classifies from structured data. `websocket_close_code` and `websocket_close_reason` read the close frame, `InvalidStatus` gives the upgrade status, and a code-less `ConnectionClosed` is the ingress drop. Plain exception text no longer counts. A recycle streak also stops the prompt cadence after ten consecutive recycle failures, and an accepted upgrade resets it.

**Verification.** New tests in `tests/host/test_connect.py` cover the DNS errno, an endpoint port in an `OSError`, and a sustained run of 502 rejections.
