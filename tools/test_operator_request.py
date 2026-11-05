#!/usr/bin/env python3
import concurrent.futures
import copy
import json
import os
import re
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "skills/poteto-mode/scripts/operator-request.py"
PREFIX = (
    b'My work to export "catalog" remains pending.\n'
    b'Observed evidence:\n'
    b'- The value from "catalog check" was "destination is unset".\n\n'
)
DEFAULT_REPLY = PREFIX + b'Will you provide "catalog destination"?\n'


def decode_record(data):
    def unique(pairs):
        record = {}
        for key, value in pairs:
            if key in record:
                raise ValueError("duplicate record key")
            record[key] = value
        return record

    raw = data[:-1] if data.endswith(b"\n") else data
    if not raw.startswith(b"{") or not raw.endswith(b"}"):
        raise ValueError("record framing")
    record = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
    if not isinstance(record, dict) or set(record) != {"kind", "text"}:
        raise ValueError("record fields")
    if any(not isinstance(value, str) for value in record.values()):
        raise ValueError("record fields")
    if record["kind"] not in {"reply", "help", "invalid", "unavailable", "internal"}:
        raise ValueError("record kind")
    if any(0xD800 <= ord(character) <= 0xDFFF for value in record.values() for character in value):
        raise ValueError("record scalar")
    return record


def accepted_reply(result, transport_error=False, truncated=False):
    if result.returncode != 0 or result.stderr or transport_error or truncated:
        raise ValueError("invocation did not complete successfully with complete output")
    record = decode_record(result.stdout)
    if record["kind"] != "reply":
        raise ValueError("not a reply")
    return record["text"].encode("utf-8")


