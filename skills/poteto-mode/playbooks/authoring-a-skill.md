### Authoring or modifying a skill

**You own the skill's voice.**

When in doubt, delete. Keep only prose that changes a decision. Match tone to scope. Point at structural sources (types, READMEs, config). Call the Skill tool with `principle-encode-lessons-in-structure`.
- **State the rule, and its reason where the mechanism can differ.** Tell the agent to do the thing. When the rule names a tool, a parameter, or how one harness behaves, add the reason in one clause, because the reason lets an agent on another harness find the equivalent action. Skip the reason when the rule is plain without one.
- **Name the intent, not one harness's parameter.** Write "run it in the background" or "start it with a fresh context". Keep exact tool names and parameters in one place per harness, so a step reads the same on every CLI.
- **Give each case its own line.** When a step or paragraph covers several cases, write one list item per case and open it with its condition. Keep every line under 150 words, because a reader that skims a long block keeps its start and end and loses the middle.
- **Open each step with its outcome.** State the condition that makes the step done before the actions, so the agent can tell done from not done.
- **Delegate by name.** To delegate to another skill, write "Call the Skill tool with `how`." with the target skill's bare name in code font, as its own sentence or step. Don't restate its content.
- A workflow you keep hitting but isn't captured → propose a new skill.

1. Author the `SKILL.md` per the [agentskills.io](https://agentskills.io) format: YAML frontmatter with `name` (kebab-case, matching the directory) and a `description` that names the concrete triggers — the words a user or task would actually contain — not generic keywords; then a body that opens with when-to-use, keeps steps imperative, and pushes bulk detail into `references/` files read on demand. Place project skills in `.agents/skills/<name>/`, personal ones in `~/.agents/skills/<name>/`, then link each project skill into whatever directories the CLIs in use discover skills from (what `npx skills` maintains on install) so every CLI finds it.
   Write each step for an agent to execute. Call the Skill tool with `technical-writing`, then follow its STE layer.
2. Validate the skill: frontmatter has `name` and `description`, referenced files exist, cross-skill links resolve, and no line runs past 150 words.
3. Test cases if structural. Skip if subjective.
4. Run **Opening a PR**.

**Reply:** summary of the skill, key design decisions, validation notes.
