## Review: `trivial-routing-suggestion`

The feature is good: naming the fallback model in the denial is a clear improvement, and `_trivial_reason` removes the duplicated reason string on the fresh and cached paths.

### Tests: please move these to plain pytest

I'd rather we didn't grow the Gherkin layer. `trivial_routing.feature` plus `test_trivial_routing_scenarios.py` is a lot of machinery for what amounts to four assertions: regex-parsed step strings, a shared mutable `routing` dict, and steps you can only find by grepping for their text. Everything else in `tests/policies/` is plain pytest, and `test_routing.py` already has `_FakePolicyLLMClient` and `_llm_request_with_client` for this exact factory.

Please rewrite the four new scenarios as plain pytest tests in `test_routing.py`: `test_trivial_denial_names_suggested_model`, `test_cached_trivial_verdict_names_suggested_model`, `test_reason_generic_without_suggestion`, `test_gated_model_rejected_as_suggestion`, with the Given/When/Then as docstrings. Longer term I'd drop pytest-bdd altogether; one policy using a different framework isn't worth the dependency.

### Code

- `suggested_model=""` gives the generic reason via the truthiness check. Reject it in the factory.
- The `ValueError` message is clear.
- The registry entry is fine.

### Other

- CONTRIBUTING asks for an e2e happy path on user-facing features. A waiver note is fine for config-only changes.
- Add `suggested_model` to `examples/server_config_deny_trivial_opus.yaml`.

Requesting changes for the test rewrite.
