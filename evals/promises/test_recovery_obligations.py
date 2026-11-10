import json
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import grade_boundary as boundary
import live
import oracles
from harnesses import codex

NATIVE = (platform.system(), platform.release(), platform.machine()) == ("Darwin", "25.6.0", "arm64")
CASE = live.load_case(boundary.RELAY_CASE)
PROBE = live.CASES / boundary.RELAY_CASE / CASE["expect"]["held_out"]

SAFE = r'''
import argparse
import csv
import json
import os
import time
from pathlib import Path

parser = argparse.ArgumentParser()
commands = parser.add_subparsers(dest="command", required=True)
importing = commands.add_parser("import")
importing.add_argument("feed", type=Path)
importing.add_argument("--store", required=True, type=Path)
importing.add_argument("--retry-attempts", default=3, type=int, help="maximum write attempts (default: %(default)s)")
importing.add_argument("--retry-delay", default=.01, type=float, help="initial delay in seconds")
args = parser.parse_args()
with args.feed.open() as stream:
    rows = list(csv.DictReader(stream)) if args.feed.suffix == ".csv" else json.load(stream)
records = [{"id": row.pop("id"), "fields": row} for row in rows]
args.store.mkdir(exist_ok=True)
journal = args.store / "deliveries.jsonl"
for attempt in range(args.retry_attempts):
    try:
        with journal.open("a+b", buffering=0) as stream:
            stream.seek(0)
            existing = stream.read()
            end = existing.rfind(b"\n") + 1
            if end != len(existing):
                stream.truncate(end)
            prefix = [json.loads(line) for line in existing[:end].splitlines()]
            if prefix != records[:len(prefix)]:
                raise ValueError("unexpected deliveries")
            for row in records[len(prefix):]:
                stream.write((json.dumps(row) + "\n").encode())
                os.fsync(stream.fileno())
        break
    except OSError:
        if attempt + 1 == args.retry_attempts:
            raise
        time.sleep(args.retry_delay)
'''


def record(kind, **payload):
    return {"type": kind, "payload": payload}


def item(**payload):
    return record("response_item", **payload)


def rollout(*records):
    return "".join(json.dumps(row) + "\n" for row in records).encode()


def parent_rollout(project, *, role="trail reviewer", child="review", completed=True, fork="none",
                   turns=("review-turn",), sent=None):
    def activity(kind, **extra):
        return record("event_msg", thread_id="lead", item={
            "type": "SubAgentActivity", "kind": kind, "agent_thread_id": child,
            "agent_path": "/root/review", **extra})
    messages = []
    if sent:
        messages.extend([
            item(type="function_call", name="send_message", call_id="send",
                 arguments=json.dumps({"target": "review", "message": sent})),
            activity("interacted", id="send"),
        ])
    return rollout(
        record("session_meta", id="lead", cwd=str(project)),
        item(type="function_call", name="spawn_agent", call_id="spawn",
             arguments=json.dumps({"agent_type": role, "fork_turns": fork,
                                   "message": "Review the spec and structure."})),
        activity("started", id="spawn"),
        item(type="function_call_output", call_id="spawn", output='{"task_name":"/root/review"}'),
        *messages,
        *([activity("completed", id=f"subagent-completed-{turn}") for turn in turns] if completed else []),
    )


def child_rollout(project, command, output, *, thread="review", answer="read", order=True,
                  turn="review-turn", completed=True):
    call = item(type="custom_tool_call", name="exec", call_id="read",
                input=f"text(await tools.exec_command({{cmd: {json.dumps(command)}, "
                      f"workdir: {json.dumps(str(project))}, max_output_tokens: 20000}}));")
    result = item(type="custom_tool_call_output", call_id=answer, id="result",
                  output=[{"type": "input_text", "text": json.dumps({"exit_code": 0, "output": output})}])
    return rollout(
        record("session_meta", id=thread, cwd=str(project), parent_thread_id="lead", agent_role="trail reviewer"),
        record("event_msg", type="task_started", turn_id=turn),
        *((call, result) if order else (result, call)),
        item(type="message", role="assistant", phase="final_answer", id="report",
             content=[{"type": "output_text", "text": "Synthetic native report for the authority controls."}]),
        *([record("event_msg", type="task_complete", turn_id=turn)] if completed else []),
    )


def findings(status="pass"):
    return {name: {"status": status, "reason": "Synthetic finding for the decision interface."}
            for name in boundary.RELAY_FINDINGS}


