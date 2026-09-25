## Review: `billing-set-monthly-limit`

Read through the screen, the client call, and the tests. This is in good shape.

### Flow

- Gating matches the rest of `/topup`: `_billing_require_admin` with its own kill-switch copy, then the non-interactive fallback, then the modal. Good.
- Showing the ceiling in the prompt (`New monthly limit (up to $1000):`) is a nice touch.
- Allowing a limit below current spend with only a dim note feels a little quiet. Auto-reload asks the user to agree before the PATCH; I'd mirror that here, since a limit under this month's spend blocks every charge until the month resets.

### `_billing_mutate`

Good generalization. One thing: the `amount=None` branch in `_billing_handle_scope_required` prints "Run /topup to continue", which is right for both callers, so no change needed.

### Client

`put_monthly_cap` sends `limitUsd` as a JSON number, consistent with `patch_auto_top_up`. The test pins method, URL and body; that's all it needs.

### Tests

- `test_limit_above_the_ceiling_is_refused_before_any_request` is exactly the right invariant.
- The owner payload fixture now includes `ceilingUsd`; consider one parse test where it's absent to pin the `None` default.

### Docs

`website/docs/developer-guide/billing-lifecycle.md` still says the monthly cap is managed on the portal. Worth a line once the TUI catches up.

Approve, with the confirm step as a suggestion.
