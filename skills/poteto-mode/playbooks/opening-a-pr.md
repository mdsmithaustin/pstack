### Opening a PR

Use when the matched playbook produces a PR.

Read this playbook in full. It has no numbered steps.

**Worktree.** Work from a git worktree off main. Subagents inherit it. Multiple `Task` calls on the same branch each get their own worktree, or `git fetch && git reset --hard origin/<branch>` between them. Dirty branch with unrelated work: patch out, fresh worktree, apply. Snarled worktree: reset from main, redo minimally.

**Commits.** Commit liberally. Rebase into small, ordered commits before opening PRs. Each commit is a future PR: landable, ordered to tell the story. Amend when the fix belongs in a just-made commit. New commit when separable.

**PRs.** Run `/deslop` over the diff before commit. Run `/no-comments` before review. Write every PR title, PR description, and commit body with `/technical-writing`, then apply `/unslop`. Apply every technical-writing layer except Diátaxis. Use one word for each action, keep articles, and avoid `-ing` when a plain verb works.

**Titles.** Use Conventional Commits in the form `type(scope): subject`. Use `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, or `perf` as the type. Use the changed area, such as `pstack` or `poteto-mode`, as the scope. Keep the subject short and imperative. Name a real symbol when one carries the change. For example, `fix(pstack): retarget opening-a-pr babysit trigger`. Do not add a trailing period.

**Descriptions.** The PR body is a briefing, not the lab notebook. A reviewer who has the diff should learn why the change exists, what it leaves out, what it could break, and how you proved it works, in under a minute. Write short, simple sentences with few identifiers. Do not write walls of text. The squash commit body is the PR body. If the body would make the squash commit longer than about 40 lines, cut the body.

Put each section under a `##` heading, not a bold lead-in, so the sections stand apart. Use these sections in order. Drop a section when it has nothing to say.

- `## Why` gives the problem and the approach in one to three short sentences. Do not list SHAs or rebase genealogy. Do not add a "based on main" preamble.
- `## What changed` has one to three short bullets. Name a real symbol or path only when it carries the change. Name both sides of a rename or retarget.
- `## Scope` always names what the PR covers and what it deliberately leaves out, for example a related follow-up or a known gap. Use one to three short items. Do not list symbols or paths, and do not write a file-by-file essay.
- `## Tradeoffs` names only rejected alternatives that a reviewer would otherwise ask about. Skip this section when there was no real choice.
- `## Blast Radius` gives one or two sentences on who or what the change touches and why that is safe or risky. If main is red, state the cost of leaving it red.
- `## Verification` has one to three bullets. Each bullet names a real run path and its outcome. For a performance change, report one primary number with its unit in `before → after` form. Link the arena or swarm directory for the remaining evidence. Do not include sample-size methodology, swarm recitals, or metric tables.

After these sections, attach videos or screenshots when they prove a claim, and follow any attachment rule the repo's `AGENTS.md` or PR template sets, such as a Demo section. Do not paste full SHAs, swarm or arena lane recitals, lever-correction essays, file-by-file checklists, or "CLEAN" verdicts. Put these details in a linked artifact. A commit body does not restate its subject.

**Forge.** Resolve the forge before the first PR operation and keep that choice for create, edit, view, watch, and merge. GitHub CLI (`gh`) is the default. If `command -v origin` succeeds and Origin can resolve the repository, prefer `origin pr ...`. If Origin is absent or cannot resolve the repository, stay on `gh` and record the fallback. Do not require Graphite (`gt`).

**Gated publish.** Resolve the publish path with the forge, before the first push.

- When `NO_MISTAKES_GATE` is set, you are a no-mistakes pipeline step. Never push, open a PR, or start a run.
- When `SANDBOX_NAME` is set, you run in a sandbox clone, which has no `no-mistakes` remote. When your brief says the repository is gated, or the repository commits `.no-mistakes.yaml`, commit on a feature branch and never push. Report the branch, the head SHA, and that a gated publish is needed. The host fetches the branch from its `sandbox-<name>` remote and publishes it.
- Otherwise the repository is gated when `git remote get-url no-mistakes` succeeds and `no-mistakes axi` prints no `error:`. When the remote exists but `no-mistakes axi` prints `error:`, the gate is broken. Stop and report the error. When the repository commits `.no-mistakes.yaml` but has no `no-mistakes` remote, stop and report that `no-mistakes init` is needed.
- When you launch a sandboxed agent on a gated repository, say in its brief that the repository is gated.

In a gated repository, the gate owns every write to the push target and every PR it opens. These rules override every push, rebase, PR creation, and retarget in other playbooks, which apply only to ungated repositories. When the no-mistakes skill is installed, read it and follow its run, gate, and `branch_sync` rules. Otherwise use `no-mistakes axi --help`.

