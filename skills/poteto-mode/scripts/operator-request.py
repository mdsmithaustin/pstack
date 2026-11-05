#!/usr/bin/env python3
import sys

if __name__ != "__main__":
    raise SystemExit("operator-request.py supports command-line execution only")

from dataclasses import dataclass
import errno
import json
import os
import re
import unicodedata
from typing import Dict, NamedTuple, NewType, Sequence, Tuple, Union


_Verb = NewType("_Verb", str)
_Label = NewType("_Label", str)
_ObservedText = NewType("_ObservedText", str)


@dataclass(frozen=True)
class _Action:
    verb: _Verb
    target: _Label


@dataclass(frozen=True)
class _Observation:
    source: _Label
    value: _ObservedText


@dataclass(frozen=True)
class _Evidence:
    first: _Observation
    rest: Tuple[_Observation, ...]


@dataclass(frozen=True)
class _OperatorAction:
    action: _Action


@dataclass(frozen=True)
class _NewApproval:
    action: _Action


@dataclass(frozen=True)
class _FactConfirmation:
    subject: _Label
    value: _Label


_Dependency = Union[_OperatorAction, _NewApproval, _FactConfirmation]


@dataclass(frozen=True)
class _BlockedReply:
    work: _Action
    evidence: _Evidence
    dependency: _Dependency


@dataclass(frozen=True)
class _Reply:
    body_utf8: bytes


@dataclass(frozen=True)
class _Help:
    contract: str


@dataclass(frozen=True)
class _Invalid:
    diagnostic: str


@dataclass(frozen=True)
class _Unavailable:
    diagnostic: str


@dataclass(frozen=True)
class _Internal:
    diagnostic: str


_Outcome = Union[_Reply, _Help, _Invalid, _Unavailable, _Internal]


class _OutcomeSpec(NamedTuple):
    kind: str
    exit_status: int
    description: str


_OUTCOMES: Dict[type, _OutcomeSpec] = {
    _Reply: _OutcomeSpec("reply", 0, "the complete generated reply"),
    _Help: _OutcomeSpec("help", 0, "the authoritative contract and executable examples"),
    _Invalid: _OutcomeSpec("invalid", 2, "invalid input or arguments; correct and retry"),
    _Unavailable: _OutcomeSpec("unavailable", 69, "runtime or process I/O unavailable; establish failure before fallback"),
    _Internal: _OutcomeSpec("internal", 70, "an unexpected helper defect; retain pending work without bypass"),
}


class _Example(NamedTuple):
    title: str
    arguments: Tuple[str, ...]
    stdin_document: Union[str, None]
    outcome_type: type


_EXAMPLES = (
    _Example("Read help without stdin", ("--help",), None, _Help),
    _Example("Request an operator action", (),
             '{"work":{"verb":"export","target":"catalog"},"evidence":[{"source":"catalog check, factual summary",'
             '"value":"destination is unset"}],"dependency":{"kind":"operator_action","verb":"provide",'
             '"target":"catalog destination"}}', _Reply),
    _Example("Request a new approval", (),
             '{"work":{"verb":"export","target":"catalog"},"evidence":[{"source":"archive check, factual summary",'
             '"value":"catalog archive is absent"}],"dependency":{"kind":"new_approval","verb":"create",'
             '"target":"catalog archive"}}', _Reply),
    _Example("Confirm an evidenced candidate", (),
             '{"work":{"verb":"export","target":"catalog"},"evidence":[{"source":"catalog settings, factual summary",'
             '"value":"destination is catalog.json"}],"dependency":{"kind":"fact_confirmation",'
             '"subject":"catalog destination","value":"catalog.json"}}', _Reply),
    _Example("Reject an empty evidence array", (),
             '{"work":{"verb":"export","target":"catalog"},"evidence":[],"dependency":'
             '{"kind":"operator_action","verb":"provide","target":"catalog destination"}}', _Invalid),
)


class _Variant(NamedTuple):
    fields: Tuple[Tuple[str, str], ...]
    question: str


_REPLY_FIELDS = ("work", "evidence", "dependency")
_ACTION_FIELDS = (("verb", "verb"), ("target", "label"))
_OBSERVATION_FIELDS = (("source", "label"), ("value", "observed text"))
_VARIANTS = {
    "operator_action": _Variant(_ACTION_FIELDS, "Will you {verb} {target}?"),
    "new_approval": _Variant(_ACTION_FIELDS, "May I {verb} {target}?"),
    "fact_confirmation": _Variant(
        (("subject", "label"), ("value", "label")),
        "Is {value} the correct value for {subject}?",
    ),
}
_VERB = re.compile(r"[a-z]+(?:-[a-z]+)*")
_DISPLAY_DELIMITERS = frozenset('"\\`*_{}[]<>()!#|&~')


