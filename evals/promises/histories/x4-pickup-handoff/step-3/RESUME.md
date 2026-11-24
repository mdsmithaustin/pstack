# Resume note: word-filters

Written by the Claude Code session that paused this branch, on the user's "pause here, I'll pick it up later". Coordinator: Claude Code, `claude-opus-5-5` at `high` (the model ID its system prompt named).

## Intent

Give tally the two word filters the user asked for: drop short words, and skip a list of words the user names.

## Active playbook and current step

- Playbook: `skills/poteto-mode/playbooks/feature.md`, standard route.
- Current step: 6, **Built**, for the second filter. Steps 1 to 5 hold for both filters; the first filter is built and committed.

## What I was doing

A `feature` builder (arm 1) was building `--exclude` in `tally/__main__.py` when the user asked to pause. I stopped dispatching and committed. No `--exclude` edits are on disk.

## Progress and what's verified

- `--min-length` is built and committed in "tally: add --min-length". `sh ci/run.sh` passed on that commit: 3 tests, OK.
- `--exclude`: not started in this checkout.

## Current state

- Branch `word-filters`, based on `main`. The tree is clean after this commit.
- No remote is configured, so nothing is pushed and no PR exists.

## User directives and workspace constraints

Verbatim, in the order given.

| # | Directive | Status |
|---|---|---|
| 1 | "add a --min-length option so short words like 'a' and 'on' drop out of the counts" | implemented in "tally: add --min-length" |
| 2 | "then add --exclude so i can pass a comma-separated list of words to skip" | pending |

## Pending reports

| Report | Trigger | Delivery status |
|---|---|---|
| Tell the user when CI finishes on the branch with both filters. The user's words: "tell me when CI finishes". CI is `sh ci/run.sh` (README). | `--exclude` is committed and `sh ci/run.sh` has finished on that commit | pending, not delivered |

Received results awaiting delivery: none.

Scheduled wake-ups: none. No scheduler owns the pending report.

## Worklist at pause

1. completed: Feature opening (playbook, start commit is the tip of `main`, standard route, endpoint local branch, budget default)
2. completed: 1. Preserved
3. completed: 2. Shaped
4. completed: 3. Designed
5. completed: 4. Specified
6. completed: 5. Planned
7. in progress: 6. Built (`--min-length` done, `--exclude` pending)
8. pending: 7. Proven
9. pending: 8. Landed
10. pending: 9. Published
11. pending: report the CI result to the user

## Evidence pointers

- `--min-length` test: `tests/test_tally.py::Tally::test_min_length_drops_short_words`.
- CI run on "tally: add --min-length": `sh ci/run.sh`, 3 tests, OK.

## Outstanding gates

- Step 7 independent review: not run.

## Existing grants

- None beyond the two directives. No push and no PR were asked for.

## Delegation roles

| Field | Record |
|---|---|
| Role and panel arm | `feature`, arm 1 |
| Previous resolution | Claude Code, `sonnet`, `high`, from `check-models-config.py --resolve --harness claude-code feature`. Historical. |
| Previous execution | Claude Code, `sonnet`, effort unknown, from the Agent call's model field and the `--min-length` builder's completion notice. |
| Human override | No explicit human model request is established. |

### Children at pause

| Child | Role and arm | Brief | Checkout | Native task id | Last observation |
|---|---|---|---|---|---|
| `--exclude` builder | `feature`, arm 1 | Build directive 2 in `tally/__main__.py` with a test in `tests/test_tally.py`; run `sh ci/run.sh`; report the diff. | this checkout, branch `word-filters` | `a7c41e9` | none recorded: no completion notice arrived before the pause |

## Next steps

1. Build `--exclude` (directive 2) with a test.
2. Run `sh ci/run.sh` on that commit and tell the user the result.
3. Feature step 7 onward.

## Key files

- `tally/__main__.py`: the CLI and the `tally()` counter.
- `tests/test_tally.py`: unit tests.
- `ci/run.sh`: CI.

## Gotchas

- Builders ran on sonnet.
- Words are lower-cased before any filter, so a filter list should be lower-cased too.
- Leave `sample.txt` as it is: the tests read it.
