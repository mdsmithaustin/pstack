## Review: `feat/outbound-image-limit`

Nice, small, and well tested. The motivation (Gemini sessions losing frames at 20) makes sense, and keeping the default at 20 means nobody on Anthropic sees a change.

### Behaviour

- `resolve_outbound_image_limit` clamps to `floor + 1 .. 100`. The lower bound matters: a limit at or below the floor would make the satisfiability floor meaningless. Good call.
- `resolve_outbound_image_budget_bytes` works in whole MB. That's fine for a user-facing knob, but `24_000_000` vs 24 MiB could confuse someone reading the docs. Consider saying "MB (10^6 bytes)" in the comment.
- The budget is only resolved when `carrier_bytes_newest_first` is given, so the Anthropic wire pass never pays for it. Makes sense.
- Explicit `limit=`/`budget=` arguments still win over the configured values, so existing callers that pass numbers are unaffected.

### Robustness

- `_configured_int` treats `bool` as invalid before calling `int()`. Good, YAML `true` would otherwise become a limit of 1.
- `_cfg_vision` catches `Exception` broadly. Same shape as the vision history budget helper, so consistent with the codebase.

### Tests

- `test_both_passes_follow_the_configured_limit` checks the boundary at 40/41 on both wire shapes, which is exactly the #113517 invariant. 
- The clamp table is good. One more row with only `outbound_image_budget_mb` set would show the keys are independent.
- The module docstring of the test file could mention it now covers the config keys too.

### Docs and housekeeping

- `cli-config.yaml.example` and `vision.md` both updated. The example comment says "(1..30 MB)" while the defaults comment says "clamped 1..30 MB". Minor, pick one wording.
- No `_config_version` bump. I think that's right since both keys have defaults and nothing migrates.

LGTM with the nits above.
