# Track a worklist

**Track a worklist.** The worklist is an ordered collection of items with `pending`, `in progress`, `completed`, or `skipped: <reason>` state. State the complete initial list before starting, keep at most one item in progress, and update it when an item changes state or the list changes.

Choose its carrier by capability, never by a remembered product-specific name:

1. Inspect the tools and channels already exposed in the live session. Prefer a native structured capability whose description says it creates or updates task, plan, or work-item state. Goal lifecycle tools are not work tracking unless the user explicitly asked to create a goal.
2. If the harness supports deferred capability discovery, make one semantic query for a capability that tracks ordered multi-step work and item status. Do not query product-specific names. Tools can arrive deferred under tool search. When task or plan tools are off, setup-pstack step 0b names the switch.
3. If structured tracking is available, use it. If discovery finds none or any call is rejected, stop trying that carrier for the rest of the task. Publish and maintain the same worklist through the harness's normal progress-update channel, using commentary when that channel exists. Both are native carriers of the same contract. On that channel, post the worklist as a numbered list with each item's state, and re-post it when an item changes state or the list changes.

Do not create a scratch task file solely because structured tracking is unavailable. A durable file is appropriate only when the workflow must resume across sessions; use that workflow's named state or decision-trail artifact. Ordinary capability variation needs no warning, apology, or "fallback" announcement. Report the current worklist, not the plumbing that carries it.

## Report-later promises

Add each promise to report a later result as a `pending` worklist item when you make it. Keep the promised result, its trigger, and delivery status in that item. A ready result is still pending until you relay it. If a result arrives during an open question, retain it and relay it once the question resolves. Mark the item `completed` after delivery, without delivering it twice.

A pending report prevents ending the session unless an actual scheduled wake-up owns it. Record the scheduler's job or receipt, the wake-up trigger, and where it will recover the promise and deliver the result. Use the [loop procedure](loops.md) to create the wake-up. A proposed schedule, manual next tick, or promise to check later is not ownership. If the next action needs the user or an operator-reserved gate, report that block and preserve the pending item through pause, interruption, and pickup.
