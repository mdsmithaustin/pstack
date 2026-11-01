# Ask a structured question

**Structured questions (`AskQuestion`).** Your harness's structured-question tool if it has one; otherwise ask in plain chat.

**Detect a session that cannot reach a human.** Some harnesses show this through the tools they offer:

- **Claude Code.** A subagent never has `AskUserQuestion`, so a subagent takes this from its brief and never from its own tools. In the top-level session, no human can answer when the `claude` process that runs your shell was started with `-p` or `--print`. To check, walk your shell's parent processes with `ps -o ppid= -p <pid>` and read the `claude` process's arguments with `ps -o args= -p <pid>`. A missing `AskUserQuestion` alone proves nothing, because a restricted tool list also removes it.
- **Codex.** `request_user_input` is offered only in some collaboration modes, so its absence proves nothing.
- **Grok Build, Hermes, other.** No verified signal.

Where this section gives no signal, treat the session as attended unless the user or the active playbook says otherwise.