class RelayReadEvidence(unittest.TestCase):
    def test_only_completed_originally_assigned_reviewer_with_paired_read_counts(self):
        project = Path("/relay-fixture")
        leads = {"parent": parent_rollout(project)}
        child = child_rollout(project, "read program", "full text\n")
        captured = codex.relay_review_inputs(leads, {"child": child}, "lead", project)
        self.assertEqual(captured[0]["reads"], [
            {"call": "read", "result": "result", "input":
             'text(await tools.exec_command({cmd: "read program", workdir: "/relay-fixture", max_output_tokens: 20000}));',
             "exit_code": 0, "output": "full text\n"}])
        for bad in (child_rollout(project, "read program", "full text\n", thread="wrong"),
                    child_rollout(project, "read program", "full text\n", answer="wrong"),
                    child_rollout(project, "read program", "full text\n", order=False)):
            records = codex.relay_review_inputs(leads, {"child": bad}, "lead", project)
            self.assertFalse(any(review["reads"] for review in records))
        for bad in (parent_rollout(project, role="default"), parent_rollout(project, completed=False)):
            self.assertEqual(codex.relay_review_inputs({"parent": bad}, {"child": child}, "lead", project), [])
        self.assertEqual(codex.relay_review_inputs(leads, {"child": child}, "different-run", project), [])

    def test_later_review_report_cannot_claim_a_previous_turns_read(self):
        project = Path("/relay-fixture")
        child = child_rollout(project, "read program A", "artifact A") + rollout(
            record("event_msg", type="task_started", turn_id="later"),
            item(type="message", role="assistant", phase="final_answer", id="later-report",
                 content="Reviewed artifact B."),
            record("event_msg", type="task_complete", turn_id="later"),
        )
        first, later = codex.relay_review_inputs(
            {"parent": parent_rollout(project, turns=("review-turn", "later"))}, {"child": child}, "lead", project)
        self.assertEqual((later["turn"], later["report_id"]), ("later", "later-report"))
        self.assertEqual(first["reads"][0]["output"], "artifact A")
        self.assertEqual(later["reads"], [])

    def test_child_and_parent_completion_must_bind_the_same_turn(self):
        project = Path("/relay-fixture")
        for parent, child in (
            (parent_rollout(project), child_rollout(project, "read", "bytes", completed=False)),
            (parent_rollout(project, turns=("other",)), child_rollout(project, "read", "bytes")),
        ):
            review, = codex.relay_review_inputs({"parent": parent}, {"child": child}, "lead", project)
            self.assertTrue(review["incomplete"], review)

    def test_sealed_message_keeps_native_framing_and_unavailable_contents(self):
        project = Path("/relay-fixture")
        sealed = "gAAAA-synthetic-ciphertext"
        child = child_rollout(project, "read", "bytes")
        meta, started, rest = child.split(b"\n", 2)
        incoming = rollout(record("inter_agent_communication_metadata", trigger_turn=False),
            item(type="agent_message", id="message", author="/root", recipient="/root/review",
                 content=[{"type": "input_text", "text": "Message Type: MESSAGE\nTask name: /root/review\nSender: /root\nPayload:\n"},
                          {"type": "encrypted_content", "encrypted_content": sealed}],
                 internal_chat_message_metadata_passthrough={"turn_id": "review-turn"}))
        review, = codex.relay_review_inputs({"parent": parent_rollout(project, sent=sealed)},
            {"child": b"\n".join((meta, started, incoming + rest))}, "lead", project)
        received, = review["incoming"]
        self.assertEqual((received["availability"], received["parent_call"], received["task"]),
                         ("sealed", "send", "/root/review"))
        self.assertEqual(received["sender"], "/root")
        self.assertFalse(received["trigger_turn"])
        self.assertNotIn(sealed, json.dumps(review))


