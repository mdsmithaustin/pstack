The PII categories were spelled out four times in `omnigent/policies/builtins/safety.py`: the pattern dict, the label dict, and the `pii_types` enum and default in `POLICY_REGISTRY`. So I did this in two steps.

1. Restructure, no behavior change. Each category is now one `_PiiCategory(label, pattern)` entry in `_PII_CATEGORIES`, and the registry's `pii_types` enum and default are `list(_PII_CATEGORIES)`. The registry entry serializes to the same JSON as before, and `tests/policies/builtins/test_safety_pii.py` and `tests/policies/test_registry.py` pass unchanged (45 passed).
2. Feature. `ip_address` is one new entry, "IP Address (IPv4)", matching dotted quads with each octet 0 to 255. It shows up in the policy settings checklist and is on by default like the other categories. I added two tests and updated `docs/POLICIES.md`. 47 passed.

To try it by hand, add "Deny PII in LLM Requests" to an agent, tick only "IP Address (IPv4)", and send "the db is at 10.20.30.40". The message is denied with "PII detected (IP Address (IPv4))".

I left both steps uncommitted. Commit the restructure first and the feature on top of it.
