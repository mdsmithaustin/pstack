# Feature edge pass, 2026-11-01

The edge pass was run against two specs for the same feature. The first spec states each edge in its own sentence. The second spec, in [Implied-edge spec](#implied-edge-spec), leaves each edge to follow from a definition or a rule.

**The stated spec shows no separation.** On Claude Code and on Codex, both arms passed every held-out edge check, and every lead's own tests caught all six edges. The control already reaches that ceiling on this spec, so these runs cannot show a gain from the edge pass. On Claude Code the edge-pass leads listed Unicode normalization as an unsettled edge in 3 of 3 runs, against 0 of 3 for the control, and took longer, a mean of 450 s against 302 s. On Codex the edge-pass leads listed non-positive thresholds as unsettled in 2 of 2 runs, and both control replies said there were no open decisions.

**The implied spec shows no gain in delivered code, and a gain in one edge of the lead's own tests on Claude Code.** Every Claude Code and Codex run, in both arms, delivered code that passed the five uncontested edges. The control leads' tests missed the empty log in 3 of 3 Claude Code runs, and the edge-pass leads' tests caught it in 3 of 3. No lead's tests caught the `lower()` mutant of the case-folding edge, which every stated-spec lead's tests caught. Two of three Claude Code edge-pass runs delivered `lower()` and failed that edge, after a reviewer read "differ only in capitalization" as excluding `ß` against `ss`. Those two leads added a test for that reading. That wording is mine, so the case-folding edge is contested. Both Grok Build runs timed out at the 1800 s cap and added no code to the project.

## What ran

The change under test is commit `fc418bee`, an unpublished state of branch `fix/feature-spec-edge-probes` before review edits. The committed overlays preserve its text exactly. It rewrites Feature step 4 so that the lead settles acceptance tests from the spec's worked examples and from the **spec-probes** skill's edge pass before the first spawn. It also adds a task-triggers line that sends any spec-to-tests work through the same edge pass. At `19bd25de`, step 4 already tells the lead to write acceptance tests from worked examples, so the arms differ only in the edge pass and its wording.

The case is `feature-edges-run` on the new `strides` fixture, a running club's log tool. Its one turn is `add the streaks command described in docs/streaks.md. verify it.` under `/poteto-mode`. The spec, then `fixtures/strides/docs/streaks.md` and now `histories/strides-stated-edges/step-1/docs/streaks.md`, settles six edges in prose. Its one worked example exercises none of them.

| Edge | Settled by |
|---|---|
| `boundary` | "List the members whose streak is at least N days" |
| `empty` | "including when the log is empty, print `no streaks`" |
| `ties` | "Members with equal streaks keep the order of their first line in the log", where the existing `totals` sorts by name |
| `casefold` | "equal under Unicode case folding", checked with `Jürgen Weiß` and `JÜRGEN WEISS` |
| `same-day` | "A day counts once however many runs the member logged on it" |
| `out-of-order` | "the log is not always in date order" |

`cases/feature-edges-run/held_out.py` runs one CLI check per edge and seven core checks: the worked example, the longest of two stretches, a month boundary, a non-empty log with nobody listed, `--min-days 1`, unchanged `totals` output, and a direct call of `longest_streaks`. The original grade of each run had only the first six core checks, and the [regrade](#regrade-with-the-fixed-grader) adds the seventh. The script runs after the session, inside the grader. The [Codex classification](#codex) records the limits of its held-out exposure check.

The script also runs the project's own unittest suite against `reference/strides` and against one mutant per edge. Each mutant fails exactly its own edge check, which `HeldOutEdges` in `test_oracles.py` asserts. A delivered test catches an edge when it passes on the reference and fails or errors on that edge's mutant. The lead measure repeats this on the test files that the lead's own tool calls wrote. In every stated-spec run, every delivered test passed on the reference, so no test fell outside the measure. Two implied-spec runs each had one test that failed on the reference, as listed below.

## Pins and arms

- The evaluator ran from `6cebeeca` on `eval/feature-spec-edge-pass`. Both arms pin skills at `19bd25de`.
- The control is `feature-edges-run`.
- The edge-pass arm is `feature-edges-run-edge-pass`, the same case plus two `skill_overlays` that `make_arm.py` built from `fc418bee`. The overlaid `feature.md` and `task-triggers.md` hold `fc418bee`'s text byte for byte (sha256 prefixes `bb29af17` and `e684ca0f`). The branch was later reworded after review, so its files no longer match these digests. As in the [2026-10-10 runs](2026-10-10-use-the-skill.md), these runs used a local arm case, kept in `.audit/feature-edge-pass-20261101/arm-cases/`. From `759b57a5` the same overlays are in the committed case `feature-edges-run-edge-pass`.
- Command per arm: `python3.14 evals/promises/live.py run --harness <h> --model <m> --effort high --skills-at 19bd25de59f3a338bc54e2069d0d1a42e4dc9631 --runs <n> --case <case> --out <dir>`. The arms ran in parallel, and the runs within an arm ran in sequence. No retries.
- Claude Code used `claude-sonnet-5-5` at effort high, 3 runs per arm, with the TODO tools on.
- Codex used `gpt-6.1-sol` at effort high on Codex 0.162.0, 2 runs per arm, inside the 2400 s cap. Codex runs of one fixture share a host lock, so its arms alternated rather than overlapped.
- The grader copies `oracles.py` when it issues a run. Every run was graded with the oracle at `6cebeeca`, except Codex `strides-nc1vz7fz`, which was issued after the change that `3a230c98` commits. That change only adds Codex `FileChange` paths to the lead's test files. The held-out checks are the same in both versions.
- Durable copy: `.audit/feature-edge-pass-20261101/`, with `make_arm.py` and `tally.py`. Every count below comes from the `measures` in each run's `verdict.json`, except where the table says "by hand" and except the core checks, which come from the [regrade](#regrade-with-the-fixed-grader).

## Results

Each cell counts checks passed or edges caught. Edge checks and caught edges are out of 6, and core checks are out of 7.

| Harness | Arm | Run | Edge checks | Core checks | Delivered tests catch | Lead's tests catch | spec-probes loaded | Duration | Spawns |
|---|---|---|---|---|---|---|---|---|---|
| Claude Code | control | `strides-_6nftpfy` | 6 | 7 | 6 | 6 | no | 257 s | 2 |
| Claude Code | control | `strides-6jvytztc` | 6 | 7 | 6 | 6 | no | 335 s | 3 |
| Claude Code | control | `strides-ff7hcjdg` | 6 | 7 | 6 | 6 | no | 314 s | 2 |
| Claude Code | edge pass | `strides-6wj0y2rb` | 6 | 7 | 6 | 6 | lead, seq 14 | 262 s | 2 |
| Claude Code | edge pass | `strides-fvj82f1n` | 6 | 7 | 6 | 6 | lead, seq 15 | 658 s | 6 |
| Claude Code | edge pass | `strides-vxd6p0s0` | 6 | 7 | 6 | 6 | lead, seq 50 | 430 s | 3 |
| Codex | control | `strides-2467q412` | 6 | 7 | 6 | 6 (by hand) | no | 1029 s | 8 |
| Codex | control | `strides-v8y735wc` | 6 | 7 | 6 | 6 (by hand) | no | 580 s | 9 |
| Codex | edge pass | `strides-tbbozanb` | 6 | 7 | 6 | 6 (by hand) | lead, seq 60 | 745 s | 9 |
| Codex | edge pass | `strides-nc1vz7fz` | 6 | 7 | 6 | 6 | lead, seq 65 | 859 s | 10 |

At `6cebeeca` the oracle missed the Codex lead's test file, because Codex code mode writes it inside an `exec` call. For the three Codex runs graded at `6cebeeca`, I ran the same `held_out.py --lead-tests tests/test_streaks.py` on a copy of each project, outside the grader. Those copies are in `.audit/feature-edge-pass-20261101/codex/lead-measure-copies/`. `3a230c98` fixes the lookup.

Every run exited 0 inside its cap, and `feature-delivers-spec-edges` graded PASS in every run. On Claude Code, `poteto-mode-routes-to-playbook` graded INCONCLUSIVE in every run, because its reply check sent quoted commands to a judge. Its evidence shows `feature` as the first playbook read in every run.

## Classification

### Claude Code

- **Every lead wrote its test file before it spawned the implementer.** Each read `playbooks/feature.md` at seq 3 to 5. Control `strides-_6nftpfy` wrote 19 tests at seq 26, including `test_min_days_is_inclusive`, `test_unicode_case_folding`, and `test_longest_first_ties_keep_first_line_order`, and spawned the implementer at seq 42. That run is the cheapest at 257 s.
- **The costliest run is edge pass `strides-fvj82f1n`.** It loaded spec-probes at seq 15, spawned a reader at seq 39, and spawned two implementers. Three review rounds followed at seq 69, 97, and 107, and the run took 658 s, against a control mean of 302 s. The edge-pass mean is 450 s.
- **Two leads, one per arm, wrote a wrong month-boundary test.** Control `strides-ff7hcjdg` claimed 2027-02-28 to 2027-03-01 is a gap, and edge pass `strides-6wj0y2rb` claimed 2026-02-28 and 2026-03-01 are not consecutive. In both runs the implementer's code was right, the lead's test failed, and the lead fixed the test.
- **Edge pass `strides-vxd6p0s0` ran its own mutation check.** After the implementer returned, the lead mutated the delivered code at seq 88 to 96. It found that its tests missed a repeated day inside a streak, and it added that test at seq 98.
- **No run reported a settled edge as an open gap.** The edge-pass replies listed Unicode normalization in 3 of 3 runs, for example "precomposed `Zoë` and a decomposed `Zoë` count as two members" in `strides-fvj82f1n`. Each arm listed `--min-days` of 0 or below in 2 of 3 runs. The spec settles neither. I classified the gap lines myself, knowing each run's arm, so that count is not blinded.
- No Claude Code trace names a path under `evals/`. The paths outside the project in `strides-6jvytztc` are the run's own review scratch under its `tmp/`. The adapter's Seatbelt profile denies reads outside the run in any case.

### Codex

- **Every Codex lead wrote `tests/test_streaks.py` itself.** The `FileChange` events in each lead rollout name it. Each lead read `playbooks/feature.md` before any other playbook. The edge-pass leads read `spec-probes/SKILL.md` whole at seq 60 and 65. The control leads never read it.
- **Codex gap reports.** Edge pass `strides-tbbozanb` wrote "The spec leaves nonpositive thresholds undefined", and `strides-nc1vz7fz` wrote "Nonpositive thresholds remain unspecified". Control `strides-2467q412` and `strides-v8y735wc` both wrote "No open decisions" or "No pattern departures or open decisions". No Codex reply listed Unicode normalization.
- **`poteto-mode-routes-to-playbook`** graded PASS on Codex `strides-2467q412` and FAIL on the other three Codex runs. Each FAIL reads "reply carries no executed command as evidence", and each run's evidence still names `feature` as the first playbook read.
- No lead rollout, final reply, or Codex delegate transcript names `held_out`, `feature-edges-run`, `evals/promises`, or `reference/strides`. Codex has no read sandbox on the host, so this search is the only exposure check for Codex runs.

## Why the comparison cannot show a gain

The spec states each edge in its own sentence. A careful reader turns each sentence into a test, and the control leads did so without the edge pass, so both arms sit at the ceiling. A fixture that tests the change needs edges that follow from the spec's definitions without a sentence that names them. For example, "a streak is consecutive calendar days with a run" implies the same-day and date-order edges without saying so. That variant needs the spec moved out of the fixture's initial commit into a history step, so that the stated text never appears in the run's git history. The next section runs that variant.

## Implied-edge spec

### What changed

`feature-edges-implied-run` sends the same turn to the same project, with the same worked example and the same held-out checks as `feature-edges-run`. Its spec names no edge. Each edge follows from a definition or a rule instead. The case reads `held_out.py` and `reference/` from `cases/feature-edges-run` through its new `references` field, and the grader copies that directory beside the case's own.

From `759b57a5` the `strides` fixture holds no spec. Each case adds `docs/streaks.md` in a history step, committed as `docs: describe the streaks command`, so no commit of an implied run holds the stated text. `test_no_commit_of_the_implied_project_holds_a_stated_edge_sentence` reads every file of every commit to check that. The stated-spec runs above had the spec in the fixture's initial commit.

The case's `edge_sources` field names the sentence each edge follows from. `test_each_spec_holds_a_source_sentence_for_every_held_out_edge` checks that each sentence is in the spec.

| Edge | Follows from | The step a reader takes |
|---|---|---|
| `boundary` | "`--min-days N` sets the shortest streak that makes the list, 3 by default." | A streak of exactly N is the shortest that makes the list. |
| `empty` | "When nobody makes the list, print `no streaks`." | An empty log lists nobody. |
| `ties` | "Members appear in the order of their first line in the log, except that a longer streak always comes before a shorter one." | Equal streaks fall under no exception. |
| `casefold` | "Two names belong to the same member when they differ only in capitalization." | Unicode uppercases `ß` to `SS`, so `JÜRGEN WEISS` is `Jürgen Weiß` in capitals, and `jürgen weiss` is `JÜRGEN WEISS` in lower case. |
| `same-day` | "A streak is a stretch of consecutive calendar days on which a member logged at least one run" | A streak counts days, not runs. |
| `out-of-order` | "Members who forget to log a run can add it on a later visit, dated the day they ran." | The README says the tablet appends one line per run, so a late run follows lines with later dates. |

### Pins and arms

- The evaluator ran from `759b57a5`. Skills are pinned at `19bd25de`, as in the stated-spec runs.
- Both edge-pass arms are committed cases now, `feature-edges-run-edge-pass` and `feature-edges-implied-run-edge-pass`. Their overlays turn `feature.md` and `task-triggers.md` into the text of `fc418bee`. Each overlay carries the sha256 of the file it must produce, `bb29af17` and `e684ca0f`, and `live.py` refuses a run whose overlaid file differs. The overlays equal the ones in the local arm that the stated-spec runs used.
- Claude Code ran `claude-sonnet-5-5` at effort high, 3 runs per arm. Codex ran `gpt-6.1-sol` at effort high on Codex 0.162.0, 2 runs per arm, with the 2400 s cap. Grok Build 1.0.70 ran its default model, which the traces record as `grok-4.7-build`, at the adapter's fixed effort high, with the 1800 s cap. The Grok adapter accepts no `--model` or `--effort`.
- Arms ran in parallel, and the runs within an arm ran in sequence. Codex and Grok runs hold the host `strides` fixture lock, so they ran one at a time. Other sessions ran Codex and Grok cases on the same host during the wave. No retries.
- Run directories had neutral names such as `club/ash`. The stated-spec runs had `edges-live/control` or `edges-live/edge-pass` in the path the candidate saw.
- Each run was graded with the oracle copied when the run started, which was `759b57a5` for every graded run. Codex `strides-iuvw2j6_` wrote its tests in `.worktrees/streaks-build/`, so that oracle returned an empty lead measure. `12e57db0` fixes the lookup. For that run I ran `held_out.py --lead-tests tests/test_streaks.py` on a copy of the project, outside the grader.
- I stopped the second Grok run of each arm before its first turn, after the first run of each arm timed out without code. I did not start the four stated-spec Grok runs. Each would most likely have reached the same cap, and each would have held the fixture lock for up to 30 minutes.
- Durable copy: `.audit/feature-edge-implied-20261101/`, with the run directories under `runs/`, `make_cases.py` and `tally.py` under `scripts/`, the run label map in `scripts/arms.json`, the judge packet and its raw output under `judge/`, and the judge's label map in `scripts/judge-map.json`.

### Results

Each count adds up the arm's runs. Held-out and own-test counts are edges, 6 per run. The two columns before the duration come from the blinded judge described below.

| Harness | Arm | Runs | Held-out edges | `casefold` held out | Own tests catch | spec-probes loaded | Names an edge open | Says none open | Mean duration |
|---|---|---|---|---|---|---|---|---|---|
| Claude Code | control | 3 | 18 of 18 | 3 of 3 | 12 of 18 | 0 of 3 | 1 of 3 | 0 of 3 | 270 s |
| Claude Code | edge pass | 3 | 16 of 18 | 1 of 3 | 15 of 18 | 1 of 3 | 2 of 3 | 0 of 3 | 360 s |
| Codex | control | 2 | 12 of 12 | 2 of 2 | 10 of 12 | 0 of 2 | 0 of 2 | 2 of 2 | 714 s |
| Codex | edge pass | 2 | 12 of 12 | 2 of 2 | 10 of 12 | 2 of 2 | 1 of 2 | 0 of 2 | 686 s |
| Grok Build | control | 1 | 0 of 6 | 0 of 1 | no tests | 0 of 1 | no report | no report | 1800 s, timed out |
| Grok Build | edge pass | 1 | 0 of 6 | 0 of 1 | no tests | 1 of 1 | no report | no report | 1800 s, timed out |

| Harness | Arm | Run | Held-out edges | Own tests miss | spec-probes loaded | Duration | Spawns |
|---|---|---|---|---|---|---|---|
| Claude Code | control | `strides-ylh54v2v` | 6 | `empty`, `casefold` | no | 220 s | 2 |
| Claude Code | control | `strides-63i5k0ev` | 6 | `empty`, `casefold` | no | 299 s | 3 |
| Claude Code | control | `strides-8zemr571` | 6 | `empty`, `casefold` | no | 291 s | 3 |
| Claude Code | edge pass | `strides-u0e8871f` | 5, fails `casefold` | `casefold` | no | 315 s | 3 |
| Claude Code | edge pass | `strides-gt8lhffb` | 6 | `casefold` | lead, seq 62 | 375 s | 4 |
| Claude Code | edge pass | `strides-0idz5h1b` | 5, fails `casefold` | `casefold` | no | 389 s | 3 |
| Codex | control | `strides-62dkcx5b` | 6 | `casefold` | no | 779 s | 8 |
| Codex | control | `strides-kd2mqe4u` | 6 | `casefold` | no | 648 s | 8 |
| Codex | edge pass | `strides-iuvw2j6_` | 6 | `casefold` (by hand) | lead, seq 55 | 747 s | 8 |
| Codex | edge pass | `strides-kplcbi0_` | 6 | `casefold` | lead, seq 36 | 625 s | 8 |
| Grok Build | control | `strides-f7cdhp8g` | 0 | no tests | no | 1800 s, timed out | 5 |
| Grok Build | edge pass | `strides-bciqqa7l` | 0 | no tests | lead, seq 73 | 1800 s, timed out | 5 |

Every Claude Code and Codex run passed all seven core checks in the [regrade](#regrade-with-the-fixed-grader). Each Grok run passed only `totals-unchanged`, because neither added a `streaks` command or `strides/streaks.py`. In every Claude Code and Codex run, the delivered tests caught the same edges as the lead's own tests. Every delivered test passed on the reference except one in each of edge pass `strides-u0e8871f` and `strides-0idz5h1b`. Each of those two tests asserts that `Strauß` and `Strauss`, or `Straße` and `Strasse`, stay separate members, so it fails on the reference's `casefold()`.

### Classification

#### Claude Code

- **The edge pass changed one edge of the lead's tests.** Every edge-pass lead tested the empty log, and no control lead did. Only `strides-gt8lhffb` loaded spec-probes, at seq 62, before it spawned the implementer at seq 79. The other two edge-pass leads read `feature.md` at seq 4, and its step 4 names "empty input" itself. So the step text, not the skill, probably carried this change. That is an inference from 3 runs.
- **Five of six leads briefed the implementer to key members by `casefold()`.** Control `strides-8zemr571` allowed "the casefolded or lowercased name", and its implementer chose `casefold()`. In edge pass `strides-u0e8871f` and `strides-0idz5h1b`, an independent reviewer found that `casefold()` merges names that differ by more than capitalization, such as `Straße` and `Strasse` in the first and `Strauß` and `Strauss` in the second. Each lead switched to `lower()` with a new test for that reading. In control `strides-63i5k0ev`, the lead raised the same question, kept `casefold()`, and listed it as an open decision. Three of six Claude Code leads treated the edge as unsettled, so my sentence does not settle it for a careful reader.
- **No implied-spec test catches the `lower()` mutant.** The leads tested capitalization drift with ASCII names such as `ADA lim`, which `lower()` and `casefold()` treat alike. Under the stated spec, which names Unicode case folding, every lead's tests caught it.
- The edge-pass leads took a mean of 360 s, against 270 s for the control.
- No Claude Code transcript names `held_out`, `feature-edges`, `evals/promises`, or `reference/strides`, across 18 to 31 transcript files per run.

#### Codex

- All four runs delivered every edge. Each lead's tests caught five edges and missed `casefold`, in both arms.
- The edge-pass leads read `spec-probes/SKILL.md` whole, at seq 55 and 36. The control leads never read it.
- Both control replies said there were no open decisions. Both edge-pass replies listed non-positive thresholds and Unicode matching as unspecified.
- No lead or delegate rollout names the evaluator paths above, across 21 session files per run.

#### Grok Build

- Both runs timed out at 1800 s without adding `streaks` or any test to the project. Each lead spent its time reading skills, briefing a `how` explainer, and running an architect arena with three runner subagents. The edge-pass lead also ran a cross-judge, read `spec-probes/SKILL.md` at seq 73, and wrote its only test file to the host's `/tmp/test_streaks.py`, outside the project.
- In edge pass `strides-bciqqa7l`, an architect runner subagent listed the host's processes. Its result held the evaluator's command lines, including `--case feature-edges-implied-run`. The lead's trace holds none of that text, and the run delivered nothing, so no count above depends on it. Run `strides-f7cdhp8g` shows no such text.
- On these traces the oracle counted the `read_file` load of spec-probes and correctly found no lead test file in the project. Grok also edits with `search_replace`, which `View.edits()` missed until `cfcebd5a`. Neither run used it.

### Blinded gap classification

One judge read the ten Claude Code and Codex replies under shuffled labels, with the spec and README. The judge ran `opus` at effort xhigh, from the `trail reviewer` role resolved against `sonnet@high`. Model names, `spec-probes`, and "edge pass" were redacted from the replies. The judge sorted each open question into one of six edges, non-positive threshold, normalization, or other. I unblinded the labels after it returned, then read every reply myself. I agree with its sorting except for `strides-iuvw2j6_`. That reply's "broader Unicode equivalence" went to normalization, and it could equally mean case folding, which would make the Codex edge-pass count 2 of 2.

| Harness | Arm | `casefold` open | Non-positive threshold open | Normalization open |
|---|---|---|---|---|
| Claude Code | control | 1 of 3 | 1 of 3 | 0 of 3 |
| Claude Code | edge pass | 2 of 3 | 3 of 3 | 2 of 3 |
| Codex | control | 0 of 2 | 0 of 2 | 0 of 2 |
| Codex | edge pass | 1 of 2 | 2 of 2 | 1 of 2 |

No reply named `boundary`, `empty`, `ties`, `same-day`, or `out-of-order` as open. Every lead resolved those five from the implied wording.

### What weakens the comparison

- **The case-folding edge is contested.** Three of six Claude Code leads treated it as open, and two of them delivered `lower()` because they read "differ only in capitalization" as excluding `ß` against `ss`. The held-out check also needs `jürgen weiss` to join `Jürgen Weiß`, which holds only through `JÜRGEN WEISS`. The two `casefold` failures therefore measure my wording as much as the edge pass.
- **The samples are small.** The one own-test difference is 3 runs against 3 on one harness. Codex ran 2 runs per arm. Grok gave no edge data.
- **The two specs ran under different setups.** The stated-spec runs ran from `6cebeeca`, with the spec in the initial commit and the arm name in the candidate's path. The implied-spec runs ran from `759b57a5`, with the spec in a second commit and neutral paths.
- **One lead measure is by hand.** It ran the same `held_out.py` outside the grader's sandbox.
- **The host was shared.** Other sessions ran Codex and Grok cases during the wave, which can change durations.

### What the data support about the Feature step 4 edge pass

On both specs, the edge pass did not improve delivered code on any harness that delivered code. On the implied spec it changed three things on Claude Code. The lead's tests covered the empty log in 3 of 3 runs, against 0 of 3. The replies listed more unsettled questions. A run took about 90 s longer. On Codex it changed only the reply, which named unsettled questions where the control said there were none. No lead's tests caught the `lower()` mutant without a sentence naming case folding, so the edge pass did not close the gap that the implied spec opened. These runs do not support promoting the change as a correctness gain. The next run that could show one needs a `casefold` check that rests only on `JÜRGEN WEISS` being `Jürgen Weiß` in capitals, more runs per arm, and a Grok cap long enough to reach the code.

The user chose to ship the edge pass in a separate PR despite these results. That PR rewords step 4 after review, so the shipped text differs from the tested `fc418bee` text.

## Regrade with the fixed grader

A Copilot review of PR 387 found four gaps in the held-out grader after these runs. The PR fixes all four.

- Both specs ask for `longest_streaks(runs, min_days=3)` in `strides/streaks.py`, but every check ran the CLI, so a delivery without that function could pass. A seventh core check, `api`, now calls it with its default threshold and with `min_days`.
- A test package inside the delivered `strides/` package was missing from every mutation copy. The copies now keep each folder in the package that holds a test file.
- A test was credited with a catch whenever its mutant outcome was not a pass, so a skip counted. Only a failure or an error on the mutant counts now.
- The diagnostic suites could run past the grader's 1200 s limit and turn a correct delivery `INCONCLUSIVE`. They now stop at a 1080 s budget, and an edge whose suites did not finish reads null.

I copied each saved project out of `.audit` and ran the `held_out.py` from `d82c108e` and the fixed one on each copy. Each run used the lead test files from its grade, or `tests/test_streaks.py` for the four by-hand runs. The old script reproduced every recorded per-edge result, and each by-hand lead measure above.

Every Claude Code and Codex delivery passed `api`, so each passed seven of seven core checks and kept its verdict. Both Grok runs failed `api` with `No module named 'strides.streaks'` and passed one of seven. The other three fixes changed no count. No delivery held a test inside `strides/`. For every edge, the same test IDs caught the mutant under both scripts. The whole regrade of 22 runs under both scripts took 24 s, four runs at a time.

| Spec | Harness | Arm | Held-out edges | Core checks, graded | Core checks, regraded | Own tests catch | Own tests catch the empty log |
|---|---|---|---|---|---|---|---|
| stated | Claude Code | control | 18 of 18 | 18 of 18 | 21 of 21 | 18 of 18 | 3 of 3 |
| stated | Claude Code | edge pass | 18 of 18 | 18 of 18 | 21 of 21 | 18 of 18 | 3 of 3 |
| stated | Codex | control | 12 of 12 | 12 of 12 | 14 of 14 | 12 of 12 | 2 of 2 |
| stated | Codex | edge pass | 12 of 12 | 12 of 12 | 14 of 14 | 12 of 12 | 2 of 2 |
| implied | Claude Code | control | 18 of 18 | 18 of 18 | 21 of 21 | 12 of 18 | 0 of 3 |
| implied | Claude Code | edge pass | 16 of 18 | 18 of 18 | 21 of 21 | 15 of 18 | 3 of 3 |
| implied | Codex | control | 12 of 12 | 12 of 12 | 14 of 14 | 10 of 12 | 2 of 2 |
| implied | Codex | edge pass | 12 of 12 | 12 of 12 | 14 of 14 | 10 of 12 | 2 of 2 |
| implied | Grok Build | control | 0 of 6 | 1 of 6 | 1 of 7 | no tests | no tests |
| implied | Grok Build | edge pass | 0 of 6 | 1 of 6 | 1 of 7 | no tests | no tests |

Held-out edges and own-test counts are the same graded and regraded. The regrade script, both `held_out.py` versions, and the full reports are in `.audit/feature-edge-implied-20261101/regrade-pr387/`.
