# Reminders maintenance development case

This case packages a known maintenance failure as public tuning material. It is not a held-out confirmation case. The starting CLI supports skip and end_series. The maintenance request adds change_cadence while preserving its existing behavior.

`case.json` is a declarative case specification, not a native comparison manifest. The case is ready for model-free instrumentation checks. Subject model, comparison, and treatments remain unset for review. The c23 native validator requires real, nonempty skill paths and both variants. A future comparison must select real treatments and generate a valid manifest before any model run. No paid efficacy claim follows from these controls.

The model inputs are `starting-project.zip`, `original-request.md`, and `prompt.md`. The archive contains exactly the seven files in `starting-project/`. It excludes the oracle, failed and repaired controls, control table, and answer keys. Both request files are unchanged historical requests. The maintenance prompt does not name the known failure or repair.

The future capture protocol starts with no `project/` directory. Archive extraction and all final application files produce additions under `project/`. The native artifact commit and workspace capture must validate before reconstruction or acceptance. Each preflight capture is synthetic and records that no model ran.

## Run the model-free preflight

From the repository root, use the existing sibling `skill-ci` environment. It contains Python 3.14 and the pinned native runtime. Set `HARNESS_PYTHON` to another Python 3.12 or newer environment only if it contains the same attested runtime and module hashes.

```sh
HARNESS_PYTHON=../skill-ci/.venv/bin/python
"$HARNESS_PYTHON" -I evals/reminders-maintenance/preflight.py --output ../mds-pstack-private/evals/reminders-maintenance/preflight-20261015/review-01
```

Failure signal for the assignment is an absent interpreter at the selected path. Failure signals for the preflight are a nonzero exit, `preflight failed` on stderr, or an absent `receipt.json`. Use a new output directory for each run. The script refuses output inside this repository, existing output directories, ignored public inputs, changed hashes, and missing runtime prerequisites.

The preflight validates every source hash and the exact archive members. It then creates native captures, invokes the unchanged `instrument/experiment.py check`, reconstructs each capture, and runs the acceptance oracle in Docker. The isolated Python launcher adds only the frozen instrument directory so the unchanged controller can import its sibling module. The script never calls its prepare or execute branches. Those copied branches retain their historical revision guard and are outside this case's supported workflow.

Docker must already have `python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36`. The checker uses no network, read-only project and oracle mounts, a read-only container root, dropped capabilities, and bounded resources. Candidates run only inside the container. A Docker or capture error cannot substitute for an expected candidate failure.

## Control expectations

`case.json` records every expected response, failure marker, and request count. The preflight requires the full checker JSON response and the exact successful stdout summary. Zero requests cannot pass. For failed candidates, the completed count is inferred from the frozen oracle's sequential scenario order and its observed first-failure label.

| Control | Expected result | Requests | Failure marker |
| --- | --- | --- | --- |
| starting-design | Pass | 76 passed | None |
| starting-maintenance | Candidate failure | 74 completed before failure | cadence_preserves_future_closed_records request 6 |
| historical-maintenance | Candidate failure | 68 completed before failure | end_at_first_date request 4 |
| positive-maintenance | Pass with starting project as prior | 129 passed, including 10 upgrade requests | None |
| constant | Candidate failure | 0 completed before failure | empty_and_rejected_requests request 1 |
| noop | Candidate failure | 0 completed before failure | empty_and_rejected_requests request 1 |
| missing-capture | Capture rejected | 0 acceptance requests | complete committed artifact required |
| tampered-capture | Capture rejected | 0 acceptance requests | complete committed artifact required |

The historical candidate returns invalid_occurrence where end_at_first_date request 4 requires series_ended. `controls/positive/` is a synthetic passing witness. Its only difference from `controls/historical/` is the predicate in `controls/positive.patch`. The witness demonstrates that the unchanged oracle accepts a repair while retaining the old contract. It does not change any skill and is not evidence of model or treatment quality.

The 129-request maintenance check includes the 10 requests in accepted_build_history_survives_upgrade. Every maintenance control supplies `starting-project/` as `--prior-project`. Omitting that input would run only 119 requests and fails the positive control's expected count.

## Frozen sources and receipts

`source-lock.json` records SHA-256 values for every case file except the lock itself. Origins use logical study and artifact names. It also pins the installed native revision and runtime module hashes. The two instrument files and two oracle files are byte-identical copies of their historical sources. The historical and starting seven-file projects remain unchanged.

Raw captures, checker stdout, checker stderr, invocation arguments, and `receipt.json` belong in the private output directory. Raw historical model outputs and traces remain outside this public case. A successful preflight records zero paid calls. After any intentional case edit, a maintainer must review and regenerate the lock before another preflight. The lock is a local integrity record, not an external authenticity signature.
