---
name: principle-model-the-domain
description: "Apply when writing stateful logic, or when code branches a lot or repeats a shape assumption across files."
---

# Model the Domain

Encode the real domain in a data structure instead of scattering it across conditionals. The right structure makes invalid states unrepresentable and deletes branches.

Reach for a state machine instead of scattered booleans or phase checks, a typed model instead of loose parameters, a map, registry, or discriminated union instead of branching spread across files, a reducer instead of ad hoc mutations, and an index, queue, or normalized collection where the access pattern calls for it.

**Use the domain's words.** Name types, functions, and modules with the domain's words. Before you name anything, read the nearest glossary if one exists, such as a `CONTEXT.md`, use its terms, and never use a word it marks as one to avoid. Name an operation by its effect in the domain, not by its mechanism.

Do not force it. Keep boring code when the shape is clear, local, and unlikely to grow, and distrust an abstraction that adds indirection without removing branches or invalid states.

The sign that you skipped this: a feature that grows an if/else chain by one more branch, or a second boolean that must stay in sync with the first.

**In review.** When you review someone else's change, also check these three.

- **One name per concept.** Flag a new name for a concept the code already names. Suggest keeping the code's word.
- **Separate contexts.** Flag a change that combines one word's different concepts, from two parts of the codebase, into one type whose fields are optional per meaning. Suggest a type in each part that shares only what means the same in both, such as an id.
- **Shared code answers to every caller.** List the callers of each shared function, type, or constant the change touches. Flag a change made for one request that alters behavior for a caller serving a different business function. Suggest forking the shared piece and changing only the requester's path. Look-alike code that different business functions change is two decisions, so do not ask to merge it.
