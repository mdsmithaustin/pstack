import contextlib
import copy
import io
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import ledger

GUIDE = ledger.ROOT / "docs" / "guide"


class CanonicalFormTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="pstack-ledger-")
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "ledger.json"

    def shuffled(self):
        def shuffle(node):
            if isinstance(node, dict):
                return {k: shuffle(node[k]) for k in reversed(list(node))}
            if isinstance(node, list):
                return [shuffle(item) for item in node]
            return node
        book = shuffle(ledger.load())
        self.path.write_text(json.dumps(book, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    def test_the_committed_ledger_is_canonical(self):
        self.assertEqual(ledger.main(["format", "--check"]), 0)

    def test_crlf_is_rejected_and_rewritten_to_canonical_lf_bytes(self):
        # The documented JSON serialization uses LF, regardless of input newlines.
        before = b'{\r\n "a": 1\r\n}\r\n'
        wanted = b'{\n "a": 1\n}\n'
        self.path.write_bytes(before)
        with contextlib.redirect_stdout(io.StringIO()):
            code = ledger.main(["format", "--check", "--ledger", str(self.path)])
        self.assertEqual(code, 1)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(ledger.main(["format", "--ledger", str(self.path)]), 0)
        self.assertEqual(self.path.read_bytes(), wanted)

    def test_a_reordered_ledger_fails_the_check_and_names_the_fix(self):
        self.shuffled()
        before = self.path.read_text(encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = ledger.main(["format", "--check", "--ledger", str(self.path)])
        self.assertEqual(code, 1)
        self.assertIn("python3 evals/promises/ledger.py format", out.getvalue())
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)

    def test_format_restores_the_committed_bytes_from_a_reordered_copy(self):
        self.shuffled()
        self.assertEqual(ledger.main(["format", "--ledger", str(self.path)]), 0)
        self.assertEqual(self.path.read_text(encoding="utf-8"), ledger.LEDGER.read_text(encoding="utf-8"))
        self.assertEqual(ledger.main(["format", "--check", "--ledger", str(self.path)]), 0)

    def test_format_that_cannot_encode_leaves_the_ledger_and_its_folder_untouched(self):
        book = ledger.load()
        book["promises"]["surrogate"] = {"claim": "\ud800"}
        self.path.write_text(json.dumps(book, indent=1) + "\n", encoding="utf-8")
        before = self.path.read_bytes()
        with self.assertRaises(UnicodeEncodeError):
            ledger.main(["format", "--ledger", str(self.path)])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual([p.name for p in self.path.parent.iterdir()], ["ledger.json"])

    def test_format_replaces_the_ledger_without_truncating_it_in_place(self):
        self.shuffled()
        inode = self.path.stat().st_ino
        ledger.main(["format", "--ledger", str(self.path)])
        self.assertNotEqual(self.path.stat().st_ino, inode)
        self.assertEqual([p.name for p in self.path.parent.iterdir()], ["ledger.json"])

    def test_a_duplicated_key_is_an_error_naming_the_key_not_a_silent_last_wins(self):
        duplicated = '{\n "promises": {},\n "units": {\n  "05-build:7": {"class": "context"},\n  "05-build:7": {"class": "promise"}\n }\n}\n'
        self.path.write_text(duplicated, encoding="utf-8")
        for argv in (["format", "--check"], ["format"], ["audit"]):
            with self.subTest(argv=argv):
                with self.assertRaisesRegex(ValueError, "duplicate key '05-build:7'"):
                    ledger.main([*argv, "--ledger", str(self.path)])
        self.assertEqual(self.path.read_text(encoding="utf-8"), duplicated)


class AuditTest(unittest.TestCase):
    def setUp(self):
        self.book = ledger.load()
        tmp = tempfile.TemporaryDirectory(prefix="pstack-ledger-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def guide_copy(self, name):
        dest = self.tmp / name
        shutil.copytree(GUIDE, dest)
        return dest

    def test_the_committed_ledger_audits_clean(self):
        self.assertEqual(ledger.audit(self.book, GUIDE), [])

    def test_a_new_guide_sentence_is_unclassified(self):
        guide = self.guide_copy("port")
        page = guide / "02-poteto-mode.md"
        page.write_text(page.read_text() + "\nThe mode now merges every PR it opens.\n")
        errors = ledger.audit(self.book, guide)
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("unclassified port unit"), errors[0])
        self.assertIn("The mode now merges every PR it opens.", errors[0])

    def test_a_reworded_upstream_sentence_is_unclassified_and_its_old_entry_stale(self):
        upstream = self.guide_copy("upstream")
        page = upstream / "06-verify-and-ship.md"
        text = page.read_text()
        old = "Babysit stops at merge-ready."
        self.assertIn(old, text)
        page.write_text(text.replace(old, "Babysit merges once checks are green."))
        book = copy.deepcopy(self.book)
        for entry in book["units"].values():
            entry["sources"] = sorted(set(entry["sources"]) | {"upstream"})
        errors = ledger.audit(book, GUIDE, upstream)
        self.assertTrue(any(e.startswith("unclassified upstream unit") and "Babysit merges once" in e for e in errors), errors)
        self.assertTrue(any(e.startswith("stale upstream unit") and old in e for e in errors), errors)

    def test_rewritten_skill_text_names_the_promise_it_breaks(self):
        book = copy.deepcopy(self.book)
        book["promises"]["babysit-never-merges"]["evidence"] = [
            {"file": "skills/poteto-mode/playbooks/babysit.md", "quote": "Babysit merges the PR once it is green."}]
        errors = ledger.audit(book, GUIDE)
        self.assertEqual(errors, ["promise babysit-never-merges quote no longer in skills/poteto-mode/playbooks/babysit.md: "
                                  "Babysit merges the PR once it is green."])

    def test_a_live_promise_bound_only_to_an_install_case_is_unchecked(self):
        book = copy.deepcopy(self.book)
        pid = "deslop-available-for-code"
        self.assertEqual(book["promises"][pid]["check"], "install")
        book["promises"][pid]["check"] = "live"
        errors = ledger.audit(book, GUIDE)
        self.assertEqual(errors, [f"promise {pid} (live) has no live case under evals/promises/cases/"])

    def test_an_install_promise_bound_only_to_a_live_case_is_unchecked(self):
        book = copy.deepcopy(self.book)
        pid = "arena-readonly-cross-judge"
        self.assertEqual(book["promises"][pid]["check"], "live")
        book["promises"][pid]["check"] = "install"
        errors = ledger.audit(book, GUIDE)
        self.assertEqual(errors, [f"promise {pid} (install) has no install case under evals/promises/cases/"])

    def test_a_hand_edited_unit_text_or_file_is_reported(self):
        book = copy.deepcopy(self.book)
        key = next(k for k, e in book["units"].items() if "port" in e["sources"] and e["class"] == "promise")
        original = book["units"][key]
        book["units"][key] = dict(original, text="Something the guide never says.", file="99-elsewhere.md")
        errors = ledger.audit(book, GUIDE)
        self.assertEqual(len(errors), 2, errors)
        self.assertTrue(any(e.startswith(f"{key} text differs from the port guide") for e in errors), errors)
        self.assertTrue(any(e.startswith(f"{key} file is '99-elsewhere.md'") for e in errors), errors)

    def test_promises_bound_only_to_deferred_cases_are_listed(self):
        deferred = ledger.deferred_only(self.book)
        self.assertIn("worktree-request-honored", deferred)
        self.assertNotIn("arena-readonly-cross-judge", deferred)

    def test_owner_status_tells_verbatim_from_port_only(self):
        upstream = self.tmp / "pstack"
        (upstream / "skills" / "tdd").mkdir(parents=True)
        shutil.copy(ledger.ROOT / "skills" / "poteto-tdd" / "SKILL.md", upstream / "skills" / "tdd" / "SKILL.md")
        self.assertEqual(ledger.owner_status("skills/poteto-tdd/SKILL.md", upstream), "verbatim")
        self.assertEqual(ledger.owner_status("skills/pstack-harness/SKILL.md", upstream), "port-only")


if __name__ == "__main__":
    unittest.main()
