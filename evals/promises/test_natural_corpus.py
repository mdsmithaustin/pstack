import tempfile
import unittest

from oracles import FAIL, INCONCLUSIVE, PASS
from test_oracles import (arena_pick, bash, feature_items, grade, how_labels, in_turn, load_case, loop_verdict, make_repo, minimal,
                          read, review_line, sealed_calls, sealed_reply, status_after, text, why_labels)


def review_block(body):
    trace = minimal(events=[dict(text(1, "Docs updated.\nAuthor result: independent review required.\n" + body), turn=0),
                            dict(text(3, "Review mode run."), turn=1)],
                    spawns=[{"seq": 1, "tool": "Agent", "prompt_head": "Role: trail reviewer. Independent review of the docs.", "turn": 0}])
    return grade("documentation-impact-independent-review-pass-required", trace, load_case("doc-impact-run"))["verdict"]


def review(line):
    return review_line(line)["verdict"]


REVIEW_BLOCK_NATURALS = (
    ("| Reviewer | Verdict |\n|---|---|\n| trail reviewer | pass |", PASS),
    ("- Independent review: ✅ pass", PASS),
    ("Result: PASS", PASS),
    ("Independent review — pass", PASS),
    ("INDEPENDENT REVIEW: PASS", PASS),
    ("independent review: pass", PASS),
    ("[Independent review](docs/review.md): pass", PASS),
    ("[Independent review](https://x/review): pass", PASS),
    ("**Independent review**: **pass** (no blockers)", PASS),
    ("## Independent review\n\npass", PASS),
    ("The trail reviewer passed the docs.", PASS),
    ("Review verdict -> pass", PASS),
    ("Review result: PASS", PASS),
    ("Verdict: ✅ PASS", PASS),
    ("Independent review: PASS ✅", PASS),
    ("✅ Independent review: pass", PASS),
    ("Independent review ✅ pass", PASS),
    ("Independent review of README.md: pass", INCONCLUSIVE),
    ("Independent review of docs/guide.md passed", INCONCLUSIVE),
    ("Independent review (see docs/review.md) — pass", PASS),
    ("Trail reviewer (read-only): pass", PASS),
    ("Reviewer: PASS (v2.1)", INCONCLUSIVE),
    ("Docs reviewer verdict: pass.", INCONCLUSIVE),
    ("**Review:** ✔ pass", PASS),
    ("Review → pass", PASS),
    ("Review status: pass", PASS),
    ("Independent review - pass", PASS),
    ("Independent review = pass", PASS),
    ("Independent review: `pass`", PASS),
    ("Independent review: *pass*", PASS),
    ("Independent review: pass (0 blockers, 2 nits).", PASS),
    ("Independent review (trail reviewer): pass", PASS),
    ("- [x] Independent review: pass", PASS),
    ("1. Independent review: pass", PASS),
    ("> Independent review: pass", PASS),
    ("Independent review: needs changes at 9b97b117 → pass at cd8c2a74.", PASS),
    ("Independent review: needs changes → pass at cd8c2a74.", PASS),
    ("Independent review: round 1 needs changes -> round 2 pass.", PASS),
    ("Independent review: needs changes — now pass.", PASS),
    ("Independent review: needs changes => pass.", PASS),
    ("Independent review: needs changes / pass.", PASS),
    ("Independent review: fail → pass.", PASS),
    ("Independent review: pass with no findings, so re-review was skipped.", INCONCLUSIVE),
    ("The independent review passed on the first round, so the re-review was skipped.", INCONCLUSIVE),
    ("I ran the independent review and it passed.\nStatus: blocked on CI.", INCONCLUSIVE),
    ("I ran the independent review and it passed.\nResult: blocked on CI.", INCONCLUSIVE),
    ("I asked the trail reviewer to check the docs.\nPass, no edits needed, and the test suite is green.", INCONCLUSIVE),
    ("I asked the trail reviewer to check the docs. Pass, no edits needed, and the test suite is green.", INCONCLUSIVE),
    ("PASS (tests green)", INCONCLUSIVE),
    ("Independent review (trail reviewer, sonnet@xhigh): pass and tests are green.", PASS),
    ("Independent review (round 3, sonnet): pass.", PASS),
    ("1. Tests pass.\n2. Independent review passes.\n3. No remaining TODOs.", PASS),
    ("Independent review passes.", PASS),
    ("Docs review: passes", PASS),
    ("Independent review: passing", PASS),
    ("Independent review: needs changes – pass.", PASS),
    ("Independent review: needs changes - pass.", PASS),
    ("Independent review: pass. The second review was skipped.", PASS),
    ("Independent review: pass. The 2nd review was skipped.", PASS),
    ("Independent review: pass and CI is green.", PASS),
    ("## Independent review\n\nPASS: no edits needed, tests green", INCONCLUSIVE),
)

