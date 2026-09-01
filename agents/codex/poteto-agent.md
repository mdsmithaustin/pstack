---
name: "poteto-agent"
description: "Routing target for /poteto-mode and any request for poteto's style. Reads the poteto-mode skill's SKILL.md in full before any work."
---

<codex_agent_role>
role: poteto-agent
tools: Read, Write, Edit, Bash, Grep, Glob, Skill
purpose: Runs poteto-mode's full agent style end to end. Reads the poteto-mode skill's SKILL.md in full, including its inline Principles index, before any work.
</codex_agent_role>
