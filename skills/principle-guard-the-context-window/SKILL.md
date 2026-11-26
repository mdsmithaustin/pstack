---
name: principle-guard-the-context-window
description: "Apply before a large read, a long command output, or a subagent brief, not only when context is filling up. Route bulk to subagents, take thin reports back, and keep summaries in the main thread, not raw payloads."
---

# Guard the Context Window

The context window is finite and non-renewable within a session. Every token should be worth its cost.

**Why:** Context overflow degrades reasoning quality, creates compression artifacts, and halts progress.

**Pattern:**
- **Isolate large payloads.** Route verbose outputs, screenshots, and large documents to subagents. The main context gets summaries, not raw data. A read-only scan or parse that returns a reduced finding runs on the `routine` role, unless the calling skill names another role. Call the Skill tool with `pstack-harness`, then follow its **Spawn a role** section to resolve the role.
- **Keep frequently used content inline.** Templates and references used on every invocation belong in the skill file, not in separate files that cost a read each time.
- **Size phases and cap scope.** Limit files per phase, set turn budgets, account for mechanism costs.
- **Return thin.** When a subagent's report feeds your next step, its brief names where the full report goes, a file the subagent writes or the PR, and asks for only the verdict or status line, any blockers, and that path or URL. Read the full report only to act on a blocker. A subagent whose output is the deliverable you relay, such as a `how` explanation, a `why` synthesis, the trail reviewer's flags, or an arena cross-judge's scores, returns it in full.
- **Read steps, not whole playbooks.** Open a playbook's worklist from the output of the mode entry's plan script, which prints the opening prose and each step's outcome. When a step starts, run the `--step` command the plan prints. Without the script, print the playbook's prose before step 1 and its numbered steps with their indented sub-items (`awk '/^[0-9]+\. /{p=1} !p && !/^#/ && NF {print; next} p && /^[^ ]/ && !/^[0-9]+\. /{exit} p' <playbook>`). When that prose says to read the playbook in full, read it in full.
