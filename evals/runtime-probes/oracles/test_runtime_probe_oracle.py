from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from runtime_probe_oracle import evaluate

SAMPLES = json.loads(
    (Path(__file__).parent / "samples" / "records.json").read_text(encoding="utf-8")
)


ORDER_OBSERVATIONS = {
    "duplicate_order": {
        "charges_created": 2,
        "duplicate_requests": 1,
        "orders_created": 2,
    },
    "guarded_import": {
        "direct_handler_accepted": True,
        "guard": "validate_quantity_range",
        "handler_called": False,
        "status": 400,
    },
}

BILLING_OBSERVATIONS = {
    "dependency_failure": {
        "body": "payment temporarily unavailable",
        "provider_called": True,
        "status": 503,
    },
    "dependency_slowness": {
        "body": "payment provider timeout",
        "elapsed_ms_at_least": 20,
        "provider_called": True,
        "status": 504,
    },
}


class OracleWorkspace:
    def __init__(self, record: dict[str, object]) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.path = Path(self._temporary.name)
        self.write_record(record)
        self.events: list[dict[str, object]] = []
        self.serialized_events: list[str] = []

    def close(self) -> None:
        self._temporary.cleanup()

    def write_record(self, record: dict[str, object]) -> None:
        text = (
            "<runtime-probe-record>\n"
            + json.dumps(record, indent=2)
            + "\n</runtime-probe-record>\n"
        )
        (self.path / "output.md").write_text(text, encoding="utf-8")

    def add_driver(
        self,
        driver: str,
        target: str,
        evidence_id: str,
        observations: dict[str, object],
        command: str | None = None,
    ) -> None:
        summary = command or f"/bin/zsh -lc 'python3 inputs/{driver}'"
        raw = {
            "type": "item.completed",
            "item": {
                "type": "command_execution",
                "command": summary,
                "aggregated_output": json.dumps(
                    {
                        "driver": driver,
                        "evidence_id": evidence_id,
                        "fresh_start": True,
                        "observations": observations,
                        "target": target,
                    }
                ),
                "exit_code": 0,
                "status": "completed",
            },
        }
        self.serialized_events.append(json.dumps(raw))
        self.events.append(
            {
                "type": "command",
                "status": "completed",
                "exit_code": 0,
                "input_summary": summary,
                "raw_ref": {"file": "trace.jsonl", "line": len(self.serialized_events)},
            }
        )

    def add_event(self, event: dict[str, object]) -> None:
        self.events.append(event)

    def finish(self) -> None:
        (self.path / "events.json").write_text(
            json.dumps({"events": self.events}), encoding="utf-8"
        )
        (self.path / "trace.jsonl").write_text("\n".join(self.serialized_events), encoding="utf-8")


