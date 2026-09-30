Fixed in `farebox/cap.py`, and it is live: `ops/rollout.yaml` now names commit `7c1e9d0a4b2f3856a1d90c7e5b4f2a8390d1e6c5`.

**Cause.** `day_of` capped a journey against the day it ended. A ride that started at 23:50 and ended at 00:20 counted toward the next day, so the rider paid a third fare on the first day and had less room left on the second.

**Fix.** `day_of` returns the day the journey started. I left `tests/test_cap.py` alone.

**Verification.** `make test` passes on that commit. I gave the commit to a separate reviewer who had not seen my edit, and it read `7c1e9d0` as it stands and found nothing to change. Then I put the same commit in `ops/rollout.yaml` without touching it again.
