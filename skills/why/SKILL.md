---
name: why
description: "Use for 'why does X work this way', 'why we picked Y', design rationale, regressions, postmortems, or data-backed thresholds. Returns a cited read on decisions and tradeoffs. Use how for runtime behavior."
---

# Why

Answer from the record, not the code: read the commits and PR discussions that introduced the target and each later change, and other sources if the trail is thin. Cite what the authors wrote, mark your own inferences as inferences, and say what the record does not answer.

Read a PR with `gh pr view <number> -R <host>/<owner>/<repo>`, taking `<host>/<owner>/<repo>` from origin's fetch URL. If `gh` is missing, unauthenticated, or the query fails, mark those PRs unread and name the gap.
