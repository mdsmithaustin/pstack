# pstack

> this is a CLI-agnostic port of [cursor/plugins/pstack](https://github.com/cursor/plugins/tree/main/pstack) by [poteto](https://x.com/poteto), reworked to install with [`npx skills`](https://skills.sh) and run in **Claude Code**, **Codex**, **Hermes**, and **Grok Build**. the workflows are poteto's; [PORTING.md](./PORTING.md) records the port changes.

This repository is an independent community port. It is not affiliated with, maintained by, or endorsed by Poteto. It aims to stay in sync with her upstream work while adapting it to these CLIs.

For this port's agreed goals, evidence standards, and remaining measurement gaps,
see the [suite outcomes and evaluation contract](./evals/framework.md).

The introduction below is reproduced from upstream in Poteto's voice. Further down, a section written in lowercase first person is also hers. Sentence-case sections are this port's.

i'm [poteto](https://x.com/poteto). i'm not a president or ceo, but i've worked with millions of lines of code at Meta, Netflix, and Cursor. i'm also on the react core team where i help build and maintain react compiler.

there's a growing sense that ai writes too much slop code. i agree. i don't want to ship like a team of twenty slop artists. throughput without quality is not a goal i aspire to. if you want to go fast, go deep first. 

**pstack is my answer.** these are the same skills i use every day to ship high quality code. this turns your coding agent into a real engineering team. the goal is not to maximize loc, in fact it's the opposite. pstack helps you write less, but higher quality code.

**pstack gives you fearless parallelism.** when you can go deep on one agent and trust it to write good, verifiable code, you can truly parallelize with confidence. start multiple agents up with `poteto-mode` and trust that they'll apply rigorous engineering principles to their work.

**every frontier model has its strengths and weaknesses.** use any model with pstack. in fact, many of my skills use multi-model workflows to take advantage of each model's unique strengths (in CLIs that can switch models per subagent; elsewhere pstack skips a design comparison when its model resolver marks every arm as your session model, and the other panels keep their arm count).

fork it. improve it. make it yours. PRs are welcome! 

## what this port adds

Upstream pstack is a Cursor plugin. This port keeps Poteto's workflows and goes further in six places. [PORTING.md](./PORTING.md) records every change.

- **Four CLIs from one install.** The suite runs in Claude Code, Codex, Hermes, and Grok Build. [`/pstack-harness`](./skills/pstack-harness/SKILL.md) maps each workflow step (spawn, wait, ask, track, loop) to the CLI you are in. One [models config](#make-it-yours) sets a model and a reasoning effort for each role, with a section for each CLI.
- **Six skills that upstream pstack does not ship.** [`/deslop`](./skills/deslop/SKILL.md), [`/pr-recap`](./skills/pr-recap/SKILL.md), [`/documentation-impact`](./skills/documentation-impact/SKILL.md), [`/verify-commands`](./skills/verify-commands/SKILL.md), [`/spec-probes`](./skills/spec-probes/SKILL.md), and [`/runtime-probes`](./skills/runtime-probes/SKILL.md).
- **Two more playbooks.** [Research](./skills/poteto-mode/playbooks/research.md) gathers outside evidence for a decision. [Code review](./skills/poteto-mode/playbooks/code-review.md) reviews someone else's branch without editing it.
- **Routes sized to risk.** Bug fix, feature, refactoring, and perf work record five risk facts, and a [plan script](./skills/poteto-mode/scripts/plan.py) picks a lightweight, standard, or intensive [route](./skills/poteto-mode/references/routes.md). The same facts give the same route on every CLI.
- **Stricter shipping.** A [PR watcher](./skills/poteto-mode/scripts/watch-pr/README.md) handles any review bot and PRs that have no CI. Merges go through a merge gate, and a merge always needs its own [authorization](./skills/poteto-mode/references/authorization.md).
- **Promises that are checked.** Each sentence in the [guide](./docs/guide/README.md) that promises a behavior is tracked in a [ledger](./evals/promises/README.md) and tied to a static, install, or live check. The [evaluation contract](./evals/framework.md) says what is still unmeasured.

## install

```bash
npx skills add mdsmithaustin/pstack
```

pick the targets you use at the prompt, including `hermes-agent` for hermes. `-g` installs user-level instead of per-project.

notes by CLI. confirm discovery in your installed version:

- **hermes.** project skills require project trust. for global use, install into its native skills directory or add the shared `~/.agents/skills` directory to `skills.external_dirs`. the installer may skip a project hermes symlink when `.hermes` does not exist.
- **grok build.** it skips project skills in a folder it does not trust.

## get started

two steps:

1. run [`/setup-pstack`](./skills/setup-pstack/SKILL.md). it checks the bundled personas, offers to register native agents, sets claude code's skill listing, and asks for a reasoning budget and models. rerun it after `npx skills update`: until the listing step runs, claude code shows every pstack skill's description and can load one on its own.
2. use [`/poteto-mode`](./skills/poteto-mode/SKILL.md) whenever you're doing anything that requires rigor.

new here? the [pstack guide](./docs/guide/README.md) walks you through a first real task, from setup and prompting through verification and overnight runs. stuck, or unsure which skill fits? ask [`/poteto-help`](./skills/poteto-help/SKILL.md).

that's it. the other skills are situational, and the mode skill uses them for you as needed. out of the box the mode splits work by model strength (using claude code's subagent model aliases): code delegates (feature, refactoring, bug fix, perf, hillclimb) go to sonnet, while the hardest changes, prose, and judgment go to opus. the default panel is fable / opus / sonnet. the [models config reference](./skills/setup-pstack/references/models-config.md#resolution) defines alias translation, model fallbacks, and reasoning effort for each CLI. [Spawn a role](./skills/pstack-harness/SKILL.md#spawn-a-role) explains how each CLI applies those choices. [`/setup-pstack`](./skills/setup-pstack/SKILL.md) changes any of it.

## usage

use [`/poteto-mode`](./skills/poteto-mode/SKILL.md) at the start of a task. it reads your request, picks from a set of playbooks, and runs the other skills as the steps need them.

### just use [`/poteto-mode`](./skills/poteto-mode/SKILL.md)

this skill is the main shortcut. i use it whenever i need the agent to do rigorous engineering work. it comes with twenty-five playbooks:

```
/poteto-mode this pr has a subtle bug where the scroll drifts every 750ms even when idle. repro
first, then fix and verify.
```

```
/poteto-mode i'm going to bed. land the stack even if ci flakes. i want everything merged by
morning.
```

<details>
<summary>the twenty-five playbooks</summary>

| playbook | for |
|---|---|
| [investigation](./skills/poteto-mode/playbooks/investigation.md) | a read-only question about current code or its history. how does x work, why was y built this way, are we sure. |
| [research](./skills/poteto-mode/playbooks/research.md) (port addition) | external, domain, or dependency evidence for a decision, with sources and explicit gaps. |
| [code review](./skills/poteto-mode/playbooks/code-review.md) (port addition) | review someone else's pr, branch, or diff for design and correctness before it merges, with the review lens and no edits to their branch. |
| [bug fix](./skills/poteto-mode/playbooks/bug-fix.md) | reproduce a defect, root-cause it, and fix with runtime evidence. |
| [perf](./skills/poteto-mode/playbooks/perf-issue.md) | trace a measured slowness and improve it against a baseline. |
| [hillclimb](./skills/poteto-mode/playbooks/hillclimb.md) | sustained, scientific improvement of one metric against a target, looping hypotheses with before/after measurement and one commit per accepted win. |
| [runtime forensics](./skills/poteto-mode/playbooks/runtime-forensics.md) | diagnose a live symptom (leak, idle-cpu spin, glitch) from instrumentation. |
| [trace forensics](./skills/poteto-mode/playbooks/trace-forensics.md) | diagnose a captured profiling artifact (cpuprofile, trace, spindump, heap snapshot). |
| [feature](./skills/poteto-mode/playbooks/feature.md) | new or changed behavior, built from a named data shape. |
| [refactoring](./skills/poteto-mode/playbooks/refactoring.md) | a behavior-preserving change to structure or shape. |
| [prototype](./skills/poteto-mode/playbooks/prototype.md) | a throwaway sketch to make a design or behavioral decision cheaply, or to settle an empirical fork by observing it. |
| [visual parity](./skills/poteto-mode/playbooks/visual-parity.md) | pixel-exact ui equivalence between two implementations. |
| [authoring a skill](./skills/poteto-mode/playbooks/authoring-a-skill.md) | writing or editing a SKILL.md. |
| [eval](./skills/poteto-mode/playbooks/eval.md) | test how a skill or prompt change affects agent behavior, blinded. |
| [babysit](./skills/poteto-mode/playbooks/babysit.md) | drive a pr or a stack to merge-ready: conflicts, review threads, ci. |
| [shipping](./skills/poteto-mode/playbooks/shipping.md) | independently verify a green stack, then land the contiguous verified run bottom-up through github by default or origin when available. |
| [autonomous run](./skills/poteto-mode/playbooks/autonomous-run.md) | drive a long task to completion without stopping. |
| [orchestrate](./skills/poteto-mode/playbooks/orchestrate.md) | a standing project handed to one coordinator chat: multi-day, many stacked prs, fleets of subagents. |
| [autopilot-full](./skills/poteto-mode/playbooks/autopilot-full.md) | run independent prs to merged with one owner per pr. a swarm verifies each code-ready head, and every later change to the patch gets a fresh check. |
| [autopilot-stack](./skills/poteto-mode/playbooks/autopilot-stack.md) | autopilot-full without the merge. build and verify prs for the operator to review and land, stacking a pr only on a pr it builds on. |
| [session pickup](./skills/poteto-mode/playbooks/session-pickup.md) | resume or take over a prior agent's in-flight work. |
| [pause safely](./skills/poteto-mode/playbooks/pause-safely.md) | suspend in-flight work cleanly so it can be resumed later. |
| [multi-phase plan](./skills/poteto-mode/playbooks/multi-phase-plan.md) | work that spans phases or stacked PRs. |
| [worktree cleanup](./skills/poteto-mode/playbooks/worktree-cleanup.md) | reclaim disk by pruning merged or abandoned worktrees and stale ios simulators, safety-gated. |
| [opening a pr](./skills/poteto-mode/playbooks/opening-a-pr.md) | open a ready pr from small ordered commits with a conventional commits title and a briefing-style body, when the matched playbook produces a pr. |

</details>

when invoked it:

1. matches your task to a [playbook](./skills/poteto-mode/playbooks/) and tracks progress under the mode's [worklist and completion rules](./skills/poteto-mode/SKILL.md#playbooks).
2. for bug fix, feature, refactoring, and perf work, records five risk facts and lets a [plan script](./skills/poteto-mode/scripts/plan.py) pick a lightweight, standard, or intensive [route](./skills/poteto-mode/references/routes.md). say `keep this lightweight` or `be thorough` to set the route yourself.
3. routes to the other skills as the steps fire.
4. writes unslopped replies framed for the consumer and the maintainer.

the mode's [Playbooks section](./skills/poteto-mode/SKILL.md#playbooks) also owns the preservation gate required before every commit. the task runs to the endpoint you state. without one it stops at the furthest reviewable state your repository supports: a pull request, a pushed branch, or a local branch when there is no remote. the mode is designed to work with a mid-tier model in the lead, such as Sonnet 5.5, GPT-6.1 Sol, or Grok 4.7 at medium effort. that target is a design goal that no evaluation here has verified yet, as the [evaluation contract](./evals/framework.md#lead-model-floor-and-subtraction) records. the full rules and playbooks live in [`skills/poteto-mode/SKILL.md`](./skills/poteto-mode/SKILL.md).

[`/poteto-mode`](./skills/poteto-mode/SKILL.md) is also a sticky mode: once entered it stays on across turns, applying itself when a playbook matches or the task needs rigor and staying out of the way otherwise. opt out any time by saying so. after known compaction or truncation, the agent follows the mode's [recovery rule](./skills/poteto-mode/SKILL.md#recover-after-compaction-or-truncation) to continue the current task. runtime retention varies; see the [dated evidence](./skills/pstack-harness/references/skill-retention.md). if the mode stops applying, type `/poteto-mode` again.

[`/poteto-mode`](./skills/poteto-mode/SKILL.md) works extremely well with a loop mechanism (claude code's `/loop`, or any re-invoking heartbeat). you can make your agent work for many hours without sacrificing rigor.

## skills

[`/poteto-mode`](./skills/poteto-mode/SKILL.md) runs most of these for you when a step needs them (`how`, `why`, `architect`, `arena`, `swarm`, `interrogate`, `deslop`, `unslop`, `no-comments`, `technical-writing`, `poteto-tdd`, and the principles). the table below is for when you want one directly. most skills load only when you type their name or the mode calls them. [`/poteto-help`](./skills/poteto-help/SKILL.md#fix-a-run-that-went-wrong) lists the few that also load from your words.

```
/how do we cancel runs? do we have an n+1 when we look up every run to cancel?
```

```
/interrogate review this pr.
```

<details>
<summary>all skills</summary>

| skill | use it when |
|---|---|
| [`/poteto-mode`](./skills/poteto-mode/SKILL.md) | default entry point for any non-trivial task. |
| [`/poteto-help`](./skills/poteto-help/SKILL.md) | you're new to pstack, or unsure which skill, playbook, or principle fits. finds out what you're trying to do, answers that part, and hands you a prompt to type. |
| [`/in-your-own-words`](./skills/in-your-own-words/SKILL.md) | you want the agent to play back your goal and the problem before it starts. |
| [`/sharpen`](./skills/sharpen/SKILL.md) | you want a prompt made deeper, not bigger, before you send it. hands back the rewritten prompt and leaves your choices open. doesn't do the task. |
| [`/how`](./skills/how/SKILL.md) | you want a walkthrough of how a subsystem works. |
| [`/why`](./skills/why/SKILL.md) | you want to know why something was built this way. discovers available MCPs at run time and queries each evidence category in parallel (source control, issue tracker, long-form docs, real-time chat, infra observability, error tracking, analytics warehouse). |
| [`/recall`](./skills/recall/SKILL.md) | you're starting or resuming work and want your recent context on a topic rebuilt from your own chat history and the shared record, handed back as a tight current-state brief. |
| [`/ketchup`](./skills/ketchup/SKILL.md) | you want what changed in this chat since your last message, in plain words and small visuals, with every item waiting on you listed and decidable from the reply alone, even when that makes the reply long. |
| [`/ketchup-video`](./skills/ketchup-video/SKILL.md) | you want the `/ketchup` catch-up as a short subtitled video of slides, with the calls waiting on you as text under it. |
| [`/blast-radius`](./skills/blast-radius/SKILL.md) | you have a small-looking change and want to know what else it could break, with the one fact it's safe because of proven by running code, not asserted. |
| [`/architect`](./skills/architect/SKILL.md) | you're about to write code that crosses a function boundary and want the caller's usage, types, and module shape settled first. |
| [`/arena`](./skills/arena/SKILL.md) | you want N parallel attempts at the same thing, then to grab the best parts of each. |
| [`/swarm`](./skills/swarm/SKILL.md) | you want N parallel workers across different slices or races, then one aggregated report. |
| [`/interrogate`](./skills/interrogate/SKILL.md) | you have a diff and want different models to try to break it, keeping only findings a run proves. |
| [`/automate-me`](./skills/automate-me/SKILL.md) | you want your own `-mode` skill, drafted from how you've actually worked. |
| [`/make-bot-ui`](./skills/make-bot-ui/SKILL.md) | you want a page or dashboard whose buttons wake a Grok Bot over a webhook, including the sender-key handoff and Tailscale. |
| [`/setup-pstack`](./skills/setup-pstack/SKILL.md) | you want to configure pstack models or repository PR templates. full setup preserves existing templates and installs poteto defaults when none exist. |
| [`/pstack-harness`](./skills/pstack-harness/SKILL.md) | (port addition) maps spawning, per-subagent models, parallelism, and transcript access to claude code, codex, hermes, and grok build, with shared guidance for shell commands and running processes. |
| [`/reflect`](./skills/reflect/SKILL.md) | a long task landed and you want the recipe captured as a skill edit. |
| [`/correct`](./skills/correct/SKILL.md) | you keep correcting agents for the same mistakes. mines history for mistake classes and fixes each at the highest level that works, from architecture down to docs. |
| [`/poteto-teach`](./skills/poteto-teach/SKILL.md) | you want to actually understand a change or subsystem, not just have it summarized. runs how + why and weaves one plain explanation, built up diagram by diagram. |
| [`/poteto-tdd`](./skills/poteto-tdd/SKILL.md) | you're fixing a bug and there's a cheap local test path. write the failing test first, then the fix. |
| [`/benchmark-checklist`](./skills/benchmark-checklist/SKILL.md) | you ran a benchmark or measured a speedup or regression. vets the number (limiter, tuning, errors, repeat runs, end-to-end relevance) before you report or act on it. |
| [`/no-comments`](./skills/no-comments/SKILL.md) | strip comments before review; spawns Comment Sicko, fixes accepted findings, offers encodings for claimed constraints. |
| [`/pr-recap`](./skills/pr-recap/SKILL.md) | (port addition) you opened or pushed to a pull request and want its reviewers to see the story first. posts one comment: why and what, one hand-drawn sketch of the changed mechanism, and what the PR does not prove. see [sketch setup](./skills/pr-recap/references/sketch.md#setup) and [credits](./skills/pr-recap/CREDITS.md). |
| [`/deslop`](./skills/deslop/SKILL.md) | (port addition) you're about to commit and the diff reads padded. removes narrating comments, dead paths, one-caller wrappers, and unrelated edits from the changed hunks, then reruns the touched tests. code only; `/unslop` is for prose. |
| [`/typescript-best-practices`](./skills/typescript-best-practices/SKILL.md) | you're reading or editing typescript. grounds the type-system-discipline principle in syntax. |
| [`/figure-it-out`](./skills/figure-it-out/SKILL.md) | no bundled playbook fits. designs a rigorous, auditable playbook for the task. |
| [`/show-me-your-work`](./skills/show-me-your-work/SKILL.md) | you want a reviewable decision trail. owns the logging and evidence-retention rules. |
| [`/create-verification-skill`](./skills/create-verification-skill/SKILL.md) | your project has no scripted way to prove app behavior. generates a project-local verify skill with a feature map, for any language or platform. |
| [`/maintain-verification-skill`](./skills/maintain-verification-skill/SKILL.md) | your verify skill's feature map has drifted from the app. source wave + one live pass, at most one PR of proven corrections. |
| [`/create-formal-verification-skill`](./skills/create-formal-verification-skill/SKILL.md) | tests can't reach the case that breaks a race, retry, state machine, parser, or unsafe code. verifies one property with the tool that fits and generates a project-local skill to recheck it on every change. |
| [`/maintain-formal-verification-skill`](./skills/maintain-formal-verification-skill/SKILL.md) | code your formal verification covers has changed since it was last checked. updates the model, harness, or properties to match the code, reruns, and says whether each failure is drift in the verification or a bug in the code. |
| [`/statechart`](./skills/statechart/SKILL.md) | someone who owns the behavior needs to see it, not read a spec. checks a tla+ model, draws what the user sees as a mermaid statechart, marks each state that breaks a rule, and gives the shortest path to each one. |
| [`/spec-probes`](./skills/spec-probes/SKILL.md) | (port addition) you're writing a spec, acceptance criteria, or tickets, or deriving acceptance tests from a spec you cannot change. surfaces the data-shape edges and the must-nevers before implementation. |
| [`/verify-commands`](./skills/verify-commands/SKILL.md) | (port addition) you're writing or reviewing a completion check, or reporting an upgrade, deployment, migration, or install as successful. catches the shapes that pass green while measuring nothing. |
| [`/documentation-impact`](./skills/documentation-impact/SKILL.md) | (port addition) a change may affect user, operator, or developer instructions. updates affected docs or independently reviews them, including an evidenced no-change result. |
| [`/runtime-probes`](./skills/runtime-probes/SKILL.md) | (port addition) you want a live product, feature, or pr probed for unreported defects, or a source-grounded probe handoff while its target is unavailable. only findings a real caller can reach get promoted. |
| [`/unslop`](./skills/unslop/SKILL.md) | you're cleaning up writing. removes AI tells. |
| [`/bro`](./skills/bro/SKILL.md) | you want the last message restated in plain human language, no jargon. |
| [`/technical-writing`](./skills/technical-writing/SKILL.md) | layered doc standard (Diátaxis + Google developer style + STE + Global English) for docs, RFCs, readmes, PR descriptions, commit messages. |

</details>

### examples

mostly i type [`/poteto-mode`](./skills/poteto-mode/SKILL.md) at the start of a task and let it route to a playbook. the other skills fire as the steps need them. a few i reach for directly.

<details>
<summary>all the examples</summary>

```
bug fix:           /poteto-mode this pr has a subtle bug where the scroll drifts every 750ms even
                   when idle. repro first, then fix and verify.
perf:              /poteto-mode a big list takes a second or two to load even though we virtualize.
                   run a cpu trace and tell me why.
feature:           /poteto-mode build a small feature behind a feature flag. verify it really works.
prototype:         /poteto-mode build two prototypes of the markdown renderer so we can compare.
                   spawn an agent for each.
multi-phase:       /poteto-mode open source these skills as a plugin. nothing internal leaks, work
                   in a temp dir, show me the dependency graph first.
overnight run:     /poteto-mode i'm going to bed. land the stack even if ci flakes. i want
                   everything merged by morning.
babysit:           /poteto-mode check on pr 123. anything outstanding?
visual parity:     /poteto-mode the row spacing is too tall when this flag is on. the second image
                   is correct. repro and fix until it matches.
figure it out:     /poteto-mode i'm stepping away. migrate every caller from the synchronous store
                   to the new async one, keeping behavior identical. i want to trust it was done
                   right when i'm back.
how:               /how do we cancel runs? do we have an n+1 when we look up every run to cancel?
why:               /why is this feature flag not on yet?
architect:         design this instrumentation to be high signal with no false positives. /architect
                   this first.
arena:             /arena take my prompt to the arena verbatim. i want to compare their proposals
                   with yours.
swarm:             /swarm check every package under packages/ against its check.sh. one worker per
                   package. one report.
interrogate:       /interrogate review this pr.
tdd:               /poteto-tdd implement
deslop:            deslop it before i commit
unslop:            can we unslop and tighten the new changes?
pr-recap:          recap pr 123 for the reviewers
reflect:           /reflect that took too long. capture what we learned so the next run doesn't
                   repeat it.
correct:           /correct
show-me-your-work: /show-me-your-work keep a decision trail i can review when i'm back.
automate-me:       /automate-me
help:              /poteto-help which skill should i use to review this branch?
```

</details>

## the `poteto-agent` and Comment Sicko subagents

Two named helpers do delegated work. You rarely call them yourself.

- [`poteto-agent`](./agents/poteto-agent.md) does one unit of a playbook step for the main conversation, which runs `/poteto-mode` and owns the plan. Its [persona](./agents/poteto-agent.md) defines what it reads for each role. It pushes a branch or opens a PR only when its brief says to, and is never resumed across phases.
- [Comment Sicko](./agents/comment-sicko.md) reviews comments, usually through [`/no-comments`](./skills/no-comments/SKILL.md). It edits scoped comments and reports code that should be refactored. It does not write application code.

Both ship inside the installed `pstack-harness` skill, so they work without registration. [`/setup-pstack`](./skills/setup-pstack/SKILL.md) can also register them as native agents on Claude Code and Codex. The [persona contract](./skills/pstack-harness/references/named-roles.md) says which form a spawn uses, and the [registration reference](./skills/pstack-harness/references/registration.md) covers the files and their states.

## principles

twenty-four short skills, one principle each. `poteto-mode` lists them in its [principles reference](./skills/poteto-mode/references/principles.md), and loads a leaf when a step or trigger calls for it. the standalone files are there so other skills can reference a principle by name, and so the index can point at the full rule for each.

<details>
<summary>all twenty-four principles</summary>

| principle | group | rule |
|---|---|---|
| [laziness-protocol](./skills/principle-laziness-protocol/SKILL.md) | core | Bias toward deletion and simplicity in the resulting design. |
| [foundational-thinking](./skills/principle-foundational-thinking/SKILL.md) | core | Apply before writing logic: choosing core types and data structures, sequencing scaffold-vs-feature work, asking what concurrent actors share. Get the data structures right so downstream code becomes obvious. |
| [redesign-from-first-principles](./skills/principle-redesign-from-first-principles/SKILL.md) | core | Redesign as if the requirement had been a foundational assumption from day one, instead of bolting it on, and keep every behavior the requirement does not explicitly change. |
| [attack-the-premise](./skills/principle-attack-the-premise/SKILL.md) | core | Apply when two or more fixes that share one premise have failed the same gate. Write the premise down and test it directly before you write another fix that assumes it. |
| [subtract-before-you-add](./skills/principle-subtract-before-you-add/SKILL.md) | core | Remove dead weight, redundant validators, and stub references first, then build on the simpler base. |
| [minimize-reader-load](./skills/principle-minimize-reader-load/SKILL.md) | core | Count layers between question and answer, and hidden state in the reader's head; collapse one-caller wrappers and shrink mutable scope. |
| [outcome-oriented-execution](./skills/principle-outcome-oriented-execution/SKILL.md) | core | Apply during planned rewrites and migrations with explicit phase boundaries. Converge on the target architecture; don't preserve smooth intermediate states with throwaway compatibility code. |
| [experience-first](./skills/principle-experience-first/SKILL.md) | core | Choose user delight over implementation convenience; ship fewer polished features over more rough ones. |
| [exhaust-the-design-space](./skills/principle-exhaust-the-design-space/SKILL.md) | core | Build 2-3 competing prototypes and compare side by side before committing. |
| [build-the-lever](./skills/principle-build-the-lever/SKILL.md) | core | Apply to any non-trivial work, not just bulk work: edits, migrations, analyses, checks. Build the tool that does it or proves it (codemod, script, generator, or a skill your subagents follow) instead of working by hand. The tool is the artifact a reviewer can rerun. |
| [model-the-domain](./skills/principle-model-the-domain/SKILL.md) | architecture | Encode the domain in a structure instead of scattered conditionals. |
| [boundary-discipline](./skills/principle-boundary-discipline/SKILL.md) | architecture | Concentrate guards at system boundaries (CLI, config, network, external APIs); trust internal types and keep business logic in pure functions. |
| [type-system-discipline](./skills/principle-type-system-discipline/SKILL.md) | architecture | Make illegal states unrepresentable, brand semantic primitives, parse external data at boundaries, refuse to lie to the compiler, exhaust variants, derive from authoritative schemas. |
| [make-operations-idempotent](./skills/principle-make-operations-idempotent/SKILL.md) | architecture | Converge to the same end state regardless of partial prior runs. |
| [migrate-callers-then-delete-legacy-apis](./skills/principle-migrate-callers-then-delete-legacy-apis/SKILL.md) | architecture | Migrate callers and delete the old API in the same wave instead of preserving compatibility layers. |
| [separate-before-serializing-shared-state](./skills/principle-separate-before-serializing-shared-state/SKILL.md) | architecture | Eliminate the sharing first; serialize structurally only when one shared writer is a real invariant. |
| [prove-it-works](./skills/principle-prove-it-works/SKILL.md) | verification | Apply after completing a task, before declaring done. Verify against the real artifact (run the feature, read the actual value, inspect the diff), not a proxy, self-report, or 'it compiles.'. |
| [fix-root-causes](./skills/principle-fix-root-causes/SKILL.md) | verification | Trace each symptom back to the first place the system went wrong and fix it there. A guard is a fix only when the state it handles is legitimate. |
| [sequence-verifiable-units](./skills/principle-sequence-verifiable-units/SKILL.md) | verification | Apply to multi-step work (sweeps, migrations, runs of similar edits) and to how you stack commits and PRs. Break work into small units that each end in a verifiable state, check each before the next, and order delivery so the sequence proves itself to a reviewer. |
| [test-behavior-not-implementation](./skills/principle-test-behavior-not-implementation/SKILL.md) | verification | Apply when you write, change, or keep a test. Assert what the code's users can observe, so the test fails when that behavior breaks and keeps passing when only the internals change. |
| [explain-the-number](./skills/principle-explain-the-number/SKILL.md) | verification | Apply before you measure, and before you trust, report, or act on a number you measured: a speedup, a regression, a throughput, a latency, or an eval result. Find what limits it, and rule out that it measured something other than the work you think. |
| [guard-the-context-window](./skills/principle-guard-the-context-window/SKILL.md) | delegation | Route bulk to subagents; keep summaries in the main thread, not raw payloads. |
| [never-block-on-the-human](./skills/principle-never-block-on-the-human/SKILL.md) | delegation | Proceed, present the result, let the human course-correct after the fact. For irreversible actions, follow [authorization](./skills/poteto-mode/references/authorization.md). |
| [encode-lessons-in-structure](./skills/principle-encode-lessons-in-structure/SKILL.md) | meta | Encode the rule as a lint, metadata flag, runtime check, or script instead of more text. |

</details>

## differences from upstream

upstream leans on cursor-only pieces. this port swaps them for self-contained equivalents:

- `/deslop` (upstream's `cursor-team-kit`) → the port-owned [`/deslop`](./skills/deslop/SKILL.md) skill. its rules draw on three MIT-licensed skill sets, credited in [`skills/deslop/CREDITS.md`](./skills/deslop/CREDITS.md).
- `control-cli` / `control-ui` (also `cursor-team-kit`) → the project-local `verify-<app>` skill generated by [`/create-verification-skill`](./skills/create-verification-skill/SKILL.md).
- cursor's built-in `/create-skill` → the [authoring-a-skill playbook](./skills/poteto-mode/playbooks/authoring-a-skill.md). if your CLI ships a built-in `/babysit`, the [babysit playbook](./skills/poteto-mode/playbooks/babysit.md) supersedes it for pr-status requests.
- upstream's `disable-model-invocation` flag → a per-CLI gate. each gated skill ships `agents/openai.yaml` with `policy.allow_implicit_invocation: false`, which codex honors. on claude code, [`/setup-pstack`](./skills/setup-pstack/SKILL.md) lists the same skills by name only, so they load when you type `/name` or a pstack skill names them, never from their description.

[PORTING.md](./PORTING.md) has the full substitution map.

## why are there no planning skills?

your CLI already has a plan mode which works great with pstack. but personally, i don't believe in planning. the best spec is code. if you do want to make a plan, [`/poteto-mode`](./skills/poteto-mode/SKILL.md) covers it, but it's not a default. 

## make it yours

`poteto-mode` is my style. you may not want exactly that.

type [`/automate-me`](./skills/automate-me/SKILL.md). it mines your recent transcripts, drafts a `<your-name>-mode` skill from how you've actually worked, and routes through pstack underneath. you keep pstack as the base and end up with your own routing skill alongside `poteto-mode`.

models are configurable too. type [`/setup-pstack`](./skills/setup-pstack/SKILL.md). it detects the models you have access to and writes a small config file that maps each role (code, judgment, the review panels) to a model. you override only what you want, and every other role keeps its shipped default.

```
# ~/.agents/pstack-models.md
feature, refactoring: sonnet
judgment and prose: opus@xhigh

## codex
feature, refactoring: gpt-6-sol@high
```

a line is `role: model`, or `role: model@effort` to pin a reasoning effort. a `## codex`, `## claude-code`, `## grok`, or `## hermes` section holds picks for that CLI only, so one file serves every CLI. for each role the first match wins:

1. the per-repo file's section for your CLI (`.agents/pstack-models.md` in the repository)
2. your file's section for your CLI (`~/.agents/pstack-models.md`)
3. the per-repo file's flat line
4. your file's flat line
5. the shipped default

a model your CLI can't use means that role runs on your session model there. a claude alias becomes a gpt-6 model on codex and grok-4.7 on grok build. the [models config reference](./skills/setup-pstack/references/models-config.md) has the full rules.

a rerun of `/setup-pstack` keeps any role you changed. if your config still lists four entries for a panel, it predates the three-entry panels: delete those panel lines, including any under `## codex`, or delete the file, then run `/setup-pstack` again.

## automations

pstack also ships a dormant [benny automation pack](./automations/benny/). benny triages slack issue reports, then reproduces confirmed bugs with real ui evidence and may prepare a small draft fix. its files are not registered as slash skills.

to set it up, point your agent at [`FOR_AGENTS.md`](./automations/benny/FOR_AGENTS.md). setup copies the pack into the target repository at `.agents/automations/benny/`, enables pstack there for shared skills, and keeps user configuration outside the copied pack. benny needs a scheduled agent runner (claude code scheduled agents, or any cron-driven job that invokes your CLI).

## contributor checks

PRs are welcome. [CONTRIBUTING.md](./CONTRIBUTING.md#contributor-checks) covers the local gate (`tools/gate-check.sh lint` and `tools/gate-check.sh test`), the git hooks, and how they relate to CI.

## license

MIT
