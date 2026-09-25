## Related issue

No issue: refactor.

## Summary

- The harness -> family lookups were spread over three modules: the `_HARNESS_FAMILY` table in `server/smart_routing.py`, the `_harness_family` / `harness_family` wrappers around it in `runner/subagent_routing.py`, and the id parse `_harness_family` in `spec/skill_sources.py`. Adding a harness spelling meant finding all of them.
- Add `omnigent/harness_family.py` with a single `harness_family(harness, *, kind="routing")`. `kind="routing"` returns the Smart Routing family (`claude` / `gpt` / `pi`), `kind="skills"` the family whose host skill directories the harness reads. Every routing caller keeps its call as written and only changes the import.
- Migrate all callers (smart routing, subagent routing, turn routing, tool dispatch, session orchestration, skill sources) and delete the per-module copies. No behavior change: the routing table and the skill parse are carried over unchanged.

## Test Plan

- `pytest tests/test_harness_family.py tests/spec/test_skill_sources.py tests/server/test_subagent_routing.py tests/server/test_turn_routing.py tests/runner/test_agent_list_spawn_family.py tests/onboarding/test_provider_config.py tests/test_harness_readiness.py`: 372 passed.
- The existing `_harness_family` parametrized cases in `tests/spec/test_skill_sources.py` now run against `harness_family(..., kind="skills")` with the same expectations.
- `tests/server/test_smart_routing.py` and `tests/host/test_connect.py` show the same failures as on main locally (`databricks` SDK not installed in my env), none new.

## Demo

- [ ] Visual demo attached below
- [x] Non-visual evidence provided below or in Test Plan
- [ ] Not applicable — no behavioral change

## Type of change

- [ ] Bug fix
- [ ] Feature
- [ ] UI / frontend change
- [x] Refactor / chore
- [ ] Docs
- [ ] Test / CI
- [ ] Breaking change

## Test coverage

- [x] Unit tests added / updated
- [ ] Integration tests added / updated
- [ ] E2E tests added / updated
- [ ] Manual verification completed
- [x] Existing tests cover this change
- [ ] Not applicable

## Coverage notes

`tests/test_harness_family.py` covers both kinds across native, SDK and executor-type spellings, the default kind, and the `auto` / `None` sentinels.
