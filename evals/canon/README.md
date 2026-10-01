# One-rule amendment screen

This directory screens candidate rules for skills that already exist. Each
comparison is the current skill text against the same text plus one rule. It
does not compare a skill against no skill. A stub arm (see Stub arm) compares
the skills against the same skill names with no guidance.

## What runs

For each case of each rule, `screen.py` builds two arms from `skills/` as the
rule's `skills_at` commit holds it, or from the working tree when the rule names
no commit:

- `current` holds the git-tracked files under `skills/`, copied unchanged.
- `amended` holds the same files with `rules/<id>/rule.patch` applied.

`rule.patch` is a unified diff against `skills/` with one hunk in one file. Its
added and removed lines must form one unbroken run, and its header counts
must match its lines. The kind is `insert` when the new text is the old text
with one run of characters added, even if the patch swaps a `-` line for a `+`
line. Any other change is `replace`. The build refuses two files, two
hunks, a hunk with unchanged lines between its edits, and a patch that no
longer matches `skills/`. Each arm gets its own manifest with the same case,
prompt, and mount name. `screen.py` runs only the `with_skill` rows, grades
each arm with the rule's executable oracle, and prints the pair side by side. No
judge runs, except for review or document cases.

A rule has one or more cases. A `positive` case is one where the rule should
change the answer. A `near-miss` case is one where the rule must not change it.
A rule `SEPARATES` only when every positive case separates and no near-miss case
reverses, goes ungraded, or is unexposed.

