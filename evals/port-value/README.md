# Port value comparison

This controller compares native Codex, the recorded upstream pstack, and the committed port on three application tasks. Each arm has two repetitions per task. The frozen plan contains 18 application lineages and 36 stage opportunities.

The comparison makes skills available for cold-start, relevance-driven discovery and measures executable application acceptance. It does not explicitly activate poteto-mode. Skill availability does not establish skill use. The retained native transcripts need a separate exposure review before anyone claims that a particular workflow caused an outcome. The private oracles do not grade requested README updates or broader task quality.

The completed [2026-10-19 comparison](results/2026-10-19.md) reports acceptance, observed usage, durations, exposure evidence, and limits.

## Verify the historical gate evidence

The [historical validation receipt](results/2026-10-19-validation.json) records gate run `01M5A84DM51F31XH1YTGENDRF2` at tested head `4244e8d387bc60e5e34197829429dedc32a55fb8`. This run prepared and calibrated new guidance, then executed two separate synthetic public application API canaries, one per guidance arm, with four completed named children. Raw spawn arguments, child completion, exact guidance, capture integrity, and cleanup were verified. Historical persona proof and all 36 retained study stages were reconciled separately without repeating study calls. The receipt lists six passing scenarios, relative evidence names, and full source and evidence hashes. Its `prior_validation` reference preserves run `01M5A55HYA9B86NW7Z5TQDDVB9`, the previous receipt hash, and the previous canary proof hash. Source hashes identify the executed bytes before this documentation update.

Use a reader-selected external evidence root containing the listed relative artifacts. Keep raw streams and private evidence outside Git. This model-free command verifies retained artifact identity, including the receipt's canary proof and historical analysis. It checks source bytes at receipt publication commit `6a66f7818f9eb43a2be4d1f380c015de65132b2b`, which preserves all recorded source hashes and must be available in local Git history. The proof still identifies the original `validation_head`. The maintained checkout has since archived some of those sources. The command does not execute evidence scripts, repeat model calls, or validate the current checkout. Run it from the repository root. A nonzero exit, missing artifact or revision, hash mismatch, or absence of `retained_evidence_verified: true` means verification failed.

```sh
EVIDENCE_ROOT=/absolute/external/evidence-directory
python3 -B - "$EVIDENCE_ROOT" <<'PY'
from pathlib import Path
import hashlib
import json
import subprocess
import sys

receipt = json.loads(Path("evals/port-value/results/2026-10-19-validation.json").read_text())
root = Path(sys.argv[1])
if not root.is_absolute() or not root.is_dir():
    raise SystemExit("external evidence directory required")
if not receipt["artifact_sha256"] or len(receipt["scenarios"]) != 6:
    raise SystemExit("incomplete validation receipt")
for name, expected in receipt["artifact_sha256"].items():
    if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
        raise SystemExit(f"evidence hash mismatch: {name}")
source_revision = "6a66f7818f9eb43a2be4d1f380c015de65132b2b"
for name, expected in receipt["source_sha256"].items():
    source = subprocess.check_output(["git", "show", f"{source_revision}:{name}"])
    if hashlib.sha256(source).hexdigest() != expected:
        raise SystemExit(f"source hash mismatch: {name}")
proof = json.loads((root / "fresh-persona-canaries/proof.json").read_text())
if proof["source"]["revision"] != receipt["validation_head"]:
    raise SystemExit("canary validation head mismatch")
if set(proof["arms"]) != {"upstream", "current"}:
    raise SystemExit("both canary arms required")
for arm in proof["arms"].values():
    if not all(arm[key] is True for key in ("native_valid", "guidance_valid", "cleanup_confirmed")):
        raise SystemExit("invalid canary receipt")
    if sorted(child["role"] for child in arm["children"]) != ["comment-sicko", "poteto-agent"]:
        raise SystemExit("both named children required")
print(json.dumps({"retained_evidence_verified": True, "gate_run_id": receipt["gate_run_id"]}))
PY
```

