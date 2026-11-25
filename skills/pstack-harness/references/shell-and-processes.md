# Shell commands and running processes

Use this reference in every runtime when you read a diff or answer what is running.

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

## Inspect running processes

Process discovery grants inspection, not permission to terminate unrelated processes. Keep command lines private when they contain credentials or user data.
