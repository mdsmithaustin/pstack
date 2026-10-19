# Prepare the pipeline exit study

This study compares the current verify-commands skill, its previous revision, and no skill. The tested edit adds the tail and pipefail rule. Setup is model-free. No model answer, judge verdict, or improvement has been measured.

The organizing record is [study.json](study.json). [source-lock.json](source-lock.json) pins treatment and oracle bytes. Both packages retain the skill identity `verify-commands`. Mount only the selected package in each isolated task.

[screen.json](screen.json) has three public exploratory cases: stale-count handling, preservation of an already-correct command, and pipeline failure propagation. The pipeline case includes the earlier independent-shell scenario and requires exactly the last 20 lines of combined verifier stdout and stderr. One repetition across current, previous, and absent skill arms produces exactly nine answers.

[confirmation.template.json](confirmation.template.json) retains four public hidden-prompt placeholders for a possible 36-answer plan. All 36 confirmation answers remain deferred, with zero authorized confirmation answers. Placeholders are not reviewed heldout cases. Before receiving budget, each future real case must name its promise, demonstrate an oracle control that catches its violation, and explain which decision the result could change.

## Install and attest the historical runtime

Run from the repository root with Git and Python 3.12 on PATH. Create a fresh, separate virtual environment outside the repository. This recipe installs distribution `skill-eval-harness-ext` version `0.6.0` at the exact historical Git revision. It does not use the repository's default skill-ci environment or change its bootstrap, pins, or installed skills.

```sh
export EXTERNAL_VENV="$HOME/.venvs/pipeline-exit-c23ed795"
test ! -e "$EXTERNAL_VENV" || { echo 'Choose a fresh EXTERNAL_VENV path' >&2; exit 1; }
python3.12 -m venv "$EXTERNAL_VENV" || exit 1
"$EXTERNAL_VENV/bin/python" -m pip install 'skill-eval-harness-ext @ git+https://github.com/mdsmithaustin/skill-eval-harness.git@c23ed79554995c60cbd63cc9da9f47837cfa6f9a' || exit 1
export HARNESS_PYTHON="$EXTERNAL_VENV/bin/python"
```

The existing-directory check, environment creation, and installation each fail with a non-zero exit. Choose a different external path if the default already exists. No sister PR is required.

Set `RUN_ROOT` to a separate output directory. The public preparation commands below do not read private cases. `PRIVATE_ROOT` is needed only by a future independently approved confirmation owner.

```sh
export STUDY="$(pwd)/evals/verify-commands/studies/pipeline-exit"
export RUN_ROOT="${RUN_ROOT:?Set RUN_ROOT to a private output directory}"
export HARNESS_PYTHON="${HARNESS_PYTHON:?Run the historical environment setup first}"
mkdir -p "$RUN_ROOT"
```

Failure signal for each required variable is a non-zero shell exit when it is absent. `mkdir` failure also exits non-zero. These setup commands do not establish readiness.

```sh
"$HARNESS_PYTHON" -I - <<'PYCODE'
import hashlib
import importlib.metadata as metadata
import importlib.util
import json
import os
from pathlib import Path
lock = json.loads((Path(os.environ["STUDY"]) / "source-lock.json").read_text())
distribution = metadata.distribution("skill-eval-harness-ext")
record = json.loads(distribution.read_text("direct_url.json"))
assert distribution.version == "0.6.0", distribution.version
assert record["vcs_info"]["commit_id"] == lock["chosen_harness_revision"], record
module = Path(importlib.util.find_spec("skill_benchmark").origin)
assert hashlib.sha256(module.read_bytes()).hexdigest() == lock["installed_harness_module"]["sha256"], module
print("Installed harness version, Git revision, and locked module hash match.")
PYCODE
```

Failure signal is a non-zero exit from a missing distribution, wrong version, revision mismatch, missing module, or module hash mismatch. The shared corpus still declares ancestor `c2a1735983fd7827491ad4d89f9bebe9e8e229a0`. This study deliberately installs `c23ed79554995c60cbd63cc9da9f47837cfa6f9a`; it does not change the shared pin.

