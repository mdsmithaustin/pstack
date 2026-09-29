## Review: `discord-purge-messages`

Read the action, the manifest entry, and the tests. Looks good.

**Behavior.** One GET for the newest `limit` messages, then one delete request. Messages older than 14 days are reported instead of failing the batch. The result shape (`deleted`, `skipped_older_than_14_days`) gives the model enough to explain what happened.

**Permissions.** `purge_messages` is registered as an admin action, and the 403 hint names MANAGE_MESSAGES. Good. Consider an `X-Audit-Log-Reason` header so server moderators can see who purged.

**Edge cases.**
- A message crossing the 14-day line between the GET and the POST fails the whole batch. A minute of margin on the cutoff would avoid it.
- A `limit` above 100 is capped by `_limit_param`, same as `fetch_messages`.
- Pinned messages get purged too. That's probably what a moderator wants, but it might deserve a word in the description.

**Tests.** Good coverage of recent, old, mixed, and empty cases. `_message` builds timestamps relative to now, so the tests won't rot.

**Docs.** The `server_actions` comment now lists `purge_messages` but still misses `delete_message`.

Approve.
