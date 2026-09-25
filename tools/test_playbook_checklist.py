#!/usr/bin/env python3
"""playbook-checklist emits one line per numbered step, with its identity and
pointers, and writes that checklist under the Worklist marker."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CHECKLIST_ARM = REPO / "evals/canon/rules/bundle-worklist-feature/arms/checklist.patch"

FEATURE = """\
1. how over the affected subsystem (**how**)
2. architect for parallel design exploration (**architect**)
3. Write the throughput checkpoint as four items in the same worklist (**principle-separate-before-serializing-shared-state**)
4. Delegate code-writing to a subagent using your configured feature model and effort (**pstack-harness**, **principle-model-the-domain**, **arena**)
5. Verify on the matching surface against the accepted scope and integrated result (**principle-prove-it-works**)
6. Rebase into small, ordered commits (**principle-sequence-verifiable-units**)
7. If the design is contested, interrogate before shipping (**interrogate**)
8. Run Opening a PR
"""

REFACTORING = """\
1. Pin the behavior contract first (**how**)
2. Name the structure the code is missing (**principle-model-the-domain**)
3. Name the target shape (**principle-foundational-thinking**, **principle-redesign-from-first-principles**, **architect**)
4. Subtract before you add (**principle-subtract-before-you-add**, **principle-laziness-protocol**)
5. Move in small behavior-preserving steps (**principle-migrate-callers-then-delete-legacy-apis**)
6. Prove behavior is unchanged on the real artifact (**principle-prove-it-works**)
7. Confirm the change is worth keeping (**principle-minimize-reader-load**)
8. Rebase into small ordered commits (**principle-sequence-verifiable-units**)
"""


def checklist_arm_skills(dest: Path) -> Path:
    """A copy of skills/ with the checklist arm applied, the only place the
    generator lives until that arm lands."""
    skills = dest / "skills"
    shutil.copytree(REPO / "skills", skills)
    subprocess.run(["git", "apply", str(CHECKLIST_ARM)], cwd=skills, check=True, capture_output=True)
    return skills


class PlaybookChecklist(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.skills = checklist_arm_skills(Path(self.tmp.name))
        self.script = self.skills / "poteto-mode/scripts/playbook-checklist"
        self.playbooks = self.skills / "poteto-mode/playbooks"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def emit(self, *args: str) -> str:
        return subprocess.run([sys.executable, str(self.script), *args], capture_output=True, text=True, check=True).stdout

    def test_emits_the_feature_and_refactoring_checklists(self) -> None:
        self.assertEqual(self.emit(str(self.playbooks / "feature.md")), FEATURE)
        self.assertEqual(self.emit(str(self.playbooks / "refactoring.md")), REFACTORING)

    def test_a_playbook_without_a_checklist_gives_the_same_lines(self) -> None:
        pristine = self.playbooks / "pristine-feature.md"
        pristine.write_text((REPO / "skills/poteto-mode/playbooks/feature.md").read_text(encoding="utf-8"), encoding="utf-8")
        self.assertEqual(self.emit(str(pristine)), FEATURE)

    def test_write_puts_the_checklist_under_the_marker_after_the_title(self) -> None:
        pristine = self.playbooks / "pristine-refactoring.md"
        original = (REPO / "skills/poteto-mode/playbooks/refactoring.md").read_text(encoding="utf-8")
        pristine.write_text(original, encoding="utf-8")
        self.emit("--write", str(pristine))
        written = pristine.read_text(encoding="utf-8")
        self.assertEqual(written, (self.playbooks / "refactoring.md").read_text(encoding="utf-8"))
        self.assertTrue(written.startswith(
            "### Refactoring\n\n**Worklist.** Copy these items into your worklist before step 1.\n\n" + REFACTORING + "\n**You own the contract."))

    def test_write_twice_changes_nothing(self) -> None:
        before = (self.playbooks / "feature.md").read_text(encoding="utf-8")
        self.emit("--write", str(self.playbooks / "feature.md"))
        self.assertEqual((self.playbooks / "feature.md").read_text(encoding="utf-8"), before)

    def test_a_bold_heading_is_the_identity_and_links_and_short_names_resolve(self) -> None:
        playbook = self.playbooks / "planted.md"
        playbook.write_text(
            "### Planted\n\n"
            "1. **Pin it.** Run the **how** skill, then [Prove It Works](../../principle-prove-it-works/SKILL.md).\n"
            "   - Split per the **separate-before-serializing-shared-state** principle skill and `sonnet`.\n"
            "2. Ship it, with `nope` and **Comments**.\n",
            encoding="utf-8",
        )
        self.assertEqual(self.emit(str(playbook)),
                         "1. Pin it (**how**, **principle-prove-it-works**, **principle-separate-before-serializing-shared-state**)\n"
                         "2. Ship it, with nope and Comments\n")


if __name__ == "__main__":
    unittest.main()