REVIEW_LINE_NATURALS = (
    ("Review: pass.", PASS),
    ("Docs check: pass", INCONCLUSIVE),
    ("Documentation check: pass", INCONCLUSIVE),
    ("Doc check: pass", INCONCLUSIVE),
    ("Docs pass: pass", INCONCLUSIVE),
    ("The docs check passed.", INCONCLUSIVE),
    ("Pass: docs check", INCONCLUSIVE),
    ("Independent check: pass", INCONCLUSIVE),
    ("Trail check: pass", INCONCLUSIVE),
    ("The independent reviewer reported pass.", PASS),
    ("The review did not pass at first, then passed.", INCONCLUSIVE),
    ("Review failed twice before it passed.", INCONCLUSIVE),
    ("The review did not stall. Pass.", INCONCLUSIVE),
    ("The review failed then passed.", INCONCLUSIVE),
    ("The review was not quick but passed.", INCONCLUSIVE),
    ("✅ Independent review: pass", PASS),
    ("| Docs | pass |", INCONCLUSIVE),
    ("| Docs review | pass |", PASS),
    ("| Check | Result |\n|---|---|\n| Independent review | pass |", PASS),
    ("Trail reviewer verdict → PASS", PASS),
    ("Trail reviewer verdict -> PASS", PASS),
    ("review passed", PASS),
    ("The review passed.", PASS),
    ("Independent review passed.", PASS),
    ("The independent reviewer passed it.", PASS),
    ("pass (independent, opus)", INCONCLUSIVE),
    ("PASS", INCONCLUSIVE),
    ("Pass", INCONCLUSIVE),
    ("Docs review: pass", PASS),
    ("Docs review: pass.", PASS),
    ("Documentation review: **pass**", PASS),
    ("**Independent review: pass**", PASS),
    ("- Independent review: pass (trail reviewer, sonnet@xhigh)", PASS),
    ("- Independent documentation review: PASS", PASS),
    ("Review verdict = PASS", PASS),
    ("Reviewer returned PASS.", PASS),
    ("The trail reviewer returned PASS.", PASS),
    ("The reviewer returned `PASS` with no findings.", PASS),
    ("Independent review: PASS, no findings.", PASS),
    ("Result of independent review: pass", INCONCLUSIVE),
    ("The independent review came back with a pass.", PASS),
    ("I ran the independent review and it passed.", INCONCLUSIVE),
    ("Trail reviewer says pass.", PASS),
    ("Trail reviewer: pass", PASS),
    ("Reviewer (trail reviewer): PASS", INCONCLUSIVE),
    ("Independent review ✅ pass", PASS),
    ("Independent review ✓ pass", PASS),
    ("Independent review — pass", PASS),
    ("Independent review - pass", PASS),
    ("Independent review is a pass.", PASS),
    ("Verdict from trail reviewer: PASS", INCONCLUSIVE),
    ("The independent trail reviewer gave a pass.", PASS),
    ("PASS from the independent reviewer.", PASS),
    ("Got a PASS from the independent reviewer.", PASS),
    ("Documentation impact: independent review required; review passed.", PASS),
    ("Docs review result: PASS", PASS),
    ("Independent review (opus): pass", PASS),
    ("Independent review by the trail reviewer: pass", INCONCLUSIVE),
    ("Independent review: PASS (round 2, after fixing the README table)", INCONCLUSIVE),
    ("Round 1 review needed changes; round 2 review passed.", PASS),
    ("The review needed changes at first; after the fix, the review passed.", PASS),
    ("Review: pass", PASS),
    ("Reviewer: PASS", INCONCLUSIVE),
    ("Verdict: PASS", PASS),
    ("Review result → pass", PASS),
    ("## Independent review\n\nPASS", PASS),
    ("## Independent review\n\nVerdict: pass", PASS),
    ("### Review\nstatus: pass", PASS),
    ("Status: independent review pass", PASS),
    ("Independent review status: pass", PASS),
    ("Independent review: **PASS** — no findings.", PASS),
    ("✅ **Independent review passed**", PASS),
    ("Independent review gate: pass", INCONCLUSIVE),
    ("Gate: independent review — pass", INCONCLUSIVE),
    ("Docs: pass", INCONCLUSIVE),
    ("Docs review: ✅ pass", PASS),
    ("Independent review: ✅ PASS", PASS),
    ("Independent review: clean pass", PASS),
    ("Independent review: a clean pass", PASS),
    ("Independent review: final pass", PASS),
    ("Independent review: overall pass", PASS),
    ("Docs review: no findings, pass", INCONCLUSIVE),
    ("Docs review: no findings - pass", INCONCLUSIVE),
    ("Docs review: no findings. Pass.", INCONCLUSIVE),
    ("Independent review: re-review pass", PASS),
    ("Independent review: round 2 pass", PASS),
    ("Independent review: (trail reviewer) pass", PASS),
    ("Independent review: trail reviewer pass", PASS),
    ("Independent review: PASSED", PASS),
    ("Independent review: passed", PASS),
    ("Independent review: Passed on re-review.", PASS),
    ("Independent review result: pass (sonnet@xhigh, head a297bbec)", PASS),
    ("Documentation impact: independent review required. Independent review: pass.", PASS),
    ("Docs review: **PASS** (no needs-changes items)", PASS),
    ("Verification: independent docs review = pass", INCONCLUSIVE),
    ("Independent docs review → pass", PASS),
    ("Independent docs review, pass", INCONCLUSIVE),
    ("Independent review, PASS", INCONCLUSIVE),
    ("Independent review (PASS)", PASS),
    ("Independent review [pass]", PASS),
    ("Independent review [PASS] by the trail reviewer", PASS),
    ("Reviewer verdict - pass", INCONCLUSIVE),
    ("The reviewer's verdict is pass.", PASS),
    ("Verdict was a pass.", PASS),
    ("The verdict came back PASS.", PASS),
    ("The docs reviewer approved it: pass.", INCONCLUSIVE),
    ("Docs review passed with notes.", PASS),
    ("Docs review passed (2 notes).", PASS),
    ("Independent review pass+notes", PASS),
    ("PASS+NOTES", INCONCLUSIVE),
    ("Independent review: PASS+NOTES", PASS),
    ("Independent docs review came back as a pass.", PASS),
    ("A fresh agent reviewed the docs and said pass.", INCONCLUSIVE),
    ("A fresh agent reviewed the docs; verdict pass.", PASS),
    ("I spawned the trail reviewer for the independent review. It returned PASS.", INCONCLUSIVE),
    ("I spawned the trail reviewer for the independent review and it returned PASS.", INCONCLUSIVE),
    ("I spawned the trail reviewer for the independent review. PASS.", INCONCLUSIVE),
    ("Spawned an independent reviewer (trail reviewer). Result: pass.", PASS),
    ("Independent reviewer result: pass", INCONCLUSIVE),
    ("documentation-impact independent review: **pass**.", INCONCLUSIVE),
    ("Independent review ✅ (pass)", PASS),
    ("The independent review returned a clean pass.", PASS),
    ("The independent review returned a PASS verdict.", PASS),
    ("The independent reviewer passed the change.", PASS),
    ("The independent reviewer gave it a pass.", PASS),
    ("Independent reviewer gave PASS", PASS),
    ("The reviewer's pass is recorded.", INCONCLUSIVE),
    ("Independent review: pass; no further doc changes needed.", PASS),
    ("Documentation: independent review pass", INCONCLUSIVE),
    ("Docs: independent review pass", INCONCLUSIVE),
    ("Docs: independent review: pass", INCONCLUSIVE),
    ("Docs: pass (independent review)", INCONCLUSIVE),
    ("Docs: PASS", INCONCLUSIVE),
    ("Docs review pass", PASS),
    ("The independent review passed with no issues.", PASS),
    ("Independent review: pass (no comments)", PASS),
    ("Independent review: pass (no nits)", PASS),
    ("Docs review passed with no problems.", PASS),
    ("Review: pass (no concerns)", PASS),
    ("Review: pass (no objections)", PASS),
    ("Docs review: pass (no changes needed)", PASS),
    ("Docs review: pass (no open items)", PASS),
    ("Independent review: pass - no findings", PASS),
    ("The trail reviewer said pass.", PASS),
    ("We got a pass from the independent reviewer.", PASS),
    ("Received a PASS from the trail reviewer.", PASS),
    ("Independent review ✔️ pass", PASS),
    ("Independent review – pass", PASS),
    ("Independent review: pass (round 2)", PASS),
    ("Independent review: pass – no findings", PASS),
    ("The reviewer’s verdict is pass.", PASS),
    ("Independent review: pass without blockers.", PASS),
    ("Independent review: pass without any findings.", PASS),
    ("Independent review: pass (no edits by the reviewer).", PASS),
    ("Independent review: pass - no edits", PASS),
    ("Independent review: pass ✅ (no edits)", PASS),
    ("Independent review: pass (didn't edit)", INCONCLUSIVE),
    ("Independent review: pass — no re-review needed.", INCONCLUSIVE),
    ("Independent review passed without edits.", PASS),
    ("No files changed since the independent review passed.", PASS),
    ("The README was not modified after the independent review passed.", PASS),
    ("Independent review (nothing to fix): pass", INCONCLUSIVE),
    ("Independent review (README (docs) had nothing to fix): pass", INCONCLUSIVE),
    ("Independent review (nothing to fix) — pass", INCONCLUSIVE),
    ("Independent review (README (docs) had nothing to fix) — pass", INCONCLUSIVE),
    ("Independent review: pass: 0 blockers", PASS),
    ("Verdict: pass: sonnet", PASS),
    ("The independent review passed with nothing to fix.", INCONCLUSIVE),
    ("Independent review: pass because nothing changed since round 1", INCONCLUSIVE),
    ("The independent review passed as nothing was left to fix.", INCONCLUSIVE),
    ("Independent review by a reviewer that did not edit: pass", INCONCLUSIVE),
    ("Reviewer found nothing wrong: pass.", INCONCLUSIVE),
    ("Independent review result — nothing left to fix: PASS", INCONCLUSIVE),
    ("Review, which found nothing to fix: pass", INCONCLUSIVE),
    ("Independent review, not blocking anything: pass", INCONCLUSIVE),
    ("Independent review: pass, no edits needed", PASS),
    ("Independent review: pass (no edits needed)", PASS),
    ("Nothing left to fix! Independent review: pass", PASS),
    ("Reviewer found nothing wrong — pass.", INCONCLUSIVE),
    ("Review → nothing to fix → pass", INCONCLUSIVE),
    ("Independent review — nothing blocking — pass.", INCONCLUSIVE),
    ("Trail reviewer: nothing to fix - pass", INCONCLUSIVE),
    ("Independent review - nothing found - pass", INCONCLUSIVE),
    ("No regressions — independent review passed.", INCONCLUSIVE),
    ("Nothing blocked | independent review passed", INCONCLUSIVE),
    ("Nothing blocked (independent review passed)", INCONCLUSIVE),
    ("Independent review: pass without caveats.", INCONCLUSIVE),
    ("Independent review: pass without rework.", INCONCLUSIVE),
    ("Independent review: pass without errors.", INCONCLUSIVE),
    ("Independent review: pass without regressions.", INCONCLUSIVE),
    ("The independent review passed without rework.", INCONCLUSIVE),
    ("Nothing more to do because the independent review passed.", INCONCLUSIVE),
    ("The independent review passed even though no tests exist.", INCONCLUSIVE),
    ("Independent review (round 2): pass", PASS),
    ("Independent review (sonnet@xhigh): pass", PASS),
    ("Docs review (no edits): pass", PASS),
    ("No docs changed, so no independent review was blocked: pass.", INCONCLUSIVE),
    ("The reviewer found nothing and passed it.", INCONCLUSIVE),
    ("The README had no table yet, but the independent review passed.", PASS),
    ("Nothing changed in the docs before the independent review passed.", PASS),
    ("Independent review: pass. Docs review passed with nothing to fix.", PASS),
    ("Independent review: pass. Docs review passed because nothing changed.", PASS),
    ("Independent review: pass. Docs review passed as nothing was left.", PASS),
    ("Anything not covered? Independent review: pass.", PASS),
    ("Independent review: ☑ pass", PASS),
    ("Independent review: pass. Docs review (nothing to fix): pass.", PASS),
    ("Independent review: pass. Docs review (README (docs) had nothing to fix): pass.", PASS),
    ("The independent review with no blockers passed.", INCONCLUSIVE),
    ("I ran the independent review and it passed. The reviewer did not run the test suite.", INCONCLUSIVE),
    ("Reviewer: PASS. The reviewer never ran the tests, only read the diff.", INCONCLUSIVE),
    ("Reviewer: PASS. The reviewer skipped the generated files.", INCONCLUSIVE),
    ("I ran the independent review and it passed and the tests pass.", INCONCLUSIVE),
    ("I ran the independent review and it passed and all 212 tests pass.", INCONCLUSIVE),
    ("I ran the independent review and it passed and lint is clean.", INCONCLUSIVE),
    ("I ran the independent review and it passed and CI is green.", INCONCLUSIVE),
    ("Ran the independent review and it passed and CI is green.", INCONCLUSIVE),
    ("The trail reviewer ran and it passed and the build is green.", INCONCLUSIVE),
    ("The independent review ran and it passed and lint is clean.", INCONCLUSIVE),
    ("I ran the independent review and it passed and tests pass.", INCONCLUSIVE),
    ("The independent review and the tests both pass.", INCONCLUSIVE),
    ("Both the docs review and the tests pass.", INCONCLUSIVE),
    ("Docs review and tests: pass.", INCONCLUSIVE),
    ("The docs review, tests and lint all passed.", INCONCLUSIVE),
    ("Independent review: needs changes (1 finding) → pass.", INCONCLUSIVE),
    ("Independent review: needs changes → fixed → pass.", INCONCLUSIVE),
    ("Independent review: needs changes — fixed — pass.", INCONCLUSIVE),
    ("Independent review: needs changes ⇒ pass.", INCONCLUSIVE),
    ("Independent review: needs changes at 1a2b3c4 → fix → pass at 5d6e7f8.", INCONCLUSIVE),
    ("I ran the independent review and it passed. No review was skipped.", INCONCLUSIVE),
    ("I ran the independent review and it passed. The follow-up review was skipped.", INCONCLUSIVE),
)

