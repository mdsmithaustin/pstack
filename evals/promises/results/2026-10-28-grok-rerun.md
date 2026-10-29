# Grok rerun, 2026-10-28

## Examined revision

The live cases ran with `--skills-at 9323358c14691a80049633ebf4a7803edf09cd65` (`9323358c`), `main` after #346. Its skills tree matches the [519d36a sync receipt](2026-10-27-sync-519d36a.md)'s `5c00045` apart from #332's `skills/poteto-mode/playbooks/eval.md`, which owns neither case. Preflight resolved Grok `1.0.70 (f50904eaee6c)` from `PATH`. Both turns ran on `grok-4.7-build` at `high` effort. The commit that adds this report changes only this file and the 519d36a receipt's Grok bullet.

## Changed live owners covered

The 519d36a receipt left the Grok column unrun. This run covers its one changed live owner:

- `skills/poteto-help/SKILL.md` (#346). It owns `poteto-help-finds-need-and-routes`.

The two bound cases, `poteto-help-run` and `poteto-help-unclear-run`, ran once each with `evals/promises/live.py run --harness grok`. `live.py report` rendered this matrix:

| promise | claude-code | codex | hermes | grok |
|---|---|---|---|---|
| `poteto-help-finds-need-and-routes` | not run | not run | not run | PASS (2) |

1 promise, 2 verdicts: PASS 2. No grader refusal, no preflight error, and no timeout. The turns took 62.5 s and 73.0 s.

I read both final replies by hand. `poteto-help-run` routes the review question to `/poteto-mode review this branch` and the Code review playbook, with `/interrogate` and `/blast-radius` named for their narrower uses, a prompt block, and a public link. `poteto-help-unclear-run` offers the five help sections, reports that no models file exists, and gives a Bug fix prompt from `recipes.md`. Each run read skills only from its own `.agents/skills` (`x_host_skill_hits` is empty), spawned no subagents, and left the project unedited.

## Why the 519d36a wave did not run Grok

The 519d36a receipt recorded `grok login is not usable: the host token expired at 2026-10-27T01:20Z` and said a maintainer must run `grok login`. That remedy was wrong. The adapter reads the host's cached access token from `~/.grok/auth.json`. That token is short-lived, and the host login also stores a refresh token. Starting the Grok CLI on the host renewed the access token without a new login. The adapter's own auth provider says the same, but its preflight refuses with the `grok login` advice instead of renewing the token. Follow-up: the preflight should renew through a host Grok command before it refuses.

## Comparison baseline

The newest earlier Grok row for this promise is in the [eb4db2b sync receipt](2026-10-22-sync-eb4db2b.md), PASS (2). The [e73df47 receipt](2026-10-24-sync-e73df47.md) and the 519d36a receipt did not run Grok. This run matches the eb4db2b row, so no verdict regressed.

Run directory: `~/pstack-live-runs/2026-10-28-grok-sync-519d36a` (`tally-h81qwckc`, `tally-gmqwiaqv`).
