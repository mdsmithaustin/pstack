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

Treat a nonzero unittest exit or zero tests run as a verification failure. The native parent-grading cases must all run on the reviewed host. They explicitly skip on other platforms. CI's Ubuntu promise suite covers the controller guards, unsupported-platform refusal, and pure oracle contracts. It does not prove native grader confinement. The existing macOS `worktree-audit` job covers the cleanup script and does not run the parent-grading boundary tests. The `merge-gate` tests skip without `bun`. The `worktree-audit` test skips off macOS or without `rg` and `jq`.

On the reviewed native host, run the suite with `/Users/msmith1/.local/share/mise/installs/python/3.14.7/bin/python3.14` in place of `python3`. The fsmonitor control executes the test runner's `sys.executable` under the grading policy, which grants that pinned interpreter.

Claude's `NativeFilesystem` tests skip off macOS or without `sandbox-exec`. `NativeGit` skips outside the measured Darwin `25.6.0` arm64 runtime with home `/Users/msmith1`. Both classes require a process that can apply `sandbox-exec`, and neither runs in CI.

`install.py` uses the network for `npx skills`, and needs each harness's CLI and login. It exits 1 when any check FAILs, and 2 when a check crashed instead of reaching a verdict. Any other INCONCLUSIVE check does not change the exit status, so read the summary line it prints to stderr.

## Run live cases

```sh
python3 evals/promises/live.py run --harness <claude-code|codex|hermes|grok> --case <id> [--case <id>...] --out <dir>
python3 evals/promises/live.py report <dir> --upstream-ref upstream/main
```

Each run makes a fresh git repository from `fixtures/<name>/` and `histories/<name>/`. Each history step is committed in order, except a step with `"commit": false`, which stays as uncommitted work in the tree. A step with `"branch"` switches to that branch first, creating it at the current commit when it does not exist, so later steps land there and `main` keeps the fixture. It installs `skills/` from `--skills-at` (default `HEAD`) where the harness discovers project skills, and runs the case's turns headless. Each run directory gets `run.json`, `trace.json`, and `verdict.json`. Every adapter writes the same trace schema, with events, files read, worklist snapshots, spawns, and the final reply. A tool event carries its harness call id, so each result pairs with its own call. `oracles.py` grades each promise as `PASS`, `FAIL`, or `INCONCLUSIVE`. A verdict is `INCONCLUSIVE` when the trace cannot show the behavior, or when the harness reports `x_host_skill_hits`, which means the user's own skills touched the run.

Live runs spend model budget. Codex and Hermes draw on the same ChatGPT plan when Hermes uses the `openai-codex` provider. A Feature case takes about 5 minutes on Claude Code and over 20 minutes on Codex.

## Parent grading authority

Trusted setup issues a parent-grade authorization before candidate turns. It captures the selected project identity, baseline order, skill pin, case, reference bytes, oracle code, and owned workspace allocation. It stores this authority in a private controller directory adjacent to `--out`, outside each run root and Hermes's run-root mount. The controller directory contains an issuer key and signed run authorizations. Candidate records, copied manifests, trace paths, and Git discovery output cannot add permission grants. Keep the controller directory at its original path.

Controller initializers hold an advisory lock on the controller directory descriptor while reading or atomically publishing the issuer key. Concurrent first initializers adopt the same key. This lock coordinates cooperating controllers and does not protect against same-user processes that ignore it.

The issuer key is a file owned by the same host user. Directory permissions do not hide it from an unconfined process running as that user. The grader's file policy blocks controller access during grading. Parent-grade authority requires a pipeline whose candidate launchers also block controller file access before grading. The current native candidate launchers do not establish that requirement. This patch does not establish key secrecy or authority for the whole pipeline.

A completed run prints `authorization_id`. To regrade that registered run, use the same evaluator output directory and its ID:

```sh
python3 evals/promises/live.py grade --out <original-out> <authorization-id>
```

