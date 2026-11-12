import collections
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "skills/pstack-harness/references/shell-and-processes.md"
SECTION = re.compile(r"^## Read a diff\n(.*?)(?=^## )", re.M | re.S)
FENCE = re.compile(r"^[ \t]*```sh\n(.*?)^[ \t]*```", re.M | re.S)
LAST_LINE = re.compile(r"(\d+) rows saved, (\d+) not shown; covers (.+); index (.+)")
NOT_SHOWN = " (not shown: git treats it as binary)"
UNCOMMITTED = "staged, unstaged and untracked"
WORKING_TREE = "working tree and untracked"
ISOLATED = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
CLEAN = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")} | ISOLATED
BASE = [
    "café.md", 'say"hi".md', "tab\there.md", "a space.md", ":!magic.md", "*.md", "-dash.md", "new\nline.md",
    "deep/er/path.md", "gone.md", "type.md", "mode.sh", "staged.md",
]
STAGED = {"staged.md": "+staged", "gone.md": "-base", "empty-added.txt": "new file mode 100644"}
TRACKED = STAGED | {
    "café.md": "+accent",
    'say"hi".md': "+quote",
    "tab\\there.md": "+tab",
    "a space.md": "+space",
    ":!magic.md": "+magic",
    "*.md": "+star",
    "-dash.md": "+dash",
    "new\\nline.md": "+newline",
    "deep/er/path.md": "+deep",
    "old.md -> sub/new.md": "rename from old.md",
    "source.md": "+source",
    "copied.md": "+copy",
    "type.md": "new file mode 120000",
    "mode.sh": "new mode 100755",
    "bin.dat" + NOT_SHOWN: "Binary files ",
    "mod": "-Subproject commit",
}
UNTRACKED = {
    'untracked "q"\\tü.md': "+untracked",
    "sub/empty.txt": "new file mode 100644",
    "-": "+lone dash",
    "link": "new file mode 120000",
    "cr\\rdel\\x7f.md": "+control",
    "fresh/directory/file.md": "+fresh",
}
COMMITTED = {"committed.md": "+committed"}
SHELLS = {
    "bash": ["", "set -euo pipefail; "],
    "zsh": ["", "set -euo pipefail; ", "setopt no_extended_glob sh_word_split; ", "setopt extended_glob; "],
    "sh": ["", "set -eu; "],
    "dash": ["", "set -eu; "],
}
INHERITED = {
    "diff.relative": {"diff.relative": "true"},
    "diff.noprefix": {"diff.noprefix": "true"},
    "diff.mnemonicPrefix": {"diff.mnemonicPrefix": "true"},
    "diff.external": {"diff.external": "false"},
    "core.quotePath=false": {"core.quotePath": "false"},
    "core.quotePath=true": {"core.quotePath": "true"},
    "color.ui": {"color.ui": "always", "color.diff": "always"},
    "status.showUntrackedFiles": {"status.showUntrackedFiles": "no"},
    "diff.ignoreSubmodules": {"diff.ignoreSubmodules": "all"},
    "diff.submodule": {"diff.submodule": "log"},
    "diff.renames=false": {"diff.renames": "false"},
    "diff.renames=copies": {"diff.renames": "copies"},
    "index.sparse": {"index.sparse": "true"},
}


def step_command(spec):
    section = SECTION.search(REFERENCE.read_text(encoding="utf-8"))
    block = FENCE.search(section.group(1)) if section else None
    if block is None:
        return None
    return block.group(1).replace("<installed skills root>", str(ROOT / "skills")).replace("<range>", spec)


IDENTITY = ["-c", "user.name=t", "-c", "user.email=test.invalid", "-c", "protocol.file.allow=always"]


def git(repo, *args, check=True):
    done = subprocess.run(
        ["git", "-C", repo, *IDENTITY, *args], env=CLEAN, check=check, capture_output=True,
    )
    return done.stdout.decode().strip()


def write(repo, name, content):
    Path(repo, name).write_bytes(content.encode() if isinstance(content, str) else content)


def with_note(expected, note):
    return {
        name.replace(" (", f" ({note}; ") if name.endswith(NOT_SHOWN) else f"{name} ({note})": line_start
        for name, line_start in expected.items()
    }


