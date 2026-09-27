## Review: `billing-set-monthly-limit`

Good feature overall; the screen reuses the existing gate, and `_billing_mutate` is a sensible generalization of the auto-reload wrapper.

### Duplicate validator

`validate_monthly_limit` is `validate_charge_amount` copy-pasted with the minimum dropped and the error strings reworded. Same `parse_money` call, same `<= 0` check, same `quantize(Decimal("0.01"))` cent check, same upper-bound check, same `AmountValidation` return. That's two copies of the money-input rules that will drift the first time someone fixes one of them.

Please merge them: either call `validate_charge_amount(raw, min_usd=None, max_usd=cap.ceiling_usd)` from the limit screen, or extract a shared `_validate_usd_amount(raw, *, min_usd, max_usd, noun="Amount")` in `billing_view.py` that both use, with the noun feeding the error copy. Then the parametrized rejection tests can cover both entry points with one table.

### Other notes

- Setting a limit below this month's spend goes straight to the PUT. Auto-reload has an agree modal; a confirm here would be consistent.
- `put_monthly_cap` sends a float, consistent with the other billing writes.
- `test_cli_billing_limit.py`'s `_Host` stub is tidy.
- The TUI overlay should get the same action soon so the surfaces don't diverge.

Requesting changes for the validator duplication.
