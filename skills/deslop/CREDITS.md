# Credits

`deslop` is pstack's own skill. Its rules were written for this port, and three MIT-licensed skill collections shaped them. This file carries the notices those sources require and names the sentences `SKILL.md` carried over, because a copied sentence owes its notice and a paraphrased idea deserves its source.

## Cursor, `cursor-team-kit`

Source: https://github.com/cursor/plugins/blob/23e4138daa01c42d4969f7a5465f82704e64f798/cursor-team-kit/skills/deslop/SKILL.md (commit `23e4138d`, read 2026-10-03).

Carried over: the name `deslop`, the scope sentence (check the diff against the base branch and remove the slop the branch introduced), four of the five focus areas (unnecessary comments, defensive checks and `try/catch` on trusted paths, casts to `any` that only bypass the checker, deep nesting an early return flattens, patterns inconsistent with the surrounding file), and two guardrails (keep behavior unchanged, prefer minimal edits over broad rewrites, a summary of one to three sentences). Rules 10, 14, and 19 and process step 2 restate these in this skill's words.

Copyright (c) 2026 Cursor. MIT License.

## Addy Osmani, `agent-skills`

Source: https://github.com/addyosmani/agent-skills/tree/a06bc63b3f8b829c14b0bbf53d99fefc39d58092 (commit `a06bc63b`, read 2026-10-03), files `skills/code-simplification/SKILL.md`, `skills/code-review-and-quality/SKILL.md`, `skills/incremental-implementation/SKILL.md`, `skills/deprecation-and-migration/SKILL.md`, and `skills/git-workflow-and-versioning/SKILL.md`.

Carried over: "three similar lines" as the limit on extracting a shared shape (rule 15), the rule that a simplification which needs a test change changed behavior (process step 4), the ban on drive-by refactors of code the task did not touch (rule 17), the "did not touch" section of the report, and the remove-the-shim sequence behind rule 7. Rules 1, 2, 11, and 12 restate its "what" comment, dead code, wrapper, and speculative abstraction rows.

Copyright (c) 2025 Addy Osmani. MIT License.

## Matt Pocock, `skills`

Source: https://github.com/mattpocock/skills/tree/d81f3a183412e71a5b1e84ca21bc1a35eea03a60 (commit `d81f3a18`, read 2026-10-03), files `skills/engineering/code-review/SKILL.md`, `skills/engineering/codebase-design/SKILL.md`, `skills/engineering/diagnosing-bugs/SKILL.md`, and `skills/engineering/prototype/UI.md`.

Carried over: "inline back until a real need shows" for speculative generality (rule 12), the middle-man cut behind rule 11, the one-adapter seam test behind rule 12, and the debug-residue list (tagged debug logs, throwaway prototypes, variant switchers) in rule 9.

Copyright (c) 2026 Matt Pocock. MIT License.

## MIT permission notice

Each source above is licensed under the MIT License, whose notice reads:

> Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

The keep list in rule 3 is pstack's own, from `agents/comment-sicko.md`. Rules 4 to 6, 8, 13, 16, and 18 come from pstack's principle skills (boundary discipline, subtract before you add, minimize reader load, migrate callers then delete legacy APIs) and from the `make-pr-easy-to-review` skill in `cursor-team-kit`, under the Cursor notice above.
