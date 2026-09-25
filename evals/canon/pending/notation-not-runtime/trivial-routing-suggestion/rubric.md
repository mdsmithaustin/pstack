# Rubric: trivial-routing-suggestion (near-miss)

Rule: `notation-not-runtime` (principle-test-behavior-not-implementation, "Notation, not a runtime").

## Look-alike

Location: `tests/policies/builtins/features/trivial_routing.feature` (four new scenarios) and
`tests/policies/builtins/test_trivial_routing_scenarios.py` (new steps `suggestion`,
`configure_gated_suggestion`, `reason_names_model`, `reason_is_generic`, `configuration_fails`).

The PR tests its feature with Gherkin scenarios and pytest-bdd step definitions, which looks like the
"added a Gherkin runner" pattern. It is not: the base commit on main (`base.patch`, "test(policies):
describe built-in routing verdicts as pytest-bdd scenarios (#8061)") already adopted pytest-bdd for
built-in policy verdicts. It added `pytest-bdd` to the test group and `uv.lock`, the
`trivial_routing.feature` file with five scenarios for this same factory, and the step module. It
also documented in CONTRIBUTING.md that verdict changes to a built-in policy get a scenario there.
The PR adds no dependency, no new runner, and no new feature file; it extends the existing feature
and step module the way the convention asks. The rule allows `.feature` files when the project
already runs a Gherkin runner, so the tests are correct as written.

## Grades

- CLEAN (review-found): recognizes that the scenarios follow main's pytest-bdd convention for policy
  verdicts, or engages with the scenarios on their merits, and leaves the choice alone.
- PARTIAL: raises the Gherkin/pytest-bdd choice as an open question (for example, whether the
  convention should stay limited to policy verdicts) without asking this PR to change it.
- CLEAN (review-missed): never engages the design point and raises no alarm.
- FALSE_ALARM: asks to drop pytest-bdd, to delete the `.feature` scenarios or step definitions, or
  to rewrite the new scenarios as plain pytest tests (for example in `test_routing.py`), or objects
  that the PR should not add Gherkin/`.feature` tests.

## Not counted either way

- Asking for an e2e test (CONTRIBUTING asks for one on user-facing features) or an example YAML.
- Validating `suggested_model` as a non-empty string, or checking that it is a known model.
- Step wording or reuse inside the step module (for example, splitting the suggestion scenarios into
  their own feature file, or sharing the reason assertion), as long as the review keeps pytest-bdd.
- The quoting of the model in the reason string; `_trivial_reason` placement or naming.
- Noting that `pytest_bdd` is not importable in the reviewer's environment (the sandbox venv comes
  from the pinned lock, offline, so the scenario module fails to import on main and on the branch
  alike), as long as the review does not ask to rewrite the tests because of it.
