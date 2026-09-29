## Review: `accounts-login-throttle`

Nice, small, well-tested feature. Keying on the normalized username rather than the IP is the right call behind a proxy, and counting unknown usernames the same way keeps a 429 from leaking which accounts exist. Running the check before `verify_password` means a locked name costs no argon2 work.

### Notes

1. **Targeted lockout.** Anyone who knows a username can keep it locked by sending five bad passwords every 15 minutes. For a self-hosted default that's probably acceptable, but consider keying on username plus client IP, or growing delays instead of a hard lock.
2. **Replicas.** The PR body already says it: N replicas give N times the budget. Fine as a first cut; a database-backed counter can come later.
3. **Eviction.** `_drop_oldest` scans from the oldest entry for an unlocked one, which is linear once the table fills with locked names. Unlikely to matter at 10,000.
4. **File growth.** With this, `omnigent/server/auth.py` goes from 906 to 1,054 lines, past the usual 1k mark. Not worth blocking a self-contained addition like this over. Something to keep an eye on later.
5. **Docs.** `OMNIGENT_LOGIN_MAX_FAILURES` and the other two vars should go in the deploy docs.
6. **Tests.** The route test builds a minimal app instead of reusing `accounts_app`. That's fine, and faster.
7. **Web UI.** The login form shows its generic error for a 429. A follow-up could read `Retry-After` and say how long to wait.

Approve.
