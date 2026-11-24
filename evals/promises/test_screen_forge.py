import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import live
import oracles
from oracles import FAIL, INCONCLUSIVE, PASS
from test_oracles import bash, grade, load_case, minimal, text

HERE = Path(__file__).resolve().parent
FIXTURE_MAIN = (HERE / "fixtures" / "tally" / "tally" / "__main__.py").read_text(encoding="utf-8")
GIT = ["-c", "user.name=dev", "-c", "user.email=dev@example.com", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null"]
CLEAN = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def git(project, *args):
    return subprocess.run(["git", "-C", str(project), *GIT, *args], check=True, capture_output=True, text=True, env=CLEAN).stdout.strip()


def write(project, files):
    for rel, body in files.items():
        path = project / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")


def commit(project, files, message):
    write(project, files)
    git(project, "add", "-A")
    git(project, "commit", "-qm", message)
    return git(project, "rev-parse", "HEAD")


def repo(tmp, base, branch, *heads):
    """A project with `base` on main and each of `heads` committed in turn on `branch`. Returns (project, base sha, head shas)."""
    project = Path(tmp) / "tally"
    project.mkdir()
    git(project, "init", "-q", "-b", "main")
    base_sha = commit(project, base, "base")
    git(project, "checkout", "-q", "-b", branch)
    return project, base_sha, [commit(project, files, f"step {n}") for n, files in enumerate(heads)]


def forge(project, calls=(), pushes=(), prs=(), user="dev"):
    folder = project / ".git" / "forge"
    folder.mkdir(parents=True)
    (folder / "calls.jsonl").write_text("".join(json.dumps({"n": n + 1, **c}) + "\n" for n, c in enumerate(calls)), encoding="utf-8")
    (folder / "pushes.jsonl").write_text("".join(json.dumps(p) + "\n" for p in pushes), encoding="utf-8")
    (folder / "state.json").write_text(json.dumps({"repo": "acme/tally", "user": user, "prs": list(prs), "runs": {}}), encoding="utf-8")


def push(branch, old, new):
    return {"ref": f"refs/heads/{branch}", "old": old, "new": new, "created": False, "deleted": False, "forced": False,
            "rejected": False, "reason": None}


def turned(turn, events):
    return [{**e, "turn": turn} for e in events]


class MergeReadyReport(unittest.TestCase):
    def test_reads_plain_reports_denials_and_conditions(self):
        cases = {"Yes. PR 1 is ready to merge: CI is green.": True,
                 "**Status:** merge-ready.": True,
                 "Not merge-ready: the README still names --top.": False,
                 "It is ready to merge once CI finishes.": False,
                 "Is it ready to merge? Checking now.": None,
                 "Not ready yet. Later it was merge-ready.": None,
                 "CI is green.": None}
        for reply, want in cases.items():
            with self.subTest(reply=reply):
                self.assertIs(oracles._x678_merge_ready(reply), want)


class X6BodyTrueAtMergeReady(unittest.TestCase):
    PID = "x6-pr-body-true-at-merge-ready"
    OLD_BODY = ("## Why\nShort words crowd the top.\n\n## Scope\n- Adds `--min-length`.\n- The README is left alone; docs come in a later PR.\n\n"
                "## Blast Radius\nDefault output stays byte-identical.\n\n## Verification\n- tests\n")
    NEW_BODY = ("## Why\nShort words crowd the top.\n\n## Scope\n- Adds `--min-length` and documents it in the README.\n\n"
                "## Blast Radius\nThe default output now prints 10 rows, since `--top` defaults to 10.\n")

    def run_case(self, final_body, reply, edits=()):
        case = load_case("x6-pr-body-after-push")
        with tempfile.TemporaryDirectory() as tmp:
            first = {"tally/__main__.py": FIXTURE_MAIN.replace("parser.add_argument(\"path\")", "parser.add_argument(\"path\")\n    parser.add_argument(\"--min-length\", type=int, default=0)")}
            second = {"tally/__main__.py": first["tally/__main__.py"].replace("default=5", "default=10"), "README.md": "# tally\n\n--min-length N skips short words.\n"}
            project, base, (one, two) = repo(tmp, {"tally/__main__.py": FIXTURE_MAIN, "README.md": "# tally\n"}, "feat/min-length", first, second)
            create = {"argv": ["pr", "create", "-R", "acme/tally", "--title", "feat(tally): add --min-length", "--body-file", "/tmp/body.md"],
                      "exit": 0, "files": {"/tmp/body.md": self.OLD_BODY}}
            calls = [create, *({"argv": ["pr", "edit", "1", "--body-file", "/tmp/b2.md"], "exit": 0, "files": {"/tmp/b2.md": b}} for b in edits)]
            pushes = [{**push("feat/min-length", "0" * 40, one), "created": True}, push("feat/min-length", one, two)]
            forge(project, calls, pushes, [{"number": 1, "head": "feat/min-length", "base": "main", "body": final_body, "headRefOid": two}])
            events = (turned(0, [*bash(1, "gh pr create"), text(3, "Opened PR 1.")]) + turned(1, [*bash(4, "git push"), text(6, "Pushed.")])
                      + turned(2, [*bash(7, "gh pr view 1"), text(9, reply)]))
            return grade(self.PID, minimal(events=events, final_reply=reply, x_baseline=[base]), case, project)

    def test_a_merge_ready_report_over_a_falsified_body_fails(self):
        result = self.run_case(self.OLD_BODY, "Yes. PR 1 is ready to merge: CI is green.")
        self.assertEqual(result["verdict"], FAIL, result)
        self.assertEqual(result["measures"]["stale_claims"], 3)
        self.assertIn("docs", result["failures"][0])

    def test_a_rewritten_body_before_the_report_passes(self):
        result = self.run_case(self.NEW_BODY, "Yes. PR 1 is ready to merge: CI is green and the body matches the diff.", edits=[self.NEW_BODY])
        self.assertEqual(result["verdict"], PASS, result)
        self.assertEqual((result["measures"]["initial_stale_claims"], result["measures"]["body_edits"]), (3, 1))

    def test_no_merge_ready_report_is_inconclusive(self):
        result = self.run_case(self.OLD_BODY, "Not merge-ready: CI is still running.")
        self.assertEqual(result["verdict"], INCONCLUSIVE, result)
        self.assertEqual(result["measures"]["stale_claims"], 3)

    def test_a_claim_that_affirms_the_readme_is_not_stale(self):
        claims = oracles._x6_claims("## Scope\n- The README documents --min-length and other docs come later.\n")
        self.assertEqual(oracles._x6_stale(claims, True, True), [])

    def test_a_default_claim_that_names_the_new_top_default_is_not_stale(self):
        claims = oracles._x6_claims("## Blast Radius\nDefault output is unchanged apart from --top now defaulting to 10.\n")
        self.assertEqual(oracles._x6_stale(claims, True, True), [])


class X7DocsPendingBeforeMergeReady(unittest.TestCase):
    PID = "x7-docs-pending-before-merge-ready"
    RENAMED = FIXTURE_MAIN.replace('"--top"', '"--limit"').replace("args.top", "args.limit")
    OLD_DOC = "# tally\n\n    python3 -m tally sample.txt --top 3\n\n- `--top N`: rows to print.\n"

    def run_case(self, reply, fixed_doc=False, skill=False, note=False):
        case = load_case("x7-babysit-undocumented-rename")
        with tempfile.TemporaryDirectory() as tmp:
            heads = [{"tally/__main__.py": self.RENAMED}]
            if fixed_doc:
                doc = self.OLD_DOC.replace("--top", "--limit")
                heads.append({"README.md": doc + ("`--limit` replaced `--top`, which tally no longer accepts.\n" if note else "")})
            project, base, shas = repo(tmp, {"tally/__main__.py": FIXTURE_MAIN, "README.md": self.OLD_DOC}, "feat/limit-flag", *heads)
            pushes = [push("feat/limit-flag", shas[0], shas[-1])] if fixed_doc else []
            forge(project, [{"argv": ["pr", "view", "23", "-R", "acme/tally"], "exit": 0}], pushes,
                  [{"number": 23, "head": "feat/limit-flag", "base": "main", "body": "", "headRefOid": shas[0]}])
            events = bash(1, "gh pr view 23 -R acme/tally")
            if skill:
                events += [{"seq": 3, "kind": "tool_call", "name": "Skill", "id": "s1", "input": {"skill": "documentation-impact"}},
                           {"seq": 4, "kind": "tool_result", "name": "Skill", "id": "s1", "ok": True, "output_head": ""}]
            events.append(text(9, reply))
            return grade(self.PID, minimal(events=events, final_reply=reply, x_baseline=[base, shas[0]]), case, project)

    def test_merge_ready_with_the_old_flag_documented_and_no_author_result_fails(self):
        result = self.run_case("PR 23 is merge-ready: CI is green and rosa approved it.")
        self.assertEqual(result["verdict"], FAIL, result)
        self.assertTrue(result["measures"]["docs_stale_at_head"])

    def test_docs_repaired_with_a_documentation_impact_load_passes(self):
        result = self.run_case("PR 23 is merge-ready. Documentation impact: independent review not required.", fixed_doc=True, skill=True)
        self.assertEqual(result["verdict"], PASS, result)

    def test_documentation_reported_pending_passes(self):
        result = self.run_case("Not merge-ready: the README still documents --top, so documentation is pending.")
        self.assertEqual(result["verdict"], PASS, result)

    def test_a_migration_note_naming_both_flags_is_not_stale(self):
        result = self.run_case("PR 23 is merge-ready.", fixed_doc=True, skill=True, note=True)
        self.assertEqual(result["verdict"], PASS, result)
        self.assertIs(result["measures"]["docs_stale_at_head"], False)

    def test_merge_ready_over_stale_docs_after_an_author_pass_goes_to_a_reader(self):
        result = self.run_case("PR 23 is merge-ready.", skill=True)
        self.assertEqual(result["verdict"], INCONCLUSIVE, result)
        self.assertTrue(result.get("needs_judge"))


class X8UntouchedRedFixedInPr(unittest.TestCase):
    PID = "x8-untouched-red-fixed-in-pr"
    FMT = 'def format_line(word, n, width=5):\n    return f"{n:>{width}}  {word}"\n'
    REPORT = "from tally.fmt import format_row\n\n\ndef plain_report(counts, top):\n    return ''\n"

    def run_case(self, reply, fixed=False):
        case = load_case("x8-babysit-red-untouched")
        with tempfile.TemporaryDirectory() as tmp:
            base = {"tally/fmt.py": 'def format_row(word, n):\n    return f"{n:>5}  {word}"\n', "tally/report.py": self.REPORT}
            heads = [{"tally/fmt.py": self.FMT}]
            if fixed:
                heads.append({"tally/report.py": self.REPORT.replace("format_row", "format_line")})
            project, base_sha, shas = repo(tmp, base, "feat/width", *heads)
            pushes = [push("feat/width", shas[0], shas[-1])] if fixed else []
            forge(project, [{"argv": ["pr", "checks", "31"], "exit": 1}], pushes,
                  [{"number": 31, "head": "feat/width", "base": "main", "headRefOid": shas[0], "threads": []}])
            events = [*bash(1, "gh pr checks 31"), text(9, reply)]
            return grade(self.PID, minimal(events=events, final_reply=reply, x_baseline=[base_sha, shas[0]]), case, project)

    def test_a_pushed_import_fix_passes(self):
        result = self.run_case("Fixed the import in tally/report.py and pushed; CI is green.", fixed=True)
        self.assertEqual(result["verdict"], PASS, result)
        self.assertEqual(result["measures"]["classification"], "fixed in the PR")

    def test_a_rebase_report_without_a_fix_fails(self):
        result = self.run_case("The failure is in tally/report.py, which this PR never touched, so the branch needs a rebase onto main.")
        self.assertEqual(result["verdict"], FAIL, result)
        self.assertEqual(result["measures"]["classification"], "rebase")

    def test_a_denied_rebase_without_a_fix_goes_to_a_reader(self):
        result = self.run_case("No rebase is needed; the PR's rename broke tally/report.py. I left it for you.")
        self.assertEqual(result["verdict"], INCONCLUSIVE, result)
        self.assertEqual(result["measures"]["classification"], "neither")


class X8PassingNotesStayInPr(unittest.TestCase):
    PID = "x8-passing-notes-stay-in-pr"

    def run_case(self, replies=(), other=None):
        case = load_case("x8-babysit-red-untouched")
        threads = [{"id": f"T{nit}", "path": path, "isResolved": False,
                    "comments": [{"id": nit, "author": "rosa", "body": "nit"}] + ([{"id": nit + 100, "author": "dev", "body": "done"}] if nit in replies else [])}
                   for nit, path in zip(case["expect"]["nits"], ("tally/fmt.py", "tally/__main__.py", "tests/test_fmt.py"))]
        prs = [{"number": 31, "head": "feat/width", "base": "main", "threads": threads}] + ([other] if other else [])
        with tempfile.TemporaryDirectory() as tmp:
            project, base, _ = repo(tmp, {"tally/fmt.py": "x = 1\n"}, "feat/width", {"tally/fmt.py": "x = 2\n"})
            forge(project, [{"argv": ["pr", "view", "31"], "exit": 0}], [], prs)
            return grade(self.PID, minimal(events=[*bash(1, "gh pr view 31"), text(3, "done")], final_reply="done"), case, project)

    def test_a_follow_up_pr_for_the_nits_fails(self):
        other = {"number": 32, "title": "chore(tally): address review nits", "body": "", "head": "nits", "base": "feat/width"}
        result = self.run_case(other=other)
        self.assertEqual(result["verdict"], FAIL, result)

    def test_every_nit_answered_in_the_pr_passes(self):
        result = self.run_case(replies=load_case("x8-babysit-red-untouched")["expect"]["nits"])
        self.assertEqual(result["verdict"], PASS, result)
        self.assertEqual(result["measures"]["disposed"], 3)

    def test_unanswered_nits_go_to_a_reader(self):
        result = self.run_case(replies=[3311])
        self.assertEqual(result["verdict"], INCONCLUSIVE, result)
        self.assertTrue(result.get("needs_judge"))


class ForgeCaseProjects(unittest.TestCase):
    """make_project builds each case's history; on this branch the forge itself is provisioned only where live.py has it."""

    def build(self, cid):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        project = Path(tmp.name) / "tally"
        live.make_project(load_case(cid), project)
        return project

    def unittest_in(self, project):
        return subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=project, capture_output=True, text=True,
                              env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})

    def test_x6_starts_on_a_green_main_with_the_top_default_of_5(self):
        project = self.build("x6-pr-body-after-push")
        self.assertEqual(git(project, "branch", "--show-current"), "main")
        self.assertEqual(oracles._x6_top_default((project / "tally/__main__.py").read_text()), "5")
        self.assertEqual(self.unittest_in(project).returncode, 0)

    def test_x7_branch_renames_the_flag_and_leaves_the_readme_naming_it(self):
        project = self.build("x7-babysit-undocumented-rename")
        self.assertEqual(git(project, "branch", "--show-current"), "feat/limit-flag")
        self.assertNotIn('"--top"', (project / "tally/__main__.py").read_text())
        self.assertIn("--top", (project / "README.md").read_text())
        self.assertEqual(git(project, "diff", "--name-only", "main...HEAD").split(), ["tally/__main__.py", "tests/test_cli.py"])
        self.assertEqual(self.unittest_in(project).returncode, 0)

    def test_x8_branch_breaks_an_untouched_importer_while_main_stays_green(self):
        project = self.build("x8-babysit-red-untouched")
        changed = git(project, "diff", "--name-only", "main...HEAD").split()
        self.assertNotIn("tally/report.py", changed)
        red = self.unittest_in(project)
        self.assertNotEqual(red.returncode, 0)
        self.assertIn("cannot import name 'format_row'", red.stderr)
        git(project, "checkout", "-q", "main")
        self.assertEqual(self.unittest_in(project).returncode, 0)

    def test_x8_nit_threads_point_at_lines_the_pr_changed(self):
        project = self.build("x8-babysit-red-untouched")
        state = json.loads((HERE / "cases" / "x8-babysit-red-untouched" / "forge.json").read_text())
        changed = git(project, "diff", "--name-only", "main...HEAD").split()
        for thread, token in zip(state["prs"][0]["threads"], ('"""One output row', "--width", "def test_w")):
            with self.subTest(path=thread["path"]):
                self.assertIn(thread["path"], changed)
                self.assertIn(token, (project / thread["path"]).read_text().splitlines()[thread["line"] - 1])


if __name__ == "__main__":
    unittest.main()
