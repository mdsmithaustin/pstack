---
name: spec-probes
description: "Apply when writing or reviewing a spec, requirements, acceptance criteria, user stories, or tickets before any code exists, when deriving acceptance tests from a spec you cannot change (fixed-spec mode), when a spec changes mid-task, and before each commit of code built from a spec. Probes data-shape edges and what the feature must never silently become, and checks the diff's outputs and rejections against the spec. Every raised item is resolved, dismissed with a reason, or carried as an explicit gap."
---

# Spec probes

A checker grades the spec's examples and stated restrictions, not your reading of them. Two rules prevent most misses, on every requirement:

- **Examples fix how each value is written.** Where a worked example shows an output value, write it in that form character for character, even where the prose allows others. An example that prints `"total": 1.50` means `1.50`, not `1.5`, though the prose says only "a decimal". Compare as text, never through a parser or normalizer. An example does not fix order, counts, or behavior that the prose defines. Where an example and the prose disagree, follow the prose and report the conflict with both sentences.
- **Accept what no requirement forbids.** Reject, error on, or reinterpret an input only when a requirement states the restriction. Examples that all show `https://` URLs do not make an `ftp://` URL an error. A stated type, range, or format is such a requirement.

## Before code

**1. Edge probe.** Classify each requirement's data shape: `numeric-range`, `collection`, `text`, `stateful`, `io`, plus `example` when it has a worked example, `variants` when it names several formats or strategies, and `look-alike` when it defines a term that resembles another. Raise only the categories whose shapes match.

| Category | Shapes | Ask |
|---|---|---|
| Unit / cardinality | collection, stateful | What counts as one item where the spec counts, groups, or joins? Take the unit the spec's noun names, and test an input where plausible units differ, such as two outer items of two parts each. |
| Boundary values | numeric-range | What happens at each min, max, or threshold, and one step either side? |
| Adjacency | collection | When two things are equal or just touch, do they merge, collide, or stay separate? |
| Empty / degenerate | collection, text | What is the result for empty, single-element, or null input? |
| Encoding | text | Whose length and equality apply: bytes, code points, graphemes, normalized form? |
| Ordering / stability | collection | When elements compare equal, is output order specified and stable? |
| Precision / overflow | numeric-range | Where can rounding, ties, or overflow occur, and what is the exact contract? |
| Idempotency | stateful | What happens if this runs twice on the same input? |
| Concurrency / effect order | stateful, io | If interrupted or run in parallel, what is guaranteed? |
| Example values | example | The first rule above fixes how values are written. Its input values, and what holds in it that no rule states, such as the order operations finish, restrict nothing. Test one input where such a property differs only when a requirement or today's behavior gives its result. |
| Variant coverage | variants | Does each raised edge behave the same in every variant? Probe each, or record why one covers the rest. |
| Look-alike terms | look-alike | Which input gets different results from the two terms? Expect both, so a test fails whichever is implemented like the other. |

A requirement with prose but no matching shape gets one "unclassified, review by hand" item, not silence.

**2. Prohibition probe.** Ask what the feature could silently become that the author would not want and the spec does not forbid. Cast wide, then keep only values, fairness, privacy, transparency, and safety items, such as "must not use shaming framing". Drop routine engineering, which belongs to the edge probe or review. Point anything a security or compliance tool owns to that step. Two or three items per feature is normal, and a pure utility yields zero.

## When the spec changes

When a new checkpoint, revision, or ticket adds or changes requirements, run Before code on those requirements only. Add their examples to the fixtures and keep every earlier fixture. Record the probed requirements and each item's state in the worklist item. If the change contradicts an earlier fixture, report both spec sentences and leave the fixture alone.

## Before each commit

Check the diff against the spec. List every rejection, error, or reinterpretation of input that the diff adds or changes, and every output it formats.

- Quote the requirement that states each rejection. Remove a rejection with no such requirement, so the input takes the permissive path.
- Compare how each formatted value is written with the example of that value, as text, and fix a mismatch.

Report the list in the reply, one line per path.

## Resolve every raised item

Each item ends in exactly one state:

- **resolved**: the spec or today's behavior states the answer (`explicit`, checked by an ordinary test), a held-out or property-based test stands in for an edge you cannot fully write down (`backstop`), or a prohibition needs human judgment (`judgment`).
- **dismissed**, with a reason, such as "N/A, input is a bounded enum". Silence is not a reason.
- **unresolved**: carried forward as an explicit gap the plan surfaces.

**A rejection needs a requirement.** A rejection is an expected result that rejects, errors on, or reinterprets an input. Expect one only where a requirement states the restriction, and name it in the criterion. This holds on a new field and on input the program accepts today, even when an example shows only one form of the value or a sibling field rejects it.
- Without such a requirement, expect the result the spec text gives the input, or today's result. A new field with no stated result gets no criterion, and the edge stays `unresolved`.
- Pair each rejection you test with the nearest valid input its definition allows, such as a leading zero, and expect it accepted.

Name the source of each criterion: a requirement, a quoted spec sentence, or the current behavior it keeps. An edge with no source stays `unresolved` with no criterion. Text you add to the spec during the task is not a source. A criterion that answers a prohibition with no source is tagged `assumption`.

**In fixed-spec mode, only what the spec states gets a test.** You are in it whenever you derive tests from a spec you cannot change. `explicit` then needs a quoted spec sentence or example, or named current behavior. An answer you supply yourself is an `assumption`: write no test for it, keep it `unresolved`, and have the code take the most permissive behavior.

Write the `backstop` and `judgment` tags into the spec, or into the reply in fixed-spec mode, so a later reviewer can see what it cannot check.

**Reply:** per requirement, the items raised and their states, then each `assumption`, then the counts: applicable, resolved, unresolved, and how many are `backstop` or `judgment`.
