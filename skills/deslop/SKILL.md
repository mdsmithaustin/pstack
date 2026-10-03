---
name: deslop
description: "Remove AI slop from the code a branch changed, before a commit and without changing behavior: narrating comments, guards on states the types or the boundary already rule out, dead compatibility paths, unrelated edits, one-caller wrappers and speculative abstractions, casts that silence the type checker, and nesting an early return flattens. Use for /deslop, deslop it, clean the diff, strip the slop, or before any commit. Code only. The unslop skill cleans prose and the no-comments skill reviews comments."
---

# Deslop

Clean AI slop out of the code a branch changed, and leave behavior unchanged. Use it before every commit, and on `/deslop`, "deslop it", "clean the diff", or "strip the slop". It cleans code only. The **unslop** skill owns prose, and the **no-comments** skill owns the comment review.

## Scope

Use the caller's files or diff. Otherwise diff against the base branch, default `main`, including the working tree, and read only the hunks the branch added or changed. Fix slop inside those hunks. Slop you notice elsewhere goes in the report and stays untouched.

## Process

1. Read the diff hunk by hunk and name the task each hunk serves. A hunk that serves none is rule 17.
2. Apply the rules below in order. Make the smallest edit. Delete before you rewrite.
3. Stop at a cut that needs a new shape, such as a type, a helper, or a state model. Flag it for the [Refactoring playbook](../poteto-mode/playbooks/refactoring.md). Deslop never adds abstraction to remove slop.
4. Prove behavior unchanged on the real artifact. Run the tests the diff touches and the type check. A test that must change to pass means behavior changed. Revert that cut.
5. Hand what remains to the neighbors. Comments the rules below do not settle go to `/no-comments`. Names, messages, and kept comments go to `/unslop`.
6. Report in the format below.

## Rules

Rule numbers are stable ids that other skills cite. A removed rule leaves a gap. Each rule names the target, its tell, and the fix.

### Comments

1. **Narrating comments.** The comment restates the line below it or names a phase (`// increment count`, `// Phase 1: add cards`). Delete it.
2. **Commented-out code and removal markers.** Code behind comment markers, or a `// removed` note. Delete it.
3. **Keep list.** License headers. Non-obvious behavior forced by an external dependency, platform, vendor, or protocol you cannot reshape. `prettier-ignore`. Doc comments that define a public API contract. Issue or RFC links that explain a constraint code cannot express. A kept comment is still prose, so `/unslop` reads it.

### Guards

4. **Guard on an impossible state.** A null check on a value the types or the boundary never leave null, `instanceof` on an already narrowed type, a length check on a tuple, a default for an argument every caller passes. Delete it. Trust the type.
5. **Defensive wrapping on a trusted path.** A `try/catch` or a fallback around an internal call that cannot fail the way the handler expects, or a handler that swallows the error. Remove the wrapper, or let it throw. A silent fallback that hides an unclear invariant is rule 4, and the report names the invariant.
6. **Repeated validation.** A check that re-parses or re-validates data the boundary already parsed. Delete the inner copy.

A guard at a system boundary (user input, network, file, environment, external API) stays. A guard a test demands stays, and the test is the proof.

### Dead paths

7. **Compatibility shims.** An old path kept beside the new one, an alias or re-export kept "for callers" with no caller, a deprecation notice for code this branch replaced. Delete the shim and migrate the caller in the same change.
8. **Unused parameters, exports, and flags.** A parameter nothing passes, an export nothing imports, an option with one value, a flag with one reachable branch, a branch marked temporary. Delete it.
9. **Debug residue.** Debug logs and prints, tagged or not, throwaway prototypes, variant switchers. Delete them.

### Types

10. **Checker silencers.** A cast to `any` or `unknown`, an `as` assertion, or a suppression comment whose only job is to make the type checker pass. Fix the type or delete the cast.

### Shape

11. **One-caller wrappers.** A function, helper, or adapter with one caller that passes its arguments through. Inline it.
12. **Speculative generality.** An abstraction, parameter, hook, or seam with one implementation and no second use in the task. Inline it back until a real need shows.
13. **Re-implemented helpers.** Code that does what a helper in the codebase already does. Call the existing one.
14. **Nesting an early return flattens.** A guard clause whose body is the rest of the function. Return early and dedent.
15. **Copy-paste with variation.** The same shape twice inside the diff with small differences. Extract only when the codebase already names the shared shape. Otherwise three similar lines stay.
16. **Structure the diff cannot fix.** A new conditional bolted onto an unrelated flow, a one-off boolean or nullable mode, repeated conditionals on one shape. Flag it for the Refactoring playbook under **principle-model-the-domain**. Do not fix it here.

### Scope

17. **Unrelated edits.** Formatting churn, renames, import reorders, or syntax modernizing in code the task did not need to touch. Revert them.
18. **A behavior change inside cleanup.** A hunk that changes what the code does under a cleanup label. Split it out and name it in the report.
19. **Style against the file.** A pattern the surrounding file does not use. Match the file.

## Report

One to three sentences, then:

- Counts by rule id, and the files touched.
- Hunks reverted under rule 17.
- Flags handed to the Refactoring playbook (step 3, rule 16) and to `/no-comments`.
- A "Did not touch" list of slop outside the scope.
- The test and type-check commands with their results.

`CREDITS.md` names the sources this skill drew on and the sentences it carried over.
