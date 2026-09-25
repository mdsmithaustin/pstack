## Related issue

Closes #8214

## Summary

- `GET /v1/sessions` accepts `?tag=key:value` (exact value) or `?tag=key` (any value) and returns only the sessions carrying that tag. It composes with the existing visibility, project, archive, and cursor parameters.
- `ConversationStore.list_conversations` gains `tag_key` / `tag_value`. The SQLAlchemy store filters with an IN-subquery on `conversation_labels`, the same shape as the `pinned` filter, so there is no extra round trip and no schema change.
- `SessionsNamespace.list(tag=...)` passes the filter through the Python client.
- Per-user pin keys (`omnigent.pinned.*`) are rejected with a 400 so the filter cannot be used to see which sessions another user pinned; `pinned=true` already covers your own.

Today the only way to find, say, every `team:infra` session from a script is to page through the whole list and filter client-side.

## Test Plan

```
OMNIGENT_SKIP_WEB_UI=true uv sync --frozen --group test
.venv/bin/python -m pytest -q tests/server/routes/test_sessions_crud.py \
  tests/frontends/sdk/test_sessions_namespace.py tests/stores/test_conversation_store.py
```

New tests: exact and any-value matching at the store and the route, 400s for an empty key and for pin keys, and the client sending `tag` on the wire.

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

`GET /v1/sessions?tag=team:infra` and `SessionsNamespace.list(tag="team:infra")` list only the sessions with that tag
