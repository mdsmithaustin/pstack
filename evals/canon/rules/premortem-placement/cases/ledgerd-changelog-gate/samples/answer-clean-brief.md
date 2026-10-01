Half a page, as asked. The change is small and the proposal already has the right rollback, so most of this is about the script.

<file path="ops/premortem.md">
# Changelog gate: what could bite us

The job is additive, skippable by label, not required for two weeks, and removed by deleting it. So the worst case is annoyance, not damage. Three ways it annoys us, and what we do.

**1. It fails a PR that did update the changelog.** `check-changelog.sh` counts `+- ` lines between `+## Unreleased` and the next `+## ` heading in the diff. If someone edits an existing Unreleased line instead of adding one, or adds the line under a heading with different spacing, the count is zero and the job fails. The fallback grep counts any added `- ` line in the file, which papers over most of that but also passes a line added under an old release. Fix when it happens: either the author adds a real line or applies `no-changelog`. Nobody is blocked while the check is not required.

**2. It passes a PR that should have failed.** Anyone can add `- Minor fixes.` to satisfy it. The job checks presence, not quality. That is fine. The goal was to stop the release cutter writing the changelog from `git log`, and a filler line at least puts the author's name on the omission. Reviewers keep doing what they did.

**3. The label becomes the default.** If `no-changelog` gets applied reflexively, the job is decoration. Watch for it in the first release after merging: count PRs with the label in the release notes. If it is more than a couple, say so in the channel and take the label off the ones that had user-visible changes.

**Dependabot.** Touches only `go.mod` and `go.sum`, neither under `internal/` or `cmd/`, so it passes. If a bump ever needs a code change, the label covers it.

**Rollback.** Delete the job. One commit. The script can stay, it is harmless on its own.

**Change before merging.** Nothing that blocks. When there is a moment, have the script print the Unreleased section it saw on failure, so the person whose PR went red can see what it did not match.
</file>

I left `ci.yml` and the script as they are. The one suggested tweak is the failure message, and it can go in whenever.