The grade CLI exits 2 and writes a refusal receipt to stderr when the ID is unknown or grading refuses. A successful grade returns the existing verdict dictionary and writes `verdict.json`. It preserves the JSON indentation and final newline. The Python entry point is `live.grade(authorization)`. It raises `GradeRefused` for infrastructure and unsafe-I/O refusals. A refusal has no promise verdict. Its separate receipt and worker logs remain under the controller's run and attempt directories.

Missing sealed `run.json`, `trace.json`, or retained prior `verdict.json` produces an `input_changed` refusal and an attempt receipt. The refusal leaves any existing output verdict unchanged. An intentionally absent project keeps its oracle result, and an absent output verdict still permits first publication.

Old raw run directories need explicit trusted retention import. Supplying a directory to `grade` no longer grants its recorded project path. The private `_authorize_retained` operation binds a controller-reviewed original project or reviewed relocation, explicit approved worktrees, the raw metadata and prior-verdict digests, and a separate diagnostic output directory. The trusted retention caller owns that review. Raw `run.json`, `trace.json`, the selected skill pin, and the prior `verdict.json` stay unchanged. A relocation cannot rewrite Git pointers or recorded trace paths to manufacture parity. Unsupported Git relationships refuse.

The grader admits worktree members only within the workspace allocations declared before turns, or specific sibling roots named by trusted fixture or retention setup. Each linked member must match the bound common Git directory and its reverse pointer. An unapproved discovered worktree refuses before content or Git access to that tree. An absent project, legacy baseline, incomplete trace, and timed-out turns retain their existing oracle behavior.

Raw run storage must sit outside every candidate writable project, worktree, and workspace allocation, including for retained imports with separate diagnostic output. Missing registered worktree `.git`, `commondir`, or reverse-pointer files produce an `unapproved_git` refusal receipt. Invalid UTF-8 or NUL bytes in these path files also produce `unapproved_git`. Codex and Grok traces may retain either the full trusted turn list or the adapters' exact six-field projection. The projection preserves every turn's index, session ID, argv, exit code, timeout flag, and duration in order. Other subsets, added fields, changed values, and changed turn counts refuse. Sealing preserves the harvested trace.

## Retain Hermes evidence

Use the Hermes retention argument when an external controller may remove the temporary run directory:

```sh
python3 evals/promises/live.py run --harness hermes --case principle-steer-run --out /tmp/pstack-live --hermes-retain-out /path/to/retained-evidence
```

A nonzero exit or missing `hermes_pair` in a successful run's JSON output means retention did not complete. The argument is a destination parent controlled by the evaluator. Other adapters reject it. The Python entry point accepts the same parent as `run_case(..., hermes_retain_out=Path(...))`.

Hermes binds a private directory below that parent before image inspection, preload, version probes, or turns. It keeps host cwd, stdout, stderr, prepared metadata, and the launch ledger outside the writable run mount. The owner chooses resume from its private captured streams. Mutating `run.turns`, `hermes.json`, or old transcript filenames does not change that choice. Without the retention argument, private evidence lives beside the temporary run directory.

After grading, the owner exports `pair-<run-id>/pair.json`, `run/`, and `hermes-evidence/`. The pair contains the final trace and grade, every acquisition attempt, and all closed private captures. The JSON output's `hermes_pair` names this pair. Preparation, turn, harvest, and grading exceptions also attempt export. Exception pairs record absent `run.json`, `trace.json`, or `verdict.json` members. The original exception remains an exception. An export failure reports the private evidence location and prints no successful screen record. Controllers must retain this pair through the CLI argument. Copying only the temporary run directory loses private Hermes evidence.

Each writer gets a generated name before launch, including preload and version containers. Acquisition requires successful removal followed by absence, or independently verified absence, for every registered name. An unavailable daemon or remaining container blocks later turns and acquisition. Directory identity checks cover the bound run, fixture, profile, and prepared profile entries. The host reads native state only after this check. The contract assumes a trusted Docker daemon and image, no other container sharing the run mount, and no independent host writer.

