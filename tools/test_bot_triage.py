from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "evals/bot-triage/compare.py"


class BotTriageComparison(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "project"
        self.workspace.mkdir()
        self.cases = self.root / "cases.json"
        self.answers = self.root / "answers.json"
        self.cases.write_text(json.dumps([{
            "id": "sample", "source": {"pr": 357, "head": "a" * 40},
            "input": {"claim": "A reported defect", "evidence": [
                {"id": "code", "text": "A source excerpt"}], "intent": "Keep behavior"},
        }]))
        self.answers.write_text(json.dumps({"sample": {
            "disposition": "fix", "basis": "HIDDEN_REFERENCE_ANSWER"}}))
        self.executable = self.root / "configured-cli"
        self.executable.write_text("#!" + sys.executable + "\n" + '''
import json, os, pathlib, sys, time
args = sys.argv[1:]
if "mcp" in args and "list" in args:
    print(json.dumps([{"name": "configured.server", "enabled": True, "transport": {"type": "stdio"}}]))
    sys.exit(0)
prompt = sys.stdin.read()
pathlib.Path(os.environ["CAPTURE"]).write_text(json.dumps({
    "args": args, "prompt": prompt, "cwd": os.getcwd(),
    "home": os.environ["HOME"], "codex_home": os.environ.get("CODEX_HOME"),
    "gateway": os.environ.get("OPENAI_BASE_URL"),
}))
mode = os.environ.get("FAKE_MODE", "fix")
if mode in ("array", "null"):
    print("[]" if mode == "array" else "null")
    sys.exit(0)
if mode == "bad-item":
    print(json.dumps({"type": "item.completed", "item": "bad"}))
    sys.exit(0)
if mode == "timeout":
    time.sleep(30)
if mode == "failed":
    print("failed invocation", file=sys.stderr)
    sys.exit(3)
answer = {"disposition": mode, "reason": "Supported by code", "evidence": ["code"], "missing": []}
if mode.startswith("nested-"):
    answer["disposition"] = "fix"
if mode in ("surrogate", "unicode", "line-separators", "deep-json", "nonfinite-usage"):
    answer["disposition"] = "fix"
    if mode == "unicode":
        answer["reason"] = "Supported " + chr(0x2603) + chr(0x1f600)
    elif mode == "line-separators":
        answer["reason"] = "Supported " + chr(0x2028) + chr(0x2029) + chr(0x85)
    elif mode == "surrogate" and json.loads(prompt.split("Supplied evidence:")[-1])["claim"] == "A reported defect":
        answer["reason"] = chr(0xd800)
if mode in ("warning", "rejected-tool"):
    answer["disposition"] = "fix"
    if mode == "warning":
        print(json.dumps({"type": "item.completed", "item": {"type": "error", "message": "Model metadata not found. Defaulting to fallback metadata"}}))
    else:
        print("codex_core::tools::router: error=request_user_input is unavailable", file=sys.stderr)
if mode == "deep-json" and json.loads(prompt.split("Supplied evidence:")[-1])["claim"] == "A reported defect":
    payload = "[" * 10000 + "0"
elif mode == "malformed":
    payload = "not JSON"
elif mode == "missing":
    payload = json.dumps({"disposition": "fix"})
elif mode == "invented-evidence":
    answer["disposition"] = "fix"
    answer["evidence"] = ["not-supplied"]
    payload = json.dumps(answer)
else:
    payload = json.dumps(answer, ensure_ascii=mode != "line-separators")
if "--tools" in args:
    if mode.startswith("nested-") and json.loads(prompt.split("Supplied evidence:")[-1])["claim"] == "A reported defect":
        depth = int(mode.split("-")[1])
        print('{"type":"result","is_error":false,"result":' + json.dumps(payload) + ',"usage":{"depth":' + "[" * depth + "0" + "]" * depth + '}}')
    else:
        print(json.dumps({"type": "result", "is_error": False, "result": payload}))
else:
    if mode == "tool-call":
        print(json.dumps({"type": "item.completed", "item": {"type": "command_execution", "command": "gh pr close 1"}}))
    print(json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": payload}}, ensure_ascii=mode != "line-separators"))
    print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": float("nan") if mode == "nonfinite-usage" else 10, "output_tokens": 4}}))
''')
        self.executable.chmod(0o700)
        self.capture = self.root / "capture.json"
        self.output = self.root / "run"

    def run_case(self, mode="fix", cli="codex", extra=()):
        env = dict(os.environ, CAPTURE=str(self.capture), FAKE_MODE=mode,
                   OPENAI_BASE_URL="https://gateway.invalid/v1", CODEX_HOME="/configured/home")
        return subprocess.run([
            sys.executable, str(RUNNER), "--cli", cli, "--executable", str(self.executable),
            "--cases", str(self.cases), "--answers", str(self.answers),
            "--workspace", str(self.workspace), "--output", str(self.output), *extra,
        ], env=env, text=True, capture_output=True, timeout=10)

    def report(self):
        return json.loads((self.output / "report.json").read_text())

    def test_preserves_configured_cli_and_hides_reference_answer(self):
        result = self.run_case(extra=("--profile", "office"))
        self.assertEqual(result.returncode, 0, result.stderr)
        capture = json.loads(self.capture.read_text())
        self.assertEqual(capture["home"], os.environ["HOME"])
        self.assertEqual(capture["codex_home"], "/configured/home")
        self.assertEqual(capture["gateway"], "https://gateway.invalid/v1")
        self.assertEqual(Path(capture["cwd"]).resolve(), self.workspace.resolve())
        self.assertIn("office", capture["args"])
        self.assertNotIn("--ignore-user-config", capture["args"])
        self.assertNotIn("--model", capture["args"])
        self.assertNotIn("HIDDEN_REFERENCE_ANSWER", capture["prompt"])
        self.assertNotIn(str(self.answers), capture["prompt"])
        self.assertEqual(self.report()["results"][0]["status"], "match")

    def test_codex_disables_configured_mcp_and_action_tools(self):
        result = self.run_case()
        self.assertEqual(result.returncode, 0, result.stderr)
        args = json.loads(self.capture.read_text())["args"]
        settings = next(value for value in args if value.startswith("mcp_servers="))
        servers = tomllib.loads(settings)["mcp_servers"]
        self.assertFalse(servers["configured.server"]["enabled"])
        self.assertEqual(servers["configured.server"]["command"], "/usr/bin/false")
        self.assertIn("features.shell_tool=false", args)
        self.assertIn("features.hooks=false", args)
        self.assertIn("features.plugins=false", args)
        self.assertIn("notify=[]", args)
        self.assertIn('developer_instructions=""', args)
        self.assertIn("read-only", args)
        self.assertIn("AGENTS.md", self.report()["instruction_context"])

    def test_claude_keeps_subscription_and_gateway_with_tools_disabled(self):
        result = self.run_case(cli="claude")
        self.assertEqual(result.returncode, 0, result.stderr)
        args = json.loads(self.capture.read_text())["args"]
        self.assertEqual(args[args.index("--tools") + 1], "")
        self.assertIn("--strict-mcp-config", args)
        self.assertIn("--safe-mode", args)
        self.assertNotIn("--bare", args)
        self.assertNotIn("--restricted", args)
        self.assertIn('"disableAllHooks": true', " ".join(args))

    def test_disagreement_is_recorded_without_becoming_an_action(self):
        result = self.run_case("dismiss")
        self.assertEqual(result.returncode, 1, result.stderr)
        row = self.report()["results"][0]
        self.assertEqual(row["status"], "mismatch")
        self.assertEqual(row["proposal"]["disposition"], "dismiss")
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_ask_is_an_answer_not_a_transport_failure(self):
        result = self.run_case("ask")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(self.report()["results"][0]["status"], "mismatch")

    def test_failures_never_turn_into_a_disposition(self):
        for mode in ("malformed", "missing", "invented-evidence", "failed", "tool-call",
                     "array", "null", "bad-item", "rejected-tool"):
            with self.subTest(mode=mode):
                self.output = self.root / mode
                result = self.run_case(mode)
                self.assertEqual(result.returncode, 1, result.stderr)
                row = self.report()["results"][0]
                self.assertEqual(row["status"], "unavailable")
                self.assertNotIn("proposal", row)

    def test_gateway_metadata_warning_preserves_completed_comparison(self):
        result = self.run_case("warning")
        self.assertEqual(result.returncode, 0, result.stderr)
        row = self.report()["results"][0]
        self.assertEqual(row["status"], "match")
        self.assertEqual(len(row["diagnostics"]), 1)

    def test_claude_nonobject_output_is_unavailable(self):
        result = self.run_case("array", cli="claude")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(self.report()["results"][0]["status"], "unavailable")

    def test_invalid_answer_does_not_lose_later_comparison(self):
        cases = json.loads(self.cases.read_text())
        later = json.loads(json.dumps(cases[0]))
        later["id"] = "later"
        later["input"]["claim"] = "A later defect"
        self.cases.write_text(json.dumps(cases + [later]))
        answers = json.loads(self.answers.read_text())
        answers["later"] = answers["sample"]
        self.answers.write_text(json.dumps(answers))
        for mode in ("surrogate", "deep-json"):
            with self.subTest(mode=mode):
                self.output = self.root / mode
                result = self.run_case(mode, cli="claude")
                self.assertEqual(result.returncode, 1, result.stderr)
                rows = self.report()["results"]
                self.assertEqual([row["status"] for row in rows], ["unavailable", "match"])
                self.assertNotIn("proposal", rows[0])

    def test_nested_cli_metadata_cannot_erase_later_comparison(self):
        cases = json.loads(self.cases.read_text())
        later = json.loads(json.dumps(cases[0]))
        later["id"] = "later"
        later["input"]["claim"] = "A later defect"
        self.cases.write_text(json.dumps(cases + [later]))
        answers = json.loads(self.answers.read_text())
        answers["later"] = answers["sample"]
        self.answers.write_text(json.dumps(answers))
        for depth in (990, 997, 1000, 10000):
            with self.subTest(depth=depth):
                self.output = self.root / str(depth)
                result = self.run_case("nested-" + str(depth), cli="claude")
                self.assertIn(result.returncode, (0, 1), result.stderr)
                self.assertTrue((self.output / "report.json").exists(), result.stderr)
                rows = self.report()["results"]
                self.assertEqual(len(rows), 2)
                self.assertIn(rows[0]["status"], ("match", "unavailable"))
                self.assertEqual(rows[1]["status"], "match")

    def test_literal_unicode_line_separators_preserve_jsonl_framing(self):
        result = self.run_case("line-separators")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.report()["results"][0]["proposal"]["reason"],
                         "Supported " + chr(0x2028) + chr(0x2029) + chr(0x85))

    def test_nonfinite_metadata_is_rejected_before_invocation(self):
        original = self.cases.read_text()
        for literal in ("NaN", "Infinity", "-Infinity", "1e999"):
            with self.subTest(literal=literal):
                self.cases.write_text(original.replace('"pr": 357', '"pr": ' + literal))
                self.output = self.root / literal
                result = self.run_case()
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertFalse(self.capture.exists())

    def test_nonfinite_cli_metadata_is_unavailable(self):
        result = self.run_case("nonfinite-usage")
        self.assertEqual(result.returncode, 1, result.stderr)
        row = self.report()["results"][0]
        self.assertEqual(row["status"], "unavailable")
        self.assertIn("non-finite JSON number", row["error"])

    def test_report_preserves_metadata_without_utf8_encoding_failure(self):
        cases = json.loads(self.cases.read_text())
        cases[0]["source"]["note"] = chr(0xd800)
        self.cases.write_text(json.dumps(cases))
        answers = json.loads(self.answers.read_text())
        answers["sample"]["basis"] = chr(0xdc00)
        self.answers.write_text(json.dumps(answers))
        result = self.run_case()
        self.assertEqual(result.returncode, 0, result.stderr)
        row = self.report()["results"][0]
        self.assertEqual(row["source"]["note"], chr(0xd800))
        self.assertEqual(row["reference"]["basis"], chr(0xdc00))

    def test_valid_unicode_answer_is_preserved(self):
        result = self.run_case("unicode")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.report()["results"][0]["proposal"]["reason"],
                         "Supported " + chr(0x2603) + chr(0x1f600))

    def test_invalid_claude_profile_is_rejected_before_invocation(self):
        result = self.run_case(cli="claude", extra=("--profile", "office"))
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.capture.exists())

    def test_file_workspace_is_rejected_before_invocation(self):
        result = self.run_case(extra=("--workspace", str(self.cases)))
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.capture.exists())

    def test_missing_claim_is_rejected_before_invocation(self):
        cases = json.loads(self.cases.read_text())
        del cases[0]["input"]["claim"]
        self.cases.write_text(json.dumps(cases))
        result = self.run_case()
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.capture.exists())

    def test_duplicate_fixture_fields_do_not_silently_replace_evidence(self):
        self.cases.write_text(self.cases.read_text().replace('"claim":', '"claim": "shadow", "claim":'))
        result = self.run_case()
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.capture.exists())

    def test_timeout_returns_an_unavailable_comparison(self):
        result = self.run_case("timeout", extra=("--timeout", "0.1"))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(self.report()["results"][0]["status"], "unavailable")

    def test_timeout_beyond_platform_wait_limit_is_unavailable(self):
        result = self.run_case("timeout", cli="claude", extra=("--timeout", "1e300"))
        self.assertEqual(result.returncode, 1, result.stderr)
        row = self.report()["results"][0]
        self.assertEqual(row["status"], "unavailable")
        self.assertIn("OverflowError", row["error"])

    def test_unknown_case_does_not_silently_run_zero_cases(self):
        result = self.run_case(extra=("--case", "absent"))
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.capture.exists())

    def test_existing_output_directory_is_not_overwritten(self):
        self.output.mkdir()
        marker = self.output / "keep"
        marker.write_text("existing run")
        result = self.run_case()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(marker.read_text(), "existing run")
        self.assertFalse(self.capture.exists())


if __name__ == "__main__":
    unittest.main()
