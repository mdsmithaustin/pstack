## Review: `sessions-list-tag-filter`

The mechanics are solid. The store filter reuses the `pinned` shape (an IN-subquery on `conversation_labels`, colocated on the AP DB), so it composes with the ACL pushdown and cursor pagination without extra round trips. Tests cover exact value, any value, and the 400s. One thing blocks merge for me, plus a few small notes.

**Blocking: this is a label filter, so please call it `label`, not `tag`.** Everything this PR filters on is what the codebase already calls a label. The table is `conversation_labels` / `SqlConversationLabel`. The create and PATCH bodies take `labels`. Every `SessionListItem` returns `labels`. The client exposes `Session.labels`. `pinned` is a label join. The new docstrings even say "tags are stored as conversation labels" and "the key/value pairs set through `labels`". With this PR a client writes `labels={"team": "infra"}` and then reads them back with `?tag=team:infra`: two names for one concept on the same public API, and `tag` becomes a word every future reader has to map back to labels. Please rename it throughout: `?label=team:infra` on the route, `label_key` / `label_value` on `list_conversations`, `label=` on `SessionsNamespace.list`, `_parse_label_filter`, and describe it in API.md as a label filter. Don't keep `tag` as an alias; nothing has shipped yet, so there are no callers to migrate.

Smaller things:

- `_parse_tag_filter` splits on the first `:`, so a key containing a colon can't be matched with a value. That's probably fine, but say it in the docstring.
- The pin-key guard is a good call. Consider refusing the other server-owned keys (`omni_project`, `omnigent.side_chat`) too, or at least note why only pins are refused.
- The route test's any-value case depends on `order=asc` to get a stable order. A set comparison would be less brittle.
- No index covers `(workspace_id, key, value)` on `conversation_labels`. That's fine at today's sizes, but worth a follow-up if the sidebar starts using this.

Happy to approve once the rename lands.