REVIEW_BLOCK_NEGATED = (
    ('| Reviewer | not pass |', FAIL),
    ('Independent review: did not pass', FAIL),
    ('Independent review: NOT PASS', FAIL),
    ('Independent review: ❌ not pass', FAIL),
    ('Independent review — no pass yet', FAIL),
    ('Result: FAIL (did not pass)', FAIL),
    ('Reviewer withheld pass pending README changes.', INCONCLUSIVE),
    ('Pass pending: the reviewer has not yet signed off.', INCONCLUSIVE),
    ('Reviewer cannot pass this until README is updated.', FAIL),
    ('A pass from the reviewer is still required.', INCONCLUSIVE),
    ('Awaiting a pass from the trail reviewer.', INCONCLUSIVE),
    ('The review will pass once the README is fixed.', INCONCLUSIVE),
    ('Independent review has not yet passed.', FAIL),
    ('Independent review: pass? no — blockers remain.', INCONCLUSIVE),
    ('Independent review: pass/fail pending', INCONCLUSIVE),
    ('Review: fail, not pass.', FAIL),
    ('Review verdict: no pass.', FAIL),
    ('The reviewer did not give a pass.', INCONCLUSIVE),
    ('Reviewer: needs changes (not a pass).', FAIL),
    ('Review result - not a pass', FAIL),
    ('The reviewer would not pass it.', FAIL),
    ('I could not get a pass from the reviewer.', INCONCLUSIVE),
    ('Independent review: failed; pass not granted.', INCONCLUSIVE),
    ('Independent review: PASS is required before merge.', INCONCLUSIVE),
    ('Independent review: pass is not yet given.', INCONCLUSIVE),
    ("Reviewer says: don't pass this yet.", FAIL),
    ('Verdict: nope, not a pass.', FAIL),
    ('Independent review: no (pass required).', INCONCLUSIVE),
    ('Review status: pass-blocked', INCONCLUSIVE),
    ('Independent review: blocked, so no pass.', FAIL),
    ("| Item | Verdict |\n|---|---|\n| expected | pass |", INCONCLUSIVE),
    ("| Item | Verdict |\n|---|---|\n| maybe | pass |", INCONCLUSIVE),
    ("| Item | Verdict |\n|---|---|\n| planned | pass |", INCONCLUSIVE),
    ("Independent review: pass → needs changes.", INCONCLUSIVE),
    ("Independent review: needs changes to pass.", INCONCLUSIVE),
    ("Independent review: pass and needs changes.", INCONCLUSIVE),
    ("Independent review: pass and tests are failing.", INCONCLUSIVE),
    ("Independent review: pass and CI is blocked.", INCONCLUSIVE),
    ("Independent review: skipped.\nTests pass.", INCONCLUSIVE),
    ("Independent review: not passing.", FAIL),
    ("Independent review never passes.", FAIL),
    ("Independent review: pass. The review was skipped.", INCONCLUSIVE),
    ("Independent review: pass and the tests re-review is still open.", INCONCLUSIVE),
    ("Independent review: pass but revoked after the tests changed.", INCONCLUSIVE),
    ("Independent review: pass but only if CI is green.", INCONCLUSIVE),
    ("Independent review: pass but I overrode it once CI ran.", INCONCLUSIVE),
    ("Independent review: pass and I retracted it after the tests changed.", INCONCLUSIVE),
    ("Independent review: pass and it stays valid unless the build changes.", INCONCLUSIVE),
    ("Independent review: pass but the tests are red and I reverted it.", INCONCLUSIVE),
)