class OperatorRequestCLI(unittest.TestCase):
    def invoke(self, document=b"", arguments=(), env=None, **kwargs):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *arguments],
            input=document, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, timeout=15, **kwargs,
        )

    def invoke_without_eof(self, arguments):
        reader, writer = os.pipe()
        process = None
        try:
            process = subprocess.Popen([sys.executable, str(SCRIPT), *arguments], stdin=reader,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate(timeout=5)
            return subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate()
            os.close(reader)
            os.close(writer)

    def envelope(self, dependency=None):
        return {
            "work": {"verb": "export", "target": "catalog"},
            "evidence": [{"source": "catalog check", "value": "destination is unset"}],
            "dependency": dependency or {"kind": "operator_action", "verb": "provide", "target": "catalog destination"},
        }

    def document(self, envelope):
        return json.dumps(envelope, ensure_ascii=False).encode("utf-8")

    def action(self, target="catalog destination", verb="provide", kind="operator_action"):
        return self.document(self.envelope({"kind": kind, "verb": verb, "target": target}))

    def record(self, result, kind, status):
        self.assertEqual(result.returncode, status, result.stderr)
        self.assertEqual(result.stderr, b"")
        record = decode_record(result.stdout)
        self.assertEqual(list(record), ["kind", "text"])
        self.assertEqual(record["kind"], kind)
        self.assertEqual(result.stdout, (json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n").encode("ascii"))
        self.assertTrue(record["text"].endswith("\n"))
        return record["text"].encode("utf-8")

    def assert_reply(self, result, expected=DEFAULT_REPLY):
        self.assertEqual(self.record(result, "reply", 0), expected)
        self.assertEqual(accepted_reply(result), expected)

    def assert_invalid(self, document, arguments=()):
        result = self.invoke(document, arguments)
        diagnostic = self.record(result, "invalid", 2)
        self.assertTrue(diagnostic.startswith(b"INVALID: "), diagnostic)
        self.assertEqual(diagnostic.count(b"\n"), 1)
        self.assertNotIn(b"Traceback", diagnostic)
        return diagnostic

    def fault(self, code, document=None, arguments=()):
        with tempfile.TemporaryDirectory(prefix="pstack-reply-fault-") as temporary:
            Path(temporary, "sitecustomize.py").write_text(code, encoding="utf-8")
            env = {**os.environ, "PYTHONPATH": temporary}
            return self.invoke(self.action() if document is None else document, arguments, env=env)

    def assert_literal(self, literal, path):
        envelope = self.envelope()
        record = envelope
        for key in path[:-1]:
            record = record[key]
        record[path[-1]] = literal
        result = self.invoke(self.document(envelope))
        self.assertEqual((result.returncode, result.stderr), (0, b""))
        body = self.record(result, "reply", 0)
        lines = body.decode("utf-8").splitlines()
        self.assertEqual(len(lines), 5)
        self.assertEqual(lines[1], "Observed evidence:")
        self.assertEqual(lines[3], "")
        decoder = json.JSONDecoder()
        work, end = decoder.raw_decode(lines[0][len("My work to export "):])
        self.assertEqual(lines[0][len("My work to export ") + end:], " remains pending.")
        observation = lines[2][len("- The value from "):]
        source, end = decoder.raw_decode(observation)
        self.assertTrue(observation[end:].startswith(" was "))
        observed, end2 = decoder.raw_decode(observation[end + len(" was "):])
        self.assertEqual(observation[end + len(" was ") + end2:], ".")
        target, end = decoder.raw_decode(lines[4][len("Will you provide "):])
        self.assertEqual(lines[4][len("Will you provide ") + end:], "?")
        values = {
            ("work", "target"): work,
            ("evidence", 0, "source"): source,
            ("evidence", 0, "value"): observed,
            ("dependency", "target"): target,
        }
        self.assertEqual(values[tuple(path)], literal)
        self.assertTrue(body.endswith(b"?\n"))
        return lines, body

    def test_operator_action_constructs_the_whole_reply(self):
        self.assert_reply(self.invoke(self.action()))

    def test_new_approval_retains_the_agent_as_the_actor(self):
        self.assert_reply(self.invoke(self.action("catalog archive", "create", "new_approval")),
                          PREFIX + b'May I create "catalog archive"?\n')

    def test_fact_confirmation_constructs_the_whole_reply(self):
        dependency = {"kind": "fact_confirmation", "subject": "catalog destination", "value": "catalog.json"}
        self.assert_reply(self.invoke(self.document(self.envelope(dependency))),
                          PREFIX + b'Is "catalog.json" the correct value for "catalog destination"?\n')

    def test_empty_and_whitespace_observations_and_duplicates_remain_in_order(self):
        envelope = self.envelope()
        envelope["evidence"] = [
            {"source": "first check", "value": ""},
            {"source": "second check", "value": " \t\n "},
            {"source": "first check", "value": ""},
        ]
        self.assert_reply(self.invoke(self.document(envelope)), (
            b'My work to export "catalog" remains pending.\nObserved evidence:\n'
            b'- The value from "first check" was "".\n'
            b'- The value from "second check" was " \\u0009\\u000a ".\n'
            b'- The value from "first check" was "".\n\n'
            b'Will you provide "catalog destination"?\n'
        ))

    def test_hexadecimal_evidence_remains_source_labeled_data(self):
        envelope = self.envelope()
        envelope["evidence"] = [
            {"source": "scanner stdout bytes, hexadecimal, complete", "value": "00ff0a"},
            {"source": "scanner stderr bytes, hexadecimal, excerpt at byte 2", "value": "fe"},
        ]
        self.assert_reply(self.invoke(self.document(envelope)), (
            b'My work to export "catalog" remains pending.\nObserved evidence:\n'
            b'- The value from "scanner stdout bytes, hexadecimal, complete" was "00ff0a".\n'
            b'- The value from "scanner stderr bytes, hexadecimal, excerpt at byte 2" was "fe".\n\n'
            b'Will you provide "catalog destination"?\n'
        ))

    def test_hyphenated_lowercase_verbs_are_accepted_for_both_actions(self):
        for word in ["re-create", "a-b-c", "inspect"]:
            envelope = self.envelope()
            envelope["work"]["verb"] = word
            envelope["dependency"]["verb"] = word
            with self.subTest(word=word):
                self.assert_reply(self.invoke(self.document(envelope)), (
                    'My work to %s "catalog" remains pending.\nObserved evidence:\n'
                    '- The value from "catalog check" was "destination is unset".\n\n'
                    'Will you %s "catalog destination"?\n' % (word, word)
                ).encode("utf-8"))

    def test_verb_grammar_rejects_alternatives_and_shell_operators(self):
        for path in [("work", "verb"), ("dependency", "verb")]:
            for word in ["", " ", "start or replace", "stop; run", "start\nstop", "Start", "écrire",
                         "-start", "start-", "start--stop", "stop_", "stop1", "a\x00b", "start\u2028stop"]:
                envelope = self.envelope()
                envelope[path[0]][path[1]] = word
                with self.subTest(path=path, word=word):
                    self.assertIn(b"verb", self.assert_invalid(self.document(envelope)))

    def test_empty_and_non_object_documents_are_rejected(self):
        for document in [b"", b" \t\r\n", b"null", b"[]", b"[{}]", b"true", b"0", b'"reply"']:
            with self.subTest(document=document):
                self.assert_invalid(document)

    def test_missing_and_unknown_fields_are_rejected_at_every_object_level(self):
        envelope = self.envelope()
        for path in [(), ("work",), ("evidence", 0), ("dependency",)]:
            record = envelope
            for key in path:
                record = record[key]
            for key in list(record):
                changed = copy.deepcopy(envelope)
                target = changed
                for part in path:
                    target = target[part]
                del target[key]
                with self.subTest(path=path, missing=key):
                    self.assert_invalid(self.document(changed))
            for key in ["body", "template", "prefix", "suffix", "question", "extra"]:
                changed = copy.deepcopy(envelope)
                target = changed
                for part in path:
                    target = target[part]
                target[key] = "caller text"
                with self.subTest(path=path, unknown=key):
                    self.assert_invalid(self.document(changed))

    def test_old_schema_unsupported_variants_and_cross_variant_fields_are_rejected(self):
        self.assert_invalid(b'{"kind":"operator_action","verb":"provide","target":"catalog"}')
        for dependency in [
            {"kind": "other", "verb": "provide", "target": "catalog"},
            {"kind": "operator_action", "verb": "provide", "target": "catalog", "subject": "catalog"},
            {"kind": "new_approval", "subject": "catalog", "value": "archive"},
            {"kind": "fact_confirmation", "subject": "catalog", "value": "archive", "verb": "create"},
            {"kind": "fact_confirmation", "subject": "catalog"},
        ]:
            with self.subTest(dependency=dependency):
                self.assert_invalid(self.document(self.envelope(dependency)))

    def test_wrong_container_types_and_empty_evidence_are_rejected(self):
        for field in ["work", "evidence", "dependency"]:
            for wrong in [None, False, 1, "text", [], [{}]]:
                envelope = self.envelope()
                envelope[field] = wrong
                with self.subTest(field=field, wrong=wrong):
                    self.assert_invalid(self.document(envelope))
        for evidence in [{}, [None], ["text"], [[]], [{}]]:
            envelope = self.envelope()
            envelope["evidence"] = evidence
            with self.subTest(evidence=evidence):
                self.assert_invalid(self.document(envelope))

    def test_every_leaf_requires_a_string_without_coercion(self):
        cases = [self.envelope(), self.envelope({"kind": "new_approval", "verb": "create", "target": "archive"}),
                 self.envelope({"kind": "fact_confirmation", "subject": "catalog", "value": "archive"})]
        for envelope in cases:
            paths = [("work", key) for key in envelope["work"]]
            paths += [("evidence", 0, key) for key in envelope["evidence"][0]]
            paths += [("dependency", key) for key in envelope["dependency"]]
            for path in paths:
                for wrong in [None, False, 1, 1.5, [], {}, {"value": "catalog"}]:
                    changed = copy.deepcopy(envelope)
                    record = changed
                    for key in path[:-1]:
                        record = record[key]
                    record[path[-1]] = wrong
                    with self.subTest(kind=envelope["dependency"]["kind"], path=path, wrong=wrong):
                        self.assert_invalid(self.document(changed))

    def test_duplicate_keys_at_every_nesting_level_are_rejected(self):
        valid = self.action()
        replacements = [
            (b'"work":', b'"work":{},"work":'),
            (b'"verb": "export"', b'"verb":"export","verb":"export"'),
            (b'"source": "catalog check"', b'"source":"a","\\u0073ource":"a"'),
            (b'"value": "destination is unset"', b'"value":"x","value":"x"'),
            (b'"kind": "operator_action"', b'"kind":"operator_action","kind":"operator_action"'),
            (b'"target": "catalog destination"', b'"target":"catalog","target":"catalog"'),
        ]
        for original, duplicate in replacements:
            with self.subTest(original=original):
                self.assertIn(b"duplicate", self.assert_invalid(valid.replace(original, duplicate)))
        envelope = self.envelope()
        envelope["evidence"][0]["value"] = {"nested": "value"}
        nested = self.document(envelope).replace(b'"nested": "value"', b'"nested":"value","nested":"value"')
        self.assertIn(b"duplicate", self.assert_invalid(nested))

    def test_multiple_documents_comments_and_trailing_garbage_are_rejected(self):
        valid = self.action()
        for document in [valid + valid, valid + b" null", valid + b"\x00", valid + b" // comment",
                         b"/* comment */" + valid, valid[:-1] + b",}", b"Will you provide the catalog?"]:
            with self.subTest(document=document):
                self.assert_invalid(document)

    def test_only_json_document_whitespace_is_accepted(self):
        self.assert_reply(self.invoke(b" \t\r\n" + self.action() + b"\n\r\t "))
        for whitespace in ["\v", "\f", "\u0085", "\u00a0", "\u2003", "\ufeff"]:
            for document in [whitespace.encode("utf-8") + self.action(), self.action() + whitespace.encode("utf-8")]:
                with self.subTest(document=document):
                    self.assert_invalid(document)

    def test_non_json_constants_and_numeric_payloads_are_rejected(self):
        for value in [b"NaN", b"Infinity", b"-Infinity", b"1", b"-1.25", b"1e10000", b"9" * 5000]:
            with self.subTest(value=value[:20]):
                self.assert_invalid(self.action().replace(b'"destination is unset"', value))

    def test_excessive_json_nesting_is_invalid_instead_of_an_internal_fault(self):
        document = self.action().replace(b'"destination is unset"', b"[" * 10000 + b"0" + b"]" * 10000)
        self.assert_invalid(document)

    def test_bom_and_invalid_utf8_have_no_reply(self):
        for document in [b"\xef\xbb\xbf" + self.action(), b"\xff", b"\xc0\xaf", b"\xe2\x82",
                         self.action().replace(b'"catalog"', b'"\xed\xa0\x80"')]:
            with self.subTest(document=document):
                self.assert_invalid(document)

    def test_unpaired_surrogates_are_rejected_in_all_payload_fields(self):
        envelopes = [self.envelope(), self.envelope({"kind": "fact_confirmation", "subject": "catalog", "value": "archive"})]
        for envelope in envelopes:
            paths = [("work", key) for key in envelope["work"]]
            paths += [("evidence", 0, key) for key in envelope["evidence"][0]]
            paths += [("dependency", key) for key in envelope["dependency"]]
            for path in paths:
                for surrogate in ["\ud800", "\udfff", "\ud800x", "x\udfff"]:
                    changed = copy.deepcopy(envelope)
                    record = changed
                    for key in path[:-1]:
                        record = record[key]
                    record[path[-1]] = surrogate
                    with self.subTest(path=path, surrogate=ascii(surrogate)):
                        self.assert_invalid(json.dumps(changed).encode("ascii"))

    def test_surrogate_pairs_and_raw_utf8_have_the_same_scalar_identity(self):
        envelope = self.envelope()
        envelope["evidence"][0]["value"] = "catalog 🚀"
        expected = (b'My work to export "catalog" remains pending.\nObserved evidence:\n'
                    + '- The value from "catalog check" was "catalog 🚀".\n\n'.encode("utf-8")
                    + b'Will you provide "catalog destination"?\n')
        self.assert_reply(self.invoke(self.document(envelope)), expected)
        self.assert_reply(self.invoke(json.dumps(envelope).encode("ascii")), expected)

    def test_labels_reject_empty_and_all_unicode_whitespace(self):
        for dependency in [self.envelope()["dependency"], {"kind": "fact_confirmation", "subject": "catalog", "value": "archive"}]:
            envelope = self.envelope(dependency)
            paths = [("work", "target"), ("evidence", 0, "source")]
            paths += [("dependency", key) for key in dependency if key not in ["kind", "verb"]]
            for path in paths:
                for literal in ["", " ", "\t\r\n", "\u0085\u00a0\u2003\u2028\u2029", "\u3000"]:
                    changed = copy.deepcopy(envelope)
                    record = changed
                    for key in path[:-1]:
                        record = record[key]
                    record[path[-1]] = literal
                    with self.subTest(path=path, literal=ascii(literal)):
                        self.assert_invalid(self.document(changed))

    def test_literal_whitespace_unicode_and_combining_order_are_preserved_in_every_role(self):
        for path in [("work", "target"), ("evidence", 0, "source"), ("evidence", 0, "value"), ("dependency", "target")]:
            for literal in [" catalog ", "\tcatalog\r\n", "é", "e\u0301", "中東", "\u0301e", "name\u200dname"]:
                with self.subTest(path=path, literal=literal):
                    self.assert_literal(literal, path)
        self.assertNotEqual(self.invoke(self.action("é")).stdout, self.invoke(self.action("e\u0301")).stdout)

    def test_display_delimiters_use_exact_reversible_unicode_escapes(self):
        literal = '"\\`*_{}[]<>()!#|&~'
        quoted = ('"\\u0022\\u005c\\u0060\\u002a\\u005f\\u007b\\u007d\\u005b\\u005d'
                  '\\u003c\\u003e\\u0028\\u0029\\u0021\\u0023\\u007c\\u0026\\u007e"')
        _, output = self.assert_literal(literal, ("dependency", "target"))
        self.assertEqual(output, PREFIX + ("Will you provide " + quoted + "?\n").encode("utf-8"))

    def test_controls_line_separators_and_format_controls_are_visible(self):
        literal = "catalog\x00\t\n\r\x7f\x85\u200d\u202e\u2028\u2029\U000e0001"
        quoted = ('"catalog\\u0000\\u0009\\u000a\\u000d\\u007f\\u0085\\u200d\\u202e'
                  '\\u2028\\u2029\\udb40\\udc01"')
        _, output = self.assert_literal(literal, ("evidence", 0, "value"))
        self.assertEqual(output, (
            'My work to export "catalog" remains pending.\nObserved evidence:\n'
            '- The value from "catalog check" was ' + quoted + '.\n\n'
            'Will you provide "catalog destination"?\n'
        ).encode("utf-8"))

    def test_urls_source_code_apostrophes_and_compound_literals_remain_data(self):
        for literal in ["report-or-final", "https://example.test/?q=one&next=two", "a && b; $(touch marker)",
                        "owner's catalog", 'print("hello")', "archive then inspect or report"]:
            with self.subTest(literal=literal):
                self.assert_literal(literal, ("dependency", "target"))

    def test_fact_literals_round_trip_independently(self):
        subject = ' catalog "destination"\n'
        value = "https://example.test/?a=b&c=d\u202e"
        envelope = self.envelope({"kind": "fact_confirmation", "subject": subject, "value": value})
        result = self.invoke(self.document(envelope))
        self.assertEqual((result.returncode, result.stderr), (0, b""))
        body = self.record(result, "reply", 0)
        self.assertTrue(body.startswith(PREFIX))
        text = body[len(PREFIX):].decode("utf-8")
        self.assertEqual(text.count("\n"), 1)
        decoder = json.JSONDecoder()
        actual_value, end = decoder.raw_decode(text[3:])
        remainder = text[3 + end:]
        middle = " the correct value for "
        self.assertTrue(remainder.startswith(middle))
        actual_subject, end = decoder.raw_decode(remainder[len(middle):])
        self.assertEqual(remainder[len(middle) + end:], "?\n")
        self.assertEqual((actual_subject, actual_value), (subject, value))

    def test_object_key_order_and_repeated_calls_produce_identical_bytes(self):
        envelope = self.envelope()
        reordered = {"dependency": dict(reversed(list(envelope["dependency"].items()))),
                     "evidence": [dict(reversed(list(envelope["evidence"][0].items())))],
                     "work": dict(reversed(list(envelope["work"].items())))}
        for document in [self.action(), self.document(reordered)] * 2:
            self.assert_reply(self.invoke(document))

    def test_concurrent_calls_keep_separate_results_without_files_or_execution(self):
        with tempfile.TemporaryDirectory(prefix="pstack-blocked-reply-") as temporary:
            path = Path(temporary)
            (path / "keep").write_bytes(b"unchanged")
            target = "$(touch marker); echo result"
            documents = [self.action(target + str(index), "inspect") for index in range(8)]
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(lambda document: self.invoke(document, cwd=temporary), documents))
            for index, result in enumerate(results):
                self.assertEqual((result.returncode, result.stderr), (0, b""))
                body = self.record(result, "reply", 0)
                self.assertTrue(body.startswith(PREFIX))
                actual = body[len(PREFIX) + len(b"Will you inspect "):-2].decode("utf-8")
                self.assertEqual(json.loads(actual), target + str(index))
            self.assertEqual(sorted(item.name for item in path.iterdir()), ["keep"])
            self.assertEqual((path / "keep").read_bytes(), b"unchanged")

    def test_output_is_utf8_even_when_python_io_encoding_is_ascii(self):
        env = {**os.environ, "PYTHONIOENCODING": "ascii", "PYTHONUTF8": "0"}
        self.assert_reply(self.invoke(self.action("München 🚀"), env=env),
                          PREFIX + 'Will you provide "München 🚀"?\n'.encode("utf-8"))

    def test_long_observations_have_no_helper_limit_or_truncation(self):
        literal = "catalog" * 20000
        envelope = self.envelope()
        envelope["evidence"][0]["value"] = literal
        self.assert_reply(self.invoke(self.document(envelope)), (
            'My work to export "catalog" remains pending.\nObserved evidence:\n'
            '- The value from "catalog check" was "' + literal + '".\n\n'
            'Will you provide "catalog destination"?\n'
        ).encode("utf-8"))

    def test_help_is_a_record_and_does_not_wait_for_stdin(self):
        result = self.invoke_without_eof(("--help",))
        text = self.record(result, "help", 0)
        self.assertTrue(text.startswith(b"Usage: operator-request.py"), text)
        for required in [b"work", b"evidence", b"dependency", b"source", b"observed text",
                         b"operator_action", b"new_approval", b"fact_confirmation", b"empty", b"hexadecimal",
                         b"entire reply", b"Exit 2", b"Exit 69", b"Exit 70", b"Python 3.9",
                         b"generated data", b"completed success", b"final outer LF", b"${PSTACK_SKILLS_ROOT:?}"]:
            with self.subTest(required=required):
                self.assertIn(required, text)

    def test_all_other_arguments_reject_without_waiting_for_stdin(self):
        for arguments in [("-h",), ("--hel",), ("--",), ("reply.json",), ("--help", "--help"),
                          ("--help", "extra"), ("--version",), ("--kind=operator_action",), ("question",)]:
            with self.subTest(arguments=arguments):
                result = self.invoke_without_eof(arguments)
                self.assertTrue(self.record(result, "invalid", 2).startswith(b"INVALID: "))

    def test_closed_stdin_reports_unavailable_without_a_reply(self):
        result = subprocess.run([sys.executable, str(SCRIPT)], preexec_fn=lambda: os.close(0),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
        self.assertEqual(self.record(result, "unavailable", 69), b"UNAVAILABLE: stdin is unavailable\n")

    def test_broken_output_reports_unavailable_instead_of_success(self):
        reader, writer = os.pipe()
        os.close(reader)
        try:
            result = subprocess.run([sys.executable, str(SCRIPT)], input=self.action(), stdout=writer,
                                    stderr=subprocess.PIPE, timeout=5)
        finally:
            os.close(writer)
        self.assertEqual(result.returncode, 69, result.stderr)
        self.assertTrue(result.stderr.startswith(b"UNAVAILABLE: "), result.stderr)

    def test_short_stdout_writes_complete_the_same_bytes(self):
        result = self.fault(
            "import os\noriginal = os.write\ndef short(fd, data):\n"
            "    return original(fd, data[:3] if fd == 1 else data)\nos.write = short\n"
        )
        self.assert_reply(result)

    def test_short_help_writes_complete_the_same_contract(self):
        expected = self.invoke(arguments=("--help",))
        result = self.fault(
            "import os\noriginal = os.write\ndef short(fd, data):\n"
            "    return original(fd, data[:3])\nos.write = short\n",
            arguments=("--help",),
        )
        self.assertGreater(len(self.record(expected, "help", 0)), 100)
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (0, expected.stdout, b""))

    def test_zero_byte_stdout_write_reports_unavailable(self):
        result = self.fault(
            "import os\noriginal = os.write\ndef stopped(fd, data):\n"
            "    return 0 if fd == 1 else original(fd, data)\nos.write = stopped\n"
        )
        self.assertEqual((result.returncode, result.stdout), (69, b""))
        self.assertTrue(result.stderr.startswith(b"UNAVAILABLE: "), result.stderr)

    def test_failed_output_prefix_is_not_reported_as_success(self):
        result = self.fault(
            "import os\noriginal = os.write\nfirst = True\ndef interrupted(fd, data):\n"
            "    global first\n    if fd != 1:\n        return original(fd, data)\n"
            "    if first:\n        first = False\n        return original(fd, data[:7])\n"
            "    raise OSError('output interrupted')\nos.write = interrupted\n"
        )
        expected = self.invoke(self.action()).stdout
        self.assertEqual((result.returncode, result.stdout), (69, expected[:7]))
        self.assertTrue(result.stderr.startswith(b"UNAVAILABLE: "), result.stderr)

    def test_late_render_fault_leaves_no_stdout_prefix(self):
        envelope = self.envelope()
        envelope["evidence"].append({"source": "late check", "value": "☃"})
        result = self.fault(
            "import unicodedata\noriginal = unicodedata.category\ndef broken(character):\n"
            "    if character == '\\u2603':\n        raise RuntimeError('render fault')\n"
            "    return original(character)\nunicodedata.category = broken\n",
            self.document(envelope),
        )
        self.assertEqual(self.record(result, "internal", 70), b"INTERNAL: unexpected helper defect\n")

    def test_unexpected_input_fault_reports_internal(self):
        result = self.fault(
            "import sys\nclass BrokenInput:\n    @property\n    def buffer(self):\n"
            "        raise RuntimeError('unexpected input adapter fault')\nsys.stdin = BrokenInput()\n"
        )
        self.assertEqual(self.record(result, "internal", 70), b"INTERNAL: unexpected helper defect\n")

    def test_runtime_memory_failure_reports_unavailable(self):
        result = self.fault(
            "import sys\nclass BrokenInput:\n    @property\n    def buffer(self):\n"
            "        raise MemoryError('input allocation failed')\nsys.stdin = BrokenInput()\n"
        )
        self.assertEqual(self.record(result, "unavailable", 69), b"UNAVAILABLE: runtime or process I/O failed\n")

    def test_exact_generated_record_has_independent_byte_and_status_oracles(self):
        result = self.invoke(self.action())
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(result.stdout,
                         br'{"kind":"reply","text":"My work to export \"catalog\" remains pending.\nObserved evidence:\n- The value from \"catalog check\" was \"destination is unset\".\n\nWill you provide \"catalog destination\"?\n"}' + b"\n")
        invalid = self.invoke(b"{}")
        self.assertEqual((invalid.returncode, invalid.stderr), (2, b""))
        self.assertEqual(invalid.stdout,
                         br"""{"kind":"invalid","text":"INVALID: reply fields differ; missing ['dependency', 'evidence', 'work']; unknown []\n"}""" + b"\n")

    def test_generated_help_examples_execute_from_an_unrelated_installed_directory(self):
        help_text = self.record(self.invoke(arguments=("--help",)), "help", 0).decode("utf-8")
        examples = re.findall(r"```sh\n(.*?)\n```", help_text, re.DOTALL)
        self.assertGreaterEqual(len(examples), 3)
        observed = []
        with tempfile.TemporaryDirectory(prefix="pstack-reply-examples-") as temporary:
            root = Path(temporary)
            installed = root / "installed skills"
            helper = installed / "poteto-mode/scripts/operator-request.py"
            helper.parent.mkdir(parents=True)
            shutil.copyfile(SCRIPT, helper)
            binaries = root / "bin"
            binaries.mkdir()
            (binaries / "python3").symlink_to(sys.executable)
            cwd = root / "unrelated"
            cwd.mkdir()
            env = {**os.environ, "PSTACK_SKILLS_ROOT": str(installed), "PATH": str(binaries)}
            for example in examples:
                with self.subTest(example=example):
                    expected = re.search(r"^# Expected kind=(\w+); exit=(\d+)$", example, re.MULTILINE)
                    self.assertIsNotNone(expected)
                    self.assertIn('exec python3 "${PSTACK_SKILLS_ROOT:?}/poteto-mode/scripts/operator-request.py"', example)
                    result = subprocess.run(["/bin/sh", "-c", example], stdin=subprocess.DEVNULL,
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, env=env, timeout=5)
                    kind, status = expected.groups()
                    self.record(result, kind, int(status))
                    observed.append((kind, "--help" in example))
            self.assertEqual(list(cwd.iterdir()), [])
        self.assertIn(("help", True), observed)
        self.assertIn(("reply", False), observed)
        self.assertIn(("invalid", False), observed)

    def test_import_refuses_without_exposing_private_functions(self):
        result = subprocess.run(
            [sys.executable, "-c", "import importlib.util,sys; "
             "spec=importlib.util.spec_from_file_location('unsupported_import',sys.argv[1]); "
             "module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)", str(SCRIPT)],
            input=self.action(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5,
        )
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (1, b"", b"operator-request.py supports command-line execution only\n"))

    def test_receiver_accepts_one_outer_lf_or_none_and_either_field_order(self):
        result = self.invoke(self.action())
        self.assertEqual(accepted_reply(result), DEFAULT_REPLY)
        self.assertEqual(decode_record(result.stdout[:-1])["text"].encode("utf-8"), DEFAULT_REPLY)
        reversed_fields = self.fault(
            "import os,json\noriginal=os.write\ndef reordered(fd,data):\n"
            "    if fd != 1: return original(fd,data)\n"
            "    value=json.loads(bytes(data))\n"
            "    original(fd,json.dumps({'text':value['text'],'kind':value['kind']}).encode('ascii'))\n"
            "    return len(data)\nos.write=reordered\n"
        )
        self.assertEqual(accepted_reply(reversed_fields), DEFAULT_REPLY)

    def test_receiver_rejects_complete_records_with_noise_or_truncation(self):
        for transform in ["b'prefix'+raw", "b'\\n'+raw", "raw+b' '", "raw+b'\\n'",
                          "raw[:-1]+b'\\r\\n'", "raw+raw", "b'Exit code 2\\n'+raw", "raw[:-8]",
                          "raw[:-2]", "raw[:-1]+b' suffix'"]:
            with self.subTest(transform=transform):
                result = self.fault(
                    "import os\noriginal=os.write\ndef corrupted(fd,data):\n"
                    "    if fd != 1: return original(fd,data)\n"
                    "    raw=bytes(data)\n    original(fd," + transform + ")\n"
                    "    return len(data)\nos.write=corrupted\n"
                )
                self.assertEqual((result.returncode, result.stderr), (0, b""))
                with self.assertRaises(ValueError):
                    accepted_reply(result)

    def test_receiver_rejects_duplicate_unknown_missing_nonstring_and_nonscalar_fields(self):
        mutations = [
            "raw.replace(b'{',b'{\"kind\":\"reply\",',1)",
            "raw.replace(b'{',b'{\"extra\":\"value\",',1)",
            "b'{\"kind\":\"reply\"}\\n'", "b'[]\\n'",
            "b'{\"kind\":\"reply\",\"text\":null}\\n'",
            "b'{\"kind\":\"reply\",\"text\":\"\\\\ud800\"}\\n'",
            "b'{\"kind\":\"reply\",\"text\":\"\\xff\"}\\n'",
            "raw.replace(b'\"reply\"',b'\"unknown\"',1)",
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                result = self.fault(
                    "import os\noriginal=os.write\ndef corrupted(fd,data):\n"
                    "    if fd != 1: return original(fd,data)\n"
                    "    raw=bytes(data)\n    original(fd," + mutation + ")\n"
                    "    return len(data)\nos.write=corrupted\n"
                )
                self.assertEqual((result.returncode, result.stderr), (0, b""))
                with self.assertRaises(ValueError):
                    accepted_reply(result)

    def test_complete_visible_record_is_unusable_after_nonzero_exit_or_signal(self):
        for callback, status in [("os._exit(7)", 7), ("os.kill(os.getpid(),signal.SIGTERM)", -15)]:
            with self.subTest(callback=callback):
                result = self.fault(
                    "import atexit,os,signal\ndef fail():\n    " + callback + "\natexit.register(fail)\n"
                )
                self.assertEqual(result.returncode, status)
                self.assertEqual(decode_record(result.stdout)["text"].encode("utf-8"), DEFAULT_REPLY)
                with self.assertRaises(ValueError):
                    accepted_reply(result)

    def test_transport_failure_or_truncation_metadata_rejects_a_complete_visible_record(self):
        result = self.invoke(self.action())
        self.assertEqual(decode_record(result.stdout)["text"].encode("utf-8"), DEFAULT_REPLY)
        for metadata in [{"transport_error": True}, {"truncated": True}]:
            with self.subTest(metadata=metadata), self.assertRaises(ValueError):
                accepted_reply(result, **metadata)

    def test_timeout_after_complete_record_does_not_establish_success(self):
        with tempfile.TemporaryDirectory(prefix="pstack-reply-timeout-") as temporary:
            Path(temporary, "sitecustomize.py").write_text(
                "import atexit,time\natexit.register(time.sleep,30)\n", encoding="utf-8")
            process = subprocess.Popen([sys.executable, str(SCRIPT)], stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       env={**os.environ, "PYTHONPATH": temporary})
            try:
                with self.assertRaises(subprocess.TimeoutExpired) as timeout:
                    process.communicate(self.action(), timeout=2)
                self.assertEqual(decode_record(timeout.exception.output)["text"].encode("utf-8"), DEFAULT_REPLY)
            finally:
                if process.poll() is None:
                    process.kill()
                stdout, stderr = process.communicate(timeout=5)
            result = subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)
            self.assertNotEqual(result.returncode, 0)
            with self.assertRaises(ValueError):
                accepted_reply(result, transport_error=True)

    def test_failed_final_outer_lf_is_fatal_even_when_the_object_is_complete(self):
        result = self.fault(
            "import os\noriginal=os.write\nfirst=True\ndef lose_lf(fd,data):\n"
            "    global first\n    if fd != 1: return original(fd,data)\n"
            "    if first:\n        first=False\n        return original(fd,data[:-1])\n"
            "    raise OSError('final LF delivery failed')\nos.write=lose_lf\n"
        )
        self.assertEqual((result.returncode, result.stderr), (69, b"UNAVAILABLE: output I/O failed\n"))
        self.assertEqual(decode_record(result.stdout)["text"].encode("utf-8"), DEFAULT_REPLY)
        self.assertFalse(result.stdout.endswith(b"\n"))
        with self.assertRaises(ValueError):
            accepted_reply(result)

    def test_interrupted_writes_retry_the_same_record(self):
        result = self.fault(
            "import errno,os\noriginal=os.write\nfirst=True\ndef interrupted(fd,data):\n"
            "    global first\n    if fd==1 and first:\n        first=False\n"
            "        raise InterruptedError(errno.EINTR,'interrupted')\n"
            "    return original(fd,data[:3])\nos.write=interrupted\n"
        )
        self.assert_reply(result)

    def test_nonretryable_write_failure_is_not_retried(self):
        result = self.fault(
            "import errno,os\noriginal=os.write\nfirst=True\ndef blocked(fd,data):\n"
            "    global first\n    if fd==1 and first:\n        first=False\n"
            "        raise BlockingIOError(errno.EAGAIN,'blocked')\n"
            "    return original(fd,data)\nos.write=blocked\n"
        )
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (69, b"", b"UNAVAILABLE: output I/O failed\n"))

    def test_emergency_stderr_finishes_short_writes_and_tolerates_failed_sinks(self):
        for behavior, expected in [("original(fd,data[:3])", b"UNAVAILABLE: output I/O failed\n"),
                                   ("0", b"")]:
            with self.subTest(behavior=behavior):
                result = self.fault(
                    "import os\noriginal=os.write\ndef stopped(fd,data):\n"
                    "    return 0 if fd==1 else " + behavior + "\nos.write=stopped\n"
                )
                self.assertEqual((result.returncode, result.stdout, result.stderr), (69, b"", expected))
        result = self.fault("import os\ndef broken(fd,data):\n    raise OSError('sink lost')\nos.write=broken\n")
        self.assertEqual((result.returncode, result.stdout, result.stderr), (69, b"", b""))

    def test_encoding_fault_is_classified_before_any_output(self):
        for fault, kind, status in [("RuntimeError('encoding fault')", "internal", 70),
                                    ("MemoryError('encoding allocation')", "unavailable", 69)]:
            with self.subTest(fault=fault):
                result = self.fault(
                    "import json\noriginal=json.dumps\nfirst=True\ndef broken(*args,**kwargs):\n"
                    "    global first\n    if first:\n        first=False\n        raise " + fault + "\n"
                    "    return original(*args,**kwargs)\njson.dumps=broken\n"
                )
                self.record(result, kind, status)
                self.assertNotIn(b"My work", result.stdout)
        result = self.fault(
            "import json\noriginal=json.dumps\ndef invalid_ascii(value,**kwargs):\n"
            "    return '\\ud800' if value['kind']=='reply' else original(value,**kwargs)\njson.dumps=invalid_ascii\n"
        )
        self.record(result, "internal", 70)

    def test_failed_diagnostic_reporting_emits_no_partial_or_second_record(self):
        for document, status in [(self.action(), 70), (b"{}", 2)]:
            with self.subTest(status=status):
                result = self.fault(
                    "import json\ndef broken(*args,**kwargs):\n    raise RuntimeError('report encoding fault')\njson.dumps=broken\n",
                    document,
                )
                self.assertEqual((result.returncode, result.stdout, result.stderr), (status, b"", b""))

    def test_input_oserror_reports_unavailable_and_base_exceptions_keep_their_status(self):
        result = self.fault(
            "import sys\nclass BrokenInput:\n    @property\n    def buffer(self):\n"
            "        raise OSError('input I/O failed')\nsys.stdin=BrokenInput()\n"
        )
        self.record(result, "unavailable", 69)
        for exception, statuses in [("SystemExit(17)", [17]), ("KeyboardInterrupt()", [-2, 130])]:
            with self.subTest(exception=exception):
                interrupted = self.fault(
                    "import sys\nclass InterruptedInput:\n    @property\n    def buffer(self):\n"
                    "        raise " + exception + "\nsys.stdin=InterruptedInput()\n"
                )
                self.assertIn(interrupted.returncode, statuses)
                self.assertEqual(interrupted.stdout, b"")
                self.assertNotIn(b"UNAVAILABLE:", interrupted.stderr)
                self.assertNotIn(b"INTERNAL:", interrupted.stderr)



if __name__ == "__main__":
    unittest.main()
