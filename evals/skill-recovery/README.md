# Skill recovery evaluator

`evaluate.py` checks reviewed recovery prerequisites in saved native Codex JSONL. It compares returned UTF-8 bytes with frozen guidance, preserves each outer call and response block, and reports content, packaging, transport, and order separately. It uses the Python standard library and calls no model or service.

This is an offline evaluator. Its manifest supplies the required guidance, recovery boundaries, and action classifications. A reviewer must establish their completeness. A result covers only the named scope and supplied recording. It does not establish runtime interception, model obedience, or compliance outside that scope.

## CLI reference

From the repository root, the synthetic repaired control runs with this command.

```sh
python3 evals/skill-recovery/evaluate.py --raw evals/skill-recovery/fixtures/repaired-entry.jsonl --manifest evals/skill-recovery/fixtures/repaired-entry.manifest.json
```

Failure signals are a nonzero exit, a status other than `SATISFIED_WITH_REPAIRS`, or an applicable window count other than one. The earlier mixed response remains in `windows[0].attempts`. Its entry attempt, `attempts[0]`, has `repaired_before_action` set to true. Its step attempt stays false because `MODE_ENTRY_CHECKPOINT` has no step requirement to repair.

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

The CLI writes one JSON report to stdout. Input files remain unchanged. Reports contain hashes and byte counts rather than raw task content. A usage error, such as a missing `--raw`, writes the argparse message to stderr, prints no JSON report, and exits 2.

| Exit | Overall result |
| --- | --- |
| 0 | Every applicable window is `SATISFIED` or `SATISFIED_WITH_REPAIRS`. |
| 1 | A supported applicable window fails a required prerequisite. |
| 2 | Invalid, unsupported, incomplete, or unresolved evidence makes the result `INCONCLUSIVE`. A usage error also exits 2, without a report. |
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

Call dispositions are `governed`, `incidental`, and `unresolved`. Read claims do not replace dispositions. A call can both read guidance and perform governed work. Its action occurs at call start, before its returned guidance can count. An unresolved disposition before the first governed call, or in a window without one, prevents a conclusive window result. Later unresolved calls and late or boundary-crossing unverified reads remain visible without changing the verdict frozen at the first governed call. Invalid raw input still invalidates the entire assessment.

A claim is exact when its output bytes equal its source bytes. A claim whose bytes differ records unverified content. An exact claim and a mismatched claim in one outer response are invalid input (`inconsistent_read_claims`), because the evaluator cannot tell a manifest error from extra content. Overlapping output claims are invalid. Two claims of one file in one block whose output and source ranges both continue each other are invalid (`split_read_claim`). A contiguous read takes one claim.

A complete known governing body left unclaimed in any outer-call output is invalid (`undeclared_governing_body`). This detects an omitted earlier full read attempt. The scan does not depend on carrier classification. It searches the raw text and the decoded body of every block for each governing file, unescaped or JSON-escaped up to two levels deep. An unescaped body in the decoded bodies of one response needs exact claims that cover it, including a body split across blocks. A JSON-escaped body cannot be claimed exactly, so it is always undeclared. In raw text, a body is undeclared unless it lies inside the encoding of the block's decoded body. A body in result metadata is one example. An unsupported block has no decoded body, and a claim of the file on that block records an unverified attempt instead. The scan does not cover message records or `replacement_history`, and those deliveries receive no recovery credit. The reviewer still owns the completeness of file inventory, partial-read claims, supplied boundaries, and action semantics.

## Native input reference

The parser pairs native `function_call` and `custom_tool_call` records with their matching output records. Both kinds use the body carriers below. A block that starts with a native exec text header, such as `Chunk ID: `, `Wall time: `, `Exit code: `, `Process exited with code `, or `Original token count: `, is unsupported. A read inside such a block is inconclusive because no committed fixture fixes that header layout. Each `call_id` has exactly one call and one later return of the corresponding kind. Missing, duplicate, or mismatched pairs invalidate the entire input, including duplicates after an apparent success.

Supported top-level record types are `session_meta`, `turn_context`, `event_msg`, `world_state`, `compacted`, `response_item`, `token_usage_record`, and `inter_agent_communication_metadata`. The `message`, `reasoning`, and `agent_message` response items provide context, and call pairing skips them. Names in command arguments or file lists do not prove a read.

A returned output can be a string or a list of text blocks. Supported body carriers are plain text, a serialized command result with `output` and `exit_code`, and a fulfilled settled-result wrapper with `i`, `result.status`, and `result.value`. The command-result metadata keys are `chunk_id`, `wall_time_seconds`, `original_token_count`, `session_id`, and `truncated`. Unknown carriers remain unsupported. A JSON object block that matches no supported carrier, such as a `status` and `value` result, is unsupported. The parser never recursively flattens arbitrary JSON. JSON nested too deeply for the parser invalidates a raw row and makes a block unsupported.

A separate first-block header line of `Script completed`, `Script failed`, or `Script running with cell ID <id>`, followed by `Wall time ... seconds` and `Output:`, is metadata. A failed header adds `command_failed`, and a running header adds `command_still_running`. Any other block that starts with one of those script phrases is unsupported. Unclaimed output prevents standalone packaging unless it is a transport notice. The evaluator judges each unclaimed stretch between claims on its own. In a stretch that holds a notice, the notice and the stretch's whitespace do not count, and any other byte is extra content. An attempt whose only unclaimed bytes are notices gets the packaging it would have without them, and its transport is unverified. Multi-file bodies and blocks remain part of one outer response. Splitting an inner batch cannot turn it into standalone reads.

Structured truncation flags, transport notices outside matched source spans, command failures, and still-running commands prevent delivery credit. Transport notices are whole lines that start with `Warning: truncated output`, `output truncated`, `output omitted`, `... N tokens truncated`, or `... N characters truncated`, a line `Total output lines: N`, and the native `…N tokens truncated…` and `…N chars truncated…` markers anywhere in unclaimed output. A truncation phrase inside exact source bytes is source text. Byte comparison applies no whitespace, line-ending, or Unicode normalization.

A requirement is satisfied only by clear, standalone, exact content returned within its recovery window before the first governed call. Every `whole_standalone` requirement, the entry included, requires one whole-body claim in one block. Explicit helper chunks can accumulate within one window. Pre-boundary reads, initial injections, replacement history, late returns, and reads crossing a later boundary receive no recovery credit.

Attempts remain in the report after a repair. Later eligible reads must cover the entire required file after each violation and before the action to repair it. Earlier chunks cannot supply missing repair coverage. After a requirement is satisfied, each unrepaired pre-action attempt follows this precedence: exact-byte proof of mixed files or of extra content other than transport notices fails, as does a clear exact partial or non-whole read under the whole-body policy. Otherwise, unclear transport, unverified content, or unverified packaging makes the attempt inconclusive. All other attempts are valid. Later complete eligible coverage repairs both proven violations and inconclusive attempts. The evaluator does not erase a bad batch to produce an unqualified clean result.

## Test reference

The public CLI suite runs with this command from the repository root.

```sh
python3 -m unittest discover -s tools -p test_skill_recovery.py -v
```

Failure signals are a nonzero exit, zero tests in the `Ran` summary, a missing summary, or a final result other than `OK`. The tests exercise stdout and process exits through the public command. They cover malformed and unsupported evidence, exact hashes and bytes, mixed responses, late repair, multiple windows, explicit chunks, and zero applicable checkpoints.

Fixture provenance and its limits are documented in [the fixture notes](fixtures/README.md). Private recording replays require separate reviewed manifests and retained derivation receipts. They are not shipped as public fixtures.
