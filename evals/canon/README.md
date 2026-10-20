# Application execution and outcome controls

This directory maintains the native application execution owner and two
outcome-grader banks. The historical instruction screens, placement and stub
comparisons, process census, and 68 configurations are preserved through the
[archive index](../archive/README.md). Their old results do not certify the
current skills or runtime.

`application.py` captures and replays native attempts. The public contract is in
[`APPLICATION.md`](APPLICATION.md). `evals/port-value/study.py` uses it; the module
does not grade task quality. Its source remains available for supported callers
and replay. Continued runtime maintenance needs a caller or explicit decision,
not merely the existence of its own tests.

`oracles/check.py` grades retained cases in `rules/steering-review-asks` and
`rules/value-type`. These cover real maintainer-request outcomes and a small
marketplace control. Reference samples, plausible wrong answers, skipped tests,
and tampering controls test the evaluator. A stand-in or reference sample is
not a model observation. Project tests require their declared image and mirror;
an unavailable prerequisite remains untested coverage.

Each case's `case.json` owns its repository and commit pins. The
[`workspace.py` module documentation](workspace.py) describes fetching that
commit into the local mirror; [`images/build.py`](images/build.py) documents
dependency-image preparation and the image registry. Detailed historical setup
instructions remain in the pinned README, available through
[archive recovery](../archive/README.md#recover-the-original-source).

The [known-issues case contract](rules/steering-review-asks/cases/hermes-known-issues/case.json)
owns the installation-safety requirements and the independent visibility and
result-contract checks.
Original maintainer-preference constraints and grades remain at the archive pin.
Other retained historical cases are development and regression material, not
unseen confirmation cases for amendments derived from them.

## Local checks without a Docker change

Run the application-owner tests, workspace regressions, and archive recovery
check from the repository root. The application tests replace the external
sandbox transport and perform real local capture and replay. They do not run
a model or establish native sandbox delivery.

The workspace regressions use disposable local Git repositories to check diff
application, checkout materialization, overlays, history, and spec validation.
They need Git on `PATH`, without an upstream mirror or project image.

```sh
python3 -m unittest discover -s evals/canon -p test_application.py -v
python3 -m unittest discover -s evals/canon -p test_workspace_core.py -v
python3 -m unittest discover -s evals/canon -p test_archive.py -v
```

For each command, a nonzero exit, a failed test, or a zero-test summary is a
failure. Native delivery and project-image checks are separate prerequisites,
documented in the application contract and the prerequisite references above.

CI retains its existing `python3 -m unittest -v` invocation in this directory.
It discovers the maintained application, workspace, archive, and oracle
contracts. Its existing Docker setup can exercise supported container controls; image-specific
and native tests still report their own unavailable prerequisites. No new paid
regression cadence or model-quality release gate is introduced here.
