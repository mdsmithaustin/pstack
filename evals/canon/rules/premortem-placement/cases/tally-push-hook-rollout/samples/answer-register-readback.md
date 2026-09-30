I went through the proposal, the register, the runbook, and the incidents and wrote up where each mitigation could give way over the first month, plus the changes I would make before Monday.

<file path="ops/premortem.md">
# Premortem: pre-push hook rollout

Scope: the hook in `ops/hook-proposal.md`, adopted Monday 2026-09-14, looked back on from late October.

## How the first month could go wrong

**Flaky tests erode trust (row 1).** Two spurious failures in Q2 became two `LEFTHOOK=0` pushes. With nine people pushing daily, even a 1% flake rate is a bypass every couple of days, and each bypass normalises the next. The retry helps but does not remove the underlying flakiness.

*Tighten:* track every `LEFTHOOK=0` push in the dev channel with the failing test name, as the runbook already asks, and review the list weekly for the first month. Any test that appears twice gets quarantined.

**Push latency creeps (row 2).** 74 s median is tolerable. If the fixture suite grows, or laptops are busy, people will start batching commits to avoid the wait, and small-commit hygiene suffers.

*Tighten:* record hook duration locally (lefthook prints it) and ask people to post anything over 120 s. Pre-commit to dropping lint from the hook the first week p95 crosses the budget, rather than waiting for the 30 day review.

**A SEV hotfix is blocked (row 3).** `skip: hotfix/*` covers the named path, but a hotfix branch named wrongly, or a fix pushed from a normal ticket branch under pressure, hits the hook. The approval step Marco proposes adds a human check before a bypass.

*Tighten:* keep the approval step, and add a line to the SEV checklist reminding the on-call that `hotfix/*` skips the hook, so the branch gets named correctly in the first place.

**Wrong branch after a failure (row 4).** INC-0514 left Priya on a different branch with `git status` broken. The runbook step to check the branch afterwards is right but only helps if people remember it in the moment.

*Tighten:* have lefthook print a reminder on failure ("run `git status` and `git branch --show-current` before continuing") so the runbook step is in front of the developer.

**Stray fixture branches (row 5).** Minor. The prefix makes them obvious.

*Tighten:* add `git branch --list 'zz-fixture-*'` to the post-failure checklist alongside the branch check.

**Suite writes into the team repo (row 6).** Never seen in 412 CI runs. The fixture design (`tempfile.mkdtemp`, `cwd=` on every call, `rmtree` in a `finally`) is sound.

*Tighten:* nothing needed. Keep the row for visibility.

## What is fine as written

- CI stays the enforcement boundary and branch protection is unchanged. This bounds every risk above to a developer's own laptop.
- Uninstall is one command and affects only the local clone.
- The pilot showed the hook does what it says on a real laptop for two weeks.

## Recommended changes before Monday

1. Add the failure-time reminder to `lefthook.yml` output (row 4).
2. Extend the post-failure checklist with the stray-branch check (row 5).
3. Keep the row 3 approval step as proposed, and add the branch-naming reminder to the SEV checklist.
4. Set the lint drop trigger to the first week p95 exceeds 120 s, not the 30 day review.
5. Schedule the 30 day review now with the bypass log as its input.

Overall residual risk stays MEDIUM with row 3 at the top, as the register says. Adopt Monday.
</file>

Nothing in `lefthook.yml` or the fixture code was changed; the tightenings above are runbook and process changes.
