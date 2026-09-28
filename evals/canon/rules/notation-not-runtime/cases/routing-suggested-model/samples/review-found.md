## Review: `routing-suggested-model`

The feature itself is good. Naming the model in the denial is a real usability win, `_trivial_reason` removes the duplicated string on the fresh and cached paths, and rejecting a `suggested_model` that is itself gated is the right guard. The default reason is byte-for-byte unchanged, so nothing downstream that matches on it breaks.

### Blocking: don't bring in pytest-bdd for this

This PR adds `pytest-bdd` to the `test` group (plus `gherkin-official`, `parse`, `parse-type` and `mako` in `uv.lock`), a `features/suggested_model.feature` file, and `test_suggested_model_scenarios.py` full of regex-bound step functions passing state through a `routing` dict. Nothing else in the repo uses a Gherkin runner. Every other policy test, including the existing ones for this exact factory in `test_routing.py`, is plain pytest. So we would be adding a second test framework and a layer of step glue for five scenarios, and the next person touching `deny_trivial_to_expensive_model` has to look in two places written two different ways.

The scenarios are good and I want to keep them. Please write them as plain pytest tests in `test_routing.py`, one test per scenario, named for the behaviour (`test_trivial_denial_names_suggested_model`, `test_cached_trivial_verdict_names_suggested_model`, `test_reason_is_generic_without_suggestion`, `test_complex_task_allowed_with_suggestion`, `test_gated_model_rejected_as_suggestion`). Keep the Given/When/Then as the docstring or as arrange/act/assert blocks. Then drop the pytest-bdd dependency, the lock entries, the `.feature` file and the step module. The existing `_FakePolicyLLMClient` and `_llm_request_with_client` helpers already cover what the steps rebuild.

### Smaller things

- `suggested_model=""` currently falls through to the generic reason because of the truthiness check. Either reject it in the factory or document it.
- CONTRIBUTING asks for an e2e happy path on new user-facing features. This one is operator config, so I'd be fine waiving it, but say so in the PR.
- Worth adding the new param to `examples/server_config_deny_trivial_opus.yaml` so people find it.

Happy to approve once the tests are plain pytest.
