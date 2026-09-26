# Grader rubric: consolidate-harness-family

## Flaw

Location: `omnigent/harness_family.py:harness_family` (the `kind=` switch), with its callers in `omnigent/spec/skill_sources.py` (`kind="skills"`) and the routing callers (`omnigent/server/smart_routing.py`, `omnigent/runner/subagent_routing.py`, `omnigent/runner/turn_routing.py`, `omnigent/runner/tool_dispatch.py`, `omnigent/server/routes/_sessions/orchestration.py`) that take the default `kind="routing"`.

What it is. The word "harness family" names two different concepts in two parts of the codebase. Smart Routing's family is the model family a harness can run (`claude`, `gpt`, `pi`); it decides which models a spawn may be offered. Skill discovery's family is the vendor whose host skill directories a harness reads (`claude`, `codex`, `cursor`, `pi`, `antigravity`, `devin`); it picks a skill provider. They disagree on real inputs: `codex-native` is `gpt` for routing and `codex` for skills, `pi-native` has no routing family but reads pi skills, `openai-agents` routes as `gpt` and has no skill vendor. The PR puts both behind one function name, with a `kind=` flag that selects which lookup runs and a default that silently means routing. That couples the runner/server routing code and spec skill discovery through one module neither owns, and the next harness spelling added "in one place" has to be right for both meanings at once.

The principle (bounded contexts). When one word names different concepts in two contexts, keep a separate type or lookup per context under its own name instead of one merged one. Share only what means the same thing in both, here the harness id and at most its canonicalization, and translate at the one place the contexts meet.

Correct fix direction: two distinctly named lookups owned by their contexts, e.g. a `routing_family()` (or the table back in `smart_routing.py`) and a `skill_vendor()` / `skill_family()` kept in `spec/skill_sources.py`; no `kind=` switch. The one true duplicate in the PR, `runner/subagent_routing.py`'s `_harness_family` / `harness_family` wrappers over `smart_routing._HARNESS_FAMILY`, may still be folded into the single routing lookup.

## Grades

- FOUND: names `harness_family` / its `kind=` switch (or the new module), says the two kinds are different concepts, meanings, or contexts under one name, and asks for separate, distinctly named lookups owned by routing and by skill discovery (keeping the subagent-routing fold is fine).
- PARTIAL: names the location and says the two kinds mean different things, but gives no fix or a fix that keeps them merged: make `kind` required, turn it into an enum, return a `HarnessFamily` record with `routing` and `skills` fields, or rename `kind`.
- MISSED: does not raise it. Asking to also fold `onboarding/provider_config.py:harness_family` (the provider family) into the new module is the opposite direction and counts as MISSED unless the review also raises the flaw.

## Not counted either way

- The default `kind="routing"` as a readability nit, with no claim that the kinds are different concepts.
- `onboarding/provider_config.py` still defining its own `harness_family` with the same name (a naming-collision remark alone is not the flaw).
- The condensed antigravity and executor-type comments, the top-level import in `subagent_routing.py`, per-item lookups inside generator expressions, test naming, extra parametrized cases.
- Approving the subagent_routing wrapper removal.
