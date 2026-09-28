## Related issue

Closes #8219

## Summary

- `GET /v1/sessions?host_id=<id>` returns only the sessions whose runner was launched on that host, the same `host_id` each list item already reports. Sessions with no host binding are excluded. It combines with visibility, project, archive, and cursor parameters.
- `ConversationStore.list_conversations` gains `host_id`. The binding lives on the metadata row, so the SQLAlchemy store resolves it the way the `project` filter resolves membership: an IN subquery on a single database, a prefetch bounded by the permission scope on a split one.
- `SessionsNamespace.list(host_id=...)` exposes it in the Python client.

Before retiring or reinstalling a host you want to see what was running on it; today that means listing every session and checking `host_id` on each row.

## Test Plan

```
OMNIGENT_SKIP_WEB_UI=true uv sync --frozen --group test
.venv/bin/python -m pytest -q tests/server/routes/test_sessions_crud.py \
  tests/frontends/sdk/test_sessions_namespace.py tests/stores/test_conversation_store.py
```

New tests: the store filter (including a rebind that moves a session between hosts and an unbound session that never matches), the route returning only the host's sessions, and the client sending `host_id`.

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

`GET /v1/sessions?host_id=...` and `SessionsNamespace.list(host_id=...)` list only the sessions launched on one host
