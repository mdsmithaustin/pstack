# One-rule amendment screen

This directory screens candidate rules for skills that already exist. Each
comparison is the current skill text against the same text plus one rule. It
does not compare a skill against no skill.

## What runs

For each case of each rule, `screen.py` builds two arms from the working tree:

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
judge runs.

A rule has one or more cases. A `positive` case is one where the rule should
change the answer. A `near-miss` case is one where the rule must not change it.
A rule `SEPARATES` only when every positive case separates and no near-miss case
reverses or goes ungraded.

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
```

Each arm root holds the grader next to the skill tree: `oracles/`, the rule's
`oracle.py`, and the case's `project/`. A workspace case's arm holds
`workspace.json` naming the pinned checkout in place of `project/`, and a
`workspace/` directory that the entry wrapper reads. It never holds `samples/`,
`test_oracle.py`, or `oracles/test_*.py`. The answering agent works in a
separate temporary workspace. A Claude trace showed its cwd under
`/private/var/folders/.../claude-ws-*`, and a Codex run's `environment.json`
records `<isolated workspace>`.

## How to add a rule

1. Create `rules/<id>/rule.json` with the research source. If the rule routes
   to a skill that users install beside pstack, list it in `companions`.
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
oracle from `cases_from`, as a variant does. Under `--entry skill` the arms
mount every skill any arm changes.

`build` writes `arms/<rule>/<case>/<arm>/` for every arm in order.
`build.json` records `"patch_kind": "arms"`, `"arms"` in order, and
`"arm_changes"`, which maps each arm to the files it changes (`current` has
none). `"target"` is the first changed file of the first arm after current, for
older readers. A pair rule's `build.json` also records
`"arms": ["current", "amended"]`.

`compare` prints one row per case and run with every arm's verdict in order,
each arm's changed files and how many it read, then one line per comparison:
each arm against current, then each later arm against each earlier one, as
`leaf+trigger vs leaf: TIE-PASS`. The exposure target of a comparison is the
set of files that differ between the two arms. The later arm is exposed when it
read one of them, or under `--entry poteto-mode` when one of them is
`poteto-mode/SKILL.md`. Each arm after current gets its own rule line against
current, `rule leaf vs current run-1 SEPARATES`. In `compare.json` these pair
entries add `baseline` and `treatment`, and these rule entries add `arm`. `plan`
lists an arm rule's arms and each arm's changed files. `chain.py` counts every
arm the build lists, and takes an arm's owner file to be the first file its
patch changes.

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
read, command, and tool events whose input names the file. It also reports
whether Claude's trace shows the `/poteto-mode` command. Each pair gets one
outcome: `separates`, `tie-pass`, `tie-fail`, `reverses`, `invalid`, or
`unexposed`. `unexposed` means the amended arm never read the patched file, so
the pair says nothing about the rule. A read through a glob or a directory-wide
grep does not count. Codex's `exec --json` stream does not show whether it
injected the entry skill, and Claude's `-p` stream does not echo the prompt, so
no trace shows the injection. Under `--entry poteto-mode` a rule patched into
`poteto-mode/SKILL.md` therefore counts as exposed without a read, because the
wrapper starts every prompt with the invocation.

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
`skills/<name>` and its `SKILL.md` joins `skill_paths`. The build refuses a
companion whose name matches a pstack skill.

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
such as a seeded `CONTEXT.md`. The case has no `project/`, and its `prompt.md`
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

The harness copies only single files into its workspace, flattened into
`inputs/`, so the entry wrapper builds the checkout itself. It runs
`workspace.py wrap` in the agent's cwd, which already holds the mounted skills.
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
`rg --pre`, and `git grep -O`. A run with a model that does not exist, which
costs nothing, accepted both flags on 2026-09-24, and an unknown flag fails
the same run at parsing. No run has yet shown each rule matching a command.

When the agent exits, `wrap` writes a binary diff of the workspace against that
tree to a slot outside the workspace. The diff covers edits, deletions, and new
files that git does not ignore. A rename shows as a deletion and an add. The
harness seals each run directory, so `run` moves each slot to a parallel tree.
The run dir `<out>/<agent>/<rule>/<case>/<arm>/runs/<run>` maps to
`<out>/<agent>/<rule>/<case>/<arm>/harvest/<run>/workspace.diff`, beside a
`workspace.json` with the tree id and timings. `run` refuses a run whose
workspace had a different tree.

`build` checks out the commit plus overlay once per spec under the cache and
writes its path into the arm's `rules/<id>/cases/<case>/workspace.json`. The
wrapper's input is the arm's `workspace/` directory, which holds
`workspace.json` (repo, commit, mirror, tree id) and `overlay/`. `build.json`
records the repo, commit, tree id, checkout path, and one hash per arm of the
workspace input, and refuses the build if the hashes differ. It also refuses a
repo that tracks a path the mounted skills take.

A workspace case's check receives a `shared.Workspace` in place of the project.
`workspace.checkout` is the pinned checkout with the overlay, and
`workspace.diff` is the run's diff. `shared.apply_diff(checkout, diff)` returns
the new bytes of every path the diff touches, with `None` for a deleted path.
The samples are `good.md` and `bad.md` with a `good.diff` and `bad.diff` beside
them. `test_oracle.py` passes `workspace=Workspace(checkout, diff)` to `grade`.
The offline stand-in applies the chosen sample's diff in its cwd. The sample
tests skip when the mirror lacks the pinned commit.

The omnigent cases grade the diff statically, with the AST of the Python files
it touches. Their upstream tests need pyyaml, pydantic, and pytest, which the
networkless image does not have. omnigent's `AGENTS.md` asks for `pre-commit`
before any commit, so each prompt says there is no need to commit. It also
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

## Authoring review cases

`review_cases.py check [RULE/CASE ...]` runs the authoring checks the build
does not: the patch applies to the pinned commit as one commit, it changes 50
to 300 lines outside lockfiles, the lines it adds carry no meta vocabulary,
the prompt names the branch and the body file, `rubric.md` does not carry the
rule id, and every `FOUND` and `FALSE_ALARM` sample passes the precheck.
`review_cases.py checkout RULE/CASE DEST` builds `main` and the PR branch
for a look by hand. A review oracle calls `shared.review_names(answer,
location)` with regexes for the flawed file or symbol, or the decoy's.

`pending/<rule>/<case>/` holds review cases that need a commit on `main`
before the PR, in `base.patch`, which the harness does not build. No loader
reads that directory. `notation-not-runtime/trivial-routing-suggestion` needs
pytest-bdd adopted on `main`, and `domain-words/session-spend-stats` needs a
`CONTEXT.md` there.

## Rule texts

R7 says "Write Given, When, Then or Gherkin-style tests" where the draft said
"these tests", because the current skill has no Given, When, Then paragraph. R6
is labeled "Observe through the caller's interface". It sits right before **The
fix** and narrows that paragraph's mock sentence to "For a mock at a system
boundary, assert the payload it received, not that it was called", so both edits
form one hunk. `preparatory-refactor` now sits in step 6 of the Feature
playbook, where the agent orders commits. Its earlier step 3 patch is kept as
`rules/preparatory-refactor/rule.step3.patch`. Codex read that version and still
shipped one commit, because a single-turn answer never writes a delegate brief.

## Model-free checks

These need Docker, `uv`, and a skill-ci checkout at `../skill-ci` or
`$SKILL_CI` with its `runner.lock`. `audit` and `run` call the harness through
`uv run <skill-ci>/tools/run_runner.py`.

```sh
docker pull python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36
(cd evals/canon && python3 -m unittest)
python3 evals/canon/screen.py plan
python3 evals/canon/screen.py audit --entry poteto-mode
CODEX_BIN=evals/canon/offline/codex python3 evals/canon/screen.py run --agent codex --out "$(mktemp -d)/offline"
CODEX_BIN=evals/canon/offline/codex python3 evals/canon/screen.py run --agent codex --entry poteto-mode --out "$(mktemp -d)/offline"
```

`python3 -m unittest` runs `test_screen.py`, `test_arms.py`, `test_workspace.py`,
`test_chain.py`, `test_sandbox.py` (its sandbox runs need `CANON_SBX_E2E=1`,
see Sandboxed runs), and `test_oracles.py`, which loads `oracles/test_shared.py` and every
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
rule=notation-not-runtime
python3 evals/canon/screen.py run --agent claude --model sonnet --entry poteto-mode --out "/private/tmp/canon-entry/claude-$rule-$(date +%m%d%H%M)" "$rule"
CODEX_BIN="$codex_bin" python3 evals/canon/screen.py run --agent codex --model gpt-6-sol --entry poteto-mode --out "/private/tmp/canon-entry/codex-$rule-$(date +%m%d%H%M)" "$rule"
```

