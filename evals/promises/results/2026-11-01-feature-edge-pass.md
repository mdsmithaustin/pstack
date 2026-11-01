# Feature edge pass, 2026-11-01

**Status: no separation.** On Claude Code and on Codex, both arms passed every held-out edge check, and every lead's own tests caught all six edges. The control already reaches that ceiling on this spec, so these runs cannot show a gain from the edge pass. On Claude Code the edge-pass leads listed Unicode normalization as an unsettled edge in 3 of 3 runs, against 0 of 3 for the control, and took longer, a mean of 450 s against 302 s. On Codex the edge-pass leads listed non-positive thresholds as unsettled in 2 of 2 runs, and both control replies said there were no open decisions.

## What ran

The change under test is commit `fc418bee` on `fix/feature-spec-edge-probes`. It rewrites Feature step 4 so that the lead settles acceptance tests from the spec's worked examples and from the **spec-probes** skill's edge pass before the first spawn. It also adds a task-triggers line that sends any spec-to-tests work through the same edge pass. At `19bd25de`, step 4 already tells the lead to write acceptance tests from worked examples, so the arms differ only in the edge pass and its wording.

The case is `feature-edges-run` on the new `strides` fixture, a running club's log tool. Its one turn is `add the streaks command described in docs/streaks.md. verify it.` under `/poteto-mode`. The spec, `fixtures/strides/docs/streaks.md`, settles six edges in prose. Its one worked example exercises none of them.

| Edge | Settled by |
|---|---|
| `boundary` | "List the members whose streak is at least N days" |
| `empty` | "including when the log is empty, print `no streaks`" |
| `ties` | "Members with equal streaks keep the order of their first line in the log", where the existing `totals` sorts by name |
| `casefold` | "equal under Unicode case folding", checked with `Jürgen Weiß` and `JÜRGEN WEISS` |
| `same-day` | "A day counts once however many runs the member logged on it" |
| `out-of-order` | "the log is not always in date order" |

`cases/feature-edges-run/held_out.py` runs one CLI check per edge and six core checks: the worked example, the longest of two stretches, a month boundary, a non-empty log with nobody listed, `--min-days 1`, and unchanged `totals` output. It runs after the session, inside the grader. The candidate cannot read the case directory.

The script also runs the project's own unittest suite against `reference/strides` and against one mutant per edge. Each mutant fails exactly its own edge check, which `HeldOutEdges` in `test_oracles.py` asserts. A delivered test catches an edge when it passes on the reference and fails on that edge's mutant. The lead measure repeats this on the test files that the lead's own tool calls wrote. In every run, every delivered test passed on the reference, so no test fell outside the measure.

## Pins and arms

- The evaluator ran from `472f82bd` on `eval/feature-spec-edge-pass`. Both arms pin skills at `19bd25de`.
- The control is `feature-edges-run`.
- The edge-pass arm is `feature-edges-run-edge-pass`, the same case plus two `skill_overlays` that `make_arm.py` built from `fc418bee`. The overlaid `feature.md` and `task-triggers.md` match the branch files byte for byte (sha256 prefixes `bb29af17` and `e684ca0f`). As in the [2026-10-10 runs](2026-10-10-use-the-skill.md), the arm case is not in the repository. A copy is in `.audit/feature-edge-pass-20261101/arm-cases/`.
- Command per arm: `python3.14 evals/promises/live.py run --harness <h> --model <m> --effort high --skills-at 19bd25de59f3a338bc54e2069d0d1a42e4dc9631 --runs <n> --case <case> --out <dir>`. The arms ran in parallel, and the runs within an arm ran in sequence. No retries.
- Claude Code used `claude-sonnet-5-5` at effort high, 3 runs per arm, with the TODO tools on.
- Codex used `gpt-6.1-sol` at effort high on Codex 0.162.0, 2 runs per arm, inside the 2400 s cap. Codex runs of one fixture share a host lock, so its arms alternated rather than overlapped.
- The grader copies `oracles.py` when it issues a run. Every run was graded with the oracle at `472f82bd`, except Codex `strides-nc1vz7fz`, which was issued after the change that `1061110a` commits. That change only adds Codex `FileChange` paths to the lead's test files. The held-out checks are the same in both versions.
- Durable copy: `.audit/feature-edge-pass-20261101/`, with `make_arm.py` and `tally.py`. Every count below comes from the `measures` in each run's `verdict.json`, except where the table says "by hand".

## Results

Each cell counts checks passed or edges caught, out of 6.

| Harness | Arm | Run | Edge checks | Core checks | Delivered tests catch | Lead's tests catch | spec-probes loaded | Duration | Spawns |
|---|---|---|---|---|---|---|---|---|---|
| Claude Code | control | `strides-_6nftpfy` | 6 | 6 | 6 | 6 | no | 257 s | 2 |
| Claude Code | control | `strides-6jvytztc` | 6 | 6 | 6 | 6 | no | 335 s | 3 |
| Claude Code | control | `strides-ff7hcjdg` | 6 | 6 | 6 | 6 | no | 314 s | 2 |
| Claude Code | edge pass | `strides-6wj0y2rb` | 6 | 6 | 6 | 6 | lead, seq 14 | 262 s | 2 |
| Claude Code | edge pass | `strides-fvj82f1n` | 6 | 6 | 6 | 6 | lead, seq 15 | 658 s | 6 |
| Claude Code | edge pass | `strides-vxd6p0s0` | 6 | 6 | 6 | 6 | lead, seq 50 | 430 s | 3 |
| Codex | control | `strides-2467q412` | 6 | 6 | 6 | 6 (by hand) | no | 1029 s | 8 |
| Codex | control | `strides-v8y735wc` | 6 | 6 | 6 | 6 (by hand) | no | 580 s | 9 |
| Codex | edge pass | `strides-tbbozanb` | 6 | 6 | 6 | 6 (by hand) | lead, seq 60 | 745 s | 9 |
| Codex | edge pass | `strides-nc1vz7fz` | 6 | 6 | 6 | 6 | lead, seq 65 | 859 s | 10 |

At `472f82bd` the oracle missed the Codex lead's test file, because Codex code mode writes it inside an `exec` call. For the three Codex runs graded at `472f82bd`, I ran the same `held_out.py --lead-tests tests/test_streaks.py` on a copy of each project, outside the grader. Those copies are in `.audit/feature-edge-pass-20261101/codex/lead-measure-copies/`. `1061110a` fixes the lookup.

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

The spec states each edge in its own sentence. A careful reader turns each sentence into a test, and the control leads did so without the edge pass, so both arms sit at the ceiling. A fixture that tests the change needs edges that follow from the spec's definitions without a sentence that names them. For example, "a streak is consecutive calendar days with a run" implies the same-day and date-order edges without saying so. That variant needs the spec moved out of the fixture's initial commit into a history step, so that the stated text never appears in the run's git history.
