"""Review cases: the blinded judge, its calibration, and review scores.

A review case hands the agent a pull request on a branch and asks for a
review. rubric.md in the case names the seeded flaw (or, for a near-miss, the
decoy that must not be flagged) and is shown only to the judge. The judge sees
the PR title, body, and diff, the review under a label derived from its text,
and the files the reviewer left in the checkout. It never sees the rule, the
arm, or which agent wrote the review, and it returns one strict JSON verdict.

A Claude review is judged by Codex and a Codex review by Claude. The judge
runs in its own sandbox whose network reaches only its model API (see
sandbox.run_judge), or, when CANON_JUDGE_STANDIN names a command, through that
command with the prompt on stdin, which costs nothing.

The rule's oracle is the precheck: CHECKS[case](answer, workspace) returns
failures unless the review names the case's file or symbol (the decoy's, for a
near-miss). A verdict that says the review flagged the location (FOUND,
PARTIAL, FALSE_ALARM) counts only when the precheck passes; otherwise the
combined verdict is MISSED for a positive case and CLEAN for a near-miss.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

CANON = Path(__file__).resolve().parent
sys.path.insert(0, str(CANON))
import workspace  # noqa: E402

VERDICTS = {"positive": ("FOUND", "PARTIAL", "MISSED"), "near-miss": ("FALSE_ALARM", "CLEAN")}
FLAGGED = {"FOUND", "PARTIAL", "FALSE_ALARM"}
PASSING = {"positive": "FOUND", "near-miss": "CLEAN"}
UNFLAGGED = {"positive": "MISSED", "near-miss": "CLEAN"}
JUDGE_FOR = {"claude": ("codex", "gpt-6-sol"), "codex": ("claude", "opus")}
MEANINGS = {
    "FOUND": "the review names where the flaw is, says what is wrong, and gives a fix direction the guide accepts.",
    "PARTIAL": "the review touches the flaw but lacks the location, the problem, or a fix direction the guide accepts.",
    "MISSED": "the review does not identify the flaw.",
    "FALSE_ALARM": "the review flags the concern the guide describes as a problem in this pull request, and the guide says it is not one.",
    "CLEAN": "the review does not flag that concern as a problem.",
}
# Bump when TEMPLATE or MEANINGS change, so older calibration no longer counts.
TEMPLATE_VERSION = "review-judge-1"
TEMPLATE = """You are grading one code review of a pull request against a grading guide.

Someone asked a reviewer to review the pull request below before it merges. Decide how the review handles the one concern the grading guide describes. Judge only that concern. Other findings, length, and tone neither help nor hurt.

Allowed verdicts: {verdicts}.
{meanings}

Return only a JSON object with exactly two keys:
- "verdict": one of {verdicts}.
- "evidence": a short verbatim quote from the review that decides the verdict, or "" when the review says nothing about the concern.

<grading_guide>
{rubric}
</grading_guide>

<pull_request>
Title: {title}

Description:
{body}

Diff against main:
{diff}
</pull_request>

<review label="{label}">
{answer}
</review>