Drop `--entry poteto-mode` for the single-skill screen. `CODEX_BIN` puts that
binary first on `PATH`, so the `exec codex` in `codex-project-only` finds it.
The shim also links every executable `codex-*` file beside the binary, because
Codex starts helpers such as `codex-code-mode-host` from its own directory and
has no shell tool without them. `screen.py compare --out DIR` reprints a
finished run. Runs made before cases existed keep their old `compare.json`,
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
  --case harness-families --out "/private/tmp/canon-sbx/codex-$(date +%m%d%H%M)" separate-contexts
```

The agent CLIs come from the kit images. On 2026-09-25 those were Claude Code
2.1.280 and Codex 0.149.1. That Codex's model catalog lists gpt-5.6-sol, terra, and luna,
but not gpt-6-sol, the host screen's default, so pass `--model` for Codex.
Set `CANON_SBX_STANDIN=evals/canon/offline/sbx-agent` to run the same command
at no model cost.

Each run goes through `sandbox.py wrap`, which does this:

1. It checks out the pinned commit and overlay in the harness workspace and
   refuses a tree that differs from the build, as `workspace.py wrap` does.
   Then it repacks the checkout so it no longer borrows objects from the
   host mirror.
2. It creates one sandbox with `sbx create --clone --skills off`. The agent
   works on a private clone inside the sandbox. The host checkout is mounted
   read-only at `/run/sandbox/source`, and the sandbox cannot write to it.
   `--skills off` keeps sbx's shared skill store out of `~/.claude/skills`.
   No Docker socket is mounted.
3. It copies in the mounted skills and the overlay as one tar. `sbx_inside.py
   setup` then links the tree to `.claude/skills` or `.agents/skills`. It
   registers the poteto-agent and Comment Sicko personas by running
   `pstack-harness/scripts/subagents.py install --harness claude-code|codex
   --project <clone>` through that link, as a user install would. For Codex
   it also trusts the clone in the sandbox's own `~/.codex/config.toml`, since
   Codex loads project roles only for a trusted project. Last, it links the
   project's dependencies and checks the clone's tree against the build.
   Setup files go to git's exclude list, so they never reach the diff. The
   payload directory is deleted before the agent starts.
4. It runs the agent in the clone with `sbx exec`, under `timeout` at the
   case budget minus 120 seconds. The harness's flags are rewritten for the
   sandbox. Claude drops `--no-session-persistence`, so its transcripts are
   written, and gets `--setting-sources project --permission-mode
   bypassPermissions --strict-mcp-config --allowedTools TodoWrite`. Codex
   drops `--ephemeral` and `--ignore-user-config`, because the sandbox's own
   config holds its proxy provider. It runs `--sandbox danger-full-access`
   with the sandbox's MCP gateway disabled. `bypassPermissions` and
   `danger-full-access` are safe only because the sandbox is the boundary. The
   prompt still starts with `/poteto-mode` or `$poteto-mode`.
5. `sbx_inside.py harvest` writes the workspace diff and copies the agent's
   session store, `~/.claude/projects` or `~/.codex/sessions`, which holds the
   lead's session and every delegate's. The wrapper copies both out, with the
   sandbox's network log, into the run's harvest slot. Then it removes the
   sandbox, even when the run fails. `sandbox.py gc` removes any `canon-*`
   sandbox a killed run left behind. Do not run it while a screen is running.

The harness takes exactly one terminal `result` event from a Claude stream.
A poteto-mode lead emits one each time it ends a turn while a background
delegate runs, and one more at the end. So for Claude the wrapper reads the
agent's stdout line by line, drops every `result` line but the last, and
forwards the rest in order. It writes the whole stream to `raw-stream.jsonl`
in the harvest dir. Codex's stream passes through unchanged.

The harvest dir of a run holds `workspace.diff`, `workspace.json`,
`network-log.json`, `raw-stream.jsonl` for Claude, and
`transcripts/claude/<project>/<session>.jsonl` with
`<session>/subagents/agent-*.jsonl` and `.meta.json`, or
`transcripts/codex/sessions/YYYY/MM/DD/rollout-*.jsonl`. `workspace.json`
records the sandbox name, the template, the CLI versions, the timings, the
network rules that applied, and `reachable`, the policy decision for each
model API host and each denied host.

**Auth.** Credentials never enter this repo or a run directory. `sbx secret`
stores them on the host, and the sandbox's proxy adds them to model API
requests. The Codex kit writes a `~/.codex/config.toml` whose provider sends
requests to `chatgpt.com/backend-api/codex` through that proxy with a
placeholder token. The Claude kit writes `~/.claude/.credentials.json` when a
sandbox is created, even from a template whose copy was deleted, and `sbx
secret ls` lists the Anthropic secret as OAuth. On 2026-09-25 a Claude run
inside the sandbox stopped with "OAuth session expired and could not be
refreshed", so that stored token had most likely expired. Refresh it before a paid Claude run, for example by
storing an API key with `sbx secret set anthropic`, and confirm with one short
prompt. `sbx secret set` supports `--oauth` for OpenAI only.

**Network.** The host's global policy denies by default. Each agent kit adds
its own hosts to that sandbox. Claude's kit adds the Anthropic API and the
claude.com hosts. Codex's kit adds chatgpt.com, the OpenAI API, GitHub, npm,
and the Ubuntu archives. A run sandbox adds a per-sandbox deny rule for every package index
and source host in `sbx.json` `run_deny_network`, so a run reaches only its
model API. A local deny can only narrow egress. The dependency build is the one
step that reaches PyPI, GitHub releases, and astral.sh, through per-sandbox
allow rules (`build_network`) on a sandbox that is removed afterwards.

**Dependencies.** `sandbox.py deps` builds one template per agent, repo, and
commit. It creates a sandbox with no workspace and extracts the pinned commit
under `/opt/canon-deps/<repo>/src`. It installs uv from `sbx.json` (the
kit's uv 0.9.26 is older than omnigent's `required-version`) and the repo's
pinned Python. Then it runs `uv sync` against the repo's lockfile, with
`--frozen --group test` and `OMNIGENT_SKIP_WEB_UI=true` for omnigent (its build
otherwise runs pnpm) and `--frozen --extra dev` for hermes. The venv, the uv cache, and the
interpreter live under `/opt/canon-deps`, outside every workspace. The source
copy and the kit's credential files are deleted before `sbx template save`.
At run time setup links `.venv` to that venv and reruns the same `uv sync`
offline, which reinstalls the project's own editable packages from the clone.
The agent runs with `UV_OFFLINE=1`, `UV_PYTHON_DOWNLOADS=never`, and the repo's
env, so `uv run pytest` works without the network. The record of each build
sits under `$CANON_CACHE/sbx/`.

**Tools observed.** `sandbox.py probe` builds a run-shaped sandbox and lists
what the agent is offered without a paid model call. Claude gets a model name
that does not exist, and its init event lists tools, agents, and slash commands
before it fails. Codex is pointed at a local server inside the sandbox that
records the request and answers 400. Observed on 2026-09-25, with and without
a dependency template:

- Claude Code 2.1.280 runs in `bypassPermissions`. Its tools are Task, Bash,
  Edit, Read, Write, NotebookEdit, Skill, TaskCreate, TaskGet, TaskList,
  TaskUpdate, TaskStop, ToolSearch, WebFetch, WebSearch, Workflow, and
  others. Its agents include poteto-agent and comment-sicko, and poteto-mode
  is a slash command. Without `--allowedTools TodoWrite`, the same `-p` run
  lists none of TaskCreate, TaskGet, TaskList, or TaskUpdate.
- Codex 0.149.1 gets exec_command, write_stdin, update_plan,
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
repack, and `sbx_inside.py` setup and harvest on a plain clone. With
`CANON_SBX_E2E=1`, it also runs both arms of a workspace rule for each agent
in real sandboxes with `offline/sbx-agent` as the agent. That stand-in exits
nonzero unless the prompt carries the invocation, the skills are linked, the
persona is registered, the flags give it full tools, and its cwd is the
clone. It applies the sample diff and writes a trace with one worklist call and
one poteto-agent spawn, plus transcripts for the lead and the delegate.
Claude's trace carries two `result` events, and the test checks that
`raw-stream.jsonl` holds both. Both agents print `SEPARATES`, and each takes
about 50 seconds. `chain.py` over that output reports the worklist tool called, one spawn with the poteto-agent
briefing, and the delegate's read of `poteto-mode/SKILL.md`, for both agents.
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
in a workspace case, subagent spawns and whether a Claude brief names the data
shape, principle citations in the reply, and denied tool calls. It parses Claude
stream-json and Codex `exec --json` traces into one event list, so both agents
go through the same stage code. `test_chain.py` checks the parsers against
trimmed real traces in `fixtures/chain/`.

```sh
python3 evals/canon/chain.py --markdown                 # stage rates per agent, workspace verdict cross-tab
python3 evals/canon/chain.py --jsonl /tmp/chain.jsonl   # one JSON line per run
```

It reads `/private/tmp/canon-entry`, `/private/tmp/canon-ws`, and
`/private/tmp/canon-screen` unless given roots. In those runs Codex's stream
shows waits on a delegate but no spawn or brief, and Claude's `-p` sessions
offer no worklist tool. Those stages read "not visible" or zero because of the
harness, not the agent.

A sandboxed run also harvests the agent's own transcripts next to its
workspace diff, in `harvest/<run>/transcripts/`. Claude writes each delegate to
`claude/<project>/<session>/subagents/agent-<id>.jsonl`, with a `.meta.json`
naming its `agentType` and the lead's spawning `toolUseId`. Codex writes one
rollout per thread under `codex/sessions/`. A child's `session_meta` names its
`parent_thread_id` and `agent_role`. When those files exist, `chain.py` parses
each delegate's reads, edits, spawns, worklist calls, and messages with actor
`delegate`. It places them right after the spawn that started them, so every
stage sees them. They fill `delegation.delegate_reads` and `delegate_edits`.
Workspace edits are judged against the child's own cwd, which in a sandbox may
sit under `/tmp`. A run without a `transcripts/` dir yields the same fields as
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
  line from `roles.json`. A Codex spawn counts when the child rollout's role is
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
prefix. A checklist under a `**Worklist.**` marker, which the checklist arm of
`bundle-worklist-feature` and `bundle-worklist-refactor` generates with
`poteto-mode/scripts/playbook-checklist`, restates the steps and adds none; each
of its lines keeps its step's identity and every pointer. `worklist.steps`
records per step whether some item keeps the identity and which pointers that
item keeps. The stages are "worklist present
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
skill, such as `/root/how_harness_family`. Arena and swarm ship no template,
so their runners are known only by a brief or path that names them. The
stage "implementation delegate ran as poteto-agent" counts code-writing
delegates outside a routed skill. "delegate outside a routed skill got the
poteto-agent briefing" counts every such delegate. `role_census` gives, per
role, spawns, code-writing, prescribed, poteto-agent, and implementation
misses, and `--markdown` prints it per agent.

**Result events.** A Claude lead that ends a turn while a background delegate
runs emits a `result` each time. The last one is the answer, and
`result_events` counts them. For a sandboxed Claude run, `chain.py` reads
`harvest/<run>/raw-stream.jsonl` in place of `trace.jsonl` when it exists. A
run that `screen.py regrade` graded takes its verdict from `regrade.json`.

`fixtures/chain/sbx-codex/` holds trimmed files from a real Codex sandbox
probe. `fixtures/chain/sbx-codex-roles/` and `claude-multi-result.jsonl` are
trimmed from real `/private/tmp/canon-sbx` runs. `fixtures/chain/sbx-claude/`
is synthetic.

## Reading the result

Read the rule line first, then the case lines. A near-miss case that never ran
shows as `missing` and blocks the rule. An `unexposed` pair is not a tie. It
means the amended arm never read the patched file. One repetition cannot show
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
