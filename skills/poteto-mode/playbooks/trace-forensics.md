### Trace forensics

**You own the diagnosis from the artifact.**

Distinct from **Runtime forensics**, which instruments the live process. Here the capture already exists. The artifact is a fixed dataset, read it, don't re-run it. Keep tooling generic: a DevTools or trace parser for cpuprofile and `.json.gz`, a text editor for a spindump, your heap tooling for a heapsnapshot.

1. **Loaded.** The artifact's format is known and the right tool has it open, with only the reduced finding in the main thread. Parse large artifacts in a subagent on the `routine` role. Call the Skill tool with `principle-guard-the-context-window`. Call the Skill tool with `pstack-harness`, then follow its **Spawn a role** section to resolve the role.
2. **Queryable.** The raw artifact is in a form you can query, one row per sample, frame, or node. Dump the trace or heap snapshot into sqlite. Reach the queryable shape before you read.
3. **Narrowed.** The hot path, the retainer chain, or the stuck thread and its wait reason is identified. Query for the frames that hold the most time and walk the call tree. For a leak, follow the retainer chain from the leaked object to a GC root. For a spindump, find the thread stuck on-CPU or blocked and its wait reason.
4. **Attributed.** The hot frame points at a file, a symbol, and a line, or the reply says plainly that the artifact carries no symbols. Map the hot frame to file, symbol, and line via the artifact's own symbols. A frame with no source mapping is not yet a diagnosis.
5. **Confirmed or labeled.** A paired capture confirms the finding, or the finding is marked as the strongest hypothesis the artifact supports. If you have a paired capture, diff the before and after artifacts. Otherwise say so.
6. **Handed back.** The diagnosis is cited and routed. Hand back a cited diagnosis, no fix unless asked. Route to Bug fix or Perf issue once the cause is known. Throughput checkpoint stays one line: `throughput checkpoint: n/a, read-only forensics`.

**Reply:** the artifact and format, the reduced finding, the source location, the artifact paths, and whether a paired capture confirmed it.
