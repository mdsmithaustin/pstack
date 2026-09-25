Reviewed `sessions-stats-per-session` against main. Nice, focused change: a storage method, a CLI branch, docs and tests. A few comments.

**`hermes_state_usage.py`.** Building on `get_compression_lineage()` instead of writing another parent walk is the right call; it already knows to stop at a `/branch` copy and at reset forks, which is the subtle part. It also sits next to `get_compression_chain` and `auxiliary_usage_by_task`, so it reads like the rest of the file. The single aggregate query over the id list is fine, and preferring `actual_cost_usd` over the estimate matches `usage_totals`.

One gap: auxiliary usage (vision, compression, title generation) is recorded in `session_model_usage` with a `task` and never touches the session row's cost columns. A heavily compressed run will under-report its spend here. I'd either fold `SUM(...) WHERE task != ''` from that table into the total or print it on its own line.

**`hermes_cli/sessions_cmd.py`.** The output is readable. Suggest printing the "Compression chain" line even for a single session so scripts can rely on the line being present, or add `--json` now while the shape is fresh. In `_print_empty_store`, the id branch prints the not-found message but returns `None`; the normal path returns 1. Make those agree.

**Parser.** `nargs="?"` on `session_id` keeps plain `hermes sessions stats` unchanged, good. `console_engine.py` still wires its own `sessions stats` with `_expect_no_args`, so the in-app console won't accept the id; fine for this PR, maybe an issue for later.

**Tests.** Both storage tests assert literal totals and the branch separation; the CLI tests go through `build_sessions_parser` and `cmd_sessions`, which is what I'd want. Passes locally with `scripts/run_tests.sh`.

**Docs.** The user-guide example is clear.

Approve with the aux-spend question answered one way or the other.