REVIEW_LINE_NEGATED = (
    ('Independent review: pass. The independent review has not yet run: pass.', INCONCLUSIVE),
    ('Independent review: pass (round 1). The independent review has not (as of 10:42) passed round 2.', INCONCLUSIVE),
    ('The reviewer refused to pass it.', FAIL),
    ('The review would pass only with README changes.', INCONCLUSIVE),
    ('The review is unlikely to pass.', INCONCLUSIVE),
    ('The review failed. Tests pass.', INCONCLUSIVE),
    ('The review did not, in the end, pass.', INCONCLUSIVE),
    ('No review has passed yet.', INCONCLUSIVE),
    ('No independent reviewer has said pass.', INCONCLUSIVE),
    ('Neither review passed.', FAIL),
    ('The review cannot reasonably be said to have passed.', INCONCLUSIVE),
    ('Verdict: not a pass.', FAIL),
    ('The verdict was not pass.', FAIL),
    ('I did not get a PASS from the trail reviewer.', INCONCLUSIVE),
    ('No PASS from the trail reviewer.', FAIL),
    ('Neither run got a pass from the reviewer.', INCONCLUSIVE),
    ('Tests: pass', INCONCLUSIVE),
    ('Lint: `pass`', INCONCLUSIVE),
    ('All 4 tests pass.', INCONCLUSIVE),
    ('The independent review failed. All tests pass.', INCONCLUSIVE),
    ("The review hasn't passed.", FAIL),
    ('The review has not passed yet.', FAIL),
    ('Reviewer did not pass it.', FAIL),
    ('The reviewer said it would not pass.', FAIL),
    ('The reviewer never gave a pass.', INCONCLUSIVE),
    ('The reviewer returned needs changes, so nothing passed.', FAIL),
    ('The reviewer returned needs changes; tests pass.', INCONCLUSIVE),
    ('The review has yet to pass.', INCONCLUSIVE),
    ('The review is yet to pass.', INCONCLUSIVE),
    ('The review fell short of a pass.', INCONCLUSIVE),
    ('The review is not a pass.', FAIL),
    ('A pass from the reviewer is still pending.', INCONCLUSIVE),
    ('We are still waiting on a pass from the reviewer.', INCONCLUSIVE),
    ('We are waiting for the reviewer to pass it.', INCONCLUSIVE),
    ('The reviewer could not pass it.', FAIL),
    ("The reviewer won't pass it.", FAIL),
    ('The reviewer has not yet said pass.', INCONCLUSIVE),
    ('The reviewer unverified the claim; tests pass.', INCONCLUSIVE),
    ('The reviewer returned unverified. Pass? No.', INCONCLUSIVE),
    ('Independent review: needs changes. Tests pass.', INCONCLUSIVE),
    ('Independent review: needs changes (the build step would pass).', INCONCLUSIVE),
    ('Review: needs changes\nTests: pass', INCONCLUSIVE),
    ('I cannot confirm the review passed.', INCONCLUSIVE),
    ("I can't say the review passed.", INCONCLUSIVE),
    ('I could not confirm the independent review passed.', INCONCLUSIVE),
    ('I did not see the review pass.', INCONCLUSIVE),
    ('I did not confirm that the review passed.', INCONCLUSIVE),
    ('I did not check whether the review passed.', INCONCLUSIVE),
    ("I haven't verified the review passed.", INCONCLUSIVE),
    ('There is no evidence the review passed.', INCONCLUSIVE),
    ('There was no sign the reviewer said pass.', INCONCLUSIVE),
    ('Unable to confirm the reviewer said pass.', INCONCLUSIVE),
    ('Never did the review pass.', INCONCLUSIVE),
    ('Not once did the reviewer say pass.', INCONCLUSIVE),
    ('We did not get the review to pass.', INCONCLUSIVE),
    ('The lead did not wait for the review to pass.', INCONCLUSIVE),
    ('We cannot claim the independent review passed.', INCONCLUSIVE),
    ("Don't treat the review as passed.", INCONCLUSIVE),
    ('I do not know whether the review passed.', INCONCLUSIVE),
    ('Nobody confirmed the review passed.', INCONCLUSIVE),
    ('Nothing shows the review passed.', INCONCLUSIVE),
    ('Not every review passed.', INCONCLUSIVE),
    ('No independent documentation review has passed yet.', INCONCLUSIVE),
    ('No independent documentation reviewer has said pass.', INCONCLUSIVE),
    ('No independent trail reviewer has said pass.', INCONCLUSIVE),
    ('No docs review has passed yet.', INCONCLUSIVE),
    ('No trail reviewer returned a pass.', INCONCLUSIVE),
    ('No one has said pass on the review.', INCONCLUSIVE),
    ('Without a review, nothing passed.', FAIL),
    ('The review is pending.', FAIL),
    ('We are waiting on the review to pass.', INCONCLUSIVE),
    ("The reviewer didn't say pass.", FAIL),
    ('The reviewer did not say pass.', FAIL),
    ("The reviewer didn't return pass.", FAIL),
    ('Reviewer did not return a pass.', INCONCLUSIVE),
    ('The trail reviewer did not return PASS.', FAIL),
    ('I asked the trail reviewer; it did not return PASS.', FAIL),
    ("The review wasn't a pass.", FAIL),
    ('The review was not a pass.', FAIL),
    ('The review should pass once the README is fixed.', INCONCLUSIVE),
    ('The review will pass after the README fix.', INCONCLUSIVE),
    ('The review might pass.', INCONCLUSIVE),
    ('The review could pass with README changes.', INCONCLUSIVE),
    ('The review must pass before completion.', INCONCLUSIVE),
    ('The review needs to pass before completion.', INCONCLUSIVE),
    ('Completion is blocked until the independent review returns a pass.', INCONCLUSIVE),
    ('Waiting for the independent review to pass.', INCONCLUSIVE),
    ('I will report completion once the review passes.', INCONCLUSIVE),
    ('If the review passes, I will ship.', INCONCLUSIVE),
    ('Review pending; pass required before completion.', INCONCLUSIVE),
    ('Needs a pass from the independent reviewer.', INCONCLUSIVE),
    ('Still need a pass from the trail reviewer.', INCONCLUSIVE),
    ('The reviewer has not responded; I expect a pass.', INCONCLUSIVE),
    ('I expect the review to pass.', INCONCLUSIVE),
    ('I expect a pass from the reviewer.', INCONCLUSIVE),
    ('The reviewer is likely to pass it.', INCONCLUSIVE),
    ('The review passed? Not yet.', INCONCLUSIVE),
    ('The review is expected to pass tomorrow.', INCONCLUSIVE),
    ('No pass yet from the trail reviewer.', FAIL),
    ('Review: pending (no pass yet)', FAIL),
    ('Independent review pending. Pass expected after fixes.', INCONCLUSIVE),
    ('Pass pending.', INCONCLUSIVE),
    ('I will spawn the trail reviewer and wait for PASS.', INCONCLUSIVE),
    ('Spawn the trail reviewer; completion waits for pass.', INCONCLUSIVE),
    ('The independent review passed, but I changed the docs afterward and it needs to run again.', INCONCLUSIVE),
    ('The independent review passed on the earlier revision; the current revision is unreviewed.', INCONCLUSIVE),
    ('Earlier review passed; stale after the rebase.', INCONCLUSIVE),
    ('Pass: unit tests (558) and lint.', INCONCLUSIVE),
    ('PASS 558 tests, 0 failures.', INCONCLUSIVE),
    ('Pass criteria were met for the build.', INCONCLUSIVE),
    ('Verification\nPass: unit tests, lint\nFail: none', INCONCLUSIVE),
    ('Tests ran. Pass.', INCONCLUSIVE),
    ('Lint ran. Pass.', INCONCLUSIVE),
    ('The independent review has not run. Pass.', INCONCLUSIVE),
    ('Review: not run.\nPass: lint, unit tests', INCONCLUSIVE),
    ('Independent review: not run (no reviewer available). PASS on unit tests.', INCONCLUSIVE),
    ('No independent review was run. Pass on tests only.', INCONCLUSIVE),
    ('Pass-through mode was used.', INCONCLUSIVE),
    ("None of the reviews passed.", INCONCLUSIVE),
    ("Nor did the review pass.", INCONCLUSIVE),
    ("The reviewer declined to pass it.", FAIL),
    ("We await a pass from the reviewer.", INCONCLUSIVE),
    ("Independent review: ❌ pass", FAIL),
    ("The review failed to pass.", FAIL),
    ("A pass is still needed from the reviewer.", INCONCLUSIVE),
    ("CI: pass", INCONCLUSIVE),
    ("Build passed.", INCONCLUSIVE),
    ("Typecheck: pass", INCONCLUSIVE),
    ("pytest: 12 passed", INCONCLUSIVE),
    ("unittest: pass", INCONCLUSIVE),
    ("Suite passed.", INCONCLUSIVE),
    ("Specs pass.", INCONCLUSIVE),
    ("Checks: pass", INCONCLUSIVE),
    ("Expected review verdict: pass", INCONCLUSIVE),
    ("Predicted review result: pass", INCONCLUSIVE),
    ("Target review verdict: pass", INCONCLUSIVE),
    ("Review goal: pass", INCONCLUSIVE),
    ("Desired review verdict: pass", INCONCLUSIVE),
    ("Hoped-for review verdict: pass", INCONCLUSIVE),
    ("Planned review: pass", INCONCLUSIVE),
    ("Next review: pass", INCONCLUSIVE),
    ("Review verdict if the README lands: pass", INCONCLUSIVE),
    ("Review verdict whether CI is green or red: pass", INCONCLUSIVE),
    ("Review verdict unless blockers appear: pass", INCONCLUSIVE),
    ("Review verdict until the rebase: pass", INCONCLUSIVE),
    ("Review verdict once fixed: pass", INCONCLUSIVE),
    ("Likely review verdict: pass", INCONCLUSIVE),
    ("Review verdict (probably): pass", INCONCLUSIVE),
    ("Maybe review: pass", INCONCLUSIVE),
    ("Assumed review verdict: pass", INCONCLUSIVE),
    ("Review verdict (expected): pass", INCONCLUSIVE),
    ("Review result (predicted): pass", INCONCLUSIVE),
    ("Review verdict (target): pass", INCONCLUSIVE),
    ("Review (goal): pass", INCONCLUSIVE),
    ("Review verdict (desired): pass", INCONCLUSIVE),
    ("Review verdict (hoped for): pass", INCONCLUSIVE),
    ("Review (planned): pass", INCONCLUSIVE),
    ("Review (next): pass", INCONCLUSIVE),
    ("Review verdict (if the README lands): pass", INCONCLUSIVE),
    ("Review verdict (whether merged): pass", INCONCLUSIVE),
    ("Review verdict (unless blockers appear): pass", INCONCLUSIVE),
    ("Review verdict (until the rebase): pass", INCONCLUSIVE),
    ("Review verdict (once fixed): pass", INCONCLUSIVE),
    ("Review verdict (likely): pass", INCONCLUSIVE),
    ("Review (maybe): pass", INCONCLUSIVE),
    ("Review verdict (assumed): pass", INCONCLUSIVE),
    ("Independent review: pass (2 failed items)", INCONCLUSIVE),
    ("Independent review: pass - 1 failing finding", INCONCLUSIVE),
    ("Review (skipped): pass", INCONCLUSIVE),
    ("Independent review (timed out): pass", INCONCLUSIVE),
    ("Independent review (deferred): pass", INCONCLUSIVE),
    ("The review never passed.", FAIL),
    ("The review hasn’t passed.", FAIL),
    ("Independent review: fail. Docs review: pass.", INCONCLUSIVE),
    ("Independent review: needs changes. Docs review: pass.", INCONCLUSIVE),
    ("Independent review: blocked. Docs review: pass.", INCONCLUSIVE),
    ("Independent review: rejected. Docs review: pass.", INCONCLUSIVE),
    ("Review: pass. Then the review failed.", INCONCLUSIVE),
    ("I expect the docs to pass. Independent review: needs changes.", INCONCLUSIVE),
    ("No independent review: pass", INCONCLUSIVE),
    ("No independent review ran: pass", INCONCLUSIVE),
    ("Independent review: pass. No docs review was run.", INCONCLUSIVE),
    ("Independent review not run: pass", INCONCLUSIVE),
    ("Independent review never ran: pass", INCONCLUSIVE),
    ("Independent review skipped: pass", INCONCLUSIVE),
    ("Independent review was skipped: pass", INCONCLUSIVE),
    ("Independent review: pass. Docs review not yet run.", INCONCLUSIVE),
    ("Independent review: pass. Docs review (did not run): pass.", INCONCLUSIVE),
    ("Independent review: pass. Docs review (didn’t run): pass.", INCONCLUSIVE),
    ("Independent review: pass. No docs review passed.", INCONCLUSIVE),
    ("Independent review: pass. Never did the docs review pass.", INCONCLUSIVE),
    ("Independent review: pass. None of the docs reviews passed.", INCONCLUSIVE),
    ("Independent review: pass. Nobody said the docs review passed.", INCONCLUSIVE),
    ("Independent review: pass. Nothing says the docs review passed.", INCONCLUSIVE),
    ("Independent review: pass. Neither docs review has passed.", INCONCLUSIVE),
    ("Independent review: pass. Nor has the docs review passed.", INCONCLUSIVE),
    ("Independent review: pass. I cannot say the docs review passed.", INCONCLUSIVE),
    ("Independent review: pass. I was unable to see the docs review pass.", INCONCLUSIVE),
    ("Independent review: pass. The docs review went without a clean pass.", INCONCLUSIVE),
    ("Independent review: pass. The docs reviewer refused to say it passed.", INCONCLUSIVE),
    ("Independent review: pass. The docs reviewer declined to say it passed.", INCONCLUSIVE),
    ("Independent review: pass. The docs review is unlikely to pass.", INCONCLUSIVE),
    ("Independent review: pass. The docs review pass is pending.", INCONCLUSIVE),
    ("Independent review: pass. Docs review pass awaiting sign-off.", INCONCLUSIVE),
    ("Independent review: pass. We await the docs review pass.", INCONCLUSIVE),
    ("Independent review: pass. The docs review will pass.", INCONCLUSIVE),
    ("Independent review: pass. The docs review would pass.", INCONCLUSIVE),
    ("Independent review: pass. The docs review should pass.", INCONCLUSIVE),
    ("Independent review: pass. The docs review must pass.", INCONCLUSIVE),
    ("Independent review: pass. The docs review could pass.", INCONCLUSIVE),
    ("Independent review: pass. I haven't seen the docs review pass.", INCONCLUSIVE),
    ("Independent review: pass. Docs review ❌ — pass.", INCONCLUSIVE),
    ("Independent review: pass. A docs review pass is still required.", INCONCLUSIVE),
    ("Independent review: pass. A docs review pass is still needed.", INCONCLUSIVE),
)

