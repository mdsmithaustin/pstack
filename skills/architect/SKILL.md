---
name: architect
description: "Sketch types, signatures, and module structure before code, then stay in the loop while implementation fills in. Use for /architect, 'architect this', 'design this', or non-trivial work where jumping to code would lock in the wrong shape."
---

# Architect

Before writing code, trace every system the change touches, then sketch two different shapes for it (types, signatures, module boundaries) and pick the one where each piece of state has one owner, each task has one way to do it, and callers need to know least. Record the criterion that decided the pick. Build first the piece that could invalidate the rest. Call the Skill tool with `principle-sequence-verifiable-units`. Redesign instead of patching if workarounds repeat.

For a large or contested design, call the Skill tool with `arena` instead of sketching alone. Start implementing, yourself or through a delegate, only after arena returns its synthesized design.