```sh
"$HARNESS_PYTHON" -I - <<'PYCODE'
import hashlib
import json
import os
from pathlib import Path
study = Path(os.environ["STUDY"])
root = Path.cwd()
lock = json.loads((study / "source-lock.json").read_text())
for item in lock["oracle_files"]:
    frozen = (study / item["frozen"]).read_bytes()
    assert hashlib.sha256(frozen).hexdigest() == item["sha256"], item
    assert frozen == (root / item["source"]).read_bytes(), item
for item in lock["treatments"]:
    assert hashlib.sha256((study / item["frozen"]).read_bytes()).hexdigest() == item["sha256"], item
print("Frozen oracle and treatment hashes match.")
PYCODE
```

Failure signal is a non-zero exit from a missing source or mismatched bytes. The source skill remains unchanged. Current source is commit `5e5eaa861a5df50c0cedc601db7e9f17e70e2ef9`, SHA-256 `e636242b63a2409e1f0b52f4cc0125bf72de527d1abbdf5c6958105965a76c2e`. Previous source is commit `af9e84907233e3f7be49d74427458690f7ef436f`, SHA-256 `a781a937661a1d5d005145f28db464d866c46c36cfd70b9eebd0ebc1c463b6a2`. The rule was added in commit `7b662326`.

The installed harness requires script assertions and their dependencies to remain inside the manifest directory. `oracle/` therefore freezes the revised canonical checker, full case definitions, and every bootstrap referenced by that manifest, including fixtures not selected for paid answers. Those dependencies add no paid cases. The canonical source revision is recorded in `source-lock.json`. The original source lock is retained in `source-lock.historical.json`; its bytes describe the historical package at commit `5277f7cd44a0f340ca89bf3efd6ce48382a11df0`, not the revised freeze. Each file must match its recorded source before a run.

The oracle uses `python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36`, network disabled, with a read-only prepared project. It authenticates the required operation and checks healthy, broken, and forced-operation-failure states. A forced operation exit of 97 must make the outer verdict non-zero. The outer interpreter is `/bin/sh`; Bash is available for an explicit invocation. The new `pipeline-tail` selector checks complete captured stdout against literal expected suffixes and requires empty stderr. Its fixture emits 30 distinct ordered lines in both healthy and broken states, including visible stderr; the task asks candidates to merge streams. Forced exit 97 occurs before the fixture body, so its expected output is empty. Any non-zero outer status preserves failure, including normalized exit 1. Only this selector provides a state-isolated `$TMPDIR` and a 1 MiB per-file limit. All selectors share the existing 64 MiB container tmpfs limit. Scratch is removed after candidate process-group teardown between states. Prepared projects remain immutable, with network disabled and no host mounts. Older selectors retain no scratch and a zero file-size allowance. The oracle cannot prove which options existed in a past tool invocation.

## Validate and prepare the public splits

These commands make no model calls. Each command fails with a non-zero exit on invalid schema, readiness blockers, or preparation failure.

```sh
"$HARNESS_PYTHON" -I -m skill_benchmark validate "$STUDY/screen.json"
"$HARNESS_PYTHON" -I -m skill_benchmark audit-manifest "$STUDY/screen.json" --split tune --fail-on-blockers --strict-judge --out "$RUN_ROOT/screen.audit.json" --format json
"$HARNESS_PYTHON" -I -m skill_benchmark prepare "$STUDY/screen.json" --split tune --include-old-skill --runs-per-variant 1 --models gpt-6.1-sol --out "$RUN_ROOT/screen.tasks.jsonl"
"$HARNESS_PYTHON" -I -m skill_benchmark validate "$STUDY/confirmation.template.json"
"$HARNESS_PYTHON" -I -m skill_benchmark audit-manifest "$STUDY/confirmation.template.json" --split holdout --fail-on-blockers --strict-judge --out "$RUN_ROOT/confirmation.audit.json" --format json
"$HARNESS_PYTHON" -I -m skill_benchmark prepare "$STUDY/confirmation.template.json" --split holdout --include-old-skill --runs-per-variant 3 --models gpt-6.1-sol --allow-missing-prompts --out "$RUN_ROOT/confirmation.plan.jsonl"
```

