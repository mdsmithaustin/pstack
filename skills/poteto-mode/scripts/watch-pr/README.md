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
