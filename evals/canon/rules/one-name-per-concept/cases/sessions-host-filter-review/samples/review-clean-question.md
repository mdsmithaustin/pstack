## Review: `sessions-list-host-filter`

Nice change, and the tests are good. A few comments, only one of them a question:

1. **Store query.** Reusing the `project` filter's single-DB / split-DB split is the right call. `host_stmt` is workspace-scoped, and the split-DB prefetch is bounded by `qualifying_ids` the same way the membership prefetch is. No concerns.

2. **Question on wording.** The docs on the route and client say "sessions whose runner was launched on this host", and the store says "conversations whose `metadata.host_id` is this host". I know the store layer has always been conversation-flavoured. Is that a deliberate boundary we document somewhere, or just history? It doesn't need to change in this PR. I'm asking so I know whether new store code should keep following it.

3. **Missing index.** There's no `(workspace_id, host_id)` index on `omnigent_conversation_metadata`, unlike `runner_id` and `project_id`. That's probably fine at current sizes.

4. **Bad ids.** `?host_id=not-a-host` returns the generic 404 from the `Uuid16` bind. A list endpoint answering "not found" is a little surprising. A 400, or an empty page, would read better, but it matches `agent_id`, so it's fine to leave.

5. **Tests.** I like the rebind assertion in `test_list_conversations_filters_by_host_id`. In the route test, maybe also assert that the unbound session is absent by id rather than relying on the list equality. The equality already covers it, so this is optional.

6. **Client.** The `host_id` docstring on `SessionsNamespace.list` is clear, and "``None`` returns sessions on any host or none" is precise.

Approve.
