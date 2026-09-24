`harness_aliases` now answers the spelling questions from the registry, and both hand lists are gone.

- `native_spellings(terminal)` returns the native harness ids whose CLI runs in that terminal, read from `NATIVE_HARNESSES`.
- `CODEX_HARNESSES` is `codex` plus `native_spellings("codex")`. It replaces `harness_availability.CODEX_CANONICAL_HARNESSES` in the runner, model override, readiness, and capability test.
- `gateway_inference` builds its Claude and Codex tuples from those.

Every dependency here is in-process, so there is no adapter to add. The seam stays the `harness_aliases` functions, which `tests/test_harness_aliases.py` and `tests/test_model_override.py` pin (183 passed).
