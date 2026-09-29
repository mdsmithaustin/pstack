## Review: `accounts-login-throttle`

Worth having. Nothing slows down password guessing against `/auth/login` today, and checking the budget before the argon2 verify is the right order: a locked name costs no hashing. Counting unknown usernames too means a 429 can't be used to enumerate accounts. The tests cover lockout, expiry, the window reset, and the route, and the injected clock keeps them deterministic.

### Warning: the throttle takes `auth.py` past 1,000 lines

`omnigent/server/auth.py` goes from 906 to 1,054 lines in this PR, and almost all of the 148 new lines are a separate job. `auth.py` extracts identity from requests. `LoginThrottleConfig`, `resolve_login_throttle_config`, `_env_non_negative_int`, and `LoginThrottle` are a failed-login budget with one caller, the login route in `routes/accounts_auth.py`, and they share nothing with `UnifiedAuthProvider`. That's the Large Class smell: the file crosses the 1k mark by absorbing a new responsibility.

Please move it into its own module, for example `omnigent/server/login_throttle.py` next to `passwords.py` and `accounts_config.py` (Move Function, Extract Class), and import it from `accounts_auth.py`. `auth.py` stays at 906 lines and the throttle gets a home a reader can find.

### Smaller things

- `nit`: keying on the username means anyone can lock a known user out for 15 minutes. That's a reasonable default for self-hosting, but say so in the docs next to the new `OMNIGENT_LOGIN_*` vars, which aren't documented yet.
- `nit`: the web login form shows its generic error for a 429. Reading `Retry-After` and saying "try again in N minutes" would help.
- The per-process caveat in the PR body is honest. Fine for a first cut.

Request changes for the module move. The rest is optional.
