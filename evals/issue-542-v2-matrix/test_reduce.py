import contextlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import reduce

RESOLVED = [{"role": "how explorer", "model": "gpt-6.1-sol", "effort": "low"}]


def child(model, effort, name="explore"):
    return {"id": name, "agent_path": f"/root/{name}", "agent_role": "default", "turn_contexts": [(model, effort)]}


def spawn(**arguments):
    return {"tool": "spawn_agent", "arguments": arguments}


class CodeModeSpawns(unittest.TestCase):
    def test_a_call_site_keeps_its_keys_and_skips_the_brief(self):
        source = 'const message = `{agent_type:"x", model:"nope"}`;\nawait tools.multi_agent_v1__spawn_agent({agent_type:"default",fork_context:false,message});'
        self.assertEqual(reduce.code_mode_spawns(source), [("multi_agent_v1__spawn_agent", {"agent_type": "default", "fork_context": False, "message": "<code-mode brief, not recorded>"})])

    def test_a_mapped_call_site_without_fork_or_model_reads_as_bare(self):
        source = "briefs.map(message => tools.multi_agent_v1__spawn_agent({agent_type:\"explorer\",message}))"
        self.assertEqual(reduce.code_mode_spawns(source)[0][1].keys(), {"agent_type", "message"})


V1_RESOLVED = [{"role": "how explorer", "model": "gpt-6.1-sol", "effort": "low"},
               {"role": "how explainer", "model": "gpt-6.1-sol", "effort": "medium"}]
V1_STYLES = {"code-mode": {"style": "code-mode"}, "function": {}}


def v1_site(style, agent_type, effort, **extra):
    arguments = {"fork_context": False, "model": "gpt-6.1-sol", "reasoning_effort": effort, **extra}
    if agent_type:
        arguments["agent_type"] = agent_type
    return {"tool": "spawn_agent", **V1_STYLES[style], "arguments": arguments}


def v1_child(role, effort, n=1):
    return {"id": f"{role}-{n}", "agent_path": None, "agent_role": role, "turn_contexts": [("gpt-6.1-sol", effort)]}


class V1Children(unittest.TestCase):
    def check(self, style, sites, children):
        return reduce.verdict({"calls": [v1_site(style, *site) for site in sites]}, children, V1_RESOLVED)[1]

    def test_children_that_ran_their_own_sites_ask_pass(self):
        for style in V1_STYLES:
            with self.subTest(style=style):
                sites = [("explorer", "low"), ("default", "medium")]
                children = [v1_child("explorer", "low", 1), v1_child("explorer", "low", 2), v1_child("default", "medium")]
                self.assertEqual(self.check(style, sites, children), [])

    def test_a_site_with_no_agent_type_asks_for_the_default_role(self):
        for style in V1_STYLES:
            with self.subTest(style=style):
                self.assertEqual(self.check(style, [(None, "medium")], [v1_child("default", "medium")]), [])

    def test_a_child_on_another_roles_resolved_arm_fails(self):
        for style in V1_STYLES:
            with self.subTest(style=style):
                problems = self.check(style, [("explorer", "low"), ("default", "medium")],
                                      [v1_child("explorer", "medium"), v1_child("default", "medium")])
                self.assertEqual(len(problems), 1)
                self.assertIn("child explorer: ran", problems[0])

    def test_a_child_whose_agent_type_no_site_used_fails(self):
        for style in V1_STYLES:
            with self.subTest(style=style):
                problems = self.check(style, [("explorer", "low")], [v1_child("explorer", "low"), v1_child("default", "medium")])
                self.assertEqual(len(problems), 1)
                self.assertIn("child default:", problems[0])

    def test_a_site_that_asks_for_no_resolved_arm_fails_even_when_its_child_obeys(self):
        for style in V1_STYLES:
            with self.subTest(style=style):
                problems = self.check(style, [("explorer", "high")], [v1_child("explorer", "high")])
                self.assertEqual(len(problems), 1)
                self.assertIn("is no resolved role arm", problems[0])

    def test_a_site_that_started_no_child_fails(self):
        for style in V1_STYLES:
            with self.subTest(style=style):
                problems = self.check(style, [("explorer", "low"), ("default", "medium")], [v1_child("default", "medium")])
                self.assertEqual(problems, ["explorer: no child rollout"])


