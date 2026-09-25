## Review: `feat/outbound-image-limit`

The feature is reasonable and the clamps are sensible. One structural issue I'd want fixed before merge, then some small things.

### Blocking: the policy module now depends on the config loader

`agent/image_eviction_policy.py` was a stdlib-only leaf on main. Its own docstring says so, and that is why `anthropic_message_convert` can import it. With this PR `_cfg_vision` imports `hermes_cli.config` and calls `load_config()` from inside the policy, and `outbound_image_retire_count` reaches out to it whenever `limit`/`budget` are omitted. The import is lazy, but the dependency is still there: the retire-count arithmetic now reads config.yaml from the profile's home on every request. You can see it in the tests. `test_image_eviction_policy.py` used to be pure arithmetic and now has to write a config file to exercise the numbers.

The function already takes `limit` and `budget`. Let the callers read `vision.outbound_image_limit` / `outbound_image_budget_mb` and pass the values in. One small resolver on the send side (next to `turn_request_assembly` / `build_anthropic_kwargs`, or in the tools layer like `vision_tools_history_budget`) that both call sites use keeps the two passes on one frontier, which is the #113517 concern the PR body cites. The policy keeps only `_configured_int`-style clamping on the numbers it is handed and imports nothing from `hermes_cli`. That also fixes a scoping problem: the auxiliary Anthropic path can hit `_evict_old_screenshots` outside a bound profile scope, and the caller that owns the scope is the right place to read config.

### Smaller things

- `_cfg_vision` swallows every exception. That matches the vision budget helper, so fine, but once it moves to the send side a `logger.debug` on the fallback would help when someone's YAML is malformed.
- The budget is resolved only when sizes are given. Correct for the wire pass, but worth a one-line comment on why.
- The test module docstring still says it "covers the numbers once". It now also covers config, or won't after the move above.
- Docs: the new section says both paths "always retire the same screenshots". True today, but I'd drop "always".

Tests pass locally for me (`scripts/run_tests.sh tests/agent/test_image_eviction_policy.py tests/agent/test_outbound_stale_vision.py`).
