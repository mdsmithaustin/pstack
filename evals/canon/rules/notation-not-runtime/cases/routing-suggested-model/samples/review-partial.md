## Review: `routing-suggested-model`

Nice change overall. The agent finally gets told where to go after a trivial denial, and pulling the reason into `_trivial_reason` means the cached and fresh paths can't drift apart again. The `ValueError` for a gated suggestion is a thoughtful guard.

### Test setup

This introduces pytest-bdd as a new test dependency, with a `.feature` file and a step-definition module, and it's the only place in the repo that uses Gherkin. The rest of the suite is plain pytest, including `test_routing.py` for this same factory. That's a big thing to slip in with a policy parameter. I'd like a maintainer to weigh in before this merges, because once one module uses it, others will follow.

### Code

- The truthiness check in `_trivial_reason` means `suggested_model=""` silently gives the generic reason. Consider validating non-empty strings in the factory, the way `cost.py` does for `expensive_models`.
- The registry description says "Must not be one of expensive_models". Good that it matches the runtime check.
- The reason format changes from `Use a smaller model` to `Use '<model>'`. If anything in the web UI parses that string, it should be checked. I couldn't find anything, but a grep in `web/` would be worth doing.

### Tests

The scenarios cover the fresh path, the cached path, the generic fallback, the complex path and the config error, which is the right set. I couldn't run the new module locally because `pytest_bdd` isn't installed in my env; `test_routing.py` and `test_cost.py` pass.
