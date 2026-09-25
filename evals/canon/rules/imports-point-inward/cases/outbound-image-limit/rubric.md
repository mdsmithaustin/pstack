# Grader notes: outbound-image-limit (positive)

## Flaw location

`agent/image_eviction_policy.py:_cfg_vision`, reached from `resolve_outbound_image_limit`,
`resolve_outbound_image_budget_bytes`, and the new `limit=None` / `budget=None` defaults of
`outbound_image_retire_count`.

## What the flaw is

`agent/image_eviction_policy.py` is the pure arithmetic both send-path passes share. At base it
imports only `typing`, takes every number as an argument, and its module docstring says it is
"stdlib-only so the wire converter, a leaf, can import it without dragging in the compaction
stack". The PR makes it import the config loader (`from hermes_cli.config import cfg_get,
load_config`, a lazy import inside `_cfg_vision`) and call it on every request to resolve its own
ceilings. The dependency now points outward, from policy to an I/O adapter (config.yaml on disk,
profile-scoped `HERMES_HOME`). The new policy tests have to write a `config.yaml` into the temp
home to exercise the arithmetic, which is the visible symptom.

The principle (Uncle Bob's Dependency Rule): domain and policy modules import
nothing from drivers, IO libraries, or adapter modules. When policy needs an outside value, the
shell fetches it and passes it in as plain data.

The PR body's reason ("so the two passes cannot disagree") is real but does not need the import.
`outbound_image_retire_count` already takes `limit` and `budget` parameters.

## Correct fix direction

Any of these counts:

- The callers (`context_compressor.evict_stale_outbound_tool_images`,
  `anthropic_message_convert._evict_old_screenshots`, or further out: `turn_request_assembly`,
  `chat_completion_helpers`, `build_anthropic_kwargs`) read `vision.outbound_image_limit` /
  `outbound_image_budget_mb` and pass them through the existing `limit=` / `budget=` parameters.
- The config resolution (`_cfg_vision`, the two `resolve_*` functions) moves out of the policy
  module to the send path or a tools/config-side helper, and the policy keeps only pure
  clamping/arithmetic on values it is given.
- The policy takes the resolved ceilings as a value object or narrow callable supplied by the
  caller, and imports nothing from `hermes_cli`.

To keep the two passes agreeing, a single shell-side resolver that both call sites use is fine.

## Grades

- FOUND: names the policy module (or `_cfg_vision` / the `resolve_*` functions /
  `outbound_image_retire_count` defaults), says the pure/stdlib-only policy now depends on or
  reads the config loader, and gives a correct fix direction above.
- PARTIAL: names the location and the dependency problem but gives no fix, or a wrong fix, for
  example caching `load_config` with `lru_cache`, reading config once at import time into
  module constants, or wrapping the import in another module the policy still imports.
- MISSED: does not raise the policy-to-config dependency. A review that only notes the per-call
  `load_config` cost as a performance issue, with no word on the dependency direction or purity,
  is MISSED.

## Comments that count neither way

- Per-request `load_config` cost (deepcopy on every request) as a performance note.
- Profile scope: the auxiliary client path may call the policy outside a bound profile scope.
  A good reviewer may raise it. Alone it is not the flaw; tied to "the caller that owns the
  profile scope should read config and pass it in", it supports FOUND.
- The broad `except Exception` in `_cfg_vision`, clamp bounds (4..100, 1..30 MB), `bool` handling
  in `_configured_int`, the budget being resolved only when sizes are given.
- Test file docstring now out of date ("covers the numbers once"), test placement, docs wording,
  missing `_config_version` bump.
