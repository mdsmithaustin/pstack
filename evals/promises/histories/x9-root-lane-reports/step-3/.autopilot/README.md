# Root run state: tally queue, full autopilot

Root-only state for this run. Owners write only inside their own `owner-<pr>/` folder.

- `queue.tsv`: the queue, each PR's owner, and its state.
- `root-decisions.tsv`: the root's decision trail.
- `issues/`: the forge issues the queue serves, copied here with their attachments.
- `lanes/`: the reports round 1's lanes returned to the root, one file per lane. `lanes/saved/` holds the saved runs they cite.
- `owner-12/`: PR 12's owner. `decisions.tsv` and `session.txt` are its trail, `children.tsv` its subagent registry.
- `owner-12/inbox.md`: messages from the root to the owner. Append to it; the owner reads it at its next turn.
- `outbox/`: the forge CLI is not logged in on this machine. Write each forge action you would take (a PR comment, an issue) as one markdown file here, with the exact command on the first line and the body below it. The operator replays them.

The repository is not gated. The PR's base is `main`.
