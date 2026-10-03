import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import install


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

    def test_a_failed_promise_exits_nonzero(self):
        code, results, err = self.run_main(passing, failing)
        self.assertEqual([r["verdict"] for r in results], ["PASS", "FAIL"])
        self.assertEqual(code, 1)
        self.assertIn("1 FAIL", err)

    def test_inconclusive_alone_exits_zero_and_says_so(self):
        code, results, err = self.run_main(passing, undecided)
        self.assertEqual([r["verdict"] for r in results], ["PASS", "INCONCLUSIVE"])
        self.assertEqual(code, 0)
        self.assertIn("INCONCLUSIVE does not change the exit status", err)

    def test_all_pass_exits_zero(self):
        code, _, err = self.run_main(passing)
        self.assertEqual(code, 0)
        self.assertIn("1 PASS", err)


if __name__ == "__main__":
    unittest.main()