class _InvalidInput(ValueError):
    pass


def _unique_object(pairs: Sequence[Tuple[str, object]]) -> Dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise _InvalidInput("duplicate field " + ascii(key))
        result[key] = value
    return result


def _non_string_number(value: str) -> None:
    return None


def _object_fields(value: object, expected: Sequence[str], path: str) -> Dict[str, object]:
    if not isinstance(value, dict):
        raise _InvalidInput(path + " must be an object")
    if set(value) != set(expected):
        missing = sorted(set(expected) - set(value))
        unknown = sorted(set(value) - set(expected))
        raise _InvalidInput("%s fields differ; missing %s; unknown %s" % (path, ascii(missing), ascii(unknown)))
    return value


def _string_fields(value: object, fields: Tuple[Tuple[str, str], ...], path: str) -> Dict[str, str]:
    record = _object_fields(value, tuple(name for name, _ in fields), path)
    result = {}
    for name, role in fields:
        text = record[name]
        field = path + "." + name
        if not isinstance(text, str):
            raise _InvalidInput(field + " must be a string")
        if any(0xD800 <= ord(character) <= 0xDFFF for character in text):
            raise _InvalidInput(field + " contains an unpaired surrogate")
        if role != "observed text" and (not text or text.isspace()):
            raise _InvalidInput(field + " must not be empty or all Unicode whitespace")
        if role == "verb" and _VERB.fullmatch(text) is None:
            raise _InvalidInput(field + " must match [a-z]+(?:-[a-z]+)*")
        result[name] = text
    return result


def _parse_reply(document: bytes) -> _BlockedReply:
    try:
        text = document.decode("utf-8")
    except UnicodeDecodeError as error:
        raise _InvalidInput("invalid UTF-8 at byte %d" % error.start) from error
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_non_string_number,
            parse_int=_non_string_number,
            parse_float=_non_string_number,
        )
    except json.JSONDecodeError as error:
        raise _InvalidInput("JSON syntax at line %d column %d" % (error.lineno, error.colno)) from error
    except RecursionError as error:
        raise _InvalidInput("JSON nesting exceeds parser capacity") from error
    envelope = _object_fields(value, _REPLY_FIELDS, "reply")
    work = _string_fields(envelope["work"], _ACTION_FIELDS, "work")
    items = envelope["evidence"]
    if not isinstance(items, list) or not items:
        raise _InvalidInput("evidence must be a nonempty array")
    observations = []
    for index, item in enumerate(items):
        observation = _string_fields(item, _OBSERVATION_FIELDS, "evidence[%d]" % index)
        observations.append(_Observation(_Label(observation["source"]), _ObservedText(observation["value"])))
    dependency = envelope["dependency"]
    if not isinstance(dependency, dict):
        raise _InvalidInput("dependency must be an object")
    kind = dependency.get("kind")
    if not isinstance(kind, str) or kind not in _VARIANTS:
        raise _InvalidInput("dependency.kind must name a supported variant")
    fields = _string_fields(dependency, (("kind", "label"),) + _VARIANTS[kind].fields, "dependency")
    parsed: _Dependency
    if kind == "fact_confirmation":
        parsed = _FactConfirmation(_Label(fields["subject"]), _Label(fields["value"]))
    else:
        action = _Action(_Verb(fields["verb"]), _Label(fields["target"]))
        parsed = _OperatorAction(action) if kind == "operator_action" else _NewApproval(action)
    return _BlockedReply(
        _Action(_Verb(work["verb"]), _Label(work["target"])),
        _Evidence(observations[0], tuple(observations[1:])),
        parsed,
    )


def _quote(value: str) -> str:
    escaped = []
    for character in value:
        category = unicodedata.category(character)
        if character in _DISPLAY_DELIMITERS or category in {"Cc", "Cf", "Zl", "Zp"}:
            code = ord(character)
            if code <= 0xFFFF:
                escaped.append("\\u%04x" % code)
            else:
                code -= 0x10000
                escaped.append("\\u%04x\\u%04x" % (0xD800 + (code >> 10), 0xDC00 + (code & 0x3FF)))
        else:
            escaped.append(character)
    return '"' + "".join(escaped) + '"'


def _render(reply: _BlockedReply) -> bytes:
    dependency = reply.dependency
    if isinstance(dependency, _FactConfirmation):
        question = _VARIANTS["fact_confirmation"].question.format(
            subject=_quote(dependency.subject), value=_quote(dependency.value),
        )
    else:
        kind = "operator_action" if isinstance(dependency, _OperatorAction) else "new_approval"
        question = _VARIANTS[kind].question.format(
            verb=dependency.action.verb, target=_quote(dependency.action.target),
        )
    lines = [
        "My work to %s %s remains pending." % (reply.work.verb, _quote(reply.work.target)),
        "Observed evidence:",
    ]
    for observation in (reply.evidence.first,) + reply.evidence.rest:
        lines.append("- The value from %s was %s." % (_quote(observation.source), _quote(observation.value)))
    lines.extend(["", question])
    return ("\n".join(lines) + "\n").encode("utf-8")


