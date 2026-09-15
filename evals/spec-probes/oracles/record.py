import json
import re
from collections import Counter
from typing import Any

from .specs import CASE_SPECS, CATEGORIES, COVERAGE_KEYS, SHAPES, CaseSpec, CheckSpec


TAG_PATTERN = re.compile(r"<spec-probe-record>\s*(.*?)\s*</spec-probe-record>", re.DOTALL)
COPY_FRAGMENTS = (
    "our planning intake accepts",
    "exactly one json object",
    "each item needs check_index",
    "coverage needs applicable",
)
PROHIBITION_GROUNDING = (
    ("sham", "repayment"),
    ("sham", "borrower"),
    ("humiliat", "repayment"),
    ("humiliat", "borrower"),
    ("third", "party", "amount"),
    ("audience", "overdue"),
    ("debt", "audience"),
    ("debt", "expos"),
    ("consent", "sms"),
    ("consent", "email"),
    ("opt", "out", "sms"),
    ("opt", "out", "email"),
    ("protected", "repayment"),
    ("fairness", "borrower"),
    ("first name", "overdue"),
    ("data", "amount"),
)


def extract_record(text: str) -> tuple[dict[str, Any] | None, list[str]]:
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


def text_has_grounding(value: str, alternatives: tuple[tuple[str, ...], ...]) -> bool:
    folded = value.casefold()
    return any(all(term in folded for term in group) for group in alternatives)


def validate_string(value: Any, path: str, errors: list[str], minimum: int = 8) -> str:
    if not isinstance(value, str) or len(value.strip()) < minimum:
        errors.append(f"{path} must be a specific non-empty string")
        return ""
    folded = value.casefold()
    if any(fragment in folded for fragment in COPY_FRAGMENTS):
        errors.append(f"{path} copies the response contract")
    return value


def expected_coverage(items: list[dict[str, Any]]) -> dict[str, int]:
    dispositions = Counter(item.get("disposition") for item in items)
    kinds = Counter(item.get("resolution_kind") for item in items)
    return {
        "applicable": len(items),
        "resolved": dispositions["resolved"],
        "dismissed": dispositions["dismissed"],
        "unresolved": dispositions["unresolved"],
        "backstop": kinds["backstop"],
        "judgment": kinds["judgment"],
    }


def validate_coverage(actual: Any, expected: dict[str, int], path: str, errors: list[str]) -> None:
    if not isinstance(actual, dict) or set(actual) != set(COVERAGE_KEYS):
        errors.append(f"{path} must contain exactly {', '.join(COVERAGE_KEYS)}")
        return
    for key, wanted in expected.items():
        value = actual.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value != wanted:
            errors.append(f"{path}.{key} must be {wanted}")


def validate_state(item: dict[str, Any], expected: CheckSpec, path: str, errors: list[str]) -> None:
    disposition = item.get("disposition")
    resolution_kind = item.get("resolution_kind")
    if disposition != expected.disposition:
        errors.append(f"{path}.disposition must be {expected.disposition}")
    if resolution_kind != expected.resolution_kind:
        errors.append(f"{path}.resolution_kind must be {expected.resolution_kind}")
    allowed = {
        "resolved": {"explicit", "backstop", "judgment"},
        "dismissed": {"not_applicable"},
        "unresolved": {"gap"},
    }
    if disposition in allowed and resolution_kind not in allowed[disposition]:
        errors.append(f"{path} has a contradictory disposition and resolution_kind")


def validate_check(item: Any, expected: CheckSpec, index: int, path: str, errors: list[str]) -> None:
    required = {
        "check_index",
        "probe_kind",
        "category",
        "question",
        "disposition",
        "reason",
        "resolution_kind",
    }
    if not isinstance(item, dict) or set(item) != required:
        errors.append(f"{path} must contain exactly the item contract fields")
        return
    if item.get("check_index") != index:
        errors.append(f"{path}.check_index must be {index}")
    if item.get("probe_kind") != expected.probe_kind:
        errors.append(f"{path}.probe_kind must be {expected.probe_kind}")
    if item.get("category") != expected.category:
        errors.append(f"{path}.category must be {expected.category}")
    if item.get("category") not in CATEGORIES:
        errors.append(f"{path}.category is not part of the closed category set")
    question = validate_string(item.get("question"), f"{path}.question", errors, 12)
    reason = validate_string(item.get("reason"), f"{path}.reason", errors, 12)
    if question and not text_has_grounding(question, expected.grounding):
        errors.append(f"{path}.question is not grounded in its requirement")
    if reason and not text_has_grounding(f"{question} {reason}", expected.grounding):
        errors.append(f"{path}.reason does not justify the disposition from supplied facts")
    validate_state(item, expected, path, errors)


