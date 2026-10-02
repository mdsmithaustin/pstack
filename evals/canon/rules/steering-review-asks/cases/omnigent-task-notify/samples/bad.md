Claude task notifications are now hidden context.

**Fix.** `claude_native_bridge.py` marks a `role=user` record as `is_meta` when its text is a task notification carrying `<task-notification>`, `<task-id>`, `<tool-use-id>`, `<status>`, and the closing tag. `itemsToBlocks.ts` hides stored rows that match the same markers.

**Verification.** Bridge and web tests cover a completed sub-agent notification.
