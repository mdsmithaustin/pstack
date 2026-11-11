import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REFERENCE = Path(__file__).resolve().parents[1] / "skills/pstack-harness/references/shell-and-processes.md"
SECTION = re.compile(r"^## Read a diff\n(.*?)(?=^## )", re.M | re.S)
FENCE = re.compile(r"^[ \t]*```sh\n(.*?)^[ \t]*```", re.M | re.S)
TRACKED = {
    "café.md": "+accent",
    'say"hi".md': "+quote",
    "tab\there.md": "+tab",
    "a space.md": "+space",
    ":!magic.md": "+magic",
    "*.md": "+star",
    "gone.md": "-base",
    "sub/new.md": "+41",
}
UNTRACKED = {'untracked "q"\tü.md': "+untracked", "sub/empty.txt": "new file mode 100644"}


def printed_command():
    section = SECTION.search(REFERENCE.read_text(encoding="utf-8"))
    block = FENCE.search(section.group(1)) if section else None
    return block.group(1) if block else None


def git(repo, *args):
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True)


def scratch_repository(root):
    repo = os.path.join(root, "repo")
    os.makedirs(os.path.join(repo, "sub"))
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "test.invalid")
    git(repo, "config", "user.name", "t")
    for name in ("café.md", 'say"hi".md', "tab\there.md", "a space.md", ":!magic.md", "*.md", "gone.md"):
        Path(repo, name).write_text("base\n", encoding="utf-8")
    Path(repo, "old.md").write_text("".join(f"{i}\n" for i in range(1, 41)), encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    for name, line in TRACKED.items():
        if line.startswith("+") and name != "sub/new.md":
            with open(os.path.join(repo, name), "a", encoding="utf-8") as handle:
                handle.write(line[1:] + "\n")
    git(repo, "mv", "old.md", "sub/new.md")
    with open(os.path.join(repo, "sub/new.md"), "a", encoding="utf-8") as handle:
        handle.write("41\n")
    git(repo, "rm", "-q", "gone.md")
    Path(repo, 'untracked "q"\tü.md').write_text("untracked\n", encoding="utf-8")
    Path(repo, "sub/empty.txt").write_text("", encoding="utf-8")
    return repo


def saved_diffs(shell, command, repo, tmp):
    done = subprocess.run(
        [shell, "-c", command], cwd=os.path.join(repo, "sub"), env={**os.environ, "TMPDIR": tmp},
        capture_output=True, text=True, check=False,
    )
    rows = [line.split(None, 3) for line in done.stdout.splitlines()]
    pieces = {name: (int(size), Path(saved).read_text(encoding="utf-8")) for size, saved, _status, name in rows}
    for saved_dir in {Path(saved).parent for _size, saved, _status, _name in rows}:
        shutil.rmtree(saved_dir)
    return pieces


class ReadADiff(unittest.TestCase):
    def test_printed_command_saves_every_changed_and_untracked_file_whole(self):
        command = printed_command()
        self.assertIsNotNone(command, "Read a diff needs one fenced sh command")
        command = command.replace("<range>", "HEAD")
        for shell in ("bash", "zsh"):
            with self.subTest(shell=shell), tempfile.TemporaryDirectory() as root:
                if shutil.which(shell) is None:
                    self.skipTest(f"{shell} is not installed")
                tmp = os.path.join(root, "tmp")
                os.mkdir(tmp)
                pieces = saved_diffs(shell, command, scratch_repository(root), tmp)
                self.assertEqual(sorted(pieces), sorted(TRACKED | UNTRACKED))
                for name, expected in (TRACKED | UNTRACKED).items():
                    size, text = pieces[name]
                    self.assertGreater(size, 0, name)
                    self.assertEqual(text.count("diff --git "), 1, name)
                    self.assertIn(expected, text.splitlines(), name)
                renamed = pieces["sub/new.md"][1].splitlines()
                self.assertIn("rename from old.md", renamed)
                self.assertEqual([line for line in renamed if line.startswith("+") and not line.startswith("+++")], ["+41"])


if __name__ == "__main__":
    unittest.main()
