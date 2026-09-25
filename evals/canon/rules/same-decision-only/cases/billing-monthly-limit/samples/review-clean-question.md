## Review: `billing-set-monthly-limit`

Nice feature, and the `_billing_mutate` generalization reads well: auto-reload and the limit now share the scope step-up and the error renderer.

### Question on the new validator

`validate_monthly_limit` looks very close to `validate_charge_amount`: same parse, same `<= 0` and sub-cent checks, an upper bound, same `AmountValidation` result. Is the similarity intentional? I can see the endpoints differ (`/monthly-cap` vs `/charge`) and the bound comes from `ceilingUsd` rather than the charge bounds, so there may be a reason to keep them distinct. A sentence in the PR description about how you see the two evolving would help the next reader. Not blocking.

### Other notes

- Lowering the limit below this month's spend goes straight to the PUT after a dim note. I'd add a confirm step like auto-reload's agree modal, since it stops all charges for the rest of the month.
- `test_admin_lowers_the_monthly_limit` checks the PUT kwargs and the success line; nice and behavioral.
- `_KILLSWITCH_REASON_LIMIT` reads fine.
- The TUI overlay follow-up is noted in the body; worth an issue so it doesn't drift.
- `billing-lifecycle.md` still describes the limit as read-only.

Looks good to merge after the confirm step.
