# Evaluation coverage audit

2026-11-08. Scope: maintained public manifests, the guide-promise ledger, native evaluation families, and their existing CI owners. Historical studies remain closed. This audit does not certify every private oracle or measure savings.

## Decisions

Keep the existing execution tools. Use skill-ci for portable lint and dispatch, skill-eval-harness for native execution and saved-output grading, and pstack for task acceptance and spending policy.

The ledger assigns 137 promises to static checks, 18 to script checks, 10 to installation checks, and 113 to live cases. Static and script checks already avoid model calls. Installation checks need native tools but no paid answer. Live promise counts are claims, not independent tasks or required calls.

The four maintained manifests contain 54 cases: 26 answer cases and 28 trigger cases. Trigger and answer populations remain separate. All are public development material. They do not become held-out evidence by changing the split label.

| Family | Cheapest reliable owner | Decision and disposition |
| --- | --- | --- |
| Skill metadata, paths, packaging, invocation policy | skill-ci lint and pstack tools tests in CI | Keep executable checks. Do not buy judgments of these same exact properties. |
| Guide inventory and quoted promises | `evals/promises/ledger.py audit`, static and script tests | Keep in CI. A quote proves text presence, not model compliance. |
| Native installation and discovery | `evals/promises/install.py`; affected live cases when behavior matters | Run on relevant installer or runtime changes. A source lint cannot replace native discovery. |
| Parser, report, and oracle correctness | Unit controls and saved trace replay | Use reduced positive and negative evidence before new subjects. |
| verify-commands | Existing container oracle, then affected fresh command generation | Keep healthy, false-green, and forced-operation-failure controls. Oracle repairs need replay, not new answers. |
| spec-probes and runtime-probes | Executable evidence where available; semantic review for remaining claims | Keep calibrated review for grounded findings and scope restraint. Do not replace meaning with keyword counts. |
| unslop | Edited-block and literal checks; residual semantic review | Literal preservation does not prove factual fidelity. The judge partly overlaps literal checks but also covers unsupported claims; deleting the whole judge would lose coverage. |
| harness-routing and skill-recovery | Saved-record parser controls; targeted native recording when runtime changes | Keep separate from task success. Do not rerun the full skill matrix for a parser fix. |
| canon | Current native capture and outcome-grader controls | Archived broad screens remain archived. Reuse controls rather than restoring the old matrix. |
| port-value and pipeline-exit | Historical aggregate review and model-free reproduction | Keep regression evidence. Saturated public tasks cannot supply fresh efficacy evidence. Do not restart closed subject slots. |

## Overlap and migration actions

No exact duplicate prompt with the same trigger/answer population and attachment list exists across the maintained manifests. Similar promise names and exposure checks are not sufficient evidence of duplication.

1. Pstack now records `evaluation_policy` in each maintained manifest. CI requires the decision, unique coverage, rerun condition, reason for model use, and existing deterministic check paths. The same CI test rejects exact duplicate prompts. This removes the need to ask a model whether those fields exist. No scheduled model job was retired. It does not judge whether their prose is convincing or forbid ad hoc paid calls.
2. Reuse the harness's existing `audit-manifest --runs` and trend findings for saturation and expensive non-discriminating cases. These require retained runs. Do not create another model to inspect pass rates. Saturation is a review signal; a useful regression case can remain all-pass.
3. Keep trigger declaration lint and live trigger cases separate. `tools/skill-trigger-cases.json` checks metadata and invocation policy. It does not execute discovery, so it cannot replace the live trigger population.
4. Keep process diagnostics outside outcome claims. The new shared outcome rate excludes process and efficiency assertions. It remains an assertion fraction, not whole-task acceptance. Existing critical gates still apply.
5. Leave the unslop judge until its semantic questions have independent calibration. Its fact-preservation rubric overlaps substring checks only partly. A mechanically preserved number can still be assigned to the wrong fact.
6. The unresolved `needs_judge` queue in the promise suite remains a specific reporting follow-up. Its present manual disposition is documented. A parser repair should use the saved corpus before another paid wave.

For each future migration, assign the implementation to its owning repository, prove that a valid control passes and the original violation fails, then put the check in authoritative CI. Retire only the covered model inspection. Changes to acceptance criteria need separate review from repairs.