Validation must report three screen cases and four confirmation placeholders. Readiness must report no blockers. Confirmation planning uses hidden placeholders and must never reach `run-agent`. A passing template audit does not establish private-case readiness.

```sh
"$HARNESS_PYTHON" -I - <<'PYCODE'
from collections import Counter
from pathlib import Path
import json
import os
study = Path(os.environ["STUDY"]).resolve()
run_root = Path(os.environ["RUN_ROOT"])
for name, count, repetitions in [("screen.tasks.jsonl", 9, 1), ("confirmation.plan.jsonl", 36, 3)]:
    rows = [json.loads(line) for line in (run_root / name).read_text().splitlines()]
    assert len(rows) == count, (name, len(rows))
    cases = 3 if name == "screen.tasks.jsonl" else 4
    assert Counter(row["variant"] for row in rows) == {arm: cases * repetitions for arm in ["with_skill", "without_skill", "old_skill"]}
    for row in rows:
        assert not set(row) & {"answer_key", "expected_behavior", "review_rubric", "assertions"}
        arm = row["variant"]
        package = "current" if arm == "with_skill" else "previous"
        expected = [] if arm == "without_skill" else [str(study / "packages" / package / "verify-commands/SKILL.md")]
        assert row["skill_paths"] == expected, row
        assert all(Path(path).is_file() for path in row["input_files"]), row
        assert row["model"] == "gpt-6.1-sol", row
    print(name, count, "tasks with correct arms, files, and no answer keys")
PYCODE
```

Failure signal is a non-zero exit on missing rows, omitted arms, changed paths, missing fixtures, wrong subject model, or answer-key fields. Do not pass `--include-answer-key` to generation preparation.

## Recheck oracle controls

[model-free-checks.json](model-free-checks.json) retains historical setup results, including the private-confirmation preflight record. Packaging this study does not repeat those checks or establish current private-case readiness. In those recorded checks, the frozen oracle accepted the existing valid npm and healthy samples. It rejected the existing ignored-operation-status sample. Nested Bash with pipefail passed; the same pipeline without pipefail failed the broken and forced-failure controls.

The behavioral regression population is retained in the canonical oracle tests. The new public CLI controls accept explicit Bash pipefail, POSIX temporary-log status capture, and normalized failure status. They reject silent, unfiltered, 19-line, 21-line, wrong-suffix, missing-operation, unprotected-tail, ignored-failure, and print-only answers. They also exercise scratch reset, immutable prepared files, and the older selectors' no-write contract.

```sh
"$HARNESS_PYTHON" -I -B -m unittest discover -s evals/verify-commands/oracles -p 'test_*.py' -v
```

Failure signal is a non-zero exit, any failed test, or an empty test population. Infrastructure status 2 must fail; it never counts as expected candidate rejection 1. The pinned Docker image must already be present because the checker uses `--pull never` and `--network none`. The source/hash check above binds the canonical implementation and all fixture dependencies to the study freeze. These model-free controls establish instrument behavior only and do not measure model improvement.

For a public frozen-checker replay, each control uses the unchanged CLI `"$HARNESS_PYTHON" -I -B "$STUDY/oracle/check_plan.py" SELECTOR OUTPUT_DIR`, where `OUTPUT_DIR/output.md` contains the complete sample. Expected controls are `valid-stale-npm.md` with `stale-summary` exit 0, `ignored-operation-status.md` with `stale-summary` exit 1, and `valid-healthy-control.md` with `healthy-control` exit 0. The three `valid-pipeline-*.md` samples use `pipeline-tail` and must exit 0; the nine remaining pipeline samples must exit 1. The prior nested-Bash stale-summary controls remain historical and the original regression tests remain intact. Native Test retains its own actual commands, cwd, exits, timings, and streams rather than relabeling historical results as fresh evidence.

