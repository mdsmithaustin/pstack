# Skill recovery evaluator

`evaluate.py` checks reviewed recovery prerequisites in saved native Codex JSONL. It compares returned UTF-8 bytes with frozen guidance, preserves each outer call and response block, and reports content, packaging, transport, and order separately. It uses the Python standard library and calls no model or service.

This is an offline evaluator. Its manifest supplies the required guidance, recovery boundaries, and action classifications. A reviewer must establish their completeness. A result covers only the named scope and supplied recording. It does not establish runtime interception, model obedience, or compliance outside that scope.

## CLI reference

From the repository root, the synthetic repaired control runs with this command.

```sh
python3 evals/skill-recovery/evaluate.py --raw evals/skill-recovery/fixtures/repaired-entry.jsonl --manifest evals/skill-recovery/fixtures/repaired-entry.manifest.json
```

Failure signals are a nonzero exit, a status other than `SATISFIED_WITH_REPAIRS`, or an applicable window count other than one. The earlier mixed response remains in `windows[0].attempts` with `repaired_before_action` set to true.

The recorded-failure projection runs with this command.

```sh
python3 evals/skill-recovery/evaluate.py --raw evals/skill-recovery/fixtures/mixed-full.jsonl --manifest evals/skill-recovery/fixtures/mixed-full.manifest.json
```

The expected result is exit 1 and status `FAIL`. Any other exit or status fails this negative control. Complete bodies from two files share one outer response and receive `MIXED_FILES` packaging.

The pickup projection runs with this command.

```sh
python3 evals/skill-recovery/evaluate.py --raw evals/skill-recovery/fixtures/pickup-late-entry.jsonl --manifest evals/skill-recovery/fixtures/pickup-late-entry.manifest.json
```

The expected result is exit 1 and status `FAIL`. Any other exit or status fails this negative control. Its first call both reads guidance and discovers task files. That action freezes recovery before the call returns. The later standalone entry read reports `LATE` and cannot repair the window.

The CLI writes one JSON report to stdout. Input files remain unchanged. Reports contain hashes and byte counts rather than raw task content. Standard argument errors go to stderr.

| Exit | Overall result |
| --- | --- |
| 0 | Every applicable window is `SATISFIED` or `SATISFIED_WITH_REPAIRS`. |
| 1 | A supported applicable window fails a required prerequisite. |
| 2 | Invalid, unsupported, incomplete, or unresolved evidence makes the result `INCONCLUSIVE`. |
| 3 | Every window is `NO_LATER_GOVERNED_ACTION`. No recovery checkpoint was checked. |

`total_windows`, `applicable_windows`, and `non_applicable_windows` expose the denominator. A window without a governed action never counts as recovered. An empty boundary list is inconclusive. Inconclusive results take precedence over failures in the overall result.

## Manifest reference

The three fixture manifests are complete examples of schema version 1. Unknown fields and duplicate JSON keys are invalid. Row numbers and block indexes are one-based and zero-based respectively. Byte ranges are half-open offsets into decoded UTF-8 bodies or frozen UTF-8 source bytes. Row hashes include the original line terminator when present.

| Field | Contract |
| --- | --- |
| `schema_version` | Integer `1`. |
| `raw_sha256` | SHA-256 of every original JSONL byte. |
| `assessment_scope` | `MODE_ENTRY_CHECKPOINT` or `CURRENT_STEP_RECOVERY`. |
| `review` | Nonempty `reviewer` and literal `complete: true`. This records an assertion, not proof of the review. |
| `files` | Unique `id`, manifest-relative `path`, exact `sha256`, and `role` of `mode_entry` or `guidance`. Exactly one file has the mode entry role. Absolute paths and parent traversal are invalid. |
| `boundaries` | Each boundary's `row`, `row_sha256`, `kind`, and complete `requirements`. |
| `calls` | Every outer call after the earliest boundary, with `row`, `row_sha256`, `call_id`, `disposition`, and nonempty `reason`. |
| `reads` | Independent claims binding `call_id`, `return_row`, `return_sha256`, `file`, `block`, `output_range`, and `source_range`. |
| `initial_injections` | Optional pre-boundary user-message claims with `row`, `row_sha256`, `file`, `block`, and `output_range`. |