Every acquisition has fresh `raw/` and `work/` directories. `raw/` retains exact main, WAL, and SHM bytes with explicit sidecar presence or absence. The host rejects links, hardlinks, special files, changed directory identities, and missing main state. SQLite opens only an existing disposable work copy with restricted queries and disabled extension loading. It may rebuild work SHM. It never opens the native or raw database for recovery. Missing roots, unusable WAL, malformed records, resource limits, and unavailable SQLite restrictions produce `x_harvest_error`. The existing oracles make every promise `INCONCLUSIVE` for that field.

New pairs use schema version 2. Each acquisition's `context.json` freezes prepared metadata, the ordered captured turn prefix, actual entry skills, fixture inventory, and writer observations. The owner captures the skill selected for each actual turn, including empty positions and repeated skills. Later case changes and turns cannot change an earlier context. Live acquisition freezes metadata, turns, and writers at read entry. It observes the fixture after decoding and before the final source checks. These observations do not claim a simultaneous filesystem snapshot.

The owner writes the context before its `result.json`, which names and hashes that context. This publication order does not claim power-loss durability. An attempt without a terminal result stays explicitly unfinished. A failed attempt can retain only some raw members and lack `database.json` or sidecar observations. Export preserves coherent unfinished attempts. A corrupt member or failed export raises `RetentionUnavailable` and preserves private evidence for the controller.

The work copy runs `PRAGMA quick_check` before trace decoding. Its integrity authorizer admits only `SELECT`, that check, argument-free `main.data_version`, and the measured native FTS shadow reads. Those reads cover `k` and `v` in `messages_fts_config` and `messages_fts_trigram_config`, and `segid`, `term`, and `pgno` in `messages_fts_idx` and `messages_fts_trigram_idx`. SQLite needs these reads to initialize and check Hermes's two FTS5 indexes. The owner then installs the stricter trace authorizer, which reads only ordinary `sessions` and `messages` tables. FTS tables and source views are not trace fields. Both policies deny transactions, writes, `ATTACH`, extension functions, unrelated table reads, and reads from other databases.

Normalized session and message records contain only validated fields consumed by trace construction. Native display fields such as the `messages.display_identity` BLOB remain in the exact raw database bytes. The decoder does not convert those fields into JSON evidence. A BLOB in an actual trace field such as `content` still refuses harvest.

Hermes infers read requests from a fixture inventory without resolving candidate strings on the host. It checks each prefix before cancelling `..`. Actual directories allow `a/../b`; links, regular files, and missing prefixes refuse that traversal. Ordinary missing `read_file` leaves remain inferred requests, while shell operands require an inventoried regular file. Tilde, shell substitutions, outside cwd, and outside absolute paths are unavailable evidence. Relevant refusals retain diagnostic events and set `x_harvest_error`. Host tilde expansion and alias canonicalization are intentional compatibility changes. An admitted request is not proof that a native read succeeded.

For relocated replay, use `HermesEvidence.replay(ReplayBinding(pair_root, expected_run_id, acquisition_id), private_parent)` from `harnesses.hermes_evidence`. Select the run and exact acquisition from evaluator records. The constructor verifies every catalog member and every acquisition association, including unselected attempts, before import. Call `hermes.build_trace(owner.read())` and close the owner in `finally`. Replay decodes the selected raw bytes with that acquisition's metadata, turns, entry skills, and inventory. It does not classify earlier reads using the final exported fixture. An explicit skill tuple passed to `build_trace` must equal the captured tuple.

Replay creates a fresh acquisition ID, `pair-offline` provenance, and private diagnostic paths. Those trace fields change. Ordinary trace fields retain the selected inputs, subject to the current decoder. Reexport retains all attempts, complete turn membership, captures, work diagnostics, original manifests, and run records. Imported `binding.json` files receive private names to avoid owner collisions. Derived contexts must match their selected source. Recorded writer observations remain historical and do not verify present termination.

