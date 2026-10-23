# Verify the result and open a PR

"It compiles" is not evidence. The [Prove It Works principle](../../skills/principle-prove-it-works/SKILL.md) makes the agent check the real artifact before it reports success, and your job is to make "the real artifact" checkable. This page covers stating a finish condition, vetting a measured number, generating a verification skill for your app, formally verifying a property tests rarely reach, opening the PR, and driving it to merged.

Verification is the slowest step in most agent work, because it's the step that usually waits on a human. Make the agent able to do it, and you stop being the bottleneck. Skip it, and running more agents only gets you more unchecked work to review.

![A prototype plane flies a real test course while she times it with a stopwatch and robots film and checklist the run; the terminal reads verify: pass, evidence: captured.](./images/verification.jpg)

## State the finish condition up front

Put what done means in the first prompt, in whatever words fit:

```text
/poteto-mode add json output to this command. text output stays byte-identical, the json parses, both run against the sample project. show me the evidence.
```

Now the agent has three checks it can run, not a mood to satisfy. When the reply comes back, it should carry the exact commands and outputs. If a check couldn't run, a good reply says "inconclusive". A confident reply without evidence is a warning sign.

Match the check to the change:

- A CLI change runs the real command.
- A UI change walks the changed flow in the running app. When it must match a reference pixel for pixel, the [Visual parity playbook](../../skills/poteto-mode/playbooks/visual-parity.md) diffs screenshots against a frozen baseline instead of judging by eye.
- A parser or migration replays a saved input.
- A perf change compares before and after profiles.
- A storage change reads back the written value.

Ask for the proof as an artifact you can inspect yourself: the failing test and then the passing one, a before-and-after video, the trace, the screenshot. If the fix already merged, ask for the same check again on main. An artifact beats a plausible explanation, because you can challenge it without replaying the whole run.

For a small diff you don't fully trust, [`/blast-radius`](../../skills/blast-radius/SKILL.md) finds what it could break elsewhere. It finds the one fact that makes the change safe and proves that fact by running code, not by arguing for it.

## Vet a measured number with `/benchmark-checklist`

A before-and-after number is the easiest evidence to get wrong by accident. A warm cache, a debug build on one side, or work that never ran inside the timed region can each produce a convincing speedup. Before you report or act on a number, type:

```text
/benchmark-checklist vet the export speedup before it goes in the pr
```

[`/benchmark-checklist`](../../skills/benchmark-checklist/SKILL.md) asks seven questions and wants evidence from a run for each:

1. What limits the number, and why isn't it double?
2. Did every side run tuned the way production runs?
3. Does the result break a physical limit, like disk bandwidth or core count?
4. Did anything error or return wrong output?
5. Does it reproduce over alternating runs, with a median and a range?
6. Does it matter end to end, on the path a user waits on?
7. Did the work actually happen inside the timed region?

The verdict comes back as faster, slower, no measurable difference, or inconclusive, with the run count, range, and limiter. It says inconclusive when it can't name the limiter or a side ran untuned. `/poteto-mode` already runs the checklist inside the Perf issue and Hillclimb playbooks, so you type it yourself when you measured something outside them, or when someone else's number looks too good. It's the working form of the [Explain the Number principle](../../skills/principle-explain-the-number/SKILL.md).

## Create a project verification skill

The UI bullet above hides a real requirement. The agent needs a scripted way to drive your app. If your project has one, great. If not, run:

```text
/create-verification-skill
```

[`/create-verification-skill`](../../skills/create-verification-skill/SKILL.md) interviews the repository, not you. It works out what a user touches, how the app launches locally, what can drive it (an existing harness first, otherwise browser and CDP, a PTY, or plain HTTP), what evidence proves behavior, and whether two instances can run side by side. It asks you only what the code can't answer.

It writes `.agents/skills/verify-<app>/`, agent-facing instructions with exact Launch, Doctor, Drive, Evidence, and Cleanup sections, a Helpers section for any script it ships, plus a feature map under `features/` that indexes what the app does and what result proves each feature works. The skill ships a [worked feature-map example](../../skills/create-verification-skill/references/feature-map-example/) with a README index and one file per feature using the four required H2s. Before handing it over, the generator proves the skill once end to end: launch, doctor check, drive one feature, capture evidence, clean up, then confirm the evidence survived the cleanup. If that proof fails, don't use the output.

From then on, "verify it in the app" is a step any agent can execute, in this repo, with no setup conversation. Name it in the prompt when you want the proof in a specific form:

