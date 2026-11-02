# Principle load phrasing, 2026-11-01

**Status: ISSUES.** On Claude Code with `claude-sonnet-5-5` at effort high, the shipped task-triggers line "Use the **principle-model-the-domain** skill" got the lead to load that principle before its first code write in 1 of 3 runs. "Load the" also passed 1 of 3. The three wordings that name how to load the skill each passed 3 of 3. They are "Call the Skill tool with", "Run /principle-model-the-domain", and a relative link to the principle's `SKILL.md` with "Read ... in full". Every lead read `task-triggers.md` before it wrote code, so each lead saw its arm's line. One final reply in 15 named a principle. Three runs per arm is a small sample, and the [validity notes](#validity) limit what the counts show.

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

The oracle `triggered-principle-loads-before-code` grades the lead. A run passes when the lead loads `principle-model-the-domain` before its first write of a code or test file, or before its first code delegate spawn when that comes sooner. On Claude Code, a load is a Skill tool call whose result succeeded, or a Read of the principle's `SKILL.md` that returned. A load after that first write fails, and so does no load at all. Delegate loads and the lead's first `task-triggers.md` read go in the evidence and do not change the verdict.

## Pins and runs

- The evaluator ran from branch `eval/principle-load-phrasing` at `65c5313a`. Its parent `2c7d3b79` adds the oracle and the cases, and `65c5313a` adds the ledger entry. `f64444ee` changes only how the oracle finds the `task-triggers.md` read for its evidence, and a regrade of all 15 sealed traces at that commit kept every verdict. The sealed `verdict.json` files keep the earlier evidence line, so `g1/roster-ahiloeo5` still reads seq 2 there. The skills pin is `f186fba3bd2b774416773abd32041f8def77956e`, origin/main on 2026-11-01.
- Command per arm: `python3.14 evals/promises/live.py run --harness claude-code --model claude-sonnet-5-5 --effort high --skills-at f186fba3 --runs 3 --case <case> --out <dir>`. The five arms ran in parallel, and the runs inside an arm ran in sequence. No run was retried.
- The adapter admitted Claude Code 2.1.314. Every run recorded `x_skill_listing` step `installed`, so the lead's listing showed the principles by name only. No run reported host skill hits.
- No run timed out. Runs took 151 to 445 s. The 15 runs reported $19.61 in total, $3.32 to $4.69 per arm.
- No Codex group ran. A Feature case takes over 20 minutes per run on Codex.
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
- **One setup.** One harness, model, effort, site, fixture, and prompt.

## Recommendation

- Three runs each cannot separate "Use the" from "Load the". Each passed 1 of 3.
- At this site on Claude Code, naming the load mechanism in the trigger line got the load every time. Naming only the skill there got it 2 times in 6, even though the entry's general rule names the Skill tool. The data cannot rank C, D, and E.
- Of the three, only E names something every harness has, a file path. C names a Claude Code tool. D uses a user syntax that the lint bans and that may work only through Claude Code's slash rule. Before shipping E's form, run A against E with more runs per arm, and run a Codex group on both. These runs did not test whether E keeps its lead over more runs, or whether it works on Codex.
- Ten of the 11 leads that loaded the principle did not name it in the reply. The one that did ran arm E. That is a separate gap from the load.
