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

1. Save each changed file's diff to its own file. Run this in bash or zsh as printed, with your range on the first line:

   ```sh
   set -- <range>
   d=$(mktemp -d); r=$(git rev-parse --show-toplevel); n=0
   git diff -z --name-status "$@" | while IFS= read -r -d '' s && IFS= read -r -d '' a; do
   	b=$a; case $s in [RC]*) IFS= read -r -d '' b ;; esac
   	n=$((n + 1)); git -C "$r" --literal-pathspecs diff "$@" -- "$a" "$b" > "$d/$n.diff"
   	printf '%s\n' "$(wc -c < "$d/$n.diff") $d/$n.diff $s $b"
   done
   git -C "$r" ls-files -z --others --exclude-standard | while IFS= read -r -d '' a; do
   	n=$((n + 1)); git -C "$r" diff --no-index -- /dev/null "$a" > "$d/new-$n.diff"
   	printf '%s\n' "$(wc -c < "$d/new-$n.diff") $d/new-$n.diff ?? $a"
   done
   ```

   Each printed line gives a byte count, the saved file, the status, and the changed file's name. The second loop saves each untracked file whole, because `git diff` never shows one. When `<range>` compares two commits, leave that loop out. Let the loop pass every path. A path you copy from a git listing can match no file and print nothing, because git prints some names quoted and `--stat` shortens them. A renamed file needs both of its paths. The new path alone shows the whole file as added, and the old path alone shows it as deleted.
2. Read every saved file, one at a time. On Codex, read each as [Read files](codex.md#read-files) says.
3. Check that you read each file that step 1 printed, to its end. A byte count of 0 means git returned nothing for that file, so report the file as unread and stop. A file that came back cut off is unread, so read its missing part before you judge the change.

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
