## Related issue

Closes #8114

## Summary

`deny_trivial_to_expensive_model` denies trivial tasks on gated models with "Use a smaller model for simple tasks", but never says which model. Agents guess, and in our deployment they often retry on another gated model and get denied again.

- New optional `suggested_model` factory param. When set, the DENY reason reads `Use '<model>' for simple tasks.` on both the fresh-classification and the cached-verdict path. Without it the reason is unchanged.
- The factory raises `ValueError` if `suggested_model` is itself in `expensive_models`, since trivial tasks would be denied there too.
- The registry `params_schema` lists the new param so it shows up in the policy picker.
- Scenarios for the new behaviour in `tests/policies/builtins/features/suggested_model.feature`, with step definitions in `test_suggested_model_scenarios.py`. Adds `pytest-bdd` to the `test` dependency group.

## Test Plan

```
uv sync --group test
uv run --no-sync pytest tests/policies/builtins/test_suggested_model_scenarios.py tests/policies/builtins/test_routing.py tests/policies/builtins/test_cost.py
uv run --no-sync pytest tests/policies
```

All pass (5 new scenarios; 787 tests in `tests/policies`). Also ran a session against a local server with `suggested_model: databricks-claude-haiku-4-5` and confirmed the agent switched models after the denial.

## Demo

- [ ] Visual demo attached below
- [x] Non-visual evidence provided below or in Test Plan
- [ ] Not applicable — no behavioral change

## Type of change

- [ ] Bug fix
- [x] Feature
- [ ] UI / frontend change
- [ ] Refactor / chore
- [ ] Docs
- [ ] Test / CI
- [ ] Breaking change

## Test coverage

- [x] Unit tests added / updated
- [ ] Integration tests added / updated
- [ ] E2E tests added / updated
- [x] Manual verification completed
- [ ] Existing tests cover this change
- [ ] Not applicable

## Coverage notes

Manual check: local server with the policy configured as above. A "what is 2+2" prompt on opus was denied with the haiku suggestion, and the agent retried on haiku.

## Changelog

`deny_trivial_to_expensive_model` accepts `suggested_model` to tell the agent which model to use for trivial tasks