def bespoke_check_spec(position: int) -> CheckSpec:
    if position == 0:
        return CheckSpec(
            category="bespoke-prohibition",
            probe_kind="prohibition",
            disposition="resolved",
            resolution_kind="judgment",
            grounding=PROHIBITION_GROUNDING,
        )
    return CheckSpec(
        category="bespoke-prohibition",
        probe_kind="prohibition",
        disposition="unresolved",
        resolution_kind="gap",
        grounding=PROHIBITION_GROUNDING,
    )


def validate_spec_record(record: dict[str, Any], spec: CaseSpec) -> list[str]:
    errors: list[str] = []
    if set(record) != {"scope", "requirements", "coverage"}:
        errors.append("record must contain exactly scope, requirements, and coverage")
    if record.get("scope") != "spec_review":
        errors.append("scope must be spec_review")
    requirements = record.get("requirements")
    if not isinstance(requirements, list):
        return [*errors, "requirements must be a list"]
    expected_ids = [requirement.requirement_id for requirement in spec.requirements]
    actual_ids = [item.get("requirement_id") if isinstance(item, dict) else None for item in requirements]
    if actual_ids != expected_ids:
        errors.append(f"requirement IDs must be {expected_ids} in source order")
    all_items: list[dict[str, Any]] = []
    next_index = 1
    for position, expected_requirement in enumerate(spec.requirements):
        if position >= len(requirements) or not isinstance(requirements[position], dict):
            continue
        requirement = requirements[position]
        path = f"requirements[{position}]"
        if set(requirement) != {"requirement_id", "shape", "items", "coverage"}:
            errors.append(f"{path} must contain exactly requirement_id, shape, items, and coverage")
        if requirement.get("shape") != expected_requirement.shape:
            errors.append(f"{path}.shape must be {expected_requirement.shape}")
        if requirement.get("shape") not in SHAPES:
            errors.append(f"{path}.shape is unknown")
        items = requirement.get("items")
        if not isinstance(items, list):
            errors.append(f"{path}.items must be a list")
            continue
        expected_checks = list(expected_requirement.checks)
        if spec.bespoke_requirement_id == expected_requirement.requirement_id:
            minimum, maximum = spec.bespoke_count
            bespoke_items = [item for item in items if isinstance(item, dict) and item.get("category") == "bespoke-prohibition"]
            if not minimum <= len(bespoke_items) <= maximum:
                errors.append(f"{path} must contain {minimum} to {maximum} bespoke prohibitions")
            expected_checks.extend(bespoke_check_spec(index) for index, _ in enumerate(bespoke_items))
        if len(items) != len(expected_checks):
            errors.append(f"{path}.items has {len(items)} checks, expected {len(expected_checks)}")
        for item_position, expected_check in enumerate(expected_checks):
            if item_position < len(items):
                validate_check(items[item_position], expected_check, next_index, f"{path}.items[{item_position}]", errors)
            next_index += 1
        typed_items = [item for item in items if isinstance(item, dict)]
        all_items.extend(typed_items)
        validate_coverage(requirement.get("coverage"), expected_coverage(typed_items), f"{path}.coverage", errors)
    validate_coverage(record.get("coverage"), expected_coverage(all_items), "coverage", errors)
    questions = [str(item.get("question", "")).casefold() for item in all_items]
    if len(questions) != len(set(questions)):
        errors.append("questions must be specific rather than repeated taxonomy prompts")
    return errors


def validate_incident_record(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected_keys = {"scope", "requirements", "coverage", "reason", "next_owner"}
    if set(record) != expected_keys:
        errors.append("incident record must contain exactly scope, requirements, coverage, reason, and next_owner")
    if record.get("scope") != "incident_triage":
        errors.append("scope must be incident_triage")
    if record.get("requirements") != []:
        errors.append("a deployed incident must not manufacture requirements")
    zeroes = {key: 0 for key in COVERAGE_KEYS}
    validate_coverage(record.get("coverage"), zeroes, "coverage", errors)
    reason = validate_string(record.get("reason"), "reason", errors, 16)
    if reason and not text_has_grounding(
        reason,
        (("deployed", "incident"), ("production", "cause"), ("shipped", "debug"), ("on-call", "reproduc")),
    ):
        errors.append("reason must ground the scope refusal in the deployed incident")
    if record.get("next_owner") not in {"debugging", "incident_response", "on_call"}:
        errors.append("next_owner must route to debugging, incident_response, or on_call")
    return errors


def evaluate(case_id: str, text: str) -> list[str]:
    record, errors = extract_record(text)
    if errors or record is None:
        return errors
    if case_id == "neg-deployed-incident-restraint":
        return validate_incident_record(record)
    spec = CASE_SPECS.get(case_id)
    if spec is None:
        return [f"unknown case: {case_id}"]
    return validate_spec_record(record, spec)
