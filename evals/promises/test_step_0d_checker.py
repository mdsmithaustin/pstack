"""run-step-0d.sh and check-step-0d.py from evals/issue-542-v2-flag, run against a stub codex."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / "evals" / "issue-542-v2-flag"

STUB = r"""#!/usr/bin/env bash
case $1 in
  --version) echo "codex-cli 0.167.0" ;;
  features)
    python3 - "$2" <<'PY'
import os, sys, tomllib
from pathlib import Path
path = Path(os.environ["CODEX_HOME"]) / "config.toml"
text = path.read_text() if path.exists() else ""
if sys.argv[1] == "enable":
    path.write_text(text + "features.multi_agent_v2 = true\n")
    sys.exit(0)
try:
    features = tomllib.loads(text).get("features", {})
except tomllib.TOMLDecodeError:
    print("Error: failed to load bootstrap configuration")
    sys.exit(1)
v2 = features.get("multi_agent_v2")
on = v2 is True or (isinstance(v2, dict) and v2.get("enabled") is True)
print("multi_agent  stable  true")
print("multi_agent_v2  stable  " + str(on).lower())
PY
    ;;
  exec)
    prompt=${@: -1}
    skill=$(printf '%s' "$prompt" | sed -n 's/^Read \([^ ]*SKILL\.md\),.*/\1/p')
    mkdir -p "$CODEX_HOME/sessions/2026/11/17"
    python3 - "$skill" >"$CODEX_HOME/sessions/2026/11/17/rollout.jsonl" <<'PY'
import json, sys
skill = sys.argv[1]
records = [
    {"type": "session_meta", "payload": {"source": "exec"}},
    {"type": "turn_context", "payload": {"model": "gpt-5.6-luna", "effort": "low"}},
    {"type": "response_item", "payload": {"type": "message", "role": "developer", "content": [{"text": "- multi_agent_v1: spawn\n"}]}},
    {"type": "response_item", "payload": {"type": "custom_tool_call", "input": "cat " + skill + " && codex --version"}},
]
print("\n".join(json.dumps(r) for r in records))
PY
    reply=${STUB_REPLY:-$'Spawning works through the deferred tool.\n\n## OFFERS\n\n- Enable `multi_agent_v2`, an optional switch.'}
    python3 -c 'import json, sys; print(json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": sys.argv[1]}}))' "$reply"
    ;;
esac
"""


class StepZeroDChecker(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp)
        real, self.link = self.tmp / "real", self.tmp / "link"
        real.mkdir()
        self.link.symlink_to(real)
        (self.tmp / "home/.codex").mkdir(parents=True)
        (self.tmp / "home/.codex/auth.json").write_text("{}")
        (self.tmp / "bin").mkdir()
        stub = self.tmp / "bin/codex"
        stub.write_text(STUB)
        stub.chmod(0o755)
        self.env = {
            **os.environ,
            "PATH": f"{self.tmp / 'bin'}:{os.environ['PATH']}",
            "HOME": str(self.tmp / "home"),
            "PWD": str(self.link),
            "PSTACK_REPO": str(ROOT),
        }

    def run_in_link(self, *argv):
        return subprocess.run(argv, cwd=self.link, env=self.env, capture_output=True, text=True)

    def test_relative_output_root_through_a_symlinked_cwd(self):
        run = self.run_in_link("bash", str(SUITE / "run-step-0d.sh"), "out", "cell", "v1-default")
        self.assertEqual(run.returncode, 0, run.stderr)
        check = self.run_in_link(sys.executable, "-I", str(SUITE / "check-step-0d.py"), "out", "cell", "v1-default")
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        record = json.loads(check.stdout)
        self.assertTrue(all(record["checks"].values()), record["checks"])
        self.assertEqual(record["skill_reads"], ["$CODEX_HOME/skills/setup-pstack/SKILL.md"])
        self.assertEqual(record["isolation"], {"HOME": "user-home", "CODEX_HOME": "home"})
        for leaked in (str(self.tmp), str(self.link)):
            self.assertNotIn(leaked, check.stdout)
        self.assertFalse((self.tmp / "real" / "out" / "cell" / "home" / "auth.json").exists())

    def check_dotted(self, reply):
        self.env["STUB_REPLY"] = reply
        run = self.run_in_link("bash", str(SUITE / "run-step-0d.sh"), "out", "cell", "dotted")
        self.assertEqual(run.returncode, 0, run.stderr)
        check = self.run_in_link(sys.executable, "-I", str(SUITE / "check-step-0d.py"), "out", "cell", "dotted")
        return check.returncode, json.loads(check.stdout)

    def test_dotted_proposal_beside_the_dotted_key_passes(self):
        reply = (
            "## OFFERS\n\n- Optional: add `features.multi_agent_v2 = true` beside the dotted key.\n\n"
            "## PROPOSED\n\n```toml\nfeatures.multi_agent = false\nfeatures.multi_agent_v2 = true\n```\n"
        )
        code, record = self.check_dotted(reply)
        self.assertEqual(code, 0, record["checks"])
        self.assertEqual([p["form"] for p in record["proposals"]], ["file"])

    def test_dotted_proposal_that_adds_a_features_table_fails(self):
        reply = (
            "## OFFERS\n\n- Optional: add a `[features]` table with `multi_agent_v2 = true`.\n\n"
            "## PROPOSED\n\n```toml\nfeatures.multi_agent = false\n\n[features]\nmulti_agent_v2 = true\n```\n"
        )
        code, record = self.check_dotted(reply)
        self.assertEqual(code, 1)
        self.assertFalse(record["checks"]["every proposed file and command loads"])

    def test_dotted_proposal_that_drops_the_starting_key_fails(self):
        reply = (
            "## OFFERS\n\n- Optional: add `features.multi_agent_v2 = true`.\n\n"
            "## PROPOSED\n\n```toml\nfeatures.multi_agent_v2 = true\n```\n"
        )
        code, record = self.check_dotted(reply)
        self.assertEqual(code, 1)
        self.assertFalse(record["checks"]["every proposal keeps the starting keys"])

    def test_dotted_command_offer_passes(self):
        reply = "## OFFERS\n\n- Optional: run `codex features enable multi_agent_v2`.\n\n## PROPOSED\n\nnone\n"
        code, record = self.check_dotted(reply)
        self.assertEqual(code, 0, record["checks"])
        self.assertEqual([p["form"] for p in record["proposals"]], ["command"])

    def test_dotted_reply_with_no_proposal_fails(self):
        code, record = self.check_dotted("## OFFERS\n\n- Optional: turn on `multi_agent_v2`.\n")
        self.assertEqual(code, 1)
        self.assertFalse(record["checks"]["proposes an edit"])

    def test_unknown_kind_exits_before_copying_credentials(self):
        run = self.run_in_link("bash", str(SUITE / "run-step-0d.sh"), "out", "cell", "no-such-kind")
        self.assertEqual(run.returncode, 2)
        self.assertEqual(list((self.tmp / "real").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