```text
/poteto-mode build the bulk-archive action. use /verify-<app> to verify your changes and show me a video and screenshots as proof.
```

```text
/poteto-mode repro this with /verify-<app>. if it repros on main, fix it and show me a video as proof.
```

Once the verify skill works, a [`/swarm`](../../skills/swarm/SKILL.md) can split a full pass by feature-map entry and aggregate the results. A swarm of verifiers also confirms a perf win over a big enough sample, or fuzzes the app for regressions before a PR ships.

Treat the verification skill as infrastructure, not a one-off. Commit it, so every person and every agent on the team drives the app the same way. Then [build the lever](../../skills/principle-build-the-lever/SKILL.md). When agents keep writing throwaway scripts to click through the app, ask for a small control CLI that the skill calls instead. Agents spend fewer tokens, and every run becomes repeatable. A CLI that agents use well has these traits:

- A few composable commands, each doing real work, rather than many thin ones.
- A `--dry-run` option on anything destructive.
- Subcommands that reveal features gradually instead of all at once.
- Error messages that say what to do instead.
- Rich `--help` text.
- Machine-readable output, such as JSON.

While you're there, make the dev setup repeatable too: seeded data, test users, and one command that brings the environment up the same way every time.

## Keep the verification skill honest

Apps change, and feature maps go out of date. Run this at least once a day, ideally from a scheduled automation so nobody has to remember:

```text
/maintain-verification-skill
```

[`/maintain-verification-skill`](../../skills/maintain-verification-skill/SKILL.md) audits the generated skill: one read-only source reader per feature in parallel, then one live pass that drives every mapped feature. It ends in exactly one of three outcomes. `clean` means full coverage and nothing to ship. `changed` means one PR of proven corrections, confined to the verification skill's own directory. `blocked` names the blocker. It never edits product code. If the live pass catches a product regression, it reports the regression instead of hiding it with a doc edit.

## Prove a property with a formal verification skill

A verification skill proves the paths you drive. Some bugs live on paths nobody drives: two retries that overlap, a lock that expires mid-write, a state change that arrives out of order. Tests rarely reach those cases. For code where such a bug is costly, run:

```text
/create-formal-verification-skill
```

[`/create-formal-verification-skill`](../../skills/create-formal-verification-skill/SKILL.md) picks the target from the code: a promise the code makes, where a break harms users and tests rarely reach the case that breaks it. It picks the strongest target, not the easiest to verify. Name an area or a bug to start there instead:

```text
/create-formal-verification-skill the job lease and retry logic. a job must never run twice at once.
```

The question picks the tool. Whether events can happen in a bad order suits a model checker over a small model of the design, and TLA+ is the default for that in any language. Whether the code behaves for every input suits a verifier that runs on the code. If no verifier runs on your language, the agent says so and tests the real code with generated inputs, not a hand-written model of the function. A property that must hold at every size can need a proof. The agent tells you which tool it chose and why.

It verifies one property and shows that property failing on a broken variant of the code, because a check you've never seen fail proves nothing. When the current code already breaks the property, you get the counterexample as a short sequence of steps in your code's terms. The property stays as stated, so the finding stays a finding. Product code doesn't change unless you ask.

It writes a project-local skill that tells the next agent whether a change touches the verified code, how to run the check with one command, and how to tell a real bug from a modeling error. Before handing it over, the generator follows that skill once on a scratch change that breaks the property, and the check must catch it. The handoff says what was verified, with which tool and bounds, what the check found, and what it doesn't cover. A pass covers the model or the bound, not the whole system.

The skill also records which code each check covers and the commit where the check last matched it. Merges and refactors that skip the skill can leave the check passing on a description of code that's gone. After them, run [`/maintain-formal-verification-skill`](../../skills/maintain-formal-verification-skill/SKILL.md). It updates the verification from the code, reruns it, shows that each updated check can still fail, and tells you whether each failure is drift in the verification or a bug in the code.

## Check documentation impact

Before Poteto reports a substantive code or public workflow change complete, it runs [`/documentation-impact`](../../skills/documentation-impact/SKILL.md) in author mode. The author checks which reader tasks changed and updates the affected docs. The author result decides whether independent review is required. When required, a different agent reviews the artifact without editing it, and completion waits for a current verdict of `pass`. Findings are repaired and reviewed again. This also applies when the work ends without a PR.

The pass checks applicable README instructions, references, examples, upgrade guidance, release notes, and diagrams against the implementation. It records the examined revision or local snapshot and the checks run. The skill defines the author result and when it requires independent review. No new spec or documentation tree is required.