<files_the_reviewer_changed_or_added>
{written}
</files_the_reviewer_changed_or_added>
"""
IDENTITY = re.compile(r"\b(claude(?: code)?|codex|anthropic|openai|gpt-[\w.-]+|opus|sonnet|haiku)\b", re.IGNORECASE)
MOUNT = re.compile(r"(?:\.claude|\.agents|\.codex)/(?:skills|agents)/\S*|skills/pstack/\S*|[/$]poteto-mode\b|\bpoteto-(?:mode|agent)\b|\bpstack\b")
WRITTEN_LIMIT = 20000


class JudgeError(Exception):
    pass


def schema(kind):
    return {"type": "object", "additionalProperties": False, "required": ["verdict", "evidence"],
            "properties": {"verdict": {"type": "string", "enum": list(VERDICTS[kind])}, "evidence": {"type": "string"}}}


def label(answer):
    """A label for the review that says nothing about where it came from."""
    return "review-" + hashlib.sha256(answer.encode()).hexdigest()[:8]


def sanitize(text, subject, secret_words=()):
    """(text, redactions): the review with the harness's paths and invocation,
    every secret word (the rule id), and every agent or vendor name the
    subject (PR and guide) never uses replaced by neutral tokens."""
    redactions = []

    def swap(pattern, token):
        nonlocal text

        def replace(match):
            redactions.append(match.group(0))
            return token
        text = pattern.sub(replace, text)

    swap(MOUNT, "[tooling]")
    for word in secret_words:
        swap(re.compile(re.escape(word), re.IGNORECASE), "[tooling]")
    used = {match.group(0).lower() for match in IDENTITY.finditer(subject)}
    text = IDENTITY.sub(lambda match: match.group(0) if match.group(0).lower() in used else (redactions.append(match.group(0)) or "[assistant]"), text)
    return text, redactions


def prompt(kind, rubric, pr, answer, written="", secret_words=()):
    """(judge prompt, answer label, redactions). pr holds title, body, diff."""
    subject = "\n".join((rubric, pr["title"], pr["body"], pr["diff"]))
    answer, redactions = sanitize(answer, subject, secret_words)
    if len(written) > WRITTEN_LIMIT:
        written = written[:WRITTEN_LIMIT] + "\n[truncated]\n"
    written, more = sanitize(written, subject, secret_words)
    verdicts = ", ".join(VERDICTS[kind])
    text = TEMPLATE.format(
        verdicts=verdicts, meanings="\n".join(f"- {name}: {MEANINGS[name]}" for name in VERDICTS[kind]),
        rubric=rubric.strip(), title=pr["title"], body=pr["body"].strip(), diff=pr["diff"].rstrip("\n"),
        label=label(answer), answer=answer.strip() or "(empty)", written=written.strip() or "(none)")
    return text, label(answer), redactions + more


def claude_answer(raw):
    """The verdict text from a `claude -p --output-format json` envelope."""
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise JudgeError(f"claude output is not a JSON envelope: {exc}") from exc
    if not isinstance(envelope, dict) or envelope.get("type") != "result":
        raise JudgeError("claude output is not a result envelope")
    if envelope.get("is_error"):
        raise JudgeError(f"claude reported an error: {str(envelope.get('result'))[:300]}")
    if isinstance(envelope.get("structured_output"), dict):
        return json.dumps(envelope["structured_output"])
    return envelope.get("result") or ""


def parse(text, kind):
    """(verdict, evidence) from judge text that must be one JSON object with
    exactly verdict and evidence, optionally inside one ```json fence."""
    body = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*\n(.*?)\n?```", body, re.DOTALL)
    if fenced:
        body = fenced.group(1).strip()
    try:
        verdict = json.loads(body)
    except json.JSONDecodeError as exc:
        raise JudgeError(f"judge output is not one JSON object: {exc}") from exc
    if not isinstance(verdict, dict) or set(verdict) != {"verdict", "evidence"}:
        raise JudgeError(f"judge output must have exactly verdict and evidence, not {sorted(verdict) if isinstance(verdict, dict) else type(verdict).__name__}")
    if verdict["verdict"] not in VERDICTS[kind]:
        raise JudgeError(f"judge verdict {verdict['verdict']!r} is not one of {VERDICTS[kind]}")
    if not isinstance(verdict["evidence"], str):
        raise JudgeError("judge evidence must be a string")
    return verdict["verdict"], verdict["evidence"]


def quoted(evidence, answer):
    squash = lambda text: " ".join(text.split()).lower()  # noqa: E731
    return squash(evidence) in squash(answer)


def combine(kind, verdict, precheck_passed):
    """The verdict that counts: a flagged verdict needs the precheck."""
    if verdict in FLAGGED and not precheck_passed:
        return UNFLAGGED[kind]
    return verdict


def invoke(backend, model, text, kind, repo=None, commit=None):
    """(raw judge text, record) from the stand-in command or a sandbox."""
    standin = os.environ.get("CANON_JUDGE_STANDIN")
    if standin:
        proc = subprocess.run([standin, backend, model], input=text.encode(), capture_output=True,
                              env={**os.environ, "CANON_JUDGE_SCHEMA": json.dumps(schema(kind))})
        if proc.returncode != 0:
            raise JudgeError(f"judge stand-in failed ({proc.returncode}): {proc.stderr.decode(errors='replace')[-300:]}")
        return proc.stdout.decode(), {"runner": "standin"}
    import sandbox  # noqa: PLC0415
    try:
        result = sandbox.run_judge(backend, model, text, schema(kind), repo, commit)
    except (sandbox.SandboxError, workspace.WorkspaceError) as exc:
        raise JudgeError(str(exc)) from exc
    raw = result.pop("raw")
    if backend == "claude":
        try:
            raw = claude_answer(raw)
        except JudgeError as exc:
            result["answer_error"] = str(exc)
            raw = ""
    return raw, {"runner": "sbx", **result}


