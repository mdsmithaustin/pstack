# Grading guide: accounts login throttle (positive)

## Flaw location

`omnigent/server/auth.py`, lines 384-528 after the PR: the `_LOGIN_*` constants, `LoginThrottleConfig`, `_env_non_negative_int`, `resolve_login_throttle_config`, `_LoginFailures`, and `LoginThrottle`.

## The flaw

The file grows past about 1,000 lines by taking on a new responsibility.

`auth.py` is 906 lines on main. Its docstring says what it is for: "User identity extraction from incoming requests." The PR adds 148 lines to it and it ends at 1,054 lines. Almost all of the new code is a failed-login budget: per-username failure counting, lockout, eviction of old entries, and parsing of three env vars. The only caller is the login route in `omnigent/server/routes/accounts_auth.py`. The budget shares no state with `UnifiedAuthProvider` or with anything else in `auth.py`. It would stand on its own as a module. The server package already keeps small single-purpose modules beside `auth.py`, such as `passwords.py` (79 lines), `accounts_secret.py` (86 lines), and `accounts_config.py` (154 lines).

The fix is to extract it. Move the constants, `LoginThrottleConfig`, the env parsing, and `LoginThrottle` into their own module, for example `omnigent/server/login_throttle.py`, and import that from `accounts_auth.py` (Move Function, Extract Class). `auth.py` then stays at 906 lines. Another placement that keeps `auth.py` under about 1,000 lines also counts, such as putting the config next to `accounts_config.py` and the counter in a new module. So does decomposing some other part of `auth.py` first so that the file stays under about 1,000 lines after the PR, when the review ties that to the crossing.

## Grading

- FOUND. The review names `auth.py`, or the throttle code in it. It says what is wrong. Either the PR pushes `auth.py` past about 1,000 lines or makes it too large (a line count, "over 1k", "too long", "too big"), or the throttle is a separate job that does not belong in a module about identity extraction. It asks for the throttle to move into a module of its own, or for another decomposition that keeps `auth.py` under about 1,000 lines. Either reason is enough. A review that asks for the move on cohesion alone and never mentions size is FOUND. The ask may be blocking or a clear request for this PR.
- PARTIAL. Any one of these:
  - The review notes that `auth.py` crosses 1,000 lines, is getting long, or mixes jobs, but asks for no extraction in this PR. Calling it fine for now, a nit, or a follow-up while approving counts here.
  - The review's fix keeps the throttle in `auth.py`, such as a section comment, a nested class, or shorter docstrings.
- MISSED. The review says nothing about where the throttle lives or about the size of `auth.py`.

## Comments that count neither way

- The state is in memory and per process, so several replicas multiply the budget. Suggestions to keep it in the database or Redis.
- Keying on the username lets anyone lock out a known user for 15 minutes. Suggestions to key on username and IP, use growing delays, or add a CAPTCHA.
- The 10,000-entry cap and its eviction order, or memory use under a username spray.
- The web login form or `omnigent login` not showing a friendly message for 429.
- The `OMNIGENT_LOGIN_*` env vars missing from the docs, or their names.
- `retry_after` rounding, `window_seconds=0`, or the choice of a monotonic clock.
- The 429 path skipping argon2, so it answers faster than a 401.
- Test style, such as the list-based clock, the minimal FastAPI app in the route test, or not reusing the `accounts_app` fixture.
- The mix of older helpers already in `auth.py` (`SharingMode`, `workspace_sharing_blocked`, the env helpers) raised on its own, with no link to this PR's growth or to the throttle.
