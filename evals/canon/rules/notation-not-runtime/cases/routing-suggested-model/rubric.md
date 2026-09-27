# Rubric: routing-suggested-model (positive)

## Flaw

Location: `tests/policies/builtins/test_suggested_model_scenarios.py` (the step-definition module) with
`tests/policies/builtins/features/suggested_model.feature` and the new `pytest-bdd` entry in
`pyproject.toml` `[dependency-groups].test` (plus `uv.lock`).

omnigent runs plain pytest everywhere; nothing in the repo uses pytest-bdd, behave, or `.feature`
files. The PR's feature code (`suggested_model` in `omnigent/policies/builtins/routing.py`) is
fine, and the Gherkin is well written, but to test five scenarios it adds a Gherkin runtime: a new
test dependency (with `gherkin-official`, `parse`, `parse-type`, `mako` pulled into the lock), a
`.feature` file, and a module of regex-bound step functions sharing a mutable dict fixture. The
plain-pytest tests for the same factory already live in `tests/policies/builtins/test_routing.py`.
The principle: write Given/When/Then as notation in the project's existing framework and not to
add a Gherkin runner or `.feature` files unless the project already runs one.

Correct fix direction: keep the five scenarios, but write them as plain pytest tests (in
`test_routing.py` or a sibling module) named for the behaviour, with Given/When/Then as test names,
docstrings, comments, or arrange-act-assert; drop `pytest-bdd` from the test group and `uv.lock`,
the `.feature` file, and the step module.

## Grades

- FOUND: names the pytest-bdd/Gherkin addition (dependency, `.feature` file, or step module), says
  the problem (a new Gherkin runner / test framework in a suite that is plain pytest everywhere,
  step-glue indirection for five scenarios), and gives the fix direction (plain pytest tests for
  the same scenarios, drop the dependency and step glue).
- PARTIAL: names the location and the problem but gives no fix, or a wrong fix (for example,
  "document pytest-bdd in CONTRIBUTING", "convert the rest of test_routing.py to Gherkin", or
  "pin pytest-bdd tighter").
- MISSED: does not object to adding pytest-bdd, or mentions it only approvingly or neutrally.

## Not counted either way

- Asking for an e2e test (CONTRIBUTING asks for one on user-facing features) or an example YAML.
- Validating `suggested_model` as a non-empty string, or checking that it is a known model.
- The quoting style of the model in the reason string, or wanting the reason to stay machine-readable.
- `_trivial_reason` placement or naming; registry schema wording.
- Noting that `pytest_bdd` is not importable in the reviewer's environment (the sandbox venv comes
  from the pinned lock, offline) without drawing the design conclusion.
- The `asyncio.run` inside a sync step versus the repo's `pytest.mark.asyncio` tests, unless tied to
  the runner point above.
