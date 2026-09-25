## Review: `sessions-list-host-filter`

The feature itself is straightforward and the query is fine. My main concern is naming.

**Two names for one concept.** This PR calls the same thing a session in the route, client, and docs, and a conversation in the store: "only return conversations whose runner was launched on this host", `test_list_conversations_filters_by_host_id`, `conv_store` in the route test. A reader has to know they're the same object. New code shouldn't add to that. Please rename the new store docstrings and the test to say sessions, e.g. `test_list_sessions_filters_by_host_id`, and describe the parameter as "only return sessions launched on this host", so the host filter uses one word from API to storage. If we're touching `list_conversations` anyway, it's a good moment to start consolidating on session rather than conversation for anything user-visible.

**Index.** No index on `host_id` in `omnigent_conversation_metadata`. `runner_id` and `project_id` both have one. Please add a migration, or at least a follow-up issue.

**Errors.** A bad id returns a generic 404 from the `Uuid16` bind. For a filter parameter I'd expect a 400. Please validate in the route.

**Tests.** The rebind case is good. The split-DB branch is untested, so consider parametrizing the store fixture over a split engine.

**Docs.** The API.md paragraph is good.

Requesting changes for the naming; the rest are suggestions.
