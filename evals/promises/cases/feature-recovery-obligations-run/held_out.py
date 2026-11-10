import builtins
import csv
import errno
import fcntl
import io
import json
import os
import re
import runpy
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

CRASH = 75
JOURNAL = "deliveries.jsonl"
ROWS = [
    {"id": "z-2", "name": "Delta", "kind": "service"},
    {"id": "b-9", "name": "Bravo", "kind": "library"},
    {"id": "a-1", "name": "Alpha", "kind": "tool"},
]


def journal_state(path):
    try:
        with path.open("rb") as stream:
            return os.fstat(stream.fileno()).st_ino, stream.read()
    except FileNotFoundError:
        return None, b""


def complete(data):
    return data[:data.rfind(b"\n") + 1]


def install_fault(journal, mode, fd, records):
    raw_open, raw_write, raw_sync, raw_sleep = io.open, os.write, os.fsync, time.sleep
    raw_wait = threading.Event.wait
    _, initial_data = journal_state(journal)
    synced = complete(initial_data)
    visible, visible_inode, ids = b"", None, set()
    fired = 0

    def emit(kind, value=None):
        raw_write(fd, (json.dumps([kind, value]) + "\n").encode())

    def target(handle):
        try:
            stat = journal.stat()
            current = os.fstat(handle)
            return (current.st_dev, current.st_ino) == (stat.st_dev, stat.st_ino)
        except OSError:
            return False

    def state():
        try:
            with raw_open(journal, "rb") as stream:
                return os.fstat(stream.fileno()).st_ino, stream.read()
        except FileNotFoundError:
            return None, b""

    def observe():
        nonlocal visible, visible_inode
        inode, data = state()
        prefix = complete(data)
        if visible and (inode != visible_inode or not prefix.startswith(visible)):
            emit("damage", "the journal removed or replaced a previously visible delivery")
            return data
        for index, line in enumerate(prefix[len(visible):].splitlines(), visible.count(b"\n")):
            try:
                row = json.loads(line)
            except ValueError:
                emit("damage", "the journal exposed a malformed complete delivery")
                continue
            if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                emit("damage", "the journal exposed a malformed complete delivery")
                continue
            emit("visible", row)
            if row["id"] in ids:
                emit("damage", "appended a previously delivered record")
            elif index >= len(records) or row != records[index]:
                emit("damage", "the journal exposed a delivery outside the expected source order or payload")
            ids.add(row["id"])
        visible, visible_inode = prefix, inode
        return data

    def append(handle, data, write, flush):
        nonlocal fired
        before = observe()
        if data:
            emit("write", synced.count(b"\n"))
        before_fault = ((mode in ("transient", "exhaust") and synced)
                        or (mode == "transient-first" and not synced))
        if data and before_fault and (mode == "exhaust" or fired < 2):
            fired += 1
            emit("before", len(before))
            raise OSError(errno.EIO, "held-out append failure")
        if mode == "partial" and synced and data:
            cut = bytes(data).find(b"\n") if not isinstance(data, str) else data.find("\n")
            write(data[:max(1, cut // 2)])
            flush()
            raw_sync(handle)
            emit("partial", len(state()[1]))
            os._exit(CRASH)
        count = write(data)
        observe()
        return count

    def synced_write(handle):
        nonlocal fired, synced
        if not target(handle):
            return
        prefix = complete(observe())
        emit("sync", len(prefix))
        if len(prefix) <= len(synced):
            return
        synced = prefix
        if mode in ("lost", "crash") and not fired:
            fired += 1
            emit(mode, len(synced))
            if mode == "crash":
                os._exit(CRASH)
            raise OSError(errno.EIO, "held-out lost acknowledgment")

    def observing_sync(sync):
        def run(handle):
            sync(handle)
            synced_write(handle)
        return run

    class JournalFile:
        def __init__(self, stream):
            self.stream = stream

        def __getattr__(self, name):
            return getattr(self.stream, name)

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, *exc):
            result = self.stream.__exit__(*exc)
            observe()
            return result

        def __iter__(self):
            return iter(self.stream)

        def write(self, data):
            return append(self.stream.fileno(), data, self.stream.write, self.stream.flush)

        def flush(self):
            self.stream.flush()
            observe()

        def close(self):
            self.stream.close()
            observe()

        def truncate(self, size=None):
            observe()
            size = self.stream.tell() if size is None else size
            result = self.stream.truncate(size)
            observe()
            return result

    def observed_open(*args, **kwargs):
        stream = raw_open(*args, **kwargs)
        return JournalFile(stream) if target(stream.fileno()) else stream

    def observed_write(handle, data):
        if not target(handle):
            return raw_write(handle, data)
        return append(handle, data, lambda data: raw_write(handle, data), lambda: None)

    def observed_sleep(seconds):
        raw_sleep(seconds)
        emit("sleep", seconds)

    def observed_wait(event, timeout=None):
        ready = raw_wait(event, timeout)
        if timeout is not None:
            emit("wait", 0 if timeout <= 0 else None if ready else timeout)
        return ready

    def same(path):
        if isinstance(path, int):
            return target(path)
        return isinstance(path, (str, bytes)) and os.path.abspath(os.fsdecode(path)) == str(journal)

    def audit(event, args):
        if event == "open":
            addressed = args[2] & os.O_TRUNC and same(args[0])
        elif event in ("os.remove", "os.rename", "os.truncate"):
            addressed = any(same(path) for path in args[:2 if event == "os.rename" else 1])
        else:
            return
        if addressed:
            observe()
            emit("mutation-attempt", event)

    observe()
    sys.addaudithook(audit)
    builtins.open = io.open = observed_open
    os.write, os.fsync, time.sleep = observed_write, observing_sync(raw_sync), observed_sleep
    threading.Event.wait = observed_wait
    if hasattr(os, "fdatasync"):
        os.fdatasync = observing_sync(os.fdatasync)
    if hasattr(fcntl, "F_FULLFSYNC"):
        raw_fcntl = fcntl.fcntl

        def observed_fcntl(handle, command, *args):
            result = raw_fcntl(handle, command, *args)
            if command == fcntl.F_FULLFSYNC:
                synced_write(handle if isinstance(handle, int) else handle.fileno())
            return result

        fcntl.fcntl = observed_fcntl
    return observe


def run_cli(image, mode, fd, records, args):
    observe = None
    if mode != "plain":
        store = Path(args[args.index("--store") + 1])
        observe = install_fault(store / JOURNAL, mode, fd, records)
    os.chdir(image)
    sys.path.insert(0, image)
    sys.argv = ["relay", *args]
    try:
        runpy.run_module("relay", run_name="__main__", alter_sys=True)
    finally:
        if observe is not None:
            observe()


def invoke(image, scratch, mode, *args, records=None):
    env = {"HOME": str(scratch), "TMPDIR": str(scratch), "LANG": "en_US.UTF-8"}
    with tempfile.TemporaryFile(dir=scratch) as observations:
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-S", "-B", __file__, "--child", str(image), mode,
                 str(observations.fileno()), json.dumps(records), *map(str, args)],
                capture_output=True, timeout=7, env=env, pass_fds=(observations.fileno(),))
            code, stdout = proc.returncode, proc.stdout
        except subprocess.TimeoutExpired as error:
            code, stdout = None, error.stdout or b""
        observations.seek(0)
        events = []
        for index, line in enumerate(observations):
            if index == 512:
                events.append(["incomplete", "too many journal observations"])
                break
            try:
                events.append(json.loads(line))
            except ValueError:
                events.append(["incomplete", "journal observation ended mid-event"])
                break
        return code, stdout, events


