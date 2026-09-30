# Proposal: fail CI when a code change has no changelog line

Author: Ines. Merge: Tuesday, once one other maintainer has thumbed it up.

## Why

Of the last 40 releases, 11 had a changelog written after the fact by whoever cut the release, from `git log`. Three of those missed a user-visible change. Asking in review works when the reviewer remembers.

## Change

Add one job to `.github/workflows/ci.yml`:

```yaml
  changelog:
    runs-on: ubuntu-latest
    if: ${{ !contains(github.event.pull_request.labels.*.name, 'no-changelog') }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - run: scripts/check-changelog.sh origin/${{ github.base_ref }}
```

`scripts/check-changelog.sh` exits 1 when the diff against the base branch touches anything under `internal/` or `cmd/` and adds no line under `## Unreleased` in `CHANGELOG.md`. It passes when the PR touches only docs, tests, CI, or `go.mod`.

The `no-changelog` label skips the job for the rare refactor with nothing to say. Dependabot PRs touch only `go.mod` and `go.sum`, so they pass without the label.

## Rollback

Delete the job from `ci.yml`. One commit, no other state. The job is not a required check in branch protection for the first two weeks, so a wrong failure blocks nobody; after that, if it has been quiet, make it required.

## Not changing

- `make test` and branch protection on it.
- The changelog format.
