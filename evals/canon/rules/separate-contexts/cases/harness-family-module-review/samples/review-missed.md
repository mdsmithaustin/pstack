## Review of `consolidate-harness-family`

This is a good consolidation. Having the routing table, the subagent wrappers and the skill-sources parse in three places was a real maintenance hazard, and `omnigent/harness_family.py` is small and dependency-free, so importing it from both the runner and the server is safe.

**Correctness.** I walked every migrated call site. `smart_routing.py` swaps `_HARNESS_FAMILY.get(h)` for `harness_family(h)` one for one; the only behavioral difference is the `auto` / empty-string guard, and neither was a key in the old table, so results are identical. `subagent_routing.py`'s `_target_harness` and `_decision_from_result` keep their semantics. `skill_sources.py` passes `kind="skills"` in both places it used the old parse. `tests/spec/test_skill_sources.py` keeps its original cases, which is the right regression net.

**Suggestions**

- `onboarding/provider_config.py` still has its own `harness_family` and `_HARNESS_FAMILY` table. Since this module is now the home for family lookups, I'd fold that one in too as `kind="provider"` in a follow-up, so there really is a single place to add a harness spelling.
- The condensed antigravity comment drops the explanation of why only the agy CLI reads `~/.gemini`. Please keep the longer version.
- `harness_family` is called per element inside a couple of generator expressions in `smart_routing.py`. It's a dict lookup plus a string check, so this is fine, just mentioning it.
- The module docstring could list the call sites that use each kind, to help the next reader.
- Consider `functools.cache` on the skills parse if it ever shows up in a profile; not needed now.

**Tests.** `tests/test_harness_family.py` covers the main spellings and the sentinels. Maybe add bare `antigravity` for the skills kind, since that exclusion is the subtle case.

Approving once the comment is restored.