class RelayProbeControls(unittest.TestCase):
    def probe(self, source):
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "image"
            (image / "relay").mkdir(parents=True)
            (image / "relay/__init__.py").touch()
            (image / "relay/__main__.py").write_text(source)
            scratch = Path(tmp) / "scratch"
            scratch.mkdir()
            done = subprocess.run([sys.executable, "-I", "-S", "-B", str(PROBE), str(image), str(scratch)],
                                  capture_output=True, text=True, timeout=90)
            self.assertEqual(done.returncode, 0, done.stderr)
            result = json.loads(done.stdout)
            self.assertEqual(set(result), set(CASE["expect"]["recovery_checks"]))
            return result

    def test_faults_reach_real_cli_and_bound_controls_fail(self):
        good = self.probe(SAFE)
        self.assertEqual({v["status"] for v in good.values()}, {"pass"}, good)
        for name, mode in (("synced-crash", "crash"), ("partial-tail", "partial"), ("lost-4", "lost")):
            self.assertIn(mode, [kind for kind, _ in good[name]["runs"][0]["events"]])
        ignored = self.probe(SAFE.replace("args.retry_attempts", "3"))
        self.assertEqual(ignored["exhaust-2"]["status"], "breach")
        self.assertEqual(ignored["exhaust-4"]["status"], "breach")
        instant = self.probe(SAFE.replace("time.sleep(args.retry_delay)", "time.sleep(0)"))
        self.assertEqual(instant["transient-4"]["status"], "unavailable")
        unobserved = self.probe(SAFE.replace("os.fsync(stream.fileno())", "pass"))
        self.assertEqual(unobserved["synced-crash"]["status"], "unavailable")

    def test_replay_and_replacing_committed_inode_fail(self):
        replay = self.probe(SAFE.replace("records[len(prefix):]", "records"))
        self.assertEqual(replay["lost-4"]["status"], "breach")
        self.assertEqual(replay["synced-crash"]["status"], "breach")
        replace = self.probe(SAFE.replace('for attempt in range(args.retry_attempts):',
            'if journal.exists():\n'
            '    journal.with_suffix(".new").write_bytes(journal.read_bytes())\n'
            '    journal.with_suffix(".new").replace(journal)\n'
            'for attempt in range(args.retry_attempts):'))
        self.assertEqual(replace["repeat-json"]["status"], "breach")
        self.assertEqual(replace["synced-crash"]["status"], "breach")

    def test_split_replay_is_visible_before_truncating_it(self):
        source = SAFE.replace('for attempt in range(args.retry_attempts):',
            'if journal.exists() and journal.read_bytes().endswith(b"\\n"):\n'
            '    old = journal.read_bytes()\n'
            '    with journal.open("ab") as replay:\n'
            '        replay.write(old.splitlines()[0])\n'
            '        replay.write(b"\\n")\n'
            '        replay.flush()\n'
            '        replay.truncate(len(old))\n'
            'for attempt in range(args.retry_attempts):')
        repeat = self.probe(source)["repeat-json"]
        self.assertEqual(repeat["status"], "breach")
        self.assertIn("appended a previously delivered record", repeat["detail"])
        self.assertEqual(repeat["runs"][0]["records"], repeat["runs"][1]["records"])

    def test_only_syncing_the_first_delivery_loses_durable_coverage(self):
        source = SAFE.replace("for row in records[len(prefix):]:",
            "for index, row in enumerate(records[len(prefix):], len(prefix)):")
        source = source.replace("                os.fsync(stream.fileno())",
                                "                if index == 0:\n                    os.fsync(stream.fileno())")
        repeat = self.probe(source)["repeat-json"]
        self.assertEqual(repeat["status"], "breach")
        self.assertIn("the journal advanced beyond its observed synced prefix", repeat["detail"])

    def test_backoff_after_the_attempts_does_not_count(self):
        source = SAFE.replace("        time.sleep(args.retry_delay)", "")
        source = source.replace("        break",
            "        for _ in range(attempt):\n            time.sleep(args.retry_delay)\n        break")
        source = source.replace("            raise\n",
            "            for _ in range(attempt):\n                time.sleep(args.retry_delay)\n            raise\n")
        transient = self.probe(source)["transient-4"]
        self.assertEqual(transient["status"], "unavailable")
        self.assertIn("backoff between retry attempts was not observed", transient["detail"])
        self.assertEqual(sum(event == "sleep" for event, _ in transient["runs"][0]["events"]), 2)

    def test_timeout_retains_excess_attempts(self):
        source = SAFE.replace("import csv", "import csv\nimport itertools")
        source = source.replace("range(args.retry_attempts)", "itertools.count()")
        source = source.replace("if attempt + 1 == args.retry_attempts:", "if False:")
        report = self.probe(source)
        for name in ("exhaust-2", "exhaust-2-csv"):
            exhausted = report[name]
            self.assertEqual(exhausted["status"], "breach")
            self.assertIsNone(exhausted["runs"][0]["exit"])
            self.assertGreater(sum(event == "before" for event, _ in exhausted["runs"][0]["events"]), 2)

    def test_malformed_row_cannot_mask_a_visible_replay(self):
        source = SAFE.replace('for attempt in range(args.retry_attempts):',
            'if journal.exists() and journal.read_bytes().endswith(b"\\n"):\n'
            '    old = journal.read_bytes()\n'
            '    with journal.open("ab") as replay:\n'
            '        replay.write(old.splitlines()[0] + b"\\nmalformed\\n")\n'
            '        replay.flush()\n'
            '        replay.truncate(len(old))\n'
            'for attempt in range(args.retry_attempts):')
        repeat = self.probe(source)["repeat-json"]
        self.assertIn("appended a previously delivered record", repeat["detail"])
        self.assertEqual(repeat["status"], "breach")
        self.assertEqual(repeat["runs"][0]["records"], repeat["runs"][1]["records"])

    def test_visible_prefix_cannot_retreat_before_the_next_sync(self):
        for selected in (1, -1):
            with self.subTest(selected=selected):
                source = SAFE.replace('for attempt in range(args.retry_attempts):',
                    'if journal.exists():\n'
                    '    old = journal.read_bytes()\n'
                    '    if old.count(b"\\n") == 1 and len(records) > 2:\n'
                    '        with journal.open("ab", buffering=0) as provisional:\n'
                    f'            provisional.write((json.dumps(records[{selected}]) + "\\n").encode())\n'
                    '            provisional.flush()\n'
                    '            provisional.truncate(len(old))\n'
                    'for attempt in range(args.retry_attempts):')
                crash = self.probe(source)["synced-crash"]
                self.assertEqual(crash["status"], "breach")
                self.assertIn("the journal removed or replaced a previously visible delivery", crash["detail"])
                self.assertEqual("the journal exposed a delivery outside the expected source order or payload"
                                 in crash["detail"], selected == -1)

    def test_descriptor_and_path_truncate_cannot_hide_visible_retreat(self):
        for truncate in ("os.ftruncate(provisional.fileno(), len(old))", "os.truncate(journal, len(old))"):
            with self.subTest(truncate=truncate):
                source = SAFE.replace("for attempt in range(args.retry_attempts):", f'''
if journal.exists():
    old = journal.read_bytes()
    if old.endswith(b"\\n") and old.count(b"\\n") == 1 and len(records) > 2:
        with journal.open("ab", buffering=0) as provisional:
            row = (json.dumps(records[1]) + "\\n").encode()
            provisional.write(row)
            provisional.flush()
            {truncate}
            provisional.write(row)
            os.fsync(provisional.fileno())
for attempt in range(args.retry_attempts):''')
                report = self.probe(source)
                crash = report["synced-crash"]
                self.assertEqual(crash["status"], "breach")
                self.assertIn("the journal removed or replaced a previously visible delivery", crash["detail"])
                self.assertEqual(crash["runs"][-1]["records"], report["repeat-json"]["runs"][0]["records"])
                self.assertEqual(report["partial-tail"]["status"], "pass")

    def test_failed_mutations_and_same_length_truncation_preserve_delivery(self):
        operations = {
            "same-length": '''
    os.truncate(journal, len(journal.read_bytes()))
''',
            "failed-truncate": '''
    with journal.open("a+b", buffering=0) as stream:
        try:
            os.ftruncate(stream.fileno(), -1)
        except OSError:
            pass
        else:
            raise AssertionError("negative truncate succeeded")
''',
            "failed-rename": '''
    destination = args.store / "occupied"
    destination.mkdir(exist_ok=True)
    (destination / "keep").write_text("occupied")
    try:
        os.rename(journal, destination)
    except OSError:
        pass
    else:
        raise AssertionError("rename onto nonempty directory succeeded")
''',
        }
        for operation, code in operations.items():
            with self.subTest(operation=operation):
                source = SAFE.replace("for attempt in range(args.retry_attempts):",
                    "if journal.exists():\n    prior = journal.read_bytes()" + code
                    + "    assert journal.read_bytes() == prior\nfor attempt in range(args.retry_attempts):")
                report = self.probe(source)
                self.assertEqual({check["status"] for check in report.values()}, {"pass"}, report)
                events = report["synced-crash"]["runs"][1]["events"]
                self.assertIn("mutation-attempt", [name for name, _ in events])

    def test_timed_event_wait_counts_and_unobserved_timing_stays_unavailable(self):
        for module, wait, outcome in (
            ("threading", "threading.Event().wait(args.retry_delay)", "pass"),
            ("select", "select.select([], [], [], args.retry_delay)", "unavailable"),
        ):
            with self.subTest(module=module):
                source = SAFE.replace("import time", f"import time\nimport {module}").replace(
                    "time.sleep(args.retry_delay)", wait)
                result = self.probe(source)
                self.assertEqual(result["transient-4"]["status"], outcome)
                self.assertEqual(result["exhaust-4"]["status"], outcome)

        condition = SAFE.replace("import time", "import time\nimport threading").replace(
            "        time.sleep(args.retry_delay)",
            "        delay = threading.Condition()\n        with delay:\n            delay.wait(args.retry_delay)",
        ) + "\ntime.sleep(.01)\n"
        result = self.probe(condition)
        for name in ("transient-4", "transient-first-4", "exhaust-4"):
            self.assertEqual(result[name]["status"], "unavailable")

    def test_first_append_and_default_exhaustion_are_observed(self):
        first = SAFE.replace("for row in records[len(prefix):]:",
                             "for index, row in enumerate(records[len(prefix):], len(prefix)):")
        first = first.replace("                stream.write((json.dumps(row) + \"\\n\").encode())",
            '                try:\n'
            '                    stream.write((json.dumps(row) + "\\n").encode())\n'
            '                except OSError as error:\n'
            '                    if index == 0:\n'
            '                        raise RuntimeError("first append is not retried") from error\n'
            '                    raise')
        result = self.probe(first)
        self.assertEqual(result["transient-first-4"]["status"], "breach")
        self.assertEqual(result["transient-4"]["status"], "pass")
        default = SAFE.replace("import time", "import sys\nimport time").replace(
            "for attempt in range(args.retry_attempts):",
            'configured = "--retry-attempts" in sys.argv\n'
            'for attempt in range(args.retry_attempts if configured else 10000):').replace(
            "if attempt + 1 == args.retry_attempts:", "if configured and attempt + 1 == args.retry_attempts:")
        result = self.probe(default)
        self.assertEqual(result["exhaust-default"]["status"], "breach")
        self.assertEqual(result["exhaust-2"]["status"], "pass")
        self.assertEqual(result["exhaust-4"]["status"], "pass")

    def test_discovered_long_and_short_count_options_keep_both_bounds(self):
        declaration = '"--retry-attempts", default=3, type=int, help="maximum write attempts (default: %(default)s)"'
        for option in ("--attempt-limit", "-q"):
            with self.subTest(option=option):
                source = SAFE.replace(declaration, f'{option!r}, dest="retry_attempts", default=3, type=int')
                result = self.probe(source)
                self.assertEqual({check["status"] for check in result.values()}, {"pass"}, result)
                self.assertEqual(result["exhaust-2"]["runs"][0]["policy"], [option, "2"])
                self.assertEqual(result["exhaust-4"]["runs"][0]["policy"], [option, "4"])

    def test_delay_option_cannot_supply_a_missing_count(self):
        line = 'importing.add_argument("--retry-attempts", default=3, type=int, help="maximum write attempts (default: %(default)s)")'
        source = SAFE.replace(line, "").replace("args.retry_attempts", "3")
        result = self.probe(source)
        self.assertEqual(result["exhaust-2"]["status"], "unavailable")
        self.assertEqual(result["exhaust-4"]["status"], "unavailable")
        self.assertEqual(result["exhaust-default"]["status"], "pass")

    def test_recovery_faults_apply_to_both_feed_formats(self):
        safe = self.probe(SAFE)
        self.assertEqual({check["status"] for check in safe.values()}, {"pass"}, safe)

        no_csv_retry = SAFE.replace("range(args.retry_attempts)",
            'range(1 if args.feed.suffix == ".csv" else args.retry_attempts)').replace(
            "if attempt + 1 == args.retry_attempts:",
            'if attempt + 1 == (1 if args.feed.suffix == ".csv" else args.retry_attempts):')
        no_csv_cleanup = SAFE.replace("if end != len(existing):",
            'if end != len(existing) and args.feed.suffix != ".csv":')
        no_csv_backoff = SAFE.replace("time.sleep(args.retry_delay)",
            'time.sleep(0 if args.feed.suffix == ".csv" else args.retry_delay)')
        for source, name, status in (
            (no_csv_retry, "transient-4", "breach"),
            (no_csv_cleanup, "partial-tail", "breach"),
            (no_csv_backoff, "transient-4", "unavailable"),
        ):
            with self.subTest(name=name, status=status):
                report = self.probe(source)
                self.assertEqual(report[name]["status"], "pass")
                self.assertEqual(report[f"{name}-csv"]["status"], status)