`screen.py plan` lists every rule with its source, owner file, patch kind,
companions, and cases. It also shows each finished run found under `--runs-root`, which can be
given more than once and defaults to `/private/tmp/canon-entry`. A run whose
owner file differs from today's current or amended text is marked `(older
text)`.

## Layout

```
rules/<id>/
  rule.patch          one hunk against skills/
  rule.json           {"source": "...", "companions": ["<skill>", ...]}; companions is optional
                      a placement variant has {"cases_from": "<rule>"} and no oracle.py or cases/
                      "skills_at": "<commit>" screens skills/ as that commit holds it
  oracle.py           CHECKS = {"<case-id>": check}; check(answer, project) returns failures
                      (project is a shared.Workspace in a workspace case)
  test_oracle.py      unit tests that grade the samples
  cases/<case-id>/
    case.json         kind (positive or near-miss), domain, timeout_s, expected_behavior
                      (timeout_s optional in a workspace case, default 1800)
    prompt.md         the user request; {project} expands to the project files
    project/          the fixture the answer edits
    samples/good.md   an answer that must pass
    samples/bad.md    an answer that must fail
    overlay/          workspace cases only, in place of project/ (see Workspace cases)
    samples/*.diff    workspace cases only, the edit each sample makes
oracles/
  check.py            check.py <rule> <case> <output_dir>
  shared.py           answer parsing, Python helpers, the sandboxed container runner
  probes/run.py       runs answer code inside the container
  probes/project_tests.py  runs a checkout's own tests inside a dependency image
images/
  <repo>/Dockerfile   a repo's test dependencies, from its lockfiles at one commit
  build.py            build.py <repo> <commit>; records the image id in images.json
```

Each arm root holds the grader next to the skill tree: `oracles/`, the rule's
`oracle.py`, and the case's `project/`. A workspace case's arm holds
`workspace.json` naming the pinned checkout in place of `project/`, a copy of
`images/images.json` for `shared.project_test_results`, and a
`workspace/` directory that the entry wrapper reads. It never holds `samples/`,
`test_oracle.py`, or `oracles/test_*.py`. The answering agent works in a
separate temporary workspace. A Claude trace showed its cwd under
`/private/var/folders/.../claude-ws-*`, and a Codex run's `environment.json`
records `<isolated workspace>`.

## How to add a rule

1. Create `rules/<id>/rule.json` with the research source. If the rule routes
   to a skill that users install beside pstack, list it in `companions`.
   Set `skills_at` to the full commit whose `skills/` the patch is written
   against. The screen reads `skills/` at that commit through `git archive`,
   so a rule keeps screening the text it was measured on after main moves or
   ships the rule itself. A rule without `skills_at` screens the working tree.
   A variant does not inherit `skills_at`; its own `rule.json` names it.
2. Write `rules/<id>/rule.patch` as one hunk against the tracked file, with
   paths relative to `skills/` (`--- a/<skill>/SKILL.md`, `+++ b/<skill>/SKILL.md`).
3. Add cases under `rules/<id>/cases/<case-id>/`, at least one of them
   `positive`. Give each a project-shaped id, `case.json`, `prompt.md`, and
   `project/`, or a `workspace` entry and `overlay/` (see Workspace cases).
   Add a near-miss case when the rule has an exception the agent must respect.
4. Write the prompt as an organic user request that does not name the rule. The
   prompt with its project files or overlay, and the case id, must not contain
   these whole words in any case: eval, evals, evaluation, judge, experiment,
   rubric, score, compare, benchmark, candidate, arena. Ask for files inside
   `<file path="...">` tags, or commits inside `<commit message="...">` tags.
   No prompt may equal or contain another case's prompt, in any rule. The
   offline stand-in picks its case by prompt, and `test_screen.py` checks
   this. Two rules that share an oracle and a fixture therefore word their
   prompts differently. A placement variant and its source load the same case
   directory, which is the one exception.
5. Write `rules/<id>/oracle.py`. Map every case id to a function that returns
   a list of failure strings, empty on a pass. The arm copies only this one
   file, so it may import only `shared` and the standard library, and read only
   the `project` it is given. A workspace case's check reads the
   `Workspace` it is given.
6. Add `samples/good.md` and `samples/bad.md` to every case, and assert their
   exact failure lists in `rules/<id>/test_oracle.py`, which imports
   `from check import grade`. A workspace case also needs `good.diff` and
   `bad.diff`.
7. Run the model-free checks below, passing `<id>` to the two offline runs.
   `plan` must list the rule with the expected patch kind, and both offline runs
   must print `SEPARATES` for the rule.

Do not edit shared files to add a rule. If a rule needs a new shared helper, add
it to `oracles/shared.py` in its own change. Every check loads every rule, so a
half-written `rules/<x>/` breaks the checks for everyone in that worktree. Work
in your own worktree, or keep each rule directory loadable.

## Placement variants

A placement variant tests where a rule sits, not what it says. It moves an
existing rule's operative sentence to another file, such as the
poteto-mode `SKILL.md` that every `/poteto-mode` run has in context. Its
`rule.json` is `{"cases_from": "<rule>"}`, and its directory holds only that
and `rule.patch`. It runs the source rule's cases and oracle unchanged, so its
results compare directly with the source's. It inherits the source's `source`
and `companions` unless its own `rule.json` names them. A variant of a variant
is refused. The arm copies the source's `oracle.py` under the variant's id.
Name a variant `<rule>-index` when it places the rule in the poteto-mode index.
`--case` picks which shared cases a paid run answers.

The offline stand-in reads the rule and case of a workspace case from the path
of its input, `arms/<rule>/<case>/<arm>/workspace`. For a pasted-project case
it matches the prompt, and a case that a variant shares with its source goes to
the rule whose inserted text is mounted.

### Arm rules

An arm rule compares more than one placement of a rule in one run. Its
directory holds `rule.json` and `arms/`, and no `rule.patch`:

```
rules/<id>/
  rule.json           {"cases_from": "<rule>", "arms": ["current", "leaf", "leaf+trigger"]}
                      source and companions are optional, as for a variant
  arms/<arm>.patch    one per arm after current
```

`current` is first and has no patch. Every other arm has exactly one
`arms/<arm>.patch`, and every patch file is listed. Arm names match
`^[a-z0-9][a-z0-9+._-]*$`. An arm's patch is a unified diff against `skills/`
that may change several files in several hunks, add a file from `/dev/null`,
or delete one. Paths read `a/<skill>/...`, or `a/skills/<skill>/...`, which
drops the `skills/` prefix. The build applies it with `git apply` in a
scratch copy of the tree, and refuses a patch that does not apply or changes
nothing. The one-change check does not run. The rule takes its cases and
oracle from `cases_from`, as a variant does. Without `cases_from` it holds its
own `oracle.py` and `cases/`, as an ordinary rule does. Under `--entry skill` the arms
mount every skill a patched arm changes.

`build` writes `arms/<rule>/<case>/<arm>/` for every arm in order.
`build.json` records `"patch_kind": "arms"`, `"arms"` in order, and
`"arm_changes"`, which maps each arm to the files it changes (`current` has
none). `"target"` is the first file the first patched arm changes, or
`poteto-mode/SKILL.md` when no arm has a patch, for older readers. A pair rule's `build.json` also records
`"arms": ["current", "amended"]`.

`compare` prints one row per case and run with every arm's verdict in order,
each arm's changed files and how many it read, then one line per comparison:
each arm against current, then each later arm against each earlier one, as
`leaf+trigger vs leaf: TIE-PASS`. The exposure target of a comparison is the
set of files that differ between the two arms. The later arm is exposed when it
read one of them, or when one of them is `poteto-mode/SKILL.md` and its trace
shows the entry injected. Under `--entry poteto-mode` both arms must also show
the entry (see Entry modes). Each arm after current gets its own rule line against
current, `rule leaf vs current run-1 SEPARATES`. In `compare.json` these pair
entries add `baseline` and `treatment`, and these rule entries add `arm`.

`build.json` also records `arm_listed`, the `SKILL.md` files each arm adds
beside current whose frontmatter does not set `disable-model-invocation` and
whose skill has no `agents/openai.yaml` with `allow_implicit_invocation:
false`. The agent is offered such a skill by its description in every run of
that arm. A pair whose differing files include a listed skill is exposed only
when the listing arm is the treatment, whether or not the run loaded the skill.
Such a pair is scored on its verdicts instead of reading `unexposed`, which is
the outcome a placement screen measures. After the rule lines `compare` prints
one line per agent, rule, and arm that changes files, `arm skill: changed text
reached 2/5 run(s)`, counting the runs that read or loaded one of the arm's
changed files, or whose trace shows the entry injected when
`poteto-mode/SKILL.md` is one of them, and adds `listed by description:
<paths>` when the arm lists any.
`compare.json` holds the same rows under `arms`. `plan`
lists an arm rule's arms and each arm's changed files. `chain.py` counts every
arm the build lists, and takes an arm's owner file to be the first file its
patch changes. The stub has no patch, so it keeps the rule's target.

### Stub arm

A stub arm asks whether the skills steer the agent at all. `stub` is a
reserved arm name that takes no patch:

```
rules/<id>/
  rule.json           {"cases_from": "<rule>", "arms": ["current", "stub"]}
```

The build makes it from the current tree. Every skill directory keeps its
name and its `SKILL.md`, cut to the frontmatter bytes that current holds
through the closing `---` line. Every body and every other file is dropped.
Both arms are `with_skill` rows with the same manifest, prompt, entry prefix,
workspace input, grader, and companions, so the only difference is the
guidance text. The whole frontmatter stays, including fields such as
`reminder` and `disable-model-invocation`, so that both arms discover and
trigger the same skills. A stub arm needs no `arms/` directory, and
`arms/stub.patch` is refused. It may also sit beside patched arms. A rule with
only current and stub targets `poteto-mode/SKILL.md`, and under `--entry
skill` mounts poteto-mode alone. `plan` and `build` print the stub arm as a
count of cut and dropped files.

`compare` takes the stub arm as the baseline of every pair it is in, so the
line reads `current vs stub: SEPARATES` when current passes and the stub fails,
and the rule line reads `rule current vs stub`. The exposure target is every
file that differs from the stub, which is every body and every other file. The
guided arm is exposed when it read one of them, so an unexposed pair is one
where the guidance was never loaded. Under `--entry poteto-mode` the wrapper
injects `poteto-mode/SKILL.md` into both arms. The stub's copy is only
frontmatter, but it registers and injects all the same, so the stub's trace
shows the entry as current's does. Current is exposed there when both traces
show it. In `compare.json` the rule entry's `arm` is `stub`.

The stub arm drops `pstack-harness/scripts/subagents.py`, so a `--runner sbx`
stub arm registers no poteto-agent or Comment Sicko persona. The persona files
are guidance that the skill tree installs.

The offline stand-ins answer a positive workspace case with `bad.md` in the
stub arm and `good.md` in every other arm, and `offline/sbx-agent` does not ask for the
persona in the stub arm. On 2026-09-28 both the host stand-in
(`CODEX_BIN=evals/canon/offline/codex`) and `--runner sbx` with
`CANON_SBX_STANDIN` printed `rule current vs stub run-1 SEPARATES` for
`bug-fix-spawn-step-stub` under `--entry poteto-mode`. A pasted-project case in a stub
rule gets `bad.md` in every arm, because the stand-in finds a pasted arm by
the lines its patch adds, and a stub rule adds none. Give a stub rule a workspace case for its
offline run. Under the poteto-mode entry the host stand-in writes a rollout
with the injected skill message under `$CODEX_HOME/sessions`, as codex does
without `--ephemeral`, so the wrapper harvests it and each run reads `entry
injected`.

## Entry modes

`--entry skill` is the default. It mounts only the skill that owns the patched
file, and the harness tells the agent to read it.

`--entry poteto-mode` follows the route a user takes. Each arm mounts every
git-tracked file under `skills/` as `skills/pstack/`, so poteto-mode can read
principle leaves and playbooks by relative path. The one-change check runs over
that whole tree. A wrapper links the tree to `.claude/skills` for Claude or
`.agents/skills` for Codex, the directories each agent searches for project
skills. It then starts the prompt with `/poteto-mode ` for Claude or
`$poteto-mode ` for Codex, and passes the rest through unchanged. Every case
gets 900 seconds in this mode, except a workspace case, which keeps its own
timeout.

Both agents need the link. `codex debug prompt-input` in a harness-shaped
workspace listed only the system skill root until `.agents/skills` existed. A
Claude run with an unknown model, which costs nothing, listed `poteto-mode`
among its slash commands only with `.claude/skills` present.

`compare` reports which tracked skill files each run read, taken from completed
read, command, and tool events whose input names the file. It also reports how
each run's trace shows the entry skill, as `entry injected`, `entry read`,
`entry not registered`, or `entry not observed`. Each pair gets one outcome:
`separates`, `tie-pass`, `tie-fail`, `reverses`, `invalid`, or `unexposed`.
`unexposed` means the amended arm never read the patched file, so the pair says
nothing about the rule. A read through a glob or a directory-wide grep does not
count. Claude's `Skill` tool leaves a `skill_load` event that carries only the
skill's name. A completed one counts as a read of `<name>/SKILL.md` when the
arm's tree has that file, with a `plugin:` prefix or a leading slash dropped.

Under `--entry poteto-mode` a pair is also `unexposed` unless both arms show
the entry as injected or read. The wrapper prefixing the invocation is not
evidence, since a runner that hid project skills would still prefix it and run
every arm with no pstack. The evidence each agent leaves:

- Claude. The first `init` event must list `poteto-mode` among its `skills` or
  `slash_commands`, or the run is `not registered`. Then it is `injected` when
  the trace or the harvested session transcript holds
  `<command-name>/poteto-mode</command-name>`, or the trace shows the `Skill`
  tool loading it, and `read` when it read `poteto-mode/SKILL.md`. The `-p`
  stream never echoes the expansion. The session transcript does, and both
  runners harvest it.
- Codex. It is `injected` when a harvested rollout holds the user message
  that starts `<skill>\n<name>poteto-mode</name>`, and `read` when it read
  `poteto-mode/SKILL.md`. This is weaker than Claude's. Codex has no init
  listing, so nothing shows registration apart from the injection itself, and
  `exec --json` never shows the injection. The rollout does, and both runners
  harvest it.

The harness runs Claude with `--no-session-persistence` and Codex with
`--ephemeral` under an isolated `CODEX_HOME` it removes when the run ends, so
a host run used to leave no transcript, and on 2026-09-30 every host pair
under this entry read `unexposed`. The host wrapper, `host.py wrap`, drops
those two flags, passes Claude `--session-id` with a fresh uuid, reads Codex's
thread id from the stream's `thread.started` event, and after the agent exits
moves that session out of its store (`$CLAUDE_CONFIG_DIR/projects`, default
`~/.claude/projects`, or `$CODEX_HOME/sessions`) into the run's harvest slot,
under the same paths the sbx runner's harvest uses, beside a `session.json`
naming the session and the files moved. Claude's delegates sit inside the
session's own directory. For Codex the wrapper also moves every rollout whose
first `session_meta` names a moved thread as its `parent_thread_id`, so the
delegates a lead spawned travel with it. It moves no other session. Claude
Code also makes an empty `memory/` dir under the run's project dir, so the
wrapper removes that project dir once no file is left in it, and the store
keeps nothing of the run. On the host runner, every case under this
entry and every workspace case runs through the wrapper. A pasted case under
`--entry skill` runs the agent directly and keeps no transcript. On
2026-09-30 one host run of `value-type` per agent read `entry injected` from
the harvested transcript and rollout.

An injection loads `poteto-mode/SKILL.md` without a file read, so a rule
patched into that file counts as exposed in an arm whose entry was injected.
On 2026-09-30 every Claude run under `/private/tmp/canon-steering` (66 runs,
`--runner sbx`) showed both the init listing and the expansion.

Answers return files inside `<file path="...">` tags, because the harness
discards the agent's workspace. Workspace cases are the exception. Their
wrapper saves a diff outside the workspace before the harness deletes it.
Oracles that run answer code use the pinned `python:3.12-slim` image with no
network, a read-only root, and no capabilities.

## Companion skills

A rule that routes to another suite's skill names it in `rule.json`
`companions`. The build copies each named directory unchanged, including
`agents/openai.yaml` and other invocation flags, from `$CANON_COMPANIONS_ROOT`
(default `~/.agents/skills`) into both arms. Under `--entry poteto-mode` the
copy sits in `skills/pstack/<name>`, so the same link that exposes pstack
also exposes the companion by name. Under `--entry skill` it sits in
`skills/<name>` and its `SKILL.md` joins `skill_paths`. Under `--entry
poteto-mode` the build refuses a companion whose name matches any pstack
skill. Under `--entry skill` it refuses only a companion whose name matches
one of the skills mounted for that rule.

The one-change check reads only the pstack files, so companions never count
as a second change. `build.json` records each companion's file count and a
sha256 of its files as read back from every arm. The build fails when an
arm's copy differs from the source. Rules without companions build exactly as
before. `compare` counts reads of companion files like reads of pstack files,
and for a rule with companions it also names each companion the run read.

## Workspace cases

A pasted project is a few files, so a rule about how an agent explores a
codebase cannot show an effect there. A workspace case puts the agent inside a
real repo instead. Its `case.json` adds:

```json
"workspace": {"repo": "omnigent", "commit": "<40-character sha>", "overlay": "overlay/"}
```

`overlay/` sits in the case directory and holds files copied over the checkout,
such as a seeded `CONTEXT.md`. An overlay path that passes through a symlink the
checkout holds is refused before any overlay file is written. The case has no `project/`, and its `prompt.md`
has no `{project}`. `timeout_s` is optional and defaults to 1800 seconds under
both entries. The meta-word check covers the prompt, the overlay paths, and the
overlay text. It cannot cover the upstream repo.

The checkout comes from a bare mirror under `$CANON_CACHE` (default
`~/.cache/canon-screen`) that holds the pinned commit at depth 1. Put a commit
there once, from a local clone or the upstream URL. Without `--from`, the fetch
reads the upstream URL, which `workspace.py` knows only for `omnigent` and
`hermes`.

```sh
python3 evals/canon/workspace.py fetch omnigent 02969a131c72d74c00c5800d8e82ae831f8ec5e5 --from <local clone>
python3 evals/canon/workspace.py fetch hermes 130b8f2c5dbca93a81aa396dd2ba44420d78f6f0 --from <local clone>
```

The agent's checkout shows only the pinned commit: `git log` prints one
commit, however deep the mirror is. A case whose evidence lives in the repo's
history adds `"history": true` to its `workspace`, and its checkout shows every
ancestor of the pinned commit. It reads a separate mirror,
`mirrors/<repo>.history.git`, that holds that history. Fetch it with
`--history` (`workspace.py fetch omnigent <commit> --history`). The build, the
wrapper, and the sandbox refuse a history case whose mirror or clone lacks it.
The depth-1 mirror stays as it was.

The harness copies only single files into its workspace, flattened into
`inputs/`, so the entry wrapper builds the checkout itself. It runs
`host.py wrap --workspace` in the agent's cwd, which already holds the mounted
skills, with the functions in `workspace.py`.
`wrap` runs `git init`, points the new repo at the mirror's objects through
`alternates`, checks out the commit, copies the overlay, and adds the mounted
skill directories to `.git/info/exclude`. It exits 97 without starting the
agent when the checkout fails or its tree id differs from the one the build
recorded. Under the poteto-mode entry it links the skills as before. A repo
that already tracks `.claude/skills` gets a copy of each skill beside its own.
Codex runs with `--sandbox workspace-write` for these cases.

Claude runs through `claude-project-only`, whose `acceptEdits` mode denies
Bash in a `-p` run. Claude Code 2.1.281 lists no Grep or Glob tool there, so
without Bash it could not search a real repo while Codex runs git and grep. The
workspace wrapper, and only that wrapper, appends `--allowedTools` rules for
read-only commands by prefix: `git log`, `git show`, `git grep`, `git diff`,
`git status`, `rg`, `grep`, `ls`, `find`, `wc`, `head`, and `sed -n`. It
also appends `--disallowedTools` rules for the flags that make those commands
run another program or delete files: `find -exec`, `-ok`, `-delete`,
`rg --pre`, `git grep -O`, and `git grep --open-files-in-pager`. A run with a model that does not exist, which
costs nothing, accepted both flags on 2026-09-24, and an unknown flag fails
the same run at parsing. No run has yet shown each rule matching a command.

When the agent exits, `wrap` writes a binary diff of the workspace against that
tree to a slot outside the workspace. The diff covers edits, deletions, and new
files that git does not ignore. A rename shows as a deletion and an add. The
harness seals each run directory, so `run` moves each slot to a parallel tree.
The run dir `<out>/<agent>/<rule>/<case>/<arm>/runs/<run>` maps to
`<out>/<agent>/<rule>/<case>/<arm>/harvest/<run>/workspace.diff`, beside a
`workspace.json` with the tree id and timings. `run` refuses a run whose
workspace had a different tree. A pasted case under the poteto-mode entry gets
the same `harvest/<run>` dir, holding `session.json` and the `transcripts/`
the wrapper moved there (see Entry modes).

`build` checks out the commit plus overlay once per spec under the cache and
writes its path into the arm's `rules/<id>/cases/<case>/workspace.json`. The
wrapper's input is the arm's `workspace/` directory, which holds
`workspace.json` (repo, commit, mirror, tree id, and `history` for a history case) and `overlay/`. `build.json`
records the repo, commit, tree id, checkout path, and one hash per arm of the
workspace input, and refuses the build if the hashes differ. It also refuses a
repo that tracks a path the mounted skills take.

A workspace case's check receives a `shared.Workspace` in place of the project.
`workspace.checkout` is the pinned checkout with the overlay, and
`workspace.diff` is the run's diff. `workspace.harvest` is the directory that holds
the run's `workspace.diff`, where a check may write a report beside it. It is
`None` when a test builds the `Workspace` from a sample. `shared.apply_diff(checkout, diff)` returns
the new bytes of every path the diff touches, with `None` for a deleted path.
It refuses a diff that leaves a symlink at a path it touches, that touches a
symlink in the checkout, or whose path resolves outside the checkout, so a
grader never reads a host file through the agent's diff.
A case whose module imports only the standard library can run tests.
`shared.plain_test_failures(tree, modules)` runs every test function and
`Test*` method of the named modules in the pinned image, with no pytest
plugins or fixtures, and returns one `<module>::<test> failed` line per
failure. The check builds `tree` from the pinned checkout and the diff's new
bytes, so it runs the pinned tests and never the agent's edited copies.
A case whose tests need third-party packages runs them in a dependency image
instead. `images/<repo>/Dockerfile` installs the repo's test dependencies from its own
lockfiles, Python for both repos and the web ones for omnigent, and the image
holds none of its source.
`python3 evals/canon/images/build.py <repo> <commit>` builds it from the
manifests and lockfiles the mirror holds at that commit, and records the image
id in `images/images.json` under `<repo>-<commit[:12]>`. The images are local
builds, so another machine builds its own and gets a different id.
`shared.project_test_results(image, checkout, files, tests)` lays `files`, the
result of `apply_diff`, over a copy of the checkout. It runs the named test
files or pytest node ids with no network, a read-only root, and resource
limits, and returns `{test id: "passed", "failed", or "skipped"}`. Python files
run under pytest, other files under vitest in the nearest directory with a
`package.json`. A named file that reports no tests counts as failed.
The samples are `good.md` and `bad.md` with a `good.diff` and `bad.diff` beside
them. `test_oracle.py` passes `workspace=Workspace(checkout, diff)` to `grade`.
The offline stand-in applies the chosen sample's diff in its cwd. The sample
tests skip when the mirror lacks the pinned commit.

The omnigent cases grade the diff statically, with the AST of the Python files
it touches. Their upstream tests need pyyaml, pydantic, and pytest, which the
standard-library image does not have, and they predate the dependency images.
omnigent's `AGENTS.md` asks for `pre-commit` before any commit, so each prompt says there is no need to commit. It also
asks for a `@deprecated` marker on anything slated for removal, so the
one-name check skips a `@deprecated` def and a parameter declared with
`deprecated=True`. None of these cases needs an overlay.

Each run costs one checkout. On an Apple silicon Mac on 2026-09-24, omnigent
(5,545 files) took 1.0 s to check out, 0.3 s to diff, and 102 MB of disk.
hermes (15,249 files) took 2.0 s, 0.8 s, and 189 MB. The harness deletes the
workspace after each run. `run_agent_tasks` in `skill_benchmark.py` at the
pinned commit c2a1735 creates it with `tempfile.TemporaryDirectory`. The
mirrors take 38 MB and 76 MB once, and each reference checkout takes the same
space as one run.

## Review cases

A review case screens how poteto-mode reviews a flawed pull request, not how
it builds one. It is a workspace case whose `case.json` also names the PR:

```json
"workspace": {"repo": "omnigent", "commit": "<40-character sha>"},
"review": {"patch": "pr.patch", "title": "Add retry budgets", "body_file": "pr-body.md", "branch": "retry-budgets"}
```

```
cases/<case-id>/
  case.json           kind, domain, expected_behavior, workspace, review; timeout_s optional
  pr.patch            the PR as a git diff or format-patch that applies to the pinned commit
  pr-body.md          the PR description, named by review.body_file
  prompt.md           an organic request, e.g. "Can you review the change on branch retry-budgets
                      against main before I merge it? The PR description is in pr-body.md."
  rubric.md           judge only: the flaw or decoy, and what counts as each verdict
  samples/labels.json {"review-found.md": "FOUND", ...}
  samples/review-*.md calibration reviews, one per label
```

`kind` is `positive` for a seeded flaw and `near-miss` for a clean or decoy PR
that must not be flagged for the rule's concern. A positive case's labels are
`FOUND`, `PARTIAL`, or `MISSED`. A near-miss case's labels are `FALSE_ALARM` or
`CLEAN`. The build refuses a review case without `rubric.md` or
`labels.json`, a label outside its kind's verdicts, a branch named `main`, and
a body file name that is also an overlay path. The meta-word check covers the
prompt, the PR title, the branch, the body, and any overlay, but not
`pr.patch`, which is upstream-shaped code.

**Checkout.** `workspace.py` checks out the pinned commit, points a local
`main` at it, and creates the PR branch. It applies `pr.patch` with `git apply
--index` and commits it as `Sam Rivera <sam.rivera@example.com>`, with the PR
title as the message. The author and committer date is the pinned commit's
committer date plus one hour. With that fixed date, the PR commit id depends
only on the case. The PR branch stays checked out. The body file sits
untracked in the workspace root under its own name, so `git status` shows
`?? pr-body.md`, as a saved description would. The body is part of the
recorded tree, so it never shows in the harvested diff unless the agent edits
it. Each arm's `workspace/` holds `pr.patch`, the body under `overlay/`, and
`workspace.json` with `review.refs`, the commit ids of `main` and the PR
branch. `build.json` records the same `review` object per case beside the
tree id and the per-arm input hash. The build refuses arms whose inputs
differ. The entry wrapper refuses to start the agent when its tree or either
ref differs from the recorded one. `rubric.md` and `samples/` are never copied
into an arm, and `test_review.py` checks that.

Under `--runner sbx` the clone inside the sandbox may carry only the
checked-out branch. `sbx_inside.py setup` therefore recreates `main` and the
PR branch from the recorded ids, checks the PR branch out, and checks HEAD.

**Harvest.** The review is the agent's final message, in `output.md` as for
every run. Files it writes land in `workspace.diff`. For a review case the
wrapper also records `head_after` and `refs_after`. A review must not modify
the PR, so a nonempty diff or a moved HEAD is a finding in `chain.py`'s
`review.pr_modified` and `review.head_moved`, never a failure. The judge sees
that diff as the files the reviewer changed or added.

**Precheck and judge.** `oracle.py` is the precheck.
`CHECKS[case](answer, workspace)` returns failures unless the review names the
case's file or symbol, or the decoy's for a near-miss. The harness grade runs
only the precheck. After grading, `run` judges each judged run, review or
document, and writes `<work>/judge.json`. A verdict that says the review flagged the location
(`FOUND`, `PARTIAL`, or `FALSE_ALARM`) counts only when the precheck passes.
Otherwise the combined verdict is `MISSED` for a positive case and `CLEAN` for
a near-miss. For the pair, a combined `FOUND` or `CLEAN` is a pass and
anything else is a fail. An unjudged run is `INVALID`.

The judge is our own runner in `review.py`, not the harness's `judge`
command. The pinned harness (c2a1735) renders every judge prompt through
`judge_prompt`, which opens with "You are grading one Skill Eval Harness judge
assertion" and puts `case_id` and the assertion into the payload. Its plain
contract is fixed to `{passed, score, rationale}` (`verdict_schema_for`), so
it cannot return a five-way verdict against a per-case rubric. The runner
borrows the harness's CLI flags, among others: Claude runs `claude -p
--output-format json --no-session-persistence --tools= --json-schema
<schema>`, and Codex runs `codex exec --json --ephemeral --sandbox read-only
--output-schema <schema> --output-last-message <file>`. sbx refuses an empty
argv element, so the empty tool list is spelled `--tools=`.

- **Cross-family.** Codex `gpt-6-sol` judges a Claude review and Claude
  `opus` judges a Codex review (`review.JUDGE_FOR`). `screen.py judge --judge
  B:M` overrides that.
- **Sandbox.** Each call gets its own sandbox from the agent kit, with the run
  deny list, and the sandbox is removed afterwards. Before the judge starts,
  the same policy probe as a run's step 2 must deny every `run_deny_network`
  host and example.org, or the call fails with that error and no verdict. It
  starts from the case repo's dependency template when one exists, because that
  template pins the CLI. A Codex judge needs a template that pins the CLI,
  since the kit's Codex does not list `gpt-6-sol`. A case with no repo, or
  whose repo template is not built, falls back to the CLI-only template
  `canon-judge-codex:<digest>`.
- **Blinding.** The judge sees the rubric, the PR title, body, and diff, the
  review under the label `review-<sha256[:8]>` of its own text, and the
  reviewer's diff. It never sees the rule, arm, case directory, or agent. The
  review loses the mounted skill paths, the invocation, the rule id, and any
  agent or vendor name (`claude`, `codex`, `gpt-*`, `opus`, and so on) that
  the PR and rubric never use. A repo about those tools keeps its own file
  names. `judge.json` lists every redaction.
- **Strict output.** Exactly `{"verdict": ..., "evidence": ...}`, one bare or
  fenced JSON object. The verdict must be one of the case kind's verdicts.
  Anything else is recorded as an error with no verdict, never guessed.
  `evidence_in_review` records whether the evidence quotes the review.

`CANON_JUDGE_STANDIN=evals/canon/offline/judge` swaps in a stand-in at no
cost. It answers with the label of the smallest calibration sample that
contains the judged text.

The judge prompt, with `{verdicts}` and `{meanings}` filled per kind:

```
You are grading one code review of a pull request against a grading guide.

Someone asked a reviewer to review the pull request below before it merges. Decide how the review handles the one concern the grading guide describes. Judge only that concern. Other findings, length, and tone neither help nor hurt.

Allowed verdicts: FOUND, PARTIAL, MISSED.
- FOUND: the review names where the flaw is, says what is wrong, and gives a fix direction the guide accepts.
- PARTIAL: the review touches the flaw but lacks the location, the problem, or a fix direction the guide accepts.
- MISSED: the review does not identify the flaw.

Return only a JSON object with exactly two keys:
- "verdict": one of FOUND, PARTIAL, MISSED.
- "evidence": a short verbatim quote from the review that decides the verdict, or "" when the review says nothing about the concern.

<grading_guide>{rubric.md}</grading_guide>
<pull_request>Title, Description, Diff against main</pull_request>
<review label="review-xxxxxxxx">{review}</review>
<files_the_reviewer_changed_or_added>{workspace.diff or (none)}</files_the_reviewer_changed_or_added>
```

A near-miss case gets `Allowed verdicts: FALSE_ALARM, CLEAN.` with "the
review flags the concern the guide describes as a problem in this pull
request, and the guide says it is not one" and "the review does not flag
that concern as a problem".

**Calibration.** `screen.py calibrate [--judge B:M ...] RULE ...` judges every
labeled sample of every review or document case with each judge (both by default). It
prints agreement per label and stores the record under
`$CANON_CACHE/calibration/<rule>/<case>/<runner>-<backend>-<model>.json`,
where the runner is `model` or `standin`. The record is keyed by the prompt
template version, judge, kind, rubric, PR, and the labeled samples with their
labels, so a change to any of them voids it. A case is calibrated for a judge
only when every sample agreed. Otherwise its run verdicts carry `calibrated: false` with
the reason, `compare` prints `uncalibrated: <reason>`, and the rule line ends
`[judge uncalibrated]`. The samples' precheck results are recorded too. A
sample labeled `FOUND` whose precheck fails means the oracle and the label
disagree.

**Scores.** `compare` prints one review line per agent, rule, and arm, and
writes the same to `compare.json` `review_scores`:

```
codex  discount-review            review amended: recall FOUND 1/1 (1.00), FOUND+PARTIAL 1/1 (1.00); false alarms 0/1 (0.00); precheck 1/1 (1.00); 0 unjudged, 0 uncalibrated
```

Recall counts positive runs and the false-alarm rate counts near-miss runs,
both on the combined verdict. The precheck rate counts positive runs.

**Pilot.** One rule per agent through poteto-mode. Calibrate first, then run
into a fresh `--out`:

```sh
rule=<review rule>
python3 evals/canon/screen.py calibrate "$rule"
python3 evals/canon/screen.py run --runner sbx --agent claude --model sonnet --entry poteto-mode --out "/private/tmp/canon-review/claude-$rule-$(date +%m%d%H%M)" "$rule"
python3 evals/canon/screen.py run --runner sbx --agent codex --model gpt-6-sol --entry poteto-mode --out "/private/tmp/canon-review/codex-$rule-$(date +%m%d%H%M)" "$rule"
```

On 2026-09-25 two Codex judge calls from the omnigent Codex template reached
`chatgpt.com/backend-api/codex` and got `401 Unauthorized: Incorrect API key
provided: sk-svcac...`. The sandbox proxy's stored OpenAI credential was
rejected, so refresh it (`sbx secret set openai --oauth`) before a paid
screen. A Claude judge call with a model name that does not exist got as far
as `unrecognized_model` with every flag accepted.

## Document cases

A document case judges one document the agent writes, with the review
machinery: the same blinded cross-family judge, calibration record, verdict
words, precheck, and scores. `case.json` names the document:

```json
"document": {"file": "ops/premortem.md"}
"document": {"message": true}
```

`file` judges one named file. `message` judges the whole final message. A
document case may be a pasted-project case or a workspace case, and it cannot
also be a review case. Beside the case's usual files it has `rubric.md` and
`samples/labels.json`, as a review case does, and its samples are
`samples/answer-*.md`.

```
rules/premortem-place/
  rule.json           {"source": "...", "arms": ["current", "playbook", "skill"]}
  arms/<arm>.patch    one per arm after current; an arms rule without cases_from owns its cases
  oracle.py           CHECKS[case](answer, project): the precheck, on the whole final message unless the
                      oracle cuts the document itself with `document_text`
  cases/<case-id>/
    case.json         kind, domain, expected_behavior, timeout_s, document
    prompt.md         the request, {project}, and a line asking for the file inside
                      <file path="ops/premortem.md"> and </file> tags
    project/...       the pasted project
    rubric.md         judge only: what FOUND, PARTIAL, and MISSED (or FALSE_ALARM and CLEAN) mean here
    samples/labels.json {"answer-found.md": "FOUND", ...}
    samples/answer-*.md full final messages, chatter and file block included
```

**Delivery.** One function, `shared.document_text(answer, document,
workspace)`, turns a run into the judged text. In a pasted case it cuts the
body of the last `<file path="...">` block for the named path from the final
message and strips one code fence, and it does not raise on an unsafe path in
some other block. In a workspace case it reads the file from the checkout after
the harvested diff, so an untouched file is the checkout's copy and a deletion
is empty. A `message` document is the final message itself. The judge
(`screen.judge_arm`) and calibration (`screen.calibrate`) cut the document
through this function, so a labeled sample is judged exactly as a run is. The
precheck receives the whole final message. It sees the cut document only when
the rule's oracle calls `document_text` itself. The offline agent stand-ins
answer with whole samples, and `offline/judge` matches the smallest sample that
contains the judged text. A labeled sample that would deliver nothing is
refused when the case loads. In a workspace case that names a file, each
sample has a sibling `samples/<name>.diff` that writes the file, as a run's
harvested diff would, and the stand-ins apply it.

**Absent means invalid.** A run that delivers no document is never sent to a
judge. Its record is `verdict: null` with `no document: ops/premortem.md not in
the final message` (or `not in the workspace`), which `compare` prints as
`INVALID` and `scores` counts as unjudged. Scoring absence as `MISSED` would
let a format failure look like a behavior failure, and scoring it as `CLEAN`
on a near-miss would reward an arm that breaks the format.

**Judge.** The verdicts are the review verdicts, `FOUND`, `PARTIAL`, and
`MISSED` for a positive case and `FALSE_ALARM` and `CLEAN` for a near-miss,
with document meanings: FOUND is "the document does what the guide requires,
in a way the guide accepts", FALSE_ALARM is "the document does the thing the
guide says this request must not get". `review.FRAMES` holds the two frames,
`review` and `document`. Every judge function takes a trailing
`frame="review"`, so the review prompt bytes, `TEMPLATE_VERSION`, and every
stored review calibration key are unchanged (`test_review.py` pins the key and
prompt hash of one fixture as computed at 25cfe807). The document prompt holds
the grading guide, the request exactly as the agent read it, project listing
included, and the document under a `document-<sha256[:8]>` label. Its template
version is `document-judge-1`, so document calibration never confuses with
review calibration. The judge never sees the chatter around the file block.
The secret words the sanitizer redacts now include every path the rule's arms
change and each path's tail inside its skill (`playbooks/premortem.md`), for
review and document cases alike. Bare words such as a skill's name stay,
because a document about the change may need them. A Claude judge needs no
sandbox template. A Codex judge needs the pinned Codex CLI, and Sandboxed runs
says how a judge gets it.

**Gates.** `build.json` records `document` per case beside `kind`, and
`run`, `judge`, and `compare` gate on `screen.judged`, which is true for a
review or a document. `calibrate` gates on `case.frame`, which is set for the
same cases. The per-run row in `compare.json` keeps the
key `review` for a document case, so `review_row`, `scores`, and their readers
do not move. That is naming debt, accepted.

**Authoring.** `review_cases.py check` covers document cases: the shape, the
labels, no rule id in `rubric.md`, no meta vocabulary in the prompt or case
id, every sample delivers the document, and, for a pasted case, every `FOUND`
and `FALSE_ALARM` sample passes the precheck. Its table row reads
`pasted document=ops/premortem.md`.
`offline/judge` matches a sample by containment of the judged text, since a
document is cut from its sample, and picks the smallest sample that holds it.
`test_document.py` builds a two-arm premortem rule with a positive and a
near-miss pasted case under a temporary `$CANON_RULES`, calibrates both with
the stand-in judge, and runs the offline `codex` under `--entry poteto-mode`:
the skill arm separates the positive case, tie-passes the near-miss, and the
arm line reads `changed text reached 2/2 run(s); listed by description:
premortem/SKILL.md`.

## Stopped runs

Every command that takes `--out` appends the traceback of any error to
`<out>/screen-error.log` and prints the log's path on both stdout and stderr.
A caller that filters one stream still sees it. `run` logs a failed arm and
goes on to the next arm, then exits 1 naming each failed arm. An arm that
stopped after the agent ran, whether its harvest slots are still numbered
`0001`, ... or it has no `grade.json`, is recovered by `screen.py regrade
--out DIR`. regrade maps the slots with the same tree check as `run`, then
grades each run from its diff. Such a run's `compare.json` row carries
`graded_from_diff` and `ungraded`. A review arm then needs `screen.py judge
--out DIR`.

## Authoring review cases

`review_cases.py check [RULE/CASE ...]` runs the authoring checks the build
does not: the patch applies to the pinned commit as one commit, it changes 50
to 300 lines outside lockfiles, the lines it adds carry no meta vocabulary,
the prompt names the branch and the body file, `rubric.md` does not carry the
rule id, and every `FOUND` and `FALSE_ALARM` sample passes the precheck.
`review_cases.py checkout RULE/CASE DEST` builds `main` and the PR branch
for a look by hand. A review oracle calls `shared.review_names(answer,
location)` with regexes for the flawed file or symbol, or the decoy's.

## Rule texts

R7 says "Write Given, When, Then or Gherkin-style tests" where the draft said
"these tests", because the current skill has no Given, When, Then paragraph. R6
is labeled "Observe through the caller's interface". It sits right before
**The fix** and narrows that paragraph's mock sentence to "For a mock at a
system boundary, assert the payload it received, not that it was called", so
both edits form one hunk. `preparatory-refactor` now sits in step 6 of the
Feature playbook, where the agent orders commits. Its earlier step 3 patch is
kept as `rules/preparatory-refactor/rule.step3.patch`. Codex read that version
and still shipped one commit, because a single-turn answer never writes a
delegate brief.

## Model-free checks

These need Docker, `uv`, and a skill-ci checkout at `../skill-ci` or
`$SKILL_CI` with its `runner.lock`. `audit` and `run` call the harness through
`uv run <skill-ci>/tools/run_runner.py`. Without a running Docker daemon, the
oracle tests that run answer code skip. The `project_test_results` tests
skip unless this machine has built the `omnigent-336207801509` image, which the
`lint` workflow does not build. `audit` and `run` need skill-ci and
`uv`, and so do the offline workspace runs in `test_workspace.py`, which skip
without them. On every pull request the `lint` workflow pulls the image,
checks out skill-ci at the commit `skill-checks.yml` pins, installs uv, and
runs the unit tests.

```sh
docker pull python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36
(cd evals/canon && python3 -m unittest)
python3 evals/canon/screen.py plan
python3 evals/canon/screen.py audit --entry poteto-mode
CODEX_BIN=evals/canon/offline/codex python3 evals/canon/screen.py run --agent codex --out "$(mktemp -d)/offline"
CODEX_BIN=evals/canon/offline/codex python3 evals/canon/screen.py run --agent codex --entry poteto-mode --out "$(mktemp -d)/offline"
```

`python3 -m unittest` runs `test_screen.py`, `test_arms.py`, `test_host.py`
(the host wrapper keeping each run's session), `test_workspace.py`,
`test_review.py` (review checkouts, the judge, calibration, scores, and stopped
runs, with an offline review run when skill-ci is present, and its
`SandboxedReviewRunTests` gated on `CANON_SBX_E2E=1`), `test_review_cases.py`
(the seeded review cases), `test_document.py` (judged document cases, with an
offline document run when skill-ci is present), `test_chain.py`, `test_sandbox.py` (its sandbox runs need
`CANON_SBX_E2E=1`, see Sandboxed runs), and `test_oracles.py`, which loads `oracles/test_shared.py` and every
`rules/*/test_oracle.py`. `test_workspace.py` builds a small repo and its
mirror in a temporary directory. With skill-ci and `uv` present, it also runs a
workspace rule through the offline pipeline and checks both harvested diffs. It
points `$CANON_RULES` and `$CANON_CACHE` at that directory, so the rule never
joins `rules/`. `audit` validates, audits, and prepares both arms of every
case. A positive case's manifest accepts one readiness blocker, "no adversarial
cases", because it holds one case. Any other blocker fails it. The last two
commands run the whole pipeline with a stand-in `codex`. For a positive case it
answers with `good.md` only when the rule text is mounted, and with `bad.md`
otherwise. For a near-miss case it answers with `good.md` in both arms. When
the workspace mounts `skills/pstack`, it exits 3 unless the prompt starts with
`$poteto-mode ` and `.agents/skills` holds the tree. For a workspace case it
also applies the sample's `.diff` in its cwd, and exits 4 without a checkout or
`--sandbox workspace-write`. Both runs must print `SEPARATES` for every
positive case and every rule, and `TIE-PASS` for every near-miss case.

## Paid screen

One paired repetition per case on each agent, through poteto-mode. Use a fresh
`--out` each time.

```sh
codex_bin=/path/to/codex   # a working Codex CLI, with its codex-* helpers beside it
rule=value-type
python3 evals/canon/screen.py run --agent claude --model sonnet --entry poteto-mode --out "/private/tmp/canon-entry/claude-$rule-$(date +%m%d%H%M)" "$rule"
CODEX_BIN="$codex_bin" python3 evals/canon/screen.py run --agent codex --model gpt-6-sol --entry poteto-mode --out "/private/tmp/canon-entry/codex-$rule-$(date +%m%d%H%M)" "$rule"
```

Drop `--entry poteto-mode` for the single-skill screen. `CODEX_BIN` puts that
binary first on `PATH`, so the `exec codex` in `codex-project-only` finds it.
The shim also links every executable `codex-*` file beside the binary, because
Codex starts helpers such as `codex-code-mode-host` from its own directory and
has no shell tool without them. `screen.py compare --out DIR` reprints a
finished run. `--arm NAME` runs only the named arms and writes no
`compare.json`. Run the other arms into the same `--out`, then `compare` it. Runs made before cases existed keep their old `compare.json`,
which `plan` reads. `compare` refuses those directories so it cannot overwrite
that file.

`screen.py regrade --out DIR` grades every run of every workspace case again,
from the run's harvested diff and its `output.md`, read as empty when it is
missing. It uses the oracle and the checkout path in the arm's grader copy,
`arms/<rule>/<case>/<arm>/rules/<rule>/`, which the harness graded with. It
writes `regrade.json` beside each `grade.json` and leaves `grade.json` as it
is. Then it reruns `compare`, which reads `regrade.json` whenever it is
present. A run the harness called INVALID, for a missing or unparseable
answer, gets `"graded_from_diff": true` in its `compare.json` row and a line in
the printed table. A run with no harvested diff keeps the harness grade, and so
does every pasted-project case.

## Sandboxed runs

`--runner sbx` runs each workspace answer inside its own Docker Sandbox
(`sbx`, v0.43.0 here) instead of on the host. A pasted-project case is
refused under this runner. The harness still prepares, times, and grades each
run, and `compare` and `chain.py` read the same directories as before.

```sh
sbx version && sbx diagnose        # daemon healthy, authenticated
sbx secret ls                      # anthropic and openai credentials for the proxy
python3 evals/canon/sandbox.py deps --agent codex --repo omnigent --commit 02969a131c72d74c00c5800d8e82ae831f8ec5e5
python3 evals/canon/sandbox.py probe --agent codex --repo omnigent --commit 02969a131c72d74c00c5800d8e82ae831f8ec5e5
python3 evals/canon/screen.py run --runner sbx --agent codex --model gpt-5.6-sol --entry poteto-mode \
  --case harness-families --out "/private/tmp/canon-sbx/codex-$(date +%m%d%H%M)" converge-within-context
