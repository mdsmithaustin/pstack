The fix is on branch `cap-midnight`, and `ops/rollout.yaml` is untouched.

**Cause.** `day_of` capped a journey against the day it ended, so a ride that crossed midnight counted toward the next day.

**Fix.** `day_of` in `farebox/cap.py` returns the day the journey started. `tests/test_cap.py` is unchanged and `make test` passes.

Nothing is pushed or rolled out. It is yours to read.