## Deferred private confirmation

No private confirmation preparation or prompt access is authorized in the current revision. The following interface is retained for future review only. After explicit authorization, an independent author writes `$PRIVATE_ROOT/cases.json`. Do not copy those cases into this repository. The study setup author must not read that file.

The private run owner copies this study directory into `$PRIVATE_ROOT/runtime`. Replace the template's `cases` list with the independently authored four cases and save `confirmation.json` alongside the copied `oracle/` and `packages/`. Normalize only interface fields: split is `holdout`, files resolve below `oracle/projects/`, and executable assertions call `oracle/check_plan.py` with the author's selector. Preserve authored prompts and their case identities. Every case needs one strong gate script assertion, one soft explanation judge assertion, and the three soft exposure assertions from the template. Public template expectations are examples for assembly, not private answer keys. The retained template examples use `stale-summary` and `healthy-control`. Each future case still requires its own promise, demonstrated violation control, and decision consequence before any budget is authorized.

The private run owner validates `confirmation.json` with `--strict-holdback`, audits it with `--split holdout --fail-on-blockers --strict-judge`, and prepares it with `--split holdout --include-old-skill --runs-per-variant 3 --models gpt-6.1-sol`. Omit `--allow-missing-prompts`. Each command's failure signal is a non-zero exit. Inspect the 36 real rows for balanced arms, matching prompts and fixture bytes within each case, correct package paths, and no answer keys. In a future independently approved confirmation study, freeze the private case file and assembled manifest hashes before any confirmation answers are visible. Any prompt edit after that point invalidates that sealed confirmation.

## Review before paid execution

All paid execution remains blocked until human review. The single answer subject is `gpt-6.1-sol`. The cross-family judge model and backend must be finalized at that review; `claude-review-required` is an explicit unresolved marker, not a runnable model choice. The root owns exactly nine subject invocations after native validation and independent review. Native Review/Test/fix phases make zero subject or judge calls. Review all nine screen answers and their oracle evidence before any further decision. All 36 confirmation answers remain deferred; the screen cannot authorize them automatically. Do not repair the skill or rewrite heldout cases between those stages without starting a new study.

Use the existing [evaluation runbook](../../../README.md) for isolated native execution. Fixture bootstraps require the Codex adapter's `workspace-write` sandbox. Resolve the project-only adapter to an absolute path before entering isolated workspaces. Do not expose the source checkout, host skill installation, private answer keys, or the alternate treatment package to an answer task.

Preparation requires `old_skill_paths` and `--include-old-skill`. Each later `grade`, `judge`, and `benchmark` invocation must repeat all three flags: `--variant with_skill --variant without_skill --variant old_skill`. Otherwise the old arm can be silently omitted. Use `--allow-scripts` on grade and benchmark. Set `--judge-runs 1`, select the reviewed cross-family judge, and do not configure a panel. Keep the nine-answer exploratory screen separate from the deferred confirmation planning output. No executable paid batch is provided here.

The primary score is each answer's existing strong executable oracle result. Judge explanations are secondary and soft. Skill-loading receipts are diagnostic and soft; loading earns no lift. Reject invalid treatment paths, contamination, incomplete or mismatched exposure, and missing output separately before comparing behavioral outcomes. A `skill_invoked` receipt alone cannot prove which mounted file supplied a read.

Reject any current-arm false green or healthy regression. Report current versus absent results as whole-skill value, and current versus previous results as added-rule value. Keep those decisions separate. Treat ceiling, floor, incomplete populations, invalid exposure, or separation confined to explanation scores as inconclusive. If there is no valid behavioral separation that informs a decision, end this study without claiming added value or automatically starting confirmation. Keep the useful regression checks even if the default model ties across arms. Three targeted cases do not establish broad skill efficacy. No synthetic control, saved verify-commands run, or result from another skill establishes model improvement here. Judge finalization and human paid-run review remain pending.
