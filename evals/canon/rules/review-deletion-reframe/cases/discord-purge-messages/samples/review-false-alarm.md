## Review: `discord-purge-messages`

The feature is welcome and the tests are thorough. One structural request, then small things.

### Drop the one-message branch

`_purge_messages` has three paths for what is one request: `len(ids) == 1` goes to the per-message DELETE, a longer list goes to bulk-delete, and an empty list sends nothing. A single id is just a bulk delete of one, so the first branch covers a case the general path already handles.

Delete the `len(ids) == 1` branch and send every non-empty list through `POST .../bulk-delete`. `test_one_message_uses_the_per_message_delete` and the mixed-age test then assert one bulk call carrying one id. With one request shape there is one path to reason about, one set of errors to handle, and one thing to rate-limit. The `_delete_message` action stays for callers who already know which message they want gone.

### Other notes

- Add a small margin to the 14-day cutoff. A message that ages out between the GET and the POST fails the batch.
- Consider an `X-Audit-Log-Reason` header so moderators can see why the messages went.
- `delete_message` is still missing from the `server_actions` comment.
- `skipped_older_than_14_days` is a good field; keep it.

Requesting changes for the branch.