def rows_that_git_status_lists(repo):
    done = subprocess.run(
        ["git", "-C", repo, "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        env=CLEAN, check=True, capture_output=True,
    )
    fields = done.stdout.decode().split("\0")[:-1]
    rows = set()
    while fields:
        state, name = fields[0][:2], fields.pop(0)[3:]
        renamed_from = fields.pop(0) + " -> " if state[0] in "RC" else ""
        if state == "??":
            rows.add(name)
        elif "U" in state or state in ("AA", "DD"):
            rows.add(f"{name} (unmerged)")
        else:
            if state[0] != " ":
                rows.add(f"{renamed_from}{name} (staged)")
            if state[1] != " ":
                rows.add(f"{name} (not staged)")
    return rows


def append(repo, name, line):
    with open(os.path.join(repo, name), "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def commit_all(repo, message):
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", message)


def new_repository(repo):
    os.makedirs(repo)
    git(repo, "init", "-q", "-b", "main")
    return repo


def scratch_repository(root):
    module = new_repository(os.path.join(root, "module"))
    append(module, "inner.md", "one")
    commit_all(module, "one")
    repo = new_repository(os.path.join(root, "repo"))
    os.makedirs(os.path.join(repo, "deep/er"))
    os.mkdir(os.path.join(repo, "sub"))
    for name in BASE:
        append(repo, name, "base")
    for name in ("old.md", "source.md"):
        Path(repo, name).write_text("".join(f"{name} {i}\n" for i in range(40)), encoding="utf-8")
    Path(repo, "bin.dat").write_bytes(b"\0\1\2")
    Path(repo, ".gitignore").write_text("*.log\n", encoding="utf-8")
    git(repo, "submodule", "add", "-q", module, "mod")
    commit_all(repo, "base")
    git(repo, "checkout", "-q", "-b", "work")
    append(repo, "committed.md", "committed")
    commit_all(repo, "committed")

    for name, line_start in TRACKED.items():
        if line_start.startswith("+") and name not in ("copied.md", "source.md"):
            append(repo, name.replace("\\t", "\t").replace("\\n", "\n"), line_start[1:])
    git(repo, "mv", "old.md", "sub/new.md")
    append(repo, "sub/new.md", "renamed")
    shutil.copy(os.path.join(repo, "source.md"), os.path.join(repo, "copied.md"))
    append(repo, "source.md", "source")
    append(repo, "copied.md", "copy")
    Path(repo, "empty-added.txt").write_text("", encoding="utf-8")
    git(repo, "add", "copied.md", "empty-added.txt", "staged.md")
    git(repo, "rm", "-q", "gone.md")
    os.remove(os.path.join(repo, "type.md"))
    os.symlink("a space.md", os.path.join(repo, "type.md"))
    os.chmod(os.path.join(repo, "mode.sh"), 0o755)
    Path(repo, "bin.dat").write_bytes(b"\0\3\4")
    append(os.path.join(repo, "mod"), "inner.md", "two")
    commit_all(os.path.join(repo, "mod"), "two")

    Path(repo, 'untracked "q"\tü.md').write_text("untracked\n", encoding="utf-8")
    Path(repo, "sub/empty.txt").write_text("", encoding="utf-8")
    Path(repo, "-").write_text("lone dash\n", encoding="utf-8")
    os.symlink("nowhere", os.path.join(repo, "link"))
    Path(repo, "ignored.log").write_text("ignored\n", encoding="utf-8")
    Path(repo, "cr\rdel\x7f.md").write_text("control\n", encoding="utf-8")
    os.makedirs(os.path.join(repo, "fresh/directory"))
    Path(repo, "fresh/directory/file.md").write_text("fresh\n", encoding="utf-8")
    Path(repo, ".git/info/exclude").write_text("ignored-by-info-exclude\n", encoding="utf-8")
    Path(repo, "ignored-by-info-exclude").write_text("ignored\n", encoding="utf-8")
    return repo


ROW_NAME = re.compile(r"(?:(?P<old>.+) -> )?(?P<new>.+?)(?: \((?P<notes>.+)\))?")
BOTH_MODIFIED = ["bm-markers.md", "bm-ours.md", "bm-theirs.md", "bm-hand.md", "bm-removed.md"]
INCOMING_SIDE = {"merge": "theirs", "rebase": "ours", "cherry-pick": "theirs", "stash pop": "ours"}


def git_bytes(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], env=CLEAN, check=True, capture_output=True).stdout


def numbered(name, count=40):
    return "".join(f"{name} {line}\n" for line in range(count))


def replace_line(repo, name, number, text):
    lines = Path(repo, name).read_text(encoding="utf-8").splitlines()
    lines[number] = text
    write(repo, name, "\n".join(lines) + "\n")


def repository_with_every_unmerged_state(root, operation):
    module = new_repository(os.path.join(root, "module"))
    append(module, "inner.md", "one")
    commit_all(module, "one")
    tips = {}
    for side in ("ours", "theirs"):
        git(module, "checkout", "-q", "-b", side, "main")
        append(module, f"{side}.md", side)
        commit_all(module, side)
        tips[side] = git(module, "rev-parse", "HEAD")
    git(module, "checkout", "-q", "main")

    repo = new_repository(os.path.join(root, "repo"))
    os.mkdir(os.path.join(repo, "sub"))
    tracked = ["ours-deleted.md", "theirs-deleted.md", "rename-both.md", "rename-delete.md", "rename-add.md",
               "sub/clean-theirs.md", "local.md", "star-local.md"]
    for name in BOTH_MODIFIED + tracked:
        write(repo, name, numbered(name))
    write(repo, "image.bin", b"\0\1\2start")
    git(repo, "submodule", "add", "-q", module, "mod")
    commit_all(repo, "start")
    git(repo, "tag", "start")

    def theirs():
        for name in BOTH_MODIFIED:
            replace_line(repo, name, 5, f"theirs clean hunk {name}")
            replace_line(repo, name, 35, f"theirs conflict {name}")
        os.remove(os.path.join(repo, "theirs-deleted.md"))
        replace_line(repo, "ours-deleted.md", 3, "theirs kept it")
        write(repo, "both-added.md", numbered("theirs-added", 6))
        write(repo, "star*.md", numbered("theirs-star", 6))
        git(repo, "mv", "rename-both.md", "rename-theirs.md")
        os.remove(os.path.join(repo, "rename-delete.md"))
        write(repo, "rename-add-new.md", numbered("theirs-new", 6))
        replace_line(repo, "sub/clean-theirs.md", 7, "theirs only")
        write(repo, "theirs-new.md", "theirs new file\n")
        write(repo, "image.bin", b"\0\1\2theirs")
        git(os.path.join(repo, "mod"), "checkout", "-q", tips["theirs"])

    def ours():
        for name in BOTH_MODIFIED:
            replace_line(repo, name, 12, f"ours clean hunk {name}")
            replace_line(repo, name, 35, f"ours conflict {name}")
        replace_line(repo, "theirs-deleted.md", 3, "ours kept it")
        os.remove(os.path.join(repo, "ours-deleted.md"))
        write(repo, "both-added.md", numbered("ours-added", 6))
        write(repo, "star*.md", numbered("ours-star", 6))
        git(repo, "mv", "rename-both.md", "rename-ours.md")
        git(repo, "mv", "rename-delete.md", "rename-kept.md")
        replace_line(repo, "rename-kept.md", 2, "ours edit in the renamed file")
        git(repo, "mv", "rename-add.md", "rename-add-new.md")
        write(repo, "image.bin", b"\0\1\2ours")
        git(os.path.join(repo, "mod"), "checkout", "-q", tips["ours"])

    git(repo, "checkout", "-q", "-b", "other")
    theirs()
    commit_all(repo, "theirs")
    git(repo, "checkout", "-q", "main")
    git(repo, "submodule", "update", "-q")
    for name in BOTH_MODIFIED:
        replace_line(repo, name, 20, f"early edit {name}")
    commit_all(repo, "early")
    ours()
    if operation == "stash pop":
        git(repo, "add", "-A")
        git(repo, "stash", "-q")
        theirs()
        commit_all(repo, "theirs on main")
    else:
        commit_all(repo, "ours")
    git(repo, *operation.split(), *([] if operation == "stash pop" else ["other"]), check=False)

    git(repo, "checkout", "--ours", "bm-ours.md")
    git(repo, "checkout", "--theirs", "bm-theirs.md")
    write(repo, "bm-hand.md", numbered("resolved by hand"))
    os.remove(os.path.join(repo, "bm-removed.md"))
    for name in ("local.md", "star-local.md"):
        replace_line(repo, name, 4, "local edit after the conflict")
    write(repo, "untracked.md", "untracked\n")
    return repo


def blob(repo, mode, sha):
    return mode, b"Subproject commit %s\n" % sha if mode == b"160000" else git_bytes(repo, "cat-file", "blob", sha)


def tree_side(repo, revision):
    side = {}
    for entry in git_bytes(repo, "ls-tree", "-r", "-z", revision).split(b"\0")[:-1]:
        (mode, _kind, sha), name = entry.split(b"\t")[0].split(), entry.split(b"\t")[1]
        side[name.decode()] = blob(repo, mode, sha)
    return side


def index_side(repo):
    side = {}
    for entry in git_bytes(repo, "ls-files", "-s", "-z").split(b"\0")[:-1]:
        (mode, sha, stage), name = entry.split(b"\t")[0].split(), entry.split(b"\t")[1]
        if stage == b"0":
            side[name.decode()] = blob(repo, mode, sha)
    return side


def working_tree_side(repo):
    side = {}
    for directory, directories, files in os.walk(repo):
        if directory == repo:
            directories.remove(".git")
        elif ".git" in files:
            name = os.path.relpath(directory, repo)
            side[name] = blob(repo, b"160000", git_bytes(directory, "rev-parse", "HEAD").strip())
            directories.clear()
            continue
        for file in files:
            found = os.path.join(directory, file)
            mode = b"100755" if os.access(found, os.X_OK) else b"100644"
            side[os.path.relpath(found, repo)] = (mode, Path(found).read_bytes())
    return side


def inherited(settings):
    env = {"GIT_CONFIG_COUNT": str(len(settings))}
    for index, (key, value) in enumerate(settings.items()):
        env[f"GIT_CONFIG_KEY_{index}"] = key
        env[f"GIT_CONFIG_VALUE_{index}"] = value
    return env


class ReadADiff(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp()
        cls.addClassCleanup(shutil.rmtree, cls.root)
        cls.tmp = os.path.join(cls.root, "tmp")
        os.mkdir(cls.tmp)
        cls.repo = scratch_repository(cls.root)

    def run_step(self, spec, cwd, shell="bash", prefix="", env=None, tmp=None, suffix="", stdout=subprocess.PIPE):
        command = step_command(spec)
        self.assertIsNotNone(command, "Read a diff needs one fenced sh command")
        return subprocess.run(
            [shell, "-c", prefix + command.rstrip("\n") + suffix], cwd=cwd,
            env={**CLEAN, "TMPDIR": tmp or self.tmp, **(env or {})},
            stdin=subprocess.DEVNULL, stdout=stdout, stderr=subprocess.PIPE, check=False,
        )

    def new_tmp(self):
        return tempfile.mkdtemp(dir=self.root)

    def saved_rows(self, done, covers):
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stderr, b"")
        first, *rows, last = done.stdout.decode().splitlines()
        count, hidden, said, index = LAST_LINE.fullmatch(last).groups()
        directory = os.path.dirname(index)
        self.addCleanup(shutil.rmtree, directory)
        self.assertEqual(first, f"index {index}")
        self.assertEqual(Path(index).read_bytes(), done.stdout.split(b"\n", 1)[1])
        self.assertEqual(said, covers)
        saved = {}
        for row in rows:
            size, path, _status, name = row.split(" ", 3)
            saved[name] = Path(path).read_bytes()
            self.assertEqual(os.path.dirname(path), directory)
            self.assertEqual(int(size), len(saved[name]), name)
            self.assertNotIn(b"\x1b", saved[name], name)
            self.assertFalse(saved[name].startswith((b"diff --cc ", b"diff --combined ")), name)
        self.assertEqual(int(count), len(rows))
        self.assertEqual(len(saved), len(rows))
        self.assertEqual(int(hidden), sum("not shown: " in name for name in saved))
        self.assertEqual(len(os.listdir(directory)), len(rows) + 1)
        self.assertNotIn(Path(os.path.realpath(self.repo)), Path(os.path.realpath(directory)).parents)
        return saved

    def assert_saved(self, done, expected, covers=WORKING_TREE, lines=True):
        saved = self.saved_rows(done, covers)
        self.assertEqual(sorted(saved), sorted(expected))
        if lines:
            for name, line_start in expected.items():
                found = saved[name].decode(errors="replace").splitlines()
                self.assertTrue(any(line.startswith(line_start) for line in found), name)
        return saved

    def assert_refused(self, done, tmp, status=1):
        self.assertEqual(done.returncode, status, done.stdout)
        self.assertNotIn(b"rows saved", done.stdout or b"")
        self.assertTrue(done.stderr.strip())
        self.assertNotIn(b"Traceback", done.stderr)
        self.assertEqual(os.listdir(tmp), [])

    def test_every_shell_and_option_saves_every_file_from_a_subdirectory(self):
        for shell, prefixes in SHELLS.items():
            for prefix in prefixes:
                with self.subTest(shell=shell, prefix=prefix):
                    if shutil.which(shell) is None:
                        self.skipTest(f"{shell} is not installed")
                    done = self.run_step("HEAD", os.path.join(self.repo, "sub"), shell, prefix)
                    saved = self.assert_saved(done, TRACKED | UNTRACKED)
                    renamed = saved["old.md -> sub/new.md"].decode().splitlines()
                    added = [line for line in renamed if line.startswith("+") and not line.startswith("+++")]
                    self.assertEqual(added, ["+renamed"])
                    for name in ("*.md", ":!magic.md", "-dash.md"):
                        self.assertEqual(saved[name].count(b"diff --git "), 1, name)

    def test_each_inherited_setting_leaves_every_saved_file_byte_equal(self):
        sub = os.path.join(self.repo, "sub")
        clean = self.assert_saved(self.run_step("HEAD", sub), TRACKED | UNTRACKED)
        for name, settings in INHERITED.items():
            with self.subTest(configuration=name):
                done = self.run_step("HEAD", sub, env=inherited(settings))
                self.assertEqual(self.saved_rows(done, WORKING_TREE), clean)
        variables = ["GIT_EXTERNAL_DIFF", "GIT_LITERAL_PATHSPECS", "GIT_GLOB_PATHSPECS", "GIT_NOGLOB_PATHSPECS",
                     "GIT_ICASE_PATHSPECS"]
        for variable in variables:
            with self.subTest(variable=variable):
                done = self.run_step("HEAD", sub, env={variable: "false" if variable == "GIT_EXTERNAL_DIFF" else "1"})
                self.assertEqual(self.saved_rows(done, WORKING_TREE), clean)

    def test_hostile_global_file_and_environment_leave_every_saved_file_byte_equal(self):
        hostile = {key: value for settings in INHERITED.values() for key, value in settings.items()}
        global_file = os.path.join(self.root, "hostile.gitconfig")
        git(self.root, "config", "--file", global_file, "core.pager", "false")
        for key, value in hostile.items():
            git(self.root, "config", "--file", global_file, key, value)
        sources = {
            "global file": {"GIT_CONFIG_GLOBAL": global_file},
            "environment": inherited(hostile) | {
                "GIT_EXTERNAL_DIFF": "false", "GIT_PAGER": "false", "GIT_LITERAL_PATHSPECS": "1",
                "GIT_ICASE_PATHSPECS": "1",
            },
        }
        ranges = {
            "": UNCOMMITTED, "--cached": "staged only", "HEAD": WORKING_TREE, "main": WORKING_TREE,
            "--merge-base main": WORKING_TREE, "main...HEAD": "commits only", "main HEAD": "commits only",
        }
        for spec, covers in ranges.items():
            clean = self.saved_rows(self.run_step(spec, self.repo), covers)
            for source, env in sources.items():
                with self.subTest(spec=spec, source=source):
                    self.assertEqual(self.saved_rows(self.run_step(spec, self.repo, env=env), covers), clean)

    def test_text_conversion_driver_output_is_saved_for_every_file(self):
        attributes = os.path.join(self.root, "attributes")
        Path(attributes).write_text("*.md diff=upper\n", encoding="utf-8")
        settings = {"core.attributesFile": attributes, "diff.upper.textconv": "tr a-z A-Z <"}
        done = self.run_step("HEAD", self.repo, env=inherited(settings))
        saved = self.assert_saved(done, TRACKED | UNTRACKED, lines=False)
        self.assertIn("+ACCENT", saved["café.md"].decode().splitlines())

    def test_ranges_without_the_working_tree_leave_untracked_files_out(self):
        for spec in ("main...HEAD", "main HEAD", "main..HEAD", "main..", "--merge-base main HEAD"):
            with self.subTest(spec=spec):
                done = self.run_step(spec, os.path.join(self.repo, "sub"))
                self.assert_saved(done, COMMITTED, covers="commits only")
        staged = STAGED | {"old.md -> sub/new.md": "rename from old.md", "copied.md": "+copy"}
        for spec in ("--cached", "--staged HEAD", "--cached --merge-base HEAD"):
            with self.subTest(spec=spec):
                saved = self.assert_saved(self.run_step(spec, self.repo), staged, covers="staged only")
                self.assertNotIn("+renamed", saved["old.md -> sub/new.md"].decode().splitlines())

    def test_ranges_with_the_working_tree_include_untracked_files(self):
        unstaged = {
            name: line_start for name, line_start in TRACKED.items()
            if name not in STAGED and name != "copied.md" and "->" not in name
        }
        staged = STAGED | {"old.md -> sub/new.md": "rename from old.md", "copied.md": "+copy"}
        expected = with_note(staged, "staged") | with_note(unstaged | {"sub/new.md": "+renamed"}, "not staged")
        self.assert_saved(self.run_step("", self.repo), expected | UNTRACKED, covers=UNCOMMITTED)
        self.assert_saved(self.run_step("--merge-base main", self.repo), TRACKED | COMMITTED | UNTRACKED)

    def test_empty_range_says_zero_files(self):
        self.assert_saved(self.run_step("HEAD HEAD", self.repo), {}, covers="commits only")

    def test_failures_are_loud(self):
        write(self.repo, "odd^{tree}", "a file whose name ends like a peeled revision\n")
        self.addCleanup(os.remove, os.path.join(self.repo, "odd^{tree}"))
        cases = {
            "bad ref": ("no-such-ref", self.repo, 1),
            "outside a repository": ("HEAD", self.root, 1),
            "path limit": ("HEAD -- sub", self.repo, 2),
            "path limit with no revision": ("-- sub", self.repo, 2),
            "unchanged path without the separator": ("HEAD .gitignore", self.repo, 1),
            "changed path without the separator": ("HEAD staged.md", self.repo, 1),
            "path alone": ("sub", self.repo, 1),
            "word that is a file name once the script peels it": ("odd", self.repo, 1),
            "word that names two commits": ("'HEAD^!'", self.repo, 1),
            "blob": ("HEAD:staged.md", self.repo, 1),
            "blob by its object name": (git(self.repo, "rev-parse", "HEAD:staged.md"), self.repo, 1),
            "bad ref in a range": ("main...no-such-ref", self.repo, 1),
            "output option": ("--stat HEAD", self.repo, 2),
            "whitespace option": ("-w HEAD", self.repo, 2),
            "three revisions": ("main work HEAD", self.repo, 2),
            "range next to a revision": ("main..work HEAD", self.repo, 2),
            "range with --merge-base": ("--merge-base main...HEAD", self.repo, 2),
            "range with --cached": ("--cached main..HEAD", self.repo, 2),
            "two revisions with --cached": ("--cached main HEAD", self.repo, 2),
            "--merge-base alone": ("--merge-base", self.repo, 2),
            "--merge-base with --cached and no revision": ("--cached --merge-base", self.repo, 2),
        }
        for name, (spec, cwd, status) in cases.items():
            with self.subTest(case=name):
                tmp = self.new_tmp()
                done = self.run_step(spec, cwd, tmp=tmp)
                self.assert_refused(done, tmp, status)
                *from_git, last = done.stderr.splitlines()
                self.assertTrue(last.startswith(b"save-diff.py: error: "), done.stderr)
                if name == "outside a repository":
                    self.assertEqual(len(from_git), 1, done.stderr)
                    continue
                self.assertEqual(from_git, [])
                self.assertIn(b"is not a range" if status == 2 else b"does not name one commit or tree", last)

    def test_git_failure_after_the_checks_ends_the_run(self):
        attributes = os.path.join(self.root, "failing-attributes")
        Path(attributes).write_text("*.md diff=broken\n", encoding="utf-8")
        settings = {"core.attributesFile": attributes, "diff.broken.textconv": "false"}
        tmp = self.new_tmp()
        done = self.run_step("HEAD", self.repo, env=inherited(settings), tmp=tmp)
        self.assert_refused(done, tmp)
        self.assertIn(b"save-diff.py: error: git exited ", done.stderr.splitlines()[-1])

    def test_second_word_that_is_a_path_and_a_branch_is_read_as_a_revision(self):
        git(self.repo, "branch", "sub", "main")
        self.addCleanup(git, self.repo, "branch", "-D", "sub")
        saved = self.assert_saved(self.run_step("HEAD sub", self.repo), {"committed.md": "-committed"},
                                  covers="commits only")
        self.assertEqual(saved["committed.md"], git_bytes(self.repo, "diff", "HEAD", "sub", "--"))

    def test_nested_repository_fails_with_a_zero_byte_line_and_keeps_nothing(self):
        nested = new_repository(os.path.join(self.repo, "nested"))
        self.addCleanup(shutil.rmtree, nested)
        tmp = self.new_tmp()
        done = self.run_step("HEAD", self.repo, tmp=tmp)
        self.assertEqual(done.returncode, 1)
        count = len(TRACKED | UNTRACKED) + 1
        self.assertEqual(done.stdout.decode().splitlines(), [
            "0 - ?? nested/ (not saved: a directory with its own repository)",
            f"FAILED: 1 of {count} rows not saved. The script removed its directory.",
        ])
        self.assertEqual(os.listdir(tmp), [])

    def test_git_directory_from_the_environment_and_a_linked_worktree(self):
        env = {"GIT_DIR": os.path.join(self.repo, ".git"), "GIT_WORK_TREE": self.repo}
        self.assert_saved(self.run_step("HEAD", self.root, env=env), TRACKED | UNTRACKED)
        relative = {"GIT_DIR": "../.git", "GIT_WORK_TREE": ".."}
        self.assert_saved(self.run_step("HEAD", os.path.join(self.repo, "sub"), env=relative), TRACKED | UNTRACKED)
        self.assert_saved(self.run_step("HEAD", self.repo, env={"GIT_DIR": ".git"}), TRACKED | UNTRACKED)
        linked = os.path.join(self.root, "linked")
        git(self.repo, "worktree", "add", "-q", linked, "main")
        self.addCleanup(git, self.repo, "worktree", "remove", "--force", linked)
        append(linked, "café.md", "accent")
        append(linked, "new here.md", "untracked")
        expected = {"café.md": "+accent", "new here.md": "+untracked"}
        self.assert_saved(self.run_step("HEAD", os.path.join(linked, "deep")), expected)

    def test_every_conflict_state_is_saved_whole_or_marked_for_every_range(self):
        for operation, incoming in INCOMING_SIDE.items():
            repo = repository_with_every_unmerged_state(os.path.join(self.root, "conflict " + operation), operation)
            states = {row[:2] for row in git_bytes(repo, "status", "--porcelain=v1").decode().splitlines()}
            self.assertLessEqual({"UU", "AA", "DU", "UD", "DD", "AU", "UA"}, states, operation)
            unmerged = sorted({
                entry.split(b"\t")[1].decode() for entry in git_bytes(repo, "ls-files", "-u", "-z").split(b"\0")[:-1]
            })
            self.assertLessEqual({"mod", "image.bin", "star*.md"}, set(unmerged))
            head, working_tree = tree_side(repo, "HEAD"), working_tree_side(repo)
            fork = {base: tree_side(repo, git(repo, "merge-base", base, "HEAD")) for base in ("other", "start")}
            ranges = {
                "": (head, working_tree, UNCOMMITTED),
                "--cached": (head, index_side(repo), "staged only"),
                "HEAD": (head, working_tree, WORKING_TREE),
                "start": (tree_side(repo, "start"), working_tree, WORKING_TREE),
                "--merge-base other": (fork["other"], working_tree, WORKING_TREE),
                "start...HEAD": (fork["start"], head, "commits only"),
                "start HEAD": (tree_side(repo, "start"), head, "commits only"),
            }
            for spec, (before, after, covers) in ranges.items():
                with self.subTest(operation=operation, spec=spec):
                    saved = self.saved_rows(self.run_step(spec, os.path.join(repo, "sub")), covers)
                    rows = {name: ROW_NAME.fullmatch(name) for name in saved}
                    if covers == "commits only":
                        self.assertFalse([name for name in saved if "unmerged" in name])
                    else:
                        for path in unmerged:
                            mine = [name for name, row in rows.items() if row["new"] == path]
                            self.assertEqual(len(mine), 1, path)
                            self.assertIn("unmerged", rows[mine[0]]["notes"])
                            revision = spec.split() or ["HEAD"]
                            against = git_bytes(repo, "diff", *revision, "--", ":(literal)" + path)
                            self.assertEqual(saved[mine[0]], against or b"* Unmerged path %s\n" % path.encode(), path)
                            if spec == "--cached":
                                self.assertIn("not shown: ", mine[0])
                        after = after | dict.fromkeys(unmerged) if spec == "--cached" else after
                    if covers in (UNCOMMITTED, WORKING_TREE):
                        clean_hunk = b"+%s clean hunk " % incoming.encode()
                        for name in ("bm-markers.md", "bm-theirs.md"):
                            self.assertIn(clean_hunk + name.encode(), saved[f"{name} (unmerged)"].splitlines())
                    self.assert_every_changed_line_is_saved(before, after, saved)
                    if spec == "":
                        self.assertEqual({re.sub(r"; not shown: [^)]+", "", name) for name in saved},
                                         rows_that_git_status_lists(repo))

    def assert_every_changed_line_is_saved(self, before, after, saved):
        rows = [(ROW_NAME.fullmatch(name), content.splitlines()) for name, content in saved.items()]
        for path in sorted(before.keys() | after.keys()):
            if before.get(path) == after.get(path):
                continue
            mine = [(row, lines) for row, lines in rows if path in (row["old"], row["new"])]
            self.assertTrue(mine, f"{path} changed and has no row")
            if any("not shown: " in (row["notes"] or "") for row, _lines in mine):
                continue
            if all(row["new"] != path for row, _lines in mine):
                continue
            source = next((row["old"] for row, _lines in mine if row["old"]), path)
            old, new = (collections.Counter(side.get(name, (None, b""))[1].splitlines())
                        for side, name in ((before, source), (after, path)))
            for sign, needed in ((b"+", new - old), (b"-", old - new)):
                header = sign * 3 + b" "
                found = collections.Counter(
                    line[1:] for _row, lines in mine for line in lines
                    if line.startswith(sign) and not line.startswith(header)
                )
                self.assertFalse(needed - found, f"{path}: lines with {sign.decode()} that no saved file holds")

    def test_name_that_is_not_utf8_is_saved_from_two_commits(self):
        repo = new_repository(os.path.join(self.root, "bytes"))
        append(repo, "plain.md", "base")
        commit_all(repo, "base")
        blob = git(repo, "hash-object", "-w", "plain.md")
        git(repo, "update-index", "--add", "--cacheinfo", f"100644,{blob},".encode() + b"caf\xe9.md")
        tree = git(repo, "write-tree")
        head = git(repo, "commit-tree", tree, "-p", "HEAD", "-m", "bytes")
        done = self.run_step(f"HEAD {head}", repo)
        self.assertEqual(done.returncode, 0, done.stderr)
        _first, row, last = done.stdout.splitlines()
        self.addCleanup(shutil.rmtree, os.path.dirname(LAST_LINE.fullmatch(last.decode()).group(4)))
        self.assertTrue(row.endswith(b" A caf\xe9.md"), row)
        self.assertIn(b"+base", Path(os.fsdecode(row.split(b" ", 3)[1])).read_bytes().splitlines())

    def test_names_that_differ_only_in_case_each_get_their_own_patch(self):
        repo = new_repository(os.path.join(self.root, "case"))
        append(repo, "plain.md", "base")
        commit_all(repo, "base")
        for name in ("Twin.md", "twin.md"):
            write(repo, "content", f"{name}\n")
            blob = git(repo, "hash-object", "-w", "content")
            git(repo, "update-index", "--add", "--cacheinfo", f"100644,{blob},{name}")
        head = git(repo, "commit-tree", git(repo, "write-tree"), "-p", "HEAD", "-m", "twins")
        for env in ({}, {"GIT_ICASE_PATHSPECS": "1"}):
            with self.subTest(env=env):
                done = self.run_step(f"HEAD {head}", repo, env=env)
                saved = self.assert_saved(done, {"Twin.md": "+Twin.md", "twin.md": "+twin.md"}, covers="commits only")
                self.assertEqual([content.count(b"diff --git ") for content in saved.values()], [1, 1])

    def test_name_with_a_tab_and_name_with_a_backslash_and_t_get_distinct_rows(self):
        repo = new_repository(os.path.join(self.root, "backslash"))
        append(repo, "plain.md", "base")
        commit_all(repo, "base")
        write(repo, "tab\there.dat", "real tab\n")
        write(repo, "tab\\there.dat", "backslash and t\n")
        write(repo, "tab\\\\there.dat", "two backslashes and t\n")
        expected = {
            "tab\\there.dat": "+real tab",
            "tab\\\\there.dat": "+backslash and t",
            "tab\\\\\\\\there.dat": "+two backslashes and t",
        }
        self.assert_saved(self.run_step("HEAD", repo), expected)

    def test_no_range_saves_every_staged_unstaged_and_untracked_file_that_git_status_lists(self):
        repo = new_repository(os.path.join(self.root, "uncommitted"))
        for name in ("a", "b", "partly.md", "moved.md", "restored.md"):
            write(repo, name, "".join(f"{name} {line}\n" for line in range(20)))
        commit_all(repo, "base")
        append(repo, "a", "s")
        git(repo, "add", "a")
        append(repo, "b", "u")
        append(repo, "partly.md", "first")
        git(repo, "add", "partly.md")
        append(repo, "partly.md", "second")
        git(repo, "mv", "moved.md", "moved-here.md")
        append(repo, "moved-here.md", "after")
        append(repo, "restored.md", "undone")
        git(repo, "add", "restored.md")
        write(repo, "restored.md", "".join(f"restored.md {line}\n" for line in range(20)))
        append(repo, "added-then-deleted.md", "gone")
        git(repo, "add", "added-then-deleted.md")
        os.remove(os.path.join(repo, "added-then-deleted.md"))
        append(repo, "new.md", "untracked")
        expected = {
            "a (staged)": "+s",
            "b (not staged)": "+u",
            "partly.md (staged)": "+first",
            "partly.md (not staged)": "+second",
            "moved.md -> moved-here.md (staged)": "rename from moved.md",
            "moved-here.md (not staged)": "+after",
            "restored.md (staged)": "+undone",
            "restored.md (not staged)": "-undone",
            "added-then-deleted.md (staged)": "+gone",
            "added-then-deleted.md (not staged)": "-gone",
            "new.md": "+untracked",
        }
        self.assertEqual(rows_that_git_status_lists(repo), set(expected))
        for cwd in (repo, self.root):
            with self.subTest(cwd=cwd):
                env = {} if cwd == repo else {"GIT_DIR": os.path.join(repo, ".git"), "GIT_WORK_TREE": repo}
                self.assert_saved(self.run_step("", cwd, env=env), expected, covers=UNCOMMITTED)

    def test_no_range_works_before_the_first_commit(self):
        repo = new_repository(os.path.join(self.root, "unborn"))
        append(repo, "staged.md", "s")
        git(repo, "add", "staged.md")
        append(repo, "new.md", "untracked")
        expected = {"staged.md (staged)": "+s", "new.md": "+untracked"}
        self.assertEqual(rows_that_git_status_lists(repo), set(expected))
        self.assert_saved(self.run_step("", repo), expected, covers=UNCOMMITTED)

    def test_index_file_holds_every_row_when_the_printed_rows_are_cut(self):
        repo = new_repository(os.path.join(self.root, "many"))
        append(repo, "base.md", "base")
        commit_all(repo, "base")
        expected = {f"file-{number:03}.md": f"+{number}" for number in range(300)}
        for name, line_start in expected.items():
            append(repo, name, line_start[1:])
        done = self.run_step("", repo)
        self.assert_saved(done, expected, covers=UNCOMMITTED)
        first_line_only = done.stdout.decode().splitlines()[0]
        *rows, last = Path(first_line_only.removeprefix("index ")).read_text(encoding="utf-8").splitlines()
        self.assertEqual(int(LAST_LINE.fullmatch(last).group(1)), 300)
        self.assertEqual(sorted(row.split(" ", 3)[3] for row in rows), sorted(expected))
        self.assertTrue(all(os.path.getsize(row.split(" ", 3)[1]) == int(row.split(" ", 1)[0]) for row in rows))

    def test_content_that_git_does_not_show_is_marked_on_its_row_and_counted(self):
        repo = new_repository(os.path.join(self.root, "hidden"))
        write(repo, ".gitattributes", "yarn.lock -diff\nvendored.js binary\n")
        for name in ("yarn.lock", "vendored.js", "plain.md"):
            write(repo, name, f"{name} one\n")
        write(repo, "wide.txt", "one\n".encode("utf-16"))
        write(repo, "image.bin", b"\0\1\2")
        commit_all(repo, "base")
        for name in ("yarn.lock", "vendored.js", "plain.md"):
            append(repo, name, "lock-secret-line")
        write(repo, "wide.txt", "one\ntwo\n".encode("utf-16"))
        write(repo, "image.bin", b"\0\3\4")
        write(repo, "new-wide.txt", "untracked\n".encode("utf-16"))
        tracked = {name + NOT_SHOWN: "Binary files " for name in ("yarn.lock", "vendored.js", "wide.txt", "image.bin")}
        tracked["plain.md"] = "+lock-secret-line"
        untracked = {"new-wide.txt" + NOT_SHOWN: "Binary files "}
        saved = self.assert_saved(self.run_step("HEAD", repo), tracked | untracked)
        for name, content in saved.items():
            self.assertEqual(b"lock-secret-line" in content, name == "plain.md", name)
            self.assertNotIn(b"\0", content, name)
        expected = with_note(tracked, "not staged") | untracked
        self.assert_saved(self.run_step("", repo), expected, covers=UNCOMMITTED)
        commit_all(repo, "change")
        self.assert_saved(self.run_step("HEAD~1 HEAD", repo), tracked | untracked, covers="commits only")

    def test_untracked_symbolic_link_is_saved_as_a_link_and_never_followed(self):
        outside = os.path.join(self.root, "outside")
        os.mkdir(outside)
        write(outside, "secret.txt", "content-outside-the-repository\n")
        repo = new_repository(os.path.join(self.root, "links"))
        os.mkdir(os.path.join(repo, "directory"))
        write(repo, "directory/inside.md", "content-inside-the-directory\n")
        commit_all(repo, "base")
        targets = {
            "to-directory": "directory",
            "to-file": "directory/inside.md",
            "dangling": "nowhere",
            "to-outside-file": os.path.join(outside, "secret.txt"),
            "to-outside-directory": outside,
            "to-root": "/",
        }
        for name, target in targets.items():
            os.symlink(target, os.path.join(repo, name))
        objects_before = git(repo, "count-objects", "-v")
        saved = self.assert_saved(self.run_step("", repo), {name: f"+{target}" for name, target in targets.items()},
                                  covers=UNCOMMITTED)
        for name, content in saved.items():
            self.assertIn(b"new file mode 120000", content, name)
            self.assertNotIn(b"content-", content, name)
        self.assertEqual(git(repo, "count-objects", "-v"), objects_before)
        self.assertEqual(git(repo, "status", "--porcelain=v1"), "\n".join(f"?? {name}" for name in sorted(targets)))

    def test_run_leaves_the_git_directory_as_it_was_with_a_split_index(self):
        repo = new_repository(os.path.join(self.root, "split-index"))
        append(repo, "tracked.md", "base")
        commit_all(repo, "base")
        git(repo, "config", "core.splitIndex", "true")
        append(repo, "tracked.md", "staged")
        git(repo, "add", "tracked.md")
        append(repo, "tracked.md", "unstaged")
        append(repo, "new.md", "untracked")
        os.symlink("tracked.md", os.path.join(repo, "link"))

        def git_directory():
            found = Path(repo, ".git").rglob("*")
            return {str(path): path.read_bytes() for path in found if path.is_file()}

        before = git_directory()
        for spec in ("", "HEAD"):
            with self.subTest(spec=spec):
                done = self.run_step(spec, repo)
                self.assertEqual(done.returncode, 0, done.stderr)
                self.addCleanup(shutil.rmtree, os.path.dirname(done.stdout.decode().splitlines()[0][len("index "):]))
                self.assertIn(" ?? new.md\n", done.stdout.decode())
                self.assertEqual(git_directory(), before)

    def test_untracked_file_outside_a_sparse_checkout_is_saved(self):
        repo = new_repository(os.path.join(self.root, "sparse"))
        os.mkdir(os.path.join(repo, "kept"))
        os.mkdir(os.path.join(repo, "left-out"))
        write(repo, "kept/a.md", "a\n")
        write(repo, "left-out/b.md", "b\n")
        commit_all(repo, "base")
        git(repo, "sparse-checkout", "set", "--cone", "kept")
        os.makedirs(os.path.join(repo, "left-out"), exist_ok=True)
        write(repo, "left-out/new.md", "untracked\n")
        self.assert_saved(self.run_step("", repo), {"left-out/new.md": "+untracked"}, covers=UNCOMMITTED)
        git(repo, "sparse-checkout", "init", "--cone", "--sparse-index")
        write(repo, "kept/new.md", "inside\n")
        self.assertEqual(git(repo, "config", "index.sparse"), "true")
        append(repo, "kept/a.md", "staged")
        git(repo, "add", "kept/a.md")
        append(repo, "kept/a.md", "unstaged")
        untracked = {"kept/new.md": "+inside", "left-out/new.md": "+untracked"}
        expected = {"kept/a.md (staged)": "+staged", "kept/a.md (not staged)": "+unstaged"} | untracked
        self.assert_saved(self.run_step("", repo), expected, covers=UNCOMMITTED)
        self.assert_saved(self.run_step("HEAD", repo), {"kept/a.md": "+staged"} | untracked)

    def test_temporary_directory_inside_the_checkout_is_refused(self):
        for tmp in (os.path.join(self.repo, "tmp-inside"), os.path.join(self.repo, "sub", "tmp-inside")):
            with self.subTest(tmp=tmp):
                os.mkdir(tmp)
                self.addCleanup(os.rmdir, tmp)
                done = self.run_step("HEAD", self.repo, tmp=tmp)
                self.assert_refused(done, tmp)
                self.assertIn(b"TMPDIR", done.stderr)

    def test_temporary_directory_beside_the_checkout_with_its_name_as_a_prefix_is_used(self):
        tmp = self.repo + "-tmp"
        os.mkdir(tmp)
        done = self.run_step("HEAD", self.repo, tmp=tmp)
        self.assert_saved(done, TRACKED | UNTRACKED)
        self.assertTrue(done.stdout.startswith(b"index " + tmp.encode() + b"/"))

    def test_output_that_cannot_be_written_leaves_one_error_line_and_no_directory(self):
        tmp = self.new_tmp()
        done = self.run_step("HEAD", self.repo, tmp=tmp, suffix=" >&-")
        self.assert_refused(done, tmp)
        self.assertEqual(len(done.stderr.splitlines()), 1, done.stderr)

        read_end, write_end = os.pipe()
        os.close(read_end)
        self.addCleanup(os.close, write_end)
        done = self.run_step("HEAD", self.repo, tmp=tmp, stdout=write_end)
        self.assert_refused(done, tmp)
        self.assertEqual(len(done.stderr.splitlines()), 1, done.stderr)

        if os.path.exists("/dev/full"):
            done = self.run_step("HEAD", self.repo, tmp=tmp, suffix=" >/dev/full")
            self.assert_refused(done, tmp)
            self.assertEqual(len(done.stderr.splitlines()), 1, done.stderr)


if __name__ == "__main__":
    unittest.main()
