# Prepare the pipeline exit study

This study compares the current verify-commands skill, its previous revision, and no skill. The tested edit adds the tail and pipefail rule. Setup is model-free. No model answer, judge verdict, or improvement has been measured.

The organizing record is [study.json](study.json). [source-lock.json](source-lock.json) pins treatment and oracle bytes. Both packages retain the skill identity `verify-commands`. Mount only the selected package in each isolated task.

[screen.json](screen.json) has exactly four public tuning prompts. It reuses `pos-stale-summary` and `healthy-control`, then adds tail-filtering and separate-shell prompts. One repetition across three arms produces 12 answers. The existing pipeline trigger case is excluded because activation is not behavioral evidence.

[confirmation.template.json](confirmation.template.json) is a public interface with four hidden prompt references. It is not a sealed dataset or an executable confirmation run. An independent author supplies four new private cases. Three repetitions across three arms produce 36 answers. Total answer budget is 48, with at most one judge verdict per answer and no panel.

## Check the runtime and frozen sources

Run from the pstack repository root. Set `HARNESS_PYTHON` to the installed skill-ci virtual environment's absolute Python executable. Set `RUN_ROOT` to a private output directory. Set `PRIVATE_ROOT` to the full private study directory that contains `cases.json`. Do not store outputs or private prompts in this public study directory.

```sh
export STUDY="$(pwd)/evals/verify-commands/studies/pipeline-exit"
export RUN_ROOT="${RUN_ROOT:?Set RUN_ROOT to a private output directory}"
export PRIVATE_ROOT="${PRIVATE_ROOT:?Set PRIVATE_ROOT to the private study directory containing cases.json}"
export HARNESS_PYTHON="${HARNESS_PYTHON:?Set HARNESS_PYTHON to the installed harness Python}"
mkdir -p "$RUN_ROOT"
```

Failure signal for each required variable is a non-zero shell exit when it is absent. `mkdir` failure also exits non-zero. These setup commands do not establish readiness.

```sh
"$HARNESS_PYTHON" -I - <<'PYCODE'
import importlib.metadata as metadata
import json
record = json.loads(metadata.distribution("skill-eval-harness-ext").read_text("direct_url.json"))
assert record["vcs_info"]["commit_id"] == "c23ed79554995c60cbd63cc9da9f47837cfa6f9a", record
print("Installed harness pin matches.")
PYCODE
```

Failure signal is a non-zero exit from a missing distribution or pin mismatch. The shared corpus still declares ancestor `c2a1735983fd7827491ad4d89f9bebe9e8e229a0`. This study deliberately chooses installed `c23ed79554995c60cbd63cc9da9f47837cfa6f9a`; it does not change the shared pin.

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

The installed harness requires script assertions and their dependencies to remain inside the manifest directory. `oracle/` therefore freezes the unchanged checker, full case definitions, and only the three required fixture bootstraps. It is not a fork of the implementation. Each file must match its recorded source before a run.

The oracle uses `python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36`, network disabled, with a read-only prepared project. It authenticates the required operation and checks healthy, broken, and forced-operation-failure states. A forced operation exit of 97 must make the outer verdict non-zero. The outer interpreter is `/bin/sh`; Bash is available for an explicit invocation. Use nested-Bash controls to test the added rule without changing the oracle. The oracle cannot prove which options existed in a past tool invocation.

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

Validation must report four cases per manifest. Readiness must report no blockers. Confirmation planning uses hidden placeholders and must never reach `run-agent`. A passing template audit does not establish private-case readiness.

```sh
"$HARNESS_PYTHON" -I - <<'PYCODE'
from collections import Counter
from pathlib import Path
import json
import os
study = Path(os.environ["STUDY"]).resolve()
run_root = Path(os.environ["RUN_ROOT"])
for name, count, repetitions in [("screen.tasks.jsonl", 12, 1), ("confirmation.plan.jsonl", 36, 3)]:
    rows = [json.loads(line) for line in (run_root / name).read_text().splitlines()]
    assert len(rows) == count, (name, len(rows))
    assert Counter(row["variant"] for row in rows) == {arm: 4 * repetitions for arm in ["with_skill", "without_skill", "old_skill"]}
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

```sh
"$HARNESS_PYTHON" -I -B - <<'PYCODE'
import importlib.util
import os
from pathlib import Path
import tempfile
study = Path(os.environ["STUDY"])
spec = importlib.util.spec_from_file_location("oracle", study / "oracle/check_plan.py")
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)
samples = Path("evals/verify-commands/oracles/samples")
controls = [
    ("stale-summary", (samples / "valid-stale-npm.md").read_text(), 0),
    ("stale-summary", (samples / "ignored-operation-status.md").read_text(), 1),
    ("healthy-control", (samples / "valid-healthy-control.md").read_text(), 0),
    ("stale-summary", "```sh\nbash -o pipefail -c 'npm run verify | tail -n 20'\n```\n", 0),
    ("stale-summary", "```sh\nbash -c 'npm run verify | tail -n 20'\n```\n", 1),
]
for selector, answer, expected in controls:
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory).resolve()
        (output / "output.md").write_text(answer)
        code, result = oracle.evaluate(selector, output)
        assert code == expected, (selector, code, result)
        print(selector, code, result["status"])
