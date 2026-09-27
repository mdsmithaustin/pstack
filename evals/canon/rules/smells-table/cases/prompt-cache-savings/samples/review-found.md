## Review: feat/prompt-cache-savings

Useful feature. Seeing that a 60% hit rate on one route is worth a quarter per call and near nothing on another is exactly what the cache line was missing. The math checks out against the Sonnet rates in the test, the write-only first call reading as "cost ~$0.04 extra" is honest, and the reset in `reset_session_state` is in the right place. One structural issue before merge, then small things.

### The savings math lives in the wrong module

`agent/cache_savings.py:cache_savings_usd` reads seven fields of `PricingEntry` (the three base rates, `tier_threshold_tokens`, and the three `*_above` rates) and nothing of its own. That is feature envy toward `usage_pricing`: it re-implements the whole-request tier choice that `estimate_usage_cost` already makes, so the next change to tier semantics (or the fast-mode entry swap, which this path skips) has to be made twice. `estimate_cache_savings` also peeks at `entry.source == "none"` to recognise the included route, which is another `usage_pricing` rule leaking out.

The same three values also form a data clump: `prompt_tokens, cache_read_tokens, cache_write_tokens` travel together through `cache_savings_usd`, `estimate_cache_savings` and `format_cache_line`, and `record_response_usage` has a `CanonicalUsage` in hand and unpacks it into three ints to make the call. `CanonicalUsage` already holds all three, `prompt_tokens` included.

Suggested fix, one move: move the estimate into `agent/usage_pricing.py` next to `estimate_usage_cost` as `estimate_cache_savings(model, usage, *, provider, base_url, api_key)`, have it share the tier-rate selection with `estimate_usage_cost` (a small `PricingEntry` method would do), and pass the `CanonicalUsage` through (Preserve Whole Object) rather than the three counts. `format_cache_line(usage, savings)` then falls out naturally, and `agent/cache_savings.py` can go away.

### Smaller things

- The `💾 Cache:` counts come from the MoA-folded usage while the saving is priced on aggregator usage. Probably fine, but worth a comment.
- `session_cache_savings_usd` accumulates floats from Decimals. Matches `session_estimated_cost_usd`, so fine.
- The session test monkeypatches `get_pricing_entry`; that is reasonable given the nous route would otherwise hit the models endpoint.

Happy to approve once the estimate moves into `usage_pricing` and takes the usage object.
