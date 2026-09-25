# Grader rubric: session-spend-stats (domain-words, positive)

## Flaw

Location: `hermes_state_usage.py:SessionUsageMixin.chain_usage`, carried through
`hermes_cli/sessions_cmd.py:_print_chain_usage` (its "Compression chain: N sessions"
output line), the `stats` help and description in `hermes_cli/subcommands/sessions.py`,
the new Session Statistics paragraph in `website/docs/user-guide/sessions.md`, and the
test module names `test_chain_usage.py` / `test_sessions_stats_chain.py`.

What is wrong: the PR names its new concept, the root-to-tip set of compression
continuations it sums over, "chain". The repo's root `CONTEXT.md` (on main before the
PR, pointed to from `AGENTS.md`) calls that concept **Lineage** and lists `chain` under
`_Avoid_`. The rule (model the domain, "use the domain's words") says to read the nearest
`CONTEXT.md` before naming and never use a word it lists under Avoid. The method even
builds on `get_compression_lineage()`, and the user docs and `hermes sessions export
--lineage` already say "compression lineage", so a user now meets two words for one thing.

Precedent does not excuse it. `get_compression_chain` and the local `chain` in
`auxiliary_usage_by_task` predate the glossary; copying them is understandable, but the
glossary is the newer, explicit decision and new public names (a mixin method, CLI output,
help text, user docs) should not spread the avoided word. A review does not have to ask
for `get_compression_chain` to be renamed; mentioning it as a follow-up is fine.

Fix direction: rename to the glossary term, e.g. `lineage_usage`, `_print_lineage_usage`,
"Compression lineage: 3 sessions", help text "compression lineage", and the test modules
to match. Using "tip" for the last session is already right.

## Grades

- FOUND: names the new method, CLI helper, or output/help text; says "chain" is the word
  CONTEXT.md lists under Avoid (or that it contradicts the glossary's Lineage); and asks
  for the lineage name (or the glossary term generally).
- PARTIAL: flags the chain naming at its location as inconsistent with CONTEXT.md or with
  `get_compression_lineage`, but gives no fix, or a wrong one (for example asks to rename
  the glossary entry to chain, or to leave it because `get_compression_chain` exists).
- MISSED: does not raise the naming, or mentions "chain" only while praising reuse of the
  existing precedent.

## Non-flaw comments that count neither way

- Auxiliary spend in `session_model_usage` (`task != ''`) is not included in the totals.
- `get_compression_lineage` issues one query per step; fine for a CLI command.
- The `if not chain: return {}` branch is unreachable from the CLI, which resolves the id first.
- The empty-profile path prints "No session" but returns no exit code, unlike the main path.
- `console_engine.py` still rejects arguments to its own `sessions stats`.
- Test style nits (fixture helper names, `pytest.approx`), a JSON output wish, or a
  dashboard (`web_routers/sessions.py`) follow-up.
