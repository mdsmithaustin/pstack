---
name: runtime-probes
description: "Apply when asked to probe, stress, fuzz, or chaos-test a running product, feature, or PR for defects nobody has reported, or to go hunting for bugs against a live surface. Two passes: a probe pass over a closed taxonomy of entry-point shapes, and a promotion gate that keeps only findings a real caller can reach. Promoted findings leave a committed regression test behind; the rest are dismissed with a reason or carried as an explicit gap."
---

# Runtime probes

The twin of the **spec-probes** skill on the other side of the code. That one probes a requirement before anything runs. This one probes the running system after. Reach for it when nothing has been reported and the job is to find out what is wrong.

Two failure modes shape the design. An unbounded probe run burns budget and returns noise. A promoted finding no caller can reach wastes a maintainer's day. Pass 1 bounds the search. Pass 2 bounds what escapes it.

## Before either pass

Name the scope, the surface, and the stop predicate, in that order.

**Scope.** A PR diff, one feature, or a whole product. For a diff, take the change map from the **blast-radius** skill and probe what it names rather than re-deriving it.

**Surface.** Probes run against the real thing through the project's `verify-<app>` driver, which the **create-verification-skill** skill builds when the project has none. A probe that never reached the running surface is `not run`, never a pass.

**Stop predicate.** A budget and a floor, both written down before the first probe. "Twenty probes per entry point, or two hours, whichever comes first" is the shape. When a loop-governance suite is installed, hand it the outer loop and keep this skill as the method that loop runs; otherwise this predicate bounds the run.

Open a `findings.tsv` through the **show-me-your-work** skill, one row per probe: id, entry point, category, probe, observed, reproduces, verdict, reason. Keep it out of the tree so it survives reverts.

## Pass 1: probe

Inventory the entry points, classify each by shape, then raise only the categories whose shapes intersect it. A read-only query is never asked about interrupted sequences. The taxonomy is closed on purpose. Eight categories cleared beat forty nobody finishes.

| Category | Shapes | Probe |
|---|---|---|
| Malformed input | `input` | What happens on the wrong type, the wrong encoding, or a field the caller was never meant to send? |
| Extreme size | `input`, `resource` | What happens at zero, at one, and far past the largest realistic value? |
| Interrupted sequence | `sequence`, `state` | What survives when the operation is abandoned halfway by a closed tab, a killed process, or a dropped connection? |
| Repeat and replay | `sequence`, `state` | What happens on the double submit, the back button, the retried request? |
| Stale state | `state` | What happens when the client acts on state the server has since changed? |
| Dependency failure | `boundary` | What does the user see when the thing it calls errors, returns nothing, or is gone? |
| Dependency slowness | `boundary`, `resource` | What happens when the call takes ten seconds instead of ten milliseconds? |
| Concurrent actors | `concurrency`, `state` | What happens when two actors touch the same record, file, or key at once? |

Fan the probes out with the **swarm** skill, partitioned by entry point. That skill resolves its own worker model and effort, so do not restate the choice here. Workers report `PASS`, `ISSUES`, or `BLOCKED` with evidence, which is swarm's own contract. Do not mint a second one.

An entry point with no matching shape gets one soft "unclassified, probe by hand" row, not silence.

## Pass 2: promote

Every worker finding is a hypothesis. Judge each on your configured `judgment and prose` model, with its configured effort per the **pstack-harness** skill. A finding promotes only when all three hold.

1. **It reproduces.** The harness replays it from a clean start and it fails again. A finding the harness cannot replay on demand does not promote, whatever the transcript showed.
2. **A real caller can reach it.** Name the caller and the path from a real entry point to the failure. Strict reachability means a defect behind a guard no caller gets past does not promote.
3. **A maintainer would take the fix.** The consequence is user-visible, data-affecting, or crosses a security or privacy boundary. Internal untidiness is not a defect.

Triage the rest against the `fix` / `dismiss` / `ask` rubric in `../poteto-mode/references/bugbot-triage.md`, and record a learned dismissal pattern there in its own format instead of re-deriving it next run.

Each finding ends in exactly one state.

- **promoted**: it clears all three. It earns a regression test and a row in the issue list.
- **dismissed**, with a reason. "Unreachable, the one caller validates this field against a bounded enum" is valid. Silence is not.
- **gap**: it reproduces but fails condition 2, and the row names the guard that makes it unreachable. Strict reachability buys a finding list nobody has to re-litigate. It costs you this row. Delete that guard later and the gap goes live, so the guard's name is the whole value of keeping the row.

## Residue

The probe harness is the artifact, so commit it. A reviewer reruns it.

Each promoted finding becomes one failing test staged before its fix per the **poteto-tdd** skill, and the fix itself runs the Bug fix playbook (`../poteto-mode/playbooks/bug-fix.md`), one finding at a time. Do not batch fixes into one commit.

A promoted test asserts an invariant, not a transcript. "Rejects a quantity below zero" survives a refactor. "Returns this exact error string for this exact byte sequence" does not. Put every promoted test through the **verify-commands** skill before it lands, because a generated test that passes green while measuring nothing is worse than no test at all.

**Reply:** scope and surface, the stop predicate and whether it was met, probes run per entry point, each promoted finding on one line with its test, the dismissed count, every gap with its named guard, and the `findings.tsv` path.
