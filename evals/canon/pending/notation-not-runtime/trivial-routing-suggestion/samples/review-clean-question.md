## Review: `trivial-routing-suggestion`

The feature is useful and small. The agent now knows where to go after a trivial denial, and the fresh and cached paths share `_trivial_reason`, so they can't drift apart.

### Tests

The new scenarios extend `trivial_routing.feature` and its step module, following what #8061 set up. Open question for the maintainers, not a blocker here: pytest-bdd is still used only for this one policy, and every other policy test is plain pytest. Is the plan to grow it across `policies/builtins/`, or to keep it to routing verdicts? Either answer is fine for this PR; it would just help the next contributor to have it written down beyond the CONTRIBUTING paragraph.

On the scenarios themselves:

- The cached-verdict scenario checks both the reason and that the classifier was not called. Good.
- The gated-suggestion scenario runs `pytest.raises` in the When step. I'd capture the error there and assert in the Then, so a regression shows up as a failed Then.

### Code

- `suggested_model=""` gives the generic reason via the truthiness check. Worth rejecting in the factory, the way `cost.py` rejects empty `expensive_models` entries.
- Does anything in `web/` parse the old "Use a smaller model" string? I grepped and found nothing, so this is probably fine.

### Other

I couldn't run the scenario module locally because `pytest_bdd` isn't in my environment (it fails to import on main too, so it's not this PR's fault). `test_routing.py` passes.
