# Skill cross-reference phrasing

Checked 2026-10-09. Installed hosts were Claude Code 2.1.295 and codex-cli 0.162.0. Codex source was read at openai/codex `4aa94dce` (main, 2026-10-09). Earlier pstack research on 2026-09-14, kept outside the repository, reached the same Codex result at rust-v0.152.0.

## Decision

pstack needs one phrasing that a skill's body uses to make the agent load a sibling skill. The phrasing has to work on Claude Code with siblings listed name-only, and on Codex with siblings set to `allow_implicit_invocation: false`.

## Recommendation

Use an imperative verb, then the bare skill name, then the word "skill": **"Use the `no-comments` skill"** (the house bold form, "Use the **no-comments** skill", is equivalent). Put it in a numbered step or a direct sentence, never in a "per" or "in" clause, at every site where the sibling must load. Leave plain mentions (routers, "see also") as they are. The **pstack-harness** skill defines what "use the X skill" means on each CLI. On Claude Code it means a Skill tool call with the bare name. On Codex, Grok, and Hermes it means reading `<installed skills root>/X/SKILL.md`.

The [2026-10-10 results record](../evals/promises/results/2026-10-10-use-the-skill.md) measures the shipped wording against an old-text control on Claude Code and Codex. It owns the hit rates, trace classifications, and remaining failures. Those runs support the deslop hand-off change, but do not establish a gain for every sibling-skill load point or harness.

Reasons, each with its evidence label.

1. Fact. Neither the slash nor the `$` sigil is model-side syntax. agentskills.io describes both as user syntax "that the harness intercepts". Codex parses `$name` only from `UserInput`, so a `$name` inside a loaded SKILL.md is plain text.
2. Fact. On Codex, `allow_implicit_invocation: false` hides the skill from the model's catalog. A name alone cannot resolve there. Only a file path, or a harness map that supplies the root, can reach the skill.
3. Fact. On Claude Code, the Skill tool takes "exact name from the listing, no leading slash". A `name-only` override keeps the name in that listing.
4. Inference from two independent origins (mattpocock/skills and zhupanov/larch). An explicit imperative tied to the load action fires more often than a bare mention. Both authors claim this without numbers.
5. Inference. Naming "the Skill tool" literally, as Pocock does, works on Claude Code only. pstack runs on four hosts, so the verb belongs in prose and the mapping belongs in pstack-harness, which already maps every other primitive.

## Vendor guidance, verbatim

