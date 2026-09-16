from __future__ import annotations

import re
import shlex
from collections import Counter
from typing import Any

from .specs import CASE_SPECS, CaseSpec
from .json_contract import strict_json_loads


TAG_PATTERN = re.compile(r"<spec-probe-record>\s*(.*?)\s*</spec-probe-record>", re.DOTALL)
REQUIREMENT_ID = re.compile(r"\b[A-Z]{2,}-\d+\b")
READ_ONLY_COMMANDS = {
    "cat", "echo", "find", "grep", "head", "ls", "printf", "pwd", "rg", "sed", "sort", "stat", "tail", "wc",
}
SORT_SAFE_SHORT_FLAGS = frozenset("bCcdfghiMmnRrsuVz")
SORT_SAFE_LONG_OPTIONS = {
    "--check", "--debug", "--dictionary-order", "--field-separator",
    "--general-numeric-sort", "--human-numeric-sort", "--ignore-case",
    "--ignore-leading-blanks", "--ignore-nonprinting", "--key", "--month-sort",
    "--numeric-sort", "--reverse", "--stable", "--unique", "--version-sort",
    "--zero-terminated",
}


def _command_segments(command: str) -> list[list[str]] | None:
    if "\n" in command or "\r" in command or any(
        marker in command for marker in ("$(", "`", "<(", ">(", ">", "<")
    ):
        return None
    try:
        lexer = shlex.shlex(command, posix=False, punctuation_chars="|&;")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return None
    segments: list[list[str]] = [[]]
    for token in tokens:
        value = token[1:-1] if len(token) >= 2 and token[0] == token[-1] and token[0] in {"'", '"'} else token
        if value in {"|", "||", "&&", ";", "&"}:
            segments.append([])
        else:
            segments[-1].append(value)
    return segments


def _sort_is_read_only(arguments: list[str]) -> bool:
    expects_value = False
    for argument in arguments:
        if expects_value:
            expects_value = False
            continue
        if argument == "--":
            return True
        if argument == "-" or not argument.startswith("-"):
            continue
        if argument.startswith("--"):
            option, separator, _ = argument.partition("=")
            if option not in SORT_SAFE_LONG_OPTIONS:
                return False
            if option in {"--field-separator", "--key"} and not separator:
                expects_value = True
            continue
        options = argument[1:]
        if options.startswith(("k", "t")):
            expects_value = len(options) == 1
            continue
        if not options or any(option not in SORT_SAFE_SHORT_FLAGS for option in options):
            return False
    return True


def _read_only_inspection(command: str) -> bool:
    segments = _command_segments(command)
    if segments is None:
        return False
    for segment in segments:
        if not segment:
            continue
        command = segment[0]
        executable = command.rsplit("/", 1)[-1]
        if executable in {"bash", "dash", "sh", "zsh"}:
            return False
        if "/" in command and command.rsplit("/", 1)[0] not in {
            "/bin", "/usr/bin", "/usr/local/bin",
        }:
            return False
        if executable not in READ_ONLY_COMMANDS:
            return False
        if executable == "find" and any(
            argument in {
                "-delete", "-exec", "-execdir", "-fls", "-fprint", "-fprint0",
                "-fprintf", "-ok", "-okdir",
            }
            for argument in segment[1:]
        ):
            return False
        if executable == "sort" and not _sort_is_read_only(segment[1:]):
            return False
        if executable == "rg" and any(
            argument == "-r" or argument.startswith("--replace")
            or argument == "--pre" or argument.startswith("--pre=")
            for argument in segment[1:]
        ):
            return False
        if executable == "sed":
            if "-n" not in segment[1:] or any(
                argument == "-i"
                or argument.startswith("-i")
                or argument == "--in-place"
                or argument.startswith("--in-place=")
                for argument in segment[1:]
            ):
                return False
    return True


def extract_import_record(text: str) -> tuple[dict[str, Any] | None, list[str]]:
    matches = TAG_PATTERN.findall(text)
    if len(matches) != 1:
        return None, [f"expected one spec-probe-record tag, found {len(matches)}"]
    try:
        record = strict_json_loads(matches[0])
    except (ValueError, RecursionError) as exc:
        return None, [f"record is not valid JSON: {exc}"]
    if not isinstance(record, dict):
        return None, ["record must be a JSON object"]
    return record, []


def _compare_counts(coverage: dict[str, Any], items: list[dict[str, Any]], path: str) -> list[str]:
    counts = Counter(item.get("disposition") for item in items)
    expected = {
        "applicable": len(items),
        "resolved": counts["resolved"],
        "dismissed": counts["dismissed"],
        "unresolved": counts["unresolved"],
    }
    return [
        f"{path}.{key} must be {wanted}"
        for key, wanted in expected.items()
        if key in coverage and coverage[key] != wanted
    ]


def _coverage_errors(record: dict[str, Any]) -> list[str]:
    requirements = record.get("requirements")
    if not isinstance(requirements, list):
        requirements = []
    errors: list[str] = []
    all_items: list[dict[str, Any]] = []
    for index, requirement in enumerate(requirements):
        if not isinstance(requirement, dict) or not isinstance(requirement.get("items"), list):
            continue
        items = [item for item in requirement["items"] if isinstance(item, dict)]
        all_items.extend(items)
        coverage = requirement.get("coverage")
        if isinstance(coverage, dict):
            errors.extend(_compare_counts(coverage, items, f"requirements[{index}].coverage"))
    coverage = record.get("coverage")
    if isinstance(coverage, dict):
        errors.extend(_compare_counts(coverage, all_items, "coverage"))
    return errors


def _trace_errors(events: list[dict[str, Any]] | None) -> list[str]:
    if events is None:
        return []
    errors: list[str] = []
    for event in events:
        if event.get("type") in {"file_change", "file_write"}:
            errors.append("pre-build review changed a file")
        if event.get("type") == "command" and not _read_only_inspection(
            str(event.get("input_summary", ""))
        ):
            errors.append("pre-build review executed a command")
    return errors


def evaluate_spec(text: str, spec: CaseSpec, events: list[dict[str, Any]] | None = None) -> list[str]:
    errors = _trace_errors(events)
    if not text.strip():
        return [*errors, "output is empty"]
    mentioned = set(REQUIREMENT_ID.findall(text))
    if spec.incident:
        if mentioned:
            errors.append("a deployed incident must not manufacture requirement IDs")
        if "<spec-probe-record>" in text:
            record, import_errors = extract_import_record(text)
            errors.extend(import_errors)
            if record is not None:
                errors.extend(_coverage_errors(record))
        return errors
    missing = [requirement_id for requirement_id in spec.requirement_ids if requirement_id not in mentioned]
    if missing:
        errors.append(f"missing source requirement anchors: {', '.join(missing)}")
    if "<spec-probe-record>" in text:
        record, import_errors = extract_import_record(text)
        errors.extend(import_errors)
        if record is not None:
            errors.extend(_coverage_errors(record))
    return errors


def evaluate(case_id: str, text: str, events: list[dict[str, Any]] | None = None) -> list[str]:
    spec = CASE_SPECS.get(case_id)
    if spec is None:
        return [f"unknown case: {case_id}"]
    return evaluate_spec(text, spec, events)
