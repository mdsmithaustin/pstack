# Sanitized native format controls

These files contain minimal Codex 0.162.0 output shapes described in [issue 287](https://github.com/mdsmithaustin/pstack/issues/287). They are model-free parser inputs. No file is a new native trial or a copy of a private recording.

`mixed-full.jsonl` is a hand-built projection of the recorded native compaction failure. Two inner command envelopes share one outer response after a `compacted` record. Their complete bodies remain separate blocks. An automatic completion header is another block.

`pickup-late-entry.jsonl` projects the separate recorded Session pickup caller. The supplied context-summary condition is not native compaction. One outer call reads two governing files and discovers task files. Its settled-result wrappers contain three command results. A later standalone entry response arrives after that task-discovery action. The recovery window must fail even though the later response passes the isolated packaging check.

`repaired-entry.jsonl` is a synthetic contrast to the failed mixed response. It adds a complete standalone entry read before the task action. It tests a repaired-before-action result, with the earlier packaging violation retained. It cannot establish native model behavior.

The guidance in `entry.md` and `step.md`, task text, output, call identifiers, commands, timings, and row positions are replacements. The fixtures contain no original task content, credentials, host paths, or original session identifiers. Each JSONL file has a matching reviewed manifest. The public CLI tests verify their expected outcomes. The projections preserve only the native boundaries and carriers needed for these controls. Independent privacy and provenance review belongs to the exact committed fixture revision.
