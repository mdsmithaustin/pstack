# Review lens

The Code review playbook opens this file at its design checks. Each question names the evidence to gather and when to leave the code alone. A question with no evidence behind it is not a finding. The governing leaf holds the rule. This file holds the review questions and a smells table.

## Vocabulary and concepts (principle-model-the-domain)

- **Does a new name use the domain's words?** Read the nearest `CONTEXT.md` and the names in the surrounding code. Flag a word the glossary lists under `_Avoid_`, and an operation named for its mechanism (`processItems`, `handleData`) where a domain effect fits. Leave it when no glossary exists and the name matches its neighbors.
- **Does the diff add a second name for a concept the code already names?** Grep the new term and the likely older one across the repo. Read what each one refers to. Flag two words for one concept. The fix direction is to keep the code's word. Leave it when the two words name different concepts, or when the PR renames every occurrence.
- **Does one type now carry two meanings?** List which callers read which fields. Flag fields that are optional per meaning, where each caller reads only its own half. Leave it when every caller reads every field.
- **Does the diff merge two types that share a name?** Read both definitions and list the importers of each. Flag the merge when the importers sit in different parts of the codebase and read disjoint fields. Share only what means the same thing in both, such as an id. Leave it when both parts use the type the same way.
- **Does the change grow a branch chain or add a flag that must stay in sync with another?** Count the branches on the same tag across files. Flag a new branch in a chain that already repeats. Leave it when the chain is local and unlikely to grow.

## Shared code and its callers (principle-model-the-domain)

- **Does the diff change shared code for one caller?** List every caller of each changed function, type, or constant with grep, or, when `.gitnexus/` exists, refresh it with `gitnexus analyze --index-only` and run `gitnexus impact <symbol>`. For each caller outside the PR's intent, decide whether its output changes. Flag a behavior change that reaches a caller serving a different business function with no test and no mention in the PR. The fix direction is to fork the piece and change only the requester's path. Leave it when every caller wants the new behavior, or the PR says so and a test covers it.
- **Does the diff merge look-alike code?** Find who changes each copy. Read `git log` on each, the owners file, and the README. Flag the merge when different business functions change the copies. Leave it when the copies change for the same reasons.

## Boundaries and dependency direction (principle-boundary-discipline)

- **Does a domain or policy module import something from the outside?** Read the import list of each changed domain module. Type-only imports count. Flag an import of a framework, driver, ORM, IO library, generated schema type, or adapter module. The fix direction is for the caller to fetch the value and pass it in as plain data. Leave it when the module is itself the adapter or the shell.
- **Does a wire, storage, or framework type cross the public surface?** Read the changed exports. Flag a re-exported transport type or a raw payload passed inward. Leave it when the module is the boundary parser that produces the domain type.
- **Does the diff add validation deep inside typed code?** Find where the data entered the system. Flag a nil check or re-validation of data that a boundary already parsed. Leave it when the data crosses a system boundary at that point.
- **Is business logic now tangled with framework wiring?** Flag a rule that can only run inside a handler, route, or component. Leave it when the logic is the wiring itself.

## Tests (principle-test-behavior-not-implementation)

- **Would each new or changed test still pass if every imported function returned `undefined`?** Read each assertion against the five shapes in the leaf. Flag a weak assertion, a mock-only check, a self-referential expected value, a constant pin, or a fixture that asserts itself. Leave it for a relation across table rows and a compile-time type test.
- **Does a test cover each behavior the PR changes?** Map each behavior change to a test that fails on the base. Flag a behavior change with no such test. Leave it when the change is structure only and existing tests already pin the behavior.
- **Does the setup establish state that production never establishes?** Read the test setup against the real initialization path. Flag a test that passes only because of that setup. Leave it when real callers can supply the same inputs.

## Restraint (principle-laziness-protocol, principle-minimize-reader-load)

- **Does the diff add a layer with one caller or one implementation?** Count callers and implementers. Flag a wrapper, interface, or helper that forwards without adding policy. Leave it when it adds policy, adaptation, or a second real implementation such as a test fake.
- **Are you about to ask for an abstraction?** Count the callers that would use it today. Leave it when the change has one caller and the current shape is clear and local. A second real caller in this repo is the evidence that earns the request.
- **Are you about to ask for a merge or dedupe?** Leave it until you have evidence that the copies change for the same reasons. Matching code today is not that evidence.

## Smells a diff can show

A smell is a reason to look, not a verdict. Name the smell and the refactoring in the finding, and leave it when the last column holds.

| Smell | What the diff shows | Refactoring to suggest | Leave it when |
|---|---|---|---|
| Mysterious Name | A name that needs the body read to know what it holds or does. | Change Function Declaration, Rename Variable, Rename Field | No honest name comes. Then the shape is the finding. |
| Duplicated Code | The same statement shape added in two or more places. | Extract Function, Slide Statements | The copies change for different reasons, or you have no evidence they change for the same ones. |
| Long Function | A block preceded by a comment saying what it does. Branches that each run several lines. | Extract Function, Decompose Conditional, Split Loop | The extracted piece would have one caller and no name better than the comment. |
| Long Parameter List | Five or more parameters. A boolean parameter that picks a code path. | Introduce Parameter Object, Preserve Whole Object, Remove Flag Argument | Each parameter is independent and every caller passes different values. |
| Global or Mutable Data | A new module-level `let`, singleton state, or a field kept in sync with another field. | Encapsulate Variable, Replace Derived Variable with Query, Split Variable | The state is already local. |
| Divergent Change | One file edited in this diff for two unrelated reasons. | Split Phase, Extract Function, Move Function | The two reasons share one invariant. |
| Shotgun Surgery | One logical change makes the same small edit in many files. | Move Function, Move Field, Inline Function | The files are separate deploy units. |
| Feature Envy | A new function reads more fields of another module's data than of its own. | Move Function, Extract Function | The data is a wire or storage type kept plain on purpose. |
| Data Clumps | The same three or more fields or parameters travel together across signatures. | Introduce Parameter Object, Preserve Whole Object | They meet in only one place. |
| Primitive Obsession | A string or number stands for an id, unit, money, or status. A status compared as a string. | Replace Primitive with Object, Replace Type Code with Subclasses | The value never leaves one function. |
| Repeated Switches | The same `switch` or `if` cascade on the same tag in two or more places. | Replace Conditional with Polymorphism, or a lookup table or discriminated union when variants hold data | The cascade appears once. |
| Lazy Element | A function or class whose body is one call. An interface with one implementation. | Inline Function, Inline Class, Collapse Hierarchy | It adds policy or adaptation, or has a second real implementation. |
| Speculative Generality | Parameters, hooks, or type parameters no caller varies. Code whose only callers are tests. | Remove Dead Code, Change Function Declaration, Inline Function | A second real caller exists in this repo. |
| Message Chains | `a.b().c().d()` in a caller. | Hide Delegate, Move Function | The chain is a fluent builder API. |
| Middle Man | A class where most methods forward to one other object. | Remove Middle Man, Inline Function | The forwarding adds policy. |