def policy_options(help_text):
    if len(help_text) > 32768:
        return [], "CLI help exceeded the observation limit"
    declarations = []
    current = None
    for line in help_text.decode("utf-8", errors="replace").splitlines():
        if line.startswith("  -"):
            syntax, *description = re.split(r" {2,}", line.strip(), maxsplit=1)
            forms = [part.replace("=", " ", 1).split() for part in syntax.split(", ")]
            names = [form[0] for form in forms if form and re.fullmatch(r"--[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}|-[a-zA-Z0-9]", form[0])]
            scalar = any(len(form) == 2 and not form[1].startswith("-") and "..." not in form[1] for form in forms)
            current = None
            if names and "--store" not in names and scalar and all(len(form) <= 2 for form in forms):
                current = description
                declarations.append((max(names, key=lambda name: name.startswith("--")), current))
        elif current is not None and line.startswith("    "):
            current.append(line.strip())
        else:
            current = None

    options = []
    for name, description in declarations:
        text = " ".join(description).lower()
        extra = None
        if re.search(r"\b(?:retry attempts?|(?:maximum|total|number of) (?:write )?attempts?)\b", text) or (
                "attempts" in text and re.search(r"including (?:the )?(?:first|initial)", text)):
            extra = 0
        elif re.search(r"\b(?:maximum|number of|limit of) (?:write )?retries\b", text):
            extra = 1
        elif re.search(r"\b(?:seconds?|milliseconds?|delay|backoff)\b", text):
            continue
        default = re.search(r"\bdefault:?\s+(\d{1,3})\b", text)
        options.append((name, extra, int(default[1]) if default else None))
    declared = [option for option in options if option[1] is not None]
    options = declared or options
    if len(options) > 6:
        return [], "CLI help exposed more than six possible count options"
    return options, "CLI help did not expose an observable retry count"


