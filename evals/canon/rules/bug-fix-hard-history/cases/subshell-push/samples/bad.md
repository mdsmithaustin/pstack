Fixed in `omnigent/policies/builtins/_shell.py`.

**Cause.** `split_command_segments` splits only on chaining operators, so in `(git push <fork> main)` the first token is `(git` and the GitHub policy never sees a push.

**Fix.** The splitter now also splits on `(`, `)`, `{`, and `}`, so a subshell, brace group, or process substitution becomes its own segment and gets gated like the bare command. Over-splitting only ever makes extra harmless segments, as the docstring says.

**Verification.** `(git push <fork> main)` and `{ git push <fork> main; }` are now denied.
