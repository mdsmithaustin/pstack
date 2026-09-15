from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from compose_eval_holdback import CompositionError, compose, public_digests


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def holdback_cases() -> list[dict[str, object]]:
    behavior = [
        {"id": f"behavior-{index}", "split": "holdback", "kind": "positive", "prompt": "Secret"}
        for index in range(1, 5)
    ]
    positive = [
        {
            "id": f"positive-trigger-{index}",
            "split": "holdback",
            "kind": "trigger",
            "should_trigger": True,
            "prompt": "Secret",
        }
        for index in range(1, 5)
    ]
    negative = [
        {
            "id": f"negative-trigger-{index}",
            "split": "holdback",
            "kind": "trigger",
            "should_trigger": False,
            "prompt": "Secret",
        }
        for index in range(1, 5)
    ]
    return [*behavior, *positive, *negative]


class ComposeEvalHoldbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "repo"
        self.skill = self.repo / "skills" / "demo" / "SKILL.md"
        self.skill.parent.mkdir(parents=True)
        self.skill.write_text("---\nname: demo\ndescription: Demo.\n---\n", encoding="utf-8")
        self.skill_reference = self.skill.parent / "references" / "rules.md"
        self.skill_reference.parent.mkdir()
        self.skill_reference.write_text("frozen", encoding="utf-8")
        self.manifest = self.repo / "evals" / "demo" / "shared-benchmark.json"
        write_json(self.manifest, {
            "version": 1,
            "skill_name": "demo",
            "skill_paths": ["skills/demo/SKILL.md"],
            "split_policy": {"holdback": "No private holdback."},
            "cases": [{"id": "public", "split": "tune", "prompt": "Public"}],
        })
        self.public_fixture = self.manifest.parent / "fixtures" / "public.txt"
        self.public_fixture.parent.mkdir()
        self.public_fixture.write_text("frozen", encoding="utf-8")
        self.overlay = self.root / "private" / "overlay.json"
        write_json(self.overlay.parent / "payload" / "prompts" / "secret.json", {"value": 7})
        self.write_overlay()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_overlay(self, **changes: object) -> None:
        value = {
            "version": 1,
            "skill_name": "demo",
            **public_digests(self.repo, "demo"),
            "payload_dir": "payload",
            "cases": holdback_cases(),
        }
        value.update(changes)
        write_json(self.overlay, value)

    def test_composes_public_and_private_inputs_without_mutating_source(self) -> None:
        cases = holdback_cases()
        cases[0].pop("prompt")
        cases[0]["prompt_ref"] = "prompts/secret.json"
        self.write_overlay(cases=cases)
        before = self.manifest.read_bytes()
        result = compose(self.repo, "demo", self.overlay, self.root / "composed")
        merged = json.loads(result.read_text(encoding="utf-8"))
        self.assertEqual(len(merged["cases"]), 13)
        self.assertEqual(merged["cases"][0]["id"], "public")
        self.assertEqual(self.manifest.read_bytes(), before)
        self.assertTrue((result.parent / "prompts" / "secret.json").is_file())
        self.assertTrue((self.root / "composed" / "skills" / "demo" / "SKILL.md").is_file())

    def test_public_digest_contract_covers_files_and_trees(self) -> None:
        values = public_digests(self.repo, "demo")
        self.assertEqual(set(values), {
            "public_manifest_sha256",
            "public_skill_sha256",
            "public_suite_sha256",
            "public_skill_tree_sha256",
        })
        self.assertEqual(values["public_manifest_sha256"], digest(self.manifest))
        self.assertTrue(all(len(value) == 64 for value in values.values()))

    def test_rejects_changed_public_manifest(self) -> None:
        self.manifest.write_text(self.manifest.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        with self.assertRaisesRegex(CompositionError, "public_manifest_sha256"):
            compose(self.repo, "demo", self.overlay, self.root / "changed")

    def test_rejects_changed_public_suite_file(self) -> None:
        self.public_fixture.write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(CompositionError, "public_suite_sha256"):
            compose(self.repo, "demo", self.overlay, self.root / "changed-suite")

    def test_rejects_changed_skill_tree_file(self) -> None:
        self.skill_reference.write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(CompositionError, "public_skill_tree_sha256"):
            compose(self.repo, "demo", self.overlay, self.root / "changed-skill-tree")

    def test_rejects_a_symlinked_public_tree_root(self) -> None:
        outside = self.root / "outside-skill"
        shutil.move(self.skill.parent, outside)
        self.skill.parent.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(CompositionError, "symlinks are not allowed"):
            public_digests(self.repo, "demo")

    def test_rejects_a_public_tree_below_a_symlinked_ancestor(self) -> None:
        outside = self.root / "outside-skills"
        shutil.move(self.repo / "skills", outside)
        (self.repo / "skills").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(CompositionError, "symlinks are not allowed"):
            public_digests(self.repo, "demo")

    def test_rejects_special_files_in_a_public_tree(self) -> None:
        os.mkfifo(self.manifest.parent / "tamper.pipe")
        with self.assertRaisesRegex(CompositionError, "special files are not allowed"):
            public_digests(self.repo, "demo")

    def test_rejects_public_case_collision(self) -> None:
        cases = holdback_cases()
        cases[0]["id"] = "public"
        self.write_overlay(cases=cases)
        with self.assertRaisesRegex(CompositionError, "not unique"):
            compose(self.repo, "demo", self.overlay, self.root / "collision")

    def test_rejects_case_ids_that_are_not_safe_path_segments(self) -> None:
        for index, case_id in enumerate(("../outside", "foo/bar", "foo\\bar", ".", "..", ".hidden", "ＦＯＯ")):
            with self.subTest(case_id=case_id):
                cases = holdback_cases()
                cases[0]["id"] = case_id
                self.write_overlay(cases=cases)
                with self.assertRaisesRegex(CompositionError, "safe lowercase id"):
                    compose(self.repo, "demo", self.overlay, self.root / f"unsafe-id-{index}")

    def test_rejects_non_holdback_private_case(self) -> None:
        cases = holdback_cases()
        cases[0]["split"] = "tune"
        self.write_overlay(cases=cases)
        with self.assertRaisesRegex(CompositionError, "split=holdback"):
            compose(self.repo, "demo", self.overlay, self.root / "wrong-split")

    def test_rejects_output_inside_repository(self) -> None:
        with self.assertRaisesRegex(CompositionError, "outside the repository"):
            compose(self.repo, "demo", self.overlay, self.repo / "generated")

    def test_rejects_file_as_output_directory(self) -> None:
        output = self.root / "composed"
        output.write_text("occupied", encoding="utf-8")
        with self.assertRaisesRegex(CompositionError, "not a directory"):
            compose(self.repo, "demo", self.overlay, output)

    def test_rejects_symlink_as_output_directory(self) -> None:
        target = self.root / "target"
        target.mkdir()
        output = self.root / "composed-link"
        output.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(CompositionError, "must not be a symlink"):
            compose(self.repo, "demo", self.overlay, output)

    def test_rejects_incomplete_private_population(self) -> None:
        self.write_overlay(cases=holdback_cases()[:-1])
        with self.assertRaisesRegex(CompositionError, "exactly 4 behavior"):
            compose(self.repo, "demo", self.overlay, self.root / "incomplete")

    def test_rejects_unsupported_private_case_kind(self) -> None:
        cases = holdback_cases()
        cases[0]["kind"] = "mystery"
        self.write_overlay(cases=cases)
        with self.assertRaisesRegex(CompositionError, "unsupported kind"):
            compose(self.repo, "demo", self.overlay, self.root / "bad-kind")

    def test_rejects_payload_parent_traversal(self) -> None:
        for value in (".", ".."):
            with self.subTest(payload_dir=value):
                self.write_overlay(payload_dir=value)
                with self.assertRaisesRegex(CompositionError, "one directory name"):
                    compose(self.repo, "demo", self.overlay, self.root / f"traversal-{value.count('.')}")

    def test_rejects_unsafe_or_missing_case_references(self) -> None:
        for reference, message in (
            ("../secret.txt", "unsafe file reference"),
            ("/tmp/secret.txt", "unsafe file reference"),
            ("prompts/missing.txt", "missing file"),
        ):
            with self.subTest(reference=reference):
                cases = holdback_cases()
                cases[0]["files"] = [reference]
                self.write_overlay(cases=cases)
                with self.assertRaisesRegex(CompositionError, message):
                    compose(self.repo, "demo", self.overlay, self.root / f"bad-ref-{len(reference)}")

    def test_rejects_non_string_reference_fields(self) -> None:
        cases = holdback_cases()
        cases[0]["files"] = "fixtures/private.json"
        self.write_overlay(cases=cases)
        with self.assertRaisesRegex(CompositionError, "files must be a string list"):
            compose(self.repo, "demo", self.overlay, self.root / "bad-files")
        cases = holdback_cases()
        cases[0]["prompt_ref"] = 7
        self.write_overlay(cases=cases)
        with self.assertRaisesRegex(CompositionError, "prompt_ref must be a string"):
            compose(self.repo, "demo", self.overlay, self.root / "bad-prompt-ref")


if __name__ == "__main__":
    unittest.main()
