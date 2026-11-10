### Runtime forensics

**You own the diagnosis.** Instrument the live process, don't theorize from source. The deliverable is a cited diagnosis, not a fix.

1. **Captured.** A real artifact from the matching surface holds the signal. Capture it via the control skill: a CPU profile for a spinning process, a heap snapshot for a leak, a CDP trace for a visual glitch. A real artifact, not a guess.
2. **Reduced.** The artifact is down to the smoking gun, and only the reduced finding is in the main thread. Reduce to the function on the hot path, the retainer chain from the leaked object to a GC root, the loop firing without input. Parse large artifacts in a subagent on the `routine` role. Call the Skill tool with `principle-guard-the-context-window`. Call the Skill tool with `pstack-harness`, then follow its **Spawn a role** section to resolve the role.
3. **Confirmed.** The mechanism has been shown on the running process, not inferred. Inject instrumentation via CDP eval on the running process, or hotfix the live code without reloading, to confirm the hypothesis cheaply.
4. **Attributed.** The finding points at a file, a symbol, and the line that allocates or schedules.
5. **Planned.** The worklist holds one line, `throughput checkpoint: n/a, read-only forensics`.

**Reply:** the signal captured, the reduced finding, how you proved the mechanism, the source location, artifact paths. No fix unless asked. Hand back to Bug fix or Perf once the cause is known.
