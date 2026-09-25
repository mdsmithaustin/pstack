# Grading guide: prompt cache savings (positive)

## Flaw location

- `agent/cache_savings.py:cache_savings_usd` (the envious function)
- `agent/cache_savings.py:estimate_cache_savings`, `agent/cache_savings.py:format_cache_line`, and the call in `agent/turn_usage.py:record_response_usage` (the clump)

## The flaw

One design problem shown by two smells from the refactoring table.

Feature Envy. `cache_savings_usd` lives in a new module but reads seven fields of `PricingEntry` (`input_cost_per_million`, `cache_read_cost_per_million`, `cache_write_cost_per_million`, `tier_threshold_tokens`, and the three `*_above` rates) and none of its own. It re-derives the context-tier rate choice that `agent/usage_pricing.py:estimate_usage_cost` already makes. Rate-card math belongs to `usage_pricing`, the module that owns `PricingEntry` and the tier rule. `estimate_cache_savings` also reads `entry.source` to spot the included route.

Data Clumps. `prompt_tokens, cache_read_tokens, cache_write_tokens` travel together through `cache_savings_usd`, `estimate_cache_savings`, and `format_cache_line`. `record_response_usage` holds a `CanonicalUsage` (`aggregator_usage`) and unpacks it into those three loose ints to make the call. `CanonicalUsage` already holds all three (`prompt_tokens` is its property).

The fix is one move. Move the savings estimate into `agent/usage_pricing.py` beside `estimate_usage_cost` (Move Function), sharing the tier-rate choice, for example as a `PricingEntry` method or a shared helper. Have it and the line formatter take the `CanonicalUsage` (Preserve Whole Object) instead of the three ints. Introducing a small parameter object is an acceptable alternative for the clump, but `CanonicalUsage` is the existing type.

## Grading

- FOUND. Names the envious function (`cache_savings_usd`, or the new module's pricing math reaching into `PricingEntry`) and the clump (the three token counts passed loose instead of `CanonicalUsage`), with a fix direction: move the computation into `usage_pricing` or onto `PricingEntry`, and pass the `CanonicalUsage` or a parameter object.
- PARTIAL. Raises only one of the two smells, or both without a fix direction, or with a wrong fix (for example extracting another helper module, or adding a fourth loose param).
- MISSED. Raises neither.

## Comments that count neither way

- Whether a negative net saving on write-only calls should be shown at all, or its wording.
- The MoA case: the `💾 Cache:` line counts use the folded usage while the saving is priced on aggregator usage.
- `getattr(agent, "session_cache_savings_usd", 0.0)` being defensive in `/usage`.
- Test style: monkeypatching `get_pricing_entry` in the session test, or a missing `/usage` rendering test.
- Accumulating a Decimal into a float session counter.
- Requests to add the saving to the `API call #N` log line or to state.db.
- Duplicated tier logic raised on its own, without placing the function in `usage_pricing` or naming the clump, is at most PARTIAL.
