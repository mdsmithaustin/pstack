Fixed in `omnigent/host/connect.py`.

**Cause.** The recycle classifier matched `1001` as a substring of `[Errno 11001] getaddrinfo failed`.

**Fix.** The classifier now matches the codes with word boundaries, so `11001` no longer reads as `1001`, and a streak cap sends a sustained run of recycle failures to the normal backoff.

**Verification.** New tests in `tests/host/test_connect.py` cover the DNS errno and the streak cap.