## Prepare a frozen comparison

Use Python 3.12 or later. The application owner also needs `sbx`, Docker, the prepared native template, and working model credentials. Discover those tools through `PATH`. This repository has no `mise` task for this controller.

Before preparation, fetch the exact pinned upstream commit from `cursor/plugins` into this checkout and confirm it is available. Run these commands from the repository root. A nonzero exit from either command means the prerequisite failed; do not continue to preparation.

```sh
git fetch https://github.com/cursor/plugins.git 1b6d44ff26d4e242f4e8f68c391e6d2f7ca16def
git cat-file -e '1b6d44ff26d4e242f4e8f68c391e6d2f7ca16def^{commit}'
```

Create a runtime receipt after probing the actual template. The required JSON fields are `template`, `observed_template_id`, `cli_version`, and a `capabilities` object containing `skills: true` and `multi_agent: true`. Retain the bootstrap observations with the receipt. The observed template ID may be a short local identifier. It is not a full OCI digest. Record an archive hash separately if one exists.

Run the following command from the repository root. Replace the directory and runtime receipt with new paths outside the checkout. Preparation creates the directory and refuses an existing one. A nonzero exit, missing `seal.json`, or a calibration receipt whose `passed` field is false means preparation failed.

```sh
python3 evals/port-value/study.py prepare ../port-value-run \
	--runtime-receipt ../port-value-runtime.json \
	--model gpt-6.1-sol --effort high --timeout 240 --seed 73129
```

Preparation freezes both requests, complete project files, private checks, controls, runtime settings, controller sources, and complete guidance trees. It exports upstream `1b6d44ff26d4e242f4e8f68c391e6d2f7ca16def` from `pstack/skills` and `pstack/agents`, and current port `701c9a6f09ae3b0bd56a4962ff299c21accf8690` from `skills`. The exported trees do not depend on uncommitted working-tree skills. Separate project and guidance snapshots preserve runtime file modes before preparation seals the input copies read-only. Runtime requests use those prepared manifests so Git cloning preserves the same guidance identity.

The upstream compatibility ledger records 102 invocation-policy edits. It translates `disable-model-invocation: true` into native `agents/openai.yaml` policy with `allow_implicit_invocation: false`. It also records five persona setup entries. Two retain the exact pinned root persona files and their source hashes. The other three contain the registration adapter and the generated `poteto-agent` and `comment-sicko` native TOML files. Each entry retains before and after bytes and hashes.

The upstream registration adapter occupies the existing application owner's `pstack-harness/scripts/subagents.py` installer path. It adds no `pstack-harness/SKILL.md`. The native persona instructions contain the upstream body plus a local skill-loading prefix. All upstream skill workflow bodies and tool and model fallback instructions stay unchanged. This arm is the minimally adapted upstream package, including its required personas. The current arm uses its pinned native port and installer.

The runtime receipt establishes generic delegation capability. Successful file registration does not prove that Codex loaded or invoked the named personas. A separate native preflight must establish that capability before task calls. Registration tests alone cannot establish workflow efficacy.

The native arm receives no custom skill tree. Every arm receives the same project and organic request, requested model, effort, execution template, tools, network policy, and deadline. Arm names and private acceptance feedback do not enter requests. The initial arm order is randomized within task and repetition blocks using the recorded seed.

Preparation calibrates each oracle against passing initial and maintenance controls, no-op controls at both stages, and named initial and maintenance defects. Every check must return a strict result with a positive assertion count. The frozen `heldout.json` also checks request bytes against committed public `evals` files at the port pin. That exact-byte check supplements the scenario overlap review in [cases/README.md](cases/README.md). It does not prove absence from external training data.

## Execute planned opportunities

The shared [application owner](../canon/application.py) creates an isolated native session, captures the application, removes the candidate sandbox, and returns the result. Acceptance then reconstructs the capture in a separate Docker container. The container has no network, a read-only application mount, a read-only root, resource limits, and only the private oracle and `checks.json` as checker files. The pinned Python image is the same image used by canon's private Python checks.

