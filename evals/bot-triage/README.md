# Historical bot-triage comparison

`compare.py` submits saved review findings and source excerpts to a configured CLI. It compares each `fix`, `dismiss`, or `ask` recommendation with a separately stored reference. It never applies a fix, replies to a bot, or dismisses a review thread.

## Invocation

From the pstack checkout on macOS or Linux, with Python 3.12 or newer available as `python3`:

```sh
python3 evals/bot-triage/compare.py --cli codex
python3 evals/bot-triage/compare.py --cli claude
```

From another directory, use the absolute path to `compare.py`. The subprocess cleanup requires POSIX process groups.

`--workspace PATH` selects the CLI working directory. `--executable PATH` selects a trusted executable or wrapper. The runner never evaluates that argument in a shell. `--profile NAME` selects an existing Codex profile. Model, provider, authentication, HOME, CODEX_HOME, and environment variables remain under CLI control. There are no direct HTTP calls or API-key requirements added by this runner. Subscription eligibility and gateway routing depend on the installed CLI and its configuration; the report does not independently verify billing.

`--case ID` selects a case and can repeat. `--timeout SECONDS` defaults to 180 seconds per invocation. Codex MCP discovery has a maximum of 30 seconds within that limit. Cases run sequentially in fresh ephemeral sessions.

The runner creates a private directory under `runs/`, which Git ignores. It writes `report.json`. Successful output capture also produces numbered stdout and stderr receipts, including nonzero CLI exits. Capture or MCP-discovery failures can leave only the error recorded in the report. Capture failures include timeouts, unsupported wait durations, and output decoding errors. Those receipts can contain host configuration diagnostics. They are local evidence, not publication artifacts.

The process exits 0 when every disposition matches, 1 for any disagreement or unavailable result, and 2 for invalid input. A disagreement does not authorize an action. An `ask` answer is a valid recommendation. A failed invocation, timeout, malformed answer, or unsupported evidence citation is `unavailable`, not `ask`.

## Cases and references

`cases.json` contains model input and source provenance. The runner sends only its `input` object as case data. `answers.json` contains comparison references and their limitations. The runner does not send reference text or historical dispositions in the case prompt. The synthetic-versus-native packet includes reported observations from public independent review, without its disposition.

Each case has a unique `id`, a `source` object, and an `input` object with a nonempty `claim` and an `evidence` list. Each evidence item has a unique `id` and nonempty `text`. `intent` supplies optional context. An empty evidence list is valid for an insufficient-evidence case. Duplicate JSON fields and non-finite numbers are rejected. Malformed model JSON or JSON beyond the parser or report encoder nesting limit becomes an unavailable result.

| Case | Supplied snapshot | Reference |
| --- | --- | --- |
| `pr357-command-before` | Command matching before the fix | `fix` |
| `pr357-command-after` | The same claim against the fixed matching code | `dismiss` |
| `pr357-partial-artifact-read` | A separate partial-read finding at the reviewed head | `fix` |
| `pr407-missing-port-relationship` | Missing upstream-to-port ledger mapping | `fix` |
| `pr412-delegation-scope` | Arena instruction within the delegation paragraph | `dismiss` |
| `pr485-mixed-suite-followup` | Later mixed-style discovery omission in the same PR | `fix` |
| `pr485-runner-exit-one` | Preservation runner accepts exit 1 without parsed results | `fix` |
| `pr491-synthetic-versus-native` | Reproduced synthetic defect with no established supported caller | `ask` |
| `pr491-insufficient-dispatch-evidence` | Deliberately incomplete packet derived from the dispatch finding | `ask` |

These cases come from public PR findings and committed source, not private session transcripts. Each fixture records its source URL and commit. The PR #491 control is a constructed missing-evidence case. Its companion uses the public independent reproduction and native-evidence limits. The companion projects a historical tracked follow-up into `ask`; a `fix` disagreement requires human review, not automatic relabeling. Its reference does not reproduce the historical decision to defer the ambiguity. Cases from the same PR are correlated and must stay together in any future data split.

Nine curated cases cannot establish accuracy, a latency distribution, or readiness for automation. Reference agreement is a smoke check, not independent proof that a judgment is correct. The runner records elapsed invocation time, including failed discovery, and available usage even when answer validation fails. CLI startup and configuration contribute to elapsed time. Reported token usage or estimated cost does not establish subscription billing.

## Execution restrictions

Codex runs read-only with approvals disabled. The runner disables discovered MCP servers, shell tools, hooks, the legacy completion notifier, plugins, apps, browser and image tools, memory, and delegation. The configured developer-instructions setting is cleared for this invocation. Stdio MCP entries receive a disabled placeholder command to support desktop-injected entries that are absent from the on-disk configuration. A reported tool/action event or a tool-router rejection diagnostic invalidates the comparison. Nonfatal model-metadata warnings are retained when the turn completes with a valid answer. Unknown gateway model aliases can expose an interactive input tool that native exec rejects; stdout alone does not show that rejected attempt. If inherited logging suppresses router diagnostics, the runner cannot detect that rejected attempt. Native exec still rejects it without external action.

Codex can still add global `$CODEX_HOME/AGENTS.md` instructions. The runner does not replace HOME or CODEX_HOME to remove them, because that could change the configured route or credentials. The report discloses this context. The supplied-evidence instruction is a request to the model, not proof of an instruction-free call. Host instructions can affect judgments and comparisons across hosts.

Claude safe mode removes workspace instructions and other customizations while preserving normal authentication and model configuration. Claude runs with an empty tool set, an empty strict MCP configuration, hooks disabled, browser integration disabled, and session persistence disabled. The runner keeps normal CLI configuration; it does not use bare or restricted authentication modes.

These restrictions rely on the installed CLI honoring its flags and configuration. A trusted wrapper must preserve them. This is not an OS isolation boundary for a malicious executable or startup configuration. The initial adapters cover Codex and Claude Code. Other harnesses need an adapter and equivalent execution checks.

## Verification

The command below must exit 0 and report a nonzero test count. The offline contract tests use a fake configured CLI to check configuration inheritance, hidden reference answers, unavailable results, and comparison-only output:

```sh
python3 -m unittest discover -s tools -p test_bot_triage.py -v
```

A live invocation exercises the installed CLI. Inspect its report and receipts separately from the deterministic contract tests. Live runs use the configured model and can consume the account's available usage.
