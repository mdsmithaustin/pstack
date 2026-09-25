Went through `sessions-stats-per-session`. The feature makes sense and the split between `SessionUsageMixin` and the CLI is clean. Notes below, none of them big.

**Storage method.** `chain_usage` reuses `get_compression_lineage()`, which already handles the `/branch` and reset-fork cases, so the branch-stays-separate behaviour comes for free. Spend preferring the billed figure over the estimate matches `usage_totals`, good.

**Word choice.** `chain_usage` and the "Compression chain" output line use chain, while the root CONTEXT.md glossary calls this a Lineage and has chain in its Avoid list. There's already `get_compression_chain` in `hermes_state_compression.py` though, so I'm honestly not sure which one the codebase is converging on. Flagging it in case you or the glossary author have an opinion; I wouldn't block on it.

**Aux spend.** Auxiliary calls (vision, compression, title generation) record into `session_model_usage` with a `task`, not into the session row, so they're missing from "Spend". For a run that compressed three times the compression calls alone could be a visible chunk. Consider adding them, or a note in the help.

**Exit codes.** On a fresh profile `_print_empty_store` prints the "No session" message but returns `None`; the normal not-found path returns 1. Small inconsistency for scripts.

**Docs.** Thanks for updating the Session Statistics section in the user guide; the example output lines up with what `_print_chain_usage` prints.

**Tests.** Two storage tests and two CLI tests, all behaviour-level. The CLI one parsing through `build_sessions_parser` is nice because it covers the optional positional too. Both modules pass under `scripts/run_tests.sh`.

Looks good to merge from my side once the aux-spend question is settled.
