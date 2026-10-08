"""Judged document cases: a rule whose arms place a premortem skill, with one
positive and one near-miss pasted-project case, labeled samples, and the
offline stand-ins for the agent and the judge."""
import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_workspace import ROOT, harness_available, screen

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "oracles"))
import review  # noqa: E402
import review_cases  # noqa: E402

RULE = "premortem-place"
FILE = "ops/premortem.md"
SKILL = ("---\nname: premortem\ndescription: Use before rolling out a change to shared infrastructure.\n---\n# Premortem\n\n"
         "Name the one upstream cause under the listed risks first. Test only on a scratch clone, with a stop rule fixed before the test.\n")
SKILL_PATCH = "--- /dev/null\n+++ b/premortem/SKILL.md\n@@ -0,0 +1,%d @@\n%s" % (SKILL.count("\n"), "".join(f"+{line}\n" for line in SKILL.splitlines()))
ORACLE = '''import re

from shared import document_text

FILE = "ops/premortem.md"


def names(pattern, failure):
    def check(answer, project):
        return [] if re.search(pattern, document_text(answer, {"file": FILE}), re.IGNORECASE) else [failure]
    return check


CHECKS = {
    "plan-hook-adoption": names(r"GIT_DIR|hook environment", "the document never names the hook environment or GIT_DIR"),
    "plan-changelog-lint": names(r"\\btrial\\b|team repository", "the document proposes no trial"),
}
'''


def message(document, opening="I read the plan and the register.", closing="Nothing else changed."):
    return f'{opening}\n\n<file path="{FILE}">\n{document}</file>\n\n{closing}\n'


CASES = {
    "plan-hook-adoption": {
        "kind": "positive",
        "prompt": ("We are about to roll out the pre-push hook described in ops/proposal.md. Do a premortem of the plan and write it to ops/premortem.md.\n\n"
                   "Here is the project:\n\n{project}\n\n"
                   'Reply with ops/premortem.md, complete, inside <file path="ops/premortem.md"> and </file> tags.\n'),
        "project": {
            "ops/proposal.md": "# Pre-push hook rollout\n\nInstall hooks/pre-push in every clone. It runs the test suite before each push.\n",
            "ops/risk-register.md": "# Risks\n\n1. Slow pushes.\n2. Fixture repositories left behind.\n3. Hook skipped with --no-verify.\n4. Test git calls change the wrong repository.\n",
            "tests/test_fixtures.py": "import subprocess\nimport tempfile\n\n\ndef test_init():\n    with tempfile.TemporaryDirectory() as d:\n        subprocess.run(['git', 'init', d], check=True)\n",
            "hooks/pre-push": "#!/bin/sh\npytest -q\n",
        },
        "rubric": ("The plan has one hidden hazard. A git hook runs with GIT_DIR set, so the test suite's fixture git calls act on the outer repository.\n"
                   "FOUND: names that shared cause and proposes testing only on a scratch clone with a stop rule fixed first.\n"
                   "PARTIAL: names the cause without the scratch-only test, or the reverse.\n"
                   "MISSED: lists the risks as independent, or proposes trying the hook on the team repository.\n"),
        "samples": {
            "answer-found.md": ("FOUND", message("# Premortem\n\n## Shared cause\nGit runs the hook with GIT_DIR set, so the fixture git calls in tests/test_fixtures.py act on the outer repository. Risks 2 and 4 are this one cause.\n\n## Test plan\nRun the hook only in a scratch clone. Stop rule, fixed now: any fixture call that touches the clone's refs ends the test.\n")),
            "answer-partial.md": ("PARTIAL", message("# Premortem\n\nThe hook environment carries GIT_DIR into the fixture git calls. We should look into that before the rollout.\n")),
            "answer-missed.md": ("MISSED", message("# Premortem\n\nPushes will be slower. Some people will skip the hook. Install it on the team repository for a week and see what breaks.\n", "Here is the premortem.")),
        },
    },
    "plan-changelog-lint": {
        "kind": "near-miss",
        "prompt": ("We plan to add the changelog lint described in ops/lint-proposal.md to CI. Do a premortem and write it to ops/premortem.md.\n\n"
                   "{project}\n\n"
                   'Reply with ops/premortem.md inside <file path="ops/premortem.md"> and </file> tags.\n'),
        "project": {"ops/lint-proposal.md": "# Changelog lint\n\nCI fails a pull request whose CHANGELOG.md has no entry. Reverting is one workflow change.\n"},
        "rubric": ("The change is one CI step and reverts with one commit, so no live trial is warranted.\n"
                   "FALSE_ALARM: the document proposes a trial on the team repository before the lint ships.\nCLEAN: anything else.\n"),
        "samples": {
            "answer-clean.md": ("CLEAN", message("# Premortem\n\nBots that open pull requests will fail the lint. Give them an exemption label before the step lands. The step reverts in one commit.\n")),
            "answer-padded.md": ("FALSE_ALARM", message("# Premortem\n\nRun a one-week trial on the team repository with the lint enforcing, and roll back if too many pull requests fail.\n")),
        },
    },
}
DOCUMENT = re.compile(r'<document label="document-[0-9a-f]{8}">\n(.*?)\n</document>', re.DOTALL)
BLIND = re.compile(r"\b(premortem-place|current|skill|claude|codex|anthropic|openai|gpt|opus|sonnet|poteto|pstack|SKILL\.md)\b", re.IGNORECASE)


