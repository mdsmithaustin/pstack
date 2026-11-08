# Structured signoff pilot

The pilot is closed and inconclusive. Both guided answers and both baseline answers passed. Do not expand this pilot, claim added skill value, or remove verify-commands based on these two tasks. Keep the executable controls and saved outputs for offline replay.

## Question and frozen design

Would verify-commands improve signoff commands enough on fresh structured-output tasks to justify a larger study? The two task instances were authored for this pilot after the skill was frozen. They were held out from skill editing and were not published before execution. Both belong to the completion-gate family; they are not independent domains or a sample of production failures.

- Component health requires a successful runner, at least one executed check, and zero reported failures. A changing healthy count must still pass.
- Snapshot parity requires two successful, complete snapshots with equal nonempty ID sets and no duplicates. Valid reordering must pass.

The budget was four subject calls, one paired repetition per task, zero judge calls, 180 seconds per call, and no retries or replacement slots. The stopping rule declared ties, invalid exposure, or incomplete execution inconclusive. A guided-only success without a guided regression could justify designing confirmation, not claiming efficacy.

The requested runtime was Codex CLI 0.167.0 with `gpt-6.1-sol` at medium effort, the same project-only launcher and workspace-write sandbox in both arms. The shared harness was commit `35b39c1f15e3a6c873329a07b0fcb5b8c5f74cc4`, whose tree matches merged revision `9e9741a42e2beed96c9c22f1e9fb8ab25988aec2`. The served model identity was unavailable in the recorded runtime evidence.

The final pre-call protocol SHA-256 is `a0b86bd9f6795f12b4615e1c127a430e09df3a908d89cbb6395aabda2ffddbd4`. The [aggregate receipt](2026-11-08-eval-efficiency.json) records the source and result hashes. Private source, protocol, controls, task assignments, and raw evidence are retained locally under the ignored `.audit/eval-efficiency-20261108/` directory. None of the model answers are committed.

## Instrument controls

The pilot reused `evals/verify-commands/oracles/check_plan.py` unchanged with new fixtures and state definitions. Before subjects ran, both reference solutions passed. Always-green, always-red, and unchecked-operation controls failed for each task. That is eight model-free controls, not eight subject trials.

The initial valid snapshot control found an overstrict oracle requirement: a command may reject an empty source snapshot before requesting the target. The empty-state operation requirement was corrected before subject generation, then all eight controls passed. The preflight audit also required an adversarial case classification. Snapshot parity received that classification because it must distinguish valid reorderings from count-equivalent wrong sets. No prompt, skill, or acceptance predicate changed for that classification.

Task acceptance required every healthy, faulty, and forced-operation-failure state to match, with the required command evidence. The container oracle isolates execution and authenticates command observations. Skill-loading observations remain separate and do not independently attest which mounted bytes were read.

## Results

| Arm | Accepted tasks | Input tokens | Cached input tokens | Output tokens | Summed subject seconds |
| --- | --- | --- | --- | --- | --- |
| verify-commands | 2 / 2 | 138,778 | 125,440 | 2,262 | 71.499 |
| no skill | 2 / 2 | 130,109 | 118,528 | 1,603 | 53.477 |

All four assigned attempts completed, and all four exposure assertions matched their assigned condition. The report contains two eligible pairs and zero blocked pairs. No operator intervened during subject execution. Preparation and interpretation effort were not timed, so this is not a human-productivity comparison.

Cached input is included in input tokens; do not add it again. Billing data was unavailable. The guided arm used more recorded tokens and elapsed time in this sample. Two paired tasks at one repetition do not establish a general resource effect or noninferiority.

Offline `benchmark --allow-scripts` returned complete evidence. The saved-run audit, also with scripts enabled, flagged both cases as saturated and no-lift, and the suite as headroom-exhausted and underpowered. Its broad-catalog taxonomy and sample-count recommendations do not authorize expanding this bounded pilot. The frozen stopping rule controls that decision.

These results support stopping spend on this pilot. They do not establish that the skill is useless elsewhere, that the model always writes safe signoff commands, or that another runtime would behave the same way. No fresh efficacy claim can come from repeating these now-used instances.
