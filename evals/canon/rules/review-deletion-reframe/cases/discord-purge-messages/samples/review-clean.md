## Review: `discord-purge-messages`

Useful action, and the shape is right: one GET, one bulk POST, and Discord's limits handled where they apply instead of coming back to the model as 400s.

### The size branches in `_purge_messages`

I checked whether `if len(ids) == 1` could fold into the bulk call. It can't. Bulk-delete takes 2 to 100 ids and answers 400 (50016) for one, so a single deletable message has to use the per-message DELETE. That path is reachable with any `limit`, because the 14-day filter can leave one recent message among old ones, and `test_one_recent_message_among_old_ones_uses_the_per_message_delete` covers it. The empty guard is there for the same reason. Keep both.

### Other notes

- A message that turns 14 days old between the GET and the POST fails the whole batch with 50034. A minute of margin on `_BULK_DELETE_MAX_AGE_SECONDS` avoids that.
- The one-id path could call `_delete_message(token=token, channel_id=channel_id, message_id=ids[0])` instead of building the DELETE inline, so the path template lives in one place. Optional.
- Consider sending `X-Audit-Log-Reason` so moderators can see the purge came from the bot.
- `delete_message` is still missing from the `server_actions` comment you edited.
- The tests assert the exact requests with `call_args_list`, which is the right level here since the request shape is the behavior.

Approve.
