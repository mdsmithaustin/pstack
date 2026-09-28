Fixed in `omnigent/policies/builtins/github.py`.

**Cause.** The GitHub policy compares the first token of each segment with `git`, and in `(git push <fork> main)` that token is `(git`.

**Fix.** The policy now strips a leading `(` from the command and a trailing `)` from its last argument, the same way the working-directory policy already strips a leading paren.

**Verification.** `(git push <fork> main)` is denied and `(git push <ours> main)` is allowed.
