Claude task notifications are now hidden context.

**Fix.** `claude_native_bridge.py` marks a `role=user` transcript record whose text is a `<task-notification>` payload as `is_meta`, so it persists for resume and never renders or seeds a title. It requires only the opening tag, `<task-id>`, and the closing tag, since `<tool-use-id>`, `<status>`, and the rest are optional (a Monitor event carries none of them). `itemsToBlocks.ts` applies the same guard to stored rows that predate the flag, so no migration is needed.

**Verification.** Bridge and web tests cover a full Task notification and a Monitor notification with the optional tags omitted.