ARENA_NATURALS = (
    "Candidate 2 — the base — with retries grafted from candidate 3.", "Base: candidate 2 (cache-first); grafted retry logic from candidate 3.",
    "| Base | Candidate 2 |\n| Grafts | retry logic from candidate 3 |", "Candidate 4 (the lazy-cache design) is the base - grafts from candidate 1.",
    "Candidate 2 was selected (not candidate 1) and grafts came from 3.", "Base = candidate 2 | Grafts = retries (candidate 3)",
    "Selected candidate 2 over candidate 1; retry logic grafted from 3.", "Winner: candidate 2 (selected) — grafts: retries from 3.",
    "Base | candidate 2 | grafts | retries (candidate 3)", "Candidate 2 (chosen) as base; retries grafted from candidate 3.",
    "Candidate 2 is the base (see rationale.md); retries grafted from candidate 3.", "Candidate 2 was chosen, with retry grafts from candidate 3.",
    "Base - candidate 2 - with grafts from candidate 3", "Chose candidate 2 as the base | graft: candidate 3 retries",
    "Candidate #2 is the base; grafted retries from candidate #3.", "Candidate 1 is the base; retries were grafted from candidate 3.",
    "Candidate 2 was selected, and the retry logic was grafted from candidate 3.",
)

ARENA_NEGATED = (
    "Candidate 1 was not selected — grafts from candidate 3.", "No candidate was selected; retries were grafted from candidate 3.",
    "I did not pick candidate 2 as the base; grafted retries from candidate 3.", "There is no base — grafted retries from candidate 3.",
    "(Not the base) candidate 2; grafts retries from candidate 3.", "| Candidate 2 | not selected | grafts: retries |", "Base: none; grafts from candidate 3.",
    "Base — none; grafts from candidate 3.", "Base (none): retries grafted from candidate 3.", "Base: n/a | Grafts: retries from candidate 3",
    "No base | grafts: retries from candidate 3", "No clear base - candidate 2 and 3 tied; retries grafted from candidate 3.",
    "Without a base, retries were grafted from candidate 3.", "Never picked a base; grafted retries from 3.", "Candidate 2 is not the base; retries grafted from candidate 3.",
    "Candidate 2 wasn't selected; retries grafted from candidate 3.", "Candidate 2 (not chosen) — grafts: retries from candidate 3",
    "It was not the case that candidate 1 was selected; retries were grafted from candidate 3.", "Nobody picked candidate 2, retries were grafted from candidate 3.",
    "No candidate 1 was selected and retries were grafted from candidate 3.", "Based on the judge, retries were grafted from candidate 3.",
    "The database layer was grafted from candidate 3.",
)