Boundary kinds are `native_compacted`, `supplied_context_summary`, and `supplied_truncation`. Every native `compacted` record must appear in the manifest. A supplied context summary must identify a user message. A truncation boundary cannot identify a call start. Supplied boundaries describe reviewed conditions and remain distinct from native compaction.

Each requirement has `file` and `policy`. The mode entry always uses `whole_standalone`. Other guidance can use `whole_standalone` or `explicit_chunks`. `MODE_ENTRY_CHECKPOINT` allows only the entry requirement. `CURRENT_STEP_RECOVERY` requires the reviewer to establish the complete set for that step. A narrow entry result does not certify the whole procedure.

Call dispositions are `governed`, `incidental`, and `unresolved`. Read claims do not replace dispositions. A call can both read guidance and perform governed work. Its action occurs at call start, before its returned guidance can count. An unresolved disposition prevents a conclusive window result.

Exact source spans must match exact returned body spans. Overlapping output claims are invalid. A complete known governing body left unclaimed anywhere in the recording is invalid. This detects an omitted earlier full read attempt. The reviewer still owns the completeness of file inventory, partial-read claims, supplied boundaries, and action semantics.

## Native input reference

The parser supports native `function_call` and `custom_tool_call` records with their matching output records. Each `call_id` has exactly one call and one later return of the corresponding kind. Missing, duplicate, or mismatched pairs invalidate the entire input, including duplicates after an apparent success.

Supported top-level record types are `session_meta`, `turn_context`, `event_msg`, `world_state`, `compacted`, `response_item`, `token_usage_record`, and `inter_agent_communication_metadata`. Message and reasoning records provide context. Names in command arguments or file lists do not prove a read.

A returned output can be a string or a list of text blocks. Supported body carriers are plain text, a serialized command result with `output` and `exit_code`, and a fulfilled settled-result wrapper with `i`, `result.status`, and `result.value`. The command-result metadata keys are `chunk_id`, `wall_time_seconds`, `original_token_count`, `session_id`, and `truncated`. Unknown carriers remain unsupported. The parser never recursively flattens arbitrary JSON.

A separate first-block completion header matching `Script completed`, `Wall time ... seconds`, and `Output:` is metadata. Other unclaimed substantive output prevents standalone packaging. Multi-file bodies and blocks remain part of one outer response. Splitting an inner batch cannot turn it into standalone reads.

Structured truncation flags, transport notices outside matched source spans, command failures, and still-running commands prevent delivery credit. A truncation phrase inside exact source bytes is source text. No whitespace, line ending, or Unicode normalization occurs.

A requirement is satisfied only by clear, standalone, exact content returned within its recovery window before the first governed call. The entry requires one whole-body claim. Explicit helper chunks can accumulate within one window. Pre-boundary reads, initial injections, replacement history, late returns, and reads crossing a later boundary receive no recovery credit.

Attempts remain in the report after a repair. A later eligible read can repair an earlier violation before the action. An invalid required-file attempt after the final eligible read remains an unrepaired violation. The evaluator does not erase a bad batch to produce an unqualified clean result.

## Test reference

The public CLI suite runs with this command from the repository root.

```sh
python3 -m unittest discover -s tools -p test_skill_recovery.py -v
```

Failure signals are a nonzero exit, zero tests in the `Ran` summary, a missing summary, or a final result other than `OK`. The tests exercise stdout and process exits through the public command. They cover malformed and unsupported evidence, exact hashes and bytes, mixed responses, late repair, multiple windows, explicit chunks, and zero applicable checkpoints.

Fixture provenance and its limits are documented in [the fixture notes](fixtures/README.md). Private recording replays require separate reviewed manifests and retained derivation receipts. They are not shipped as public fixtures.