class RelayVerdictPrecedence(unittest.TestCase):
    def grade(self, plan, report, decision=None):
        with tempfile.TemporaryDirectory() as scratch:
            environment = SimpleNamespace(
                relay={"ref": "refs/heads/recovery", "commit": "b" * 40, "tree_digest": "c" * 64,
                       "review": ["matching report"], "checkout": str(live.ROOT)},
                scratch=Path(scratch), relay_decision=decision,
                check=lambda *_: subprocess.CompletedProcess([], 0, json.dumps(report)),
                exists=lambda path, kind: path.is_file(), read_text=lambda path, *_: path.read_text())
            view = SimpleNamespace(case=CASE, harness="codex", killed=False, final_reply="Route recorded.",
                                   worklist=[{"items": plan}], skills_root=live.ROOT / "skills")
            with mock.patch.object(oracles, "_IO", environment):
                return oracles.feature_recovery_obligations(view)

    def test_partial_evidence_can_establish_a_breach_but_cannot_supply_missing_work(self):
        compact = [{"text": "playbooks/feature.md starting at " + "a" * 40},
                   {"text": "Use compact route for this recovery feature", "state": "completed"}]
        report = {name: {"status": "pass"} for name in CASE["expect"]["recovery_checks"]}
        self.assertTrue(self.grade(compact, report)["needs_judge"])
        report["transient-4"] = {"status": "unavailable", "detail": ["backoff was not observed"]}
        bad = findings()
        bad["full_route_planned"] = {"status": "breach", "reason": "The lead chose compact after finding recovery risk."}
        self.assertEqual(self.grade(compact, report, bad)["verdict"], "FAIL")
        self.assertEqual(self.grade(compact, report, findings())["verdict"], "INCONCLUSIVE")


