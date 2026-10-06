# Set up pstack

In this page you install the skills, pick which models pstack uses, and run your first task. Setup is one command plus a short conversation.

## Install the skills

From your project root, run:

```sh
npx skills add mdsmithaustin/pstack
```

Choose the targets you use, including `hermes-agent` for Hermes. The installer delivers the skills and bundled personas. Hermes requires trust for project skills, and its project link can be skipped when `.hermes` does not exist. For global Hermes use, install into its native skills directory or configure `skills.external_dirs` for the shared `~/.agents/skills` directory. Confirm discovery in your installed version.

## Pick your models

Run:

```text
/setup-pstack
```

[`/setup-pstack`](../../skills/setup-pstack/SKILL.md) first checks both bundled personas and offers optional native registration for Claude Code or Codex. Choose project or user scope if you want native agent files. Setup preserves existing user-managed agent files and reports payload readiness, native files, and live agent loading separately. `npx skills update` does not refresh registered agent files, so rerun `/setup-pstack` after an update. It finds the personas and, on Claude Code, the five `pstack-effort-<level>` agents that an older version generated, and offers to refresh them. A generic delegate can receive the complete persona while native loading remains unverified. Hermes uses that briefing through delegation context, and Grok Build gets it in each spawn prompt.

Setup also checks whether Claude Code's task tools and Codex's plan tool are on, because `/poteto-mode` keeps its worklist in them. When one is off, setup shows you the exact setting and writes it only if you say yes. On Codex it also checks whether native subagent spawning is available, because without it pstack runs each role through a `codex exec` subprocess or inline, and an inline review is not independent. When a Codex session shows spawning is missing and a config file holds a key that could cause it, setup names that key as a possible cause and may offer to change it, editing only with your yes. Otherwise it reports what it saw and the causes it cannot rule out.

Setup then detects the models you have access to, asks for a reasoning budget, shows you each role (code delegates, judgment, the review panels), and asks what you want. Answer the questions. It writes `~/.agents/pstack-models.md`, a small file that every pstack spawn reads through `check-models-config.py --resolve`. Each role maps to a model and, when you want to pin it, a reasoning effort (`sonnet@high`). On Claude Code a written effort applies once setup has registered pstack's effort agents. Until then subagents run at your session effort. A `## codex` section holds the picks that apply only on Codex, so one file serves every CLI you use.

You only override what you care about. A role with no line in the rule keeps the skill's default. To restore a default, delete that role's line. A rerun of `/setup-pstack` keeps any role you changed, whether its model, effort, panel list, alias, or harness section. A config written before the panels shrank to three entries still lists four panel entries, so delete those panel lines, including any under `## codex`, or delete the file, then run `/setup-pstack` again.

You might be wondering what happens if you use Auto. Set a role to `inherit-parent` or `auto` and pstack omits the subagent `model` field, so the subagent inherits your parent chat model. Both values mean the same thing, and neither is a model slug. For a panel role the value is a list, and one subagent runs per entry, so the list length sets the panel size. Setup also configures `swarm workers`, the model for every `/swarm` worker that runs something, unless a race names a model for each arm. A swarm worker that reads and judges a diff runs on `trail reviewer` instead.

## Accept the verification offer, or don't

At the end of setup, `/setup-pstack` looks for a way to prove app behavior in your project, either a `verify-*` skill or an existing harness. If it finds neither, it offers once to generate one with [`/create-verification-skill`](../../skills/create-verification-skill/SKILL.md).

Say yes and it writes `.agents/skills/verify-<app>/`, a project-local skill that teaches agents to drive your app the way a user does. It proves the skill works once before handing it over. Say no and setup moves on. You can run `/create-verification-skill` yourself any time. [Verify and ship](./06-verify-and-ship.md#create-a-project-verification-skill) covers when it earns its place.

Skills read the model configuration when they next run. Codex project agents also require project trust. After registering native agents, start a fresh session and confirm that its live agent catalog lists them. Setup does not change trust settings.

## Run your first task

Pick something real but small, and describe it the way you'd describe it to a colleague:

```text
/poteto-mode add a --json flag to this command. text output stays byte-identical. verify both.
```

Watch the todo list, or the numbered list in chat when the task tools are off. Its first items are the matched playbook's opening prose and steps copied in, the Feature playbook for this prompt. If `/poteto-mode` skips a step, the step stays in the list with `skipped: <reason>`, so you can see what it chose not to do.

From here you can type normal follow-ups. `/poteto-mode` is sticky. It stays on for the conversation until you opt out by saying so.

Next: [Route work through `/poteto-mode`](./02-poteto-mode.md).
