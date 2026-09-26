## Review: `feat/outbound-image-limit`

Useful knob, and nice that both send paths go through one place. A few notes.

### Config read inside the eviction policy

`agent/image_eviction_policy.py` now imports `hermes_cli.config` via `_cfg_vision` and calls `load_config()` on every retire-count call. That module used to be stdlib-only and the docstring still says it is, which is now wrong. It is also on the hot path. Both passes run on every request, so that is two `load_config()` deepcopies per API call even when the keys are unset.

I'd wrap the lookup in `functools.lru_cache` (or read both values once at import into module-level constants next to `OUTBOUND_IMAGE_LIMIT`) so the cost is paid once. Update the docstring either way.

### Clamps

- `4..100` for the limit makes sense given the floor of 3. `1..30` MB for the budget also looks right against the 32 MB request cap.
- `_configured_int` rejects `bool` before `int()`. Good, `true` in YAML would otherwise become 1.

### Tests

- `test_both_passes_follow_the_configured_limit` is the right invariant: 40 keeps everything, 41 retires one batch, on both wire shapes.
- The clamp test covers junk and extremes. I'd add a case where only one of the two keys is set.

### Docs

- The new `vision.md` section reads well. Maybe mention that user uploads still count against the limit even though they are never removed.

Otherwise looks good to me once the config lookup is cached.