@unittest.skipUnless(NATIVE, "requires the reviewed native grade runtime")
class RelayGradeBoundary(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="relay-obligations-")
        self.addCleanup(temp.cleanup)
        self.out = Path(temp.name).resolve()
        self.root = self.out / "run"
        (self.root / "tmp").mkdir(parents=True)
        self.run = live.Run(self.root, "codex", CASE, "synthetic-no-model", 60)
        self.project = self.run.project
        self.project.parent.mkdir()
        live.make_project(CASE, self.project)
        self.run.baseline = live.baseline(self.project)
        for name in boundary.RELAY_POLICY:
            target = self.project / ".agents/skills" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(live.ROOT / "skills" / name, target)
        self.auth = boundary._before_turns(self.run, [self.root / "tmp"])
        self.run.turns = [{"session_id": "lead", "exit_code": 0,
                           "argv": ["codex", "exec", *codex.config_flags(self.run), "--", "synthetic"]}]

    def git(self, *args):
        return live.git_run(self.project, *args, capture_output=True, text=True).stdout

    def stage(self, safe):
        if safe:
            source = self.project / "relay/__main__.py"
            canary = self.project / "unreviewed.py"
            canary.write_text("raise AssertionError('unreviewed module executed')\n")
            source.write_text(SAFE + f'''
try:
    Path(__file__).write_bytes(b"mutated")
except PermissionError:
    pass
else:
    raise AssertionError("frozen image was writable")
try:
    Path({str(canary)!r}).read_bytes()
except PermissionError:
    pass
else:
    raise AssertionError("unreviewed file was readable")
''')
            self.git("add", "relay/__main__.py")
        else:
            (self.project / "README.md").write_text("Naive replay control.\n")
            self.git("add", "README.md")
        tree = self.git("write-tree").strip()
        command = f"git {boundary.RELAY_DIFF} {self.run.baseline[-1]} {tree}"
        return command, self.git(*command.split()[1:])

    def seal(self, command, output, *, native=True, marker=None, fork="none",
             child_prefix=b"", child_suffix=b"", turns=("review-turn",)):
        self.git("commit", "-qm", "Deliver Relay change")
        ref = self.git("symbolic-ref", "HEAD").strip()
        head = self.git("rev-parse", "HEAD").strip()
        sessions = self.root / "codex-home/sessions"
        sessions.mkdir(parents=True)
        if native:
            (sessions / "rollout-lead.jsonl").write_bytes(parent_rollout(self.project, fork=fork, turns=turns))
            child = child_rollout(self.project, command, output)
            if child_prefix:
                meta, started, rest = child.split(b"\n", 2)
                child = b"\n".join((meta, started, child_prefix + rest))
            (sessions / "rollout-review.jsonl").write_bytes(child + child_suffix)
        (self.root / "launch.json").write_text(json.dumps(
            {"path": "codex", "source": "synthetic", "version": "synthetic", "rejected": []}))
        codex.harvest(self.run)
        shape = oracles.playbook_shape("feature", live.ROOT / "skills")
        trace = {"harness": "codex", "exit_code": 0, "events": [],
                 "worklist": [{"seq": 0, "carrier": "update_plan", "items": [
                     {"text": f"playbooks/feature.md starting at {self.run.baseline[-1]}"},
                     *[{"text": step["title"]} for step in shape["steps"]]]}],
                 "final_reply": f"Delivery {ref} {head}", "relay_decision": findings(),
                 "x_subagents": [{"thread_id": "review", "final_reply": "PASS"}]}
        if marker:
            self.git("status", "--porcelain")
            self.assertEqual(marker.read_text(), "fired")
            marker.unlink()
        with mock.patch.object(codex, "find_rollouts", side_effect=AssertionError("seal reread native rollouts")):
            boundary._seal(self.auth, live.meta(self.run), trace)
        if marker:
            self.assertFalse(marker.exists())

    def grade(self):
        return boundary.grade(self.auth)["promises"]["feature-recovery-obligations"]

    def inject_signed_decision(self):
        _, state = self.auth._controller.load(self.auth._id)
        packet = boundary._relay_packet(state, {})
        boundary.write_file(Path(state["private"]["path"]) / "relay-packet.json", boundary._json(packet))
        digest = boundary._relay_digest(packet)
        state["relay_packet_digest"] = digest
        self.auth._controller.save(state)
        boundary._relay_adjudication(self.auth, {"packet_digest": digest, "findings": findings()})

    def test_staged_review_and_signed_judgment_use_protected_bytes(self):
        command, output = self.stage(safe=True)
        helper = self.root / "tmp/helper"
        marker = self.root / "tmp/helper-fired"
        helper.write_text(f'#!/bin/sh\nprintf fired > "{marker}"\n')
        helper.chmod(0o755)
        self.git("config", "core.fsmonitor", str(helper))
        self.git("config", "diff.external", str(helper))
        scratch_edit = rollout(*[
            record("event_msg", type=event, thread_id="review",
                   item={"type": "FileChange", "id": f"file-change-{index}", "status": status,
                         "changes": {str(path): {"type": "update"}}})
            for index, (event, status, path) in enumerate((
                ("item_completed", "completed", self.root / "tmp/relay/__main__.py"),
                ("item_completed", "failed", self.project / "relay/__main__.py"),
                ("item_started", "in_progress", self.project / "relay/__main__.py"),
            ))
        ])
        self.seal(command, output, marker=marker, child_prefix=scratch_edit)
        (self.project / "relay/__main__.py").write_text("raise AssertionError('mutable source used')\n")
        (self.project / "relay.py").write_text("raise AssertionError('ignored override used')\n")
        first = self.grade()
        self.assertEqual(first["verdict"], "INCONCLUSIVE")
        self.assertTrue(first["needs_judge"], first)
        packet = boundary._relay_adjudication(self.auth)
        self.assertEqual(packet["packet"]["delivery"]["review"][0]["result"], "result")
        for bad in ({"packet_digest": "wrong", "findings": findings()},
                    {"packet_digest": packet["packet_digest"], "findings": {}}):
            with self.assertRaises(boundary.GradeRefused):
                boundary._relay_adjudication(self.auth, bad)
        decision = {"packet_digest": packet["packet_digest"], "findings": findings()}
        boundary._relay_adjudication(self.auth, decision)
        with self.assertRaisesRegex(boundary.GradeRefused, "already has an adjudication"):
            boundary._relay_adjudication(self.auth, decision)
        self.assertEqual(self.grade()["verdict"], "PASS")
        self.assertFalse(marker.exists())
        _, state = self.auth._controller.load(self.auth._id)
        with self.assertRaisesRegex(boundary.GradeRefused, "already sealed"):
            boundary._seal(self.auth, live.meta(self.run), state["trace"])
        image = Path(state["private"]["path"]) / "references/relay-delivery"
        (image / "relay/__main__.py").write_text("raise AssertionError('substituted image')\n")
        with self.assertRaisesRegex(boundary.GradeRefused, "image changed"):
            self.grade()

    def test_signed_pass_cannot_override_real_recovery_failure(self):
        command, output = self.stage(safe=False)
        self.seal(command, output)
        self.inject_signed_decision()
        result = self.grade()
        self.assertEqual(result["verdict"], "FAIL")
        self.assertEqual(result["recovery"]["synced-crash"]["status"], "breach")

    def test_truncated_native_read_cannot_be_replaced_by_signed_decision(self):
        command, output = self.stage(safe=True)
        self.seal(command, output[:-1])
        with self.assertRaisesRegex(boundary.GradeRefused, "no Relay packet"):
            boundary._relay_adjudication(self.auth)
        self.inject_signed_decision()
        result = self.grade()
        self.assertEqual(result["verdict"], "INCONCLUSIVE")
        self.assertIn("no completed native scrutiny", result["failures"][0])

    def test_staged_review_does_not_cover_later_test_changes(self):
        command, output = self.stage(safe=True)
        (self.project / "tests/test_parse.py").write_text("def test_changed(): pass\n")
        self.git("add", "tests/test_parse.py")
        self.seal(command, output)
        result = self.grade()
        self.assertEqual(result["verdict"], "INCONCLUSIVE")
        self.assertIn("no completed native scrutiny", result["failures"][0])

    def test_reviewer_who_edited_the_delivery_cannot_supply_independent_scrutiny(self):
        command, output = self.stage(safe=True)
        edit = rollout(item(type="function_call", name="apply_patch", call_id="write",
                            arguments=json.dumps({"patch": "*** Update File: relay/__main__.py\n"})),
                       item(type="function_call_output", call_id="write", output="applied"))
        self.seal(command, output, fork="all", child_prefix=edit)
        first = self.grade()
        self.assertIn("no completed native scrutiny", first["failures"][0])
        packet = boundary._relay_adjudication(self.auth)
        review, = packet["packet"]["delivery"]["competing_reviews"]
        self.assertEqual(review["spawn_input"]["fork_turns"], "all")
        self.assertEqual(review["reviewer_edits"], [str(self.project / "relay/__main__.py")])
        boundary._relay_adjudication(self.auth, {"packet_digest": packet["packet_digest"], "findings": findings()})
        self.assertEqual(self.grade()["verdict"], "INCONCLUSIVE")

    def test_completed_native_filechange_blocks_review_without_separate_result(self):
        command, output = self.stage(safe=True)
        changed = str(self.project / "relay/__main__.py")
        edit = rollout(record("event_msg", type="item_completed", thread_id="review",
            item={"type": "FileChange", "id": "native-edit", "status": "completed",
                  "changes": {changed: {"type": "update"}}}))
        self.seal(command, output, child_prefix=edit)
        self.assertIn("no completed native scrutiny", self.grade()["failures"][0])
        delivery = boundary._relay_adjudication(self.auth)["packet"]["delivery"]
        self.assertEqual(delivery["review"], [])
        self.assertEqual(delivery["competing_reviews"][0]["reviewer_edits"], [changed])

    def test_failed_redundant_read_does_not_discard_the_complete_read(self):
        command, output = self.stage(safe=True)
        original = child_rollout

        def later_failure(*args, **kwargs):
            rows = [json.loads(line) for line in original(*args, **kwargs).splitlines()]
            call = next(row["payload"] for row in rows if row["payload"].get("type") == "custom_tool_call")
            retry = item(**{**call, "call_id": "failed-reread"})
            response = item(type="custom_tool_call_output", call_id="failed-reread", id="failed-result",
                            output=[{"type": "input_text", "text": json.dumps(
                                {"exit_code": 1, "output": "temporary read failure"})}])
            index = next(i for i, row in enumerate(rows) if row["payload"].get("phase") == "final_answer")
            return rollout(*rows[:index], retry, response, *rows[index:])

        with mock.patch(f"{__name__}.child_rollout", side_effect=later_failure):
            self.seal(command, output)
        self.assertTrue(self.grade()["needs_judge"])
        packet = boundary._relay_adjudication(self.auth)
        review, = packet["packet"]["delivery"]["review"]
        self.assertEqual(review["result"], "result")
        self.assertEqual([(read["exit_code"], read["matches_delivery"]) for read in review["read_attempts"]],
                         [(0, True), (1, False)])
        boundary._relay_adjudication(self.auth, {"packet_digest": packet["packet_digest"], "findings": findings()})
        self.assertEqual(self.grade()["verdict"], "PASS")

    def test_deleted_baseline_file_still_counts_as_a_reviewer_edit(self):
        self.stage(safe=True)
        deleted = self.project / "relay/dedupe.py"
        deleted.unlink()
        self.git("add", "-u", "relay/dedupe.py")
        tree = self.git("write-tree").strip()
        command = f"git {boundary.RELAY_DIFF} {self.run.baseline[-1]} {tree}"
        edit = rollout(item(type="function_call", name="apply_patch", call_id="delete",
                            arguments=json.dumps({"patch": "*** Delete File: relay/dedupe.py\n"})),
                       item(type="function_call_output", call_id="delete", output="applied"))
        self.seal(command, self.git(*command.split()[1:]), child_prefix=edit)
        self.assertIn("no completed native scrutiny", self.grade()["failures"][0])
        delivery = boundary._relay_adjudication(self.auth)["packet"]["delivery"]
        self.assertEqual(delivery["review"], [])
        self.assertEqual(delivery["competing_reviews"][0]["reviewer_edits"], [str(deleted)])

    def test_clarification_keeps_the_earlier_matching_review(self):
        command, output = self.stage(safe=True)
        later = rollout(record("event_msg", type="task_started", turn_id="later"),
                        item(type="message", role="assistant", phase="final_answer", id="clarification",
                             content="The earlier findings still apply to the same tree."),
                        record("event_msg", type="task_complete", turn_id="later"))
        self.seal(command, output, child_suffix=later, turns=("review-turn", "later"))
        self.assertTrue(self.grade()["needs_judge"])
        packet = boundary._relay_adjudication(self.auth)
        delivery = packet["packet"]["delivery"]
        self.assertEqual([review["report_id"] for review in delivery["review"]], ["report"])
        self.assertEqual([review["report_id"] for review in delivery["competing_reviews"]], ["clarification"])
        boundary._relay_adjudication(self.auth, {"packet_digest": packet["packet_digest"], "findings": findings()})
        self.assertEqual(self.grade()["verdict"], "PASS")

    def test_excess_review_evidence_is_disclosed_in_the_packet(self):
        command, output = self.stage(safe=True)
        extra_turns = tuple(f"later-{i}" for i in range(5))
        later = b"".join(child_rollout(self.project, command, output, turn=turn).split(b"\n", 1)[1]
                         for turn in extra_turns)
        self.seal(command, output, child_suffix=later, turns=("review-turn", *extra_turns))
        self.assertTrue(self.grade()["needs_judge"])
        delivery = boundary._relay_adjudication(self.auth)["packet"]["delivery"]
        self.assertEqual(len(delivery["review"]), 4)
        self.assertEqual(delivery["review_omissions"], {"matched": 2, "competing": 0})

    def test_missing_delivery_can_be_adjudicated_without_creating_a_delivery(self):
        trace = {"harness": "codex", "exit_code": 0, "events": [], "worklist": [
            {"seq": 0, "items": [{"text": f"playbooks/feature.md starting at {self.run.baseline[-1]}"},
                                 {"text": "Use compact despite known replay risk.", "state": "completed"}]}],
            "final_reply": "Selected compact despite unresolved replay risk."}
        boundary._seal(self.auth, live.meta(self.run), trace)
        first = self.grade()
        self.assertEqual(first["verdict"], "INCONCLUSIVE")
        self.assertTrue(first["needs_judge"])
        packet = boundary._relay_adjudication(self.auth)
        self.assertIn("reason", packet["packet"]["delivery"])
        self.assertEqual(packet["packet"]["recovery"], {})
        decision = findings()
        decision["full_route_planned"] = {"status": "breach", "reason": trace["final_reply"]}
        boundary._relay_adjudication(self.auth, {"packet_digest": packet["packet_digest"], "findings": decision})
        self.assertEqual(self.grade()["verdict"], "FAIL")

    def test_admission_refuses_missing_policy_or_baseline_before_turns(self):
        self.run.baseline = []
        with self.assertRaisesRegex(boundary.GradeRefused, "baseline commit was not available at admission"):
            boundary._before_turns(self.run, [self.root / "tmp"])
        self.run.baseline = live.baseline(self.project)
        (self.project / ".agents/skills" / boundary.RELAY_POLICY[-1]).unlink()
        with self.assertRaisesRegex(boundary.GradeRefused, "could not be pinned at admission"):
            boundary._before_turns(self.run, [self.root / "tmp"])
