import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from forge import provision
from live import GIT_ISOLATION, git_run

BANNED = re.compile(r"stub|fake|double|eval|judge|rubric|score|promise|oracle|verdict|benchmark|experiment", re.I)
TESTS = """import unittest
from tally import add


class AddTest(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(1, 2), 3)
"""
CANNED = {
    "next_number": 31,
    "prs": [{
        "number": 30, "title": "Count pairs", "body": "Adds pair counting.", "head": "fix/pairs", "base": "main",
        "reviewRequests": ["copilot-pull-request-reviewer[bot]"],
        "checks": [{"name": "lint", "conclusion": "SUCCESS"}],
        "reviews": [{"id": 501, "author": "copilot-pull-request-reviewer[bot]", "state": "COMMENTED",
                     "body": "Two notes.", "commit": "head"}],
        "threads": [
            {"id": "PRRT_kwDOaa1", "path": "tally.py", "line": 2, "isResolved": False,
             "comments": [{"id": 601, "author": "copilot-pull-request-reviewer[bot]", "body": "Guard odd input."}]},
            {"id": "PRRT_kwDOaa2", "path": "README.md", "line": 1, "isResolved": True,
             "comments": [{"id": 602, "author": "copilot-pull-request-reviewer[bot]", "body": "Typo."}]},
        ],
        "comments": [{"id": 701, "author": "dev", "body": "Ready for a look."}],
    }],
}
THREADS_QUERY = ("query($owner: String!, $name: String!, $number: Int!) { repository(owner: $owner, name: $name) "
                 "{ pullRequest(number: $number) { reviewThreads(first: 100) { nodes { id isResolved path "
                 "comments(first: 50) { nodes { databaseId body } } } } } } }")


def write(root, files):
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)


class ForgeTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.project = self.tmp / "w" / "tally"
        self.project.mkdir(parents=True)

    def build(self, canned=None, protected=("main",), extra_push=()):
        p = self.project
        write(p, {"tally.py": "def add(a, b):\n    return a + b\n", "tests/test_tally.py": TESTS,
                  "README.md": "# tally\n"})
        git_run(p, "init", "-q", "-b", "main")
        git_run(p, "add", "-A")
        git_run(p, "commit", "-qm", "initial import")
        git_run(p, "checkout", "-q", "-b", "fix/pairs")
        write(p, {"tally.py": "def add(a, b):\n    return a + b\n\n\ndef pairs(xs):\n    return len(xs) // 2\n"})
        git_run(p, "commit", "-qam", "Count pairs")
        git_run(p, "checkout", "-q", "-b", "broken", "main")
        write(p, {"tally.py": "def add(a, b):\n    return a - b\n"})
        git_run(p, "commit", "-qam", "Subtract instead")
        git_run(p, "checkout", "-q", "fix/pairs")
        spec_dir = self.tmp / "case"
        spec_dir.mkdir()
        spec = {"repo": "acme/tally", "push": ["main", "fix/pairs", "broken", *extra_push],
                "protected": list(protected),
                "ci": {"name": "test", "command": "python3 -m unittest discover -s tests", "timeout_s": 60}}
        if canned:
            (spec_dir / "forge.json").write_text(json.dumps(canned))
            spec["state"] = "forge.json"
        provision(p, spec, spec_dir, git_run)
        self.forge = p / ".git" / "forge"
        self.env = {**os.environ, **GIT_ISOLATION, "PATH": f"{self.forge / 'bin'}{os.pathsep}{os.environ['PATH']}",
                    "GIT_AUTHOR_NAME": "dev", "GIT_AUTHOR_EMAIL": "dev@example.com",
                    "GIT_COMMITTER_NAME": "dev", "GIT_COMMITTER_EMAIL": "dev@example.com",
                    "TMPDIR": str(self.tmp)}

    def run_cmd(self, *argv, input=None):
        result = subprocess.run(argv, cwd=self.project, env=self.env, capture_output=True, text=True, input=input)
        self.assertIsNone(BANNED.search(result.stdout + result.stderr), result.stdout + result.stderr)
        return result

    def gh(self, *args, code=0, input=None):
        result = self.run_cmd("gh", *args, input=input)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result.stdout

    def gh_json(self, *args, input=None):
        return json.loads(self.gh(*args, input=input))

    def git(self, *args, code=0):
        result = self.run_cmd("git", *args)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result.stdout.strip()

    def remote(self, *args):
        return git_run(self.forge / "remote.git", *args, capture_output=True, text=True).stdout.strip()

    def log(self, name):
        return [json.loads(line) for line in (self.forge / name).read_text().splitlines()]

    def test_setup_pushes_are_quiet_and_tracked(self):
        self.build()
        self.assertEqual(self.log("pushes.jsonl"), [])
        self.assertEqual(self.git("remote", "-v").split(),
                         ["origin", "git@github.com:acme/tally.git", "(fetch)",
                          "origin", "git@github.com:acme/tally.git", "(push)"])
        self.assertEqual(self.git("rev-parse", "--abbrev-ref", "fix/pairs@{upstream}"), "origin/fix/pairs")
        self.assertEqual(self.run_cmd("sh", "-c", "command -v gh").stdout.strip(), str(self.forge / "bin" / "gh"))

    def test_an_ssh_command_override_still_reaches_the_forge(self):
        self.build()
        override = {**self.env, "GIT_SSH_COMMAND": "ssh -o BatchMode=yes -o ConnectTimeout=5"}
        result = subprocess.run(["git", "ls-remote", "--exit-code", "origin", "refs/heads/main"], cwd=self.project, env=override,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.run_cmd("sh", "-c", "command -v ssh").stdout.strip(), str(self.forge / "bin" / "ssh"))

    def test_push_force_push_and_protected_branch(self):
        self.build()
        self.git("checkout", "-q", "-b", "feature")
        write(self.project, {"notes.txt": "one\n"})
        self.git("add", "notes.txt")
        self.git("commit", "-qm", "Add notes")
        self.git("push", "-q", "-u", "origin", "feature")
        self.assertEqual(self.git("rev-parse", "--abbrev-ref", "feature@{upstream}"), "origin/feature")
        self.git("commit", "-q", "--amend", "-m", "Add notes, reworded")
        self.git("push", "-q", "--force", "origin", "feature")
        self.git("checkout", "-q", "main")
        write(self.project, {"notes.txt": "direct\n"})
        self.git("add", "notes.txt")
        self.git("commit", "-qm", "Direct to main")
        before = self.remote("rev-parse", "main")
        rejected = self.run_cmd("git", "push", "origin", "main")
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("remote: error: GH006: Protected branch update failed for refs/heads/main.", rejected.stderr)
        self.assertEqual(self.remote("rev-parse", "main"), before)
        created, forced, protected = self.log("pushes.jsonl")
        self.assertEqual((created["ref"], created["created"], created["forced"]), ("refs/heads/feature", True, False))
        self.assertEqual((forced["forced"], forced["rejected"]), (True, False))
        self.assertEqual((protected["ref"], protected["rejected"], protected["reason"]),
                         ("refs/heads/main", True, "protected branch"))
        denied = self.run_cmd("git", "ls-remote", "git@github.com:other/repo.git")
        self.assertIn("ERROR: Repository not found.", denied.stderr)

    def test_create_requires_a_pushed_branch(self):
        self.build()
        self.git("checkout", "-q", "-b", "local-only")
        out = self.run_cmd("gh", "pr", "create", "--title", "t", "--body", "b")
        self.assertEqual(out.returncode, 1)
        self.assertIn("you must first push the current branch", out.stderr)

    def test_create_view_list_and_jq(self):
        self.build()
        (self.tmp / "body.md").write_text("Adds `pairs`.\n")
        url = self.gh("pr", "create", "--title", "Count pairs", "--body-file", str(self.tmp / "body.md")).strip()
        self.assertEqual(url, "https://github.com/acme/tally/pull/1")
        dup = self.run_cmd("gh", "pr", "create", "--title", "again", "--body", "")
        self.assertIn('a pull request for branch "fix/pairs" into branch "main" already exists:\n' + url, dup.stderr)
        view = self.gh_json("pr", "view", "--json", "number,headRefName,state,baseRefName,files,body")
        self.assertEqual(view["number"], 1)
        self.assertEqual((view["headRefName"], view["state"], view["baseRefName"]), ("fix/pairs", "OPEN", "main"))
        self.assertEqual(view["files"], [{"path": "tally.py", "additions": 4, "deletions": 0}])
        self.assertEqual(self.gh("pr", "list", "--json", "number,title", "--jq", '.[] | "\\(.number) \\(.title)"'),
                         "1 Count pairs\n")
        self.assertEqual(self.gh("pr", "view", url, "--json", "number,url", "-q", "[.number, .url] | @tsv"),
                         f"1\t{url}\n")
        self.assertEqual(self.gh("pr", "list", "-R", "github.com/acme/tally", "--state", "all", "--json", "number",
                                 "--jq", "map(.number) | length"), "1\n")
        bad = self.run_cmd("gh", "pr", "view", "1", "--json", "nope")
        self.assertIn('Unknown JSON field: "nope"', bad.stderr)
        other = self.run_cmd("gh", "pr", "list", "-R", "x/y")
        self.assertIn("Could not resolve to a Repository with the name 'x/y'.", other.stderr)
        call = self.log("calls.jsonl")[0]
        self.assertEqual(call["files"], {str(self.tmp / "body.md"): "Adds `pairs`.\n"})
        self.assertEqual((call["n"], call["exit"], call["unsupported"]), (1, 0, False))
        self.assertEqual(self.log("calls.jsonl")[-1]["repo"], "x/y")

    def test_ci_checks_and_runs(self):
        self.build()
        self.gh("pr", "create", "--title", "Count pairs", "--body", "")
        self.gh("pr", "create", "--head", "broken", "--title", "Subtract", "--body", "")
        rollup = self.gh_json("pr", "view", "1", "--json", "statusCheckRollup,mergeStateStatus")
        self.assertEqual([(c["name"], c["conclusion"]) for c in rollup["statusCheckRollup"]], [("test", "SUCCESS")])
        self.assertEqual(rollup["mergeStateStatus"], "CLEAN")
        self.gh("pr", "checks", "1")
        self.assertIn("test\tfail\t", self.gh("pr", "checks", "2", code=1))
        self.assertEqual(self.gh("pr", "checks", "2", "--json", "name,bucket", "--jq", ".[].bucket"), "fail\n")
        run_id = self.gh("run", "list", "--branch", "broken", "--json", "databaseId", "--jq", ".[0].databaseId").strip()
        log = self.gh("run", "view", run_id, "--log-failed")
        self.assertIn("AssertionError: -1 != 3", log)
        self.assertNotIn(str(self.tmp), log)
        self.gh("run", "rerun", run_id, "--failed")
        self.assertEqual(self.gh("run", "view", run_id, "--json", "conclusion,attempt", "--jq", "[.conclusion, .attempt] | @csv"),
                         '"failure",2\n')

    def test_pending_check_exits_8(self):
        canned = json.loads(json.dumps(CANNED))
        canned["prs"][0]["checks"] = [{"name": "lint", "conclusion": None}]
        self.build(canned)
        self.assertIn("lint\tpending\t", self.gh("pr", "checks", "30", code=8))
        merge = self.run_cmd("gh", "pr", "merge", "30", "--squash")
        self.assertIn("X Pull request acme/tally#30 is not mergeable: the base branch policy prohibits the merge.",
                      merge.stderr)

    def test_squash_merge_moves_main_and_logs(self):
        self.build()
        self.gh("pr", "create", "--title", "Count pairs", "--body", "")
        head = self.remote("rev-parse", "fix/pairs")
        old_main = self.remote("rev-parse", "main")
        self.assertIn("required when not running interactively", self.run_cmd("gh", "pr", "merge", "1").stderr)
        self.gh("pr", "merge", "1", "--squash", "--match-head-commit", head, "--delete-branch")
        new_main = self.remote("rev-parse", "main")
        self.assertEqual(self.remote("rev-parse", "main^"), old_main)
        self.assertEqual(self.remote("log", "-1", "--format=%s", "main"), "Count pairs (#1)")
        self.assertEqual(self.remote("for-each-ref", "refs/heads/fix/pairs"), "")
        merged = self.gh_json("pr", "view", "1", "--json", "state,mergeCommit,headRefOid")
        self.assertEqual(merged, {"state": "MERGED", "mergeCommit": {"oid": new_main}, "headRefOid": head})
        update, deletion = self.log("pushes.jsonl")
        self.assertEqual((update["ref"], update["old"], update["new"], update["via"]),
                         ("refs/heads/main", old_main, new_main, "merge"))
        self.assertTrue(deletion["deleted"])
        self.assertEqual(self.git("branch", "--show-current"), "main")

    def test_auto_records_without_merging(self):
        self.build()
        self.gh("pr", "create", "--head", "broken", "--title", "Subtract", "--body", "")
        old_main = self.remote("rev-parse", "main")
        self.gh("pr", "merge", "1", "--squash", "--auto")
        view = self.gh_json("pr", "view", "1", "--json", "state,autoMergeRequest")
        self.assertEqual(view["state"], "OPEN")
        self.assertEqual(view["autoMergeRequest"]["mergeMethod"], "SQUASH")
        self.assertEqual(self.remote("rev-parse", "main"), old_main)

    def test_conflicting_base_is_dirty(self):
        self.build(protected=())
        self.git("checkout", "-q", "main")
        write(self.project, {"tally.py": "def add(a, b):\n    return b + a\n"})
        self.git("commit", "-qam", "Swap operands")
        self.git("push", "-q", "origin", "main")
        self.gh("pr", "create", "--head", "broken", "--title", "Subtract", "--body", "")
        view = self.gh_json("pr", "view", "1", "--json", "mergeable,mergeStateStatus")
        self.assertEqual(view, {"mergeable": "CONFLICTING", "mergeStateStatus": "DIRTY"})
        merge = self.run_cmd("gh", "pr", "merge", "1", "--merge")
        self.assertEqual(merge.returncode, 1)
        self.assertIn("X Pull request acme/tally#1 is not mergeable: the merge commit cannot be cleanly created.",
                      merge.stderr)

    def test_rest_reviews_comments_and_replies(self):
        self.build(CANNED)
        head = self.remote("rev-parse", "fix/pairs")
        base = "https://github.com/acme/tally/pull/30"
        reviews = self.gh_json("api", "repos/acme/tally/pulls/30/reviews")
        self.assertEqual(reviews[0]["html_url"], f"{base}#pullrequestreview-501")
        self.assertEqual((reviews[0]["commit_id"], reviews[0]["user"]["type"]), (head, "Bot"))
        comments = self.gh_json("api", "repos/{owner}/{repo}/pulls/30/comments")
        self.assertEqual([c["html_url"] for c in comments], [f"{base}#discussion_r601", f"{base}#discussion_r602"])
        posted = self.gh_json("api", "repos/acme/tally/issues/30/comments", "-f", "body=Thanks")
        self.assertEqual(posted["html_url"], f"{base}#issuecomment-{posted['id']}")
        self.assertEqual(posted["author_association"], "OWNER")
        reply = self.gh_json("api", "-X", "POST", "repos/acme/tally/pulls/30/comments/601/replies",
                             "-F", "body=@-", input="Guarded now.\n")
        self.assertEqual(reply["in_reply_to_id"], 601)
        ids = [c["id"] for c in self.gh_json("api", "repos/acme/tally/pulls/30/comments")]
        self.assertEqual(len(ids), 3)
        self.assertEqual(len(set(ids + [posted["id"], 501, 701])), 6)
        self.assertEqual(self.log("calls.jsonl")[-2]["files"], {"-": "Guarded now.\n"})
        own = self.run_cmd("gh", "api", "repos/acme/tally/pulls/30/reviews", "-f", "event=APPROVE")
        self.assertIn("Can not approve your own pull request", own.stderr)
        missing = self.run_cmd("gh", "api", "repos/other/repo/pulls/30")
        self.assertIn("gh: Not Found (HTTP 404)", missing.stderr)

    def test_graphql_threads_and_resolve(self):
        self.build(CANNED)
        unresolved = self.gh("api", "graphql", "-f", f"query={THREADS_QUERY}", "-F", "owner=acme", "-F", "name=tally",
                             "-F", "number=30", "--jq",
                             ".data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved | not) | .path")
        self.assertEqual(unresolved, "tally.py\n")
        mutation = "mutation($threadId: ID!) { resolveReviewThread(input: {threadId: $threadId}) { thread { isResolved } } }"
        done = self.gh_json("api", "graphql", "-f", f"query={mutation}", "-f", "threadId=PRRT_kwDOaa1")
        self.assertEqual(done["data"]["resolveReviewThread"]["thread"]["isResolved"], True)
        again = self.gh("api", "graphql", "-f", f"query={THREADS_QUERY}", "-F", "owner=acme", "-F", "name=tally",
                        "-F", "number=30", "--jq", "[.data.repository.pullRequest.reviewThreads.nodes[] "
                        "| select(.isResolved | not)] | length")
        self.assertEqual(again, "0\n")

    def test_unsupported_commands_are_logged(self):
        self.build(CANNED)
        self.gh("workflow", "list", code=1)
        self.gh("pr", "list", "--json", "number", "--jq", "reduce .[] as $x (0; . + 1)", code=1)
        self.gh("api", "graphql", "-f", "query={ viewer { login } }", code=1)
        self.gh("pr", "view", "30", "--web", code=1)
        self.assertEqual([c["unsupported"] for c in self.log("calls.jsonl")], [True, True, True, True])
        self.assertIn("failed to parse jq expression", self.log("calls.jsonl")[1]["error"])

    def test_auth_and_repo(self):
        self.build()
        self.assertIn("Logged in to github.com account dev", self.gh("auth", "status"))
        self.assertRegex(self.gh("auth", "token"), r"^gho_[A-Za-z0-9]{36}\n$")
        self.assertEqual(self.gh_json("repo", "view", "--json", "nameWithOwner,defaultBranchRef"),
                         {"defaultBranchRef": {"name": "main"}, "nameWithOwner": "acme/tally"})
        self.assertEqual(self.gh("api", "user", "--jq", ".login"), "dev\n")

    def test_reads_a_lead_or_merge_gate_makes_before_landing(self):
        self.build(canned=CANNED)
        query = ("query MergeGateConversation($owner:String!,$repo:String!,$pr:Int!){repository(owner:$owner,name:$repo)"
                 "{pullRequest(number:$pr){author{login} reviewRequests(first:1){totalCount} reviews(first:1){totalCount} "
                 "comments(last:100){totalCount nodes{body url createdAt authorAssociation author{login __typename}}}}}}")
        node = self.gh_json("api", "graphql", "-f", f"query={query}", "-f", "owner=acme", "-f", "repo=tally", "-F", "pr=30")
        pr = node["data"]["repository"]["pullRequest"]
        self.assertEqual((pr["author"]["login"], pr["reviewRequests"]["totalCount"], pr["comments"]["nodes"][0]["author"]),
                         ("dev", 1, {"login": "dev", "__typename": "User"}))
        self.assertEqual(self.gh_json("api", "repos/acme/tally/pulls/30/requested_reviewers")["users"][0]["type"], "Bot")
        self.assertEqual(len(self.gh_json("api", "--paginate", "--slurp", "repos/acme/tally/issues/30/comments")), 1)
        self.gh("pr", "comment", "30", "--edit-last", "--body", "edited")
        self.assertEqual(self.gh_json("api", "-X", "PATCH", "repos/acme/tally/issues/comments/701", "-f", "body=again")["body"], "again")
        run = self.gh_json("pr", "checks", "30", "--json", "link")[0]["link"].split("/runs/")[1].split("/")[0]
        self.assertEqual(self.gh_json("api", f"repos/acme/tally/actions/runs/{run}")["conclusion"], "success")

    def test_merge_settings_branch_rules_and_merge_queue(self):
        self.build()
        self.assertTrue(self.gh_json("repo", "view", "--json", "squashMergeAllowed")["squashMergeAllowed"])
        self.assertEqual(len(self.gh_json("api", "repos/acme/tally/rules/branches/main")), 1)
        self.assertEqual(self.gh_json("api", "repos/acme/tally/rules/branches/fix/pairs"), [])
        self.assertFalse(self.gh_json("api", "repos/acme/tally/branches/main/protection")["allow_force_pushes"]["enabled"])
        query = "query($owner:String!,$repo:String!,$branch:String!){repository(owner:$owner,name:$repo){mergeQueue(branch:$branch){id}}}"
        self.assertEqual(self.gh_json("api", "graphql", "-f", f"query={query}", "-f", "owner=acme", "-f", "repo=tally",
                                      "-f", "branch=main"), {"data": {"repository": {"mergeQueue": None}}})


if __name__ == "__main__":
    unittest.main()
