"""Reduce a harvested trace to the events and fields the oracles read, for a committed regression fixture."""

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import oracles

HOME_PATH = re.compile(r"/(?:Users|home)/[^/\s\"']+")


def load_case(case_id):
    case = json.loads((HERE / "cases" / case_id / "case.json").read_text(encoding="utf-8"))
    case["id"] = case_id
    return case


def fingerprint(trace, cases, exact=()):
    rows = []
    for case in cases:
        for pid in case["promises"]:
            result = oracles.check(pid, trace, case, None)
            rows.append(result if pid in exact else {"verdict": result["verdict"], "failures": result["failures"]})
    return json.dumps(rows, sort_keys=True)


def children(node):
    if isinstance(node, dict):
        return list(node)
    if isinstance(node, list):
        return list(range(len(node)))
    return []


def containers(node):
    if isinstance(node, (dict, list)):
        yield node
        for key in children(node):
            yield from containers(node[key])


def shrink_lists(trace, keep):
    changed = False
    for lst in [c for c in containers(trace) if isinstance(c, list)]:
        size = max(1, len(lst) // 2)
        while size >= 1:
            start = 0
            while start < len(lst):
                removed = lst[start:start + size]
                del lst[start:start + size]
                if keep():
                    changed = True
                else:
                    lst[start:start] = removed
                    start += size
            size //= 2
    return changed


def shrink_keys(trace, keep):
    changed = False
    for mapping in [c for c in containers(trace) if isinstance(c, dict)]:
        for key in list(mapping):
            value = mapping.pop(key)
            if keep():
                changed = True
            else:
                mapping[key] = value
    return changed


def shrink_strings(trace, keep):
    changed = False
    for node in [c for c in containers(trace)]:
        for key in children(node):
            value = node[key]
            if not isinstance(value, str) or not value:
                continue
            for cut in ("", *(value[:n] for n in sorted({len(value) // 2, len(value) // 4, 1}) if 0 < n < len(value))):
                node[key] = cut
                if keep():
                    changed = True
                    value = cut
                    break
            else:
                node[key] = value
    return changed


def sanitize(trace):
    def clean(node):
        if isinstance(node, str):
            return HOME_PATH.sub(lambda m: m.group(0).rsplit("/", 1)[0] + "/dev", node)
        if isinstance(node, list):
            return [clean(v) for v in node]
        if isinstance(node, dict):
            return {k: clean(v) for k, v in node.items()}
        return node
    return clean(trace)


def reduce_trace(trace, cases, exact=()):
    want = fingerprint(trace, cases, exact)
    def keep():
        try:
            return fingerprint(trace, cases, exact) == want
        except Exception:
            return False

    while shrink_lists(trace, keep) | shrink_keys(trace, keep) | shrink_strings(trace, keep):
        pass
    cleaned = sanitize(trace)
    if fingerprint(cleaned, cases, exact) != want:
        raise SystemExit("sanitizing changed a verdict; reduce a trace that holds no host paths")
    return cleaned


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("trace", nargs="+", help="trace.json files; each is rewritten in place unless --out is set")
    parser.add_argument("--case", action="append", required=True, help="case id whose promises must keep their verdicts and failure reasons")
    parser.add_argument("--exact", action="append", default=[], help="promise id whose evidence lines must stay identical too")
    parser.add_argument("--out", help="write the one reduced trace here instead of in place")
    args = parser.parse_args(argv)
    if args.out and len(args.trace) != 1:
        parser.error("--out takes exactly one trace")
    cases = [load_case(c) for c in args.case]
    for name in args.trace:
        path = Path(name)
        before = path.stat().st_size
        reduced = reduce_trace(json.loads(path.read_text(encoding="utf-8")), cases, args.exact)
        dest = Path(args.out) if args.out else path
        dest.write_text(json.dumps(reduced, indent=1) + "\n", encoding="utf-8")
        print(f"{path.name}: {before} -> {dest.stat().st_size} bytes", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
