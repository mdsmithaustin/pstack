## Review: `accounts-login-throttle`

Good addition. Until now only argon2's cost slowed down guessing against `/auth/login`.

### Correctness

- The budget check runs before `login_snapshot` and the verify, so a locked username costs nothing. Good.
- Unknown usernames call `record_failure` too, so a 429 does not confirm that an account exists. Good.
- `record_success` runs only after the generation checks pass, so a login that later returns 401 for a stale generation doesn't clear the count. Correct.
- `retry_after` rounds up with `math.ceil`, so the header never says 0 while the lock is still on.

### Concerns

- Keying only on the username lets an attacker keep a known admin locked out by retrying every 15 minutes. I'd at least log a warning when a lock starts, with the redacted name, so operators can see it happening.
- The table is per process. With two replicas the budget is ten attempts, not five. Worth a line in the docs.
- A negative `OMNIGENT_LOGIN_MAX_FAILURES` silently falls back to 5. Failing loud at startup, the way `AccountsConfig.from_env` does, would be more consistent.

### Tests

- `test_login_refuses_a_locked_username_even_with_the_right_password` pins the key contract.
- `Retry-After` is asserted as a range, which is fine given the real clock in the route test.

Approve with the logging suggestion.