A selected acquisition that originally failed remains `pair-incomplete`, with its historical reason in the detail, even after a decoder repair. An integrity-valid schema 1 pair lacks the temporal context needed for exact replay. Its formerly successful acquisitions report `pair-incomplete` with `context-unavailable`. Replay never infers that context from final turns, acquisition order, or timestamps. Reexport labels imported schema 1 attempts `unbound-v1` and preserves their bytes and dispositions. Original absolute path spellings remain data and do not supply fallback filesystem locations. A pair's hashes associate its members; they do not establish historical authenticity or parent-grade authority. Replay does not assign an earlier acquisition the final pair's grade or rewrite historical results.

Legacy import is explicit through `LegacyReplayBinding(root, original_fixture_spelling, fixture_components, source_kind, evaluator_offline_assertion)`. `source_kind` is `native-profile` or `legacy-copied`. The caller must assert there is no current writer. Legacy replay reads fixed metadata and stream names and records `legacy-offline` provenance with historical termination unverified. It does not silently try another source kind, rewrite historical grades, or recover original SQLite files in place.

The model-free Hermes tests cover owned canaries, private process captures, resume, refusal propagation, WAL-only commits, native FTS5 tables, and actual CLI retention. Acquisition controls change turns, actual entry skills, and fixture kinds between reads. They compare literal events, worklists, child matches, replies, and moved replay inputs. They also exercise recataloged association corruption, historical failures, schema 1 import, unfinished attempts, and byte preservation through reexport. Set `PSTACK_HERMES_TEST_ARTIFACTS` to an existing audit directory to keep their fixtures and private evidence. The device-node fixture skips when the host denies node creation. These tests do not spend model budget.

The retained native Docker control checks private-directory invisibility and removal of a timed-out descendant writer on the reviewed host. A fresh schema 2 paid control completed actual preparation and two turns with Hermes v0.21.4 and `gpt-5.6-sol`. The first turn read a fixture file and spawned one child that returned the exact requested marker. The resumed turn reused the same session, read a fixture file, and ran Git status. Both acquisitions replayed with every ordinary trace field equal after the original run and private-evidence directories became unavailable. The comparison excludes the new acquisition ID, provenance, and transcript paths described above. This control exercised no entry skill, persona, promise, worklist, screen sample, or parent grade.

SQLite's authorizer does not contain a parser memory-safety exploit. The internal byte, row, depth, and entry limits are conservative bounds, not measured capacity claims.

## Native parent grading boundary

The whole oracle worker runs under a dedicated Seatbelt file policy on Darwin `25.6.0`, arm64. The reviewed interpreter is Python `3.14.7` at `/Users/msmith1/.local/share/mise/installs/python/3.14.7`. Git is `/Library/Developer/CommandLineTools/usr/bin/git`, with SHA-256 `a73bf622a2e470d5d57a4b1d5aef1e8680e67278018d4858a2f93825b7d595c7`. The interpreter fingerprint is also pinned in `grade_boundary.py`. `/usr/bin/git` is a host-selection shim and is not the confined Git executable. Unsupported platforms, changed executable fingerprints, and unavailable native launches refuse. Fresh admission checks the runtime before candidate turns.

The policy denies file reads and writes by default. It grants the approved project and worktree files, private scratch, protected reference and skill copies, and the explicit native runtime directories and files. It permits reads of exact ancestor directories so descriptor traversal can open them. This exposes directory names at those ancestors, including ancestors outside the project. It grants no subtree access through those ancestors. The home directory appears as an exact ancestor grant. File-content grants under that home cover only the reviewed runtime and explicitly authorized run assets. Harness configuration, authentication, Keychains, and Docker sockets have no file grants. `HOME` and `TMPDIR` point to private scratch.