class RunDirectory(unittest.TestCase):
    def test_child_effort_is_checked_end_to_end(self):
        for effort, expected in [("medium", "PASS"), ("high", "FAIL")]:
            with self.subTest(effort=effort), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                config = root / "project/.agents/pstack-models.md"
                config.parent.mkdir(parents=True)
                shutil.copyfile(reduce.HERE / "models.md", config)
                (root / "run.json").write_text(json.dumps({
                    "row": "how", "model": "gpt-6.1-sol", "effort": "high",
                    "v2_flag": True, "turns": ["Explain the order total"], "skills_at": "synthetic",
                }))
                sessions = root / "codex-home/sessions"
                sessions.mkdir(parents=True)
                arguments = dict(task_name="explain", agent_type="default", fork_turns="none",
                                 model="gpt-6.1-sol", reasoning_effort="medium", message="Explain totals")
                for name, parent, actual_effort in [("lead", None, "high"), ("explain", "lead", effort)]:
                    agent_path = f"/root/{name}" if parent else "/root"
                    records = [
                        {"type": "session_meta", "payload": {
                            "id": name, "parent_thread_id": parent, "agent_path": agent_path, "cli_version": "0.167.0",
                            "source": {"subagent": {"thread_spawn": {
                                "agent_path": agent_path, "agent_role": "default",
                            }}},
                        }},
                        {"type": "turn_context", "payload": {"model": "gpt-6.1-sol", "effort": actual_effort}},
                    ]
                    if parent is None:
                        records.append({"type": "response_item", "payload": {
                            "type": "function_call", "name": "spawn_agent", "call_id": "spawn-1",
                            "arguments": json.dumps(arguments),
                        }})
                    (sessions / f"rollout-{name}.jsonl").write_text("\n".join(map(json.dumps, records)) + "\n")
                out = root / "extract.json"
                with patch("sys.argv", ["reduce.py", str(root), "--out", str(out)]), contextlib.redirect_stdout(io.StringIO()):
                    reduce.main()
                extract = json.loads(out.read_text())
                self.assertEqual(extract["verdict"], expected)
                self.assertEqual(extract["cli_versions"], ["0.167.0"])
                self.assertEqual(len(extract["spawns"]), 1)
                recorded = extract["spawns"][0]
                self.assertEqual(recorded["tool_name"], "spawn_agent")
                self.assertEqual(recorded["fork_field"], "fork_turns")
                self.assertEqual(recorded["fork_value"], "none")
                self.assertEqual(recorded["child_contexts"], [["gpt-6.1-sol", effort]])
                if expected == "PASS":
                    self.assertEqual(extract["problems"], [])
                else:
                    self.assertEqual(len(extract["problems"]), 1)
                    self.assertIn("explain: child ran", extract["problems"][0])


class Verdict(unittest.TestCase):
    def test_a_child_that_ran_what_was_asked_passes(self):
        lead = {"calls": [spawn(task_name="explore", fork_turns="none", model="gpt-6.1-sol", reasoning_effort="low")]}
        self.assertEqual(reduce.verdict(lead, [child("gpt-6.1-sol", "low")], RESOLVED)[1], [])

    def test_a_child_that_ignored_the_asked_effort_fails(self):
        lead = {"calls": [spawn(task_name="explore", fork_turns="none", model="gpt-6.1-sol", reasoning_effort="low")]}
        problems = reduce.verdict(lead, [child("gpt-6.1-sol", "high")], RESOLVED)[1]
        self.assertEqual(len(problems), 1)
        self.assertIn("child ran", problems[0])

    def test_a_model_with_a_full_history_fork_fails(self):
        lead = {"calls": [spawn(task_name="explore", fork_turns="all", model="gpt-6.1-sol", reasoning_effort="low")]}
        self.assertIn("fork_turns 'all'", reduce.verdict(lead, [child("gpt-6.1-sol", "low")], RESOLVED)[1][0])

    def test_a_missing_fork_field_fails(self):
        lead = {"calls": [spawn(task_name="explore", model="gpt-6.1-sol", reasoning_effort="low")]}
        self.assertEqual(reduce.verdict(lead, [child("gpt-6.1-sol", "low")], RESOLVED)[1], ["explore: no fork field set"])

    def test_a_v1_child_on_the_parent_model_is_no_resolved_arm(self):
        lead = {"calls": [{"tool": "spawn_agent", "style": "code-mode", "arguments": {"agent_type": "default", "fork_context": False}}]}
        problems = reduce.verdict(lead, [{**child("gpt-5.6-luna", "high"), "agent_path": None}], RESOLVED)[1]
        self.assertEqual(len(problems), 2)

    def test_a_v2_spawn_without_model_or_effort_fails(self):
        lead = {"turn_contexts": [("gpt-5.6-luna", "high")],
                "calls": [spawn(task_name="explore", fork_turns="none")]}
        problems = reduce.verdict(lead, [child("gpt-5.6-luna", "high")], RESOLVED)[1]
        self.assertEqual(problems, ["explore: spawn call passed no model or effort"])


if __name__ == "__main__":
    unittest.main()
