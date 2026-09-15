import json
import re
from collections import Counter
from typing import Any

from .specs import CASE_SPECS, CaseSpec


TAG_PATTERN = re.compile(r"<spec-probe-record>\s*(.*?)\s*</spec-probe-record>", re.DOTALL)
REQUIREMENT_ID = re.compile(r"\b[A-Z]{2,}-\d+\b")


def extract_import_record(text: str) -> tuple[dict[str, Any] | None, list[str]]:
    matches = TAG_PATTERN.findall(text)
    if len(matches) != 1:
        return None, [f"expected one spec-probe-record tag, found {len(matches)}"]
    try:
        record = json.loads(matches[0])
    except json.JSONDecodeError as exc:
        return None, [f"record is not valid JSON: {exc.msg}"]
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
        if event.get("type") == "command":
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
