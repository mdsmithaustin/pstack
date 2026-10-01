# ledgerd

Double-entry posting service for Billing Platform. Go 1.23, `make test`, GitHub Actions.

## Contributing

- Every user-visible change gets a line under `## Unreleased` in `CHANGELOG.md`, in Keep a Changelog form (Added, Changed, Fixed, Removed).
- Dependabot opens dependency bumps weekly. They carry the `dependencies` label and never touch `CHANGELOG.md`.
- CI runs `make test` on every pull request. Branch protection requires it green before merge.
- Proposals for changes to CI or the shared workflow go in `ops/` and get a thumbs up from one other maintainer in the PR.
