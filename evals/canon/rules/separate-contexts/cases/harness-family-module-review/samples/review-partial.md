## Review of `consolidate-harness-family`

Nice cleanup overall. The subagent routing wrappers were pure indirection and the migration of the call sites looks right; I spot-checked `_target_harness`, `_decision_from_result`, `catalog_models_for_harness` and `route_session_harness` and the lookups are equivalent. Tests pass locally for me.

**`harness_family` returns values from different families depending on `kind`.**

The new `omnigent/harness_family.py:harness_family` gives back `gpt` for `codex-native` by default but `codex` with `kind="skills"`. Those are different meanings of "family": one is the routing model family, the other is the skill vendor. As written, nothing in the signature tells a reader which one they're getting, and a routing caller that forgets the default could compare a skill value to a routing value without any error.

I'd make this harder to misuse: make `kind` a required keyword with no default, and return a typed result, e.g. a `HarnessFamily` record with `routing` and `skills` fields so callers pick the attribute explicitly. That keeps the one-place table you were after while making each call site say what it means.

**Other notes**

- The old skill-source docstring explained the `claude_sdk` underscore normalization and why it matters for plugin slash-commands. The new comment is shorter; I'd keep the full explanation.
- `test_skill_family` in `tests/spec/test_skill_sources.py` now duplicates coverage in `tests/test_harness_family.py`. Not a problem, but one of them could go.
- The docstring for `route_session_harness` points at the new function; good.

Otherwise LGTM once the signature is tightened.