## Per-case routing

The table below inventories every maintained answer case. Trigger rows are counted separately above and remain native activation checks. Script and command assertions can grade evidence without a judge; fresh answers still need a subject. A judge is retained only for the case's semantic questions. Exposure checks are diagnostics of the treatment.

| Corpus / case | Outcome assertions | Process assertions | Route |
| --- | --- | --- | --- |
| `runtime-probes/neg-plan-order-service-unavailable` | judge | skill_invoked | Fresh behavior; calibrated semantic review |
| `runtime-probes/pos-live-order-replay` | judge | command_ran, skill_invoked | Fresh behavior; calibrated semantic review |
| `runtime-probes/neg-guarded-order-import` | judge | command_ran, skill_invoked | Fresh behavior; calibrated semantic review |
| `runtime-probes/pos-billing-dependency-boundary` | judge | command_ran, skill_invoked | Fresh behavior; calibrated semantic review |
| `runtime-probes/neg-permission-boundary-escalation` | judge | skill_invoked | Fresh behavior; calibrated semantic review |
| `spec-probes/pos-mixed-shapes` | judge | skill_invoked | Fresh behavior; calibrated semantic review |
| `spec-probes/pos-unclassified-prose` | judge | skill_invoked | Fresh behavior; calibrated semantic review |
| `spec-probes/pos-bespoke-reminder` | judge | skill_invoked | Fresh behavior; calibrated semantic review |
| `spec-probes/pos-open-product-choice` | judge | skill_invoked | Fresh behavior; calibrated semantic review |
| `spec-probes/pos-variant-coverage` | judge | skill_invoked | Fresh behavior; calibrated semantic review |
| `spec-probes/pos-new-field-unrequested-rejection` | judge | skill_invoked | Fresh behavior; calibrated semantic review |
| `spec-probes/pos-extension-keeps-accepted-input` | judge | skill_invoked | Fresh behavior; calibrated semantic review |
| `spec-probes/pos-look-alike-terms` | judge | skill_invoked | Fresh behavior; calibrated semantic review |
| `spec-probes/neg-deployed-incident-restraint` | judge | skill_invoked | Fresh behavior; calibrated semantic review |
| `unslop/readme-paragraph-tells` | judge, script | skill_invoked | Fresh behavior; calibrated semantic review |
| `unslop/docs-section-protected-constructs` | script | skill_invoked | Fresh behavior; executable grading |
| `verify-commands/pos-lifecycle-observation` | script | skill_invoked | Fresh behavior; executable grading |
| `verify-commands/pos-stale-summary` | judge, script | skill_invoked | Fresh behavior; calibrated semantic review |
| `verify-commands/pos-empty-selection` | judge, script | skill_invoked | Fresh behavior; calibrated semantic review |
| `verify-commands/pos-defaulted-parity` | judge, script | skill_invoked | Fresh behavior; calibrated semantic review |
| `verify-commands/pos-package-path` | judge, script | skill_invoked | Fresh behavior; calibrated semantic review |
| `verify-commands/pos-scoped-source` | judge, script | skill_invoked | Fresh behavior; calibrated semantic review |
| `verify-commands/pos-bytecode-controls` | judge, script | skill_invoked | Fresh behavior; calibrated semantic review |
| `verify-commands/healthy-control` | judge, script | skill_invoked | Fresh behavior; calibrated semantic review |
| `verify-commands/neg-explain-pipefail` | judge | skill_invoked | Fresh behavior; calibrated semantic review |
| `verify-commands/neg-format-command` | judge | skill_invoked | Fresh behavior; calibrated semantic review |

## Verification and limits

`python3 -m unittest discover -s tools -p test_eval_artifacts.py` checks the policy and packaging contracts. A nonzero exit or a zero-test summary fails verification. CI runs this file through its existing tools discovery step. Positive and negative policy controls exercise missing coverage and missing check paths.

The policy applies to the four maintained manifests under `evals/*/shared-benchmark.json`. The separate promise ledger and historical study contracts keep their own formats. Presence checks cannot prove unique semantic coverage, measure maintenance cost, or authorize a run. No savings percentage follows from this audit.
