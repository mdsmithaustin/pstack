## Review: `sessions-list-tag-filter`

I read the three layers and the tests. This is a clean change. Notes in order of importance:

**Store query.** Filtering with `SqlConversation.id.in_(select(...conversation_id))` is the right call. It mirrors the `pinned` branch, stays on the AP database, and composes with the ACL pushdown and the cursor. I checked that the subquery is scoped to `current_workspace_id()`, which is easy to forget. Good.

**Parsing.** `_parse_tag_filter` splits on the first `:`, so `a:b:c` becomes key `a`, value `b:c`. That's a reasonable choice, but put it in the docstring and in API.md so callers with colon-bearing keys know what to expect. An empty value (`team:`) currently means "value is the empty string", which differs from `team` (any value). That's subtle. Either test it or reject it.

**Security.** Rejecting `omnigent.pinned.*` keys matters, because list items collapse other users' pins, so the filter would otherwise leak them. Please also add a test that a request whose tag is the caller's own per-user pin key gets a 400, not just someone else's, to pin down the prefix check.

**API shape.** Only one filter per request. That's fine for a first cut, but if multiple values are likely soon, switching now to `list[str] = Query(default=[])` with AND semantics saves a compatibility dance later.

**Tests.** Good coverage at all three layers. Two nits:
- `test_list_sessions_filtered_by_tag` depends on `order=asc` to get a stable list. Use a set.
- The client test could also assert that `tag` is omitted when it's `None`.

**Docs.** The API.md paragraph is clear.

Approve with nits.
