# Application cases

These three fresh application tasks cover unrelated data models. They use only Python's standard library and do not depend on infrastructure or external services. Parcel manifests group ordered items and later split them by capacity. Meter intervals calculate cumulative usage and later handle meter replacement. Retention schedules calculate calendar deadlines and later honor legal holds.

The case directories were authored for this comparison. The overlap review searched the tracked `canon`, `promises`, `harness-routing`, `runtime-probes`, `spec-probes`, `unslop`, and `verify-commands` corpora under `evals`. It inspected task metadata and prompts, then read the nearby application code for matching themes. This review found no prior scenario with these input contracts and maintenance changes. The conclusion concerns this repository, not external model training data.

Some domain vocabulary already occurs in the corpus. `canon/rules/two-hats/cases/free-shipping` changes a shipping-price threshold and checks commit sequencing. `canon/rules/domain-words/cases/shipment-tracking` adds an overdue-shipment flag using a glossary. `canon/rules/smells-table/cases/delivery-dates` preserves checkout and carrier date calculations during refactoring. These share delivery vocabulary with the new parcel case, but do not group parcel manifests or split ordered consignments by weight. `canon/rules/domain-test-names/cases/hold-expiry` concerns a box-office seat reservation that expires after 15 minutes. The new retention case instead calculates document deadlines and combines record-specific legal holds with release dates. The search found no cumulative utility-reading or meter-replacement scenario. The new tasks share general sorting, validation, and date arithmetic with other applications, so they are held out by scenario rather than by every underlying programming concept.

Each `case.json` names these paths relative to its directory:

- `project` is the starter application directory. Copy only its contents into the application's working directory.
- `initial_request` and `maintenance_request` are UTF-8 text files containing the two user requests.
- `oracle` is the acceptance command. It reads the adjacent private `checks.json` file.
- `controls.initial` and `controls.maintenance` are complete application directories that pass their corresponding stages.
- `controls.noop` is an application directory that fails both stages.
- `controls.targeted` is an application directory that passes initial behavior and fails a named maintenance check.
- `defects` lists an initial defect and a maintenance defect, with each directory, stage, and expected failure name.

The oracle and controls remain outside the copied application. Each oracle runs the application as a subprocess. Expected JSON results are literal values in `checks.json` and do not come from any control implementation. The maintenance stage runs the complete initial set again before its additional checks.

Run an oracle with `python3 oracle.py --project DIR --stage initial` or `--stage maintenance` from its case directory. It emits one JSON object with `passed`, `assertions`, and `failures`. A passing result exits zero. A behavior failure exits one and contains at least one named failure. The assertion count is 16 initial and 26 maintenance for parcels, 18 and 28 for meters, and 17 and 29 for retention. A protocol error, missing application, nonzero application exit, or application timeout is a failure. Each application call has a three-second timeout.

Run `python3 -m unittest discover -s evals/port-value -p test_cases.py -v` at the repository root to exercise all controls through the public subprocess interface. A nonzero exit, a failure summary, or a zero-test summary means verification did not succeed. The suite also copies each case to a new temporary location and verifies that its oracle still works there. Initial controls must fail the new maintenance behavior. Targeted maintenance defects must preserve initial behavior and fail their named maintenance checks.

The cases cover small batch commands, not persistence, concurrent access, network errors, packaging, or large-scale performance. They measure completed application behavior for these requests. They do not establish that one development method is better for every application.
