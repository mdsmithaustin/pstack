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

Read without a cap any diff, test file, or code that you will judge. Never pipe it through `head`, `tail`, or a line limit. A cap on search, log, or listing output is fine. When a skill tells you to print one part of a file, such as one playbook step, you need only that part, and it must arrive uncut.

1. List the changed files with `git diff --name-only <range>`. Do not list them with `--stat`, which shortens a long path to one that matches no file.
2. Read `git diff <range> -- <file>` for one file at a time. On Codex, read each file's diff as [Read files](codex.md#read-files) says.
3. Check that the files you read are the files that step 1 lists. A file whose diff came back cut off is unread, so read its missing part before you judge the change.

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
