---
name: how
description: "Use for \"how does X work\", code walkthroughs before changing something, and placement / ownership / layering questions (\"where should this live\", \"which package owns this\", \"is this the right layer\"). Explains subsystem architecture, runtime flow, onboarding mental models. Use why for motivation."
---

# How

Explore the codebase to answer "how does X work?" questions. Produce architectural explanations at the level of a senior engineer onboarding onto a subsystem, enough to build a working mental model, not so much that it reads like annotated source code.

## Step 1. Assess Complexity

If the scope is ambiguous, state your interpretation and explore. The user can redirect.

- **Simple** (a single module, a small utility, a narrow question such as "how does function X work"): no explorers. One explainer explores and explains in a single pass. Go to Step 2b.
- **Complex** (a subsystem spanning multiple files or services, a cross-cutting feature, a full architectural overview): spawn parallel explorers first, then hand off to the explainer. Go to Step 2a.

When in doubt, take the simple path.

If the repo has a GitNexus index (`.gitnexus/` exists), refresh it first — run `gitnexus analyze --index-only` once yourself before spawning anything (it is incremental and a no-op when up to date; never run it from parallel arms). Then seed exploration: `gitnexus query "<concept>"` for execution flows, `gitnexus context <symbol>` for callers/callees, `gitnexus trace <from> <to>` for the path between two symbols. Graph results choose where to read; the code itself remains the source of truth — the index reflects the last analyzed commit and never sees uncommitted edits. No index? Explore normally; after answering a complex question, you may suggest `gitnexus analyze` to the user once for repos worth exploring again.

## Step 2a. Explore (complex questions only)

Decompose the question into 2 to 4 exploration angles, each a distinct slice of the subsystem. Spawn per this CLI (in short: native subagent tool → your own CLI as a subprocess → sequential arms, same count; unconfirmed model = inherit-parent); full mapping in the **pstack-harness** skill. Spawn all explorers in a single message:

- `subagent_type`: `general-purpose`
- `model`: your configured how-explorer model (default `sonnet`), with its configured effort per the **pstack-harness** skill
- `readonly`: `true`

Each explorer gets the prompt in `references/explorer-prompt.md` with its angle filled in. Then go to Step 3.

## Step 2b. Direct Explain (simple questions)

Spawn one Task subagent that explores and explains in one pass:

- `subagent_type`: `general-purpose`
- `model`: your configured how-explainer model (default `fable`), with its configured effort per the **pstack-harness** skill
- `readonly`: `true`

Build its prompt from `references/explainer-prompt.md` without the explorer-findings section. Go to Step 4.

## Step 3. Synthesize (complex questions only)

Once all explorers have returned, spawn one Task subagent to synthesize their findings into one explanation:

- `subagent_type`: `general-purpose`
- `model`: your configured how-explainer model (default `fable`), with its configured effort per the **pstack-harness** skill
- `readonly`: `true`

Build its prompt from `references/explainer-prompt.md` with every explorer's findings filled in.

## Step 4. Present

Present the explainer's output to the user. Light edits for clarity or context from the conversation are fine. Do not substantially rewrite it.

## Output Format

The explanation uses the sections defined in `references/explainer-prompt.md`, dropping any that do not apply: Overview, Key Concepts, How It Works, Where Things Live, Gotchas.
