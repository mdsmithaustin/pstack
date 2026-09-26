# Sessions

The words hermes-agent uses for what `state.db` keeps about each run of the agent.

## Language

**Session**:
One row in `state.db` with its own id. Compression ends a session and starts a new one.
_Avoid_: conversation, chat

**Lineage**:
The compression continuations of one session, in order from root to tip.
_Avoid_: chain, thread

**Continuation**:
A session whose parent ended because of compression.

**Tip**:
The live, last session of a lineage.
_Avoid_: head, latest

**Branch**:
A copy of a session that the user makes with `/branch`. It owns its own transcript and is not part of its source's lineage.
_Avoid_: fork, clone

**Profile**:
One isolated `HERMES_HOME` with its own `state.db`.
_Avoid_: workspace, account

## Relationships

- A **Lineage** holds one root **Session** and its **Continuations**.
- A **Branch** is the root of a lineage of its own.
