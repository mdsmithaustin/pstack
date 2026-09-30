I treated this the way I would any workflow change and worked back from the failure. The document is below.

<file path="ops/premortem.md">
# Premortem: changelog gate

## Failure headline

By mid October the `changelog` job has failed 30 pull requests, 22 of them wrongly, `no-changelog` is on half of all open PRs, and two maintainers have asked for the job to be deleted. The release cutter is back to writing the changelog from `git log`, now with the added step of removing filler lines.

## Shared cause

Every failure above comes from one input: the script's reading of the diff. It anchors on `+## Unreleased`, counts `+- ` lines, and falls back to counting any added `- ` line anywhere in the file. That fallback masks the primary check, and the primary check is sensitive to heading spelling, section order, and whether the base ref is current. Before we rate anything else we should establish how often the script is wrong on our real history.

## The critical assumption and its check

Assumption: the script agrees with a human on whether a PR needed a changelog line, on at least 95% of PRs.

Check, on a copy only:

1. Fork `ledgerd` to a scratch repository under the platform org, `ledgerd-gate-trial`. No branch protection, nobody works in it.
2. Add the `changelog` job there. Replay the last 60 merged PRs as branches against the fork's main and run the job on each.
3. Stop rule, fixed now: if more than 3 of the 60 verdicts disagree with the label a maintainer gives them by hand, we do not merge on Tuesday. We fix the script and rerun the 60. Merge only when the disagreement is 3 or fewer.
4. After merging, run the job in report-only mode for two weeks: it posts its verdict as a comment but never fails. Keep a tally in a sheet: PRs seen, failures, false failures, labels applied. Review the tally at the end of the two weeks before making the check required. If false failures exceed one in ten, revert.

## Rollbacks

- Trigger: delete the job. One commit.
- Damage: PRs that were wrongly failed need their authors told the check was wrong, and any filler changelog lines added to appease it should be removed before the next release. Grep `CHANGELOG.md` for lines added in the trial period and review each.

## Cleared

- Dependabot: touches only `go.mod` and `go.sum`, so passes. Fine.
- Branch protection unchanged. Fine.

## Change before adoption

1. Run the 60 PR replay on the fork before Tuesday.
2. Add the report-only mode and the two week tally.
3. Print the Unreleased section the script saw when it fails.
4. Name an owner for the tally review.
</file>

The fork and the replay are the part I would do first. Without them we are guessing at the false-failure rate.
