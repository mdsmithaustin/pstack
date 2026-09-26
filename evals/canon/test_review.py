import contextlib
import difflib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

import test_workspace
from test_workspace import ROOT, ShopRepo, ShopRule, git, harness_available, screen

import review  # noqa: E402
import sandbox  # noqa: E402
import sbx_inside  # noqa: E402
import workspace  # noqa: E402
from shared import apply_diff  # noqa: E402

ORDERS = test_workspace.UPSTREAM["app/orders.py"]
FLAWED = ORDERS + "\n\ndef apply_discount(order, percent):\n    return {**order, \"total\": order[\"total\"] * (1 - percent / 100)}\n"
README = test_workspace.UPSTREAM["README.md"]
NOTED = README + "Orders take discounts at checkout.\n"


def unified(path, before, after):
    return "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), f"a/{path}", f"b/{path}"))


ORACLE = '''def names(*words):
    def check(answer, workspace):
        return [] if any(word in answer for word in words) else [f"the review names none of {list(words)}"]
    return check


CHECKS = {"discount-cap": names("apply_discount", "app/orders.py"), "discount-note": names("README.md")}
'''
CASES = {
    "discount-cap": {
        "kind": "positive", "branch": "discount-cap", "body_file": "pr-body.md", "title": "Add percentage discounts to orders",
        "patch": unified("app/orders.py", ORDERS, FLAWED),
        "body": "Adds apply_discount so support can knock a percentage off an order.\n",
        "prompt": "Can you review the change on branch discount-cap against main before I merge it? The PR description is in pr-body.md.\n",
        "rubric": "Seeded flaw: apply_discount in app/orders.py takes any percent, so a percent above 100 makes the total negative.\n"
                  "FOUND: names apply_discount or app/orders.py, says the percent is unbounded or the total can go negative, and suggests clamping or rejecting it.\n"
                  "PARTIAL: points at apply_discount but lacks the problem or the fix.\nMISSED: anything else.\n",
        "samples": {
            "review-found.md": ("FOUND", "apply_discount in app/orders.py accepts any percent, so 150 makes the total negative. Clamp percent to 0..100 or reject it.\n"),
            "review-partial.md": ("PARTIAL", "apply_discount in app/orders.py looks risky around its percent values.\n"),
            "review-missed.md": ("MISSED", "Looks good to me. Nice small change.\n"),
        },
    },
    "discount-note": {
        "kind": "near-miss", "branch": "docs/discount-note", "body_file": "PR.md", "title": "Mention discounts in the README",
        "patch": unified("README.md", README, NOTED),
        "body": "Documents that orders take discounts.\n",
        "prompt": "Please look over branch docs/discount-note against main before it goes in. The description is in PR.md.\n",
        "rubric": "The change only adds one README.md sentence. Nothing is wrong with it.\n"
                  "FALSE_ALARM: the review says the README.md change is a bug or must change before merge.\nCLEAN: anything else.\n",
        "samples": {
            "review-clean.md": ("CLEAN", "README.md gains one sentence about discounts. Nothing to change.\n"),
            "review-false-alarm.md": ("FALSE_ALARM", "README.md now promises discounts the code never applies; fix this before merge.\n"),
        },
    },
}
RULE = "discount-review"