Use one planned cell to check the complete two-stage flow. A nonzero exit means a preparation or command error. The resulting native states and acceptance fields decide whether the application succeeded.

```sh
python3 evals/port-value/study.py run ../port-value-run --cell p01
```

Limit the next dispatch to one unspent opportunity with this command. A nonzero exit means a command error. Check `report.json` to identify the dispatched stage and its result.

```sh
python3 evals/port-value/study.py run ../port-value-run --limit 1
```

Run remaining opportunities with at most two concurrent lineages. A nonzero exit means a command error. Native failures, missing captures, and oracle errors remain explicit in `report.json` even when dispatch itself exits zero.

```sh
python3 evals/port-value/study.py run ../port-value-run --concurrency 2
```

An existing stage directory is spent, including a directory left by a crash. Repeating `run` selects only unspent stages. It never retries a spent native call. A study dispatch lock prevents simultaneous controller processes from exceeding the two-lineage limit. Missing or invalid initial capture blocks maintenance. A valid initial capture binds the exact maintenance parent even when initial behavior or native completion failed. Maintenance uses a fresh session and the same arm's guidance. It receives only the frozen maintenance request, without acceptance feedback.

The controller checks frozen inputs and source hashes before each application call and before grading. It also checks the observed local template ID before each call, with a 15-second catalog deadline. Changed input makes the comparison invalid. Start a new preparation after an intentional controller or runtime source change.

## Read all planned outcomes

Generate `report.json` and `report.md` with this command. A nonzero exit means the report could not be generated. An `input_integrity_error` value invalidates acceptance even when earlier behavioral checks passed.

```sh
python3 evals/port-value/study.py report ../port-value-run
```

The report keeps all 36 opportunities, including attempted, incomplete, blocked, and never-started stages. It separates native validity from executable application acceptance. Both-stage acceptance requires valid native completion, a replayable retained capture, and a passing strict private grade for each stage.

Report generation validates the capture's blobs and manifest and requires its directory to be the planned stage's `application/harvest/capture`. It binds the application receipt and request claim to the frozen request, arm guidance, and runtime. The initial parent must match the frozen project. The maintenance parent must match the same lineage's validated retained initial capture. It also binds the grade to the stage, oracle, and capture. It compares the retained acceptance receipt and parses the oracle output again.

Invalid records receive an explicit `evidence_error` and cannot pass. Malformed state, native validity, usage, total elapsed, and native duration fields receive safe report values before aggregation. Duration values must be null or nonnegative finite numbers. Native results, usage, and durations require a retained application receipt bound to the frozen stage inputs, including attempts without a capture. Reported usage and durations must match that receipt. Invalid retained evidence makes native results, usage, and both durations unknown for that stage. Correctly bound failed attempts retain their known measurements without passing acceptance. These errors preserve all planned opportunities. Reporting never repeats spent calls.

The report retains two separate durations. `native_elapsed_s` measures the native process inside the sandbox. `elapsed_s` measures the application attempt from its claim through sandbox cleanup and excludes acceptance grading. Each arm reports sums of known values and separate known and unknown opportunity counts for each duration. A sum is null when no duration is known. Unknown durations never become zero. Raw observed usage, unknown usage counts, and paired task outcomes remain separate fields.

The paired sample contains three tasks and two repetitions per arm. Timing results describe this sample and do not establish a winner or general performance. Remote inference capacity and its effect on concurrency are unmeasured. Requested model settings do not prove served model identity. Acceptance does not measure requested README updates, human judgment of task quality, or the efficacy of an explicitly activated poteto workflow.

Raw native streams, captures, checker logs, and execution receipts stay in the external run directory. Keep them outside Git. Preserve failed preparations as diagnostic receipts. Do not promote findings from this three-task comparison into a general causal claim or count repetitions as independent task diversity.

## Reproduce an archived report

