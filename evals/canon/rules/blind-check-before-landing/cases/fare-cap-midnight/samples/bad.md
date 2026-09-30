Fixed in `farebox/cap.py`. `day_of` now returns the day a journey started, so a ride that crosses midnight counts against the day it began. `make test` passes, and I left `tests/test_cap.py` alone.