- Never run `git push` or `git push --force-with-lease` to the push target. Publish a branch and open its PR with `no-mistakes axi run --intent-file <file> --no-publish-intent`. Write the user's goal and decisions into the intent file. For a stacked child, add `--base-branch <parent-branch>`. To reattach after a wait, run `no-mistakes axi run` with no intent.
- Never create or retarget the PR with a forge CLI or a built-in PR tool.
- Never rebase a published branch by hand. While a run or its CI monitor is live, it rebases on conflict, so leave the branch to it. After a terminal outcome, or once the monitor has stopped, restack or retarget with `no-mistakes rerun --base-branch <new-base>`.
- Push work-in-progress snapshots only to `refs/pstack/wip/<branch>` on origin. When the repository's AGENTS.md, CLAUDE.md, or CONTRIBUTING names a branch or ref convention for agent work, use that convention. When the remote rejects the ref, keep snapshots local and record why. Do not retry under another name. Delete the snapshot ref after the PR merges.
- Before any local commit or `rerun` on a published branch, read `branch_sync` and follow its `next_action`. Commit only when it allows a commit.
- Relay an `ask-user` finding verbatim to the user, or from a subagent to its parent. Pass `--yes` only when the user's grant names no-mistakes.
- When `no-mistakes doctor` fails or the gate cannot run, stop and report. Publish around the gate only when the user said "bypass no-mistakes" in this session.
- After each run, check the pipeline's PR title against **Titles** and correct it with the forge. The squash body comes from `merge-gate --body-file` in `playbooks/shipping.md`.
- `axi run` and `axi respond` block for up to 8 minutes. Give each call a tool timeout of 10 minutes. `rerun` has no `--wait` flag, so run it in the background and read its output when it exits.

**Attachments.** Upload through the forge, not a browser. With Origin, use its attach flag when `origin pr create --help` lists one. Otherwise, for a GitHub repository, use `gh`, whichever CLI opened the PR. Pass `--attach <path>` to `gh pr create`, `gh pr edit`, or `gh pr comment`, once per file, with alt text after `#` (`--attach './login.png#The login error'`). A body that references the local path, such as `![alt](./login.png)`, gets that reference rewritten to the upload. `--attach` needs gh 2.99.0 or later and push access. When `gh pr edit --help` does not list it, run a gh at 2.99.0 or later. Do not upload through undocumented endpoints.

After posting, read the PR back with `gh pr view <number> --json body,comments` and request each `https://github.com/user-attachments/assets/` URL with `curl -s -o /dev/null -w '%{http_code}' -L -H "Authorization: Bearer $(gh auth token)" <url>`. It must return `200`. A signed-out request can fail on a working upload, so it proves nothing. When a URL does not return `200`, attach the file again once. Report an upload blocker only when no gh at 2.99.0 or later is available or the retry fails, and quote the gh version and the error.

**Built-in PR tool.** In a gated repository, follow **Gated publish** instead. When the run provides a built-in PR tool, create, edit, retarget, and mark ready through it, never through a forge CLI. Its own instructions say how. A PR made with the CLI misses what the tool tracks, such as a description later runs can edit. Use the resolved forge for everything the tool does not cover, and for every PR operation when the run has no such tool.

**Size and stacks.** Prefer five narrow PRs to one large PR. In a gated repository, build stacks through **Gated publish**. A stack is a base-branch chain. The root PR targets trunk. Each child branch rebases onto its parent's exact tip and its PR targets the parent branch. Without a built-in PR tool, create a child with `origin pr create --status open --base <parent-branch>` or `gh pr create --base <parent-branch>` according to the resolved forge, and retarget an existing child with `origin pr edit <pr> --base <parent-branch>` or `gh pr edit <pr> --base <parent-branch>`. Branch from trunk only for independent work. Rebase on trunk before substantial stack work.

**Readiness.** Open every PR ready, never as a draft. A built-in PR tool can default to draft, so set `draft: false` on every creation call through it. With Origin, pass `--status open`. With `gh`, omit `--draft`. If a PR still opens as a draft, mark it ready through the PR tool, or run `origin pr ready <number>` or `gh pr ready <number>` according to the resolved forge. Run `origin pr view <number>` or `gh pr view <number>` before you refer to PR status.

**Babysit.** Opening a PR does not start a babysit. Post the URL and keep building. Finish the phase or stack first. Run a separate babysit pass only when the user asks for one after the whole stack exists. A babysit for each new PR stalls the build and spends checks on commits that later waves restart. Push back when feedback drifts from intent.

A subagent that opens a PR runs `interrogate`, `/deslop`, and `/no-comments`, and posts the URL. Then it returns to the parent without babysitting, unless it is an Autopilot-full or Autopilot-stack owner. That owner's brief assigns the babysit loop and is the ask `playbooks/babysit.md` waits for. The owner starts the loop after its code-ready report and reports merge-ready or STACK-READY as its playbook says. The rules here and in `playbooks/babysit.md` that hold babysitting until a whole stack is built do not apply to that owner.
