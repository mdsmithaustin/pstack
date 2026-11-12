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
NAME_ONLY = "; not shown: git prints only the name of this conflicted file)"
ISOLATED = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
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
}
COMMITTED = {"committed.md": "+committed"}
WITHOUT_RENAMES = {"old.md": "deleted file mode 100644", "sub/new.md": "new file mode 100644"}
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
        ["git", "-C", repo, *IDENTITY, *args], env={**os.environ, **ISOLATED}, check=check, capture_output=True,
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
        env={**os.environ, **ISOLATED}, check=True, capture_output=True,
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
    return repo


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
            env={**os.environ, **ISOLATED, "TMPDIR": tmp or self.tmp, **(env or {})},
            stdin=subprocess.DEVNULL, stdout=stdout, stderr=subprocess.PIPE, check=False,
        )

    def new_tmp(self):
        return tempfile.mkdtemp(dir=self.root)

    def assert_saved(self, done, expected, covers=WORKING_TREE, lines=True):
        self.assertEqual(done.returncode, 0, done.stderr)
        first, *rows, last = done.stdout.decode().splitlines()
        count, hidden, said, index = LAST_LINE.fullmatch(last).groups()
        directory = os.path.dirname(index)
        self.addCleanup(shutil.rmtree, directory)
        self.assertEqual(first, f"index {index}")
        self.assertEqual(Path(index).read_bytes(), done.stdout.split(b"\n", 1)[1])
        self.assertEqual((int(count), said), (len(expected), covers))
        self.assertEqual(int(hidden), sum("not shown: " in name for name in expected))
        saved = {}
        for row in rows:
            size, path, _status, name = row.split(" ", 3)
            saved[name] = Path(path).read_bytes()
            self.assertEqual(os.path.dirname(path), directory)
            self.assertEqual(int(size), len(saved[name]), name)
        self.assertEqual(sorted(saved), sorted(expected))
        self.assertEqual(len(rows), len(expected))
        self.assertEqual(len(os.listdir(directory)), len(expected) + 1)
        self.assertNotIn(os.path.realpath(self.repo), os.path.realpath(directory))
        for name, line_start in expected.items():
            self.assertNotIn(b"\x1b", saved[name], name)
            if lines:
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

    def test_inherited_git_configuration_hides_no_file(self):
        for name, settings in INHERITED.items():
            for cwd in (self.repo, os.path.join(self.repo, "sub")):
                with self.subTest(configuration=name, cwd=cwd):
                    self.assert_saved(self.run_step("HEAD", cwd, env=inherited(settings)), TRACKED | UNTRACKED)
        with self.subTest(configuration="GIT_EXTERNAL_DIFF"):
            done = self.run_step("HEAD", self.repo, env={"GIT_EXTERNAL_DIFF": "false"})
            self.assert_saved(done, TRACKED | UNTRACKED)

    def test_rename_detection_settings_change_the_listing_and_lose_no_line(self):
        without = {name: line_start for name, line_start in TRACKED.items() if "->" not in name} | WITHOUT_RENAMES
        done = self.run_step("HEAD", self.repo, env=inherited({"diff.renames": "false"}))
        self.assert_saved(done, without | UNTRACKED)
        done = self.run_step("HEAD", self.repo, env=inherited({"diff.renames": "copies"}))
        copies = {name: line_start for name, line_start in TRACKED.items() if name != "copied.md"} | UNTRACKED
        saved = self.assert_saved(done, copies | {"source.md -> copied.md": "+copy"})
        self.assertIn("copy from source.md", saved["source.md -> copied.md"].decode().splitlines())

    def test_text_conversion_driver_output_is_saved_for_every_file(self):
        attributes = os.path.join(self.root, "attributes")
        Path(attributes).write_text("*.md diff=upper\n", encoding="utf-8")
        settings = {"core.attributesFile": attributes, "diff.upper.textconv": "tr a-z A-Z <"}
        done = self.run_step("HEAD", self.repo, env=inherited(settings))
        saved = self.assert_saved(done, TRACKED | UNTRACKED, lines=False)
        self.assertIn("+ACCENT", saved["café.md"].decode().splitlines())

    def test_ranges_without_the_working_tree_leave_untracked_files_out(self):
        for spec in ("main...HEAD", "main HEAD", "main..HEAD", "--merge-base main HEAD"):
            with self.subTest(spec=spec):
                done = self.run_step(spec, os.path.join(self.repo, "sub"))
                self.assert_saved(done, COMMITTED, covers="commits only")
        staged = STAGED | {"old.md -> sub/new.md": "rename from old.md", "copied.md": "+copy"}
        for spec in ("--cached", "--staged HEAD"):
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
        cases = {
            "bad ref": ("no-such-ref", self.repo, 1),
            "outside a repository": ("HEAD", self.root, 1),
            "path limit": ("HEAD -- sub", self.repo, 2),
            "unchanged path without the separator": ("HEAD .gitignore", self.repo, 1),
            "output option": ("--stat HEAD", self.repo, 2),
            "whitespace option": ("-w HEAD", self.repo, 2),
        }
        for name, (spec, cwd, status) in cases.items():
            with self.subTest(case=name):
                tmp = self.new_tmp()
                self.assert_refused(self.run_step(spec, cwd, tmp=tmp), tmp, status)

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

    def test_conflicted_file_has_one_row_that_says_unmerged(self):
        for operation in ("merge", "rebase"):
            repo = new_repository(os.path.join(self.root, f"conflict-{operation}"))
            for name in ("both.md", "theirs-deleted.md", "plain.md"):
                write(repo, name, "".join(f"{name} {line}\n" for line in range(30)))
            commit_all(repo, "base")
            git(repo, "checkout", "-q", "-b", "other")
            append(repo, "both.md", "theirs")
            git(repo, "rm", "-q", "theirs-deleted.md")
            commit_all(repo, "theirs")
            git(repo, "checkout", "-q", "main")
            write(repo, "both.md", "early-edit\n" + "".join(f"both.md {line}\n" for line in range(1, 30)))
            commit_all(repo, "early")
            append(repo, "both.md", "ours")
            append(repo, "theirs-deleted.md", "ours")
            commit_all(repo, "ours")
            git(repo, operation, "other", check=False)
            append(repo, "plain.md", "later")
            both, deleted = "both.md (unmerged)", "theirs-deleted.md (unmerged)"
            name_only = {deleted[:-1] + NAME_ONLY: "* Unmerged path "}
            head_has_the_file = operation == "merge"
            ranges = {
                "": ({both: "++<<<<<<< ", "plain.md (not staged)": "+later"} | name_only, UNCOMMITTED),
                "--cached": ({both: "++<<<<<<< "} | name_only, "staged only"),
                "HEAD": (
                    {both: "+<<<<<<< ", "plain.md": "+later"}
                    | (name_only if head_has_the_file else {deleted: "new file mode"}),
                    WORKING_TREE,
                ),
                "main~2": ({both: "+early-edit", deleted: "+ours", "plain.md": "+later"}, WORKING_TREE),
                "--merge-base other": (
                    {both: "+early-edit", deleted: "+ours" if head_has_the_file else "new file mode", "plain.md": "+later"},
                    WORKING_TREE,
                ),
                "main~1 main": ({"both.md": "+ours", "theirs-deleted.md": "+ours"}, "commits only"),
            }
            for spec, (expected, covers) in ranges.items():
                with self.subTest(operation=operation, spec=spec):
                    saved = self.assert_saved(self.run_step(spec, repo), expected, covers=covers)
                    if covers == WORKING_TREE:
                        against_revision = subprocess.run(
                            ["git", "-C", repo, "diff", *spec.split(), "--", "both.md"],
                            env={**os.environ, **ISOLATED}, check=True, capture_output=True,
                        ).stdout
                        self.assertEqual(saved[both], against_revision)
                        self.assertIn(b"+<<<<<<< ", saved[both])
            self.assertEqual(rows_that_git_status_lists(repo), {name.replace(NAME_ONLY, ")") for name in ranges[""][0]})

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

    def test_temporary_directory_inside_the_checkout_is_refused(self):
        tmp = os.path.join(self.repo, "tmp-inside")
        os.mkdir(tmp)
        self.addCleanup(os.rmdir, tmp)
        done = self.run_step("HEAD", self.repo, tmp=tmp)
        self.assert_refused(done, tmp)
        self.assertIn(b"TMPDIR", done.stderr)

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
