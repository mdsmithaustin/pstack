import importlib.util
import json
import shlex
import shutil
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "tools/check-personal-paths.py"
spec = importlib.util.spec_from_file_location("personal_paths", CHECKER)
personal_paths = importlib.util.module_from_spec(spec)
spec.loader.exec_module(personal_paths)


def home_path(kind, account):
    return "/" + kind + "/" + account


class PersonalPathsCLI(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.git("init", "-q")
        fixtures = {}
        for name, kind, account in personal_paths.EXCEPTIONS:
            fixtures.setdefault(name, []).append(home_path(kind, account) + "/fixture")
        for name, lines in fixtures.items():
            self.track(name, "\n".join(sorted(lines)))

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)

    def track(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode())
        self.git("add", "--", name)
        return path

    def scan(self, cwd=None, source="worktree", input=None):
        return subprocess.run([sys.executable, str(CHECKER), "--source", source], cwd=cwd or self.root,
                              env={**os.environ, "GIT_CEILING_DIRECTORIES": str(Path(cwd or self.root).parent)},
                              input=input, capture_output=True, text=True, timeout=10)

    def test_tracked_leak_fails_then_symbolic_homes_pass(self):
        account = "private-account-731"
        file = self.track("new-document.txt", "first line\n" + home_path("Users", account) + "/project\n")
        done = self.scan()
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertEqual(done.stdout, "new-document.txt:2: personal home path /Users/<redacted>\n")
        self.assertEqual(done.stderr, "")
        self.assertNotIn(account, done.stdout + done.stderr)
        file.write_text("$HOME/project\n~/project\n" + home_path("Users", "<account>") +
                        "/project\n" + home_path("home", "${USER}") + "/project\n" +
                        home_path("home", "$USER") + "/project\n" +
                        home_path("Users", "${ACCOUNT}") + "/project\n")
        done = self.scan()
        self.assertEqual((done.returncode, done.stdout, done.stderr),
                         (0, "PASS personal paths: checked 9 tracked text files\n", ""))

    def test_both_root_kinds_spaces_punctuation_and_terminal_roots_are_redacted(self):
        self.track("notes.txt", "(" + home_path("Users", "private person") + "/project), " +
                   home_path("home", "private-linux") + "\n")
        done = self.scan()
        self.assertEqual((done.returncode, done.stdout, done.stderr),
                         (1, "notes.txt:1: personal home path /Users/<redacted>\n"
                             "notes.txt:1: personal home path /home/<redacted>\n", ""))

    def test_untracked_text_is_checked_only_after_git_add(self):
        (self.root / "new.txt").write_text(home_path("home", "untracked-person"))
        before = self.scan()
        self.assertEqual((before.returncode, before.stdout),
                         (0, "PASS personal paths: checked 8 tracked text files\n"))
        self.git("add", "new.txt")
        after = self.scan()
        self.assertEqual((after.returncode, after.stdout),
                         (1, "new.txt:1: personal home path /home/<redacted>\n"))

    def test_fixture_exception_does_not_allow_another_file_or_account(self):
        self.track("copy.txt", home_path("Users", "someone") + "/project")
        with (self.root / "evals/promises/test_live.py").open("a") as file:
            file.write("\n" + home_path("Users", "private-new-person"))
        done = self.scan()
        self.assertEqual((done.returncode, done.stdout, done.stderr),
                         (1, "copy.txt:1: personal home path /Users/<redacted>\n"
                             "evals/promises/test_live.py:2: personal home path /Users/<redacted>\n", ""))

    def test_fixture_exception_requires_the_complete_account_component(self):
        name = "evals/promises/test_reduce_trace.py"
        accounts = (("home", "bob$"), ("home", "bob+"),
                    ("Users", "dev@company"), ("home", "dev="))
        with (self.root / name).open("a") as file:
            for kind, account in accounts:
                file.write("\n" + home_path(kind, account) + "/private-project")
        done = self.scan()
        self.assertEqual((done.returncode, done.stdout, done.stderr),
                         (1, "evals/promises/test_reduce_trace.py:6: personal home path /home/<redacted>\n"
                             "evals/promises/test_reduce_trace.py:7: personal home path /home/<redacted>\n"
                             "evals/promises/test_reduce_trace.py:8: personal home path /Users/<redacted>\n"
                             "evals/promises/test_reduce_trace.py:9: personal home path /home/<redacted>\n", ""))

    def test_filename_account_is_completely_redacted_in_findings(self):
        name = "notes" + home_path("Users", "person@personal-domain") + "/record.txt"
        self.track(name, home_path("home", "private-person") + "/project")
        done = self.scan()
        self.assertEqual((done.returncode, done.stdout, done.stderr),
                         (1, "notes/Users/<redacted>/record.txt:0: personal home path /Users/<redacted>\n"
                             "notes/Users/<redacted>/record.txt:1: personal home path /home/<redacted>\n", ""))

    def test_filename_account_is_completely_redacted_in_acquisition_errors(self):
        name = "notes" + home_path("Users", "person@personal-domain") + "/record.txt"
        file = self.track(name, "clean")
        file.unlink()
        done = self.scan()
        self.assertEqual((done.returncode, done.stdout, done.stderr),
                         (2, "", "ERROR: cannot inspect tracked file notes/Users/<redacted>/record.txt\n"))

    def test_unused_exception_is_an_acquisition_failure(self):
        (self.root / "PORTING.md").write_text("symbolic home only")
        done = self.scan()
        self.assertEqual((done.returncode, done.stdout, done.stderr),
                         (2, "", "ERROR: unused personal-path exception for PORTING.md\n"))

    def test_binary_is_skipped_and_non_utf8_text_still_detects_paths(self):
        self.track("binary.bin", b"\0" + home_path("Users", "binary-person").encode())
        done = self.scan()
        self.assertEqual((done.returncode, done.stdout),
                         (0, "PASS personal paths: checked 8 tracked text files\n"))
        self.track("legacy.txt", b"\xff\n" + home_path("home", "legacy-person").encode())
        done = self.scan()
        self.assertEqual((done.returncode, done.stdout, done.stderr),
                         (1, "legacy.txt:2: personal home path /home/<redacted>\n", ""))

    def test_symlink_target_spelling_is_checked_without_reading_external_content(self):
        with tempfile.TemporaryDirectory() as outside:
            external = Path(outside) / "external.txt"
            external.write_text(home_path("Users", "external-secret"))
            link = self.root / "linked.txt"
            link.symlink_to(os.path.relpath(external, self.root))
            self.git("add", "linked.txt")
            done = self.scan()
            self.assertEqual((done.returncode, done.stdout, done.stderr),
                             (0, "PASS personal paths: checked 9 tracked text files\n", ""))
            link.unlink()
            link.symlink_to(home_path("home", "linked-person") + "/missing")
            done = self.scan()
            self.assertEqual((done.returncode, done.stdout, done.stderr),
                             (1, "linked.txt:1: personal home path /home/<redacted>\n", ""))

    def test_missing_tracked_file_and_symlinked_parent_fail_without_external_reads(self):
        file = self.track("nested/file.txt", "clean")
        file.unlink()
        done = self.scan()
        self.assertEqual((done.returncode, done.stdout, done.stderr),
                         (2, "", "ERROR: cannot inspect tracked file nested/file.txt\n"))
        file.parent.rmdir()
        with tempfile.TemporaryDirectory() as outside:
            (Path(outside) / "file.txt").write_text(home_path("home", "external-secret"))
            (self.root / "nested").symlink_to(outside, target_is_directory=True)
            done = self.scan()
            self.assertEqual((done.returncode, done.stdout, done.stderr),
                             (2, "", "ERROR: cannot inspect tracked file nested/file.txt\n"))

    def test_missing_git_inventory_and_empty_inventory_fail_closed(self):
        with tempfile.TemporaryDirectory() as empty:
            missing = self.scan(cwd=empty)
            subprocess.run(["git", "init", "-q"], cwd=empty, check=True, capture_output=True)
            initialized = self.scan(cwd=empty)
        for done in (missing, initialized):
            self.assertEqual((done.returncode, done.stdout, done.stderr),
                             (2, "", "ERROR: cannot acquire a nonempty tracked-file inventory\n"))

    def commit(self):
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture" + "@" + "example.invalid",
                 "-c", "core.hooksPath=/dev/null", "commit", "-qm", "fixture")
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root,
                              check=True, capture_output=True, text=True).stdout.strip()

    def push_input(self, *tips):
        return "".join(f"refs/heads/local{i} {tip} refs/heads/remote{i} {'0' * 40}\n"
                       for i, tip in enumerate(tips))

    def test_index_scans_staged_bytes_despite_unstaged_edits(self):
        file = self.track("notes.txt", home_path("Users", "staged-secret"))
        file.write_text("clean")
        done = self.scan(source="index")
        self.assertEqual((done.returncode, done.stdout, done.stderr),
                         (1, "notes.txt:1: personal home path /Users/<redacted>\n", ""))
        self.git("add", "notes.txt")
        file.write_text(home_path("home", "unstaged-secret"))
        self.assertEqual(self.scan(source="index").returncode, 0)

    def test_push_scans_all_supplied_tips_and_ignores_deleted_refs_and_history(self):
        file = self.track("notes.txt", home_path("Users", "committed-secret"))
        leaking = self.commit()
        file.write_text("clean")
        self.git("add", "notes.txt")
        clean = self.commit()
        self.assertEqual(self.scan(source="pre-push", input=self.push_input(clean)).returncode, 0)
        done = self.scan(source="pre-push", input=self.push_input(clean, leaking, "0" * 40))
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn("notes.txt:1: personal home path /Users/<redacted>", done.stdout)
        self.assertNotIn("committed-secret", done.stdout + done.stderr)
        self.assertEqual(self.scan(source="pre-push", input=self.push_input("0" * 40)).returncode, 0)
        for invalid in ("not a push record\n", self.push_input("f" * 40)):
            self.assertEqual(self.scan(source="pre-push", input=invalid).returncode, 2)

    def test_index_allows_missing_fixtures_but_worktree_requires_used_exceptions(self):
        self.git("rm", "-r", "--cached", ".")
        self.track("clean.txt", "clean")
        done = self.scan(source="index")
        self.assertEqual((done.returncode, done.stdout, done.stderr),
                         (0, "PASS personal paths: checked 1 tracked text files\n", ""))
        self.track("PORTING.md", home_path("Users", "you") + "/fixture")
        done = self.scan(source="index")
        self.assertEqual((done.returncode, done.stdout, done.stderr),
                         (0, "PASS personal paths: checked 2 tracked text files\n", ""))
        done = self.scan()
        self.assertEqual(done.returncode, 2)
        self.assertIn("ERROR: unused personal-path exception", done.stderr)
        self.track("PORTING.md", home_path("Users", "you-private") + "/project")
        done = self.scan(source="index")
        self.assertEqual((done.returncode, done.stdout, done.stderr),
                         (1, "PORTING.md:1: personal home path /Users/<redacted>\n", ""))

    def test_push_allows_older_and_multiple_tips_with_missing_fixtures(self):
        self.git("rm", "-r", "--cached", ".")
        self.track("clean.txt", "clean")
        older = self.commit()
        self.track("PORTING.md", home_path("Users", "you") + "/fixture")
        partial = self.commit()
        for tips in ((older,), (older, partial)):
            done = self.scan(source="pre-push", input=self.push_input(*tips))
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(done.stderr, "")
            self.assertEqual(done.stdout.count("PASS personal paths:"), len(tips))
        self.track("PORTING.md", home_path("Users", "you-private") + "/project")
        leaking = self.commit()
        done = self.scan(source="pre-push", input=self.push_input(older, partial, leaking))
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn("PORTING.md:1: personal home path /Users/<redacted>", done.stdout)
        self.assertEqual(done.stderr, "")
        self.assertNotIn("you-private", done.stdout)

    def test_filename_paths_at_root_and_nested_are_checked_in_every_mode(self):
        for kind in ("Users", "home"):
            for prefix in ("", "nested/"):
                name = prefix + kind + "/filename-secret/record.bin"
                self.track(name, b"\0clean")
        tip = self.commit()
        for source in ("worktree", "index", "pre-push"):
            done = self.scan(source=source, input=self.push_input(tip))
            self.assertEqual(done.returncode, 1, done.stderr)
            self.assertEqual(done.stdout.count(":0: personal home path"), 4)
            self.assertNotIn("filename-secret", done.stdout + done.stderr)

    def test_root_filename_is_redacted_in_acquisition_and_exception_errors(self):
        for kind in ("Users", "home"):
            name = kind + "/diagnostic-secret/record.txt"
            file = self.track(name, "clean")
            file.unlink()
            done = self.scan()
            self.assertEqual(done.stderr,
                             f"ERROR: cannot inspect tracked file {kind}/<redacted>/record.txt\n")
            self.assertNotIn("diagnostic-secret", done.stdout + done.stderr)
            file.write_text("clean")
        original = personal_paths.EXCEPTIONS
        self.addCleanup(setattr, personal_paths, "EXCEPTIONS", original)
        import contextlib
        import io
        for kind in ("Users", "home"):
            personal_paths.EXCEPTIONS = {(f"{kind}/diagnostic-secret/record.txt", kind, "fixture")}
            errors = io.StringIO()
            with contextlib.redirect_stderr(errors):
                result = personal_paths.scan(os.fsencode(self.root), [("clean.txt", b"clean")])
            self.assertEqual(result, 2)
            self.assertEqual(errors.getvalue(),
                             f"ERROR: unused personal-path exception for {kind}/<redacted>/record.txt\n")

    def test_index_and_tip_scan_symlink_blobs_without_following_targets(self):
        link = self.root / "link"
        link.symlink_to(home_path("home", "symlink-secret") + "/missing")
        self.git("add", "link")
        tip = self.commit()
        link.unlink()
        link.symlink_to("clean")
        for source in ("index", "pre-push"):
            done = self.scan(source=source, input=self.push_input(tip))
            self.assertEqual((done.returncode, done.stdout, done.stderr),
                             (1, "link:1: personal home path /home/<redacted>\n", ""))

    @unittest.skipUnless(shutil.which("lefthook"), "native hook regression requires Lefthook")
    def test_native_hooks_use_index_and_forward_push_stdin(self):
        self.commit()
        config = json.loads((ROOT / "lefthook.yml").read_text(encoding="utf-8"))
        config["templates"]["python"] = shlex.quote(sys.executable)
        (self.root / "lefthook.yml").write_text(json.dumps(config))
        tools = self.root / "tools"
        tools.mkdir(exist_ok=True)
        (tools / "check-personal-paths.py").write_bytes(CHECKER.read_bytes())
        hooks = self.root / ".git/hooks"
        for hook in ("pre-commit", "pre-push"):
            path = hooks / hook
            path.write_text("#!/bin/sh\nexec lefthook run " + hook +
                            ' --command personal-paths --no-auto-install --force "$@"\n')
            path.chmod(0o755)
        file = self.track("notes.txt", home_path("Users", "native-secret"))
        file.write_text("clean")
        done = subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture" + "@" + "example.invalid",
                               "-c", "core.hooksPath=.git/hooks", "commit", "-qm", "blocked"], cwd=self.root, capture_output=True, text=True)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("notes.txt:1: personal home path /Users/<redacted>", done.stdout + done.stderr)
        leaking = self.commit()
        remote = self.root / "remote.git"
        self.git("init", "--bare", "-q", str(remote))
        self.git("remote", "add", "fixture", str(remote))
        def push(tip):
            return subprocess.run(["git", "-c", "core.hooksPath=.git/hooks", "push", "fixture", f"{tip}:refs/heads/result"],
                                  cwd=self.root, capture_output=True, text=True, timeout=30)
        done = push(leaking)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("notes.txt:1: personal home path /Users/<redacted>", done.stdout + done.stderr)
        self.assertNotIn("native-secret", done.stdout + done.stderr)
        self.git("add", "notes.txt")
        clean = self.commit()
        file.write_text(home_path("home", "unstaged-secret"))
        done = push(clean)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        published = subprocess.run(["git", "--git-dir", str(remote), "rev-parse", "refs/heads/result"],
                                   check=True, capture_output=True, text=True).stdout.strip()
        self.assertEqual(published, clean)


