# Track a worklist

**Track a worklist.** The worklist is an ordered collection of items with `pending`, `in progress`, `completed`, or `skipped: <reason>` state. State the complete initial list before starting, keep at most one item in progress, and update it when an item changes state or the list changes.

Choose its carrier by capability, never by a remembered product-specific name:

1. Inspect the tools and channels already exposed in the live session. Prefer a native structured capability whose description says it creates or updates task, plan, or work-item state.
2. If the harness supports deferred capability discovery, make one semantic query for a capability that tracks ordered multi-step work and item status. Do not query product-specific names.
3. If structured tracking is available, use it. If discovery finds none or any call is rejected, stop trying that carrier for the rest of the task. Publish and maintain the same worklist through the harness's normal progress-update channel. Both are native carriers of the same contract. On that channel, post the worklist as a numbered list with each item's state, and re-post it when an item changes state or the list changes.

Do not create a scratch task file solely because structured tracking is unavailable. A durable file is appropriate only when the workflow must resume across sessions; use that workflow's named state or decision-trail artifact. Ordinary capability variation needs no warning, apology, or "fallback" announcement. Report the current worklist, not the plumbing that carries it.
