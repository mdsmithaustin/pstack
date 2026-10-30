# Set up pstack

In this page you install the skills, pick which models pstack uses, and run your first task. Setup is one command plus a short conversation.

## Install the skills

From your project root, run:

```sh
npx skills add mdsmithaustin/pstack
```

Choose the targets you use, including `hermes-agent` for Hermes. The installer delivers the skills and bundled personas. Hermes requires trust for project skills, and its project link can be skipped when `.hermes` does not exist. For global Hermes use, install into its native skills directory or configure `skills.external_dirs` for the shared `~/.agents/skills` directory. Some skills don't load from their description. They load when you type their name or when another pstack skill tells the agent to use them. Codex honors this as installed, and Claude Code does once `/setup-pstack` sets its skill listing. An agent that lists the skills folder can still open one of these skills by its folder name. The [promise suite's known gap](../../evals/promises/README.md#run-live-cases) explains this limitation and links the observed results. In the 2026-10-03 run of the guide-promise evals, Hermes and Grok Build loaded such a skill without being asked. Confirm discovery in your installed version.

## Pick your models

Run:

```text
/setup-pstack
```

[`/setup-pstack`](../../skills/setup-pstack/SKILL.md) first checks both bundled personas and offers optional native registration for Claude Code or Codex. Choose project or user scope if you want native agent files. Setup preserves existing user-managed agent files and reports payload readiness, native files, and live agent loading separately. `npx skills update` does not refresh registered agent files, so rerun `/setup-pstack` after an update. It finds the personas and, on Claude Code, the five `pstack-effort-<level>` agents that an older version generated, and offers to refresh them. A generic delegate can receive the complete persona while native loading remains unverified. Hermes uses that briefing through delegation context, and Grok Build gets it in each spawn prompt.

Setup also checks whether Claude Code's task tools and Codex's plan tool are on, because `/poteto-mode` keeps its worklist in them. When one is off, setup shows you the exact setting and writes it only if you say yes. On Claude Code it also checks the skill listing, and with your yes it lists the skills that don't load from their description by name only, from your next session. Until then, including after an update from a version that gated those skills in their frontmatter, Claude Code shows their descriptions and can load them on its own. On Codex it also checks whether native subagent spawning is available, because without it pstack runs each role through a `codex exec` subprocess or inline, and an inline review is not independent. When a Codex session shows spawning is missing and a config file holds a key that could cause it, setup names that key as a possible cause and may offer to change it, editing only with your yes. Otherwise it reports what it saw and the causes it cannot rule out.

Setup then detects the models you have access to, asks for a reasoning budget, shows you each role (code delegates, judgment, the review panels), and asks what you want. Answer the questions. It writes `~/.agents/pstack-models.md`, a small file that every pstack spawn reads through `check-models-config.py --resolve`. Each role maps to a model and, when you want to pin it, a reasoning effort (`sonnet@high`). On Claude Code a written effort applies once setup has registered pstack's effort agents. Until then subagents run at your session effort. A `## codex` section holds the picks that apply only on Codex, so one file serves every CLI you use.

The shipped defaults write no effort on their flat lines except `routine`, which writes `medium`, and the `default` budget keeps what is written. On Claude Code and Grok Build a role with no written effort runs at your session effort, and on Codex the `## codex` section pins its own. The other budgets write one effort on every role that names a model: `unlimited` writes `max`, `large` writes `xhigh`, `medium` writes `high`, and `small` writes `medium`. On Claude Code and Codex a written effort replaces your session effort, whether it is higher or lower. Grok Build's spawn tool takes no effort, so there every role runs at your session effort, whatever the file writes.

You only override what you care about. A role with no line in the rule keeps the skill's default. To restore a default, delete that role's line. A rerun of `/setup-pstack` keeps any role you changed, whether its model, effort, panel list, alias, or harness section. A config written before the panels shrank to three entries still lists four panel entries, so delete those panel lines, including any under `## codex`, or delete the file, then run `/setup-pstack` again.

You might be wondering what happens if you use Auto. Set a role to `inherit-parent` or `auto` and pstack omits the subagent `model` field, so the subagent inherits your parent chat model. Both values mean the same thing, and neither is a model slug. For a panel role the value is a list, and one subagent runs per entry, so the list length sets the panel size. Setup also configures `swarm workers`, the model for every `/swarm` worker that runs something, unless a race names a model for each arm. A swarm worker that reads and judges a diff runs on `trail reviewer` instead. Setup also configures `routine`, the model for read-only subagents that scan or parse bulk material, such as a long transcript, and return a short finding.

## Accept the verification offers, or don't

At the end of setup, `/setup-pstack` looks for a way to prove app behavior in your project, either a `verify-*` skill or an existing harness. If it finds neither, it offers once to generate one with [`/create-verification-skill`](../../skills/create-verification-skill/SKILL.md).

Say yes and it writes `.agents/skills/verify-<app>/`, a project-local skill that teaches agents to drive your app the way a user does. It proves the skill works once before handing it over. Say no and setup moves on. You can run `/create-verification-skill` yourself any time. [Verify and ship](./06-verify-and-ship.md#create-a-project-verification-skill) covers it in depth.

If you're new to pstack, say yes. An agent that can check its own work keeps going until the check passes. An agent that can't hands every result back to you to check by hand. Of everything in this guide, the verification skill pays off the most.

Then setup offers once to generate a formal verification skill with [`/create-formal-verification-skill`](../../skills/create-formal-verification-skill/SKILL.md), unless the project already has one. Tests check the cases someone thought to write. A formal verification skill checks one key property of your code, such as "a job never runs twice at once", in every case within a stated scope. Say yes when your code has concurrency, retries, a state machine, or a parser, where a bug is costly and tests rarely reach the case that breaks. Otherwise say no, and run it later if that changes. [Verify and ship](./06-verify-and-ship.md#prove-a-property-with-a-formal-verification-skill) covers it.

Skills read the model configuration when they next run. Codex project agents also require project trust. After registering native agents, start a fresh session and confirm that its live agent catalog lists them. Setup does not change trust settings.

## Keep the cost in check

pstack spends extra tokens on subagents and review panels. That's the price of the rigor. To spend fewer:

- Rerun `/setup-pstack` and pick a smaller reasoning budget or cheaper models. A strong model in the main chat with cheaper, faster models in the code roles is a good split.
- Set a role to `auto` or `inherit-parent` so it runs on the chat's own model.
- Shorten a panel list. Each entry runs one subagent.
- Save `/poteto-mode` for work that needs rigor. A small, obvious edit doesn't.

## Run your first task

Pick something real but small, and describe it the way you'd describe it to a colleague:

```text
/poteto-mode add a --json flag to this command. text output stays byte-identical. verify both.
```

Watch the todo list, or the numbered list in chat that `/poteto-mode` requires when the task tools are off. Its first items are the matched playbook's opening prose and steps copied in, the Feature playbook for this prompt. If `/poteto-mode` skips a step, the step stays in the list with `skipped: <reason>`, so you can see what it chose not to do. In a repository with a remote, the run ends by pushing a branch and opening a PR. Add "no PR" to the prompt to stop at local commits, as [Open the PR](./06-verify-and-ship.md#open-the-pr) explains. The [retained runs](../../PORTING.md#guide-promise-fixes) met the full fallback requirement in only 1 of 3 Claude Code runs and did not show reliable compliance on Hermes.

From here you can type normal follow-ups. `/poteto-mode` is sticky. It stays on for the conversation until you opt out by saying so. See the [README](../../README.md#usage) for continuation after compaction and what to do if the mode stops applying.

Next: [Route work through `/poteto-mode`](./02-poteto-mode.md).
