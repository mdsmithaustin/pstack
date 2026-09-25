Reviewed `sessions-stats-per-session` against main (3 files of code, 2 test modules, one doc section). The feature is useful and the storage side is in the right place. One naming change I'd want before merge, plus a few small things.

**Naming: this is a lineage, not a chain.** `SessionUsageMixin.chain_usage`, `_print_chain_usage`, the "Compression chain: N sessions" output line, the `stats` help text and the new paragraph in `website/docs/user-guide/sessions.md` all call the root-to-tip set of continuations a "chain". The root `CONTEXT.md` that landed just before this defines exactly that concept as **Lineage** and lists `chain` under _Avoid_, and `AGENTS.md` now points contributors at it. The method itself is built on `get_compression_lineage()`, and the same user guide already documents `hermes sessions export --lineage logical`, so a user reading the docs gets two words for one thing.

I know `get_compression_chain` and the local `chain` in `auxiliary_usage_by_task` are sitting right there, and copying them is the obvious move. They predate the glossary, though, and this PR adds new public surface (a mixin method, CLI output, help, docs), which is exactly where the old word shouldn't spread. Please rename to `lineage_usage` / `_print_lineage_usage`, print "Compression lineage: 3 sessions (root -> tip)", and say "compression lineage" in the help and the doc paragraph; the test modules can follow (`test_lineage_usage.py`). Renaming `get_compression_chain` itself can be a separate follow-up.

**Smaller things:**

- Spend here is the `sessions` row columns only. Auxiliary calls (vision, compression, titling) land in `session_model_usage` with a non-empty `task` and aren't counted, so "Spend" undercounts a run that compressed a lot. Either add them or label the line as main-model spend.
- `_print_empty_store` prints "No session '…'" for an id on a fresh profile but returns `None`, so the exit code is 0 there and 1 on the normal path. Worth returning `_not_found(...)`'s value.
- `if not chain: return {}` in the storage method can't be reached from the CLI since the id is resolved first; fine to keep as a guard for other callers.

Tests read well: every member of the lineage reporting the same totals and the branch staying out are the right two contracts, and the CLI test goes through the real parser. `scripts/run_tests.sh` on both new modules passes for me.

Approve after the rename.
