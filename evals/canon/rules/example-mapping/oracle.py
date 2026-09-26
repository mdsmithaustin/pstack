"""Map each stated rule to Given, When, Then examples and never invent a Then.

The story states three rules and leaves one outcome open: a withdrawal that
lands exactly on the -£100 overdraft limit. Examples are read from Gherkin-style
step lines, one-line "Given ..., when ..., then ..." sentences, and Markdown
tables with Given, When, and Then columns."""
import re

STEP = re.compile(r"^(given|when|then|and|but)\b[\s:]*(.*)$", re.IGNORECASE)
INLINE_SPLIT = re.compile(r"[,;]?\s+\b(when|then)\b\s*", re.IGNORECASE)
MARKUP = re.compile(r"^[\s>#*_`+-]*(?:\d+[.)]\s*)?[*_`]*")
OPEN = re.compile(r"\?|\b(tbd|tbc|to be (decided|confirmed)|unknown|open question|unresolved|undecided|not stated|unspecified|needs? a decision)\b", re.IGNORECASE)
MONEY = re.compile(r"(minus\s+|-\s*)?£\s*(-\s*)?(\d[\d,]*(?:\.\d+)?)", re.IGNORECASE)
PLAIN_BALANCE = re.compile(r"\bbalance (?:is|of)\s+(-?\d+(?:\.\d+)?)\b", re.IGNORECASE)
PLAIN_AMOUNT = re.compile(r"\bwithdraw(?:s|ing|al of)?\s+(\d+(?:\.\d+)?)\b", re.IGNORECASE)
LIMIT = -100
MINIMUM = 10


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


def amounts(text, skip_limit):
    found = []
    for match in MONEY.finditer(text):
        before = text[max(0, match.start() - 25):match.start()].lower()
        if skip_limit and ("limit" in before or "overdraft" in before):
            continue
        value = float(match.group(3).replace(",", ""))
        after = text[match.end():match.end() + 12].lower()
        negative = bool(match.group(1) or match.group(2)) or "overdrawn by" in before[-14:] or after.lstrip().startswith("overdrawn")
        found.append(-value if negative else value)
    return found


def category(example):
    given, when = " ".join(example["given"]), " ".join(example["when"])
    balances = amounts(given, skip_limit=True) or [float(value) for value in PLAIN_BALANCE.findall(given)]
    withdrawals = amounts(when, skip_limit=True) or [float(value) for value in PLAIN_AMOUNT.findall(when)]
    if not balances or not withdrawals:
        return None
    balance, amount = balances[0], abs(withdrawals[0])
    if amount < MINIMUM:
        return "minimum"
    after = balance - amount
    if after > LIMIT:
        return "paid"
    if after < LIMIT:
        return "refused"
    return "at-limit"


def asserts(example):
    return any(line and not OPEN.search(line) for line in example["then"])


def raises_limit_question(text):
    for line in normalize(text).splitlines():
        if OPEN.search(line) and re.search(r"£\s*100\b|-\s*£?\s*100\b", line) and re.search(r"\b(exactly|at the limit|on the limit|equal|equals|lands?|reach(es)?|hits?)\b", line, re.IGNORECASE):
            return True
    return False


def check_examples(answer, project):
    found = examples(answer)
    if not found:
        return ["no Given, When, Then examples"]
    by_category = {}
    for example in found:
        by_category.setdefault(category(example), []).append(example)
    failures = []
    for rule in ("minimum", "paid", "refused"):
        if not any(asserts(example) for example in by_category.get(rule, [])):
            failures.append(f"no example with literal amounts and a Then for the {rule} rule")
    at_limit = by_category.get("at-limit", [])
    if any(asserts(example) for example in at_limit):
        failures.append("a Then asserts an outcome for a withdrawal that lands exactly on -£100")
    elif not (at_limit or raises_limit_question(answer)):
        failures.append("the withdrawal that lands exactly on -£100 is not raised as an open question")
    return failures


CHECKS = {"withdrawal-story": check_examples}
