## Review: `sessions-list-host-filter`

Small, well-scoped change. It reads like it was always part of the list endpoint. My notes:

**Store.** The `host_id` branch copies the `project` filter's two paths exactly: an IN subquery when metadata shares the conversations engine, and a prefetch bounded by `qualifying_ids` when it doesn't. That's the right precedent, and scoping `host_stmt` to `current_workspace_id()` is correct. The split-DB path has no test of its own, but neither does the project filter's, so I won't block on it.

**Vocabulary.** The route, client, and API.md talk about sessions, while the store docstring and `test_list_conversations_filters_by_host_id` talk about conversations. That's the repo's existing layering (`/v1/sessions` over `ConversationStore`, `parent_session_id` on the wire stored as `parent_conversation_id`), and the new code follows it on each side. I wouldn't rename anything here. `host_id` is the same name the list item, the metadata column, and `set_host_id` already use.

**Behaviour to know about.** A malformed `host_id` reaches the `Uuid16` bind and comes back as the app-wide 404 "Not found." That's a little odd for a list filter, but it's how a bad `agent_id` already behaves, so it's consistent. Maybe mention it in API.md.

**Index.** `omnigent_conversation_metadata` has indexes for `runner_id` and `project_id` but not `host_id`. With a single-DB IN subquery this becomes a scan of the workspace's metadata rows. That's fine today, but worth a follow-up migration if the web UI starts calling it on every host page.

**Tests.** The store test's rebind case is a nice touch: it proves the filter reads the current binding, not the first one. The route test asserts both the ids and the echoed `host_id`, which is what I'd want.

**Follow-up idea, not for this PR.** The resume picker filters `host_id` client-side, but it deliberately keeps unbound rows, so it can't switch to this filter as is.

LGTM.