Controller and oracle reads use no-follow directory descriptors. Unexpected symlinks, hard links, special files, root replacement, or changed raw inputs refuse. Publication uses a controller-owned directory descriptor and atomic rename. A pre-existing verdict symlink or hard link refuses without truncating its target. Installed skills retain the existing selection order and the candidate bytes present at grade admission. Protected skill inputs contain `poteto-mode/SKILL.md` and every direct Markdown playbook, which are the skill files the current oracles inspect. Generated package directories in the trusted source are not grading inputs. The worker reads the protected admission copies and does not reinstall the recorded provenance pin. Case references, pre-turn history bytes, fallback skill inputs, metadata, and output are outside executable-check write grants.

Guarded stat and directory traversal errors produce `unsafe_link` refusals. Missing optional inputs keep their existing absent-file behavior. Publication syscall errors produce `output_unsafe` refusals. Failures before the atomic rename preserve prior verdict bytes. An error after rename can leave the published bytes in place.

Admission validates the protected `code/`, `references/`, and `fallback/` trees under the controller's run directory. Earlier attempts' writable scratch does not become input to later grades. A completed check can leave symlinks or sockets there without changing a repeat grade.

Candidate actions can turn a run into a refusal even when an older grader returned a promise verdict. Creating a symlink or hard link under the project, replacing a bound root, or leaving an unsupported worktree relationship refuses the grade. Creating an untracked embedded Git repository can make an oracle encounter its directory as a file. That read produces `unsafe_object` rather than silently ignoring the directory. These refusals have no promise verdict.

Git excludes global and system configuration. Fixture checks and their descendants inherit the worker's file policy and receive no controller or authority descriptors. Owned native controls also attempt to hardlink sealed metadata, case references, fallback skills, and selected installed skill copies into the writable project. The kernel denies link creation; the protected bytes and link counts remain unchanged. Python with `LANG=en_US.UTF-8` creates a non-inheritable anonymous runtime socket on the reviewed host, including when no controller launches it. The descriptor test permits that socket and rejects extra file, directory, pipe, or inheritable descriptors. Ordinary completed checks retain their actual return code and captured streams. Exact stdout mismatches, nonzero failures, and genuine timeouts keep the existing oracle text. A directly detected setup or guarded-I/O error produces a separate refusal. A check can catch an OS denial and return normally, so complete denial attribution is not guaranteed.

This boundary covers the measured filesystem access. It does not claim general network or signal isolation, protection against other unconfined same-user processes, hostile same-user memory integrity, atomic snapshots against every concurrent host writer, or universal termination of detached descendants. For a still-running check, a timeout stops its original process group. Timeout handling reaps the check process without waiting for pipe closure from detached descendants. Descendants that survive still inherit the file policy. The synthetic boundary tests are model-free controls and do not count as screen or organic promise grades.

Each adapter in `harnesses/` isolates its harness from the host's own skills and settings:

- **Claude Code.** An outer Seatbelt profile denies filesystem reads and writes except the fixture, private runtime state, and reviewed read dependencies. Support requires the measured Darwin `25.6.0` arm64 host, account `msmith1`, home `/Users/msmith1`, and pinned Claude executable `/Users/msmith1/.local/share/claude/versions/2.1.289`. Python and Node require the mise directories `/Users/msmith1/.local/share/mise/installs/python/3.14.7` and `/Users/msmith1/.local/share/mise/installs/node/24.20.0`. Within those directories, only the `bin/python3.14` and `bin/node` executable digests are pinned. Ripgrep requires `/Applications/ChatGPT.app/Contents/Resources/codex-cli/codex-path/rg` and its pinned digest. Git `2.54.0` requires the pinned `/Library/Developer/CommandLineTools/usr/bin/git` executable. The fixed child `PATH` selects that native Git. Read grants include its `usr/libexec/git-core` and `usr/share/git-core/templates` directories and literal `usr/share/git-core/gitattributes` file. The adapter also grants named system tools, `/System/Library`, `/usr/lib`, literal locale and resolver files, and the user's `Library/Keychains` tree for reading. Literal read grants include `/`, `/private/etc/hosts`, `/dev/null`, `/dev/random`, and `/dev/urandom`. Writes also permit `/dev/null` and `/dev/fd`. It does not derive grants from the host `PATH`. Unsupported hosts, missing dependencies, changed executables, invalid policy, or substituted directories stop launch. `--setting-sources project` preserves installed project skills and agents. Strict empty MCP configuration applies to initial and resumed turns. The boundary restricts filesystem access. Network, signals, and IPC remain unconfined.
- **Codex.** A moved `HOME` and a private `CODEX_HOME` with an `auth.json` link preserve login without loading host settings. `--disable apps` excludes account apps and their `codex_apps` MCP tools on initial and resumed turns.
- **Hermes.** A throwaway `docker run` of the existing local gateway image, with a temp `HERMES_HOME` and `auth.json` mounted read-only. Preparation resolves the local image ID once. Every probe and turn uses that ID with `--pull=never`, including when `HERMES_IMAGE` names a mutable tag.
- **Grok Build.** A temp `HOME` and `GROK_HOME`, with an auth provider that reads `~/.grok/auth.json` and never writes it.

