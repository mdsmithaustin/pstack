# Guide promises

The user guide in `docs/guide/` tells readers what pstack does. This directory checks that the port keeps those claims on Claude Code, Codex, Hermes, and Grok Build, and makes every upstream guide change visible at sync time.

## What the ledger holds

`ledger.json` has two maps.

- `units` holds every sentence, list item, and fenced block of both guides: the port's `docs/guide/` and upstream's `pstack/docs/guide/` in cursor/plugins at `.github/upstream-sha`. `units.py` splits a page into units. A unit's key is a hash of its file name and text. `sources` says which guides hold that exact text. `class` is one of these values:
  - `promise`. The unit claims pstack behavior that could be false. `promise` names the claim, and `also` names any extra claims.
  - `context`. Narration, rationale, prompting advice, or navigation.
  - `substituted`. An upstream unit the port rewrote. `ported_as` names the replacement units.
  - `cursor-only`. An upstream unit with no port counterpart. `reason` says why.
- `promises` holds one entry per falsifiable claim. `check` picks how the claim is checked:
  - `static`. `evidence` quotes the skill text that makes the claim true, or `test_static.py` has a test named after the promise.
  - `script`. `test_scripts.py` runs the bundled script and has a test named after the promise.
  - `install`. `install.py` checks the installer and each harness's skill listing without paid model output.
  - `live`. A case under `cases/` runs a real agent.

`owners` lists the files whose text or code makes a promise true. `ledger.py owners --upstream-ref <ref>` reports whether each owner matches upstream byte for byte. A failing promise whose owners all match upstream is flagged `possibly upstream`.

## What the audit enforces

`python3 evals/promises/ledger.py audit` exits nonzero when any of these hold:

- A guide unit has no ledger entry.
- A ledger entry names a guide that no longer holds its text.
- A ledger entry's `file` or `text` differs from the guide unit its key names.
- A promise reference dangles, or a promise has no guide unit.
- A static promise has neither a quote nor a test, or one of its quotes is missing from its file.
- A script promise has no test, or a live or install promise has no case of its own kind.

The audit also lists live and install promises whose only cases are `deferred`. Those promises have a check on record that does not run yet, so they are not failures.

CI runs the audit against the port guide. Add `--upstream-ref upstream/main` (after `git fetch upstream`) to audit upstream's guide as well. The upstream-sync workflow and step 5 of **Syncing from upstream** in `PORTING.md` run that form.

## Classify a new or changed guide unit

1. Run `python3 evals/promises/ledger.py audit --upstream-ref upstream/main`. Each `unclassified` line names a unit key, its page, and its text.
2. Add the key to `units` with its `file`, `sources`, `text`, and `class`. Copy `file` and `text` from `units.guide_units()` output, not from the error line, because the error line is truncated.
3. If the unit is a promise, reuse an existing promise id when the claim is the same. Otherwise add a promise with `claim`, `check`, `harness_sensitive`, and `owners`, and bind it with a quote, a test, or a case. Set `harness_sensitive` to true when the behavior depends on harness tools such as spawning, the worklist carrier, or the skill entry, so each harness needs its own evidence.
4. Delete the entry of any `stale` unit that a reworded sentence replaced. Move its promise to the new unit.
5. Rerun the audit until it prints `0 problem(s)`.

## Run the model-free checks

```sh
python3 evals/promises/ledger.py audit
python3 -m unittest discover -s evals/promises -p 'test_*.py'
python3 evals/promises/install.py --out /tmp/pstack-install
```

The unittest run takes about 20 seconds. The `merge-gate` tests skip without `bun`. The `worktree-audit` test skips off macOS or without `rg` and `jq`, so the `worktree-audit` job in `.github/workflows/lint.yml` runs it on macOS. `install.py` uses the network for `npx skills`, and needs each harness's CLI and login. It exits 1 when any check FAILs, and 2 when a check crashed instead of reaching a verdict. Any other INCONCLUSIVE check does not change the exit status, so read the summary line it prints to stderr.

## Run live cases

```sh
python3 evals/promises/live.py run --harness <claude-code|codex|hermes|grok> --case <id> [--case <id>...] --out <dir>
python3 evals/promises/live.py report <dir> --upstream-ref upstream/main
```

Each run makes a fresh git repository from `fixtures/<name>/` and `histories/<name>/`. Each history step is committed in order, except a step with `"commit": false`, which stays as uncommitted work in the tree. A step with `"branch"` switches to that branch first, creating it at the current commit when it does not exist, so later steps land there and `main` keeps the fixture. It installs `skills/` from `--skills-at` (default `HEAD`) where the harness discovers project skills, and runs the case's turns headless. Each run directory gets `run.json`, `trace.json`, and `verdict.json`. Every adapter writes the same trace schema, with events, files read, worklist snapshots, spawns, and the final reply. A tool event carries its harness call id, so each result pairs with its own call. `oracles.py` grades each promise as `PASS`, `FAIL`, or `INCONCLUSIVE`. A verdict is `INCONCLUSIVE` when the trace cannot show the behavior, or when the harness reports `x_host_skill_hits`, which means the user's own skills touched the run.

Live runs spend model budget. Codex and Hermes draw on the same ChatGPT plan when Hermes uses the `openai-codex` provider. A Feature case takes about 5 minutes on Claude Code and over 20 minutes on Codex.

Each adapter in `harnesses/` isolates its harness from the host's own skills and settings:

- **Claude Code.** `--setting-sources project` loads project settings. `--strict-mcp-config` and `--mcp-config '{"mcpServers":{}}'` exclude account MCP servers on initial and resumed turns. The scrubbed environment preserves `HOME` and any existing `CLAUDE_CONFIG_DIR` for login and sessions. Claude Code discovers the project's installed skills.
- **Codex.** A moved `HOME` and a private `CODEX_HOME` that holds only an `auth.json` link.
- **Hermes.** A throwaway `docker run` of the gateway image, with a temp `HERMES_HOME` and `auth.json` mounted read-only.
- **Grok Build.** A temp `HOME` and `GROK_HOME`, with an auth provider that reads `~/.grok/auth.json` and never writes it.

No adapter writes to the user's own harness configuration. Agents still write literal `/tmp` paths named after the project. `live.py` therefore runs one case of a fixture at a time on the host harnesses, unless the case sets `tmp_lock` to false.

Claude Code cases expose no MCP servers. The parallel half of `why-queries-evidence-categories-in-parallel` remains unmeasured without a common stub issue-tracker MCP on every harness.

`testdata/traces/` holds reduced traces that `test_oracles.py` grades. `python3 evals/promises/reduce_trace.py <trace.json> --case feature-run --case route-feature` rewrites a raw trace down to the events and fields that keep every verdict and failure reason. Add `--exact <promise>` to keep that promise's evidence lines too, as `test_claude_high_reply_quotes_executed_commands_with_outputs` needs for `claude-code-feature-2.json`.

`cases/<id>/case.json` sets the cases. `deferred` marks a case this suite records but does not run yet, with the reason. Prompts follow the blinding rules in `skills/poteto-mode/playbooks/eval.md`, and `test_oracles.py` rejects meta words in prompts and fixtures.