class GateInterpreter(unittest.TestCase):
    def test_explicit_home_relative_and_uv_interpreter_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True)
            log = root / "runner.log"
            home = root / "home"
            native = home / ".local/share/mise/installs/python/3.14.7/bin/python3.14"
            override = root / "override"
            uv = root / "bin/uv"
            for path, name in ((native, "native"), (override, "override"), (uv, "uv")):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('#!/bin/sh\nprintf "%s\\n" "' + name + ' $*" >> "$RUNNER_LOG"\n')
                path.chmod(0o755)
            env = {**os.environ, "HOME": str(home), "RUNNER_LOG": str(log),
                   "PATH": str(uv.parent) + ":/usr/bin:/bin"}
            env.pop("PSTACK_GATE_PYTHON", None)
            for expected, current in (("override", {**env, "PSTACK_GATE_PYTHON": str(override)}),
                                      ("native", env), ("uv", env)):
                if expected == "uv":
                    native.unlink()
                log.unlink(missing_ok=True)
                done = subprocess.run(["/bin/bash", str(ROOT / "tools/gate-check.sh"), "lint"],
                                      cwd=root, env=current, capture_output=True, text=True, timeout=10)
                self.assertEqual(done.returncode, 0, done.stderr)
                lines = log.read_text().splitlines()
                self.assertEqual(len(lines), 8)
                self.assertTrue(all(line.startswith(expected + " ") for line in lines), lines)
                self.assertIn("tools/check-personal-paths.py", "\n".join(lines))


if __name__ == "__main__":
    unittest.main()
