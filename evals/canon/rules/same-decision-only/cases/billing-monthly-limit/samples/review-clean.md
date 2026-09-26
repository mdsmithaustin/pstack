## Review: `billing-set-monthly-limit`

Solid change. The screen follows the same gate and step-up path as Add funds and Auto-reload, and the scripted-host test in `test_cli_billing_limit.py` actually drives the screen instead of poking internals.

### Validation

`validate_monthly_limit` sits right under `validate_charge_amount` and the bodies read almost line for line the same. I looked at routing the limit through `validate_charge_amount` with `min_usd=None`, and I'd keep them apart. The charge validator mirrors `POST /charge` and the payments bounds; the limit validator mirrors `PUT /monthly-cap` and the org's `ceilingUsd`. Those are owned and changed by different people: the next charge-side change is a Stripe minimum or a fraud cap, the next cap-side change is something like "zero pauses spending" or a floor at this month's spend. Sharing one function would make each of those edits reason about the other. Same numbers today, different decisions.

`_billing_mutate` on the other hand is a good consolidation: one scope step-up and error path for every billing settings write is the same decision in two places, and folding it is right.

### Other notes

- Setting a limit below `spent_this_month_usd` only prints a dim note and then sends the PUT. Auto-reload asks for an explicit agree step; lowering a limit under current spend blocks every further charge for the month, so a confirm modal here seems worth it.
- `float(v.amount)` on the wire matches `patch_auto_top_up` / `post_charge`, fine.
- The PR body says docs are unchecked. `website/docs/developer-guide/billing-lifecycle.md` still documents the limit as portal-only for the TUI; a line noting the CLI can now change it would help.
- A dev fixture with a `monthly_cap` (and `ceiling_usd`) would make the screen testable offline with `HERMES_DEV_BILLING_FIXTURE`.

Approve with the confirm-step suggestion as optional.
