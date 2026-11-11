---
name: spec-probes
description: "Apply when writing or reviewing a spec, requirements, acceptance criteria, user stories, or tickets before any code exists, and when deriving acceptance tests from a spec you cannot change (fixed-spec mode). Two passes: an edge probe over a closed taxonomy of data-shape boundaries, and a prohibition probe for what the feature must never silently become. Every raised item is resolved, dismissed with a reason, or carried as an explicit gap."
---

# Spec probes

A verifier only checks assertions that exist, and it is confidently wrong about edges the spec never stated. Run these two passes over each requirement before code, in this order.

## Pass 1: edge probe

Classify each requirement's data shape: `numeric-range`, `collection`, `text`, `stateful`, `io`. The shape also includes `example` when the spec gives the requirement a worked example, and `variants` when the requirement names several variants, such as formats, languages, or strategies. It includes `look-alike` when the requirement defines a term that looks like another term in the spec. Then raise only the categories whose shapes intersect it.

| Category | Shapes | Ask |
|---|---|---|
| Unit / cardinality | collection, stateful | What counts as one item where the spec counts, numbers, groups, or joins? Take the unit the spec's noun names. Test an input where the plausible units differ: two outer items of two parts each, a header line present, two occurrences in one window. |
| Boundary values | numeric-range | What happens exactly at each min, max, or threshold, and one step either side? |
| Adjacency | collection | When two things are exactly equal or just touch, do they merge, collide, or stay separate? |
| Empty / degenerate | collection, text | What is the result for empty, single-element, or null input? |
| Encoding | text | Whose definition of length and equality applies: bytes, code points, grapheme clusters, normalized form? |
| Ordering / stability | collection | When elements compare equal, is output order specified and stable? |
| Precision / overflow | numeric-range | Where can rounding, tie-breaking, precision loss, or overflow occur, and what is the exact contract: half-up or half-even, floor or truncate? |
| Idempotency | stateful | What happens if this runs twice on the same input? |
| Concurrency / effect order | stateful, io | If interrupted or run in parallel, what is guaranteed? |
| Example values | example | An example's output is exact: expect it character for character, never through a parser or normalizer, in the format the examples show where prose allows several. Its input values, and whatever else holds in it that no rule states, such as the order its operations finish, restrict nothing. Add one test where such a property does not hold when a requirement or today's behavior gives its result. Otherwise carry the edge as `unresolved`. |
| Variant coverage | variants | Does each raised edge behave the same in every named variant? Probe it in each variant, or record why checking one variant covers the others. |
| Look-alike terms | look-alike | Where the spec defines two similar terms differently, which input gets different results from them? Expect both results, so a test fails whichever term is implemented like the other. |

A requirement with prose but no matching shape gets one soft "unclassified, review by hand" item, not silence.

The defects this catches: "one reminder per overdue loan", tested with a member who has one loan of one book, passes whether reminders go out per member, per loan, or per book. "Merge overlapping intervals" says nothing about `[1,2]` and `[2,3]`, which only touch. For a handler that accepts a JSON or form-encoded body, checking the empty-field edge only in JSON misses that a form field has no null.

## Pass 2: prohibition probe

Edge shapes cannot surface "the reminder must not shame the user". For each requirement ask: **what could this feature silently become that the author would not want, but the spec does not forbid?** Cast wide first; ten raw candidates per requirement is expected.

Then one precision pass:

- **Drop** routine engineering: must not mutate its input, must not throw on empty, must not leak a handle. Those belong to pass 1 or to code review.
- **Keep** values, fairness, privacy, transparency, and safety items: must not use shaming framing, must not proxy on protected attributes, must not store raw PII in plaintext.
- **Refer, do not mint,** anything a dedicated tool already owns (injection, path traversal, data-retention law, generic bias canon): one breadcrumb to the security or compliance step, then stop.

Two or three bespoke items per feature is the normal yield. A pure utility yields zero, and that is the right answer, so a non-empty list always carries signal.

## Resolve every raised item

Each item ends in exactly one state:

- **resolved**: the spec states the answer (`explicit`, checked by an ordinary test); or a held-out or property-based test will stand in for an edge you know but cannot fully write down (`backstop`); or, for a prohibition that needs human judgment rather than a test, `judgment`.
- **dismissed**, with a reason. "N/A, input is a bounded enum, no boundary exists" is valid; silence is not. The reason is the audit trail.
- **unresolved**: carried forward as an explicit gap the plan must surface, never dropped silently.

**A new rejection needs a requirement that states the restriction.** A rejection is an expected result that rejects, errors on, or reinterprets an input. Expect one only where a requirement states the restriction, and name that requirement in the criterion. A stated type, range, or format is such a requirement, so expect an input that breaks it to be rejected. The rule holds on a new field and on input the program accepts today, even when a worked example shows only one form of the value or a sibling field has the rejection. Without such a requirement, expect the result the spec text gives the input, or the result the program gives it today. Pair each rejection you test with the nearest valid input its definition allows, such as a leading zero or a single column, and expect it accepted. A validator that fails the pair is wider than its definition.

**In fixed-spec mode, only what the spec states gets a test.** You are in it whenever you derive tests or criteria from a spec you cannot change. `explicit` then needs a spec sentence or example you quote, or current behavior you name, and each criterion cites it. Text you add to the spec during the task is not a source. An answer you supply yourself, to an edge or a pass 2 prohibition, is an `assumption`: write no criterion or test for it, keep the item `unresolved`, and have the code take the most permissive behavior.

Write the `backstop` and `judgment` tags into the spec itself. A reviewer later abstains on those instead of passing them by inspection; without the tag it cannot see its own blind spot.

**Reply:** per requirement, the items raised and their states; then each `assumption`; then the coverage count: applicable, resolved, unresolved, and how many are `backstop` or `judgment`.
