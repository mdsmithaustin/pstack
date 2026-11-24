# Lane 3: regression against trunk (round 1, PR 12)

Head: the code-ready head owner-12 reported (branch tip of `pr-12-min-length`). Trunk: `main`.

## Gates

`sh ci/run.sh` at the head: 3 tests, OK.

## Regression lane

Trunk has no `--min-length`, so the issue's command cannot run there. Recorded that fact.

## Findings

### trunk-1: the CRM export from issue 9 crashes

`python3 -m tally .autopilot/issues/9-crm-export.txt` raises `UnicodeDecodeError` at the head and on `main` alike. Saved run: `lanes/saved/trunk-1.txt`. The PR does not touch how the file is opened.
