### Authoring or modifying a skill

**You own the skill's voice.**

1. Author the `SKILL.md` per the [agentskills.io](https://agentskills.io) format: YAML frontmatter with `name` (kebab-case, matching the directory) and a `description` that names the concrete triggers — the words a user or task would actually contain — not generic keywords; then a body that opens with when-to-use, keeps steps imperative, and pushes bulk detail into `references/` files read on demand. Place project skills in `.agents/skills/<name>/`, personal ones in `~/.agents/skills/<name>/`, then link each project skill into whatever directories the CLIs in use discover skills from (what `npx skills` maintains on install) so every CLI finds it.
2. Validate the skill: frontmatter has `name` and `description`, referenced files exist, cross-skill links resolve.
3. Test cases if structural. Skip if subjective.
4. Run **Opening a PR**.

When in doubt, delete. Keep only prose that changes a decision. Tell it to do the thing and skip the reason. Explain only when the rule is confusing without one. Match tone to scope. Point at structural sources (types, READMEs, config) per the **encode-lessons-in-structure** principle skill. Delegate to other skills by path. Don't restate. A workflow you keep hitting but isn't captured → propose a new skill.

**Reply:** summary of the skill, key design decisions, validation notes.
