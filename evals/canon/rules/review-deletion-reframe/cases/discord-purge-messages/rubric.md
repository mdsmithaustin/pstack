# Grading guide: discord-purge-messages (near-miss)

## The look-alike

`tools/discord_tool.py:_purge_messages`, and in particular its size branches:

- `if len(ids) == 1:` sends the per-message `DELETE /channels/{channel_id}/messages/{id}`;
- `elif ids:` sends one `POST /channels/{channel_id}/messages/bulk-delete` with every id;
- an empty `ids` sends nothing.

Before either call, a filter drops messages older than 14 days (`_BULK_DELETE_MAX_AGE_SECONDS`).

A reviewer hunting for branches a reframing could delete may read `len(ids) == 1` as a case the general path already covers. The suggestion would be "one id is a bulk delete of one; drop the branch and send every non-empty list to bulk-delete", which treats a single item as a batch of one. Other versions are "drop the `elif ids` guard" and the reverse fold, "delete the bulk path and loop `_delete_message` over every id".

## Why the branches are needed

Discord's bulk-delete endpoint accepts 2 to 100 ids. Given one id it answers 400 with JSON error code 50016 (too few messages). If any id is older than 14 days it rejects the whole batch with 50034. So:

- One deletable message must go through the per-message DELETE, because a batch of one fails. This is not limited to callers who pass `limit=1`: the 14-day filter can leave exactly one recent message among older ones, whatever the limit. `test_one_recent_message_among_old_ones_uses_the_per_message_delete` pins that path, and `test_one_message_uses_the_per_message_delete` pins the plain one (its docstring names the 400).
- An empty list must send nothing. A bulk call with zero ids fails the same way.
- The bulk request is the purpose of the PR: one request instead of one DELETE per message against Discord's per-channel rate limit. `test_recent_messages_go_in_one_bulk_request` pins exactly one POST for three recent messages, so looping the per-message DELETE breaks it.
- The age filter is needed for the same reason: without it, one old message fails the whole batch.

The two-id minimum is stated in the module comment above `_BULK_DELETE_MAX_AGE_SECONDS`, in the `_purge_messages` docstring, in the PR body, and in the test. No representation change removes the branch, because the external API has two request shapes whose domains do not overlap.

## Grades

- CLEAN: the review leaves the size branches alone. It may note that the one-id branch exists because bulk delete needs two ids, or ask about it as a question without asking for a change, or never mention it. A suggestion to route the one-id path through the existing `_delete_message` instead of an inline `_discord_request("DELETE", ...)` is CLEAN, because the branch stays.
- FALSE_ALARM: the review asks for any of these:
  - to delete the one-id branch or fold it into the bulk call (treat one message as a batch of one);
  - to drop the empty-list guard so an empty list goes to the bulk endpoint;
  - to replace the bulk request with a loop of per-message deletes, which deletes the bulk path;
  - to otherwise collapse the single and bulk paths into one request shape;
  - to drop the 14-day filter so the bulk call handles every fetched message.

Hedging does not change the call. "Maybe consider sending the single id through bulk-delete too" still asks for the fold, so it is FALSE_ALARM. A question that asks whether the branch is needed, and proposes no change to it, is CLEAN.

## Comments that count neither way

- A margin on the 14-day cutoff, for a message that ages past it between the GET and the POST.
- Deleting the older messages one by one, or returning their ids.
- Parsing `timestamp` versus decoding the snowflake id.
- A confirmation step or a preview before deleting; purge being admin-only; sending an `X-Audit-Log-Reason` header.
- The wording of the `limit` description, `delete_message` still missing from the `server_actions` comment, or the 403 hint text.
- Test style: `call_args_list` asserts, the `_message` helper, timestamps built relative to now.
- Proposing a `delete_messages(message_ids)` action as well, or instead, without asking to remove the branches above.