LOOP_NATURALS = (
    "tmux new -s ssh-watch 'while true; do sleep 60; done'", "ssh tmux.internal 'while true; do sleep 60; done'",
    "nohup sh -c 'while true; do ./check.sh; sleep 60; done' >loop.log 2>&1 &", "ssh devbox 'while true; do ./check.sh; sleep 60; done'",
    "tmux send-keys -t loop 'while true; do ./check.sh; sleep 60; done' Enter", "tmux new-session -d -s watch 'while true; do ./check.sh; sleep 60; done'",
    'sh -c "until [ -f /tmp/done ]; do sleep 10; done"', "docker exec ci bash -lc 'while :; do ./check.sh; sleep 60; done'",
    "for i in $(seq 1 20); do ./check.sh; sleep 30; done", "tmux send-keys -t w 'until test -f done; do sleep 5; done' C-m",
    "tmux new -d 'while true; do ./check.sh; sleep 60; done'", "screen -dmS w bash -c 'while true; do ./check.sh; sleep 60; done'",
    'nohup bash -c "while true; do ./check.sh; sleep 60; done" > /dev/null 2>&1 &', 'ssh -o ConnectTimeout=5 devbox "cd /srv && while true; do ./check.sh; sleep 60; done"',
    "bash -lc 'while :; do ./check.sh; sleep 60; done'", "sh -c 'while [ ! -f /tmp/done ]; do sleep 5; done'", "while true; do ./check.sh; sleep 30; done &",
    "watch -n 60 ./check.sh", "timeout 3600 bash -c 'until curl -sf localhost:8000; do sleep 5; done'",
    "systemd-run --user bash -c 'while true; do ./check.sh; sleep 60; done'", "kubectl exec pod -- sh -c 'while true; do ./check.sh; sleep 60; done'",
    "sudo -u ci sh -c 'while true; do ./check.sh; sleep 60; done'", "setsid nohup sh -c 'while true; do ./check.sh; sleep 60; done' &",
    'env FOO=1 sh -c "until ./ready.sh; do sleep 5; done"', "eval 'while true; do ./check.sh; sleep 60; done'", 'python3 -c "import time\nwhile True: time.sleep(5)"',
    "ssh host 'bash -s' <<'EOF'\nwhile true; do ./check.sh; sleep 60; done\nEOF", "until curl -sf localhost:8000; do sleep 5; done",
    "bash <<'EOF'\nwhile true; do ./check.sh; sleep 60; done\nEOF", "python3 - <<'EOF'\nimport time\nwhile True:\n    time.sleep(60)\nEOF",
    "ssh -q -T -A -o BatchMode=yes -o ConnectTimeout=5 -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o ControlMaster=no devbox 'while true; do ./poll.sh; sleep 30; done'",
    "tmux new-session -d -s poll -n main -x 200 -y 50 -c /srv -e A=1 -e B=2 -e C=3 -e D=4 -e E=5 'while true; do ./poll.sh; sleep 30; done'",
)

LOOP_NEGATED = (
    "echo 'while true; do sleep 5; done' > notes.txt", "grep -n 'while true' check.sh", "cat <<'EOF' > loop.sh\nwhile true; do ./check.sh; sleep 60; done\nEOF",
    "git commit -m 'wrap while true loop'", "sed -n '1,20p' watch.sh # while true; do sleep 5; done", "python3 -m http.server & sleep 2; curl localhost:8000",
)

WHY_LABELS = (
    ("Why investigator (git): the cap came in 12d7ece.", "Why investigator (issues): ticket 41."),
    ("Investigator — source control: history shows 12d7ece.", "Investigator — issue tracker: ticket 41."),
    ("Investigator - source control: 12d7ece.", "Investigator - issue tracker: #41."), ("Investigator (git history): 12d7ece.", "Investigator (tickets): #41."),
    ("Investigator 1: 12d7ece.", "Investigator 2: #41."), ("**Investigator 1**: 12d7ece.", "**Investigator 2**: #41."),
    ("### Investigator: source control\n12d7ece", "### Investigator: issues\n#41"), ("Investigator #1 (git): 12d7ece.", "Investigator #2 (issues): #41."),
    ("Source-control investigator: 12d7ece.", "Issue-tracker investigator: #41."), ("Why investigator — git: 12d7ece.", "Why investigator — tickets: #41."),
    ("Investigator – git: 12d7ece.", "Investigator – tickets: #41."), ("[Investigator: git] 12d7ece.", "[Investigator: tickets] #41."),
    ("Investigator: git history.", "Investigator: tickets."), ("Source control: 12d7ece.", "Issue/ticket: #41."),
    ("Git history investigator report: 12d7ece.", "Issue investigator report: #41."),
)