```

Claude Code comes from the kit image, 2.1.280 on 2026-09-25. Codex comes
from the dependency template: `sandbox.py deps` installs `@openai/codex@0.157.0`
(`sbx.json` `agents.codex.cli`) with npm over the kit's copy, so every Codex
run uses 0.157.0. The kit image alone carried Codex 0.149.1 on 2026-09-25,
and the model catalog and tool list below were observed on that kit-only
version. Its catalog lists gpt-5.6-sol, terra, and luna, but not gpt-6-sol,
the host screen's default, so pass `--model` for Codex.

A Codex judge with no case repo (a pasted-project judged case) starts from the
CLI-only template `canon-judge-codex:<digest>`. Build it once per cli pin bump
with `python3 evals/canon/sandbox.py deps --agent codex`. The digest covers the
kit and the cli pin, so a uv bump leaves it alone. Claude needs no template.

Set `CANON_SBX_STANDIN="$PWD/evals/canon/offline/sbx-agent"` to run the same
command at no model cost. The path must be absolute, because the wrapper runs
it from the harness workspace. A relative one makes every run exit 97 with
"sbx-agent plan returned non-zero exit status 2".

Each run goes through `sandbox.py wrap`, which does this:

1. It checks out the pinned commit and overlay in the harness workspace and
   refuses a tree that differs from the build, as `host.py wrap --workspace` does.
   Then it repacks the checkout so it no longer borrows objects from the
   host mirror.
2. It creates one sandbox with `sbx create --clone --skills off`. The agent
   works on a private clone inside the sandbox. The host checkout is mounted
   read-only at `/run/sandbox/source`, and the sandbox cannot write to it.
   `--skills off` keeps sbx's shared skill store out of `~/.claude/skills`.
   No Docker socket is mounted. Before anything runs in the sandbox, it asks
   `sbx policy check network --sandbox <name> <host> --json` about every host
   in `run_deny_network` and about example.org, which no rule names. If any
   answer is not a denial, the run is refused and the agent never starts.
3. It copies in the mounted skills and the overlay as one tar. Under
   `--entry poteto-mode`, `sbx_inside.py setup` then links the tree to
   `.claude/skills` or `.agents/skills` and registers the poteto-agent and
   Comment Sicko personas, and on Claude Code the five `pstack-effort-*`
   delegate agents when the pinned tree ships them, by running `pstack-harness/scripts/subagents.py install
   --harness claude-code|codex --project <clone>` through that link, as a user
   install would. For Codex it also trusts the clone in the sandbox's own
   `~/.codex/config.toml`, since Codex loads project roles only for a trusted
   project. Last, it links the project's dependencies and checks the clone's
   tree against the build. Setup files go to git's exclude list, so they never
   reach the diff. The payload directory is deleted before the agent starts.
4. It runs the agent in the clone with `sbx exec`, under `timeout` at the
   case budget minus 120 seconds. The harness's flags are rewritten for the
   sandbox. Claude drops `--no-session-persistence`, so its transcripts are
   written, and gets `--setting-sources project --permission-mode
   bypassPermissions --strict-mcp-config --allowedTools TodoWrite`. Codex
   drops `--ephemeral` and `--ignore-user-config`, because the sandbox's own
   config holds its proxy provider. It runs `--sandbox danger-full-access`
   with the sandbox's MCP gateway disabled. `bypassPermissions` and
   `danger-full-access` are safe only because the sandbox is the boundary.
   Under `--entry poteto-mode`, the prompt still starts with `/poteto-mode` or
   `$poteto-mode`.
5. `sbx_inside.py harvest` writes the workspace diff and copies the agent's
   session store, `~/.claude/projects` or `~/.codex/sessions`, which holds the
   lead's session and every delegate's. The wrapper copies both out, with the
   sandbox's network log, into the run's harvest slot. Then it removes the
   sandbox, even when the run fails. `sandbox.py gc` removes any `canon-*`
   sandbox a killed run left behind. Do not run it while a screen is running.

The harness takes exactly one terminal `result` event from a Claude stream.
A poteto-mode lead emits one each time it ends a turn while a background
delegate runs, and one more at the end. So for Claude the wrapper reads the
agent's stdout line by line, forwards every other line in order, and writes
the last `result` line last, after any task notification that followed it. It writes the whole stream to `raw-stream.jsonl`
in the harvest dir. Codex's stream passes through unchanged.

The harvest dir of a run holds `workspace.diff`, `workspace.json`,
`network-log.json`, `raw-stream.jsonl` for Claude, and
`transcripts/claude/<project>/<session>.jsonl` with
`<session>/subagents/agent-*.jsonl` and `.meta.json`, or
`transcripts/codex/sessions/YYYY/MM/DD/rollout-*.jsonl`. `workspace.json`
records the sandbox name, the template, the CLI versions, the timings, the
network rules that applied, `reachable`, the policy decision for each model
API host, and `egress`, the decision for each probe host.

After the harness returns, `run` scans the arm's run and harvest dirs. A file
named `.credentials.json` or `auth.json`, or one that holds an `sk-` key or a
JSON access or refresh token, fails the arm before grading, and the error
names each file. A match whose exact bytes also occur in the case's reference
checkout does not count, so a transcript that quotes an upstream test fake
passes. The scan does not delete the files it names. `regrade` runs the same
scan first and skips an arm it refuses, so a regrade never grades a leaked arm.

**Auth.** `sbx secret` stores the credentials on the host, and the sandbox's
proxy adds them to model API requests. Nothing writes them to this repo. A run
directory can still receive one, because harvest copies the agent's
transcripts out of the sandbox. The scan above fails that arm and leaves the
file for you to inspect and delete. The Codex kit writes a `~/.codex/config.toml` whose provider sends
requests to `chatgpt.com/backend-api/codex` through that proxy with a
placeholder token. The Claude kit writes `~/.claude/.credentials.json` inside
the sandbox when it is created, even from a template whose copy was deleted,
and `sbx secret ls` lists the Anthropic secret as OAuth. Whether that file
holds a placeholder or a live OAuth token is unverified. On 2026-09-25 a Claude run
inside the sandbox stopped with "OAuth session expired and could not be
refreshed", so that stored token had most likely expired. Refresh it before a paid Claude run, for example by
storing an API key with `sbx secret set anthropic`, and confirm with one short
prompt. `sbx secret set` supports `--oauth` for OpenAI only.

**Network.** The run requires the host's global policy to deny by default;
`sbx policy ls` shows it, and the probe in step 2 refuses a run where it does
not. Each agent kit adds
its own hosts to that sandbox. Claude's kit adds the Anthropic API,
platform.claude.com, claude.com, code.claude.com, downloads.claude.ai,
bridge.claudeusercontent.com, and mcp-proxy.anthropic.com (`sbx policy ls
--wide` on 2026-09-27). Codex's kit adds chatgpt.com, the OpenAI API, GitHub, npm,
and the Ubuntu archives. A run sandbox adds a per-sandbox deny rule for every package index,
source host, and non-model kit host in `sbx.json` `run_deny_network`, so a run reaches only its
model API. A local deny can only narrow egress. The dependency build is the one
step that reaches PyPI, GitHub releases, astral.sh, and the npm registry,
through per-sandbox allow rules (`build_network`) on a sandbox that is removed
afterwards.

**Dependencies.** `sandbox.py deps` builds one template per agent, repo, and
commit with `--repo` and `--commit`. Without them it builds the CLI-only judge
template, which also deletes the kit's credential files before it saves. With
them it creates a sandbox with no workspace and extracts the pinned commit
under `/opt/canon-deps/<repo>/src`. It installs uv from `sbx.json` (the
kit's uv 0.9.26 is older than omnigent's `required-version`) and the repo's
Python, which is the commit's `.python-version` when it has one and the
repo's `python` in `sbx.json` otherwise. Then it runs `uv sync --frozen`
against the repo's lockfile, plus `--group <tools.group>` when the commit's
`pyproject.toml` declares that dependency group, else `--extra <tools.extra>`,
and refuses a commit that declares neither. omnigent also gets
`OMNIGENT_SKIP_WEB_UI=true`, since its build otherwise runs pnpm. The venv, the uv cache, and the
interpreter live under `/opt/canon-deps`, outside every workspace. The source
copy and the kit's credential files are deleted before `sbx template save`.
At run time setup links `.venv` to that venv and reruns the same `uv sync`
offline, which reinstalls the project's own editable packages from the clone.
If that sync fails, setup refuses the run with the tail of uv's stderr.
The agent runs with `UV_OFFLINE=1`, `UV_PYTHON_DOWNLOADS=never`, and the repo's
env, so `uv run pytest` works without the network. The record of each build
sits under `$CANON_CACHE/sbx/`.

**Tools observed.** `sandbox.py probe` builds a run-shaped sandbox and lists
what the agent is offered without a paid model call. Claude gets a model name
that does not exist, and its init event lists tools, agents, and slash commands
before it fails. A probe whose sandbox setup fails stops there with setup's
stderr, before any check or agent runs. Codex is pointed at a local server inside the sandbox that
records the request and answers 400. Observed on 2026-09-25, with and without
a dependency template:

- Claude Code 2.1.280 runs in `bypassPermissions`. Its tools are Task, Bash,
  Edit, Read, Write, NotebookEdit, Skill, TaskCreate, TaskGet, TaskList,
  TaskUpdate, TaskStop, ToolSearch, WebFetch, WebSearch, Workflow, and
  others. Its agents include poteto-agent and comment-sicko, and poteto-mode
  is a slash command. Without `--allowedTools TodoWrite`, the same `-p` run
  lists none of TaskCreate, TaskGet, TaskList, or TaskUpdate.
- Codex 0.149.1, the kit-only version, gets exec_command, write_stdin, update_plan,
  request_user_input, view_image, web_search, the goal tools, and the
  multi_agent_v1 namespace with spawn_agent, send_input, wait_agent,
  close_agent, and resume_agent. spawn_agent's agent_type lists poteto-agent and comment-sicko. The request
  carries the injected poteto-mode `SKILL.md`. A paid smoke run (one
  poteto-agent spawn replying "ok", gpt-5.6-luna at low effort, 32,611 input
  tokens) showed `collab_tool_call` items for spawn_agent with the brief in
  `exec --json`. The child's rollout names `agent_role: poteto-agent`, starts
  with the persona briefing, and reads `.agents/skills/poteto-mode/SKILL.md`.

**Costs measured** on an Apple silicon Mac on 2026-09-25, with the offline
stand-in on the small test repo: create 4.0 to 4.3 s, setup 3.3 s, harvest
2.4 to 3.0 s, destroy 0.8 s per run. The first sandbox from a kit image took
14 to 18 s. On omnigent with its template, the three arms of one case each took
0.95 to 1.21 s to check out and repack, 4.1 to 4.9 s to create, 4.5 to 5.2 s
for setup (0.43 to 0.62 s of it the offline `uv sync`), 3.8 to 4.4 s to
harvest, and 0.9 to 1.1 s to destroy. The clone inside the sandbox took 142
MB. The four dependency templates:

| template | uv install | sync | save | deps under /opt | image |
|---|---|---|---|---|---|
| codex, omnigent | 56 s | 225 s | 34 s | 604 MB venv, 64 MB cache, 91 MB Python | 1.90 GB |
| claude, omnigent | 130 s | 319 s | 32 s | same | 1.76 GB |
| codex, hermes | 88 s | 188 s | 21 s | 213 MB venv, 52 MB cache, 97 MB Python | 1.39 GB |
| claude, hermes | 65 s | 89 s | 22 s | same | 1.24 GB |

The kit images are 1.27 GB for Codex and 0.92 GB for Claude. In a run from
its template, `uv run pytest --collect-only tests` collected 30,321 omnigent
tests with 24 collection errors, and 50,215 hermes tests with 57 errors, with
no network.

**Offline check.** `test_sandbox.py` unit-tests the argv rewrite, the staging
repack, and `sbx_inside.py` setup and harvest on a plain clone. With a fake
`sbx`, it checks the exact `sbx create` argv and that an allowed probe host
refuses the run before the agent starts. With `CANON_SBX_E2E=1`, `sbx` on
`PATH`, and a skill-ci checkout at `$SKILL_CI` with `uv`, it also runs both arms of a workspace rule for each agent
in real sandboxes with `offline/sbx-agent` as the agent. That stand-in exits
nonzero unless the prompt carries the invocation, the skills are linked, the
persona is registered, the flags give it full tools, and its cwd is the
clone. It applies the sample diff and writes a trace with one worklist call and
one poteto-agent spawn, plus transcripts for the lead and the delegate.
Claude's trace carries two `result` events, and the test checks that
`raw-stream.jsonl` holds both. Both agents print `SEPARATES`, and each takes
about 50 seconds. `chain.py` over that output reports the worklist tool
called, one spawn with the poteto-agent briefing, and the delegate's read of
`poteto-mode/SKILL.md`, for both agents.
The same stand-in, run through `screen.py run --runner sbx` on the three-arm
rule `bundle-separate-contexts-harness` and its omnigent case
`harness-families`, printed `leaf vs current: SEPARATES`, `leaf+trigger vs
current: SEPARATES`, and `leaf+trigger vs leaf: TIE-PASS`.

```sh
(cd evals/canon && CANON_SBX_E2E=1 python3 -m unittest test_sandbox -v)
```

## Chain census

`chain.py` reads finished run dirs and reports, per run, how far the agent
followed the poteto-mode chain. It records the entry and whether the invocation
was injected, which playbooks the lead read, and whether it wrote a worklist and
how much of it copies the playbook's steps. It also records each skill file read
with its event index, whether the rule's owner file came before the first edit
in a workspace case, subagent spawns and whether a spawn's brief names the data
shape, principle citations in the reply, and denied tool calls. It parses Claude
stream-json and Codex `exec --json` traces into one event list, so both agents
go through the same stage code. `test_chain.py` checks the parsers against
real and synthetic traces in `fixtures/chain/`.

```sh
python3 evals/canon/chain.py --markdown                 # stage rates per agent, workspace verdict cross-tab
python3 evals/canon/chain.py --jsonl /tmp/chain.jsonl   # one JSON line per run
```

`--markdown` counts only runs whose entry is poteto-mode, since a single-skill
entry mounts no playbooks. It prints how many it left out, as "N single-skill
entry run(s) left out."

It reads `/private/tmp/canon-entry`, `/private/tmp/canon-ws`, and
`/private/tmp/canon-screen` unless given roots. In those runs Codex's stream
shows waits on a delegate but no spawn or brief, and Claude's `-p` sessions
offer no worklist tool. Those stages read "n/a" or zero because of the
harness, not the agent.

A wrapped run on either runner also harvests the agent's own transcripts next
to its workspace diff, in `harvest/<run>/transcripts/`. Claude writes each delegate to
`claude/<project>/<session>/subagents/agent-<id>.jsonl`, with a `.meta.json`
naming its `agentType` and the lead's spawning `toolUseId`. Codex writes one
rollout per thread under `codex/sessions/`. A child's `session_meta` names its
`parent_thread_id` and `agent_role`. When those files exist, `chain.py` parses
each delegate's reads, edits, spawns, worklist calls, and messages with actor
`delegate`. It places them right after the spawn that started them, so every
stage sees them. They fill `delegation.delegate_reads` and the top-level
`delegate_edits`. A Claude background delegate's events all sit at its spawn
index too, though the lead keeps working while it runs. So `full_suite_run`
can count a lead test run made mid-delegate as after the last edit. No pilot
result changes: across all 6 Claude code-writing delegates, the lead ran no
test while one was running.
A Claude lead's checkout is the cwd of its first `init` record. A turn that a
task notification resumes opens with another `init`, whose cwd is wherever the
lead's shell last moved. A Claude child starts in that shell cwd too, so its
edits are judged against the lead's checkout when its cwd sits inside it, and
against its own cwd otherwise, as in an isolated worktree. A Codex child's
edits are judged against its own cwd. In a sandbox either may sit under
`/tmp`. A run without a `transcripts/` dir yields the same fields as
before.

Two stages use them:

- `worklist_tool` gives `offered`, `called`, and `calls` for the lead. Claude's
  init event says whether TodoWrite or TaskCreate was offered. Codex shows no
  tool list, so `offered` stays `null` until the lead calls `update_plan`,
  seen as a `todo_list` item or in the lead's rollout.
- `delegate_persona` counts the lead's spawns whose delegate got the
  poteto-agent briefing, with each spawn's role. A Claude spawn counts when it
  names `poteto-agent` and the init event lists that agent, when the child's
  meta says `poteto-agent`, or when the brief carries the persona body's first
  sentence from `roles.json`. A Codex spawn counts when the child rollout's role is
  `poteto-agent` or its first developer message is the installed-skill-paths
  briefing. A Codex spawn's `collab_tool_call` prompt is its brief for the
  data-shape stage. Codex 0.157 encrypts the task it sends a child, so its
  children have no readable brief.

**Worklist.** The pstack-harness contract puts the worklist on a structured
tool when one is offered, else in the normal progress messages, which also
take over after a rejected tool call. `worklist.carrier` is `tool`, `message`,
or `none`. `valid_carrier` applies the contract to `tool_offered`, which is
Claude's TodoWrite or TaskCreate in the init tools, or for Codex an
`update_plan` in the rollout's tool list or any `update_plan` call, else
`null`. A message counts as a worklist when it says worklist or names two
playbook steps. Each numbered step of the matched playbook has an identity,
its opening bold heading or else its first clause cut to five words, and
pointers, the bold or backticked skill names in the step and the indented
lines under it. An item keeps a pointer it names bare or with its `principle-`
prefix. `worklist.steps` records per step whether some item keeps the
identity and which pointers that item keeps. The stages are "worklist present
via a valid carrier", "every playbook step listed", and "step pointers
preserved (fraction)", a mean over runs. `verbatim_fraction` stays in the
JSONL.

**Delegate roles.** A routed skill may prescribe its delegates' role, and
poteto-mode defers to it, so those delegates are not persona misses. `PRESCRIBED`
in `chain.py` names each one. Comment Sicko is known by its role or its
briefing line. A how explorer or explainer, why investigator or synthesizer,
architect runner, interrogate reviewer, or reflect reviewer or synthesizer is
known by its template's opening sentence or path in the brief, by the
delegate's own read of that template, or by an agent path that names the
skill, such as `/root/how_harness_family`. When the segment under `/root`
names a skill, that skill decides, so `/root/architect_candidate_2` stays an
architect runner even though it read the how explainer prompt while
grounding. Arena and swarm ship no template,
so their runners are known only by a brief or path that names them. The
stage "implementation delegate ran as poteto-agent" counts code-writing
delegates outside a routed skill. "delegate outside a routed skill got the
poteto-agent briefing" counts every such delegate. `role_census` gives, per
role, spawns, code-writing, prescribed, poteto-agent, and implementation
misses, and `--markdown` prints it per agent.

**Review route.** For a review case every row carries a `review` object,
which is `null` for other cases. `route` lists the review skill files the
lead read, in order and each once. The candidates are
`poteto-mode/playbooks/investigation.md`, `interrogate/SKILL.md`, its
`references/code-quality-review.md` and `references/reviewer-prompt.md`,
`architect/references/design-red-flags.md`, `how/SKILL.md`, and any other
poteto-mode playbook. `primary` is the first route, or `none`.
`principle_leaves` splits the principle `SKILL.md` reads between lead and
delegates. `delegated` gives the spawn count and each spawn's role, with
interrogate reviewers known through `PRESCRIBED`. The object also holds
`pr_modified` with `pr_paths`, `head_moved`, and the judge's combined verdict
and calibration from `judge.json`. `--markdown` adds a review table per agent,
with primary route counts, reference, leaf, and delegation rates, and primary
route by combined verdict. Pass review run dirs as roots, since
`/private/tmp/canon-review` is not a default root.

**Result events.** A Claude lead that ends a turn while a background delegate
runs emits a `result` each time. The last one is the answer, and
`result_events` counts them. For a sandboxed Claude run, `chain.py` reads
`harvest/<run>/raw-stream.jsonl` in place of `trace.jsonl` when it exists. A
run that `screen.py regrade` graded takes its verdict from `regrade.json`.

**Delegate returns.** Three stages ask when a delegate returned to the lead.
A foreground Claude spawn returns in its Agent or Task tool_result. A
background one first gets an "Async agent launched" result with its agentId.
It returns later, in a `<task-notification>` user message or, in
stream-json, a `system` record with subtype `task_notification`. Either names
its tool-use-id, or its agentId as the task-id. A Codex child returns at the
first `wait` whose `agents_states` shows it no longer pending or running.
When the trace shows none of these, the child's own first `task_complete`
stands in. Codex 0.157's stream shows no spawn and names no child in a
wait, so its children are placed by time. Every rollout line carries a
timestamp. The lead's rollout, the one whose first `session_meta` has
`thread_source` `user`, records the stream's messages, commands, and collab
calls in the same order, so the kth of each kind in one is the kth in the
other. That gives each stream line a time. A child's spawn sits at its
rollout's first line, and each of its events, its `task_complete` included,
sits after the last lead line at or before it. When the harvest holds no lead
rollout, or the two disagree on kinds or commands, the children are attached
after the lead's last line with no place in lead order. Each of these stages
counts such delegates or edits as `unordered` and reads `null` where order
decides the answer.

**Delegate wrote code.** `delegated_code` is true when any delegate made a
workspace edit, the same edits `delegate_edits` lists. A workspace edit is an
edit tool call, or a shell redirect, `sed -i`, or write verb, whose path lands
in the checkout. A relative shell write path joins the `cd` before it in the
same command, so `cd /tmp && cat > sanity.mjs` writes `/tmp/sanity.mjs`. A
write to an unexpanded variable or substitution (`"$tmpclean"`,
`"$(dirname "$scratch")"`) or a `~` path is not an edit. Agents aim those at
scratch files outside the checkout. A `cd` to a variable or substitution, or
any `cd` inside a subshell, leaves later relative writes unjoined, so they
still count as edits. A `cd` in one tool call does not carry into the next,
and `cd ..` is not resolved, so a relative write after either counts as an
edit.

**Lead inspection.** `lead_reviewed_delegate` gives `code_delegates`,
`reviewed`, `all`, and `unordered`. A code-writing delegate counts as
inspected when the lead does one of these after the delegate returned and
before the lead's last message:

- It reads a file that delegate edited, with Read or with a shell read verb,
  `rg`, or `grep` naming the file. Paths match on their trailing components,
  so `src/tree.py` names `/workspace/app/src/tree.py`.
- It runs `git diff`, `git show`, or `git status`.

One read of one edited file, or a bare `git status`, is enough, so the
stage shows the lead looked at the work, not that it reviewed the whole
diff. A delegate that never returns is not inspected. `all` is `null` when
no delegate wrote code or one of them is unordered. The stage is "lead
inspected code-writing delegate's work (all)".

**Parallel investigation.** An investigation spawn is a delegate the lead
spawned itself that `prescribed_by` gives a `how` or `why` role, or an
unprescribed delegate of an explore type (Claude's `Explore`, Codex's
`explorer`) that the lead spawned and that wrote no code. A Codex child of a
child, such as `/root/how_lint_subsystem/direct_explainer`, runs while its
parent waits on it, so it is part of its parent's investigation and does not count.
A delegate another routed skill prescribes (architect, arena, interrogate,
reflect, swarm, no-comments) is never investigation, even when it only
reads. So a Codex architect cross-judge spawned as `explorer` stays out,
because its `architect_` path names architect. A spawn is in flight from its
spawn until it returns, or to the end of the trace.
`parallel_investigation` gives `investigation_spawns`, `max_in_flight`,
`parallel`, and `unordered`. `parallel` is true when two were in flight at
once. It is `null` when two or more exist, fewer than two overlap, and one is
unordered. A run without transcripts cannot tell which delegates wrote code,
so every unprescribed explore-type spawn counts there. The stage "delegated
investigation" is true when a run has any investigation spawn, so a run with
none reads as a miss. The stage "parallel investigation spawns" rates only
the runs that delegated investigation.

**Investigation first.** `investigation_before_first_edit` gives the event
index of the lead's first investigation spawn (the same spawns as parallel
investigation), of its own first workspace edit, and of its first
code-writing spawn, with `before`. `before` is true when the investigation
spawn comes before both, a missing edit or code-writing spawn counting as
later. It is false when the run has no investigation spawn or the spawn comes
at or after either, and `null` when one of the three has no lead order. The
stage is "investigation before first edit". An edit made only through a script,
such as a `python3` heredoc that opens a file for writing, is not seen as an
edit, so a spawn after it can still count as before.

**Wide test run.** `full_suite_run` takes the run's last workspace edit by
any actor and lists `test_commands_after`, every test command any actor ran
after it. A command counts even when it exits nonzero. The runners are
pytest, including `python -m pytest`, `uv run pytest`, and hermes's
`scripts/run_tests.sh` wrapper, `python -m unittest`, `npm`, `pnpm`, or `yarn
test`, also after `--prefix`, `-C`, `--dir`, or `--cwd <dir>`, `node --test`, `go test`, `cargo test`,
and `just test`. A pytest run is single when every target is a
`path::name` node id or a `-k` selector. A unittest run is single when every
target is a `Class.test_method` dotted name or a `-k` selector. A file,
directory, module, or no target is wide, and so is every other runner.
`wide` is true when some command after the edit is wide. It is `null` when
the run made no edit or an edit is unordered, which `ordered` shows. The
stage is "wide test run after last edit".

`fixtures/chain/sbx-codex/` holds trimmed files from a real Codex sandbox
probe. `fixtures/chain/sbx-claude-background/`,
`fixtures/chain/sbx-codex-timestamps/`, and `fixtures/chain/sbx-codex-nested/` are trimmed from the
`/private/tmp/canon-cuts` pilot runs, with the sandbox temp path renamed. `fixtures/chain/sbx-codex-roles/` and `claude-multi-result.jsonl` are
trimmed from real `/private/tmp/canon-sbx` runs. `fixtures/chain/sbx-claude/`,
`fixtures/chain/sbx-claude-review/`, and `fixtures/chain/sbx-codex-review/` are
synthetic, and so is the lead trace under `fixtures/chain/sbx-codex-delegates/`
(its harvested child transcripts are real).
`fixtures/chain/sbx-claude-delegates/` and `fixtures/chain/sbx-codex-parallel/`
are synthetic too. They follow the return shapes above, the Claude ones as a
Claude Code session transcript records them.

## Held-cuts screen

Upstream cut some prose after testing it only with an Opus 5.5 lead. This
screen asks whether those cuts change what a GPT-5.6 Codex lead or a Sonnet
lead does. Every rule reads `skills/` at fcc6c78f, which has the six lines
64aac129 held and upstream #414's cuts.

| arm rule | arms | cases from | case | repo |
|---|---|---|---|---|
| `restore-tdd-nearby-validation` | current, restored | `nearby-validation` | `paste-markers` | hermes |
| `cut-bug-fix-review` | current, cut | `nearby-validation` | `paste-markers` | hermes |
| `cut-feature-review` | current, cut | `feature-review-diffs` | `no-debugger-lint` | omnigent |
| `cut-refactor-review` | current, cut | `refactor-review-diff` | `lint-report-loop` | omnigent |

`restored` puts back poteto-tdd step 7 as upstream 70b2dc8 removed it. Each
`cut` arm removes the held sentences from one playbook. Each base rule holds
the case and oracle, and its `rule.patch` is the same edit as the arm patch.
Run the arm rules.

Read a `cut` line the other way round from an amendment. A cut that hurts
shows as `cut vs current: REVERSES`. `SEPARATES` there means the cut arm did
better. A tie in one repetition says only that this pair showed no
difference. The restored arm counts as exposed only when it reads
`poteto-tdd/SKILL.md`, which the Bug fix playbook routes to only for a cheap
local test path, so `unexposed` is a likely outcome there.

- **paste-markers.** A user reports that a `[200~` paste marker stays in the
  prompt when the paste follows a typed word. Stripping `[200~` anywhere fixes
  the report but breaks `test_does_not_strip_non_wrapper_bracket_forms_in_normal_text`
  in the same module, and the prompt does not say so. The oracle runs the
  pinned `tests/hermes_cli/test_input_sanitize.py` and
  `tests/hermes_cli/test_cli_bracketed_paste_sanitizer.py`, the second
  through a `cli.py` shim, plus three reported cases.
- **no-debugger-lint.** A new `no-debugger` custom lint rule, across a new
  module, the `custom_lint.py` registry, and tests. The oracle runs held
  cases for every debugger shape, strings and comments, the disable comment,
  the standalone exit codes, and registration after the existing rules.
- **lint-report-loop.** Move the argv report loop two omnigent lint scripts
  share into `_framework.py`. The asyncio lint prints a hint line after every
  hit, and a shared per-hit label drops it. The oracle checks that the loop
  moved, then runs held stdout and exit-code cases for both scripts. It runs
  each script as the pre-commit hook does, `python3 dev/lint/<script>.py
  <files>` from the repo root, so `from _framework import` resolves and
  `from dev.lint._framework import` does not. The venv's editable install
  exposes only `omnigent*`, so the hook cannot import `dev` either.

`chain.py` reports the stages these cuts target: whether a delegate wrote
code, whether the lead inspected its work, parallel investigation spawns, and a test
run wider than one test after the last edit.

```sh
for rule in restore-tdd-nearby-validation cut-bug-fix-review cut-feature-review cut-refactor-review; do
  python3 evals/canon/screen.py run --runner sbx --agent claude --model sonnet --entry poteto-mode \
    --out "/private/tmp/canon-cuts/claude-$rule-$(date +%m%d%H%M)" "$rule"
  python3 evals/canon/screen.py run --runner sbx --agent codex --model gpt-5.6-sol --entry poteto-mode \
    --out "/private/tmp/canon-cuts/codex-$rule-$(date +%m%d%H%M)" "$rule"
done
python3 evals/canon/chain.py --markdown /private/tmp/canon-cuts/*
```

## Spawn-step screen

This screen asks whether a Bug fix step 2 that spawns investigators before
the lead reads source changes what the lead does and what it ships. The
`spawn-step` arm tells the lead to spawn the `how` skill's explainer over the
affected subsystem and a **why** skill investigator over its regression
history, in one message, and to reproduce while they run. `spawn-step-paste`
and `spawn-step-history` read `skills/` at 4fe21347, and the `spawn-step-hard`
rules at 324b3e80, whose `skills/` tree is the same.

| arm rule | arms | cases from | case | repo | history |
|---|---|---|---|---|---|
| `spawn-step-paste` | current, spawn-step | `nearby-validation` | `paste-markers` | hermes | no |
| `spawn-step-history` | current, spawn-step | `bug-fix-spawn-step` | `zsh-first-tab` | hermes | yes |
| `spawn-step-hard` | current, spawn-step | `bug-fix-hard-history` | `subshell-push` | omnigent | yes |

The base rule `bug-fix-spawn-step` holds the zsh case and its oracle, and its
`rule.patch` is the same edit as the arm patch. Run the arm rules.

Eval mirrors are depth 1, so only a case with `"history": true` shows the
agent any git history. `paste-markers` is not one, so its checkout gives a
`why` investigator one commit and no history to read. There, a spawn step can
change what the lead reads first but cannot hand it a regression's story.
`zsh-first-tab` is the case where history holds the answer.

- **zsh-first-tab.** A user saved `hermes completion zsh` as `_hermes` on
  their fpath, and the first `hermes <TAB>` in every new shell completes
  nothing. compinit autoloads `_hermes` from that file, so the first TAB runs
  the file as the function's body. The file ends with `compdef _hermes
  hermes`, which only registers the function the body just defined. The
  obvious fix ends the file with `_hermes "$@"`, as other completion files do.
  That breaks the documented install, `eval "$(hermes completion zsh)"`,
  which then runs `_arguments` outside a completion and never calls
  `compdef`. The script's header comment names the eval install. Only git
  history says the bare call was tried and failed. a686dbdd26 shipped
  `_hermes "$@"`, 8c4bec6155 "fix(cli): repair broken zsh completion
  generation" swapped it for `compdef` with a test, 6d30b4a7e3 added
  `test_zsh_eval_style_source_registers_after_compinit`, and 6b81590c55's
  suite-wide prune removed those two regression tests. The remaining zsh
  syntax tests went later, in d09dacf66a. The pinned
  `tests/hermes_cli/test_completion.py` has none.

The oracle runs the pinned `tests/hermes_cli/test_completion.py` and four
held checks against the completion module the diff leaves. The grader image
has no zsh, so the held checks read the generated script's structure. The
script's lines outside any function body count as its top level, and a line
counts as guarded when an enclosing `if` or `case`, or the line itself,
names `funcstack`, `zsh_eval_context` or `ZSH_EVAL_CONTEXT`, `compstate`, or
`$0`. The checks are:

- line 1 is `#compdef hermes`
- a top-level `compdef _hermes hermes` exists
- a top-level call to `_hermes` exists
- no top-level call to `_hermes` is unguarded

A structural pass is not a zsh run. The checks cannot tell which branch a
guard takes, so an inverted guard passes and breaks both installs. They fail
a working guard written with another test, such as `[[ ${(%):-%N} == _hermes
]]`, and miss a fix in `hermes_cli/main.py` that post-processes the script. Brace counting
ignores only single-quoted text, so a function written on one line, or a
brace inside double quotes, can hide or expose a line.
`RealZshCalibrationTests` in the rule's `test_oracle.py` runs when `zsh` is
on `PATH`. For ten endings of the script, it checks the structural grade
and what a fresh `zsh -f -i` does on the first TAB from an fpath file and
after `eval`, and whether `eval` prints an error. On zsh 5.9 the grade passed
exactly the endings that worked in both installs with no error, except two. The inverted
guard passed and works in neither. The `${(%):-%N}` guard failed and works in
both. Each run takes about 30 seconds.

The case needs the history mirror, fetched once:

```sh
python3 evals/canon/workspace.py fetch hermes 130b8f2c5dbca93a81aa396dd2ba44420d78f6f0 --history
```

On 2026-09-28 the fetch took 29 minutes over the network. The mirror holds
41,953 commits and 382,628 objects in one 867 MB pack. A fetch killed partway
leaves a `tmp_pack_*` file in the mirror's `objects/pack/`, and the next
`fetch` starts over; delete the stale temp pack by hand. On an Apple silicon
Mac, a history checkout took 2.2 s, as a depth-1 one does. Staging it for a
sandbox took 2.9 s more to repack, since the clone carries the 846 MB of
history, and a plain clone of the staged copy held all 41,953 commits. In
sandboxed stand-in runs of `spawn-step-history`, each arm took 4.9 to 5.1 s
to check out and repack, 4.2 to 4.8 s to create, 4.0 to 4.7 s for setup,
and 3.0 to 3.6 s to harvest, for both agents.

```sh
for rule in spawn-step-paste spawn-step-history; do
  python3 evals/canon/screen.py run --runner sbx --agent claude --model sonnet --entry poteto-mode --runs 4 \
    --out "/private/tmp/canon-spawn/claude-$rule-$(date +%m%d%H%M)" "$rule"
  python3 evals/canon/screen.py run --runner sbx --agent codex --model gpt-5.6-sol --entry poteto-mode --runs 2 \
    --timeout 2700 --out "/private/tmp/canon-spawn/codex-$rule-$(date +%m%d%H%M)" "$rule"
done
for i in 1 2 3 4; do
  python3 evals/canon/screen.py run --runner sbx --agent claude --model sonnet --entry poteto-mode --timeout 2700 \
    --out "/private/tmp/canon-hard/claude-$i-$(date +%m%d%H%M)" spawn-step-hard
done
python3 evals/canon/screen.py run --runner sbx --agent codex --model gpt-5.6-sol --entry poteto-mode --runs 2 \
  --timeout 2700 --arm current --out "/private/tmp/canon-hard/codex-$(date +%m%d%H%M)" spawn-step-hard
python3 evals/canon/chain.py --markdown /private/tmp/canon-spawn/* /private/tmp/canon-hard/*
```

Read `spawn-step vs current` per case, then the chain stages "delegated
investigation", "parallel investigation spawns", and "investigation before
first edit". A `SEPARATES` on `zsh-first-tab` with no change in those stages
says the arm helped some other way.

**Result, 2026-09-28.** The pilot ran one paired run per rule and agent on Sonnet and gpt-5.6-sol leads, plus two `spawn-step` runs per case on an Opus lead. The step changed nothing on either model, so it did not ship:

- Claude spawned no investigator in any of the 8 runs: 4 Sonnet (current and spawn-step) and 4 Opus (spawn-step). It read the rewritten step in 5 of the 6 spawn-step runs, then read the source itself and fixed the bug in 10 to 17 tool calls. The lead had `Task` with `Explore`, `general-purpose`, and `poteto-agent` available, and it opened no worklist.
- Codex spawned parallel `how` and `why` investigators before its first edit in all 4 runs, with the step and without it.
- Every run passed its hidden tests.
- On `zsh-first-tab`, Codex's investigators found a686dbdd26, 8c4bec6155, 6d30b4a7e3, and 6b81590c55 with `git log` in the history checkout. The history case reaches the agent.

Claude treats investigation fan-out as a proportionality call on a single-file bug, and it passed without it. A case that separates the two behaviors needs a bug whose cause spans subsystems and lives in history.

`spawn-step-hard` runs that case with the same two arms. Its base rule
`bug-fix-hard-history` holds `subshell-push` on omnigent 02969a13 with
history, and both rules read `skills/` at 324b3e80, whose `skills/` matches
4fe21347. The case needs the omnigent history mirror, fetched with
`workspace.py fetch omnigent 02969a131c72d74c00c5800d8e82ae831f8ec5e5
--history`, which holds 4,112 commits.

- **subshell-push.** A user reports that the GitHub policy denies a push to a
  fork but allows `(git push <fork> main)`. The cause is the shell parser in
  `omnigent/policies/builtins/_shell.py`, which the GitHub and
  working-directory policies share. It splits segments only on chaining
  operators, so `(`, `{`, and `<(` hide the command from both policies.
  Patching `github.py` alone leaves `{ … }`, `<( … )`, and the wrapped `cd`
  open. The obvious fix splits on `(){}`. e6b1c83a (#7999) shipped that split,
  then a quote-aware version, and reverted both in the same squash. Its
  message says splitting broke brace expansion (`main{,} feature` pushed the
  second branch), escaped quotes, and comments with an apostrophe. It asks
  for a follow-up that extracts `<(…)` bodies and strips leading grouping
  tokens. No code comment or test at the pin says so, and the quote-aware
  splitter passes every pinned test.

The oracle runs the pinned `test_github.py`, `test_working_dir.py`, and
`test_shell_nesting.py` with a small pytest stand-in (parametrize, raises,
asyncio) and stubs for the modules that need pydantic. A pinned test counts
only when it passes on the checkout. The 8 engine and registry tests that
need the real modules fail on both trees. It then runs twelve held cases
against the diff's tree:

- the four wrapped pushes to the fork are denied
- the two wrapped `cd /etc` are denied
- brace expansion, a brace list, an escaped quote, and an apostrophe in a comment still deny
- a wrapped push to `acme/storefront` main and a wrapped `cd` inside the workspace are allowed

The good sample strips grouping in `_shell.py` and drops the local paren
strip in `working_dir.py`. The `(){}` split fails 3 pinned tests and the two
brace cases. The quote-aware split fails the four history cases and no pinned
test. The `github.py`-only patch fails five of the six wrapped cases. With
omnigent's test group installed, pytest on the host gave the same verdicts
for the checkout and all three samples.

**Result on `subshell-push`, 2026-09-28.** This ran 4 paired Claude Sonnet runs, current against spawn-step, and 2 Codex gpt-5.6-sol runs on `current`, each with a 2700 s cap.

- **Claude passed 8 of 8, in both arms.** No run delegated investigation or code, including the spawn-step arm. Every run fixed the shared parser, `_shell.py`, rather than `github.py`, by stripping grouping tokens and extracting `<(…)` bodies, and none took the quote-aware splitter. 4 of the 8 listed e6b1c83a in a `git log --oneline` of the parser or `github.py`, which shows only its title. No run read its message, where the revert is, so every run reached the fix from the code.
- **Codex failed 2 of 2.** One run left the brace-group and process-substitution pushes open, and the brace-group `cd`. The other denied a wrapped push to the allowed repo and branch, because it left trailing parentheses on the refspec. One of the two delegated investigation, and both delegated the code change.
- **Reading.** On a multi-module bug, a Claude lead that investigates inline did not lose correctness. No run read the history, so this case did not test whether history helps: the correct fix is reachable from the code alone. The spawn step is not proposed.

## Reading the result

Read the rule line first, then the case lines. A near-miss case that never ran
shows as `missing` and blocks the rule. An `unexposed` pair is not a tie. It
means the amended arm never read the patched file, and it blocks the rule for a
near-miss case too. One repetition cannot show
that a rule helps. It shows whether the pair separates in the predicted
direction. When both arms pass a positive case, the case cannot show a
difference. If neither agent separates, drop the rule rather than tuning the
fixture until it does. Before promotion, a rule needs repeated pairs and at
least one near-miss case that holds.

## Confounds shared by both arms

- The harness wraps every prompt with "Return the final answer for this eval
  task. Do not include hidden answer keys or rubrics." The screen cannot remove
  it without a harness change.
- Under the poteto-mode entry the invocation comes first, and the harness's own
  preamble follows it: "Read and follow the skill file(s) below", the
  `skills/pstack` path, then "Task prompt:" and the case prompt.
- The BDD prompts say "test" because that is the task. The skill's own name
  contains it too.
- Under the single-skill entry only one skill is mounted, so links to sibling
  skills do not resolve.
- `codex-project-only` keeps `CODEX_HOME`, so `~/.codex/AGENTS.md` and hooks may
  load. The pinned harness source (c2a1735) also swaps in a scratch
  `CODEX_HOME` with only `auth.json` and `config.toml`, and passes
  `--ignore-user-config --ignore-rules`. That was read from source, not
  observed. Either way both arms load the same files.
- Each run answers `current` before `amended`, so time of day differs between
  the arms.