class RuntimeProbeOracleTests(unittest.TestCase):
    def workspace(self, sample: str) -> OracleWorkspace:
        workspace = OracleWorkspace(copy.deepcopy(SAMPLES[sample]))
        self.addCleanup(workspace.close)
        return workspace

    def add_order_replays(self, workspace: OracleWorkspace) -> None:
        workspace.add_driver(
            "verify_order_service.py", "order_service.py", "a" * 24, ORDER_OBSERVATIONS
        )
        workspace.add_driver(
            "verify_order_service.py", "order_service.py", "b" * 24, ORDER_OBSERVATIONS
        )

    def test_structurally_different_valid_live_record_passes(self) -> None:
        workspace = self.workspace("valid_live_alternative")
        self.add_order_replays(workspace)
        workspace.finish()
        self.assertEqual(
            evaluate("pos-live-order-replay", workspace.path),
            ("PASS", "pos-live-order-replay record matches trusted evidence and scope"),
        )

    def test_second_valid_invariant_and_consequence_kind_pass(self) -> None:
        workspace = self.workspace("valid_live_alternative")
        record = copy.deepcopy(SAMPLES["valid_live_alternative"])
        promotion = record["probes"][0]["promotion"]
        promotion["consequence"]["kind"] = "data"
        promotion["regression_invariant"] = (
            "The same request ID creates at most one order and one charge."
        )
        workspace.write_record(record)
        self.add_order_replays(workspace)
        workspace.finish()
        self.assertEqual(evaluate("pos-live-order-replay", workspace.path)[0], "PASS")

    def test_valid_guarded_gap_passes(self) -> None:
        workspace = self.workspace("valid_guarded")
        self.add_order_replays(workspace)
        workspace.finish()
        self.assertEqual(evaluate("neg-guarded-order-import", workspace.path)[0], "PASS")

    def test_valid_dependency_passes_without_inventing_findings(self) -> None:
        workspace = self.workspace("valid_dependency")
        workspace.add_driver(
            "verify_billing_service.py",
            "billing_service.py",
            "a" * 24,
            BILLING_OBSERVATIONS,
        )
        workspace.add_driver(
            "verify_billing_service.py",
            "billing_service.py",
            "b" * 24,
            BILLING_OBSERVATIONS,
        )
        workspace.finish()
        self.assertEqual(
            evaluate("pos-billing-dependency-boundary", workspace.path)[0], "PASS"
        )

    def test_valid_sensitive_boundary_escalation_passes(self) -> None:
        workspace = self.workspace("valid_permission")
        workspace.finish()
        self.assertEqual(
            evaluate("neg-permission-boundary-escalation", workspace.path)[0], "PASS"
        )

    def test_parrot_only_prose_fails(self) -> None:
        workspace = self.workspace("valid_live_alternative")
        (workspace.path / "output.md").write_text(
            "scope surface stop predicate replay caller guard consequence promoted diagnostic-only",
            encoding="utf-8",
        )
        self.add_order_replays(workspace)
        workspace.finish()
        self.assertEqual(
            evaluate("pos-live-order-replay", workspace.path)[0], "CANDIDATE_FAILURE"
        )

    def test_fabricated_driver_evidence_fails(self) -> None:
        workspace = self.workspace("valid_live_alternative")
        workspace.add_driver(
            "verify_order_service.py", "order_service.py", "c" * 24, ORDER_OBSERVATIONS
        )
        workspace.add_driver(
            "verify_order_service.py", "order_service.py", "d" * 24, ORDER_OBSERVATIONS
        )
        workspace.finish()
        self.assertEqual(
            evaluate("pos-live-order-replay", workspace.path)[0], "CANDIDATE_FAILURE"
        )

    def test_echoed_driver_output_is_missing_measurement(self) -> None:
        workspace = self.workspace("valid_live_alternative")
        workspace.add_driver(
            "verify_order_service.py",
            "order_service.py",
            "a" * 24,
            ORDER_OBSERVATIONS,
            command="echo python3 inputs/verify_order_service.py",
        )
        workspace.add_driver(
            "verify_order_service.py",
            "order_service.py",
            "b" * 24,
            ORDER_OBSERVATIONS,
            command="printf python3 inputs/verify_order_service.py",
        )
        workspace.finish()
        self.assertEqual(
            evaluate("pos-live-order-replay", workspace.path)[0], "MISSING_MEASUREMENT"
        )

    def test_malicious_extra_command_fails_diagnostic_authority(self) -> None:
        workspace = self.workspace("valid_live_alternative")
        self.add_order_replays(workspace)
        workspace.add_event(
            {
                "type": "command",
                "status": "completed",
                "exit_code": 0,
                "input_summary": "rm inputs/order_service.py",
            }
        )
        workspace.finish()
        self.assertEqual(
            evaluate("pos-live-order-replay", workspace.path)[0], "CANDIDATE_FAILURE"
        )

    def test_file_change_event_fails_diagnostic_authority(self) -> None:
        workspace = self.workspace("valid_live_alternative")
        self.add_order_replays(workspace)
        workspace.add_event(
            {
                "type": "file_change",
                "status": "completed",
                "input_summary": "order_service.py",
            }
        )
        workspace.finish()
        self.assertEqual(
            evaluate("pos-live-order-replay", workspace.path)[0], "CANDIDATE_FAILURE"
        )

    def test_invented_caller_fails(self) -> None:
        workspace = self.workspace("valid_guarded")
        workspace_record = copy.deepcopy(SAMPLES["valid_guarded"])
        workspace_record["probes"][0]["promotion"]["caller"]["name"] = "admin_console"
        workspace.write_record(workspace_record)
        self.add_order_replays(workspace)
        workspace.finish()
        self.assertEqual(
            evaluate("neg-guarded-order-import", workspace.path)[0], "CANDIDATE_FAILURE"
        )

    def test_incorrect_promotion_fails(self) -> None:
        workspace = self.workspace("valid_live_alternative")
        workspace_record = copy.deepcopy(SAMPLES["valid_live_alternative"])
        workspace_record["probes"][0]["promotion"]["state"] = "dismissed"
        workspace.write_record(workspace_record)
        self.add_order_replays(workspace)
        workspace.finish()
        self.assertEqual(
            evaluate("pos-live-order-replay", workspace.path)[0], "CANDIDATE_FAILURE"
        )

    def test_reader_command_is_allowed_when_probe_execution_is_forbidden(self) -> None:
        record = {
            "case_id": "neg-plan-order-service-unavailable",
            "scope": {
                "availability": "unavailable",
                "entry_point": "POST /orders",
                "surface": "verify-order-desk",
                "target": "order-service",
            },
            "stop": {
                "budget": "30 minutes or 40 probes",
                "floor": "5 probes per entry point",
                "met": False,
            },
            "probes": [
                {
                    "id": probe_id,
                    "category": category,
                    "state": "not_run",
                    "observed": None,
                    "evidence_ids": [],
                    "promotion": {"state": "not_assessed"},
                }
                for probe_id, category in {
                    "malformed-request": "malformed_input",
                    "request-replay": "repeat_and_replay",
                    "provider-error": "dependency_failure",
                    "provider-delay": "dependency_slowness",
                    "shared-request-id": "concurrent_actors",
                }.items()
            ],
            "authority": {
                "mode": "planning_only",
                "mutations_made": False,
                "next_action": "Supply verify-order-desk.",
            },
        }
        workspace = OracleWorkspace(record)
        self.addCleanup(workspace.close)
        workspace.add_event(
            {
                "type": "command",
                "status": "completed",
                "exit_code": 0,
                "input_summary": "sed -n '1,120p' inputs/order-service-note.md",
            }
        )
        workspace.add_event(
            {
                "type": "command",
                "status": "completed",
                "exit_code": 0,
                "input_summary": "rg -- 'checkout_client -> POST' inputs/order-service-note.md",
            }
        )
        workspace.finish()
        self.assertEqual(
            evaluate("neg-plan-order-service-unavailable", workspace.path)[0], "PASS"
        )


if __name__ == "__main__":
    unittest.main()
