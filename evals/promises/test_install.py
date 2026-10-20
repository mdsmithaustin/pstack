import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import install
from harnesses import claude_code


def passing(ctx, harness):
    return install.Outcome({"ok": True})


def failing(ctx, harness):
    return install.Outcome({"ok": False}, ["not installed"])


def undecided(ctx, harness):
    raise install.Inconclusive("network down")


class ExitStatus(unittest.TestCase):
    def run_main(self, *fns):
        checks = tuple(install.Check(f"p{i}", ("codex",), fn) for i, fn in enumerate(fns))
        with tempfile.TemporaryDirectory(prefix="pstack-install-test-") as tmp:
            ctx = SimpleNamespace(work=Path(tmp) / "work", skills_version="1")
            err = io.StringIO()
            with mock.patch.object(install, "CHECKS", checks), mock.patch.object(install, "Context", return_value=ctx), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                code = install.main(["--harness", "codex", "--out", tmp])
            results = json.loads((Path(tmp) / "install.json").read_text())
        return code, results, err.getvalue()

    def test_a_check_that_crashes_exits_nonzero(self):
        def broken(ctx, harness):
            raise NameError("name 'listing' is not defined")
        code, results, err = self.run_main(passing, broken)
        self.assertEqual([r["verdict"] for r in results], ["PASS", "INCONCLUSIVE"])
        self.assertEqual(code, 2)
        self.assertIn("1 check error", err)

    def test_a_failed_promise_exits_nonzero(self):
        code, results, err = self.run_main(passing, failing)
        self.assertEqual([r["verdict"] for r in results], ["PASS", "FAIL"])
        self.assertEqual(code, 1)
        self.assertIn("1 FAIL", err)

    def test_inconclusive_alone_exits_zero_and_says_so(self):
        code, results, err = self.run_main(passing, undecided)
        self.assertEqual([r["verdict"] for r in results], ["PASS", "INCONCLUSIVE"])
        self.assertEqual(code, 0)
        self.assertIn("1 INCONCLUSIVE", err)
        self.assertNotIn("check error", err)

    def test_all_pass_exits_zero(self):
        code, _, err = self.run_main(passing)
        self.assertEqual(code, 0)
        self.assertIn("1 PASS", err)


class ClaudeList(unittest.TestCase):
    INIT = '{"type":"system","subtype":"init","skills":["a"],"slash_commands":["a"],"agents":[],"claude_code_version":"2.1.400"}'

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name).resolve()
        versions = self.home / ".local/share/claude/versions"
        launcher = self.home / ".local/bin/claude"
        versions.mkdir(parents=True)
        launcher.parent.mkdir(parents=True)
        self.binary = versions / "2.1.400"
        self.ran = self.home / "ran-admitted"
        self.binary.write_text(f"#!/bin/sh\ntouch '{self.ran}'\nprintf '%s\\n' '{self.INIT}'\n")
        self.binary.chmod(0o755)
        launcher.symlink_to(self.binary)
        self.codesign = self.home / "codesign"
        self.fake_codesign("exit 0")
        for name, value in (("CLAUDE_LAUNCHER", launcher), ("CLAUDE_VERSIONS", versions), ("CODESIGN", self.codesign)):
            self.enterContext(mock.patch.object(claude_code, name, value))
        self.decoy = self.home / "path-bin"
        self.decoy.mkdir()
        self.decoy_ran = self.home / "ran-decoy"
        (self.decoy / "claude").write_text(f"#!/bin/sh\ntouch '{self.decoy_ran}'\n")
        (self.decoy / "claude").chmod(0o755)
        project = self.home / "project"
        project.mkdir()
        self.box = SimpleNamespace(env={"PATH": f"{self.decoy}:/usr/bin:/bin", "HOME": str(self.home)}, project=project)

    def fake_codesign(self, verdict):
        self.codesign.write_text(f"#!/bin/sh\n{verdict}\n")
        self.codesign.chmod(0o755)

    def test_the_admitted_release_is_listed_and_the_path_claude_is_never_run(self):
        listing = install.claude_list(None, self.box)
        self.assertEqual(listing.discovered, frozenset({"a"}))
        self.assertEqual(listing.detail["version"], "2.1.400")
        self.assertTrue(self.ran.exists())
        self.assertFalse(self.decoy_ran.exists())

    def test_a_release_that_fails_the_requirement_is_never_run(self):
        self.fake_codesign("echo 'failed to satisfy specified code requirement(s)' >&2\nexit 3")
        with self.assertRaisesRegex(claude_code.IsolationUnavailable, "fails code requirement"):
            install.claude_list(None, self.box)
        self.assertFalse(self.ran.exists())
        self.assertFalse(self.decoy_ran.exists())

    def test_a_missing_launcher_is_inconclusive_without_a_check_error(self):
        claude_code.CLAUDE_LAUNCHER.unlink()
        with self.assertRaisesRegex(install.Inconclusive, "^claude is not installed$"):
            install.claude_list(None, self.box)
        result = install.evaluate(SimpleNamespace(skills_version="1"), install.Check(
            "listing", ("claude-code",), lambda ctx, harness: install.claude_list(ctx, self.box)), "claude-code")
        self.assertEqual(result["verdict"], "INCONCLUSIVE")
        self.assertEqual(result["evidence"], {"skills_cli": "1", "reason": "claude is not installed"})
        self.assertFalse(self.ran.exists())
        self.assertFalse(self.decoy_ran.exists())

    def test_a_dangling_launcher_is_a_check_error(self):
        self.binary.unlink()
        result = install.evaluate(SimpleNamespace(skills_version="1"), install.Check(
            "listing", ("claude-code",), lambda ctx, harness: install.claude_list(ctx, self.box)), "claude-code")
        self.assertEqual(result["verdict"], "INCONCLUSIVE")
        self.assertTrue(result["evidence"]["check_error"])
        self.assertIn("IsolationUnavailable", result["evidence"]["reason"])
        self.assertFalse(self.decoy_ran.exists())

    def test_an_unadmitted_claude_is_a_check_error_not_a_verdict(self):
        self.fake_codesign("exit 3")
        result = install.evaluate(SimpleNamespace(skills_version="1"), install.Check(
            "listing", ("claude-code",), lambda ctx, harness: install.claude_list(ctx, self.box)), "claude-code")
        self.assertEqual(result["verdict"], "INCONCLUSIVE")
        self.assertTrue(result["evidence"]["check_error"])
        self.assertIn("IsolationUnavailable", result["evidence"]["reason"])


if __name__ == "__main__":
    unittest.main()
