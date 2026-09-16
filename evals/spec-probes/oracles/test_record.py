import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oracles.record import evaluate, evaluate_spec, extract_import_record
from oracles import check_record
from oracles.check_record import (
    load_events,
    main as check_record_main,
    parse_events,
    read_evaluation_artifacts,
    read_output,
)
from oracles.specs import CaseSpec


class RecordOracleTests(unittest.TestCase):
    def test_event_parser_rejects_ambiguous_or_nonfinite_json(self) -> None:
        for text in (
            '{"schema_version":2,"source":"test","events":[{"type":"file_change"}],"events":[]}',
            '{"schema_version":2,"source":"test","events":[{"type":"file_change","type":"message"}]}',
            '{"schema_version":2,"source":"test","events":[],"ignored":NaN}',
            '{"schema_version":2,"source":"test","events":[],"ignored":1e400}',
            '{"schema_version":2,"source":"test","events":[],"ignored":"\\ud800"}',
            '{"schema_version":2,"source":"test","events":[],"ignored":' + "[" * 101 + "0" + "]" * 101 + "}",
            '[' * 1100 + '0' + ']' * 1100,
        ):
            with self.subTest(text=text), self.assertRaisesRegex(
                ValueError,
                "cannot read events.json",
            ):
                parse_events(text)

    def test_accepts_markdown_table_and_structurally_different_prose(self) -> None:
        table = """| Source | Open decision |\n| --- | --- |\n| SP-101 | Which rounding rule applies? |\n| SP-102 | Do touching windows merge? |\n| SP-103 | What counts as a character? |\n| SP-104 | Which overlapping worker effect wins? |"""
        prose = "SP-104 leaves concurrent effects open. SP-102 does not define touching windows. Character counting remains open in SP-103, while SP-101 omits its rounding rule."
        self.assertEqual(evaluate("pos-mixed-shapes", table), [])
        self.assertEqual(evaluate("pos-mixed-shapes", prose), [])

    def test_embedded_record_rejects_duplicate_keys_and_nonfinite_numbers(self) -> None:
        for payload in (
            '{"coverage":{"applicable":0},"coverage":{"applicable":0}}',
            '{"coverage":{"applicable":NaN}}',
            '{"coverage":{"applicable":1e400}}',
        ):
            record, errors = extract_import_record(
                f"<spec-probe-record>{payload}</spec-probe-record>"
            )
            self.assertIsNone(record)
            self.assertEqual(len(errors), 1)
            self.assertIn("not valid JSON", errors[0])

    def test_reordered_requirements_and_paraphrased_questions_keep_the_verdict(self) -> None:
        first = "CH-401 leaves adjacent windows undecided. CH-402 needs a definition of character."
        second = "How should the product count a display-name symbol under CH-402? Must abutting availability periods combine under CH-401?"
        self.assertEqual(evaluate("pos-open-product-choice", first), [])
        self.assertEqual(evaluate("pos-open-product-choice", second), [])

    def test_consistent_requirement_rename_keeps_the_verdict(self) -> None:
        spec = CaseSpec(("AC-17", "AC-29"))
        original = evaluate_spec("AC-17 has one open decision. AC-29 has another.", spec)
        renamed_spec = CaseSpec(("ZX-4", "ZX-8"))
        renamed = evaluate_spec("ZX-4 has one open decision. ZX-8 has another.", renamed_spec)
        self.assertEqual(original, [])
        self.assertEqual(renamed, original)

    def test_rejects_parrot_and_forged_source_anchors(self) -> None:
        parrot = "Review the specification before implementation and report coverage."
        forged = "ZZ-999 is the only requirement that needs review."
        self.assertIn("missing source requirement anchors", evaluate("pos-open-product-choice", parrot)[0])
        self.assertIn("missing source requirement anchors", evaluate("pos-open-product-choice", forged)[0])

    def test_rejects_unsafe_trace_events(self) -> None:
        events = [{"type": "command", "input_summary": "git commit -am fix"}]
        errors = evaluate("pos-unclassified-prose", "HP-201 needs a product decision.", events)
        self.assertEqual(errors, ["pre-build review executed a command"])

    def test_allows_read_only_fixture_and_skill_inspection(self) -> None:
        events = [{
            "type": "command",
            "input_summary": "/bin/zsh -lc \"sed -n '1,240p' skills/spec-probes/SKILL.md && sed -n '1,280p' inputs/billing-spec.md\"",
        }]
        self.assertEqual(evaluate("pos-mixed-shapes", "SP-101 SP-102 SP-103 SP-104", events), [])

    def test_rejects_mutating_discovery_commands(self) -> None:
        for command in (
            "find inputs -type f -delete",
            "sort -o inputs/changed inputs/source",
            "sort -oinputs/changed inputs/source",
            "sort --compress-program=/tmp/mutate inputs/source",
            "sed -i '' 's/a/b/' inputs/spec.md",
            "sed -n '1,20p' -i inputs/spec.md",
            "rg --replace changed pattern inputs/spec.md",
            "rg --pre /tmp/mutate pattern inputs/spec.md",
            "cat inputs/spec.md || rm inputs/spec.md",
            "cat inputs/spec.md & rm inputs/spec.md",
            "cat inputs/spec.md\nrm inputs/spec.md",
            "./bash -lc 'cat inputs/spec.md'",
        ):
            with self.subTest(command=command):
                events = [{"type": "command", "input_summary": command}]
                errors = evaluate("pos-unclassified-prose", "HP-201 needs a decision.", events)
                self.assertEqual(errors, ["pre-build review executed a command"])

    def test_event_envelope_must_exist_but_may_be_empty(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            with self.assertRaisesRegex(ValueError, "must not be symlinks"):
                load_events(root)
            (root / "events.json").write_text(
                '{"schema_version": 2, "source": "test", "events": []}',
                encoding="utf-8",
            )
            self.assertEqual(load_events(root), [])

    def test_event_loader_rejects_non_object_envelopes_and_events(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for envelope in (
                [],
                {"events": []},
                {"schema_version": 2.0, "source": "test", "events": []},
                {"schema_version": 2, "source": "test", "events": [42]},
            ):
                (root / "events.json").write_text(json.dumps(envelope), encoding="utf-8")
                with self.subTest(envelope=envelope), self.assertRaises(ValueError):
                    load_events(root)

    def test_event_loader_rejects_a_symlinked_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            target = root / "real-events.json"
            target.write_text(
                '{"schema_version": 2, "source": "test", "events": []}',
                encoding="utf-8",
            )
            (root / "events.json").symlink_to(target)
            with self.assertRaisesRegex(ValueError, "must not be symlinks"):
                load_events(root)

    def test_check_record_rejects_a_symlinked_output_or_run_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            real_output = root / "real-output.md"
            real_output.write_text("HP-201 needs a product decision.", encoding="utf-8")
            (root / "output.md").symlink_to(real_output)
            (root / "events.json").write_text(
                '{"schema_version": 2, "source": "test", "events": []}',
                encoding="utf-8",
            )
            with mock.patch("sys.argv", ["check_record.py", "pos-unclassified-prose", str(root)]):
                self.assertEqual(check_record_main(), 2)

            real_run = root / "real-run"
            real_run.mkdir()
            (real_run / "output.md").write_text("HP-201 needs a product decision.", encoding="utf-8")
            (real_run / "events.json").write_text(
                '{"schema_version": 2, "source": "test", "events": []}',
                encoding="utf-8",
            )
            with mock.patch("sys.argv", ["check_record.py", "pos-unclassified-prose", str(real_run)]):
                self.assertEqual(check_record_main(), 0)
            linked_run = root / "linked-run"
            linked_run.symlink_to(real_run, target_is_directory=True)
            with mock.patch("sys.argv", ["check_record.py", "pos-unclassified-prose", str(linked_run)]):
                self.assertEqual(check_record_main(), 2)

            real_parent = root / "real-parent"
            real_parent.mkdir()
            nested_run = real_parent / "run"
            nested_run.mkdir()
            (nested_run / "output.md").write_text("HP-201 needs a product decision.", encoding="utf-8")
            (nested_run / "events.json").write_text(
                '{"schema_version": 2, "source": "test", "events": []}',
                encoding="utf-8",
            )
            with mock.patch("sys.argv", ["check_record.py", "pos-unclassified-prose", str(nested_run)]):
                self.assertEqual(check_record_main(), 0)
            alias_parent = root / "alias-parent"
            alias_parent.symlink_to(real_parent, target_is_directory=True)
            with mock.patch(
                "sys.argv",
                ["check_record.py", "pos-unclassified-prose", str(alias_parent / "run")],
            ):
                self.assertEqual(check_record_main(), 2)

    def test_output_reader_rejects_hard_links_fifos_and_open_swaps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            target = root / "real-output.md"
            target.write_text("HP-201 needs a product decision.", encoding="utf-8")
            output = root / "output.md"
            output.hardlink_to(target)
            with self.assertRaisesRegex(ValueError, "exactly one hard link"):
                read_output(root)

            output.unlink()
            target.unlink()
            os.mkfifo(output)
            with self.assertRaisesRegex(ValueError, "regular file"):
                read_output(root)
            output.unlink()

            output.write_text("HP-201 needs a product decision.", encoding="utf-8")
            replacement = root / "replacement-output.md"
            replacement.write_text("substituted", encoding="utf-8")
            real_open = os.open
            swapped = False

            def swap_then_open(path, flags, *args, **kwargs):
                nonlocal swapped
                if path == "output.md" and not swapped:
                    swapped = True
                    output.unlink()
                    output.symlink_to(replacement)
                return real_open(path, flags, *args, **kwargs)

            with mock.patch.object(check_record.os, "open", side_effect=swap_then_open):
                with self.assertRaisesRegex(ValueError, "must not be symlinks"):
                    read_output(root)
            self.assertTrue(swapped)

    def test_artifact_pair_keeps_one_run_directory_descriptor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            run = base / "run"
            run.mkdir()
            (run / "output.md").write_text(
                "HP-201 needs a product decision.",
                encoding="utf-8",
            )
            initial_events = {
                "schema_version": 2,
                "source": "test",
                "events": [{"type": "command", "input_summary": "git commit -am fix"}],
            }
            (run / "events.json").write_text(json.dumps(initial_events), encoding="utf-8")
            replacement = base / "replacement"
            replacement.mkdir()
            (replacement / "output.md").write_text("substituted", encoding="utf-8")
            (replacement / "events.json").write_text(
                '{"schema_version": 2, "source": "test", "events": []}',
                encoding="utf-8",
            )
            real_open = os.open
            swapped = False

            def swap_then_open(path, flags, *args, **kwargs):
                nonlocal swapped
                if path == "events.json" and not swapped:
                    swapped = True
                    run.rename(base / "original-run")
                    replacement.rename(run)
                return real_open(path, flags, *args, **kwargs)

            with mock.patch.object(check_record.os, "open", side_effect=swap_then_open):
                text, events = read_evaluation_artifacts(run)
            self.assertTrue(swapped)
            self.assertEqual(text, "HP-201 needs a product decision.")
            self.assertEqual(events, initial_events["events"])

    def test_accepts_deployed_incident_scope_refusal_without_fixed_wording(self) -> None:
        first = "This shipped failure belongs with incident response and debugging. I would not redefine the product contract here."
        second = "Route the production duplicate charge to the on-call investigation. No pre-build requirement review applies."
        self.assertEqual(evaluate("neg-deployed-incident-restraint", first), [])
        self.assertEqual(evaluate("neg-deployed-incident-restraint", second), [])

    def test_incident_rejects_manufactured_requirement_ids(self) -> None:
        errors = evaluate("neg-deployed-incident-restraint", "Create requirement BUG-401 for the incident.")
        self.assertEqual(errors, ["a deployed incident must not manufacture requirement IDs"])

    def test_incident_rejects_nonzero_tagged_coverage(self) -> None:
        text = '<spec-probe-record>{"coverage":{"applicable":1}}</spec-probe-record>'
        self.assertEqual(
            evaluate("neg-deployed-incident-restraint", text),
            ["coverage.applicable must be 0"],
        )

    def test_importer_integration_checks_parseable_coverage_arithmetic(self) -> None:
        record = {
            "requirements": [{"requirement_id": "HP-201", "items": [{"disposition": "unresolved"}], "coverage": {"applicable": 1, "unresolved": 1}}],
            "coverage": {"applicable": 1, "unresolved": 1},
        }
        text = f"<spec-probe-record>{json.dumps(record)}</spec-probe-record>"
        self.assertEqual(evaluate("pos-unclassified-prose", text), [])
        forged = text.replace('"applicable": 1', '"applicable": 9', 1)
        self.assertEqual(evaluate("pos-unclassified-prose", forged), ["requirements[0].coverage.applicable must be 1"])

    def test_importer_integration_rejects_duplicate_or_malformed_records(self) -> None:
        self.assertEqual(extract_import_record("plain prose")[1], ["expected one spec-probe-record tag, found 0"])
        duplicated = "<spec-probe-record>{}</spec-probe-record>" * 2
        self.assertEqual(extract_import_record(duplicated)[1], ["expected one spec-probe-record tag, found 2"])
        malformed = "<spec-probe-record>{not json}</spec-probe-record> HP-201"
        self.assertIn("record is not valid JSON", evaluate("pos-unclassified-prose", malformed)[0])


if __name__ == "__main__":
    unittest.main()
