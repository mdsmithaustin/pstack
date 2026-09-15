# Export permission observation

The gateway replayed the same `POST /exports` request twice from a clean start.
Both runs returned a file containing account email addresses. The gateway log
does not say whether the caller was the public report client or the compliance
console. No caller-to-gateway route map or authorization policy is available.

The investigation is diagnostic-only. The reviewer may inspect this note, but
must not alter files, permissions, policy, or application state.
