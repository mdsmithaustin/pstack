"""An explicit resolution is a Given, When, Then example with a literal Then.

LP-1 answers its own rounding question: part of a pound earns nothing. The
review passes when some example gives an order with pence and a Then that
states the points earned, rounded down. Examples are read the same way as in
example-mapping: step lines, one-line sentences, and Given, When, Then tables."""
import math
import re

STEP = re.compile(r"^(given|when|then|and|but)\b[\s:]*(.*)$", re.IGNORECASE)
INLINE_SPLIT = re.compile(r"[,;]?\s+\b(when|then)\b\s*", re.IGNORECASE)
MARKUP = re.compile(r"^[\s>#*_`+-]*(?:\d+[.)]\s*)?[*_`]*")
OPEN = re.compile(r"\?|\b(tbd|tbc|to be (decided|confirmed)|unknown|open question|unresolved|undecided|not stated|unspecified|needs? a decision)\b", re.IGNORECASE)


def normalize(text):
    return text.translate({0x2212: "-", 0x2013: "-", 0x2014: "-", 0xA0: " "})


def table_examples(lines):
    examples, columns = [], None
    for line in lines:
        cells = [cell.strip().strip("*_` ").strip() for cell in line.strip().strip("|").split("|")] if line.strip().startswith("|") else None
        if cells is None:
            columns = None
            continue
        lowered = [cell.lower() for cell in cells]
        if {"given", "when", "then"} <= set(lowered):
            columns = {key: lowered.index(key) for key in ("given", "when", "then")}
            continue
        if columns is None or all(set(cell) <= set("-: ") for cell in cells):
            continue
        get = lambda key: cells[columns[key]] if columns[key] < len(cells) else ""
        examples.append({"given": [get("given")], "when": [get("when")], "then": [get("then")] if get("then") else []})
    return examples


def step_examples(lines):
    examples, current, last = [], None, None
    for raw in lines:
        line = MARKUP.sub("", raw).strip()
        match = STEP.match(line)
        if not match:
            if line:
                current, last = None, None
            continue
        parts = [match.group(1).lower(), match.group(2)]
        pieces = INLINE_SPLIT.split(parts[1])
        steps = [(parts[0], pieces[0])] + [(pieces[index].lower(), pieces[index + 1]) for index in range(1, len(pieces) - 1, 2)]
        for keyword, body in steps:
            body = body.strip().strip("*_`").strip()
            if keyword in ("and", "but"):
                keyword = last
            if keyword is None:
                continue
            if current is None or (keyword == "given" and (current["when"] or current["then"])) or (keyword == "when" and current["then"]):
                current = {"given": [], "when": [], "then": []}
                examples.append(current)
            current[keyword].append(body)
            last = keyword
    return examples


def examples(text):
    lines = normalize(text).splitlines()
    return step_examples(lines) + table_examples(lines)


PENCE = re.compile(r"(\d+)\.(\d{2})\b")
POINTS = re.compile(r"(\d+)\s*(?:loyalty\s+)?points?\b", re.IGNORECASE)


def asserts(line):
    return bool(line) and not OPEN.search(line)


def states_fraction_rule(example):
    setup = " ".join(example["given"] + example["when"])
    orders = [math.floor(float(f"{whole}.{pence}")) for whole, pence in PENCE.findall(setup) if pence != "00"]
    held = [int(value) for value in POINTS.findall(" ".join(example["given"]))]
    earned = {int(value) for line in example["then"] if asserts(line) for value in POINTS.findall(line)}
    return any(order in earned or any(order + start in earned for start in held) for order in orders)


def check_explicit(answer, project):
    if any(states_fraction_rule(example) for example in examples(answer)):
        return []
    return ["LP-1's part-of-a-pound rule has no Given, When, Then example with a literal Then"]


CHECKS = {"loyalty-points": check_explicit}
