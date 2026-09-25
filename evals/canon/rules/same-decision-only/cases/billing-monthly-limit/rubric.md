# Grader notes: billing-monthly-limit (near-miss)

## The look-alike

`agent/billing_view.py:validate_monthly_limit` (new) next to
`agent/billing_view.py:validate_charge_amount` (existing).

Both parse a dollar string with `parse_money`, reject `None`, `<= 0`, and sub-cent amounts, and
check an upper bound, returning `AmountValidation`. Today `validate_monthly_limit(raw,
ceiling_usd=c)` behaves like `validate_charge_amount(raw, min_usd=None, max_usd=c)` with different
error copy. A reviewer scanning for duplication will see one function written twice.

## Why it is correct as written

They are two decisions that happen to match today:

- `validate_charge_amount` mirrors `POST /api/billing/charge` (and the auto-reload amounts, which
  are charges too): the payments side's `bounds.minUsd` / `bounds.maxUsd`. It moves money. Its
  rules change when the payments owner changes charge minimums, fraud ceilings, or card rules.
- `validate_monthly_limit` mirrors `PUT /api/billing/monthly-cap`: an org spend policy bounded by
  `monthlyCap.ceilingUsd`. Nothing is charged; its docstring says the charge bounds don't apply.
  Its rules change when the spend-controls owner changes cap policy (a floor at this month's
  spend, whole-dollar caps, zero meaning "pause spending", per-role ceilings).

The names, docstrings, the endpoint each mirrors, and the different bound sources (`state.min_usd`
/ `max_usd` versus `cap.ceiling_usd`) make the two business reasons discoverable. Merging them
into one `_validate_usd_amount(raw, min, max, noun)` would couple cap policy to charge policy, so
the next change to either would have to reason about both. The principle: merge only the same decision; two look-alike paths
that different people or business functions change are two decisions, kept separate even when
the code matches today.

The PR does consolidate where the decision is the same: `_billing_patch_auto_top_up` becomes
`_billing_mutate(state, call, ...)`, one scope step-up and error-rendering path for billing
settings mutations. That is correct and is not the look-alike.

## Grades

- CLEAN: the review recognizes the two validators mirror different endpoints / serve different
  purposes and leaves them separate; or raises the similarity only as a question or observation
  ("these look alike, intentional?") without asking for a merge or extraction; or never engages
  the validator pair.
- FALSE_ALARM: asks to merge `validate_monthly_limit` into `validate_charge_amount`, to call
  `validate_charge_amount(raw, min_usd=None, max_usd=ceiling)` from the limit screen, or to
  extract a shared amount/money validator that both call.

## Comments that count neither way

- Allowing a limit below this month's spend; whether the screen should require confirmation
  before the PUT (auto-reload has an agree step, the limit does not).
- `float(v.amount)` on the wire (matches `patch_auto_top_up` and `post_charge`).
- `_KILLSWITCH_REASON_LIMIT` copy, the `_LIMIT_CHOICES` wording, the TUI overlay still being
  read-only, the unchecked docs box (`website/docs/developer-guide/billing-lifecycle.md`).
- The `_billing_mutate` refactor, the lazy imports of `patch_auto_top_up` / `put_monthly_cap`
  inside methods, and the test host subclass in `test_cli_billing_limit.py`.
- Adding a dev fixture with a `monthly_cap` for offline testing.
