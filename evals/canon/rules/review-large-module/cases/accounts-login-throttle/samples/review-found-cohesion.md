## Review: `accounts-login-throttle`

Good addition. Nothing slows password guessing against `/auth/login` today, and checking the budget before `verify_password` means a locked name costs no argon2 work. Counting unknown usernames the same way keeps a 429 from revealing which accounts exist, and the injected clock keeps the lockout and expiry tests deterministic.

### Warning: the throttle doesn't belong in `auth.py`

`omnigent/server/auth.py` is about working out who a request is. Its docstring says "User identity extraction from incoming requests", and everything in it serves `UnifiedAuthProvider`. `LoginThrottleConfig`, `resolve_login_throttle_config`, `_env_non_negative_int`, and `LoginThrottle` are a different job, a failed-login budget with its own env parsing and eviction. Its only caller is the login route in `routes/accounts_auth.py`, and it shares no state with anything else in `auth.py`.

Please move it into its own module, for example `omnigent/server/login_throttle.py` beside `passwords.py` and `accounts_config.py`, and import it from `accounts_auth.py` (Move Function, Extract Class). The login route then reads its dependencies from files named for what they do.

### Smaller things

- `nit`: keying on the username lets anyone lock a known user out for 15 minutes. Reasonable for self-hosting, but say so in the docs, which don't list the `OMNIGENT_LOGIN_*` vars yet.
- `nit`: the web login form shows its generic error for a 429. Reading `Retry-After` would let it say how long to wait.
- The per-process caveat in the PR body is honest. Fine for a first cut.

Request changes for the module move.