Claude keeps native sessions, memory, caches, sockets, and temporary files in fixed directories under the run. The adapter overrides `CLAUDE_CONFIG_DIR`, `CLAUDE_CODE_TMPDIR`, `TMPDIR`, and XDG directories. It preserves real `HOME` and sets `CLAUDE_SECURESTORAGE_CONFIG_DIR` to the empty string for the measured login route. This selects the default host Keychain namespace, so the run shares the host login item. Real `HOME` receives no general filesystem grant. The Keychains read exception does not establish credential secrecy, refresh compatibility, or absence of credential-service writes.

Claude session files stay in the private native store for resume. Harvest rejects symlinks, hard links, special files, duplicate leads, and directory substitution. A missing native `projects/` directory or selected lead transcript aborts harvest. The exception stops the entire `live.py run` batch before the affected run gets `trace.json` or `verdict.json`. It does not return a partial trace for those failures. Harvest copies a complete selected session file set into an atomic `transcripts/snapshot-<turn-count>-<digest>` directory. Later harvests retain earlier snapshots and return the selected snapshot through `x_evidence_snapshot`. Stream readers use fixed evaluator-owned paths. Recorded Read paths and non-flag arguments of Bash read commands undergo lexical normalization without host filesystem queries. The records can include nonexistent paths, grep patterns, and sed programs. They describe requested arguments and do not establish successful file reads.

After harvest succeeds, a timeout, nonzero exit, missing successful native result or child evidence, or an explicit native `run_in_background` request leaves `x_evidence_complete` false. Retained events can still show bounded behavior. The completion field does not infer background execution from arbitrary shell command text and does not establish process quiescence. Process-group termination does not establish that detached writers stopped.

The adapters avoid direct filesystem writes to the user's own harness configuration. Claude still shares the host login Keychain item through credential services. Claude denies shared `/tmp` paths outside its run and does not take the host fixture lock. The other host adapters still permit literal `/tmp` paths named after the project. `live.py` runs one case of a fixture at a time for those adapters, unless the case sets `tmp_lock` to false.

Claude Code and Codex cases exclude account MCP servers. The parallel half of `why-queries-evidence-categories-in-parallel` remains unmeasured without a common stub issue-tracker MCP on every harness.

`testdata/traces/` holds reduced traces that `test_oracles.py` grades. `python3 evals/promises/reduce_trace.py <trace.json> --case feature-run --case route-feature` rewrites a raw trace down to the events and fields that keep every verdict and failure reason. Add `--exact <promise>` to keep that promise's evidence lines too, as `test_claude_high_reply_quotes_executed_commands_with_outputs` needs for `claude-code-feature-2.json`.

`cases/<id>/case.json` sets the cases. `deferred` marks a case this suite records but does not run yet, with the reason. Prompts follow the blinding rules in `skills/poteto-mode/playbooks/eval.md`, and `test_oracles.py` rejects meta words in prompts and fixtures.
