# Ask a structured question

**Structured questions (`AskQuestion`).** Your harness's structured-question tool if it has one; otherwise ask in plain chat.

**Detect a session that cannot reach a human.** Some harnesses show this through the tools they offer:

- **Claude Code.** `AskUserQuestion` is missing from your tools only in a non-interactive run (`claude --print`). When it is missing, no human can answer.
- **Codex.** `request_user_input` is offered only in some collaboration modes, so its absence proves nothing.
- **Grok Build, Hermes, other.** No verified signal.

Where this section gives no signal, treat the session as attended unless the user or the active playbook says otherwise.
