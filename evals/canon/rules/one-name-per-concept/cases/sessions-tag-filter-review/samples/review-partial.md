## Review: `sessions-list-tag-filter`

Nice, focused change. The store filter follows the `pinned` pattern (an inline IN-subquery against `conversation_labels`), which keeps it cheap and lets it combine with visibility, project, and cursor paging. Tests cover the store, the route, and the client. Comments:

1. **Terminology.** The `tag` filter here is really matching the same thing the codebase stores as labels: the table is `conversation_labels`, and sessions are created with a `labels` map. A caller reading the API docs could reasonably wonder whether tags are a separate feature. I'd add a sentence to API.md and to the `SessionsNamespace.list` docstring that spells it out, e.g. "tags are the session's labels; any label set at create time or via PATCH can be filtered here", so nobody goes looking for a separate endpoint to create tags.

2. `_parse_tag_filter` uses `partition(":")`, so a key with a colon in it can't be combined with a value. Worth a docstring note, or reject such keys explicitly.

3. The pin-key rejection is a good catch, since the per-user pin keys are hidden on read. Should `omni_project` be refused too, given `?project=` already covers it with the dual read?

4. Only one filter value is supported. If multiple values show up later (`?tag=a:1&tag=b:2`), `list[str] = Query(default=[])` would be the natural shape. Not needed for this PR.

5. Minor: the route test's any-value assertion relies on `order=asc`. Comparing sets would be sturdier.

6. No index covers key/value lookups on `conversation_labels`. That's fine for now, but keep an eye on it if the web sidebar starts using this.

Looks good to me after the docs clarification.