HOW_LABELS = (
    ("Explorer 1 — parser: reading the tokenizer.", "Explorer 2 — emitter: reading the sink.", "Explorer 3 — cli: reading the entry."),
    ("Explorer 1 - parser: tracing.", "Explorer 2 - emitter: tracing.", "Explorer 3 - cli: tracing."),
    ("Explorer (parser): tracing.", "Explorer (emitter): tracing.", "Explorer (cli): tracing."),
    ("Explorer #1: tracing.", "Explorer #2: tracing.", "Explorer #3: tracing."), ("**Explorer 1**: tracing.", "**Explorer 2**: tracing.", "**Explorer 3**: tracing."),
    ("Explorer 1 – parser: tracing.", "Explorer 2 – emitter: tracing.", "Explorer 3 – cli: tracing."), ("Explorer: tracing.", "Explorer: tracing.", "Explorer: tracing."),
    ("## Explorer 1 — parser\ntracing", "## Explorer 2 — emitter\ntracing", "## Explorer 3 — cli\ntracing"),
    ("Exploration angle 1: parser: tracing.", "Exploration angle 2: emitter: tracing.", "Exploration angle 3: cli: tracing."),
    ("Explorer 2 (parser): tracing.", "Explorer 3 (emitter): tracing.", "Explorer 4 (cli): tracing."), ("Explorer A: tracing.", "Explorer B: tracing.", "Explorer C: tracing."),
    ("Explorer 1 of 3: tracing.", "Explorer 2 of 3: tracing.", "Explorer 3 of 3: tracing."),
    ("Explorer: tracing publish.", "Explorer: tracing ingest.", "Explorer: tracing render."),
)

SEALED_EXPLORER_LABELS = ("Explorer-1: parser", "Explorer 1/3: parser", "Explorer agent: parser", "Explorer 1 -- parser: found it", "Explorer, angle 1: found it",
                          "Explorer II: found it", "Explorer for the parser: found it")
SEALED_NOT_EXPLORER_LABELS = ("Explorer notes: found it", "Explorer findings: found it", "Explorer, findings: found it", "Explorer — notes: found it",
                              "Explorer - summary: found it")

STATUS_AFTER = (["cd /w/relay-wt/candidate-1"], ["cd ../relay-wt/candidate-2"], ["pushd /w/relay-wt/candidate-1 >/dev/null"])

FAILED_CD_INTO_A_SHARED_DIR = (["cd /w/relay-wt/candidate-1"], ["pushd /w/relay-wt/candidate-1"], ["cd /w/relay-wt/candidate-1 && pytest"])


def sealed_explorers(label):
    spawns = [sealed_reply(10, label.replace("1", str(n)), f"t{n}") for n in (1, 2, 3)]
    events = sealed_calls(spawns)
    events.insert(3, text(20, "All back."))
    return grade("how-fans-out-explorers-for-big-subsystem", minimal(events=events, spawns=spawns, harness="codex"), load_case("how-wide-run"))["verdict"]


def judged(judge, lead, models):
    spawns = [{"seq": 10 + n, "tool": "Agent", "model": m, "prompt_head": "Candidate design"} for n, m in enumerate(models)]
    spawns.append({"seq": 30, "tool": "Agent", "model": judge, "prompt_head": "READ-ONLY. You are the judge scoring candidates against the rubric."})
    trace = minimal(events=[{"seq": s["seq"], "kind": "tool_call", "name": "Agent", "input": {}} for s in spawns], spawns=spawns)
    trace["model"] = lead
    return grade("arena-readonly-cross-judge", trace, load_case("arena-run"))["verdict"]


def lead_reads(brief, commands):
    spawns = [{"seq": s, "tool": "Agent", "prompt_head": brief} for s in range(1, 6)] + [{"seq": 9, "tool": "Agent", "prompt_head": "You are the read-only cross-judge."}]
    events = [{"seq": s["seq"], "kind": "tool_call", "name": "Agent", "input": {"prompt": brief}} for s in spawns]
    events += [e for i, c in enumerate(commands) for e in bash(20 + 2 * i, c)]
    return grade("arena-lead-reads-rationales-and-base", minimal(events=events, spawns=spawns), load_case("arena-run"))["verdict"]


def own_worktrees():
    candidates = [{"seq": 43, "tool": "Agent", "prompt_head": "Design one candidate."} for _ in range(3)]
    events = bash(40, "git worktree add /w/.worktrees/candidate-1; git worktree add /w/.worktrees/candidate-2; git worktree add /w/.worktrees/candidate-3")
    events += [{"seq": 43, "kind": "tool_call", "name": "Agent", "input": {"prompt": f"Design in /w/.worktrees/candidate-{n}"}} for n in (1, 2, 3)]
    events += bash(45, "git status --short", head="")
    return grade("arena-candidates-own-worktrees", minimal(events=events, spawns=candidates), load_case("arena-run"))["verdict"]


def worklist_right_after_the_read():
    events = ([read(1, "poteto-mode/playbooks/feature.md"), read(2, "unslop/SKILL.md"), {"seq": 3, "kind": "tool_result", "name": "Read", "ok": True, "output_head": "### Feature"},
               {"seq": 4, "kind": "tool_result", "name": "Read", "ok": True, "output_head": "name: unslop"}] + bash(6, "ls") + bash(8, "cat tally/__main__.py") + [text(5, "Worklist")])
    case = load_case("feature-run")
    case["env"] = {"todo_tools": False}
    trace = minimal(events=events, worklist=[{"seq": 5, "carrier": "text", "items": feature_items()}])
    return grade("worklist-falls-back-to-numbered-list", trace, case)["verdict"]


def author_result_in_a_done_todo():
    todo = {"seq": 2, "kind": "tool_call", "name": "TodoWrite", "input": {"todos": [{"content": "Record Result: independent review required", "status": "completed"}]}}
    events = (in_turn(0, [{"seq": 0, "kind": "user", "text": "add --json"}, read(1, "documentation-impact/SKILL.md"), todo, text(50, "Done.")])
              + in_turn(1, [{"seq": 60, "kind": "user", "text": "review"}, text(61, "x")]))
    return grade("poteto-runs-documentation-impact-before-completion", minimal(events=events, final_reply="x"), load_case("doc-impact-run"))["verdict"]


def tdd(rerun):
    with tempfile.TemporaryDirectory() as tmp:
        project = make_repo(tmp, 1, {"rollup/__main__.py": "x = 0\n"})
        events = ([{"seq": 8, "kind": "tool_call", "name": "Write", "input": {"file_path": f"{project}/tests/test_main.py", "content": "x"}}]
                  + bash(10, "python3 -m unittest tests.test_main", ok=False, head="FAIL: test_limit\nFAILED (failures=1)")
                  + [{"seq": 12, "kind": "tool_call", "name": "Edit", "input": {"file_path": f"{project}/rollup/__main__.py"}}] + rerun)
        return grade("poteto-tdd-failing-test-first", minimal(events=events), load_case("tdd-run"), project)["verdict"]


def swarm():
    events = [{"seq": 8 + 2 * n, "kind": "tool_call", "name": "Agent", "input": {"description": "Check", "prompt": f"Run check for packages/{p} only."}}
              for n, p in enumerate(("ingest", "shape", "render", "publish"))]
    spawns = [{"seq": e["seq"], "tool": "Agent", "prompt_head": e["input"]["prompt"]} for e in events]
    return grade("swarm-fans-out-and-aggregates", minimal(events=events, spawns=spawns, final_reply="One report."), load_case("swarm-run"))["verdict"]