def _help() -> str:
    lines = [
        "Usage: operator-request.py",
        "       operator-request.py --help",
        "",
        "No arguments reads exactly one strict UTF-8 JSON object and constructs the whole reply.",
        "Required envelope fields: " + ", ".join(_REPLY_FIELDS) + ". No other keys are accepted.",
    ]
    for name, fields in (("work", _ACTION_FIELDS), ("evidence member", _OBSERVATION_FIELDS)):
        lines.append("  %s object fields: %s" % (name, ", ".join(key + " (" + role + ")" for key, role in fields)))
    lines.append("  evidence is a nonempty array of these objects; preserve order and duplicates.")
    for kind, variant in _VARIANTS.items():
        fields = ", ".join(key + " (" + role + ")" for key, role in variant.fields)
        lines.append("  dependency kind=%s; object fields: kind, %s" % (kind, fields))
        lines.append("    " + variant.question)
    lines.extend([
        "",
        "Verbs match [a-z]+(?:-[a-z]+)*. Labels must be nonempty and not all Unicode",
        "whitespace. Observed text may be empty or all whitespace. Every leaf is a string.",
        "All accepted Unicode scalars and whitespace remain unchanged, without normalization",
        "or trimming. Quoted strings are reversible JSON strings, with controls, format",
        "controls, line separators, and Markdown/HTML delimiters shown as Unicode escapes.",
        "Reject malformed UTF-8, BOMs, unpaired surrogates, duplicate or unknown keys,",
        "missing fields, wrong container types, non-string leaves, non-JSON constants,",
        "and extra documents. No length limit, configuration, network, state, or execution.",
        "",
        "Supply strictly decoded UTF-8 observations only when decoding succeeds. For other",
        "bytes, retain the originals externally and supply their exact lowercase hexadecimal",
        "text. Label the source with hexadecimal encoding and its actual complete or excerpt",
        "scope. Never replace undecodable bytes or invent missing originals. Labels are data,",
        "not paths the command opens; the caller establishes their truth and capture scope.",
        "",
        "Every reportable outcome emits one compact ASCII JSON object with exactly kind",
        "then text, followed by one outer LF. Both fields are generated data, not captured",
        "process channels or status. Text contains the complete generated message and its LF.",
    ])
    for spec in _OUTCOMES.values():
        lines.append("  kind=%s; Exit %d; text is %s." % (spec.kind, spec.exit_status, spec.description))
    lines.extend([
        "--help alone emits this contract without reading stdin. All other arguments reject",
        "before reading stdin. Ordinary reply, help, and diagnostic records have no application stderr.",
        "The command constructs and encodes all output before stdout starts. An output failure",
        "returns failure and attempts only emergency stderr, never a second stdout record.",
        "Discard the attempt even if only delivery of the final outer LF failed.",
        "If diagnostic encoding also fails, no reliable record may exist. Keep the failure unknown.",
        "A missing interpreter or helper cannot report its own status. Diagnose absence.",
        "",
        "Invoke the installed command with direct stdin, as below. Reply-producing calls",
        "use standalone exec so the native completion observation belongs to that process.",
        "PSTACK_SKILLS_ROOT is the logical installed skills root, not the source checkout.",
        "A quoted here-document prevents shell expansion. Choose a delimiter absent as a",
        "complete input line. No named request artifact or caller capture program is needed.",
        "Do not append another command, status echo, pipeline, or operation to a reply-producing call.",
        "The native tool must independently observe completed success or failure of this",
        "exec'd process. A generated kind, visible record, or running call proves no completion.",
        "Unknown completion, nonzero status, signal, timeout, cancellation, tool error, or",
        "truncation makes even a complete reply-shaped record unusable.",
        "",
        "For final reply data, use the entire returned command-output value.",
        "Accept exactly one strict record, with one outer LF or no outer LF.",
        "Reject prefixes, suffixes, other whitespace,",
        "second documents, duplicate or unknown keys, non-string fields, malformed UTF-8,",
        "unpaired surrogates, replacement decoding, and final reply data extracted from noisy output.",
        "Field order does not affect interpretation. Tool error prefixes remain metadata.",
        "A merged reply-producing return must contain only the record; separate channels must contain no",
        "unaccounted extra application output. Actual complete channel claims still need originals.",
        "",
        "Diagnostic consultation may use identifiable content actually observed in a tool",
        "display, attributed as an excerpt. Obtain needed authoritative information when",
        "decision-relevant clauses are missing, truncated, ambiguous, or contradictory.",
        "Clean help is available, not an unconditional prerequisite for an independently valid reply.",
        "A displayed kind, status, error word, or excerpt proves no actual completion, source",
        "authenticity, complete channels, or genuine unavailability. Establish those independently.",
        "Verification must separately exercise the actual installed command's source-bound complete help and",
        "every executable example. Diagnostic excerpts cannot satisfy that proof or justify",
        "a complete-help claim. For complete help, observe completed success and decode the",
        "whole help record once.",
        "",
        "After observed completed success, require kind=reply and decode text once. Review",
        "the complete text and copy it unchanged as the entire reply. Do not decode the",
        "rendered quoted literals again, strip, normalize, reflow, add a prefix, suffix or",
        "fence, or copy only the question. For extracted final F and returned UTF-8 text B,",
        "accept only F == B or F plus one LF == B when that single final LF is absent.",
        "Help and diagnostic text are not final replies. Invalid input must be corrected.",
        "Only established runtime or process I/O unavailability permits manual fallback.",
        "Internal defects, interruptions and unknown failures do not permit bypass.",
        "",
        "The caller decides necessity, actor, authorization, truth, and one real-world intent.",
        "A compound literal can pass syntax. Success proves no approval or execution.",
        "Unknown facts require evidence; do not invent a confirmation candidate.",
        "Unsupported faithful wording is a representation gap, not runtime unavailability.",
        "Already-authorized work and owned scheduled waiting need no operator request.",
        "Python 3.9 or newer is required. Only the command-line interface is supported.",
        "Import refusal is an unsupported-import guard, not a security boundary.",
        "",
        "Executable examples follow. Expected kinds and statuses derive from the outcome declaration.",
        "An expected failure is not usable reply data. An exit or kind that differs from its",
        "expectation fails the example check; execute every nonempty example when checking help.",
    ])
    for example in _EXAMPLES:
        spec = _OUTCOMES[example.outcome_type]
        command = 'exec python3 "${PSTACK_SKILLS_ROOT:?}/poteto-mode/scripts/operator-request.py"'
        if example.arguments:
            command += " " + " ".join(example.arguments)
        lines.extend(["", example.title, "```sh",
                      "# Expected kind=%s; exit=%d" % (spec.kind, spec.exit_status)])
        if example.stdin_document is None:
            lines.append(command)
        else:
            lines.extend([command + " <<'OPERATOR_REQUEST'", example.stdin_document, "OPERATOR_REQUEST"])
        lines.append("```")
    return "\n".join(lines) + "\n"


