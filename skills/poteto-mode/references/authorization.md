# Apply authorization to irreversible writes

Irreversible writes include force-push to shared branches, deploys, data deletion, and customer messages. A request that names the action grants authorization within its stated scope. Proceed without asking again. A request to prepare, rehearse, review, or plan an action does not authorize execution.

Unnamed actions, operator-reserved decisions, and tool-enforced approvals still need permission. A full-autonomy grant does not bypass a refused gate or expand the requested scope.

If a real blocker needs the operator, retain the pending agent action and diagnostic evidence. In an unattended run, continue independent authorized work first. Preserve the blocked action and required decision when nothing else can proceed. Never report blocked work as complete. Already-authorized work and scheduled waiting with an actual wake owner need no operator question or helper invocation. Preserve the [usage-limit recovery procedure](usage-limit-recovery.md).

Judge what the operator must supply before constructing the reply. Choose one necessary operator action, new approval for an agent action outside the grant, or confirmation of an evidenced fact. Preserve actor reservations and retain the assigned work.

Request new approval for an agent action only when evidence establishes its necessity and an executable route the agent can use after approval. An approval-required refusal establishes a gate, not an agent operation for clearing it. If the clearing route is unknown, retain that uncertainty and request one necessary operator action or named information artifact. Never invent agent capability.

A connection refusal alone does not establish a clearing action. If a required fact has no evidenced candidate, request one named information artifact through a faithful provide action. Never invent a value to make a confirmation fit. The helper checks representation, not necessity, authority, factual truth, or a single real-world operation.

For that operator dependency, invoke the installed [whole-reply helper](../scripts/operator-request.py). Resolve `PSTACK_SKILLS_ROOT` through the [portable resource contract](../../pstack-harness/references/portable-paths.md). Obtain the authoritative fields, outcomes, statuses, and examples needed for the request. A direct help call is available and reads no stdin.

```sh
exec python3 "${PSTACK_SKILLS_ROOT:?}/poteto-mode/scripts/operator-request.py" --help
```

Diagnostic consultation may use identifiable content actually observed in a tool display, attributed as an excerpt. Missing, truncated, ambiguous, or contradictory decision-relevant clauses remain unresolved until you obtain the needed authoritative information. Clean help is available, but is not an unconditional prerequisite for an independently valid reply. A displayed kind, status, error word, or excerpt proves no actual completion, source authenticity, complete channels, or genuine unavailability.

Verification must separately exercise the actual source-bound installed command's complete help record and every executable example. Diagnostic excerpts cannot satisfy that proof or justify a complete-help claim. For complete help, observe completed success, decode the whole help record once, and read its `text`.

Supply the request directly on stdin using the quoted here-document examples in help. A reply-producing native call executes only the helper command. Use `exec` so the native completion observation belongs to that process. Keep the request in stdin without staging a request file or writing a caller capture program.

For final reply data, accept only the whole strict generated `kind` and `text` object described in help, with its one outer LF or with that LF absent from the native display. Field order does not affect interpretation. Reject extra whitespace, prefixes, suffixes, additional documents, duplicate or unknown keys, malformed data, and replacement decoding. Never extract final reply data from noisy output. Native error prefixes are tool metadata, not application stderr or successful reply data. If the tool merges channels, the entire reply-producing command-output value must still be exactly one record. Separate channels must contain no unaccounted application output. Every reportable helper outcome still emits exactly one declared record.

The record is generated data. Neither field captures process channels or establishes process completion. Observe actual completed success separately through the native tool before using any reply. Running, yielded, unknown, interrupted, cancelled, timed-out, truncated, or failed invocations supply no usable reply, even when complete reply-shaped data is visible. If the tool cannot establish completion independently, this integration is unusable.

For diagnostic evidence obtained only from a tool display, use a neutral label such as "command output, tool-display excerpt" or "file display excerpt". A trimmed or merged display is an excerpt. Keep literal excerpt values exact. Record return codes and other metadata separately under their actual sources. If you combine or rephrase observations, explicitly label the source as a factual summary rather than a literal excerpt.

Never label a tool-display excerpt complete stderr or complete file contents. To claim a complete channel or file, first retain its actual original bytes. Do not strip or normalize those bytes while claiming completeness. Retain original diagnostic bytes outside the helper input. Decode them with strict UTF-8 only when decoding succeeds. For non-UTF-8 bytes, supply their exact lowercase hexadecimal text. Label the source with the encoding and its actual complete or excerpt scope. A complete label requires complete capture. Keep an excerpt labeled as an excerpt. Never use replacement decoding or invent original bytes from replaced or truncated tool display. An unavailable original stream remains a proof gap, not `UNAVAILABLE`.

After actual completed success and acceptance of a complete `reply` record, use its once-decoded `text`. Review the whole text's meaning, evidence, and actors. Copy that text unchanged as the whole final reply, including its terminal LF. If final extraction omits that one LF, compare the whole final plus one LF with the returned text. No other stripping, normalization, reflow, prefix, suffix, code fence, explanation, or competing request is allowed. Do not decode the body's quoted literals again. Matching only the last question is insufficient. This also applies to a sandbox or tool refusal that leaves a genuine operator dependency. The helper cannot enforce invocation, copying, or continued agent ownership of the work.

Use diagnostic records only to diagnose and correct failures. Never send them as the final reply. Use the help contract to distinguish input rejection, internal defects, and runtime or process I/O unavailability. Correct rejected input and invoke again. Never send rejected content manually. An internal defect, interruption, unexplained failure, or missing original evidence does not establish unavailability. Only demonstrated runtime or process I/O unavailability permits a manual final yes/no question under the [writing rule](writing.md). Confirm a missing interpreter or helper before taking the fallback. Missing output alone is insufficient. Put the pending agent work, diagnostic evidence, formatting-unverified notice, and continuation consequences before the one final direct yes/no question. End the reply at that question. An unavailable helper creates no new approval or installation gate. Continue independently authorized work. If the required reply cannot be represented faithfully, preserve that gap rather than invent data or call it unavailability.

For a catalog export that needs the operator's destination, use this factual-summary example only after the observed runtime failure and a direct path check confirm a missing helper file.

```text
My work to export "catalog" remains pending until you provide the catalog destination.
Factual summary of the runtime failure and path check: Python could not open the installed helper file, and the check confirmed its absence.
This manual reply's formatting is unverified. Once you provide the destination, I will export the catalog and verify the result.

Will you provide the catalog destination?
```
