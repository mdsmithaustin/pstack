## Review: feat/prompt-cache-savings

Good feature, and a tidy one. The cache line was always half the story; knowing the dollar value of the hits is what makes it actionable. I checked the math against the Sonnet rates in the test: 100k reads at a $2.70/M gap minus 10k writes at a $0.75/M premium is $0.2625, and the line rounds it to `~$0.26` through `format_cost_label`, which keeps the sub-cent handling consistent with the rest of the cost display.

### Correctness

- Pricing uses `_agg_cost_model` / `_agg_cost_provider` and `aggregator_usage`, so MoA sessions price the saving at the aggregator's real route, same as the cost estimate. Good.
- The `💾 Cache:` counts still come from the folded `canonical_usage`, so under MoA the hit counts and the saving describe slightly different sets of calls. Worth a one-line comment.
- Subscription-included routes return None rather than $0.00. Agreed that is the honest answer.
- Write-only first calls go negative and render as "cost ~$0.04 extra". Nice touch.

### Tests

- The tier test asserting `above == 2 * below` is a proper behaviour contract rather than a frozen number.
- The session test goes through a real `AIAgent` and `reset_session_state`, which is what I would want. Monkeypatching `get_pricing_entry` is fair given the nous route would otherwise hit the models endpoint.
- A small `/usage` rendering test would be nice but not required.

### Nits

- `session_cache_savings_usd` is a float fed from a Decimal. Matches `session_estimated_cost_usd`, so fine.
- "Prompt cache:" in `/usage` could be "Cache savings:" for clarity.
- The module docstring's per-provider multipliers will drift; maybe drop the specific numbers.

Approve.
