# Shell commands and running processes

Use this reference in every runtime when writing shell commands or answering what is running. The CLI's agent list and the operating system's process list answer different parts of that question.

## Write shell commands

Discover the shell that executes the command. `$SHELL` names the login preference and does not prove which shell a tool uses. On macOS, both Claude Code and Codex can execute through zsh.

- Quote patterns meant for a command, such as `rg --glob '*.md'`, so zsh does not expand them first. Quote model arguments such as `'opus[1m]@xhigh'`. If the shell must expand a glob, handle the no-match case explicitly before using its results.
- Use arrays for lists in bash and zsh. Iterate with `for item in "${items[@]}"`. A whitespace-delimited string does not preserve paths with spaces, and zsh does not split an unquoted scalar like bash does.
- Delimit variable names with braces when punctuation follows. Write `"${value}:suffix"`, because `$value:suffix` can invoke a zsh parameter modifier.
- When a snippet requires bash syntax, discover bash and execute it with `bash -c` or a script whose interpreter is bash. Quote the whole `-c` body so the outer shell does not expand it first. Supply data as positional arguments rather than interpolating it into shell code.

This example preserves two list elements, a literal pattern, and the colon suffix in either bash or zsh:

```sh
items=('one path' 'two')
for item in "${items[@]}"; do
	printf '%s\n' "${item}:done"
done
printf '%s\n' 'opus[1m]@xhigh' '*.jsonl'
```

## Read a diff

Read without a cap any diff, test file, or code that you will judge. Never pipe it through `head`, `tail`, or a line limit. A cap on search or log output that you only scan is fine. Never cap the list from step 1. When a skill tells you to print one part of a file, such as one playbook step, you need only that part, and it must arrive uncut.

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

   The script makes a new directory under the system temporary directory and saves one file there for each row. When that directory would be inside the checkout, the script refuses to run. Set `TMPDIR` to a directory outside the checkout and run it again. The first line it prints is `index <file>`. That index file holds every line that follows. Each row is `<bytes> <saved file> <status> <name>`, and notes can follow the name in parentheses:

   - `staged` or `not staged`. With no range, a file with both kinds of change has one row for each.
   - `unmerged`. The file is in conflict, and it has this one row. With one revision or `--merge-base` as the range, the row holds the file's diff against that revision.
   - `not shown`. The saved file holds none of the content. Git treats the content as binary, as it does for a file with a `-diff` or `binary` attribute, which lockfiles often have, and for UTF-16 text. Or git prints only the name of a conflicted file, as it does when one side deleted the file.

   The last line is `<n> rows saved, <k> not shown; covers <what the range covers>; index <file>`. If the output came back cut or without that last line, do not run the script again. Read the index file as [Read files](codex.md#read-files) says, and take the rows and the last line from it.

   The script saves each untracked file whole, because `git diff` never shows one. It saves an untracked symbolic link as the link's target and never reads what the link names. It leaves ignored files out, and it saves a submodule as its commit change only. It cannot save an untracked directory that holds its own repository, so that run fails and prints the directory with a byte count of 0. Let the script pass every path. A path you copy from a git listing can match no file and print nothing, because git prints some names quoted and `--stat` shortens them. The script refuses a path limit and every git option other than `--cached`, `--staged`, and `--merge-base`, because either one leaves part of the change unread.
2. Read every saved file, one at a time. On Codex, read each as [Read files](codex.md#read-files) says.
3. Check the last line. `<n>` must equal the count of rows and the count of saved files that you read to the end. A file that came back cut off is unread, so read its missing part before you judge the change. For each row marked `not shown`, read the file itself, with `git show :<name>` for a `staged` or `--cached` row and `git show <revision>:<name>` when the range ends at a commit, or report that file as unread. If the command exits with an error, the change is unread and the script has already removed its directory. Report the error line and stop.
4. Remove the directory that holds the index file once you have judged the change.

## Inspect running processes

1. Read the runtime's native agent or task list. Report what it tracks and which children remain live or have unknown status.
2. Identify the session's OS PID from a runtime receipt or its verified process ancestry. A shell command's `$$` is that command's shell, not necessarily the long-lived session process. Record the chosen PID and why it belongs to this session.
3. Take an OS process snapshot. On macOS and Linux, this command includes the parent PID, process group, terminal, elapsed time, and command:

   ```sh
   ps -axo pid=,ppid=,pgid=,tty=,etime=,command=
   ```

   Walk parent PIDs from the command or runtime PID to the session process. Then follow every descendant whose parent PID is in that tree. Include shell, PTY, runner, and worker processes even when the native task list omits them. Check related process groups and terminals for reparented workers. Label uncertain ownership instead of assigning every process on the host to this session.
4. If the session uses a container, identify that exact container and inspect its process namespace too. Use its available process tools through the configured container runtime, such as `docker compose exec -T <service> ps -ef`. A host snapshot alone can hide the container's workers. Do not start a new container or assume it has `ps` just to answer the question.
5. Recheck relevant PIDs before reporting. Processes can exit or reparent between snapshots. Distinguish native agents, observed OS workers, and unknown ownership. If a namespace or process list is unavailable, report that gap. A native list with no active agents does not establish that no background work is running.

Process discovery grants inspection, not permission to terminate unrelated processes. Keep command lines private when they contain credentials or user data.
