---
name: how
description: "Use for \"how does X work\", code walkthroughs before changing something, and placement / ownership / layering questions (\"where should this live\", \"which package owns this\", \"is this the right layer\"). Explains subsystem architecture, runtime flow, onboarding mental models. Use why for motivation."
---

# How

Explore the codebase to answer "how does X work?" questions.

If the scope is ambiguous, state your interpretation and explore. The user can redirect.

If the repo has a GitNexus index (`.gitnexus/` exists) and `gitnexus` is on `PATH`, run `gitnexus analyze --index-only` once yourself before spawning. It is incremental and a no-op when up to date. Never run it from parallel arms.

## 1. Explain

Spawn one read-only `general-purpose` subagent on the `how explainer` line in the pstack models config (default `opus`) that explores and explains in one pass. Call the Skill tool with `pstack-harness` to resolve its model, effort, and agent type. Its **Spawn a role** section also covers a missing config, `inherit-parent`, and a rejected value. Give it the user's question and this brief:

> You are writing an architectural explanation for a senior engineer. Explore the codebase and write an explanation that a senior engineer unfamiliar with this area could read and walk away with a solid mental model. They should understand the architecture well enough to start working in it confidently. You have read-only access to the codebase. If `.gitnexus/` exists and `gitnexus` is on `PATH`, seed your search with `gitnexus query "<concept>"`, `gitnexus context <symbol>`, and `gitnexus trace <from> <to>`, then verify in the code, because the index never sees uncommitted edits. Never run `gitnexus analyze`.

## 2. Present

Present the subagent's output. Light edits for clarity or context from the conversation are fine. Do not substantially rewrite it.
