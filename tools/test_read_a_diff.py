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
LAST_LINE = re.compile(r"(\d+) files (changed or untracked|changed), (\d+) saved in (.+)")
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
    "bin.dat": "Binary files ",
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
    "core.pager": {"core.pager": "false", "pager.diff": "true"},
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
    done = subprocess.run(["git", "-C", repo, *IDENTITY, *args], check=check, capture_output=True)
    return done.stdout.decode().strip()


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

    def run_step(self, spec, cwd, shell="bash", prefix="", env=None):
        command = step_command(spec)
        self.assertIsNotNone(command, "Read a diff needs one fenced sh command")
        return subprocess.run(
            [shell, "-c", prefix + command], cwd=cwd, env={**os.environ, "TMPDIR": self.tmp, **(env or {})},
            stdin=subprocess.DEVNULL, capture_output=True, check=False,
        )

    def assert_saved(self, done, expected, scope="changed or untracked", lines=True):
        self.assertEqual(done.returncode, 0, done.stderr)
        *rows, last = done.stdout.decode().splitlines()
        count, said, saved_count, directory = LAST_LINE.fullmatch(last).groups()
        self.addCleanup(shutil.rmtree, directory)
        self.assertEqual((int(count), int(saved_count), said), (len(expected), len(expected), scope))
        saved = {}
        for row in rows:
            size, path, _status, name = row.split(" ", 3)
            saved[name] = Path(path).read_bytes()
            self.assertEqual(os.path.dirname(path), directory)
            self.assertEqual(int(size), len(saved[name]), name)
        self.assertEqual(sorted(saved), sorted(expected))
        self.assertEqual(len(os.listdir(directory)), len(expected))
        self.assertNotIn(os.path.realpath(self.repo), os.path.realpath(directory))
        for name, line_start in expected.items():
            self.assertNotIn(b"\x1b", saved[name], name)
            if lines:
                self.assertTrue(any(found.startswith(line_start) for found in saved[name].decode().splitlines()), name)
        return saved

    def assert_refused(self, done, status=1):
        self.assertEqual(done.returncode, status, done.stdout)
        self.assertNotIn(b"saved in", done.stdout)
        self.assertTrue(done.stderr.strip())

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
                self.assert_saved(self.run_step(spec, os.path.join(self.repo, "sub")), COMMITTED, scope="changed")
        staged = STAGED | {"old.md -> sub/new.md": "rename from old.md", "copied.md": "+copy"}
        for spec in ("--cached", "--staged HEAD"):
            with self.subTest(spec=spec):
                saved = self.assert_saved(self.run_step(spec, self.repo), staged, scope="changed")
                self.assertNotIn("+renamed", saved["old.md -> sub/new.md"].decode().splitlines())

    def test_ranges_with_the_working_tree_include_untracked_files(self):
        unstaged = {
            name: line_start for name, line_start in TRACKED.items()
            if name not in STAGED and name != "copied.md" and "->" not in name
        }
        self.assert_saved(self.run_step("", self.repo), unstaged | {"sub/new.md": "+renamed"} | UNTRACKED)
        self.assert_saved(self.run_step("--merge-base main", self.repo), TRACKED | COMMITTED | UNTRACKED)

    def test_empty_range_says_zero_files(self):
        self.assert_saved(self.run_step("HEAD HEAD", self.repo), {}, scope="changed")

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
                self.assert_refused(self.run_step(spec, cwd), status)

    def test_nested_repository_fails_with_a_zero_byte_line(self):
        nested = new_repository(os.path.join(self.repo, "nested"))
        self.addCleanup(shutil.rmtree, nested)
        done = self.run_step("HEAD", self.repo)
        self.assertEqual(done.returncode, 1)
        *rows, last = done.stdout.decode().splitlines()
        self.addCleanup(shutil.rmtree, last.rsplit(" ", 1)[1])
        self.assertIn("0 - ?? nested/ (not saved: a directory with its own repository)", rows)
        self.assertTrue(last.startswith(f"FAILED: 1 of {len(TRACKED | UNTRACKED) + 1} files not saved"), last)

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

    def test_unmerged_file_is_saved(self):
        repo = new_repository(os.path.join(self.root, "conflict"))
        append(repo, "both.md", "base")
        commit_all(repo, "base")
        git(repo, "checkout", "-q", "-b", "other")
        append(repo, "both.md", "theirs")
        commit_all(repo, "theirs")
        git(repo, "checkout", "-q", "main")
        append(repo, "both.md", "ours")
        commit_all(repo, "ours")
        git(repo, "merge", "-q", "other", check=False)
        for spec in ("", "HEAD"):
            with self.subTest(spec=spec):
                done = self.run_step(spec, repo)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                *rows, last = done.stdout.decode().splitlines()
                directory = LAST_LINE.fullmatch(last).group(4)
                self.addCleanup(shutil.rmtree, directory)
                self.assertEqual(int(LAST_LINE.fullmatch(last).group(1)), len(rows))
                saved = [row.split(" ", 3)[1] for row in rows if row.endswith(" both.md")]
                texts = [Path(path).read_text(encoding="utf-8") for path in saved]
                self.assertTrue(any("theirs" in text for text in texts), rows)

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
        row, last = done.stdout.splitlines()
        self.addCleanup(shutil.rmtree, LAST_LINE.fullmatch(last.decode()).group(4))
        self.assertTrue(row.endswith(b" A caf\xe9.md"), row)
        self.assertIn(b"+base", Path(os.fsdecode(row.split(b" ", 3)[1])).read_bytes().splitlines())


if __name__ == "__main__":
    unittest.main()
