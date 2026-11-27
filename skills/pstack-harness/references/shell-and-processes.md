# Shell commands and running processes

Use this reference in every runtime when you read a diff, wait on a command or outside state, or answer what is running.

## Read a diff

Read without a cap any diff, test file, or code that you will judge. A cap on search or log output that you only scan is fine. Never cap the list from step 1. When a skill tells you to print one part of a file, such as one playbook step, you need only that part, and it must arrive uncut.

1. Save each changed file's diff to its own file. Run this in any shell, with one range from the table in place of `<range>`. Quote a revision that holds `^`, as in `'HEAD^'`.

   ```sh
   python3 "<installed skills root>/pstack-harness/scripts/save-diff.py" <range>
   ```

   | `<range>` | What the script saves |
   |---|---|
   | nothing | Everything not yet committed: staged changes, unstaged changes, and untracked files. Use it before a commit. |
   | `--cached` | Staged changes only. |
   | `HEAD`, or one other revision | The working tree against that revision, and untracked files. |
   | `--merge-base <base>` | A branch's whole change against the commit where it left `<base>`: its commits, its working tree, and untracked files. |
   | `<base>...HEAD`, or two revisions | Commits only. It leaves out the working tree and untracked files. |

   It prints `index <file>`, then one row per file, `<bytes> <saved file> <status> <name>` with notes in parentheses, then the last line, `<n> rows saved, <k> not shown; covers <what the range covers>; index <file>`. An `unmerged` row holds the working tree copy with its conflict markers. A `not shown` row holds none of the content. If the output came back cut or without that last line, do not run the script again. Read the index file as [Read files](codex.md#read-files) says, and take the rows and the last line from it. When the script refuses a word or its temporary directory, follow its message. Let it pass every path, and pass it revisions only.
2. Read every saved file, one at a time. On Codex, read each as [Read files](codex.md#read-files) says.
3. Check the last line. `<n>` must equal the count of rows and the count of saved files that you read to the end. A file that came back cut off is unread, so read its missing part before you judge the change. For each row marked `not shown`, read the file itself or report that file as unread. Read the working tree file for an `unmerged` row, `git show :<name>` for any other `staged` or `--cached` row, and `git show <revision>:<name>` when the range ends at a commit. If the command exits with an error, the change is unread and the script has already removed its directory. Report the error line and stop.
4. Remove the directory that holds the index file once you have judged the change.

## Wait for a change, not a tick

Each return from a wait makes you reread your whole context, so a wait costs about as much as the session so far. Make each wait return only when the state you need changes or a deadline passes.

- To wait on a long command, such as a test run, start it once under a deadline and wait for it to exit. Use the command's own timeout flag, or wrap it in a timeout. Never check its output again and again while it runs. When the deadline passes, read its output once to see why.
- To wait on a GitHub PR, use the `watch-pr` watcher that Babysit names, because it already exits on every blocker, review findings included.
- To wait on other outside state, such as CI or a gate run, run one command that checks in a loop, and give it a deadline. It prints nothing until the state changes or its deadline passes, then prints one line and exits.
- Never sleep between your own checks, and never wait in short steps that each wake you to find nothing changed.
- On Claude Code, apply this with [its wait tools](claude-code.md#wait-for-a-change). On Codex, apply it with [its wait tools](codex.md#wait-on-a-command-with-one-long-wait). On another runtime, use the longest wait its tools offer that still returns when the command exits.

## Hand a PR watch to a child

Use this for Babysit `drive` and the Shipping queue wait on GitHub. A `routine` child holds the watch, so the lead's context is reread once, for the report, not at every watcher return.

- Resolve `routine` with **Spawn a role**. When it resolves to `inherit-parent`, or the runtime cannot pin a model (Grok Build, Hermes), hold the watch yourself under the rule above. A child on your own model saves nothing.
- Brief the child to run `watch-pr` in the foreground, never to end its turn while the watch is open, and to report once. A child that ends its turn finishes, and each stop wakes you. It reruns the watcher without a report on exit 5, which only a nonzero `--timeout` produces, and on a first exit 7. Any other exit ends the watch.
- Give the child a format for its entire final reply, with at most five lines total. Use one plain-text line each for the exit code, the verdict (`READY`, `COMPLETE`, or the blocker kind), the head SHA, and a review URL when exit 8 names one. Start with the exit code and end the reply after the last field. Take the head SHA from the terminal `watch-pr` JSON, and on exit 8 use `blocker.reviews[].commitOid` and the URL from the same review. Leave out a field the JSON does not carry.
- The child reads, and it never changes state. It never merges, runs `merge-gate`, answers a review thread, or posts a comment. It writes no security, privacy, auth, or data finding. You do those. After each report you read the review bodies yourself, and in a gated repository `no-mistakes axi status`. On exit 7 the child has already retried, so report the query failure.
- After each report, act, then start a fresh child to watch the next head. Never resume one across pushes.
- On Claude Code, set `run_in_background: true` on the `Agent` call and end your turn after launch. The child runs the watcher in a foreground Bash call with `timeout: 600000` and `--timeout 540`, and reruns on exit 5. The Bash tool caps a call at 600000 ms, and the Claude Code docs set a ten-minute stall timeout for subagents.
- On Codex, the child follows [its wait tools](codex.md#wait-on-a-command-with-one-long-wait), and each poll rereads the child's context, not yours. Wait for the child with `wait_agent` and `timeout_ms: 3600000`, so its timeout is the only empty wake. With `close_agent` in your tools, pass the child's ID. The wait returns when the child reaches a final status and lowers a larger value to its maximum. Without `close_agent`, the wait takes no ID, returns on any mailbox message, and fails a value above its configured maximum, 3600000 by default at 0.170.0. Read the live schema.

## Inspect running processes

Process discovery grants inspection, not permission to terminate unrelated processes. Keep command lines private when they contain credentials or user data.
