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
injected the entry skill.

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
The offline stand-in applies the chosen sample's diff in its cwd.

Each run costs one checkout. On an Apple silicon Mac on 2026-09-24, omnigent
(5,545 files) took 1.0 s to check out, 0.3 s to diff, and 102 MB of disk.
hermes (15,249 files) took 2.0 s, 0.8 s, and 189 MB. The harness deletes the
workspace after each run. `run_agent_tasks` in `skill_benchmark.py` at the
pinned commit c2a1735 creates it with `tempfile.TemporaryDirectory`. The
mirrors take 38 MB and 76 MB once, and each reference checkout takes the same
space as one run.

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

`python3 -m unittest` runs `test_screen.py`, `test_workspace.py`, and
`test_oracles.py`, which loads `oracles/test_shared.py` and every
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