You can request either mode directly:

```text
/documentation-impact update the docs affected by this change.
/documentation-impact review this change's documentation coverage without editing files.
```

Babysit reports documentation readiness alongside forge status. A status-only request reports a missing or stale author result or a missing or stale required independent review verdict as pending. Shipping requires a current independent review verdict of `pass` only when the author result requires it and rechecks current documentation evidence after relevant changes, including a rebase that changes documentation context.

## Open the PR

```text
/poteto-mode open the pr. small ordered commits, evidence in the description.
```

The [Opening a PR playbook](../../skills/poteto-mode/playbooks/opening-a-pr.md) works from a worktree, rebases the work into small ordered commits, cleans the diff, unslops the prose, and returns the PR link. Five narrow PRs beat one fat one, and stacked follow-ups beat a growing branch. The playbook also invokes [pr-recap](../../skills/pr-recap/SKILL.md), which defines when to post a reviewer recap and its comment format.

When a repository gates pushes through [no-mistakes](https://kunchenguid.github.io/no-mistakes/), the agent publishes each branch and opens each PR through the no-mistakes pipeline, and restacks with `no-mistakes rerun` once a run ends. It pushes nothing else except work-in-progress snapshots under `refs/pstack/wip/`, or under the agent ref convention the repository names. When the gate is broken, it stops and reports. It pushes around the gate only after you say "bypass no-mistakes" in the session. An agent in a Docker sandbox commits and leaves the push to the host. Run `no-mistakes init` in your main checkout, from the exact path spelling that git reports, because on a case-insensitive disk no-mistakes matches the spelling `init` used.

Poteto uses the repository's selected PR template or documented format. Without one, it keeps Why, What changed, Scope, Blast Radius, and Verification, with Tradeoffs when needed. A full `/setup-pstack` in a repository installs the default template only when there is no existing template or custom format. For a repository using no-mistakes, setup also fills a missing `pr.template` selection. Existing templates and explicit selections stay in place.

No-mistakes reads that template and its configuration from the trusted default branch, so both must land before template mode activates. Until then, generic pipeline runs can replace the author sections. After publication, the opening playbook restores the selected format and preserves generated evidence. It repeats this check after later updates. See the [template setup instructions](../../skills/setup-pstack/references/pr-template.md).

## Drive the PR to merge-ready with Babysit

An open PR starts collecting blockers immediately. Checks fail, reviewers comment, trunk moves. Hand that churn to the [Babysit playbook](../../skills/poteto-mode/playbooks/babysit.md):

```text
/poteto-mode babysit this pr. get it green.
```

Babysit watches the PR, with a bundled watcher on GitHub or the Origin CLI when it's available, and takes blockers in order: conflicts, then review threads and bot findings that live only in a review body, then CI. Every known fix batches into one push, so the checks restart once instead of after every fix. The comment triage is skeptical, because humans and bots file real catches and noise in the same list. A real finding gets a fix. Noise in a thread gets dismissed with the disproof posted on the thread. A body-only finding has no thread, so the disproof goes in a PR comment that links the review. When all you want is status, ask smaller and Babysit answers without starting the loop:

```text
/poteto-mode check on pr 123. anything outstanding?
```

Babysit stops at merge-ready. It never merges, even with everything green, because merging is a different decision.

When a failed Actions log ends before the assertion, the bundled
[failed-check diagnostic command](../../skills/poteto-mode/scripts/watch-pr/README.md)
can recover JUnit failure and error records from that exact run. It verifies the
checked head, keeps unavailable artifacts as evidence gaps, and never reruns CI.

## Land the stack with Shipping

Green is not the same as safe. When you're ready to land, say so:

```text
/poteto-mode land the stack.
```

The [Shipping playbook](../../skills/poteto-mode/playbooks/shipping.md) verifies each PR independently before it arms anything. One fresh agent per PR proves the behavior live, and the agent that judges a change is never the one that wrote it. Then Shipping lands only the contiguous verified run from the bottom, one PR at a time through GitHub by default or Origin when its CLI is available, and reports the first PR that breaks the chain. A verified PR sitting above an unverified one waits, because merging it would pull the gap in underneath. On GitHub each merge goes through `merge-gate`. It refuses to merge until the verdict still matches the PR's patch, every check passed, and every bot's review is acknowledged. It also refuses when the base branch has a merge queue, because the queue would land the PR later without rechecking the verdict or the bot reviews. When it refuses, it lists every gate that failed. The lead asks you before it overrides any refusal.

Next: [Run work while you sleep](./07-overnight.md).
