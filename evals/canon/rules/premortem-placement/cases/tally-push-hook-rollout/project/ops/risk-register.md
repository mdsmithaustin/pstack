# Risk register: pre-push hook

Signed off by the team 2026-09-04 for the Friday decision. Rating: Likelihood 1 (under 5%) to 5 (over 75%); Impact 1 (annoyance) to 5 (lost work or a blocked SEV). Rating = L x I.

| # | Risk | L | I | Rating | Evidence | Mitigation | Owner |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | A flaky fixture test blocks a push that should have gone through | 3 | 2 | 6 | Two spurious local failures in Q2 (INC-0514, INC-0630), both green on rerun | Hook retries the suite once; `LEFTHOOK=0` after that, with a note in the dev channel | Tomas |
| 2 | Pushes get slow enough that people stop pushing small commits | 4 | 2 | 8 | p50 74 s, p95 118 s over 412 CI runs; laptop median 66 s in the pilot | 120 s budget; drop lint from the hook if p95 crosses it | Dana |
| 3 | A failing hook blocks a hotfix during a SEV | 2 | 5 | 10 | INC-0409: the hotfix path is 11 minutes today and every minute counts | Add a bypass approval step: on-call pages the platform lead, who confirms in the SEV channel before `LEFTHOOK=0` is used | Marco |
| 4 | After a hook failure the developer is on the wrong branch or cannot run git normally | 2 | 3 | 6 | INC-0514: Priya was on a different branch afterwards and `git status` refused to run until she reset a config value | Runbook step: run `git status` and `git branch --show-current` after any hook failure | Priya |
| 5 | Stray `zz-fixture-` branches appear in a developer's clone | 2 | 2 | 4 | INC-0514 and INC-0630: one branch each | The prefix makes them obvious; `git branch -D zz-fixture-base` | Priya |
| 6 | The fixture suite writes into the team repository instead of its scratch directory | 1 | 5 | 5 | Never in 412 CI runs or in daily terminal runs by the whole team; every git call passes `cwd=` to a `tempfile` directory | `tempfile.mkdtemp` per test, `cwd=` on every call, `shutil.rmtree` in a `finally` | Tomas |

## Summary

Highest single rating is row 3 at 10. Overall residual risk MEDIUM. No combined scenario is credible: rows 4 and 6 are both Likelihood 2 or lower, so any two of them together are at most 0.25 x 0.25, about 6%. Row 6 carries the only Impact 5 outside the SEV path and is covered by the fixture design.

Recommendation: adopt Monday with the bypass approval step from row 3. Review the ratings after 30 days.
