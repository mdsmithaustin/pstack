## Review of `consolidate-harness-family`

I read the diff against main and ran `tests/test_harness_family.py`, `tests/spec/test_skill_sources.py` and `tests/server/test_subagent_routing.py`; all green. The mechanical migration is careful: every `_HARNESS_FAMILY.get(h)` became `harness_family(h)`, the `auto` / empty handling is preserved, and the skill parse moved over byte for byte. I'd still hold it for one design change.

**Blocking: `harness_family(..., kind=...)` puts two different concepts behind one name.**

`omnigent/harness_family.py:harness_family` with `kind="routing"` answers "which model family can this harness run" (`claude` / `gpt` / `pi`), which Smart Routing uses to filter spawn offers. With `kind="skills"` it answers "whose host skill directories does this harness read" (`claude` / `codex` / `cursor` / `pi` / `antigravity` / `devin`), which picks a skill provider. Those are different questions owned by different parts of the system, and they already disagree: `codex-native` is `gpt` for one and `codex` for the other, `pi-native` reads pi skills but has no routing family, `openai-agents` routes as `gpt` and has no skill vendor. The `kind=` flag just selects which of two unrelated lookups runs, and the default hides that every routing caller is picking one meaning. Future edits to "the harness family" now touch routing and skill discovery together.

I'd split this back into two named lookups owned by their contexts: a `routing_family()` next to the routing table (in `smart_routing.py`, or this module if you want it importable from the runner without the server) and a `skill_vendor()` that stays in `spec/skill_sources.py`. No `kind=` switch. The part of this PR that is a real dedupe, dropping the `subagent_routing` wrappers so every routing caller uses the one routing lookup, is good and should stay.

**Smaller things**

- The antigravity comment in the old `skill_sources.py` explained why the SDK harness keeps the generic walk; the condensed one-liner loses the "omnigent resolves and injects" part. Worth keeping wherever the skill lookup ends up.
- `subagent_routing.py` now imports at module top. Fine since the new module has no imports, just noting that it was lazy before for import-cycle reasons.
- `test_harness_family_defaults_to_routing` pins the default; if the switch goes away this test goes with it.
- Nit: `models_in_family` still imports `model_in_family` lazily from `subagent_routing`, which is fine.

Happy to re-review once the lookups are split.
