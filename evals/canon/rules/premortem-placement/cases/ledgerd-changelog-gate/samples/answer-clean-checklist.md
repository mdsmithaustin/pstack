Here it is. I kept it to what is likely in the first few weeks and what the fix is in each case.

<file path="ops/premortem.md">
# Changelog gate, first weeks

Merging this can cost us at most a red check on a PR that nobody is required to respect for two weeks. Everything below is in that frame.

## Likely misfires

- **Docs PR that brushes `cmd/`.** Someone fixes a typo in a `cmd/` help string. Code changed, no changelog line, red check. Correct behaviour strictly, irritating in practice. Answer: `no-changelog` label. If it happens more than a few times, exclude `*_test.go` and help-text files in the script.
- **Reworded heading.** The script anchors on `+## Unreleased`. If a release PR renames the section or someone writes `## [Unreleased]`, the primary count is zero and the fallback count (any added `- ` line) decides. Usually still passes. Fix the regex when it bites.
- **Merge commits in the diff.** `git diff base...HEAD` on a branch that merged main will include main's changelog lines as additions if the base ref is stale. `fetch-depth: 0` and `origin/<base>` should make the base current, but if a PR goes green with no changelog line of its own, this is why. Not worth fixing ahead of time.
- **Filler lines.** `- Updated code.` satisfies the check. Accept it. The check is for forgetting, not for quality, and reviewers still read the changelog.
- **Label creep.** `no-changelog` applied out of habit. The only cheap signal is the label count at the next release. If it is high, talk about it, do not add tooling.

## What is fine as proposed

- Not required for two weeks. Right call. A wrong red blocks nobody.
- Dependabot passes by construction.
- Revert is one commit and leaves nothing behind.

## Before merging

Open a draft PR that touches one file under `internal/` with and without a changelog line, and look at the two job outputs once. Ten minutes, and it catches a typo in the script before anyone else sees it. Then merge.

## Rollback

Delete the `changelog` job from `ci.yml`. Done.
</file>

Nothing changed in the repo; the draft PR is the only thing I would do before merging.
