Added an `ip_address` category to the PII guardrail in `omnigent/policies/builtins/safety.py`.

- A new IPv4 pattern in `_PII_CATEGORY_PATTERNS` (each octet 0 to 255) and the label "IP Address (IPv4)" in `_PII_CATEGORY_LABELS`.
- `ip_address` added to the `pii_types` enum and default in `POLICY_REGISTRY`, so admins can pick it in the policy settings and it is on by default.
- Two tests in `tests/policies/builtins/test_safety_pii.py`, and the category list in `docs/POLICIES.md`.

`tests/policies/builtins/test_safety_pii.py` passes (29 passed).

To try it by hand, add "Deny PII in LLM Requests" to an agent, tick only "IP Address (IPv4)", and send "the db is at 10.20.30.40". The message is denied with "PII detected (IP Address (IPv4))".