class DocumentRule(unittest.TestCase):
    """The premortem placement rule in a private rules root, with a private cache."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        rules = self.base / "rules"
        rule = rules / RULE
        (rule / "arms").mkdir(parents=True)
        (rule / "rule.json").write_text(json.dumps({"source": "premortem fixture", "arms": ["current", "skill"]}))
        (rule / "arms" / "skill.patch").write_text(SKILL_PATCH)
        (rule / "oracle.py").write_text(ORACLE)
        for case_id, case in CASES.items():
            root = rule / "cases" / case_id
            (root / "samples").mkdir(parents=True)
            (root / "case.json").write_text(json.dumps({"kind": case["kind"], "domain": "planning-docs", "timeout_s": 600,
                                                        "expected_behavior": ["Writes ops/premortem.md."], "document": {"file": FILE}}))
            (root / "prompt.md").write_text(case["prompt"])
            (root / "rubric.md").write_text(case["rubric"])
            for path, text in case["project"].items():
                (root / "project" / path).parent.mkdir(parents=True, exist_ok=True)
                (root / "project" / path).write_text(text)
            for name, (_, text) in case["samples"].items():
                (root / "samples" / name).write_text(text)
            (root / "samples" / "labels.json").write_text(json.dumps({name: label for name, (label, _) in case["samples"].items()}))
        environment = {"CANON_RULES": str(rules), "CANON_CACHE": str(self.base / "cache"),
                       "CODEX_BIN": str(ROOT / "offline" / "codex"), "CANON_JUDGE_STANDIN": str(ROOT / "offline" / "judge")}
        for patch in (mock.patch.object(screen, "RULES", rules), mock.patch.object(review_cases.screen, "RULES", rules), mock.patch.dict(os.environ, environment)):
            patch.start()
            self.addCleanup(patch.stop)
        self.rules = rules
        self.rule = screen.load_rule(RULE)
        self.cases = {case.id: case for case in self.rule.cases}
        self.out = self.base / "out"

    def build(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return screen.build(self.out, [self.rule], "poteto-mode")[RULE]


class DocumentCaseShapeTests(DocumentRule):
    def rewrite(self, case_id, **changes):
        root = self.cases[case_id].root
        spec = {**json.loads((root / "case.json").read_text()), **changes}
        (root / "case.json").write_text(json.dumps({key: value for key, value in spec.items() if value is not None}))
        return root

    def test_the_case_knows_its_frame_and_document(self):
        case = self.cases["plan-hook-adoption"]

        self.assertEqual((case.frame, case.document, case.review, case.workspace), ("document", {"file": FILE}, None, None))
        self.assertEqual(screen.judged({"kind": "positive", "document": {"file": FILE}}), True)
        self.assertEqual(screen.judged({"kind": "positive", "timeout_s": 600}), False)

    def test_a_document_must_be_a_file_or_the_message_and_never_also_a_review(self):
        for document, error in (({"file": "../escape.md"}, "unsafe file path"), ({"path": FILE}, r"document must be"), ({"message": False}, r"document must be")):
            with self.subTest(document=document):
                root = self.rewrite("plan-hook-adoption", document=document)
                with self.assertRaisesRegex(screen.ScreenError, error):
                    screen.load_case(RULE, root)
        root = self.rewrite("plan-hook-adoption", document={"file": FILE}, review={"patch": "pr.patch", "title": "t", "body_file": "b.md", "branch": "b"})
        with self.assertRaisesRegex(screen.ScreenError, "both a review and a document"):
            screen.load_case(RULE, root)

    def test_a_sample_that_delivers_no_document_is_refused_at_load(self):
        root = self.cases["plan-hook-adoption"].root
        (root / "samples" / "answer-missed.md").write_text("Done, the premortem is written to ops/premortem.md.\n")

        with self.assertRaisesRegex(screen.ScreenError, r'sample answer-missed.md delivers no document; a run\'s final message would need a <file path="ops/premortem.md"> block'):
            screen.load_case(RULE, root)
        self.assertEqual(review_cases.document_problems(RULE, root, json.loads((root / "case.json").read_text())), ["answer-missed.md delivers no document"])

    def test_a_workspace_sample_diff_that_deletes_the_document_is_refused(self):
        root = self.base / "workspace-case"
        (root / "samples").mkdir(parents=True)
        (root / "prompt.md").write_text("Write NOTES.md in the repository.\n")
        (root / "rubric.md").write_text("FOUND: names the cause.\nMISSED: anything else.\n")
        labels = {"answer-found.md": "FOUND", "answer-missed.md": "MISSED"}
        for name in labels:
            (root / "samples" / name).write_text("Done.\n")
        (root / "samples" / "labels.json").write_text(json.dumps(labels))
        writes = "diff --git a/NOTES.md b/NOTES.md\nnew file mode 100644\n--- /dev/null\n+++ b/NOTES.md\n@@ -0,0 +1 @@\n+The hook environment is the cause.\n"
        deletes = "diff --git a/NOTES.md b/NOTES.md\ndeleted file mode 100644\n--- a/NOTES.md\n+++ /dev/null\n@@ -1 +0,0 @@\n-old\n"
        spec = {"kind": "positive", "domain": "planning-docs", "expected_behavior": ["Writes NOTES.md."], "document": {"file": "NOTES.md"},
                "workspace": {"repo": "shop", "commit": "0" * 40}}
        (root / "samples" / "answer-found.diff").write_text(writes)
        (root / "samples" / "answer-missed.diff").write_text(writes)

        self.assertEqual(screen.check_labels(root, "positive", spec["document"], True), labels)
        self.assertEqual(review_cases.document_problems(RULE, root, spec), [])

        (root / "samples" / "answer-found.diff").write_text(deletes)

        with self.assertRaisesRegex(screen.ScreenError, r"sample answer-found.md has a sibling answer-found.diff that deletes NOTES.md"):
            screen.check_labels(root, "positive", spec["document"], True)
        self.assertEqual(review_cases.document_problems(RULE, root, spec), ["answer-found.md has a sibling answer-found.diff that deletes NOTES.md"])

    def test_the_authoring_check_accepts_both_cases_and_names_a_pasted_document_in_its_table(self):
        for case in self.cases.values():
            with self.subTest(case=case.id):
                self.assertEqual(review_cases.document_problems(RULE, case.root, case.spec), [])
                self.assertEqual(review_cases.precheck_problems(RULE, case.root), [])
        with contextlib.redirect_stdout(io.StringIO()) as printed:
            status = review_cases.check([f"{RULE}/plan-changelog-lint"])
        self.assertEqual(status, 0)
        self.assertEqual(printed.getvalue().splitlines(), [f"ok   {RULE}/plan-changelog-lint{' ' * 20} near-miss pasted   document=ops/premortem.md"])

    def test_the_judge_never_learns_the_changed_paths_or_their_tails(self):
        self.assertEqual(screen.secret_words(self.rule, self.cases["plan-hook-adoption"]), (RULE, RULE, "premortem/SKILL.md"))
        paired = mock.Mock(paired=True, target="poteto-mode/playbooks/premortem.md", id="pm", arm_patches=())
        self.assertEqual(screen.secret_words(paired, self.cases["plan-hook-adoption"]), ("pm", RULE, "playbooks/premortem.md", "poteto-mode/playbooks/premortem.md"))

    def test_build_records_the_document_and_lists_the_skill(self):
        built = self.build()

        self.assertEqual(built["cases"]["plan-hook-adoption"], {"kind": "positive", "timeout_s": 900, "document": {"file": FILE}})
        self.assertEqual(built["arm_listed"], {"current": [], "skill": ["premortem/SKILL.md"]})
        for case in self.cases:
            self.assertFalse((self.out / "arms" / RULE / case / "skill" / "rubric.md").exists())
            self.assertFalse((self.out / "arms" / RULE / case / "skill" / "rules" / RULE / "cases" / case / "samples").exists())


class DocumentJudgeTests(DocumentRule):
    def test_calibration_judges_only_the_cut_document_and_stores_a_document_key(self):
        prompts = []
        invoke = review.invoke

        def recording(backend, model, text, kind, repo=None, commit=None):
            prompts.append(text)
            return invoke(backend, model, text, kind, repo, commit)

        with mock.patch.object(review, "invoke", side_effect=recording), contextlib.redirect_stdout(io.StringIO()) as printed:
            summary = screen.calibrate([self.rule], [("claude", "opus")])

        self.assertEqual([(result["case"], result["template"], result["agreement"], result["calibrated"]) for result in summary], [
            ("plan-changelog-lint", "document-judge-1", {"CLEAN": [1, 1], "FALSE_ALARM": [1, 1]}, True),
            ("plan-hook-adoption", "document-judge-1", {"FOUND": [1, 1], "MISSED": [1, 1], "PARTIAL": [1, 1]}, True),
        ])
        self.assertEqual({name: sample["precheck"] for name, sample in summary[1]["samples"].items()},
                         {"answer-found.md": "PASS", "answer-partial.md": "PASS", "answer-missed.md": "FAIL"})
        self.assertIn(f"{RULE}/plan-hook-adoption positive judge claude:opus: CALIBRATED", printed.getvalue())
        self.assertEqual(len(prompts), 5)
        for text in prompts:
            self.assertEqual(BLIND.findall(text), [], text)
            self.assertNotIn("I read the plan and the register.", text)
            self.assertNotIn("<file path=", DOCUMENT.search(text).group(1))
            self.assertIn("<request>\nWe ", text)
        self.assertIn('<document label="document-', prompts[0])
        case = self.cases["plan-hook-adoption"]
        rubric, subject = (case.root / "rubric.md").read_text(), screen.case_subject(case)
        self.assertEqual(screen.case_calibration(case, "claude", "opus", rubric, subject), (True, "every labeled sample agreed"))
        self.assertEqual(screen.case_calibration(case, "claude", "opus", rubric, {"request": subject["request"] + "x"}),
                         (False, "the guide, the labeled samples, the PR, or the judge changed since calibration"))

    def test_a_run_that_delivers_no_document_is_invalid_not_missed(self):
        self.build()
        case = self.cases["plan-hook-adoption"]
        work = self.out / "codex" / RULE / case.id / "skill"
        run_base = work / "runs" / case.id / "with_skill" / "run-1"
        run_base.mkdir(parents=True)
        (work / "tasks.jsonl").write_text(json.dumps({"run_number": 1, "run_dir": f"{case.id}/with_skill/run-1"}) + "\n")
        (run_base / "output.md").write_text("I wrote the premortem to ops/premortem.md with my tools. GIT_DIR is the cause.\n")
        (run_base / "events.json").write_text(json.dumps({"events": []}))
        (work / "grade.json").write_text(json.dumps({"results": [{"run_number": 1, "run_base": str(run_base),
                                                                  "assertions": [{"name": "rule-behavior", "passed": False, "evidence": "FAIL: no file"}]}]}))

        with contextlib.redirect_stdout(io.StringIO()) as printed:
            rows = screen.judge_arm(self.out, "codex", self.rule, case, "skill")
            screen.compare(self.out)

        self.assertEqual((rows[0]["verdict"], rows[0]["error"], rows[0]["combined"]), (None, "no document: ops/premortem.md not in the final message", "UNJUDGED"))
        compared = json.loads((self.out / "compare.json").read_text())
        self.assertEqual([(row["verdict"], row["reasons"]) for row in compared["runs"]], [("INVALID", "not judged: no document: ops/premortem.md not in the final message")])
        self.assertIn("    skill: review UNJUDGED (judge None, precheck FAIL, uncalibrated: no calibration record)", printed.getvalue().splitlines())


@unittest.skipUnless(harness_available(), "needs the skill-ci command on PATH")
class OfflineDocumentRunTests(DocumentRule):
    def test_the_skill_arm_separates_the_positive_case_and_tie_passes_the_near_miss(self):
        prompts = []
        invoke = review.invoke

        def recording(backend, model, text, kind, repo=None, commit=None):
            prompts.append((backend, model, text))
            return invoke(backend, model, text, kind, repo, commit)

        with contextlib.redirect_stdout(io.StringIO()):
            screen.calibrate([self.rule], [("claude", "opus")])
        with mock.patch.object(review, "invoke", side_effect=recording), contextlib.redirect_stdout(io.StringIO()) as printed:
            screen.run("codex", self.out, [self.rule], "gpt-6-sol", 1, None, "poteto-mode")

        log = printed.getvalue()
        compared = json.loads((self.out / "compare.json").read_text())
        self.assertEqual([(pair["case"], pair["treatment"], pair["outcome"]) for pair in compared["pairs"]],
                         [("plan-changelog-lint", "skill", "tie-pass"), ("plan-hook-adoption", "skill", "separates")], log[-3000:])
        self.assertEqual([(rule["arm"], rule["verdict"], rule.get("uncalibrated")) for rule in compared["rules"]], [("skill", "separates", None)])
        self.assertEqual({(r["case"], r["arm"]): (r["verdict"], r["review"]["combined"], r["review"]["verdict"], r["review"]["precheck"], r["review"]["calibrated"])
                          for r in compared["runs"]}, {
            ("plan-hook-adoption", "current"): ("FAIL", "MISSED", "MISSED", "FAIL", True),
            ("plan-hook-adoption", "skill"): ("PASS", "FOUND", "FOUND", "PASS", True),
            ("plan-changelog-lint", "current"): ("PASS", "CLEAN", "CLEAN", "FAIL", True),
            ("plan-changelog-lint", "skill"): ("PASS", "CLEAN", "CLEAN", "FAIL", True),
        })
        self.assertEqual(compared["arms"], [{"agent": "codex", "rule": RULE, "arm": "skill", "changed_text_reached": 2, "runs": 2, "listed": ["premortem/SKILL.md"]}])
        self.assertIn(f"codex  {RULE:26} arm skill: changed text reached 2/2 run(s); listed by description: premortem/SKILL.md", log)
        self.assertIn(f"codex  {RULE:26} review skill: recall FOUND 1/1 (1.00), FOUND+PARTIAL 1/1 (1.00); false alarms 0/1 (0.00); precheck 1/1 (1.00); 0 unjudged, 0 uncalibrated", log)
        self.assertEqual({(backend, model) for backend, model, _ in prompts}, {("claude", "opus")})
        self.assertEqual(len(prompts), 4)
        for _, _, text in prompts:
            self.assertEqual(BLIND.findall(text), [], text)
            self.assertNotIn("<file path=", DOCUMENT.search(text).group(1))
            self.assertNotIn("I read the plan and the register.", text)
        judged = json.loads((self.out / "codex" / RULE / "plan-hook-adoption" / "skill" / "judge.json").read_text())
        self.assertEqual((judged["results"][0]["template"], judged["results"][0]["label"][:9], judged["results"][0]["evidence_in_review"]),
                         ("document-judge-1", "document-", True))


if __name__ == "__main__":
    unittest.main()