Use the retained external run directory and its frozen sources to reproduce a report without model calls or sandbox creation. Keep the run directory at its original recorded absolute path. Integrity checks compare the absolute source paths in `inputs/plan.json` as well as their hashes. Copying the directory elsewhere and changing those paths invalidates the archive.

Set `RUNROOT` to that original absolute directory. This example requires host Python 3 and Docker. It derives the original `EVALS` directory and pinned `oracle_image` from the plan. The two bind mounts expose only the run directory and its frozen controller sources. The source mount is read-only. The run mount permits replacement of the derived reports. No host Docker socket enters the container.

A nonzero exit, a non-null `input_integrity_error`, or changed report hashes means reproduction failed. The script also rejects missing reports and a report with no opportunities. A successful run prints `exact_reproduction: true` and both report hashes.

```sh
RUNROOT=/absolute/original/run-directory
python3 - "$RUNROOT" <<'PY'
from pathlib import Path
import hashlib
import json
import subprocess
import sys

runroot = Path(sys.argv[1]).resolve()
plan = json.loads((runroot / "inputs/plan.json").read_text())
source = next(Path(p) for p in plan["sources"] if p.endswith("/port-value/study.py"))
evals = source.parent.parent
reports = [runroot / "report.json", runroot / "report.md"]
before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in reports}
command = [
	"docker", "run", "--rm", "--network", "none", "--read-only",
	"--cap-drop", "ALL", "--security-opt", "no-new-privileges",
	"--pids-limit", "128", "--memory", "512m", "--cpus", "1",
	"--tmpfs", "/tmp:rw,nosuid,size=128m",
	"--mount", f"type=bind,src={runroot},dst={runroot}",
	"--mount", f"type=bind,src={runroot / 'inputs/source'},dst={evals},readonly",
	plan["oracle_image"], "python", "-I", "-B", str(source), "report", str(runroot),
]
subprocess.run(command, check=True)
report = json.loads((runroot / "report.json").read_text())
after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in reports}
if report["input_integrity_error"] is not None:
	raise SystemExit(report["input_integrity_error"])
if report["planned_opportunities"] != plan["opportunities"] or not report["rows"]:
	raise SystemExit("report does not cover the frozen plan")
if before != after:
	raise SystemExit("report hashes changed")
print(json.dumps({"exact_reproduction": True, "report_sha256": after}, indent=2))
PY
```

Preserve the raw native streams, captures, and private checker files outside Git. Share only the aggregate results that omit private host paths and task evidence.

## Verify the controller without model calls

The controller tests use actual application snapshots and replay. A recording application callable writes native outcome receipts, and local subprocess oracles check their output. A real Git clone checks guidance identity after the same Git mode normalization that the native sandbox uses. The tests run the upstream installer, inspect its native TOML files, and exercise report rejection of tampered captures, false grades, and broken evidence bindings. A test also calls the real application API with recorded sandbox command responses, then validates its actual harvest capture layout and retained durations through the report. These tests validate the controller, not named persona activation, model behavior, or Docker isolation. The application owner's tests cover native process handling and capture integrity separately.

Use Python 3.12 or later. Before running the controller tests, fetch the exact pinned upstream commit from `cursor/plugins` into this checkout and confirm it is available. The tests export its skills and read its persona files, so a fresh clone needs this prerequisite even without model calls. Run these commands from the repository root. A nonzero exit from either command means the prerequisite failed; do not continue to the tests.

```sh
git fetch https://github.com/cursor/plugins.git 1b6d44ff26d4e242f4e8f68c391e6d2f7ca16def
git cat-file -e '1b6d44ff26d4e242f4e8f68c391e6d2f7ca16def^{commit}'
```

Run this command at the repository root. A nonzero exit, a failure summary, or a zero-test summary means verification failed.

```sh
python3 -m unittest discover -s evals/port-value -p test_study.py -v
```

Run the case controls separately with this command. A nonzero exit, a failure summary, or a zero-test summary means verification failed.

```sh
python3 -m unittest discover -s evals/port-value -p test_cases.py -v
```
