import collections
import json
from pathlib import Path

import ledger

HARNESSES = ("claude-code", "codex", "hermes", "grok")


def collect(out):
    cells = collections.defaultdict(list)
    for path in sorted(Path(out).rglob("verdict.json")):
        record = json.loads(path.read_text())
        for pid, result in record["promises"].items():
            if not result.get("not_applicable"):
                cells[(pid, record["harness"])].append((result["verdict"], str(path.parent)))
    for path in sorted(Path(out).rglob("install.json")):
        for row in json.loads(path.read_text()):
            cells[(row["promise"], row["harness"])].append((row["verdict"], str(path)))
    return cells


def listing_states(out):
    states = collections.defaultdict(collections.Counter)
    for path in sorted(Path(out).rglob("verdict.json")):
        trace = path.parent / "trace.json"
        listing = json.loads(trace.read_text()).get("x_skill_listing") if trace.is_file() else None
        if listing:
            states[json.loads(path.read_text())["harness"]][listing.get("step")] += 1
    return [f"{harness} skill listing: " + ", ".join(f"{step} {n}" for step, n in sorted(counts.items()))
            for harness, counts in sorted(states.items())]


def cell(results):
    if not results:
        return ""
    counts = collections.Counter(v for v, _ in results)
    if len(counts) == 1:
        verdict, n = next(iter(counts.items()))
        return f"{verdict} ({n})" if n > 1 else verdict
    return ", ".join(f"{v} {n}" for v, n in sorted(counts.items()))


def render(out, upstream=None):
    book = ledger.load()
    cells = collect(out)
    pids = sorted({pid for pid, _ in cells})
    flags = ledger.owners_report(book, upstream, [p for p in pids if p in book["promises"]]) if upstream else {}
    lines = ["| promise | " + " | ".join(HARNESSES) + " | upstream |", "|---" * (len(HARNESSES) + 2) + "|"]
    for pid in pids:
        row = [cell(cells.get((pid, h), [])) for h in HARNESSES]
        failed = any("FAIL" in c for c in row)
        flag = ""
        if failed and pid in flags:
            flag = "possibly upstream" if flags[pid]["possibly_upstream"] else "port"
        elif pid not in book["promises"]:
            flag = "retired"
        lines.append(f"| `{pid}` | " + " | ".join(row) + f" | {flag} |")
    totals = collections.Counter(v for results in cells.values() for v, _ in results)
    lines.append("")
    lines.append(f"{len(pids)} promises, {sum(totals.values())} verdicts: " +
                 ", ".join(f"{v} {n}" for v, n in sorted(totals.items())))
    lines += listing_states(out)
    return "\n".join(lines)
