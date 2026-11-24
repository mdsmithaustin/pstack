# Recover failed-check evidence

`failed-check-evidence` reads logs and JUnit artifacts for one Actions run and
the head SHA that the failed check tested. It requires Bun, authenticated `gh`,
and `python3` version 3.9 or newer. It does not rerun, cancel, or dispatch CI.

Supply the repository, run ID, full checked SHA, and observed run attempt.
These values identify the failed check. Artifact names do not establish the
checked head. The command does not select another run or look up a PR.

```sh
skills/poteto-mode/scripts/watch-pr/failed-check-evidence \
	--owner "$EVIDENCE_OWNER" --repo "$EVIDENCE_REPO" \
	--run "$EVIDENCE_RUN_ID" --head "$EVIDENCE_CHECKED_HEAD" \
	--attempt "$EVIDENCE_RUN_ATTEMPT"
```

`--host` overrides the GitHub hostname. Its default is `GH_HOST`, then
`github.com`. `--pretty` indents the same JSON receipt.

## Read the receipt

The command verifies the run ID, SHA, and attempt before retrieval and again
after collection. A `verified` receipt contains the requested identity, bounded
`logs`, JUnit `records`, and `gaps`. Each record identifies its artifact, XML
member, test name, classname, failure or error kind, message, type, and body.
Both failure and error records on one testcase remain separate.

An `unverified` receipt contains the requested identity and gaps. It contains no
logs or attributed records. An identity change or failed final metadata read
discards the collected evidence.

Artifacts from a stable first attempt have `verified-first-attempt` binding.
Later attempts retain evidence for the verified run and head with `run-only`
binding and an `attempt-unbound` gap. Their artifact metadata cannot prove which
rerun attempt produced them.

Missing, expired, inaccessible, malformed, unsafe, and over-limit data remain
explicit gaps. One unavailable artifact does not suppress safe records from
other artifacts. An unsafe or corrupt archive contributes no partial records.
Logs that end before an assertion can coexist with a recovered JUnit traceback.

Exit 0 means a verified receipt without gaps. Exit 2 means the receipt has gaps.
Exit 64 means invalid arguments. Recovered failure records describe failed
tests. A successful diagnostic query does not mean CI passed.

## Retrieval limits

The command reads at most two inventory pages of 50 artifacts. It downloads at
most eight artifact archives plus the requested attempt's log archive. Each
download is at most 8 MiB, and downloads share a 32 MiB budget.

Archives allow at most 128 entries, 1 MiB per expanded member, 8 MiB expanded
per archive, and 32 MiB expanded across collection. The maximum compression
ratio is 100. The reader validates the directory before allocating ZIP entries.
It rejects ZIP64, multidisk archives, unsafe paths, duplicate members, links,
special members, Unix executable permissions, encryption, unsupported compression, and corrupt
sizes or checksums. It never extracts or executes archive contents.

XML allows depth 64, 50,000 elements per document, and 16,384 combined attribute
name and value characters per element. DTD and entity declarations and external
resolution are forbidden, including declarations in UTF-16 input.
The isolated Python parser supports
Python 3.9.6 with Expat 2.2.8. Its parent enforces a three-second deadline.

Collection retains at most 32 JUnit records. Its 24,576-character JUnit evidence
budget counts JSON-serialized archive record data, including escaping, plus
artifact-name length before escaping.
Bodies retain at most 2,048 characters, and other record fields retain at most
256 characters. Logs retain the last four members with the final 8,192 characters each.
Field truncation and omitted records produce limit gaps. Final JSON is at most
64 KiB, including escaping and pretty formatting. It remains valid JSON when
evidence is omitted.

Each GitHub subprocess has a 15-second deadline. Collection has a 90-second
deadline. JSON replies are at most 1 MiB and subprocess stderr is at most
8 KiB. Missing Python and query failures become evidence gaps.

## Review-body findings

`watch-pr` and `merge-gate` apply these rules through `review-bodies.ts`.

- The watcher reads bold counted summaries from any bot, `<summary><strong>Name (N)</strong></summary>` or `<summary><strong>N name</strong></summary>`, with N above 0 and a name whose first word is not "resolved", in any case.
- It masks only code that GitHub's renderer must show as code: a fenced block whose fence starts its line, and a code span that closes on its own line. A line that starts with three backticks or tildes, after any indentation, list marker, or footnote label, ends all masking for the rest of the body unless it opens a masked fence. An HTML comment, `<pre>`, or similar HTML block that its first line leaves open does the same, except inside a blockquote, where it ends masking only until the next blank line.
- Any unescaped `<`, `](`, or `][` outside a masked code span, an unpaired backtick, a run of more than 80 backticks, or a code span written directly after a word with a colon or `www.` ends masking for the rest of that line and until the next blank line. It never masks a code span on a line that contains `|`. A code example can therefore still yield a finding. Masking is meant never to hide a counted summary that GitHub shows, and the oracle tests check that against cmark-gfm, the renderer GitHub uses.
- A section whose name's first word is "open", in any case, is an Open section, such as `Open (3)` or `3 open issues`. Its items that link a review thread with `#discussion_r<id>` belong to the thread gate. Treat a thread link inside a code span or inline HTML, or one after masking has ended for the rest of the body, as no thread link, so its item stays a body finding. Its other items and every item in other counted sections are body findings. Missing items produce "(unparsed)" findings, with count-based padding capped at 20. A review blocks only when these rules yield at least one body finding. A counted summary is not one: an `Open (1)` section whose only item links a thread yields none. Wording, headings, and markers outside these rules block nothing.
