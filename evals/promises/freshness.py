"""Bind live verdicts to the bytes they tested, and name the promises a change left without fresh evidence.

No model runs here. `record` copies verdicts a person already paid for into receipts.json with the digests of what
was tested. `check` compares those digests to the tree. `plan` picks the cheapest cases that would settle the debt.
"""

import argparse
import datetime
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import ledger
import report
from harnesses.login import ERROR, applicability

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RECEIPTS = HERE / "receipts.json"
POLICY = HERE / "freshness.json"
GRADER = ("oracles.py", "grade_boundary.py")
# A verdict that differs from the one it replaces is settled only by this many runs on the same bytes.
SETTLING_RUNS = 3
DEFAULT_TIMEOUT_S = 1800
FRESH, UNSETTLED, DISPUTED, STALE, MISSING, DEFERRED = "fresh", "unsettled", "disputed", "stale", "missing", "deferred"
DEBT = (UNSETTLED, DISPUTED, STALE, MISSING)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def tree_digest(paths, here=HERE):
    """One digest over every file under `paths`, so a case's receipt goes stale when its prompt, fixture, or history moves."""
    digest = hashlib.sha256()
    for root in paths:
        files = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
        for path in files:
            digest.update(path.relative_to(here).as_posix().encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def case_paths(case_id, spec, here=HERE):
    paths = [here / "cases" / case_id, here / "fixtures" / spec["fixture"]]
    if spec.get("history"):
        paths.append(here / "histories" / spec["history"])
    return [p for p in paths if p.exists()]


def load_cases(here=HERE):
    cases = {}
    for path in sorted((here / "cases").glob("*/case.json")):
        cases[path.parent.name] = json.loads(path.read_text(encoding="utf-8"))
    return cases


def runnable(spec):
    return spec.get("kind", "live") == "live" and not spec.get("deferred")


def timeout_for(spec, harness):
    limits = spec.get("timeout_s", DEFAULT_TIMEOUT_S)
    return limits if isinstance(limits, int) else limits.get(harness, limits.get("default", DEFAULT_TIMEOUT_S))


def tree_reader(root=ROOT):
    def read(path):
        target = root / path
        return target.read_bytes() if target.is_file() else None
    return read


def commit_reader(commit, root=ROOT):
    def read(path):
        shown = subprocess.run(["git", "-C", str(root), "cat-file", "blob", f"{commit}:{path}"], capture_output=True)
        return shown.stdout if shown.returncode == 0 else None
    return read


def owner_digests(owners, read):
    return {owner: (lambda data: sha(data) if data is not None else None)(read(owner)) for owner in sorted(owners)}


def grader_digest(here=HERE):
    return sha(b"".join((here / name).read_bytes() for name in GRADER))


def load_receipts(path=RECEIPTS):
    path = Path(path)
    return ledger.parse(path.read_text(encoding="utf-8")) if path.is_file() else {"version": 1, "receipts": {}}


def save_receipts(book, path=RECEIPTS):
    Path(path).write_text(ledger.canonical(book), encoding="utf-8")


def load_policy(path=POLICY):
    policy = json.loads(Path(path).read_text(encoding="utf-8"))
    unknown = sorted(set(policy["harnesses"]) - set(report.HARNESSES))
    if unknown:
        raise ValueError(f"freshness policy names unknown harnesses: {', '.join(unknown)}")
    return policy


def record(out, receipts, promises, cases, *, today, reader_at=commit_reader, read_now=None, grader=None, here=HERE):
    """Fold each graded run under `out` into `receipts`. Returns one line per cell written.

    A run already folded in is skipped, and so is a run on bytes other than the tree's when the receipt on record
    already matches the tree: an old output directory cannot displace current evidence. An arm case rewrites skill text before it runs, so its verdict is not evidence about the committed skill and is
    skipped. A run a dead login ended carries no verdict about the skill either.
    """
    grader = grader or grader_digest(here)
    read_now = read_now or tree_reader()
    lines = []
    for path in sorted(report.run_verdicts(out), key=lambda p: p.stat().st_mtime):
        raw = path.read_bytes()
        run = json.loads(raw)
        # Names the run, so folding the same output directory in twice counts each run once.
        run_id = sha(path.parent.name.encode() + b"\0" + raw)[:16]
        case_id, harness, commit = run.get("case"), run["harness"], run.get("skills_at")
        spec = cases.get(case_id)
        if spec is None or not commit or spec.get("skill_overlays"):
            lines.append(f"skipped {path.parent.name}: {'arm case' if spec and commit else 'no bound case or skills commit'}")
            continue
        trace = path.parent / "trace.json"
        model = json.loads(trace.read_text(encoding="utf-8")).get("model") if trace.is_file() else None
        read = reader_at(commit)
        case = tree_digest(case_paths(case_id, spec, here), here)
        for pid, result in sorted(run["promises"].items()):
            promise = promises.get(pid)
            verdict = result["verdict"]
            if promise is None or promise["check"] != "live" or result.get("not_applicable") or verdict == ERROR:
                continue
            inputs = {"case": case, "owners": owner_digests(promise["owners"], read)}
            cell = receipts["receipts"].setdefault(pid, {}).setdefault(harness, {})
            prior = cell.get(case_id)
            current = {"case": case, "owners": owner_digests(promise["owners"], read_now)}
            if prior and prior["inputs"] == current != inputs:
                lines.append(f"skipped {pid} {harness} {case_id}: the receipt on record tested the current tree and this run did not")
                continue
            if prior and prior["inputs"] == inputs and prior["grader"] == grader:
                if run_id in prior["runs"]:
                    continue
                counts, runs, previous = dict(prior["verdicts"]), prior["runs"], prior.get("previous")
            else:
                counts, runs, previous = {}, [], unanimous(prior["verdicts"]) if prior else None
            counts[verdict] = counts.get(verdict, 0) + 1
            entry = {"grader": grader, "inputs": inputs, "recorded": today, "runs": sorted([*runs, run_id]),
                     "skills_at": commit, "verdicts": counts}
            if previous:
                entry["previous"] = previous
            if model:
                entry["model"] = model
            cell[case_id] = entry
            lines.append(f"recorded {pid} {harness} {case_id}: {summary(counts)}" + (f" (was {previous})" if previous else ""))
    return lines


def unanimous(counts):
    return next(iter(counts)) if len(counts) == 1 else "MIXED"


def summary(counts):
    return ", ".join(f"{verdict} {n}" for verdict, n in sorted(counts.items()))


def entry_state(entry, inputs):
    """(state, reason) for one case receipt against the tree's current digests."""
    if entry["inputs"]["case"] != inputs["case"]:
        return STALE, "case, fixture, or history changed"
    moved = sorted(o for o, digest in inputs["owners"].items() if entry["inputs"]["owners"].get(o) != digest)
    if moved or set(entry["inputs"]["owners"]) != set(inputs["owners"]):
        return STALE, "owner changed: " + ", ".join(moved or sorted(set(entry["inputs"]["owners"]) ^ set(inputs["owners"])))
    audit = entry.get("audit")
    if audit and not audit["agrees"]:
        return DISPUTED, "a reader disagreed with the recorded verdict"
    runs = sum(entry["verdicts"].values())
    verdict = unanimous(entry["verdicts"])
    flipped = entry.get("previous") not in (None, verdict)
    if runs < SETTLING_RUNS and (verdict == "MIXED" or flipped):
        why = f"changed from {entry['previous']} to {verdict}" if flipped else "runs disagree"
        return UNSETTLED, f"{why} after {runs} run(s); needs {SETTLING_RUNS}"
    return FRESH, summary(entry["verdicts"])


def cells(receipts, promises, cases, harnesses, *, read=None, applies=None, here=HERE):
    """One row per live promise and policy harness: its state, reason, and the bound cases that could settle it."""
    read = read or tree_reader()
    applies = applies or (lambda pid, harness: not applicability(pid, harness).get("not_applicable"))
    bound = {}
    for case_id, spec in cases.items():
        for pid in spec.get("promises", []):
            bound.setdefault(pid, []).append(case_id)
    digests = {}
    rows = []
    for pid, promise in sorted(promises.items()):
        if promise["check"] != "live":
            continue
        ready = [c for c in bound.get(pid, []) if runnable(cases[c])]
        owners = owner_digests(promise["owners"], read)
        for harness in harnesses:
            if not applies(pid, harness):
                continue
            row = {"promise": pid, "harness": harness, "cases": ready, "owners": promise["owners"]}
            if not ready:
                rows.append({**row, "state": DEFERRED, "reason": "no runnable case"})
                continue
            states = []
            for case_id in ready:
                entry = receipts["receipts"].get(pid, {}).get(harness, {}).get(case_id)
                if entry is None:
                    states.append((MISSING, "no receipt", case_id))
                    continue
                if case_id not in digests:
                    digests[case_id] = tree_digest(case_paths(case_id, cases[case_id], here), here)
                states.append((*entry_state(entry, {"case": digests[case_id], "owners": owners}), case_id))
            # One bound case with fresh evidence covers the cell. Otherwise report the state closest to fresh.
            order = (FRESH, UNSETTLED, DISPUTED, STALE, MISSING)
            state, reason, case_id = min(states, key=lambda s: order.index(s[0]))
            rows.append({**row, "state": state, "reason": reason, "receipt_case": case_id if state != MISSING else None})
    return rows


def changed_files(base, root=ROOT):
    """Paths that differ between the merge base with `base` and the working tree, committed or not."""
    fork = subprocess.run(["git", "-C", str(root), "merge-base", base, "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    names = subprocess.run(["git", "-C", str(root), "diff", "--name-only", fork], check=True, capture_output=True, text=True).stdout
    return sorted(filter(None, names.splitlines()))


def touched(rows, changed, cases, here=HERE, root=ROOT):
    """The rows a change reaches: one of the promise's owners changed, or an input of one of its bound cases did."""
    changed = set(changed)
    prefixes = {}
    for case_id, spec in cases.items():
        prefixes[case_id] = [p.relative_to(root).as_posix() + "/" for p in case_paths(case_id, spec, here)]
    def hit(row):
        if changed & set(row["owners"]):
            return True
        return any(name.startswith(prefix) for case_id in row["cases"] for prefix in prefixes[case_id] for name in changed)
    return [row for row in rows if hit(row)]


def stale_grader(receipts, grader):
    return sum(1 for by_harness in receipts["receipts"].values() for by_case in by_harness.values()
               for entry in by_case.values() if entry["grader"] != grader)


def render_check(rows, blocking, regrade, quiet=False):
    counts = {}
    for row in rows:
        counts[row["state"]] = counts.get(row["state"], 0) + 1
    lines = [f"live promise cells: {len(rows)}" + "".join(f"; {state} {counts[state]}" for state in (FRESH, *DEBT, DEFERRED) if state in counts)]
    for row in rows:
        if row["state"] in DEBT and (not quiet or row["promise"] in blocking):
            mark = " [blocking]" if row["promise"] in blocking else ""
            lines.append(f"{row['state']:<9} {row['harness']:<11} {row['promise']}{mark}: {row['reason']}")
    if regrade:
        lines.append(f"{regrade} receipt(s) were graded by an earlier grader; regrade their saved traces, without new answers")
    return lines


def plan(rows, cases, budget_s=None):
    """Per harness, the cheapest runnable cases that settle the debt in `rows`.

    Greedy weighted cover: each pick is the case that settles the most open promises per second of its time limit.
    The time limit is an upper bound on a run, not a cost estimate. With a budget, picks stop when no remaining case
    fits and the uncovered promises stay listed as debt.
    """
    out = {}
    for harness in sorted({row["harness"] for row in rows}):
        need = {}
        for row in rows:
            if row["harness"] == harness and row["state"] in DEBT:
                # An unsettled receipt needs repeats of the case it was recorded on; other debt takes any bound case.
                need[row["promise"]] = [row["receipt_case"]] if row["state"] == UNSETTLED else row["cases"]
        open_, picks, spent = dict(need), [], 0
        while open_:
            best = None
            for case_id in sorted({c for options in open_.values() for c in options}):
                cost = timeout_for(cases[case_id], harness)
                if budget_s is not None and spent + cost > budget_s:
                    continue
                covers = sorted(pid for pid, options in open_.items() if case_id in options)
                if best is None or len(covers) / cost > len(best[1]) / best[2]:
                    best = (case_id, covers, cost)
            if best is None:
                break
            case_id, covers, cost = best
            picks.append({"case": case_id, "settles": covers, "timeout_s": cost})
            spent += cost
            for pid in covers:
                del open_[pid]
        repeats = [row for row in rows if row["harness"] == harness and row["state"] == UNSETTLED]
        out[harness] = {"cases": picks, "timeout_s_upper_bound": spent, "uncovered": sorted(open_),
                        "repeat_until_settled": sorted({row["receipt_case"] for row in repeats}),
                        "command": command(harness, [p["case"] for p in picks]) if picks else None}
    return out


def command(harness, case_ids):
    return f"python3 evals/promises/live.py run --harness {harness} " + " ".join(f"--case {c}" for c in case_ids)


def audit_sample(receipts, rows, count):
    """PASS receipts no person has read, in an order fixed by their content so the pick cannot favor easy ones."""
    fresh = {(row["promise"], row["harness"], row["receipt_case"]) for row in rows if row["state"] == FRESH}
    unread = []
    for pid, harness, case_id in fresh:
        entry = receipts["receipts"][pid][harness][case_id]
        if "audit" not in entry and unanimous(entry["verdicts"]) == "PASS":
            unread.append((sha(f"{pid}\0{harness}\0{case_id}\0{entry['skills_at']}".encode()), pid, harness, case_id, entry["skills_at"]))
    return [{"promise": pid, "harness": harness, "case": case_id, "skills_at": commit} for _, pid, harness, case_id, commit in sorted(unread)[:count]]


def record_audit(receipts, pid, harness, case_id, agrees, note, today):
    try:
        entry = receipts["receipts"][pid][harness][case_id]
    except KeyError:
        raise ValueError(f"no receipt for {pid} on {harness} from {case_id}") from None
    entry["audit"] = {"agrees": agrees, "recorded": today, **({"note": note} if note else {})}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--receipts", default=str(RECEIPTS))
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record", help="fold graded runs into the receipts file")
    r.add_argument("out", help="the --out directory of live.py run")
    for name, text in (("check", "list live promises without fresh evidence"), ("plan", "pick the cheapest cases that settle the debt")):
        c = sub.add_parser(name, help=text)
        c.add_argument("--base", help="report only promises the change since this ref reaches")
        c.add_argument("--harness", action="append", choices=report.HARNESSES, help="default: the policy's harnesses")
        if name == "check":
            c.add_argument("--strict", action="store_true", help="exit 1 when a blocking promise lacks fresh evidence")
            c.add_argument("--quiet", action="store_true", help="print the counts and the blocking debt only")
        else:
            c.add_argument("--budget-s", type=int, help="stop picking when the summed time limits would pass this")
    s = sub.add_parser("audit-sample", help="name PASS receipts for a person to read against their traces")
    s.add_argument("--count", type=int, default=5)
    a = sub.add_parser("audit", help="record a reader's agreement or disagreement with one receipt")
    a.add_argument("promise")
    a.add_argument("harness", choices=report.HARNESSES)
    a.add_argument("case")
    verdict = a.add_mutually_exclusive_group(required=True)
    verdict.add_argument("--agrees", action="store_true")
    verdict.add_argument("--disputes", action="store_true")
    a.add_argument("--note")
    args = parser.parse_args(argv)
    receipts, promises, cases = load_receipts(args.receipts), ledger.load()["promises"], load_cases()
    today = datetime.date.today().isoformat()
    if args.cmd == "record":
        print("\n".join(record(Path(args.out), receipts, promises, cases, today=today)))
        save_receipts(receipts, args.receipts)
        return 0
    if args.cmd == "audit":
        try:
            record_audit(receipts, args.promise, args.harness, args.case, args.agrees, args.note, today)
        except ValueError as error:
            print(error, file=sys.stderr)
            return 2
        save_receipts(receipts, args.receipts)
        return 0
    policy = load_policy()
    rows = cells(receipts, promises, cases, getattr(args, "harness", None) or policy["harnesses"])
    if args.cmd == "audit-sample":
        print(json.dumps(audit_sample(receipts, rows, args.count), indent=1))
        return 0
    if args.base:
        rows = touched(rows, changed_files(args.base), cases)
    if args.cmd == "plan":
        print(json.dumps(plan(rows, cases, args.budget_s), indent=1))
        return 0
    blocking = set(policy["blocking"])
    print("\n".join(render_check(rows, blocking, stale_grader(receipts, grader_digest()), args.quiet)))
    blocked = [row for row in rows if row["state"] in DEBT and row["promise"] in blocking]
    return 1 if args.strict and blocked else 0


if __name__ == "__main__":
    sys.exit(main())