class ReviewCase(ShopRepo):
    """A rule in a private rules root with one positive and one near-miss
    review case on the shop repo."""

    def setUp(self):
        super().setUp()
        rules = self.base / "rules"
        rule = rules / RULE
        rule.mkdir(parents=True)
        shutil.copyfile(ROOT / "rules" / "preparatory-refactor" / "rule.patch", rule / "rule.patch")
        (rule / "rule.json").write_text(json.dumps({"source": "shop review fixture"}))
        (rule / "oracle.py").write_text(ORACLE)
        for case_id, case in CASES.items():
            root = rule / "cases" / case_id
            (root / "samples").mkdir(parents=True)
            (root / "case.json").write_text(json.dumps({
                "kind": case["kind"], "domain": "orders", "expected_behavior": ["Reviews the pull request."],
                "workspace": {"repo": "shop", "commit": self.commit},
                "review": {"patch": "pr.patch", "title": case["title"], "body_file": case["body_file"], "branch": case["branch"]},
            }))
            (root / "pr.patch").write_text(case["patch"])
            (root / case["body_file"]).write_text(case["body"])
            (root / "prompt.md").write_text(case["prompt"])
            (root / "rubric.md").write_text(case["rubric"])
            for name, (_, text) in case["samples"].items():
                (root / "samples" / name).write_text(text)
            (root / "samples" / "labels.json").write_text(json.dumps({name: label for name, (label, _) in case["samples"].items()}))
        patches = [mock.patch.object(screen, "RULES", rules), mock.patch.dict(os.environ, {"CANON_RULES": str(rules)})]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.rule = screen.load_rule(RULE)
        self.cases = {case.id: case for case in self.rule.cases}
        self.out = self.base / "out"

    def review_spec(self, case_id="discount-cap"):
        return screen.case_spec(self.cases[case_id])

    def build(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return screen.build(self.out, [self.rule], "poteto-mode")[RULE]


class ReviewMaterializeTests(ReviewCase):
    def test_both_arms_get_main_the_pr_branch_and_the_body_with_equal_ids(self):
        spec = self.review_spec()
        roots = [self.harness_workspace(name, "# Poteto mode\n") for name in ("one", "two")]

        trees = [workspace.materialize(root, self.mirror, self.commit, spec.overlay, spec.review) for root in roots]

        refs = [workspace.refs(root, "discount-cap") for root in roots]
        self.assertEqual(trees[0], trees[1])
        self.assertEqual(refs[0], refs[1])
        self.assertEqual(refs[0]["main"], self.commit)
        for root in roots:
            self.assertEqual(git(root, "rev-parse", "--abbrev-ref", "HEAD").strip(), "discount-cap")
            self.assertEqual(git(root, "log", "-1", "--format=%an <%ae>|%cn|%s|%P").strip(),
                             f"Sam Rivera <sam.rivera@example.com>|Sam Rivera|Add percentage discounts to orders|{self.commit}")
            self.assertEqual(git(root, "diff", "--name-only", "main...HEAD"), "app/orders.py\n")
            self.assertEqual((root / "app" / "orders.py").read_text(), FLAWED)
            self.assertEqual((root / "pr-body.md").read_text(), CASES["discount-cap"]["body"])
            self.assertEqual(git(root, "status", "--porcelain"), "?? pr-body.md\n")

    def test_a_patch_that_does_not_apply_is_refused(self):
        spec = self.review_spec()
        broken = {**spec.review, "patch": unified("app/orders.py", "something else\n", "other\n").encode()}

        with self.assertRaisesRegex(workspace.WorkspaceError, r"git apply --index failed: (.|\n)*app/orders.py: patch does not apply"):
            workspace.materialize(self.harness_workspace("broken", "# Poteto mode\n"), self.mirror, self.commit, spec.overlay, broken)

    def test_build_records_one_input_and_the_refs_and_mounts_no_rubric(self):
        built = self.build()

        record = built["cases"]["discount-cap"]
        checkout, tree = workspace.reference_checkout(self.review_spec())
        self.assertEqual(record["review"], {"title": "Add percentage discounts to orders", "branch": "discount-cap", "body_file": "pr-body.md",
                                            "refs": workspace.refs(checkout, "discount-cap")})
        self.assertEqual(len(set(record["workspace"]["arms"].values())), 1)
        self.assertEqual(record["workspace"]["tree"], tree)
        for arm in screen.ARMS:
            arm_input = self.out / "arms" / RULE / "discount-cap" / arm / "workspace"
            self.assertEqual((arm_input / "pr.patch").read_text(), CASES["discount-cap"]["patch"])
            self.assertEqual(json.loads((arm_input / "workspace.json").read_text())["review"], record["review"])
            self.assertEqual((arm_input / "overlay" / "pr-body.md").read_text(), CASES["discount-cap"]["body"])
        outside_skills = [path for path in (self.out / "arms").rglob("*") if path.is_file() and "pstack" not in path.relative_to(self.out).parts]
        self.assertFalse({"rubric.md", "labels.json", "review-found.md", "review-clean.md"} & {path.name for path in outside_skills})
        self.assertNotIn("Seeded flaw", "".join(path.read_text(errors="replace") for path in (self.out / "arms").rglob("*") if path.is_file()))

    def test_a_review_needs_a_rubric_and_labels_the_judge_can_give(self):
        root = self.cases["discount-note"].root
        (root / "samples" / "labels.json").write_text(json.dumps({"review-clean.md": "FOUND"}))

        with self.assertRaisesRegex(screen.ScreenError, r"labels review-clean.md 'FOUND'; a near-miss case's verdicts are \('FALSE_ALARM', 'CLEAN'\)"):
            screen.load_rule(RULE)
        (root / "rubric.md").unlink()
        with self.assertRaisesRegex(screen.ScreenError, "has no rubric.md"):
            screen.load_rule(RULE)


REVIEWER = """import pathlib, subprocess, sys
def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True).stdout.strip()
pathlib.Path("seen.txt").write_text(git("rev-parse", "--abbrev-ref", "HEAD") + " " + git("rev-parse", "main") + " " + pathlib.Path("pr-body.md").read_text())
pathlib.Path("REVIEW.md").write_text("apply_discount needs a cap.\\n")
"""


class ReviewWrapTests(ReviewCase):
    def run_wrap(self, tamper=None):
        self.build()
        arm = self.out / "arms" / RULE / "discount-cap" / "amended" / "workspace"
        if tamper:
            record = json.loads((arm / "workspace.json").read_text())
            tamper(record)
            (arm / "workspace.json").write_text(json.dumps(record))
        root = self.harness_workspace("wrapped", "# Poteto mode\n")
        (self.base / "reviewer.py").write_text(REVIEWER)
        previous = Path.cwd()
        os.chdir(root)
        try:
            with mock.patch.dict(os.environ, {"CANON_WORKSPACE": str(arm), "CANON_HARVEST": str(self.base / "harvest")}), \
                    contextlib.redirect_stderr(io.StringIO()):
                code = workspace.wrap(["--", sys.executable, str(self.base / "reviewer.py")], stdin=io.BytesIO(b"Review it."))
        finally:
            os.chdir(previous)
        slot = self.base / "harvest" / "0001"
        return code, root, json.loads((slot / "workspace.json").read_text()), slot

    def test_reviewer_sees_the_pr_branch_and_its_written_file_is_harvested(self):
        code, root, record, slot = self.run_wrap()

        refs = json.loads((self.out / "arms" / RULE / "build.json").read_text())["cases"]["discount-cap"]["review"]["refs"]
        self.assertEqual(code, 0)
        self.assertEqual((root / "seen.txt").read_text(), f"discount-cap {self.commit} {CASES['discount-cap']['body']}")
        self.assertEqual((record["refs"], record["head_after"], record["refs_after"]), (refs, refs["discount-cap"], refs))
        checkout = workspace.reference_checkout(self.review_spec())[0]
        self.assertEqual(apply_diff(checkout, (slot / "workspace.diff").read_text()),
                         {"REVIEW.md": b"apply_discount needs a cap.\n", "seen.txt": (root / "seen.txt").read_bytes()})

    def test_wrapper_refuses_refs_that_are_not_the_recorded_ones(self):
        code, root, record, _ = self.run_wrap(lambda spec: spec["review"]["refs"].update(main="0" * 40))

        self.assertEqual(code, workspace.REFUSED)
        self.assertIn("are not the recorded", record["error"])
        self.assertFalse((root / "REVIEW.md").exists())


class ReviewInsideTests(ReviewCase):
    """sbx_inside setup on a clone that carries only the PR branch, as a
    single-branch clone would."""

    def test_setup_recreates_main_and_the_pr_branch_in_the_clone(self):
        spec = self.review_spec()
        stage = self.base / "stage"
        stage.mkdir()
        tree = workspace.materialize(stage, self.mirror, self.commit, {}, spec.review)
        refs = workspace.refs(stage, "discount-cap")
        sandbox.self_contained(stage)
        clone = self.base / "clone"
        subprocess.run(["git", "clone", "-q", "--single-branch", "--branch", "discount-cap", str(stage), str(clone)],
                       env={**os.environ, **workspace.GIT_ENV}, check=True, capture_output=True)
        git(clone, "checkout", "-q", "--detach")
        git(clone, "branch", "-D", "discount-cap")
        payload = self.base / "payload"
        (payload / "skills" / "tools").mkdir(parents=True)
        (payload / "skills" / "tools" / "notes.md").write_text("mounted\n")
        (payload / "overlay").mkdir()
        (payload / "overlay" / "pr-body.md").write_text(CASES["discount-cap"]["body"])
        record = {"repo": "shop", "commit": self.commit, "tree": workspace.reference_checkout(spec)[1],
                  "review": {"branch": "discount-cap", "refs": refs}}
        (payload / "manifest.json").write_text(json.dumps(sandbox.manifest("claude", clone, record, None)))

        result = sbx_inside.setup(payload / "manifest.json")

        self.assertEqual(result["tree"], workspace.reference_checkout(spec)[1])
        self.assertNotEqual(tree, result["tree"])
        self.assertEqual(workspace.refs(clone, "discount-cap"), refs)
        self.assertEqual(git(clone, "rev-parse", "--abbrev-ref", "HEAD").strip(), "discount-cap")
        self.assertEqual(workspace.head_state(clone)["head_after"], refs["discount-cap"])


PR = {"title": "Add percentage discounts to orders", "body": "Adds apply_discount.\n", "diff": CASES["discount-cap"]["patch"]}


class JudgeParseTests(unittest.TestCase):
    def test_a_strict_verdict_parses_bare_or_fenced(self):
        self.assertEqual(review.parse('{"verdict": "FOUND", "evidence": "clamp it"}', "positive"), ("FOUND", "clamp it"))
        self.assertEqual(review.parse('```json\n{"verdict": "CLEAN", "evidence": ""}\n```', "near-miss"), ("CLEAN", ""))

    def test_off_contract_output_is_refused(self):
        for text, kind, message in (
            ('{"verdict": "FOUND"}', "positive", "exactly verdict and evidence"),
            ('{"verdict": "FOUND", "evidence": "", "score": 1}', "positive", "exactly verdict and evidence"),
            ('{"verdict": "FOUND", "evidence": ""}', "near-miss", "is not one of"),
            ('{"verdict": "found", "evidence": ""}', "positive", "is not one of"),
            ('{"verdict": "MISSED", "evidence": 3}', "positive", "evidence must be a string"),
            ('Verdict: FOUND', "positive", "not one JSON object"),
            ('{"verdict": "FOUND", "evidence": ""} {"verdict": "MISSED", "evidence": ""}', "positive", "not one JSON object"),
        ):
            with self.subTest(text=text), self.assertRaisesRegex(review.JudgeError, message):
                review.parse(text, kind)

    def test_claude_envelope_yields_its_structured_output_or_result(self):
        structured = json.dumps({"type": "result", "is_error": False, "result": "", "structured_output": {"verdict": "MISSED", "evidence": ""}})
        plain = json.dumps({"type": "result", "is_error": False, "result": '{"verdict": "PARTIAL", "evidence": "x"}'})

        self.assertEqual(review.parse(review.claude_answer(structured), "positive"), ("MISSED", ""))
        self.assertEqual(review.parse(review.claude_answer(plain), "positive"), ("PARTIAL", "x"))
        with self.assertRaisesRegex(review.JudgeError, "claude reported an error: OAuth session expired"):
            review.claude_answer(json.dumps({"type": "result", "is_error": True, "result": "OAuth session expired"}))

    def test_a_flagged_verdict_counts_only_when_the_precheck_passes(self):
        self.assertEqual([review.combine("positive", verdict, passed) for verdict, passed in
                          (("FOUND", True), ("FOUND", False), ("PARTIAL", False), ("MISSED", True))], ["FOUND", "MISSED", "MISSED", "MISSED"])
        self.assertEqual([review.combine("near-miss", verdict, passed) for verdict, passed in
                          (("FALSE_ALARM", True), ("FALSE_ALARM", False), ("CLEAN", False))], ["FALSE_ALARM", "CLEAN", "CLEAN"])

    def test_judge_schema_offers_only_the_kinds_verdicts(self):
        self.assertEqual(review.schema("near-miss")["properties"]["verdict"]["enum"], ["FALSE_ALARM", "CLEAN"])
        self.assertEqual(review.schema("positive")["required"], ["verdict", "evidence"])
        self.assertFalse(review.schema("positive")["additionalProperties"])


BLIND = re.compile(r"\b(discount-review|current|amended|claude|codex|anthropic|openai|gpt|opus|sonnet|poteto|pstack|skills?)\b", re.IGNORECASE)


class JudgeBlindingTests(unittest.TestCase):
    def test_prompt_names_no_rule_arm_agent_or_skill(self):
        answer = ("I read .claude/skills/poteto-mode/SKILL.md and skills/pstack/interrogate/SKILL.md after /poteto-mode, "
                  "per discount-review. As Claude I think apply_discount in app/orders.py lets 150 percent make the total negative.\n")
        written = "diff --git a/REVIEW.md b/REVIEW.md\n+Codex says: cap the percent.\n"

        text, label, redactions = review.prompt("positive", CASES["discount-cap"]["rubric"], PR, answer, written, (RULE,))

        self.assertEqual(BLIND.findall(text), [])
        self.assertRegex(label, r"^review-[0-9a-f]{8}$")
        self.assertIn(f'<review label="{label}">', text)
        self.assertIn("apply_discount in app/orders.py lets 150 percent make the total negative.", text)
        self.assertIn(CASES["discount-cap"]["patch"].rstrip("\n"), text)
        self.assertIn("Allowed verdicts: FOUND, PARTIAL, MISSED.", text)
        self.assertEqual(sorted(redactions), sorted([".claude/skills/poteto-mode/SKILL.md", "skills/pstack/interrogate/SKILL.md", "/poteto-mode",
                                                     "discount-review", "Claude", "Codex"]))

    def test_an_agent_name_the_pr_itself_uses_is_kept(self):
        pr = {**PR, "diff": PR["diff"] + "+# the claude adapter rounds here\n"}

        text, _, redactions = review.prompt("positive", "Flaw in the claude adapter.\n", pr, "The claude adapter rounds wrong.\n")

        self.assertIn("The claude adapter rounds wrong.", text)
        self.assertEqual(redactions, [])

    def test_the_label_depends_only_on_the_review_text(self):
        self.assertEqual(review.label("same review"), review.label("same review"))
        self.assertNotEqual(review.label("same review"), review.label("other review"))


class CalibrationMathTests(unittest.TestCase):
    SAMPLES = {
        "review-found.md": {"label": "FOUND", "verdict": "FOUND"},
        "review-partial.md": {"label": "PARTIAL", "verdict": "MISSED"},
        "review-missed.md": {"label": "MISSED", "verdict": "MISSED"},
        "review-missed-2.md": {"label": "MISSED", "verdict": None},
    }

    def test_agreement_counts_each_label_and_any_miss_leaves_it_uncalibrated(self):
        self.assertEqual(review.agreement(self.SAMPLES), ({"FOUND": [1, 1], "PARTIAL": [0, 1], "MISSED": [1, 2]}, False))
        self.assertEqual(review.agreement({"a": {"label": "CLEAN", "verdict": "CLEAN"}}), ({"CLEAN": [1, 1]}, True))
        self.assertEqual(review.agreement({}), ({}, False))

    def test_status_names_why_a_case_is_uncalibrated(self):
        agreed = {"key": "k", "samples": {"a": {"label": "CLEAN", "verdict": "CLEAN"}}}
        self.assertEqual(review.calibration_status(None, "k"), (False, "no calibration record"))
        self.assertEqual(review.calibration_status(agreed, "other"), (False, "the guide, the PR, or the judge changed since calibration"))
        self.assertEqual(review.calibration_status({"key": "k", "samples": self.SAMPLES}, "k"),
                         (False, "judge disagrees with labels: review-missed-2.md labeled MISSED judged None; review-partial.md labeled PARTIAL judged MISSED"))
        self.assertEqual(review.calibration_status(agreed, "k"), (True, "every labeled sample agreed"))

    def test_key_changes_with_the_rubric_the_pr_and_the_judge(self):
        key = review.calibration_key("codex", "gpt-6-sol", "positive", "guide", PR)
        self.assertEqual(key, review.calibration_key("codex", "gpt-6-sol", "positive", "guide", dict(PR)))
        self.assertEqual(len({key, review.calibration_key("claude", "opus", "positive", "guide", PR),
                              review.calibration_key("codex", "gpt-6-sol", "positive", "guide 2", PR),
                              review.calibration_key("codex", "gpt-6-sol", "positive", "guide", {**PR, "diff": ""})}), 4)


def row(kind, combined, precheck="PASS", calibrated=True):
    return {"kind": kind, "review": {"combined": combined, "precheck": precheck, "calibrated": calibrated}}


class ScoreTests(unittest.TestCase):
    def test_recall_counts_positive_runs_and_false_alarms_count_near_miss_runs(self):
        rows = [row("positive", "FOUND"), row("positive", "PARTIAL"), row("positive", "MISSED", "FAIL"), row("positive", "UNJUDGED", "FAIL", False),
                row("near-miss", "CLEAN"), row("near-miss", "FALSE_ALARM", calibrated=False)]

        self.assertEqual(review.scores(rows), {
            "recall_found": {"count": 1, "of": 4, "rate": 0.25},
            "recall_found_or_partial": {"count": 2, "of": 4, "rate": 0.5},
            "false_alarm_rate": {"count": 1, "of": 2, "rate": 0.5},
            "precheck_pass": {"count": 2, "of": 4, "rate": 0.5},
            "unjudged": 1,
            "uncalibrated": 1,
        })

    def test_an_arm_without_near_miss_runs_has_no_rate(self):
        self.assertEqual(review.scores([row("positive", "FOUND")])["false_alarm_rate"], {"count": 0, "of": 0, "rate": None})
        self.assertEqual(screen.score_line({"agent": "codex", "rule": RULE, "arm": "amended", **review.scores([row("positive", "FOUND")])}),
                         "recall FOUND 1/1 (1.00), FOUND+PARTIAL 1/1 (1.00); false alarms 0/0; precheck 1/1 (1.00); 0 unjudged, 0 uncalibrated")


class StreamFailureTests(ShopRule):
    """An arm that fails after the agent ran must leave a traceback, not vanish."""

    def test_a_failing_arm_is_logged_with_its_traceback_and_the_next_arm_still_runs(self):
        ran = []

        def run_arm(agent, out, rule, case, arm, *rest):
            ran.append(arm)
            if arm == "current":
                raise RuntimeError("the wrapper filled 0 workspace slot(s) for 1 run(s)")

        with mock.patch.object(screen, "agent_env", return_value={}), mock.patch.object(screen, "check_manifest"), \
                mock.patch.object(screen, "run_arm", side_effect=run_arm), contextlib.redirect_stdout(io.StringIO()) as printed, \
                contextlib.redirect_stderr(io.StringIO()) as errors:
            with self.assertRaisesRegex(screen.ScreenError, r"1 arm\(s\) or case\(s\) failed: orders-workspace/orders-amend/current"):
                screen.run("codex", self.out, [self.rule], "gpt-6-sol", 1, None, "poteto-mode")

        self.assertEqual(ran, ["current", "amended"])
        log = (self.out / screen.ERROR_LOG).read_text()
        self.assertIn("codex/orders-workspace/orders-amend/current", log)
        self.assertIn("Traceback (most recent call last):", log)
        self.assertIn("RuntimeError: the wrapper filled 0 workspace slot(s) for 1 run(s)", log)
        for stream in (printed, errors):
            self.assertIn("screen: ERROR in codex/orders-workspace/orders-amend/current: RuntimeError", stream.getvalue())

    def test_an_unexpected_error_in_any_command_is_logged_and_exits_one(self):
        with mock.patch.object(screen, "compare", side_effect=KeyError("grade.json")), \
                contextlib.redirect_stdout(io.StringIO()) as printed, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(screen.main(["compare", "--out", str(self.out)]), 1)

        log = (self.out / screen.ERROR_LOG).read_text()
        self.assertIn("Traceback (most recent call last):", log)
        self.assertIn("KeyError: 'grade.json'", log)
        self.assertIn(f"traceback in {self.out.resolve() / screen.ERROR_LOG}", printed.getvalue())

    def test_regrade_maps_numbered_slots_and_grades_a_run_the_harness_never_graded(self):
        with contextlib.redirect_stdout(io.StringIO()):
            built = screen.build(self.out, [self.rule], "poteto-mode")
        tree = built["orders-workspace"]["cases"]["orders-amend"]["workspace"]["tree"]
        work = self.out / "codex" / "orders-workspace" / "orders-amend" / "amended"
        run_dir = "orders-amend/with_skill"
        (work / "runs" / run_dir).mkdir(parents=True)
        (work / "runs" / run_dir / "output.md").write_text("Done.\n")
        (work / "tasks.jsonl").write_text(json.dumps({"run_number": 1, "run_dir": run_dir, "variant": "with_skill"}) + "\n")
        slot = work / "harvest" / "0001"
        slot.mkdir(parents=True)
        (slot / "workspace.json").write_text(json.dumps({"tree": tree}))
        (slot / "workspace.diff").write_text(test_workspace.GOOD_DIFF)

        with contextlib.redirect_stdout(io.StringIO()) as printed:
            self.assertEqual(screen.main(["regrade", "--out", str(self.out)]), 0)

        self.assertTrue((work / "harvest" / run_dir / "workspace.diff").is_file())
        self.assertFalse(slot.exists())
        compared = json.loads((self.out / "compare.json").read_text())
        self.assertEqual([(r["arm"], r["run"], r["verdict"], r.get("graded_from_diff"), r.get("ungraded")) for r in compared["runs"]],
                         [("amended", 1, "PASS", True, True)])
        self.assertIn("amended: no grade.json; the run stopped before the harness graded it", printed.getvalue())


def judge_env():
    return mock.patch.dict(os.environ, {"CODEX_BIN": str(ROOT / "offline" / "codex"), "CANON_JUDGE_STANDIN": str(ROOT / "offline" / "judge")})


@unittest.skipUnless(harness_available(), "needs a skill-ci checkout at $SKILL_CI and uv")
class OfflineReviewRunTests(ReviewCase):
    def test_stand_in_reviews_are_judged_blind_scored_and_calibrated(self):
        prompts = []
        invoke = review.invoke

        def recording(backend, model, text, kind, repo=None, commit=None):
            prompts.append((backend, model, text))
            return invoke(backend, model, text, kind, repo, commit)

        with judge_env(), mock.patch.object(review, "invoke", side_effect=recording), contextlib.redirect_stdout(io.StringIO()) as printed:
            screen.run("codex", self.out, [self.rule], "gpt-6-sol", 1, None, "poteto-mode")

        log = printed.getvalue()
        compared = json.loads((self.out / "compare.json").read_text())
        self.assertEqual([(pair["case"], pair["outcome"]) for pair in compared["pairs"]], [("discount-cap", "separates"), ("discount-note", "tie-pass")], log[-3000:])
        self.assertEqual([(rule["verdict"], rule.get("uncalibrated")) for rule in compared["rules"]], [("separates", True)])
        self.assertEqual({(r["case"], r["arm"]): (r["review"]["combined"], r["review"]["verdict"], r["review"]["precheck"]) for r in compared["runs"]}, {
            ("discount-cap", "current"): ("MISSED", "MISSED", "FAIL"),
            ("discount-cap", "amended"): ("FOUND", "FOUND", "PASS"),
            ("discount-note", "current"): ("CLEAN", "CLEAN", "PASS"),
            ("discount-note", "amended"): ("CLEAN", "CLEAN", "PASS"),
        })
        scores = {score["arm"]: (score["recall_found"]["count"], score["recall_found"]["of"], score["false_alarm_rate"]["count"],
                                 score["false_alarm_rate"]["of"], score["uncalibrated"]) for score in compared["review_scores"]}
        self.assertEqual(scores, {"current": (0, 1, 0, 1, 2), "amended": (1, 1, 0, 1, 2)})
        self.assertIn(f"codex  {RULE:26} review amended: recall FOUND 1/1 (1.00)", log)
        self.assertEqual({(backend, model) for backend, model, _ in prompts}, {("claude", "opus")})
        self.assertEqual(len(prompts), 4)
        for _, _, text in prompts:
            self.assertEqual(BLIND.findall(text), [])
        judged = json.loads((self.out / "codex" / RULE / "discount-cap" / "amended" / "judge.json").read_text())
        self.assertEqual(judged["judge"], {"backend": "claude", "model": "opus"})
        self.assertEqual((judged["results"][0]["calibrated"], judged["results"][0]["calibration"]), (False, "no calibration record"))

        with judge_env(), contextlib.redirect_stdout(io.StringIO()) as printed:
            summary = screen.calibrate([self.rule], [("claude", "opus")])
            screen.judge_all(self.out)

        self.assertEqual([(result["case"], result["agreement"], result["calibrated"]) for result in summary], [
            ("discount-cap", {"FOUND": [1, 1], "MISSED": [1, 1], "PARTIAL": [1, 1]}, True),
            ("discount-note", {"CLEAN": [1, 1], "FALSE_ALARM": [1, 1]}, True),
        ])
        self.assertEqual({name: sample["precheck"] for name, sample in summary[0]["samples"].items()},
                         {"review-found.md": "PASS", "review-missed.md": "FAIL", "review-partial.md": "PASS"})
        compared = json.loads((self.out / "compare.json").read_text())
        self.assertEqual({row["review"]["calibrated"] for row in compared["runs"]}, {True})
        self.assertEqual([rule.get("uncalibrated") for rule in compared["rules"]], [None])
        self.assertIn("discount-review/discount-cap positive judge claude:opus: CALIBRATED", printed.getvalue())

    def test_a_changed_rubric_makes_the_case_uncalibrated_again(self):
        with judge_env(), contextlib.redirect_stdout(io.StringIO()):
            screen.calibrate([self.rule], [("claude", "opus")])
        case = self.cases["discount-cap"]
        rubric, pr = (case.root / "rubric.md").read_text(), screen.review_pr(case)

        with judge_env():
            self.assertEqual(screen.case_calibration(case, "claude", "opus", rubric, pr), (True, "every labeled sample agreed"))
            self.assertEqual(screen.case_calibration(case, "claude", "opus", rubric + "More.\n", pr),
                             (False, "the guide, the PR, or the judge changed since calibration"))
            self.assertEqual(screen.case_calibration(case, "codex", "gpt-6-sol", rubric, pr), (False, "no calibration record"))
        self.assertEqual(screen.case_calibration(case, "claude", "opus", rubric, pr), (False, "no calibration record"))


@unittest.skipUnless(os.environ.get("CANON_SBX_E2E") == "1" and shutil.which("sbx") and harness_available(),
                     "needs CANON_SBX_E2E=1, Docker Sandboxes (sbx), and the skill-ci harness")
class SandboxedReviewRunTests(ReviewCase):
    def test_codex_stand_in_reviews_the_pr_branch_inside_a_sandbox(self):
        environment = {"CANON_SBX_STANDIN": str(ROOT / "offline" / "sbx-agent"), "CANON_JUDGE_STANDIN": str(ROOT / "offline" / "judge")}
        with mock.patch.dict(os.environ, environment), contextlib.redirect_stdout(io.StringIO()) as printed:
            screen.run("codex", self.out, [self.rule], "gpt-6-sol", 1, None, "poteto-mode", "sbx")

        compared = json.loads((self.out / "compare.json").read_text())
        self.assertEqual([(pair["case"], pair["outcome"]) for pair in compared["pairs"]], [("discount-cap", "separates"), ("discount-note", "tie-pass")],
                         printed.getvalue()[-3000:])
        refs = json.loads((self.out / "arms" / RULE / "build.json").read_text())["cases"]["discount-cap"]["review"]["refs"]
        record = json.loads((self.out / "codex" / RULE / "discount-cap" / "amended" / "harvest" / "discount-cap" / "with_skill" / "workspace.json").read_text())
        self.assertEqual((record["agent_rc"], record["refs"], record["head_after"], record["refs_after"]), (0, refs, refs["discount-cap"], refs))


class StandinCalibrationTests(unittest.TestCase):
    def test_standin_calibration_never_counts_for_the_model_judge(self):
        pr = {"title": "t", "body": "b", "diff": "d"}
        with mock.patch.dict(os.environ, {"CANON_JUDGE_STANDIN": "/bin/true"}):
            standin_key = review.calibration_key("codex", "gpt-6-sol", "positive", "guide", pr)
            standin_path = review.calibration_path("r", "c", "codex", "gpt-6-sol")
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CANON_JUDGE_STANDIN", None)
            model_key = review.calibration_key("codex", "gpt-6-sol", "positive", "guide", pr)
            model_path = review.calibration_path("r", "c", "codex", "gpt-6-sol")
        self.assertNotEqual(standin_key, model_key)
        self.assertEqual(standin_path.name, "standin-codex-gpt-6-sol.json")
        self.assertEqual(model_path.name, "model-codex-gpt-6-sol.json")


if __name__ == "__main__":
    unittest.main()
