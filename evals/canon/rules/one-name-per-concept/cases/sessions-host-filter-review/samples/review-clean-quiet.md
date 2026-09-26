## Review: `sessions-list-host-filter`

Read through all eight files. Good change, a few notes:

**Correctness.** The new branch in `list_conversations` is placed after the `pinned` filter and before the cursor is applied, so pagination sees the filtered set. Good. `host_stmt` is scoped to `current_workspace_id()`, and in the split-DB path it's intersected with `qualifying_ids` when a permission scope is active, so the IN list can't balloon to every session in the workspace.

**Error handling.** A malformed id (`?host_id=abc`) fails in the `Uuid16` bind and surfaces as the app's generic 404. Not ideal for a filter, but it's consistent with the existing `agent_id` filter. If you want to be friendlier, validate with `uuid_to_bytes` in the route and return 400. Optional.

**Performance.** There's no index on `host_id` in the metadata table (`runner_id` and `project_id` both have one). For a CLI or occasional UI use that's fine. If this ends up behind a host detail page that polls, add the index.

**Tests.**
- Store: covers match, rebind, and unbound. 
- Route: covers the filter and checks the echoed `host_id`.
- Client: checks the query parameter. Maybe also assert it's absent when `host_id=None`, like the visibility tests do for the other optional params.

**Docs.** The API.md paragraph mentions `omnigent run` sessions having no host, which is exactly the case people will trip over. Good.

Approve with the optional nits above.
