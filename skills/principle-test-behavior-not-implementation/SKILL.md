---
name: principle-test-behavior-not-implementation
description: "Apply when you write, change, or keep a test. Assert what the code's users can observe, so that the test fails when that behavior breaks and keeps passing when only the internals change."
---

# Test Behavior, Not Implementation

A test is a claim about what users of the code can observe through its interface: return values, errors, state they can read back, and effects on outside systems. Private helpers, internal call order, and intermediate data are implementation.

Judge each test against two imagined edits:

- **Break the behavior** (a wrong value, a skipped or doubled effect). If the test still passes, it proves nothing. The usual causes are a loose assertion, an expected value computed by the code under test, and an assertion on data the test built itself.
- **Change the internals** and keep every observable result. If the test fails, it is pinned to the implementation.

Keep a test that catches the first edit and survives the second. Rewrite or delete the rest. Drive the code through its public interface with a concrete input, and derive the expected value from the requirement. What an external service receives is behavior. A call to an internal helper is not. Pair "this never happens" with a case where it does happen. Assert the error type that callers branch on, not the message.

**Production prerequisites.** An acceptance test must not pass because its setup establishes state or ordering that production never establishes. Exercise the real initialization path or prove the caller supplies the prerequisite. Fixture inputs real callers can supply are valid.

**Notation, not a runtime.** Write Given, When, Then or Gherkin-style tests in the project's existing framework. Do not add Cucumber, a Gherkin runner, or `.feature` files unless the project already runs one or the user explicitly asks for one of them. A request for Gherkin-style tests is not such a request.