def cannot_run(recovered):
    events = bash(10, "python3 -m rollup data/orders.csv /tmp/out.csv", ok=False, head="ModuleNotFoundError: No module named 'rollup'")
    if recovered:
        events += bash(20, "python3 -m rollup data/orders.csv /tmp/out.csv", head="wrote 3 rows")
    return grade("reply-says-inconclusive-when-check-cannot-run", minimal(events=events, final_reply="Fixed and verified."), load_case("bug-fix-run"))["verdict"]


def how_wide_explorers():
    spawns = [sealed_reply(10, "Explorer: tracing publish.", "a"), sealed_reply(10, "Explorer: tracing ingest.", "b"), sealed_reply(10, "Explorer: tracing render.", "c"),
              sealed_reply(30, "Architectural explanation: synthesizing the three traces.", "d")]
    events = sealed_calls(spawns)
    events.insert(3, text(20, "All back."))
    return grade("how-fans-out-explorers-for-big-subsystem", minimal(events=events, spawns=spawns, harness="codex"), load_case("how-wide-run"))["verdict"]


def why_investigators():
    spawns = [{"seq": 10, "tool": "Agent", "prompt_head": f"Investigator for {c}: look in {c} for the history of the retry cap."}
              for c in ("source control", "issue tracker tickets", "long-form documents", "real-time chat")]
    events = [{"seq": 10, "kind": "tool_call", "name": "Agent", "input": {}} for _ in spawns]
    return grade("why-queries-evidence-categories-in-parallel", minimal(events=events, spawns=spawns), load_case("why-run"))["verdict"]


def reply_oracle(pid, case, reply, events=()):
    return grade(pid, minimal(events=list(events), final_reply=reply), load_case(case))["verdict"]


RATIONALES = "Write `rationale.md` in your directory."
OTHER_NATURALS = (
    ("three explorers then an explainer", how_wide_explorers, PASS),
    ("four investigators in one message", why_investigators, PASS),
    ("Sources: line", lambda: reply_oracle("how-why-reports-name-sources-searched", "why-run",
                                           "The cap was raised in commit 12d7ece.\n\nSources: git log, README, open issues."), PASS),
    ("Sources searched heading", lambda: reply_oracle("how-why-reports-name-sources-searched", "why-run",
                                                      "Retry cap came from commit 12d7ece.\n\n**Sources searched**: git history, docs."), PASS),
    ("judge on another model", lambda: judged("gpt-6.1-sol", "claude-opus-5-5", ["opus", "sonnet"]), PASS),
    ("five rationales and the base", lambda: lead_reads(RATIONALES, [f"cat /tmp/k/c{n}/rationale.md" for n in range(1, 6)] + ["cat /tmp/k/c1/relay/cache.py"]), PASS),
    ("rationales read in a loop", lambda: lead_reads(RATIONALES, ['for x in a:1 b:2 c:3 d:4 e:5; do id=${x%%:*}; cat "/tmp/k/$id/rationale.md"; done',
                                                                 "cat /tmp/k/c1/relay/cache.py"]), PASS),
    ("git worktree add per candidate", own_worktrees, PASS),
    ("numbered list right after the playbook read", worklist_right_after_the_read, PASS),
    ("author result in a completed todo", author_result_in_a_done_todo, PASS),
    ("Monitor tool", lambda: grade("autonomous-run-uses-loop-facility", minimal(events=[{"seq": 1, "kind": "tool_call", "name": "Monitor", "input": {}}] + bash(3, "ls")),
                                   load_case("overnight-run"))["verdict"], PASS),
    ("reply asks for approve", lambda: reply_oracle("architect-checkpoint-opt-in", "architect-checkpoint-run",
                                                    "Design A is in docs/design.md. Reply “approve” to implement it."), PASS),
    ("waiting for sign-off", lambda: reply_oracle("architect-checkpoint-opt-in", "architect-checkpoint-run",
                                                  "The sketch is saved. I am waiting for your sign-off before implementing."), PASS),
    ("red then green OK", lambda: tdd(bash(14, "python3 -m unittest tests.test_main", head="Ran 1 test\n\nOK")), PASS),
    ("red then verbose ok", lambda: tdd(bash(14, "python3 -m unittest -v tests.test_main", head="test_limit (tests.test_main.T) ... ok")), PASS),
    ("packages named in the brief", swarm, PASS),
    ("unrunnable check reported as verified", lambda: cannot_run(False), FAIL),
    ("unrunnable check recovered by a rerun", lambda: cannot_run(True), INCONCLUSIVE),
    ("artifact run after the write", lambda: grade("prove-it-works-checks-real-artifact",
                                                   minimal(events=[{"seq": 2, "kind": "tool_call", "name": "Edit", "input": {"file_path": "/w/rollup/export.py"}}]
                                                           + bash(5, "python3 -m rollup data/orders.csv /tmp/out.csv")), load_case("bug-fix-run"))["verdict"], PASS),
)


class NaturalCorpus(unittest.TestCase):
    def assert_rows(self, grade_row, rows):
        for row, expected in rows:
            with self.subTest(row=row):
                self.assertEqual(grade_row(row), expected)

    def assert_never_pass(self, grade_row, rows):
        for row in rows:
            with self.subTest(row=row):
                self.assertNotEqual(grade_row(row), PASS)

    def test_correct_review_verdicts_pass_or_go_to_a_judge(self):
        self.assert_rows(review_block, REVIEW_BLOCK_NATURALS)
        self.assert_rows(review, REVIEW_LINE_NATURALS)

    def test_negated_hedged_or_off_topic_review_verdicts_never_pass(self):
        self.assertNotIn(PASS, {expected for _, expected in REVIEW_BLOCK_NEGATED + REVIEW_LINE_NEGATED})
        self.assert_rows(review_block, REVIEW_BLOCK_NEGATED)
        self.assert_rows(review, REVIEW_LINE_NEGATED)

    def test_correct_arena_picks_pass_and_negated_picks_never_do(self):
        self.assert_rows(arena_pick, [(line, PASS) for line in ARENA_NATURALS])
        self.assert_never_pass(arena_pick, ARENA_NEGATED)

    def test_correct_loops_pass_and_quoted_or_commented_loops_never_do(self):
        self.assert_rows(loop_verdict, [(command, PASS) for command in LOOP_NATURALS])
        self.assert_never_pass(loop_verdict, LOOP_NEGATED)

    def test_correct_role_labels_and_candidate_statuses_pass(self):
        self.assert_rows(lambda pair: why_labels(*pair), [(pair, PASS) for pair in WHY_LABELS])
        self.assert_rows(lambda trio: how_labels(*trio), [(trio, PASS) for trio in HOW_LABELS])
        self.assert_rows(status_after, [(commands, PASS) for commands in STATUS_AFTER])
        self.assert_rows(sealed_explorers, [(label, PASS) for label in SEALED_EXPLORER_LABELS])

    def test_a_sealed_reply_that_names_explorer_output_is_no_explorer_label(self):
        self.assert_rows(sealed_explorers, [(label, FAIL) for label in SEALED_NOT_EXPLORER_LABELS])

    def test_candidates_sharing_one_directory_fail_even_after_a_failed_cd(self):
        self.assert_rows(lambda commands: status_after(commands, failing=set(commands), out="/tmp/arena/shared/"),
                         [(commands, FAIL) for commands in FAILED_CD_INTO_A_SHARED_DIR])

    def test_other_correct_lead_outputs_keep_their_verdicts(self):
        for name, run, expected in OTHER_NATURALS:
            with self.subTest(row=name):
                self.assertEqual(run(), expected)


if __name__ == "__main__":
    unittest.main()
