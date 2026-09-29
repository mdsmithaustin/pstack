## Related issue

Closes #8231

## Summary

- `POST /auth/login` now refuses a username with `429` and a `Retry-After` header after 5 failed password attempts within 15 minutes, for 15 minutes. The check runs before the argon2 verify, so a locked username costs no hashing.
- The budget is keyed on the normalized username, not the client IP, so rotating IPs or sitting behind a proxy does not reset it. Unknown usernames are counted the same way, so a `429` does not reveal whether an account exists. A successful login clears the count.
- `LoginThrottle` and `LoginThrottleConfig` sit in `omnigent/server/auth.py` beside the other auth env settings. `OMNIGENT_LOGIN_MAX_FAILURES` (`0` turns it off), `OMNIGENT_LOGIN_FAILURE_WINDOW_SECONDS`, and `OMNIGENT_LOGIN_LOCKOUT_SECONDS` configure it. `create_accounts_auth_router` builds one from the env, or takes one for tests.

Accounts mode is the default for containerized deploys, and today nothing slows down password guessing against `/auth/login` except argon2's cost. Counts are per process: with several replicas the budget multiplies by the replica count, which still bounds guessing to a handful of tries per window.

## Test Plan

```
OMNIGENT_SKIP_WEB_UI=true uv sync --frozen --group test
.venv/bin/python -m pytest -q tests/server/test_login_throttle.py tests/server/test_accounts.py
```

New tests: lockout and expiry against an injected clock, failures outside the window not adding up, success clearing the count, env parsing with bad values, and the route refusing a locked username even with the right password, including an unknown username.

## Demo

- [ ] Visual demo attached below
- [x] Non-visual evidence provided below or in Test Plan
- [ ] Not applicable — no behavioral change

## Type of change

- [ ] Bug fix
- [x] Feature
- [ ] UI / frontend change
- [ ] Refactor / chore
- [ ] Docs
- [ ] Test / CI
- [ ] Breaking change

## Test coverage

- [x] Unit tests added / updated
- [x] Integration tests added / updated
- [ ] E2E tests added / updated
- [ ] Manual verification completed
- [ ] Existing tests cover this change
- [ ] Not applicable

## Coverage notes

## Changelog

Repeated failed password logins for one username are refused with `429` for 15 minutes (configurable with `OMNIGENT_LOGIN_*`)