PYCODE
```

Failure signal is a non-zero Python exit. Infrastructure status 2, rejected valid controls, or accepted false-green controls all fail this check. The pinned Docker image must already be present because the oracle uses `--pull never`. These synthetic controls verify the instrument and its Bash environment; they do not measure model behavior.

## Assemble private confirmation

The independent author writes `$PRIVATE_ROOT/cases.json`. Do not copy those cases into this repository. The study setup author must not read that file.

The private run owner copies this study directory into `$PRIVATE_ROOT/runtime`. Replace the template's `cases` list with the independently authored four cases and save `confirmation.json` alongside the copied `oracle/` and `packages/`. Normalize only interface fields: split is `holdout`, files resolve below `oracle/projects/`, and executable assertions call `oracle/check_plan.py` with the author's selector. Preserve authored prompts and their case identities. Every case needs one strong gate script assertion, one soft explanation judge assertion, and the three soft exposure assertions from the template. Public template expectations are examples for assembly, not private answer keys. The three supported private selectors are `stale-summary`, `package-path`, and `healthy-control`.

The private run owner validates `confirmation.json` with `--strict-holdback`, audits it with `--split holdout --fail-on-blockers --strict-judge`, and prepares it with `--split holdout --include-old-skill --runs-per-variant 3 --models gpt-6.1-sol`. Omit `--allow-missing-prompts`. Each command's failure signal is a non-zero exit. Inspect the 36 real rows for balanced arms, matching prompts and fixture bytes within each case, correct package paths, and no answer keys. Freeze the private case file and assembled manifest hashes before screen answers are visible. Any prompt edit after that point invalidates the sealed confirmation.

## Review before paid execution

All paid execution remains blocked until human review. The single answer subject is `gpt-6.1-sol`. The cross-family judge model and backend must be finalized at that review; `claude-review-required` is an explicit unresolved marker, not a runnable model choice. Review all 12 screen answers and their oracle evidence before authorizing 36 confirmation answers. Do not repair the skill or rewrite heldout cases between those stages without starting a new study.

Use the existing [evaluation runbook](../../../README.md) for isolated native execution. Fixture bootstraps require the Codex adapter's `workspace-write` sandbox. Resolve the project-only adapter to an absolute path before entering isolated workspaces. Do not expose the source checkout, host skill installation, private answer keys, or the alternate treatment package to an answer task.

Preparation requires `old_skill_paths` and `--include-old-skill`. Each later `grade`, `judge`, and `benchmark` invocation must repeat all three flags: `--variant with_skill --variant without_skill --variant old_skill`. Otherwise the old arm can be silently omitted. Use `--allow-scripts` on grade and benchmark. Set `--judge-runs 1`, select the reviewed cross-family judge, and do not configure a panel. Keep the 12-answer screen and 36-answer confirmation in separate output trees. No executable paid batch is provided here.

The primary score is each answer's existing strong executable oracle result. Judge explanations are secondary and soft. Skill-loading receipts are diagnostic and soft; loading earns no lift. Reject invalid treatment paths, contamination, incomplete or mismatched exposure, and missing output separately before comparing behavioral outcomes. A `skill_invoked` receipt alone cannot prove which mounted file supplied a read.

Reject any current-arm false green or healthy regression. Treat no separation, ceiling, floor, incomplete populations, or separation confined to explanation or exposure scores as inconclusive. A current-arm advantage against both previous and absent arms, with no rejection, is a candidate signal for human review. Four targeted cases do not establish broad skill efficacy. No saved verify-commands runs or weak results from another skill establish a measured weakness here.
