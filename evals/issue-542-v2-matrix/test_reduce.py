import unittest

import reduce

RESOLVED = [{"role": "how explorer", "model": "gpt-6.1-sol", "effort": "low"}]


def child(model, effort, name="explore"):
    return {"id": name, "agent_path": f"/root/{name}", "agent_role": "default", "turn_contexts": [(model, effort)]}


def spawn(**arguments):
    return {"tool": "spawn_agent", "arguments": arguments}


class CodeModeSpawns(unittest.TestCase):
    def test_a_call_site_keeps_its_keys_and_skips_the_brief(self):
        source = 'const message = `{agent_type:"x", model:"nope"}`;\nawait tools.multi_agent_v1__spawn_agent({agent_type:"default",fork_context:false,message});'
        self.assertEqual(reduce.code_mode_spawns(source), [{"agent_type": "default", "fork_context": False, "message": "<code-mode brief, not recorded>"}])

    def test_a_mapped_call_site_without_fork_or_model_reads_as_bare(self):
        source = "briefs.map(message => tools.multi_agent_v1__spawn_agent({agent_type:\"explorer\",message}))"
        self.assertEqual(reduce.code_mode_spawns(source)[0].keys(), {"agent_type", "message"})


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


if __name__ == "__main__":
    unittest.main()