def fixture(directory, rows, kind):
    feed = directory / f"partner.{kind}"
    if kind == "csv":
        with feed.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=ROWS[0])
            writer.writeheader()
            writer.writerows(rows)
    else:
        feed.write_text(json.dumps(rows), encoding="utf-8")
    return feed


def expected(rows):
    return [{"id": row["id"], "fields": {k: v for k, v in row.items() if k != "id"}} for row in rows]


def delivered(data):
    try:
        return [json.loads(line) for line in complete(data).splitlines()]
    except (ValueError, UnicodeError):
        return None


class Scenario:
    def __init__(self, image, scratch, name, rows, kind):
        self.image = image
        self.scratch = scratch
        self.directory = scratch / name
        self.directory.mkdir()
        self.feed = fixture(self.directory, rows, kind)
        self.original_feed = self.feed.read_bytes()
        self.store = self.directory / "store"
        self.journal = self.store / JOURNAL
        self.expected = expected(rows)
        self.observations = []
        self.breaches = []
        self.missing = []

    def run(self, mode="observe", flags=(), *, status=0, exact=True):
        prior_inode, prior = journal_state(self.journal)
        code, _, events = invoke(self.image, self.scratch, mode,
                                 "import", self.feed, "--store", self.store, *flags, records=self.expected)
        inode, data = journal_state(self.journal)
        rows = delivered(data)
        self.observations.append({"mode": mode, "policy": list(flags), "exit": code, "events": events,
                                  "records": rows, "partial_bytes": len(data) - len(complete(data))})
        if code is None:
            self.missing.append("CLI timed out")
        if complete(prior) and (inode != prior_inode or not data.startswith(complete(prior))):
            self.breaches.append("the journal changed an already delivered prefix")
        if self.feed.read_bytes() != self.original_feed:
            self.breaches.append("the importer changed the feed")
        self.breaches += [detail for event, detail in events if event == "damage"]
        incomplete = [detail for event, detail in events if event == "incomplete"]
        self.missing += incomplete
        if len(complete(data)) > len(complete(prior)):
            syncs = [size for event, size in events if event == "sync"]
            if not syncs:
                self.missing.append("no observed sync covered new deliveries")
            elif not incomplete and max(syncs) < len(complete(data)):
                self.breaches.append("the journal advanced beyond its observed synced prefix")
        if rows is None or rows != self.expected[:len(rows)]:
            self.breaches.append("journal records are malformed, duplicated, changed or out of order")
        fault = {"crash": "crash", "lost": "lost", "partial": "partial",
                 "exhaust": "before", "transient": "before", "transient-first": "before"}.get(mode)
        reached = not fault or any(event == fault for event, _ in events)
        if not reached:
            self.missing.append(f"the {mode} fault did not fire")
        if reached and code is not None:
            if status == "failure" and code == 0 or type(status) is int and code != status:
                self.breaches.append(f"{mode} exited {code}, expected {status}")
            if exact and (rows != self.expected or data != complete(data)):
                self.breaches.append("the journal does not contain exactly the expected deliveries")
        return events, rows, data

    def resume(self):
        self.run()
        _, before = journal_state(self.journal)
        self.run()
        if journal_state(self.journal)[1] != before:
            self.breaches.append("a repeated import changed the completed journal")

    def result(self):
        return {"status": "breach" if self.breaches else "unavailable" if self.missing else "pass",
                "detail": self.breaches + self.missing, "runs": self.observations}


def waits_between_attempts(events):
    observed = None
    waits = []
    for event, value in events:
        if event == "before":
            observed = False
        elif observed is not None and event == "write":
            waits.append(observed)
            observed = None
        elif observed is not None and event in ("sleep", "wait") and value is not None and value > 0:
            observed = True
    return waits


def fault_count(run):
    return sum(event == "before" for event, _ in run["events"])


