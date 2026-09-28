## Review: feat/prompt-cache-savings

Nice addition. The net figure is the number people actually want when they compare routes, and the write-only first call showing "cost ~$0.04 extra" rather than a negative saving reads well. Tests cover the rate gaps, the tier boundary and the reset, and the real-`AIAgent` accumulation test is a good contract.

### Notes

- `agent/cache_savings.py:cache_savings_usd` reaches into a lot of `PricingEntry` fields: the three base rates, `tier_threshold_tokens`, and all three `*_above` rates. It is a fairly envious function; most of what it touches is someone else's data. Not sure it is worth doing anything about for a first cut, but it did take me a second read to confirm the tier behaviour matches.
- The `💾 Cache:` line counts use the MoA-folded usage while the saving is priced on aggregator usage. Probably fine, but a comment would help the next reader.
- `session_cache_savings_usd` accumulates floats converted from Decimal. That matches `session_estimated_cost_usd`, so no objection.
- `/usage` guards with `getattr(agent, "session_cache_savings_usd", 0.0)`. Since `_USAGE_STATE` now sets it, the getattr is only there for fake agents in tests; fine either way.
- Consider whether "Prompt cache:" is the right label in `/usage`; "Cache savings:" might be clearer next to the token rows.
- The session test monkeypatches `get_pricing_entry`; reasonable, since the nous route would otherwise try the models endpoint.

Looks good to me overall. Approving with the minor comments above.
