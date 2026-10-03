import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import live

CODEX_CHAT = """I'm using `poteto-mode`. I'll identify the command first.

1. In progress. **You own the design. Plan, review, verify.** Delegate implementation. Stay in the lead.
2. Pending. `how` over the affected subsystem.
3. ⏭️ `architect`. skipped: one module
4. [x] Verify on the matching surface."""


class ChatWorklist(unittest.TestCase):
    def test_capitalized_states_skips_and_checkboxes_parse(self):
        items = live.chat_worklist(CODEX_CHAT)
        self.assertEqual([i["state"] for i in items], ["in progress", "pending", "skipped: one module", "completed"])
        self.assertEqual(items[1]["text"], "Pending. `how` over the affected subsystem.")

    def test_a_list_with_no_state_is_not_a_worklist(self):
        self.assertIsNone(live.chat_worklist("1. read the code\n2. write the fix"))

    def test_a_reply_summary_with_one_state_word_is_not_a_worklist(self):
        reply = "Summary\n- the flag now emits rows\n- default text stays byte-identical\n- verification done for both forms"
        self.assertIsNone(live.chat_worklist(reply))

    def test_bare_checkbox_lines_parse(self):
        self.assertEqual([i["state"] for i in live.chat_worklist("[x] one\n[ ] two\n- [~] three")],
                         ["completed", "pending", "in progress"])


class FixtureCommits(unittest.TestCase):
    def test_commits_ignore_the_contributors_signing_and_hook_settings(self):
        with tempfile.TemporaryDirectory(prefix="pstack-live-test-") as tmp:
            tmp = Path(tmp)
            hooks = tmp / "hooks"
            hooks.mkdir()
            (hooks / "pre-commit").write_text("#!/bin/sh\nexit 1\n")
            (hooks / "pre-commit").chmod(0o755)
            config = tmp / "gitconfig"
            config.write_text(f"[commit]\n\tgpgsign = true\n[gpg]\n\tprogram = /usr/bin/false\n[core]\n\thooksPath = {hooks}\n"
                              "[user]\n\tname = Someone Else\n\temail = someone@example.org\n")
            case = {"fixture": "relay", "history": "relay-retry-limit"}
            dest = tmp / "project"
            with mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(config), "GIT_CONFIG_NOSYSTEM": "1"}):
                live.make_project(case, dest)
            log = subprocess.run(["git", "-C", str(dest), "log", "--format=%an <%ae>"], capture_output=True, text=True,
                                 env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull}).stdout.split("\n")
            self.assertEqual({line for line in log if line}, {"dev <dev@example.com>"})
            self.assertGreater(len([line for line in log if line]), 1)


class GradeRun(unittest.TestCase):
    def test_a_run_with_host_skill_hits_writes_inconclusive_for_every_promise(self):
        with tempfile.TemporaryDirectory(prefix="pstack-live-test-") as tmp:
            root = Path(tmp)
            case = live.load_case("feature-run")
            trace = {"harness": "claude-code", "model": "m", "exit_code": 0, "events": [], "worklist": [], "spawns": [],
                     "files_read": [], "final_reply": "done", "x_host_skill_hits": ["/Users/someone/.claude/skills"]}
            (root / "run.json").write_text(json.dumps({"harness": "claude-code", "case": case["id"], "skills_at": "x", "project": str(root / "p")}))
            (root / "trace.json").write_text(json.dumps(trace))
            graded = live.grade(root)
            self.assertEqual({r["verdict"] for r in graded["promises"].values()}, {"INCONCLUSIVE"})
            self.assertEqual(set(graded["promises"]), set(case["promises"]))
            self.assertEqual(json.loads((root / "verdict.json").read_text()), graded)


if __name__ == "__main__":
    unittest.main()