| Source | Quote | Link |
| --- | --- | --- |
| Claude Code skills docs | "Claude uses skills when relevant, or you can invoke one directly with `/skill-name`." | [code.claude.com/docs/en/skills](https://code.claude.com/docs/en/skills) |
| Claude Code skills docs, `skillOverrides` | `"name-only"` → Listed to Claude "Name only", in `/` menu "Yes" | [#override-skill-visibility-from-settings](https://code.claude.com/docs/en/skills#override-skill-visibility-from-settings) |
| Claude Code skills docs | "**Hide individual skills** by adding `disable-model-invocation: true` to their frontmatter. This removes the skill from Claude's context entirely." | [#restrict-claudes-skill-access](https://code.claude.com/docs/en/skills#restrict-claudes-skill-access) |
| Claude Code Skill tool description, observed in this 2.1.295 session | "`skill`: exact name from the listing, no leading slash." and "Users may also ask for one by name (`/<name>`, or \"slash command\")" | Tool schema in session, not a public page |
| Anthropic best practices | Names should be consistent so you can "Reference Skills in documentation and conversations". It says nothing on cross-skill invocation. | [platform.claude.com best-practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) |
| agentskills.io client guide | "The most common pattern is a **slash command or mention syntax** (`/skill-name` or `$skill-name`) that the harness intercepts." (under "User-explicit activation") | [adding-skills-support](https://agentskills.io/client-implementation/adding-skills-support) |
| agentskills.io client guide | "**Hide filtered skills entirely** from the catalog rather than listing them and blocking at activation time." (lists `disable-model-invocation` as a filter reason) | same |
| agentskills.io spec | Covers only file references ("Keep file references one level deep from `SKILL.md`"). It says nothing on referencing other skills. | [specification](https://agentskills.io/specification) |
| OpenAI Codex docs | "In Codex CLI or the IDE extension, run `/skills` or type `$` to mention a skill." | [developers.openai.com/codex/skills](https://developers.openai.com/codex/skills) |
| OpenAI Codex docs | "`allow_implicit_invocation` (default: `true`): When `false`, Codex won't implicitly invoke the skill based on user prompt; explicit `$skill` invocation still works." | same |
| Codex system prompt source | "If the user names a skill (with `$SkillName` or plain text) OR the task clearly matches a skill's description shown above, you must use that skill for that turn." | [catalog_prompt.rs](https://github.com/openai/codex/blob/4aa94dce270de668eff6e2fa8585c82385e84455/codex-rs/ext/skills/src/catalog_prompt.rs) |
| Codex source | `if !skill.allows_implicit_invocation() { entry = entry.hidden_from_prompt(); }`, and `is_model_visible` is `self.enabled && self.prompt_visible` | [provider/host.rs](https://github.com/openai/codex/blob/4aa94dce270de668eff6e2fa8585c82385e84455/codex-rs/ext/skills/src/provider/host.rs), [catalog.rs](https://github.com/openai/codex/blob/4aa94dce270de668eff6e2fa8585c82385e84455/codex-rs/ext/skills/src/catalog.rs) |
| Codex source | Explicit selection matches `UserInput::Skill`, `UserInput::Mention`, and `$` mentions in `UserInput::Text`. No other text is scanned. | [selection.rs](https://github.com/openai/codex/blob/4aa94dce270de668eff6e2fa8585c82385e84455/codex-rs/ext/skills/src/selection.rs) |
| Cursor | `cursor.com/docs/context/skills.md` returned "Page not found". Cursor docs were not inspected. | none |

## What public suites do

Commits are the shallow-clone HEADs from 2026-10-09. Star counts were read the same day. The counts come from a script that matched sibling names in every SKILL.md body, so treat them as rough.

| Suite (stars, commit) | Dominant form | Exact quote | Link |
| --- | --- | --- | --- |
| mattpocock/skills (282k, `49dd158`) | "Call the Skill tool with" + quoted name. Slash only in human-facing routers or "tell the user to run" | "Call the Skill tool with \"tdd\" where possible, at pre-agreed seams." | [implement/SKILL.md#L11](https://github.com/mattpocock/skills/blob/49dd158d1076134a641b33efb035946536778336/skills/engineering/implement/SKILL.md#L11) |
| mattpocock/skills, convention doc | same | "Dependencies are expressed as an explicit instruction to **call the Skill tool** with the named skill (`Call the Skill tool with \"grilling\"`), not deep `../other-skill/FILE.md` cross-references, and not a bare `/skill`-style mention left for the model to interpret." | [.agents/invocation.md](https://github.com/mattpocock/skills/blob/49dd158d1076134a641b33efb035946536778336/.agents/invocation.md) |
| mattpocock/skills, convention doc | user-invoked carve-out | "A user-invoked skill can never be reached this way, full stop ... phrase it as an instruction for the human to act on: \"tell the user to run `/setup-matt-pocock-skills`\"" | same |
| obra/superpowers (297k, `8ca22db`) | Requirement marker + verb + namespaced name | "**REQUIRED SUB-SKILL:** load superpowers:test-driven-development now" | [executing-plans/SKILL.md#L149](https://github.com/obra/superpowers/blob/8ca22dba9a94f28898bbce59f2537ff4d87c747d/skills/executing-plans/SKILL.md#L149) |
| obra/superpowers, authoring guide | same | "Use skill name only, with explicit requirement markers: ✅ Good: `**REQUIRED SUB-SKILL:** Use superpowers:test-driven-development` ... ❌ Bad: `See skills/testing/test-driven-development` (unclear if required) ❌ Bad: `@skills/testing/test-driven-development/SKILL.md` (force-loads, burns context)" | [writing-skills/SKILL.md#L278-L287](https://github.com/obra/superpowers/blob/8ca22dba9a94f28898bbce59f2537ff4d87c747d/skills/writing-skills/SKILL.md#L278-L287) |
| cursor/plugins pstack, upstream (10.6k, `ccb5507`) | Bold name after "run", "per", or "via". Its own rule says "by path" | "run the **architect** skill (it runs **arena**)" and "Delegate to other skills by path." | [figure-it-out/SKILL.md#L30](https://github.com/cursor/plugins/blob/ccb5507cec1546dc88135c1139c811e6c59115ba/pstack/skills/figure-it-out/SKILL.md#L30), [authoring-a-skill.md#L10](https://github.com/cursor/plugins/blob/ccb5507cec1546dc88135c1139c811e6c59115ba/pstack/skills/poteto-mode/playbooks/authoring-a-skill.md#L10) |
| openai/skills (28k, `49f948f`) | Mixed. `$name` for a visible system skill, "load the `x` skill", and a relative SKILL.md link | "Use `$imagegen` for all normal visual generation." / "load the `figma-use` skill before calling it." / "You MUST also load [figma-use](../figma-use/SKILL.md) before any `use_figma` call." | [hatch-pet#L16](https://github.com/openai/skills/blob/49f948faa9258a0c61caceaf225e179651397431/skills/.curated/hatch-pet/SKILL.md#L16), [figma-create-new-file#L68](https://github.com/openai/skills/blob/49f948faa9258a0c61caceaf225e179651397431/skills/.curated/figma-create-new-file/SKILL.md#L68), [figma-generate-design#L10](https://github.com/openai/skills/blob/49f948faa9258a0c61caceaf225e179651397431/skills/.curated/figma-generate-design/SKILL.md#L10) |
| addyosmani/agent-skills (104k, `1401c8b`) | Repo path plus code-span name | "Execute tasks one at a time following `skills/incremental-implementation/SKILL.md` (`incremental-implementation`)" | [spec-driven-development#L214](https://github.com/addyosmani/agent-skills/blob/1401c8b8030e023baeebb31781a6653fe8e93026/skills/spec-driven-development/SKILL.md#L214) |
| trailofbits/skills (7.5k, `442fc9d`) | "use the `x` skill" | "Generating diagrams (use the `diagramming-code` skill after augmenting)" | [audit-augmentation#L36](https://github.com/trailofbits/skills/blob/442fc9d6c89b1e937e6f7a477e7071ea75fcbea4/plugins/trailmark/skills/audit-augmentation/SKILL.md#L36) |
| anthropics/skills (180k, `dbd4588`) | None. Its 19 skills never reference each other | none | [skills/](https://github.com/anthropics/skills/tree/dbd4588f9e1033efb41dad4bef2f7947c8993d44/skills) |
| vercel-labs/agent-skills (32k, `063bee9`) | None found | none | none |

Independent origins that state a rule: Pocock, superpowers, larch, and upstream pstack. timharris707/skills#302 adopts Pocock's rule and cites him, so it is not independent. The other suites state no rule and only show usage.

## Evidence on reliability

- mattpocock/skills [PR #878](https://github.com/mattpocock/skills/pull/878), merged 2026-08-15. "Naming the tool directly gets a higher hit rate than dropping a bare `/name` into prose and hoping the model reads it as a command." No eval is cited.
- mattpocock/skills commit [1dab982](https://github.com/mattpocock/skills/commit/1dab98299c3b81f560026c01b7ebf55ed5d91373), fixing [#453](https://github.com/mattpocock/skills/issues/453). The explicit phrasing "made this fire more reliably in the wrong direction" against a `disable-model-invocation` target. This is the same hazard pstack's gated siblings faced before PR 185 removed the flag.
- zhupanov/larch [#168](https://github.com/zhupanov/larch/issues/168), a research report from 2026-04-19 with three agents. "Phrasing matters, but phrasing alone cannot guarantee the caller will call the sub-skill." It recommends "an explicit numbered step with an imperative verb, the tool name, and literal args", ranked below structural checks (narrow `allowed-tools`, verify the child's side effect). It reports no measured rates.
- anthropics/claude-code [#43809](https://github.com/anthropics/claude-code/issues/43809), closed. "Error: Skill cc-use-subagents cannot be used with Skill tool due to disable-model-invocation" when a subagent tries to load a gated skill.
- anthropics/claude-code [#73774](https://github.com/anthropics/claude-code/issues/73774), closed. Claude Code's system prompt tells the model to invoke the Skill tool for any `/<name>` reference, and that duplicate call errors on a gated skill.
- timharris707/skills [#302](https://github.com/timharris707/skills/issues/302). "add it without a paid eval" and "Out of scope: Measuring the hit rate."

## Contradictions

- Upstream pstack says "Delegate to other skills by path", yet its text uses bold names almost everywhere. Pocock rejects `../other-skill` links. OpenAI's own curated skills use them.
- Pocock calls "Call the Skill tool" "more harness-neutral". That holds for the sigil only. Codex has no `Skill` tool for host skills, and a hidden Codex skill cannot be reached by name at all.
- superpowers and Pocock both name the target bare, with no sigil. superpowers uses the `superpowers:` namespace that Claude Code gives plugin skills. pstack installs skills flat, so it has no namespace to use.

## Pstack state before PR 185 (measured)

This census describes the tree at f8eb694f, before PR 185 (e4968e32) dropped `disable-model-invocation` from all 47 skills. `skills/` holds 57 skills. 47 have `disable-model-invocation: true` and 47 have `allow_implicit_invocation: false`. `skills/**/*.md` contains the phrase "the **x** skill" 127 times. Where a preposition comes first, it is mostly "in" (31) or "per" (22). Imperative "Run" or "Use" comes first only 5 times. Slash forms appear in SKILL.md a handful of times (for example `/poteto-mode` 3 times).

## Unknowns

1. Precedence. Moot for pstack, because PR 185 removed the frontmatter flag and the 2026-10-10 runs loaded figure-it-out through the Skill tool on a name-only listing. The docs question stays open. The docs do not say whether a `skillOverrides` value of `"name-only"` overrides frontmatter `disable-model-invocation: true`. If frontmatter wins, the Skill tool keeps refusing gated siblings (#43809), and Claude Code needs the path route too. One `/skills` check or one `Skill` call settles it.
2. Hit rate. The [2026-10-10 results record](../evals/promises/results/2026-10-10-use-the-skill.md) compares the shipped deslop wording with its old-text control. It does not isolate the step 5 wording from the Report wording or compare "Use the X skill", "Call the Skill tool with X", `/X`, and a path as separate arms.
3. Grok Build and Hermes. Their docs and source were not inspected for how they handle sibling skills.
4. Cursor. Its skills docs URL returned 404, and nothing else was inspected.
