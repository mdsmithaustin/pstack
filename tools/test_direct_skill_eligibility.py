from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from direct_skill_eligibility import validate_answer_runs, validate_judge_receipt
from direct_skill_lanes import _eval_contract_sha256, _load_eval_manifest


MODEL = "gpt-5.6-sol"
SKILL = "verify-commands"
CASE = "behavior"


def canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def file_digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


class AnswerRunEligibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runs = self.root / "runs"
        self.manifest = self.root / "manifest.json"
        write_json(self.manifest, {
            "cases": [{
                "id": CASE,
                "kind": "positive",
                "split": "holdback",
                "assertions": [{
                    "name": "with-skill-loaded",
                    "type": "skill_invoked",
                    "expected": True,
                    "variants": ["with_skill"],
                    "severity": "gate",
                }],
            }],
        })
        self.write_answer_tree()

    def write_answer_tree(self, repetitions: int = 3, model: str = MODEL) -> None:
        identities = []
        for variant in ("with_skill", "old_skill"):
            for run_number in range(1, repetitions + 1):
                run_dir = f"{CASE}/{model}/{variant}/run-{run_number}"
                identities.append({
                    "case_id": CASE,
                    "model": model,
                    "variant": variant,
                    "run_number": run_number,
                    "run_dir": run_dir,
                    "task_sha256": f"sha256:{'1' * 64}",
                    "case_input_sha256": f"sha256:{'2' * 64}",
                    "instruction_sha256": f"sha256:{'3' * 64}",
                    "planned_skill_tree_hash": ("4" if variant == "with_skill" else "6") * 64,
                    "fixture_tree_hash": "5" * 64,
                })
        identities.sort(key=lambda row: (row["case_id"], row["model"], row["variant"], row["run_number"]))
        payload = {
            "schema_version": 2,
            "population": "answer",
            "eval_contract_sha256": _eval_contract_sha256(
                _load_eval_manifest(self.manifest), self.manifest, "holdback"
            ),
            "identities": identities,
        }
        design = {**payload, "design_sha256": canonical_digest(payload)}
        write_json(self.runs / "answer-design.json", design)
        for identity in identities:
            self.write_run(identity, design["design_sha256"])

    def write_run(self, identity: dict[str, object], design_digest: str) -> None:
        run_dir = self.runs / str(identity["run_dir"])
        run_dir.mkdir(parents=True, exist_ok=True)
        events = []
        if identity["variant"] == "with_skill":
            events.append({
                "type": "skill_load",
                "name": "Read",
                "input_summary": f"./skills/{SKILL}/SKILL.md",
                "status": "completed",
            })
        write_json(run_dir / "events.json", {
            "schema_version": 2,
            "source": "test",
            "events": events,
        })
        write_json(run_dir / "metrics.json", {"schema_version": 2, "source": "test"})
        (run_dir / "output.md").write_text("measured answer\n", encoding="utf-8")
        telemetry_basis = {
            "population": "answer",
            "provider": "codex",
            "runner": "codex",
            "model": identity["model"],
            "billing_scope": "run",
            "case_id": identity["case_id"],
            "run_number": identity["run_number"],
            "skill_tree_hash": identity["planned_skill_tree_hash"],
        }
        measurements = {
            name: {
                "availability": "available",
                "value": value,
                "provenance": "provider_reported",
                "basis": telemetry_basis,
            }
            for name, value in (("input_tokens", 10), ("output_tokens", 2), ("total_tokens", 12))
        }
        write_json(run_dir / "metadata.json", {
            "population": "answer",
            "case_id": identity["case_id"],
            "run_number": identity["run_number"],
            "variant": identity["variant"],
            "answer_design_sha256": design_digest,
            "answer_task_sha256": identity["task_sha256"],
            "answer_instruction_sha256": identity["instruction_sha256"],
            "skill_tree_hash": identity["planned_skill_tree_hash"],
            "fixture_tree_hash": identity["fixture_tree_hash"],
            "provider": "codex",
            "model": identity["model"],
            "returncode": 0,
            "timed_out": False,
            "invocation_state": "complete",
            "observation_complete": True,
            "trace_observation_complete": True,
            "process_observation_complete": True,
            "provider_response_complete": True,
            "operation_observation_complete": True,
            "telemetry_schema_version": 3,
            "telemetry": {
                "schema_version": 3,
                "population": "answer",
                "basis": telemetry_basis,
                "measurements": measurements,
            },
        })
        inventory = {
            name: file_digest(run_dir / name).removeprefix("sha256:")
            for name in ("output.md", "events.json", "metrics.json", "metadata.json")
        }
        write_json(run_dir / "artifact-commit.json", {
            "schema_version": 1,
            "required_files": ["output.md", "events.json", "metrics.json", "metadata.json"],
            "inventory_sha256": inventory,
        })

    def validate(self, **overrides: object) -> dict[str, object]:
        arguments = {
            "runs": self.runs,
            "manifest": self.manifest,
            "target_skill": SKILL,
            "split": "holdback",
            "model": MODEL,
            "repetitions": 3,
            "expected_case_ids": [CASE],
        }
        arguments.update(overrides)
        return validate_answer_runs(**arguments)

    def issue_codes(self, report: dict[str, object]) -> set[str]:
        return {issue["code"] for issue in report["issues"]}

    def test_valid_run_tree_is_headline_eligible(self) -> None:
        report = self.validate()
        self.assertEqual(report["status"], "eligible")
        self.assertEqual(report["issues"], [])
        self.assertEqual(report["counts"]["expected_runs"], 6)
        self.assertEqual(report["counts"]["exposure_runs"], 6)
        self.assertEqual(len(report["evidence_digests"]["artifact_commits"]), 6)

    def test_missing_run_directory_is_infrastructure_failure(self) -> None:
        run = self.runs / CASE / MODEL / "with_skill" / "run-3"
        for path in run.iterdir():
            path.unlink()
        run.rmdir()
        report = self.validate()
        self.assertIn("run_directory_missing", self.issue_codes(report))
        self.assertFalse(report["headline_eligible"])

    def test_duplicate_design_coordinate_is_missing_measurement(self) -> None:
        design_path = self.runs / "answer-design.json"
        design = json.loads(design_path.read_text(encoding="utf-8"))
        design["identities"].append(dict(design["identities"][0]))
        payload = {key: design[key] for key in (
            "schema_version", "population", "eval_contract_sha256", "identities"
        )}
        design["design_sha256"] = canonical_digest(payload)
        write_json(design_path, design)
        report = self.validate()
        self.assertIn("duplicate_run", self.issue_codes(report))

    def test_wrong_model_and_repetition_request_are_rejected(self) -> None:
        wrong_model = self.validate(model="claude-opus-5")
        self.assertIn("model_population", self.issue_codes(wrong_model))
        wrong_runs = self.validate(repetitions=4)
        self.assertIn("missing_runs", self.issue_codes(wrong_runs))
        insufficient = self.validate(repetitions=2)
        self.assertIn("insufficient_repetitions", self.issue_codes(insufficient))

    def test_stale_metadata_hash_is_infrastructure_failure(self) -> None:
        path = self.runs / CASE / MODEL / "with_skill" / "run-1" / "metadata.json"
        metadata = json.loads(path.read_text(encoding="utf-8"))
        metadata["fixture_tree_hash"] = "f" * 64
        write_json(path, metadata)
        report = self.validate()
        codes = self.issue_codes(report)
        self.assertIn("metadata_attestation_mismatch", codes)
        self.assertIn("artifact_digest_mismatch", codes)

    def test_missing_artifact_commit_is_infrastructure_failure(self) -> None:
        path = self.runs / CASE / MODEL / "old_skill" / "run-2" / "artifact-commit.json"
        path.unlink()
        report = self.validate()
        self.assertIn("artifact_commit_missing", self.issue_codes(report))

    def test_undigested_required_artifact_is_infrastructure_failure(self) -> None:
        run = self.runs / CASE / MODEL / "old_skill" / "run-2"
        commit_path = run / "artifact-commit.json"
        commit = json.loads(commit_path.read_text(encoding="utf-8"))
        commit["required_files"].append("extra.json")
        write_json(commit_path, commit)
        report = self.validate()
        self.assertIn("artifact_digest_missing", self.issue_codes(report))

    def test_completed_nonzero_invocation_is_candidate_failure(self) -> None:
        run = self.runs / CASE / MODEL / "with_skill" / "run-2"
        path = run / "metadata.json"
        metadata = json.loads(path.read_text(encoding="utf-8"))
        metadata["returncode"] = 7
        write_json(path, metadata)
        commit = json.loads((run / "artifact-commit.json").read_text(encoding="utf-8"))
        commit["inventory_sha256"]["metadata.json"] = file_digest(path).removeprefix("sha256:")
        write_json(run / "artifact-commit.json", commit)
        report = self.validate()
        categories = {issue["category"] for issue in report["issues"]}
        self.assertIn("candidate_failure", categories)

    def test_malformed_invocation_lifecycle_is_infrastructure_failure(self) -> None:
        run = self.runs / CASE / MODEL / "with_skill" / "run-2"
        path = run / "metadata.json"
        metadata = json.loads(path.read_text(encoding="utf-8"))
        metadata.pop("timed_out")
        write_json(path, metadata)
        commit = json.loads((run / "artifact-commit.json").read_text(encoding="utf-8"))
        commit["inventory_sha256"]["metadata.json"] = file_digest(path).removeprefix("sha256:")
        write_json(run / "artifact-commit.json", commit)
        report = self.validate()
        issues = [issue for issue in report["issues"] if issue["code"] == "candidate_invocation_invalid"]
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["category"], "infrastructure_failure")

    def test_answer_cli_writes_report_and_returns_success(self) -> None:
        output = self.root / "answer-eligibility.json"
        result = subprocess.run(
            [
                "python3",
                str(Path(__file__).with_name("direct_skill_eligibility.py")),
                "answer-runs",
                "--runs", str(self.runs),
                "--manifest", str(self.manifest),
                "--skill", SKILL,
                "--split", "holdback",
                "--model", MODEL,
                "--repetitions", "3",
                "--case", CASE,
                "--out", str(output),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(output.read_text(encoding="utf-8"))["headline_eligible"])


class JudgeReceiptEligibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tasks = self.root / "compare-tasks.jsonl"
        self.results = self.root / "compare-results.jsonl"
        self.prompt = self.root / "judge-prompt.md"
        self.rubric = self.root / "judge-rubric.md"
        self.calibration_set = self.root / "judge-calibration.jsonl"
        self.calibration_results = self.root / "judge-calibration-results.jsonl"
        self.order_swap_results = self.root / "judge-order-swap-results.jsonl"
        self.receipt = self.root / "judge-receipt.json"
        self.prompt.write_text("Judge prompt\n", encoding="utf-8")
        self.rubric.write_text("Judge rubric\n", encoding="utf-8")
        self.write_jsonl(self.calibration_set, [
            {
                "id": f"control-{number}",
                "expected_winner": "A" if number % 2 else "B",
                "critical": number <= 2,
            }
            for number in range(1, 6)
        ])
        self.write_jsonl(self.calibration_results, [
            {
                "id": f"control-{number}",
                "winner": "A" if number % 2 else "B",
                "observation_complete": True,
                "returncode": 0,
            }
            for number in range(1, 6)
        ])
        self.write_jsonl(self.order_swap_results, [
            {
                "pair_id": f"swap-{number}",
                "original_winner": "A",
                "swapped_winner": "B",
                "original_observation_complete": True,
                "swapped_observation_complete": True,
                "original_returncode": 0,
                "swapped_returncode": 0,
            }
            for number in range(1, 5)
        ])
        task_rows = []
        result_rows = []
        for number in (1, 2):
            task_id = f"case-{number}::run-1::blind-with_skill-vs-old_skill"
            task = {
                "schema_version": 1,
                "comparison_task_id": task_id,
                "case_id": f"case-{number}",
                "model": MODEL,
                "run_number": 1,
                "answer_design_sha256": f"sha256:{'a' * 64}",
                "blind_nonce": f"{number:032x}",
                "prompt": f"Case {number}",
                "expectations": ["ground the answer"],
                "rubric": {"expected_behavior": ["grounded"], "review_rubric": ["accurate"]},
                "output_a_sha256": f"sha256:{'c' * 64}",
                "output_b_sha256": f"sha256:{'d' * 64}",
                "result_schema": {"winner": "A|B|TIE"},
                "comparison_design_sha256": f"sha256:{'b' * 64}",
            }
            task_identity = {
                key: task[key]
                for key in (
                    "schema_version", "comparison_task_id", "case_id", "model", "run_number",
                    "answer_design_sha256", "blind_nonce", "prompt", "expectations", "rubric",
                    "output_a_sha256", "output_b_sha256", "result_schema",
                )
            }
            task_digest = canonical_digest(task_identity)
            task["comparison_task_sha256"] = task_digest
            task_rows.append(task)
            result_rows.append({
                "schema_version": 1,
                "comparison_task_id": task_id,
                "observation_complete": True,
                "returncode": 0,
                "answer_design_sha256": task["answer_design_sha256"],
                "comparison_design_sha256": task["comparison_design_sha256"],
                "comparison_task_sha256": task_digest,
                "winner": "A",
                "reasoning": "A better satisfies the rubric.",
            })
        self.write_jsonl(self.tasks, task_rows)
        self.write_jsonl(self.results, result_rows)
        self.write_receipt()

    def write_jsonl(self, path: Path, rows: list[dict[str, object]]) -> None:
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    def write_receipt(self, **overrides: object) -> None:
        receipt = {
            "schema_version": 1,
            "answer": {"family": "openai", "model": MODEL},
            "judge": {"family": "anthropic", "model": "claude-opus-5"},
            "evidence_sha256": {
                "compare_tasks": file_digest(self.tasks),
                "results": file_digest(self.results),
                "prompt": file_digest(self.prompt),
                "rubric": file_digest(self.rubric),
                "calibration_set": file_digest(self.calibration_set),
                "calibration_results": file_digest(self.calibration_results),
                "order_swap_results": file_digest(self.order_swap_results),
            },
            "calibration": {
                "labeled_count": 5,
                "correct_count": 5,
                "accuracy": 1.0,
                "minimum_accuracy": 0.8,
                "critical_controls_total": 2,
                "critical_controls_passed": 2,
            },
            "order_swap": {
                "pair_count": 4,
                "consistent_count": 4,
                "consistency": 1.0,
                "minimum_consistency": 0.9,
            },
            "verdict_coverage": {"expected": 2, "observed": 2, "complete": True},
        }
        receipt.update(overrides)
        write_json(self.receipt, receipt)

    def validate(self) -> dict[str, object]:
        return validate_judge_receipt(
            receipt_path=self.receipt,
            compare_tasks_path=self.tasks,
            results_path=self.results,
            prompt_path=self.prompt,
            rubric_path=self.rubric,
            calibration_set_path=self.calibration_set,
            calibration_results_path=self.calibration_results,
            order_swap_results_path=self.order_swap_results,
            answer_family="openai",
            answer_model=MODEL,
        )

    def issue_codes(self, report: dict[str, object]) -> set[str]:
        return {issue["code"] for issue in report["issues"]}

    def test_valid_alternative_family_receipt_is_headline_eligible(self) -> None:
        report = self.validate()
        self.assertEqual(report["status"], "eligible")
        self.assertEqual(report["counts"]["expected_verdicts"], 2)
        self.assertEqual(report["counts"]["calibration_labels"], 5)
        self.assertEqual(report["counts"]["order_swap_pairs"], 4)

    def test_same_family_judge_is_rejected(self) -> None:
        self.write_receipt(judge={"family": "openai", "model": "gpt-6-astra"})
        self.assertIn("judge_not_cross_family", self.issue_codes(self.validate()))

    def test_stale_task_digest_is_rejected(self) -> None:
        rows = [json.loads(line) for line in self.results.read_text(encoding="utf-8").splitlines()]
        rows[0]["comparison_task_sha256"] = f"sha256:{'f' * 64}"
        self.write_jsonl(self.results, rows)
        self.write_receipt()
        self.assertIn("stale_task_digest", self.issue_codes(self.validate()))

    def test_failed_calibration_is_rejected(self) -> None:
        rows = [json.loads(line) for line in self.calibration_results.read_text().splitlines()]
        rows[0]["winner"] = "B"
        self.write_jsonl(self.calibration_results, rows)
        self.write_receipt(calibration={
            "labeled_count": 5,
            "correct_count": 4,
            "accuracy": 0.8,
            "minimum_accuracy": 0.8,
            "critical_controls_total": 2,
            "critical_controls_passed": 1,
        })
        self.assertIn("calibration_failed", self.issue_codes(self.validate()))

    def test_fabricated_calibration_summary_is_rejected(self) -> None:
        rows = [json.loads(line) for line in self.calibration_results.read_text().splitlines()]
        rows[0]["winner"] = "B"
        self.write_jsonl(self.calibration_results, rows)
        self.write_receipt()
        self.assertIn("calibration_failed", self.issue_codes(self.validate()))

    def test_inconsistent_order_swap_artifact_is_rejected(self) -> None:
        rows = [json.loads(line) for line in self.order_swap_results.read_text().splitlines()]
        rows[0]["swapped_winner"] = "A"
        self.write_jsonl(self.order_swap_results, rows)
        self.write_receipt(order_swap={
            "pair_count": 4,
            "consistent_count": 3,
            "consistency": 0.75,
            "minimum_consistency": 0.9,
        })
        self.assertIn("order_swap_failed", self.issue_codes(self.validate()))

    def test_incomplete_verdict_population_is_rejected(self) -> None:
        first = self.results.read_text(encoding="utf-8").splitlines()[0]
        self.results.write_text(first + "\n", encoding="utf-8")
        self.write_receipt(verdict_coverage={"expected": 2, "observed": 1, "complete": False})
        self.assertIn("verdict_coverage", self.issue_codes(self.validate()))

    def test_stale_receipt_artifact_digest_is_rejected(self) -> None:
        receipt = json.loads(self.receipt.read_text(encoding="utf-8"))
        receipt["evidence_sha256"]["prompt"] = f"sha256:{'f' * 64}"
        write_json(self.receipt, receipt)
        self.assertIn("judge_digest_mismatch", self.issue_codes(self.validate()))

    def test_cli_writes_report_and_returns_success(self) -> None:
        output = self.root / "eligibility.json"
        result = subprocess.run(
            [
                "python3",
                str(Path(__file__).with_name("direct_skill_eligibility.py")),
                "judge-receipt",
                "--receipt", str(self.receipt),
                "--compare-tasks", str(self.tasks),
                "--results", str(self.results),
                "--prompt", str(self.prompt),
                "--rubric", str(self.rubric),
                "--calibration-set", str(self.calibration_set),
                "--calibration-results", str(self.calibration_results),
                "--order-swap-results", str(self.order_swap_results),
                "--answer-family", "openai",
                "--answer-model", MODEL,
                "--out", str(output),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(output.read_text(encoding="utf-8"))["headline_eligible"])


if __name__ == "__main__":
    unittest.main()
