### Perf issue

**You own the measurement story.** Tie every fix to a measurement, don't read source instead of measuring.

For sustained improvement against a metric rather than a one-off fix, use the Hillclimb playbook (`playbooks/hillclimb.md`).

1. **Baselined.** A trace from the matching surface records the slowness as a number you trust. Capture a baseline trace via the matching control skill. Call the Skill tool with `benchmark-checklist` to vet the baseline and each later number.
2. **Hypothesized.** Each candidate fix names the mantra it applies and the trace signal that supports it. Call the Skill tool with `how` to ground hypotheses. Don't claim a perf ceiling without running it first.
   Treat the mantras as hypothesis generators. Admit an attempt only when the trace shows its supporting signal.
   Try the performance mantras in order, cheapest first:
   1. Don't do it. Stop work whose result nothing uses rather than cheapening it. Call the Skill tool with `how` to prove the work is deletable. A trace shows cost, not whether the work is needed.
   2. Do it, but don't do it again. Cache only when the same computation or fetch repeats on identical inputs. Name what invalidates the result before claiming the win.
   3. Do it less.
   4. Do it later.
   5. Do it when they're not looking. When moving work away from the interactive moment, measure the interactive path, not total work done.
   6. Do it concurrently. Before duplicating work to take the fastest result, require a trace that shows the wait dominates and the system has headroom.
   7. Do it cheaper. Add an indirection hop only when it removes more from the critical path than it adds.

   When an earlier mantra meets the target, stop.
3. **Fixed without regression.** The fix is in, the tests that must keep passing still pass, and a post-fix trace exists. Plan the fix from the trace. Before the first change, record a green run of the tests that must keep passing. Rerun them after each fix, and revert a faster result that changes output. If the fix crosses a function boundary, call the Skill tool with `architect` first. Delegate implementation to a subagent on the `perf-issue` role. Call the Skill tool with `pstack-harness`, then follow its **Spawn a role** section to resolve the role. Review the diff. Capture a post-fix trace. Call the Skill tool with `principle-sequence-verifiable-units`. Verify each attempt before trying the next.
4. **Compared.** Baseline and post-fix artifacts have been parsed and diffed, and the delta is a number. Parse and compare the artifacts (JSON to sqlite, diff). "Inconclusive" or wrong-surface is not a pass. Flag it.
5. **Published.** The PR cites the measurement. Run **Opening a PR**.

**Reply:** baseline number, post-fix number, delta, artifact path.