def judge(backend, model, kind, rubric, pr, answer, written="", secret_words=(), repo=None, commit=None):
    """One verdict record. A judge that fails or answers off-contract yields
    verdict None and its error, never a guess."""
    text, answer_label, redactions = prompt(kind, rubric, pr, answer, written, secret_words)
    record = {"label": answer_label, "backend": backend, "model": model, "template": TEMPLATE_VERSION,
              "prompt_sha256": hashlib.sha256(text.encode()).hexdigest(), "redactions": redactions}
    try:
        raw, record["invocation"] = invoke(backend, model, text, kind, repo, commit)
        if record["invocation"].get("answer_error"):
            raise JudgeError(record["invocation"]["answer_error"])
        record["verdict"], record["evidence"] = parse(raw, kind)
        record["evidence_in_review"] = quoted(record["evidence"], answer)
    except JudgeError as exc:
        record.update(verdict=None, error=str(exc))
    return record


def judge_runner():
    """Calibration from the stand-in judge must never vouch for the real one."""
    return "standin" if os.environ.get("CANON_JUDGE_STANDIN") else "model"


def calibration_key(backend, model, kind, rubric, pr):
    parts = [TEMPLATE_VERSION, judge_runner(), backend, model, kind, rubric, pr["title"], pr["body"], pr["diff"]]
    return hashlib.sha256(json.dumps(parts).encode()).hexdigest()


def calibration_path(rule, case, backend, model):
    return workspace.cache_root() / "calibration" / rule / case / f"{judge_runner()}-{backend}-{model}.json"


def agreement(samples):
    """{label: [agreed, total]} over {name: {"label", "verdict"}}, and whether
    every sample agreed."""
    table = {}
    for sample in samples.values():
        row = table.setdefault(sample["label"], [0, 0])
        row[0] += sample["verdict"] == sample["label"]
        row[1] += 1
    return table, bool(samples) and all(agreed == total for agreed, total in table.values())


def calibration_status(record, key):
    """(calibrated, reason) for a stored calibration record."""
    if record is None:
        return False, "no calibration record"
    if record.get("key") != key:
        return False, "the guide, the PR, or the judge changed since calibration"
    misses = [f"{name} labeled {sample['label']} judged {sample['verdict']}" for name, sample in sorted(record["samples"].items())
              if sample["verdict"] != sample["label"]]
    if misses:
        return False, "judge disagrees with labels: " + "; ".join(misses)
    if not record["samples"]:
        return False, "no labeled samples"
    return True, "every labeled sample agreed"


def scores(rows):
    """Per-arm review scores from compare rows that carry a judge verdict.
    Recall counts positive runs; the false-alarm rate counts near-miss runs."""
    positive = [row for row in rows if row["kind"] == "positive"]
    near = [row for row in rows if row["kind"] == "near-miss"]
    judged = [row for row in positive + near if row["review"]["combined"] != "UNJUDGED"]

    def share(count, total):
        return {"count": count, "of": total, "rate": round(count / total, 3) if total else None}

    return {
        "recall_found": share(sum(row["review"]["combined"] == "FOUND" for row in positive), len(positive)),
        "recall_found_or_partial": share(sum(row["review"]["combined"] in ("FOUND", "PARTIAL") for row in positive), len(positive)),
        "false_alarm_rate": share(sum(row["review"]["combined"] == "FALSE_ALARM" for row in near), len(near)),
        "precheck_pass": share(sum(row["review"]["precheck"] == "PASS" for row in positive), len(positive)),
        "unjudged": len(positive) + len(near) - len(judged),
        "uncalibrated": sum(not row["review"]["calibrated"] for row in judged),
    }
