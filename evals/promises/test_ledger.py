import copy
import shutil
import tempfile
import unittest
from pathlib import Path

import ledger

GUIDE = ledger.ROOT / "docs" / "guide"


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

    def test_owner_status_tells_verbatim_from_port_only(self):
        upstream = self.tmp / "pstack"
        (upstream / "skills" / "tdd").mkdir(parents=True)
        shutil.copy(ledger.ROOT / "skills" / "poteto-tdd" / "SKILL.md", upstream / "skills" / "tdd" / "SKILL.md")
        self.assertEqual(ledger.owner_status("skills/poteto-tdd/SKILL.md", upstream), "verbatim")
        self.assertEqual(ledger.owner_status("skills/pstack-harness/SKILL.md", upstream), "port-only")


if __name__ == "__main__":
    unittest.main()