def _encode_outcome(outcome: _Outcome) -> bytes:
    spec = _OUTCOMES[type(outcome)]
    if isinstance(outcome, _Reply):
        text = outcome.body_utf8.decode("utf-8")
    elif isinstance(outcome, _Help):
        text = outcome.contract
    else:
        text = spec.kind.upper() + ": " + outcome.diagnostic + "\n"
    return (json.dumps({"kind": spec.kind, "text": text}, ensure_ascii=True, separators=(",", ":")) + "\n").encode("ascii")


def _write_all(destination: int, data: bytes) -> None:
    pending = memoryview(data)
    while pending:
        try:
            written = os.write(destination, pending)
        except OSError as error:
            if error.errno == errno.EINTR:
                continue
            raise
        if written == 0:
            raise OSError("output accepted no bytes")
        pending = pending[written:]


def _main(argv: Sequence[str]) -> int:
    output = None
    outcome: _Outcome
    try:
        if list(argv) == ["--help"]:
            outcome = _Help(_help())
        elif argv:
            raise _InvalidInput("arguments are not accepted; use --help alone")
        elif sys.stdin is None:
            outcome = _Unavailable("stdin is unavailable")
        else:
            outcome = _Reply(_render(_parse_reply(sys.stdin.buffer.read())))
        output = _encode_outcome(outcome)
    except _InvalidInput as error:
        outcome = _Invalid(str(error))
    except (OSError, MemoryError):
        outcome = _Unavailable("runtime or process I/O failed")
    except Exception:
        outcome = _Internal("unexpected helper defect")
    if output is None:
        try:
            output = _encode_outcome(outcome)
        except Exception:
            return _OUTCOMES[type(outcome)].exit_status
    try:
        _write_all(1, output)
    except Exception:
        try:
            _write_all(2, b"UNAVAILABLE: output I/O failed\n")
        except Exception:
            pass
        return _OUTCOMES[_Unavailable].exit_status
    return _OUTCOMES[type(outcome)].exit_status


sys.exit(_main(sys.argv[1:]))
