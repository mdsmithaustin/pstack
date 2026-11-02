# Principle load phrasing, 2026-11-01

**Status: ISSUES.** On Claude Code with `claude-sonnet-5-5` at effort high, the shipped task-triggers line "Use the **principle-model-the-domain** skill" got the lead to load that principle before its first code write in 1 of 3 runs. "Load the" also passed 1 of 3. The three wordings that name how to load the skill each passed 3 of 3. They are "Call the Skill tool with", "Run /principle-model-the-domain", and a relative link to the principle's `SKILL.md` with "Read ... in full". Every lead read `task-triggers.md` before it wrote code, so each lead saw its arm's line. One final reply in 15 named a principle. Three runs per arm is a small sample, and the [validity notes](#validity) limit what the counts show. On Codex with `gpt-6.1-sol` and on Grok Build with `grok-4.7-build`, both at effort high, the shipped line and the three mechanism wordings each passed 2 of 2, so those harnesses did not separate the wordings. Neither has a Skill tool. Every lead there loaded the principle by reading its `SKILL.md`, including the leads that ran arm C. The [Codex and Grok Build](#codex-and-grok-build) section has those runs.

## What ran

The site under test is the task-triggers line `- Any code → name the data shape first. Use the **principle-model-the-domain** skill to choose its organizing structure.` in `skills/poteto-mode/references/task-triggers.md`. Each arm replaces only its second sentence. Every other file is installed from the pin.

| Arm | Case | Second sentence of the line |
|---|---|---|
| A | `principle-load-run` | Use the **principle-model-the-domain** skill to choose its organizing structure. (shipped) |
| B | `principle-load-arm-load` | Load the **principle-model-the-domain** skill to choose its organizing structure. |
| C | `principle-load-arm-skill-tool` | Call the Skill tool with `principle-model-the-domain` to choose its organizing structure. |
| D | `principle-load-arm-slash` | Run /principle-model-the-domain to choose its organizing structure. |
| E | `principle-load-arm-path` | `Read [principle-model-the-domain](../../principle-model-the-domain/SKILL.md) in full to choose its organizing structure.` (the link resolves from `poteto-mode/references/`) |

The arm cases live in the repository this time. Each one is `principle-load-run` plus one `skill_overlays` entry, and `live.py` refuses an arm whose old text no longer occurs exactly once. `tools/skill-references.py` bans arm D's slash spelling in shipped skill text. The overlay exists only in the installed copy of one run, and the case's `note` says so.

All five cases run the roster fixture with the prompt `/poteto-mode members.csv is getting a status column: active, leave, or alumni. team counts should only count active members and show how many are on leave next to each team. alumni don't count anywhere. add the column to the sample data too.` The request needs a data-shape decision about how to represent the status and how the count uses it.

The oracle `triggered-principle-loads-before-code` grades the lead's load of `principle-model-the-domain`. The [suite guide](../README.md#run-live-cases) defines accepted loads, the code-write deadline, and verdicts when no code is written. Delegate loads and the lead's first `task-triggers.md` read appear only in the evidence.

## Pins and runs

- The evaluator ran from branch `eval/principle-load-phrasing` at `65c5313a`. Its parent `2c7d3b79` adds the oracle and the cases, and `65c5313a` adds the ledger entry. `f64444ee` changes only how the oracle finds the `task-triggers.md` read for its evidence, and a regrade of all 15 sealed traces at that commit kept every verdict. The sealed `verdict.json` files keep the earlier evidence line, so `g1/roster-ahiloeo5` still reads seq 2 there. The skills pin is `f186fba3bd2b774416773abd32041f8def77956e`, origin/main on 2026-11-01.
- This record names local commits from before the branch was rebased onto #387: `2c7d3b79`, `65c5313a`, `f64444ee`, `061513c1`, and `bf187a77`. None was published. The rebase folded `f64444ee` into the commit that adds the oracle. It kept `bf187a77` as "fix(evals): count Codex patches as edits in View.edits", which now also replaces #387's separate `FileChange` reader. Each rebased commit also carries #387's oracle changes, so its code differs from the code the runs used.
- Command per arm: `python3.14 evals/promises/live.py run --harness claude-code --model claude-sonnet-5-5 --effort high --skills-at f186fba3 --runs 3 --case <case> --out <dir>`. The five arms ran in parallel, and the runs inside an arm ran in sequence. No run was retried.
- The adapter admitted Claude Code 2.1.314. Every run recorded `x_skill_listing` step `installed`, so the lead's listing showed the principles by name only. No run reported host skill hits.
- No run timed out. Runs took 151 to 445 s. The 15 runs reported $19.61 in total, $3.32 to $4.69 per arm.
- The [Codex and Grok Build](#codex-and-grok-build) section records the runs on those harnesses.
- Durable copy: `.audit/guide-promises/live/principle-load-phrasing/`. Folders `g1` to `g5` hold arms A to E, as `arm-map.txt` records. The folder names keep the arm out of the path the lead sees. `tally.py` and `tally.jsonl` there hold the per-run counts below. A seq number below is a trace event number.

## Results

| Arm | Lead PASS | Lead load, seq | `task-triggers.md` read, seq | First code write, seq | Delegate loads | Reply names a principle |
|---|---|---|---|---|---|---|
| A use | 1/3 | Skill at 83 | 2, 4, 2 | 57, 63, 89 | 1 run, a read | 0/3 |
| B load | 1/3 | Skill at 60 | 4, 2, 1 | 66, 80, 54 | none | 0/3 |
| C Skill tool | 3/3 | Skill at 44, 45, 75 | 2, 3, 2 | 57, 53, 82 | none | 0/3 |
| D slash | 3/3 | Skill at 20, 44, 14 | 2, 2, 2 | 34, 72, 16 | none | 0/3 |
| E path | 3/3 | Read at 10, 15, 52 | 2, 1, 2 | 60, 52, 65 | none | 1/3 |

The `task-triggers.md` column counts a file read whose result returned, not a shell command such as `wc -l` that only names the file. Every first code write was an acceptance test, `tests/test_report.py` or `tests/test_cli.py`, which the Feature playbook has the lead write before it delegates.

## Classification

- **A and B, 4 FAIL.** Each lead read `task-triggers.md` at seq 1 to 4. Each called the Skill tool for `how`, and most also for `pstack-harness`, `deslop`, and `documentation-impact`. None loaded `principle-model-the-domain` at any point.
  - In `roster-ahiloeo5` (A), the seq 59 worklist update skips the `architect` step because the change is "one validated field on an existing row dict". The lead settled that data shape with no principle load.
  - In `roster-36zi0q3p` (A), the lead's brief to its `poteto-agent` at seq 81 says "Data shape (decided, per principle-model-the-domain)". The delegate read the principle's `SKILL.md`, and the lead never did. That read is the one delegate load in the table.
- **A and B, 2 PASS.** `roster-ukgqv_br` (A) called the Skill tool for the principle at seq 83, then for `principle-test-behavior-not-implementation` at seq 86, then wrote tests at seq 89. `roster-8_nrvimn` (B) loaded it at seq 60.
- **C and D, 6 PASS.** Each lead called the Skill tool with the bare name. In 5 of the 6, the call came 2 to 4 events after `Skill(how)`, the trigger two lines above. The other came at seq 75, 26 events after `how`. No D lead typed the slash form in its text or asked the user to run it.
- **E, 3 PASS.** Each lead opened the linked file with the Read tool at seq 10, 15, and 52. None used the Skill tool for the principle. Only `roster-0wglq7_y` named the principle in its reply, with its choice: "A `Status` enum, parsed in `load` (principle-model-the-domain)."
- **Reply naming, 1 of 15.** The mode entry's rule to name each principle that changed a decision held in one run, and a load did not make it hold. Eleven of the 15 leads loaded the principle, and ten of those eleven did not name it.

## Validity

- **Every lead saw its arm's line.** Each lead read `task-triggers.md` at seq 1 to 4, before its first code write. The trace keeps only the first 400 characters of each tool result, so the check used the session transcripts. In all 15 lead transcripts, the returned `task-triggers.md` text holds that arm's exact line.
- **No grading material reached a candidate.** The prompt and fixture contain none of the banned words, which `CaseHygiene` enforces. No lead or delegate file read named `evals/`, a case file, the ledger, an oracle, or a verdict. That scan covers `x_files_read_by` for every agent. It does not cover tool output beyond those reads.
- **The arms differ in more than the verb.** At the trigger line, C, D, and E name a load mechanism, while A and B name only the skill. The injected poteto-mode entry gave every arm the general rule: "Use a principle's leaf skill before applying it," and "On Claude Code, that is a Skill tool call with the bare name." A and B leads failed 4 of 6 with that rule in context. C's wording differs from it mainly by sitting at the trigger line. These runs cannot tell whether the verb, the named mechanism, or its place next to the trigger made the difference.
- **Arm D may rely on a Claude Code rule.** Claude Code's system prompt tells the model to call the Skill tool for a `/<name>` reference ([anthropics/claude-code#73774](https://github.com/anthropics/claude-code/issues/73774)). Codex treats the slash and `$` sigils as user syntax only, as the [phrasing decision](../../../docs/skill-cross-reference-phrasing.md) records.
- **The sample is small.** No single arm pair separates at three runs: 1 of 3 against 3 of 3 gives a one-sided Fisher exact p of 0.2. Pooled, the mechanism wordings passed 9 of 9 and the skill-name wordings passed 2 of 6, for a one-sided p of 0.011. That pooling was chosen after the results came in.
- **Two other mentions stayed constant.** The Feature playbook's step 4 says to name the data shape "per **principle-model-the-domain**", and the poteto-mode entry's Principles index lists the principle. Every lead had the entry injected and read `feature.md` at seq 3 to 8. In `roster-36zi0q3p` (A), the lead copied that "per" phrase into its delegate brief without loading the skill. The arm results hold only with those two mentions present.
- **One setup.** One harness, model, effort, site, fixture, and prompt in the runs above.

## Codex and Grok Build

The operator asked for the winning arms to run on Codex and Grok Build before any wording ships. Arms C, D, and E ran there with the shipped arm A as the control, two runs per arm on each harness. No shipped skill text changed.

### What ran there

- The evaluator ran from a detached worktree at `061513c1`, so the oracle fix below could land while the runs went on. The skills pin, cases, fixture, and prompt match the Claude Code runs.
- Codex: codex-cli 0.162.0 with `gpt-6.1-sol` at effort high. Command per run: `python3.14 evals/promises/live.py run --harness codex --model gpt-6.1-sol --effort high --skills-at f186fba3 --runs 1 --case <case> --out <dir>`.
- Grok Build: grok 1.0.70. The adapter refuses `--model` and `--effort` and writes effort high into the run's config, so the Grok command drops those two flags. Every Grok lead ran `grok-4.7-build` at effort high.
- Both adapters let a lead write literal `/tmp` paths, so `live.py` runs one roster case at a time across Codex and Grok. The 16 runs went one after another from 19:06 to 00:24 UTC, alternating harnesses and rotating arms. Each run had its own `live.py` call, so each Grok login preflight ran just before its run. No run was retried, and no run reported host skill hits.
- Codex runs took 357 to 759 s. Every Grok run reached the case's 1,800 s timeout and was killed. A killed run still grades when its lead loaded the principle before the kill.
- Durable copy: `.audit/guide-promises/live/principle-load-phrasing/codex/` and `grok/`. Folders `g1`, `g3`, `g4`, and `g5` hold arms A, C, D, and E, as `xharness/arm-map.txt` records. `xharness/` also holds the driver, its log, and the tally and validity scripts with their output.

### Results there

| Arm | Claude Code | Codex | Grok Build |
|---|---|---|---|
| A use (shipped) | 1/3 | 2/2 | 2/2 |
| C Skill tool | 3/3 | 2/2 | 2/2 |
| D slash | 3/3 | 2/2 | 2/2 |
| E path | 3/3 | 2/2 | 2/2 |

| Harness | Arm | Lead PASS | Lead load, seq | `task-triggers.md` read, seq | First code write, seq | Seconds | Runs |
|---|---|---|---|---|---|---|---|
| Codex | A use | 2/2 | shell at 13, shell at 19 | 6, 14 | 91, 75 | 732, 357 | `roster-ew6a4pxa`, `roster-zus47jdu` |
| Codex | C skill tool | 2/2 | shell at 58, shell at 39 | 15, 19 | 135, 127 | 554, 594 | `roster-axm5tqwr`, `roster-x35memsd` |
| Codex | D slash | 2/2 | shell at 17, shell at 54 | 6, 13 | 90, 93 | 759, 637 | `roster-kd0p29jp`, `roster-qq2vt0ls` |
| Codex | E path | 2/2 | shell at 15, shell at 19 | 7, 10 | 95, 101 | 603, 440 | `roster-b7xgxzld`, `roster-vnpctzca` |
| Grok | A use | 2/2 | read at 58, read at 51 | 2, 2 | 73, none | 1800, 1800 | `roster-lt4al8nc`, `roster-nogezvi8` |
| Grok | C skill tool | 2/2 | read at 61, read at 50 | 2, 2 | 144, none | 1800, 1800 | `roster-02ozhwsn`, `roster-xjipfk13` |
| Grok | D slash | 2/2 | read at 50, read at 41 | 2, 2 | none, 74 | 1800, 1800 | `roster-6ncv0ph4`, `roster-yu_r7feu` |
| Grok | E path | 2/2 | read at 39, read at 43 | 2, 2 | 73, 88 | 1800, 1800 | `roster-0b267y_p`, `roster-zgdrjajf` |

A Codex load is a `cat` of the file inside a shell command that exited 0. A Grok load is a `read_file` call. A first code write of "none" means the run was killed before any code write. In six runs the first code write is the spawn of the architect step's three `poteto-agent` runners, which the [oracle check](#oracle-check-there) covers. Codex final replies named the principle in 5 of 8 runs, none of them in arm A. No Grok run reached a final reply.

### What each harness did with arm C

Neither Codex nor Grok has a Skill tool. Each C lead read the principle's `SKILL.md` with its own file tools, as every other lead on those harnesses did. No C lead called a tool named Skill, named the Skill tool in a message, or failed on the missing tool. Codex keeps its reasoning encrypted in the rollout, so whether a Codex lead noticed the tool name is not visible. The Grok session keeps no reasoning.

### How the leads came to load it

- Codex leads read the principle with a `cat` of several skill files. In 4 of 8 runs, the same command read `how/SKILL.md`, the trigger two lines above. In 3, the read came with or right after `architect/SKILL.md`, the trigger one line below. One E lead (`roster-vnpctzca`) read the principle alone, right after `feature.md`.
- All 8 Grok leads read the principle during the architect step, after `architect/SKILL.md` and its references.
- The A leads on both harnesses loaded the principle as reliably as the C, D, and E leads. On Codex and Grok, these runs show no effect of the trigger line's wording.

### Oracle check there

- On Codex, a load is a shell read that returned the whole file. Every Codex lead load was a `cat` in a command that exited 0, so the README's [failed command chain](../README.md#known-oracle-gaps) edge never applied to this principle. One C run, `roster-x35memsd`, had a failed chain, but that chain read `principle-guard-the-context-window`.
- On Grok, a load is a `read_file` call whose result did not start with an error. Grok's tool list has no skill tool, so a file read is its only way to load a skill.
- Before `bf187a77`, the oracle missed Codex patches and Grok in-place edits. A Codex lead's patches reach the trace as `FileChange` calls, and Grok edits in place with `search_replace`. `View.edits` knew neither. In `roster-zus47jdu`, the lead patched two test files at seq 75, and the oracle put the first code write at seq 91, the delegate spawn. The fix counts both kinds. Regraded with it, 5 of the 8 Codex runs got an earlier first code write and no verdict moved. No Grok run changed. A project-free regrade of 1,338 saved traces under `.audit`, at `061513c1` and with the fix, moved none of 2,548 promise verdicts.
- The architect step spawns three `poteto-agent` runners that sketch designs in candidate worktrees. The oracle counts that spawn as a code delegate, which set the first code write in 2 Codex and 4 Grok runs. That deadline comes before the lead's first test write, so it can only turn a PASS into a FAIL. Every lead load came before it.

### Validity there

- Every Codex and Grok lead read `task-triggers.md` before its first code write. Its returned text held that arm's line and no other arm's line. The check read the Codex exec stream and the Grok lead's chat history, since the trace keeps only 400 characters of each result.
- No lead or delegate read a file under `evals/`, a case file, the ledger, an oracle, or a verdict, by the same scan as above plus a search of each run's raw session files.
- All 16 runs passed, so these runs cannot rank the wordings on Codex or Grok. They show only that C, D, and E do not stop the load there.
- Runs wrote literal `/tmp` files with names that recur across runs, such as `/tmp/roster-status-task.txt` and `/tmp/poteto-agent-brief.md`, and those files outlive a run. In every run, the lead's first use of each recurring name wrote the file, so no lead read a file an earlier run left. Delegate use was not checked beyond that.
- Two runs per arm is a small sample. The Grok model and effort came from the adapter. Hermes did not run.

## Recommendation

- Three runs each cannot separate "Use the" from "Load the". Each passed 1 of 3.
- At this site on Claude Code, naming the load mechanism in the trigger line got the load every time. Naming only the skill there got it 2 times in 6, even though the entry's general rule names the Skill tool. The data cannot rank C, D, and E.
- On Codex and Grok Build, every arm got the load 2 of 2, the shipped one included. Those harnesses cannot tell the wordings apart. None of C, D, or E broke the load there, and C's tool name did no harm. Those leads read the file, as they do for every skill.
- C holds up, so it can ship at this line as the operator prefers. Its gain is on Claude Code, and on Codex and Grok it costs nothing these runs can see. The data cannot rank C over E on any harness. E names a file path, which every harness has. C puts a Claude Code tool name in a line that Codex, Grok, and Hermes leads also read. The [phrasing decision](../../../docs/skill-cross-reference-phrasing.md#recommendation) owns the selected wording and pending rollout. A harness-neutral form of C was not run, and Hermes ran no arm. D uses a user syntax that the lint bans.
- These runs cover one trigger line. They do not show that C helps at other cross-references.
- On Claude Code, ten of the 11 leads that loaded the principle did not name it in the reply. The one that did ran arm E. That is a separate gap from the load.