def assess_retries(check, bound):
    run = check.observations[0]
    attempts = fault_count(run)
    if not attempts:
        return
    if bound is not None and (attempts > bound or (run["exit"] is not None and attempts != bound)):
        check.breaches.append("write attempts differ from the configured policy")
    if not all(waits_between_attempts(run["events"])):
        check.missing.append("backoff between retry attempts was not observed")
    if run["mode"] == "exhaust" and run["records"] != check.expected[:1]:
        check.breaches.append("retry exhaustion did not preserve the durable prefix")


def bind_policy(image, scratch, options, kind):
    candidates, trials = [], []
    suffix = "" if kind == "json" else f"-{kind}"
    for index, (option, declared, default) in enumerate(options):
        measured = []
        for value in (2, 4):
            check = Scenario(image, scratch, f"policy-{index}-{value}{suffix}", ROWS, kind)
            check.run("exhaust", (option, str(value)), status="failure", exact=False)
            measured.append(check)
        runs = [check.observations[0] for check in measured]
        counts = [fault_count(run) for run in runs]
        trials.append(f"{option} observed {counts[0]} and {counts[1]} attempted writes")
        if declared is not None and len(options) == 1:
            return (option, declared, default, measured), trials
        if all(run["exit"] not in (0, None) for run in runs) and counts in ([2, 4], [3, 5]):
            offset = counts[0] - 2
            candidates.append((option, declared if declared is not None else offset, default, measured))
    return (candidates[0] if len(candidates) == 1 else None), trials


def recover(image, scratch):
    checks = {}

    def scenario(name, kind, rows=ROWS):
        checks[name] = Scenario(image, scratch, name, rows, kind)
        return checks[name]

    code, help_text, _ = invoke(image, scratch, "plain", "import", "--help")
    options, reason = policy_options(help_text) if code == 0 else ([], "CLI help was unavailable")
    for kind in ("json", "csv"):
        suffix = "" if kind == "json" else f"-{kind}"
        scenario(f"repeat-{kind}", kind).resume()
        scenario(f"empty-{kind}", kind, []).resume()
        single = scenario(f"singleton-{kind}", kind, ROWS[:1])
        single.run("crash", status=CRASH)
        single.resume()

        crash = scenario(f"synced-crash{suffix}", kind)
        events, rows, data = crash.run("crash", status=CRASH, exact=False)
        if any(event == "crash" for event, _ in events) and (not rows or data != complete(data)):
            crash.breaches.append("the crash did not leave a complete durable prefix")
        crash.resume()
        partial = scenario(f"partial-tail{suffix}", kind)
        events, rows, data = partial.run("partial", status=CRASH, exact=False)
        if any(event == "partial" for event, _ in events) and (not rows or data == complete(data)):
            partial.breaches.append("the crash did not leave a partial tail after a durable prefix")
        partial.resume()

        binding, trials = bind_policy(image, scratch, options, kind)
        default = scenario(f"exhaust-default{suffix}", kind)
        default.run("exhaust", status="failure", exact=False)
        default_bound = binding[2] + binding[1] if binding and binding[2] is not None else None
        assess_retries(default, default_bound)
        default.resume()

        if binding:
            option, extra, _, measured = binding
            for value, check in zip((2, 4), measured):
                checks[f"exhaust-{value}{suffix}"] = check
                assess_retries(check, value + extra)
                check.resume()
        else:
            for value in (2, 4):
                scenario(f"exhaust-{value}{suffix}", kind).missing.extend([reason, *trials])

        for mode, value in (("transient", 4), ("transient-first", 4), ("lost", 4), ("lost", 1)):
            check = scenario(f"{mode}-{value}{suffix}", kind)
            if not binding:
                check.missing.append(reason)
                continue
            args = (option, str(value))
            status = "any" if mode == "lost" and value == 1 else 0
            events, rows, data = check.run(mode, args, status=status, exact=status == 0)
            if mode == "lost" and any(event == "lost" for event, _ in events):
                exit_code = check.observations[-1]["exit"]
                durable = next(value for event, value in events if event == "lost")
                if not rows or len(complete(data)) < durable:
                    check.breaches.append("the lost acknowledgment erased a synced delivery")
                if exit_code == 0 and rows != check.expected:
                    check.breaches.append("the importer reported success with missing deliveries")
            elif mode.startswith("transient"):
                assess_retries(check, 2)
            check.resume()
    return {name: check.result() for name, check in checks.items()}


if __name__ == "__main__":
    if sys.argv[1] == "--child":
        run_cli(sys.argv[2], sys.argv[3], int(sys.argv[4]), json.loads(sys.argv[5]), sys.argv[6:])
    else:
        print(json.dumps(recover(Path(sys.argv[1]), Path(sys.argv[2]))))
