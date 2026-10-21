#!/usr/bin/env python3
"""Evaluate reviewed recovery prerequisites in saved native Codex JSONL."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re


class _InputError(Exception):
    def __init__(self, code: str, row: int | None = None):
        self.code = code
        self.row = row


def _require(condition, code, row=None):
    if not condition:
        raise _InputError(code, row)


def _json(data, row=None):
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, "duplicate_json_key", row)
            result[key] = value
        return result

    def constant(_value):
        raise _InputError("invalid_json_number", row)

    try:
        return json.loads(data, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError) as error:
        raise _InputError("invalid_json_or_utf8", row) from error
    except RecursionError as error:
        raise _InputError("json_nesting_too_deep", row) from error


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _text(value, row=None):
    _require(isinstance(value, str), "expected_text", row)
    try:
        return value.encode("utf-8")
    except UnicodeError as error:
        raise _InputError("invalid_utf8_text", row) from error


def _object(value, required, optional=(), row=None):
    _require(isinstance(value, dict), "expected_object", row)
    _require(set(required) <= value.keys(), "missing_field", row)
    _require(value.keys() <= set(required) | set(optional), "unknown_field", row)
    return value


def _array(value, row=None):
    _require(isinstance(value, list), "expected_array", row)
    return value


def _string(value, row=None):
    _require(bool(_text(value, row)), "empty_text", row)
    return value


def _digest(value, row=None):
    _require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value), "invalid_sha256", row)
    return value


def _span(value, limit=None, row=None):
    _require(isinstance(value, list) and len(value) == 2, "invalid_byte_range", row)
    start, end = value
    _require(type(start) is int and type(end) is int and 0 <= start < end and
             (limit is None or end <= limit), "invalid_byte_range", row)
    return start, end


def _flags(*objects):
    found = set()
    for obj in objects:
        if "truncated" in obj:
            if obj["truncated"] is True:
                found.add("structured_truncation")
            elif obj["truncated"] is not False:
                found.add("unsupported_truncation_flag")
    return tuple(sorted(found))


@dataclass(frozen=True)
class _File:
    id: str
    role: str
    data: bytes


@dataclass(frozen=True)
class _Body:
    block: int
    kind: str
    raw: bytes
    data: bytes | None
    flags: tuple[str, ...]


@dataclass(frozen=True)
class _Call:
    id: str
    row: int
    return_row: int
    bodies: tuple[_Body, ...]
    flags: tuple[str, ...]


@dataclass(frozen=True)
class _Claim:
    call: str
    file: str
    block: int
    output: tuple[int, int]
    source: tuple[int, int]


@dataclass
class _Window:
    row: int
    end: int
    kind: str
    requirements: dict[str, str]
    first_action: int | None = None
    attempts: list = field(default_factory=list)
    coverage: dict = field(default_factory=dict)
    unresolved: list = field(default_factory=list)


_HEADER = re.compile(r"Script (completed|failed|running with cell ID [^\n]+)\nWall time [0-9.]+ seconds\nOutput:\n")
_HEADER_FLAGS = {"completed": (), "failed": ("command_failed",), "running": ("command_still_running",)}
_NATIVE_HEADER = re.compile(r"Script (?:completed|failed|running)\b|Chunk ID: |Wall time: |Exit code: |Process exited with code |Original token count: ")
_NOTICE = re.compile(rb"(?im)^(?:Warning: truncated output\b|\[?output (?:truncated|omitted)\b|\.\.\.\s*\d+ (?:characters|tokens) truncated\b)|\xe2\x80\xa6\d+ (?:tokens|chars) truncated\xe2\x80\xa6")
_ENVELOPE_KEYS = {"output", "exit_code", "chunk_id", "wall_time_seconds", "original_token_count", "session_id", "truncated"}


def _bodies(output, row):
    _require(isinstance(output, (str, list)), "unsupported_outer_output", row)
    blocks = output if isinstance(output, list) else [output]
    result = []
    for index, block in enumerate(blocks):
        flags = ()
        if isinstance(block, dict):
            flags = _flags(block)
            if block.get("type") not in ("input_text", "text") or "text" not in block or block.keys() - {"type", "text", "truncated"}:
                encoded = json.dumps(block, sort_keys=True).encode()
                result.append(_Body(index, "unsupported", encoded, None, flags))
                continue
            text = block["text"]
        else:
            text = block
        data = _text(text, row)
        header = _HEADER.fullmatch(text) if index == 0 else None
        if header:
            flags += _HEADER_FLAGS[header[1].split()[0]]
            result.append(_Body(index, "completion_header", data, None, flags))
            continue
        if _NATIVE_HEADER.match(text):
            result.append(_Body(index, "unsupported", data, None, flags))
            continue
        inner = None
        if text.lstrip().startswith("{"):
            try:
                inner = _json(text, row)
            except _InputError:
                result.append(_Body(index, "unsupported", data, None, flags))
                continue
        kind = "text"
        if isinstance(inner, dict) and set(inner) == {"i", "result"}:
            settled = inner["result"]
            if type(inner["i"]) is not int or not isinstance(settled, dict) or set(settled) != {"status", "value"} or settled["status"] != "fulfilled":
                result.append(_Body(index, "unsupported", data, None, flags + ("settled_result_not_fulfilled",)))
                continue
            inner = settled["value"]
            kind = "settled_command_result"
        elif isinstance(inner, dict) and ("output" in inner or "exit_code" in inner):
            kind = "command_result"
        if kind != "text":
            if not isinstance(inner, dict) or inner.keys() - _ENVELOPE_KEYS or not isinstance(inner.get("output"), str):
                result.append(_Body(index, "unsupported", data, None, flags))
                continue
            flags += _flags(inner)
            code = inner.get("exit_code")
            if type(code) is not int:
                flags += ("missing_integer_exit_code",)
                code = None
            elif code != 0:
                flags += ("command_failed",)
            if "session_id" in inner and code is None:
                flags += ("command_still_running",)
            result.append(_Body(index, kind, data, _text(inner["output"], row), flags))
        elif inner is not None:
            result.append(_Body(index, "unsupported", data, None, flags))
        else:
            result.append(_Body(index, kind, data, data, flags))
    return tuple(result)


def _trace(raw):
    _require(bool(raw), "empty_raw")
    lines = raw.split(b"\n")
    if lines[-1] == b"":
        lines.pop()
    records = []
    line_bytes = []
    starts = {}
    returns = {}
    allowed = {"session_meta", "turn_context", "event_msg", "world_state", "compacted",
               "response_item", "token_usage_record", "inter_agent_communication_metadata"}
    for number, line in enumerate(lines, 1):
        _require(bool(line.strip()), "empty_jsonl_row", number)
        record = _json(line, number)
        _require(isinstance(record, dict) and isinstance(record.get("type"), str) and
                 record["type"] in allowed, "unsupported_record", number)
        _require(isinstance(record.get("payload"), dict), "unsupported_payload", number)
        records.append(record)
        line_bytes.append(line + (b"\n" if number < len(lines) or raw.endswith(b"\n") else b""))
        if record["type"] != "response_item":
            continue
        payload = record["payload"]
        kind = payload.get("type")
        if kind in ("message", "reasoning", "agent_message"):
            continue
        _require(kind in ("function_call", "custom_tool_call", "function_call_output", "custom_tool_call_output"),
                 "unsupported_response_item", number)
        call_id = _string(payload.get("call_id"), number)
        target = returns if kind.endswith("_output") else starts
        _require(call_id not in target, "duplicate_outer_identity", number)
        target[call_id] = (number, record)
    _require(starts.keys() == returns.keys(), "unpaired_outer_call")
    calls = {}
    for call_id, (number, record) in starts.items():
        returned, returned_record = returns[call_id]
        payload = record["payload"]
        result = returned_record["payload"]
        _require(number < returned, "return_precedes_call", returned)
        _require(result["type"] == payload["type"] + "_output", "mismatched_outer_kind", returned)
        _string(payload.get("name"), number)
        _require("output" in result, "missing_outer_output", returned)
        calls[call_id] = _Call(call_id, number, returned, _bodies(result["output"], returned),
                               _flags(record, payload, returned_record, result))
    return records, line_bytes, calls


def _read_file(path, code):
    try:
        return path.read_bytes()
    except (OSError, UnicodeError, ValueError) as error:
        raise _InputError(code) from error


def _bind(raw, manifest, directory):
    _object(manifest, {"schema_version", "raw_sha256", "assessment_scope", "review", "files", "boundaries", "calls", "reads"}, {"initial_injections"})
    _require(manifest["schema_version"] == 1 and type(manifest["schema_version"]) is int, "unsupported_schema")
    _require(_digest(manifest["raw_sha256"]) == _sha(raw), "raw_hash_mismatch")
    scope = manifest["assessment_scope"]
    _require(scope in ("MODE_ENTRY_CHECKPOINT", "CURRENT_STEP_RECOVERY"), "invalid_assessment_scope")
    review = _object(manifest["review"], {"reviewer", "complete"})
    _string(review["reviewer"])
    _require(review["complete"] is True, "review_not_complete")
    records, lines, calls = _trace(raw)

    def row_ref(value, number_key="row", hash_key="row_sha256"):
        number = value[number_key]
        _require(type(number) is int and 1 <= number <= len(records), "invalid_row_reference")
        _require(_digest(value[hash_key], number) == _sha(lines[number - 1]), "row_hash_mismatch", number)
        return number, records[number - 1]

    files = {}
    for item in _array(manifest["files"]):
        _object(item, {"id", "path", "sha256", "role"})
        file_id = _string(item["id"])
        _require(file_id not in files, "duplicate_file")
        relative = Path(_string(item["path"]))
        _require(not relative.is_absolute() and ".." not in relative.parts, "expected_path_not_relative")
        data = _read_file(directory / relative, "expected_file_unreadable")
        try:
            data.decode("utf-8")
        except UnicodeError as error:
            raise _InputError("expected_file_not_utf8") from error
        _require(bool(data) and _digest(item["sha256"]) == _sha(data), "expected_file_hash_or_bytes_mismatch")
        _require(item["role"] in ("mode_entry", "guidance"), "invalid_file_role")
        files[file_id] = _File(file_id, item["role"], data)
    _require(sum(f.role == "mode_entry" for f in files.values()) == 1, "require_one_mode_entry")
    entry = next(f.id for f in files.values() if f.role == "mode_entry")
    windows = []
    seen_boundaries = set()
    for item in _array(manifest["boundaries"]):
        _object(item, {"row", "row_sha256", "kind", "requirements"})
        number, record = row_ref(item)
        _require(number not in seen_boundaries, "duplicate_boundary", number)
        seen_boundaries.add(number)
        kind = item["kind"]
        _require(kind in ("native_compacted", "supplied_context_summary", "supplied_truncation"), "invalid_boundary_kind", number)
        _require((record["type"] == "compacted") == (kind == "native_compacted"), "boundary_kind_mismatch", number)
        if kind == "supplied_context_summary":
            payload = record["payload"]
            _require(record["type"] == "response_item" and payload.get("type") == "message" and
                     payload.get("role") == "user", "summary_boundary_not_user_message", number)
        if kind == "supplied_truncation":
            _require(record["payload"].get("type") not in ("function_call", "custom_tool_call"),
                     "truncation_boundary_is_call_start", number)
        requirements = {}
        for required in _array(item["requirements"], number):
            _object(required, {"file", "policy"}, row=number)
            file_id = required["file"]
            _require(isinstance(file_id, str) and file_id in files and file_id not in requirements, "invalid_requirement_file", number)
            policy = required["policy"]
            _require(policy in ("whole_standalone", "explicit_chunks"), "invalid_read_policy", number)
            _require(file_id != entry or policy == "whole_standalone", "mode_entry_cannot_use_chunks", number)
            requirements[file_id] = policy
        _require(entry in requirements, "missing_mode_requirement", number)
        _require(scope != "MODE_ENTRY_CHECKPOINT" or set(requirements) == {entry}, "checkpoint_has_extra_requirements", number)
        windows.append(_Window(number, len(records) + 1, kind, requirements))
    _require(bool(windows), "missing_boundary")
    windows.sort(key=lambda window: window.row)
    _require({i for i, record in enumerate(records, 1) if record["type"] == "compacted"} ==
             {window.row for window in windows if window.kind == "native_compacted"}, "omitted_native_boundary")
    for left, right in zip(windows, windows[1:]):
        left.end = right.row
    dispositions = {}
    for item in _array(manifest["calls"]):
        _object(item, {"row", "row_sha256", "call_id", "disposition", "reason"})
        number, _ = row_ref(item)
        call_id = item["call_id"]
        _require(isinstance(call_id, str) and call_id in calls and calls[call_id].row == number, "call_reference_mismatch", number)
        _require(call_id not in dispositions, "duplicate_call_disposition", number)
        _require(item["disposition"] in ("governed", "incidental", "unresolved"), "invalid_call_disposition", number)
        _string(item["reason"], number)
        dispositions[call_id] = item["disposition"]
    _require(set(dispositions) == {call.id for call in calls.values() if call.row > windows[0].row}, "incomplete_call_review")
    claims = []
    seen_claims = set()
    for item in _array(manifest["reads"]):
        _object(item, {"call_id", "return_row", "return_sha256", "file", "block", "output_range", "source_range"})
        number, _ = row_ref(item, "return_row", "return_sha256")
        call_id = item["call_id"]
        _require(isinstance(call_id, str) and call_id in calls and calls[call_id].return_row == number, "read_pair_mismatch", number)
        file_id = item["file"]
        _require(isinstance(file_id, str) and file_id in files, "unknown_read_file", number)
        block = item["block"]
        _require(type(block) is int and 0 <= block < len(calls[call_id].bodies), "invalid_block_reference", number)
        body = calls[call_id].bodies[block]
        _require(body.kind != "completion_header", "metadata_is_not_source", number)
        limit = len(body.data) if body.data is not None else None
        output_span = _span(item["output_range"], limit, number)
        source_span = _span(item["source_range"], len(files[file_id].data), number)
        claim = _Claim(call_id, file_id, block, output_span, source_span)
        _require(claim not in seen_claims, "duplicate_read_claim", number)
        seen_claims.add(claim)
        claims.append(claim)
    encodings = {file.id: _encodings(file.data) for file in files.values()}
    for call_id in calls:
        selected = [claim for claim in claims if claim.call == call_id]
        for block in {claim.block for claim in selected}:
            spans = sorted(claim.output for claim in selected if claim.block == block)
            _require(all(left[1] <= right[0] for left, right in zip(spans, spans[1:])), "overlapping_output_claims", calls[call_id].return_row)
        data = b""
        offsets = {}
        for body in calls[call_id].bodies:
            if body.data is not None:
                offsets[body.block] = len(data)
                data += body.data
        for file in files.values():
            start = data.find(file.data)
            while start != -1:
                spans = [claim.source for claim in selected if claim.file == file.id and claim.block in offsets and
                         offsets[claim.block] + claim.output[0] == start + claim.source[0] and
                         offsets[claim.block] + claim.output[1] == start + claim.source[1]]
                _require(_complete(spans, len(file.data)),
                         "undeclared_governing_body", calls[call_id].return_row)
                start = data.find(file.data, start + 1)
        for body in calls[call_id].bodies:
            if body.kind == "unsupported":
                for file in files.values():
                    _require(not any(form in body.raw for form in encodings[file.id]) or
                             any(claim.file == file.id and claim.block == body.block for claim in selected),
                             "undeclared_governing_body", calls[call_id].return_row)
    injections = []
    for item in _array(manifest.get("initial_injections", [])):
        _object(item, {"row", "row_sha256", "file", "block", "output_range"})
        number, record = row_ref(item)
        payload = record["payload"]
        _require(record["type"] == "response_item" and payload.get("type") == "message" and payload.get("role") == "user", "invalid_initial_injection", number)
        _require(number < windows[0].row, "injection_is_not_recovery", number)
        file_id = item["file"]
        _require(isinstance(file_id, str) and file_id in files, "unknown_injection_file", number)
        content = _array(payload.get("content"), number)
        block = item["block"]
        _require(type(block) is int and 0 <= block < len(content) and isinstance(content[block], dict), "invalid_injection_block", number)
        data = _text(content[block].get("text"), number)
        start, end = _span(item["output_range"], len(data), number)
        injections.append({"row": number, "file": file_id, "exact_content": data[start:end] == files[file_id].data,
                           "recovery_credit": False})
    return files, windows, calls, dispositions, claims, injections


def _encodings(data):
    forms = {data}
    for _ in range(2):
        forms |= {json.dumps(form.decode(), ensure_ascii=ascii_only)[1:-1].encode() for form in forms for ascii_only in (False, True)}
    return forms


def _complete(spans, size):
    end = 0
    for start, stop in sorted(spans):
        if start > end:
            return False
        end = max(end, stop)
    return end == size


def _residual(data, spans):
    cursor = 0
    result = bytearray()
    for left, right in sorted(spans):
        result.extend(data[cursor:left])
        cursor = right
    result.extend(data[cursor:])
    return bytes(result)


def _measure(call, claims, files):
    exact = []
    flags = set(call.flags)
    extra = False
    unsupported = False
    for body in call.bodies:
        flags.update(body.flags)
        if body.kind == "completion_header":
            continue
        if body.data is None:
            unsupported = True
            flags.add("unsupported_output_carrier")
            continue
        spans = []
        for claim in claims:
            if claim.block != body.block:
                continue
            left, right = claim.output
            start, end = claim.source
            if body.data[left:right] == files[claim.file].data[start:end]:
                exact.append(claim)
                spans.append((left, right))
        residual = _residual(body.data, spans)
        if residual:
            extra = True
            if _NOTICE.search(residual):
                flags.add("transport_notice")
    file_ids = {claim.file for claim in exact}
    if len(file_ids) > 1:
        packaging = "MIXED_FILES"
    elif unsupported:
        packaging = "UNVERIFIED"
    elif extra:
        packaging = "EXTRA_CONTENT"
    elif len(file_ids) == 1:
        packaging = "STANDALONE"
    else:
        packaging = "UNVERIFIED"
    return exact, packaging, tuple(sorted(flags)), unsupported


def _evaluate(files, windows, calls, dispositions, claims, injections, scope):
    claims_by_call = {}
    for claim in claims:
        claims_by_call.setdefault(claim.call, []).append(claim)
    owner = {}
    for call in calls.values():
        owner[call.id] = next((window for window in windows if window.row < call.row < window.end), None)
    events = []
    for call in calls.values():
        events.append((call.row, "call", call))
        events.append((call.return_row, "return", call))
    outside = []
    for _, kind, call in sorted(events, key=lambda event: event[0]):
        window = owner[call.id]
        if kind == "call":
            if window is not None:
                disposition = dispositions[call.id]
                if disposition == "unresolved":
                    window.unresolved.append(call.row)
                if disposition == "governed" and window.first_action is None:
                    window.first_action = call.row
            continue
        selected = claims_by_call.get(call.id, [])
        if not selected:
            continue
        exact, packaging, flags, unsupported = _measure(call, selected, files)
        for file_id in sorted({claim.file for claim in selected}):
            spans = [claim.source for claim in exact if claim.file == file_id]
            whole = (0, len(files[file_id].data)) in spans
            if window is None or call.return_row >= window.end:
                ordering = "CROSSES_BOUNDARY"
            elif window.first_action is not None:
                ordering = "LATE"
            else:
                ordering = "BEFORE_ACTION"
            observed = "COMPLETE" if _complete(spans, len(files[file_id].data)) else "EXACT_CHUNK" if spans else "UNVERIFIED"
            attempt = {"call_id": call.id, "call_row": call.row, "return_row": call.return_row, "file": file_id,
                       "content": observed, "source_ranges": [list(span) for span in spans], "whole_body": whole,
                       "packaging": packaging, "ordering": ordering,
                       "transport": "UNVERIFIED" if flags or unsupported else "CLEAR", "reasons": list(flags),
                       "repaired_before_action": False}
            if window is None:
                outside.append(attempt)
                continue
            index = len(window.attempts)
            window.attempts.append(attempt)
            if ordering == "BEFORE_ACTION" and packaging == "STANDALONE" and not flags and not unsupported:
                policy = window.requirements.get(file_id)
                if policy == "explicit_chunks" or (policy == "whole_standalone" and whole):
                    progress = window.coverage.setdefault(file_id, [])
                    progress.extend((span, index) for span in spans)
    reports = []
    for window in windows:
        requirement_reports = []
        repaired = False
        failed = False
        inconclusive = any(window.first_action is None or row < window.first_action for row in window.unresolved)
        for file_id, policy in window.requirements.items():
            progress = window.coverage.get(file_id, [])
            satisfied = _complete([span for span, _ in progress], len(files[file_id].data))
            attempts = [(i, attempt) for i, attempt in enumerate(window.attempts) if attempt["file"] == file_id]
            witnesses = sorted({index for _, index in progress}) if satisfied else []
            unrepaired = []
            if satisfied:
                for index, attempt in attempts:
                    unverified = attempt["transport"] != "CLEAR" or attempt["content"] == "UNVERIFIED"
                    proven_violation = (attempt["content"] != "UNVERIFIED" and
                                        (attempt["packaging"] != "STANDALONE" or
                                         (policy == "whole_standalone" and not attempt["whole_body"])))
                    if (unverified or proven_violation) and attempt["ordering"] == "BEFORE_ACTION":
                        if _complete([span for span, witness in progress
                                      if window.attempts[witness]["return_row"] > attempt["return_row"]],
                                     len(files[file_id].data)):
                            attempt["repaired_before_action"] = True
                            repaired = True
                        elif proven_violation:
                            unrepaired.append(index)
                            failed = True
                        else:
                            inconclusive = True
            else:
                failed = True
                if any(attempt["ordering"] == "BEFORE_ACTION" and
                       (attempt["transport"] != "CLEAR" or attempt["content"] == "UNVERIFIED")
                       for _, attempt in attempts):
                    inconclusive = True
            requirement_reports.append({"file": file_id, "policy": policy, "satisfied_before_action": satisfied,
                                        "witness_attempts": witnesses, "unrepaired_violation_attempts": unrepaired,
                                        "observed_content_complete": _complete([tuple(span) for _, attempt in attempts for span in attempt["source_ranges"]], len(files[file_id].data))})
        if window.first_action is None:
            status = "NO_LATER_GOVERNED_ACTION" if not window.unresolved else "INCONCLUSIVE"
            for attempt in window.attempts:
                if attempt["ordering"] == "BEFORE_ACTION":
                    attempt["ordering"] = "NO_ACTION"
        elif inconclusive:
            status = "INCONCLUSIVE"
        elif failed:
            status = "FAIL"
        else:
            status = "SATISFIED_WITH_REPAIRS" if repaired else "SATISFIED"
        reports.append({"boundary_row": window.row, "boundary_kind": window.kind, "end_row_exclusive": window.end,
                        "assessment_scope": scope, "first_action_row": window.first_action,
                        "status": status, "requirements": requirement_reports, "attempts": window.attempts,
                        "unresolved_call_rows": window.unresolved})
    statuses = {report["status"] for report in reports}
    if "INCONCLUSIVE" in statuses:
        code, status = 2, "INCONCLUSIVE"
    elif "FAIL" in statuses:
        code, status = 1, "FAIL"
    elif statuses == {"NO_LATER_GOVERNED_ACTION"}:
        code, status = 3, "NO_LATER_GOVERNED_ACTION"
    elif "SATISFIED_WITH_REPAIRS" in statuses:
        code, status = 0, "SATISFIED_WITH_REPAIRS"
    else:
        code, status = 0, "SATISFIED"
    return code, {"status": status, "assessment_scope": scope, "windows": reports,
                  "total_windows": len(windows),
                  "applicable_windows": sum(window.first_action is not None for window in windows),
                  "non_applicable_windows": sum(report["status"] == "NO_LATER_GOVERNED_ACTION" for report in reports),
                  "initial_deliveries": injections, "outside_window_attempts": outside}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args(argv)
    report = {"schema_version": 1, "evaluator_sha256": _sha(Path(__file__).read_bytes()),
              "semantic_limit": "Action classifications and complete requirements are reviewed inputs, not inferred guarantees."}
    try:
        raw = _read_file(args.raw, "raw_unreadable")
        manifest_bytes = _read_file(args.manifest, "manifest_unreadable")
        report.update(raw_sha256=_sha(raw), manifest_sha256=_sha(manifest_bytes))
        manifest = _json(manifest_bytes)
        bound = _bind(raw, manifest, args.manifest.parent)
        code, result = _evaluate(*bound, manifest["assessment_scope"])
        report.update(result)
        files, _, calls, _, _, _ = bound
        report["files"] = [{"id": item.id, "role": item.role, "sha256": _sha(item.data), "bytes": len(item.data)} for item in files.values()]
        report["outer_responses"] = [{"call_id": call.id, "call_row": call.row, "return_row": call.return_row,
                                       "blocks": [{"index": body.block, "carrier": body.kind, "raw_sha256": _sha(body.raw),
                                                   "raw_bytes": len(body.raw), "body_sha256": _sha(body.data) if body.data is not None else None,
                                                   "body_bytes": len(body.data) if body.data is not None else None} for body in call.bodies]}
                                      for call in calls.values()]
    except _InputError as error:
        code = 2
        report.update(status="INCONCLUSIVE", errors=[{"code": error.code, "row": error.row}], windows=[])
    print(json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
