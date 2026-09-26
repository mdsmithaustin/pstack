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
  test_oracle.py      unit tests that grade the samples
  cases/<case-id>/
    case.json         kind (positive or near-miss), domain, timeout_s, expected_behavior
    prompt.md         the user request; {project} expands to the project files
    project/          the fixture the answer edits
    samples/good.md   an answer that must pass
    samples/bad.md    an answer that must fail
oracles/
  check.py            check.py <rule> <case> <output_dir>
  shared.py           answer parsing, Python helpers, the sandboxed container runner
  probes/run.py       runs answer code inside the container
```

Each arm root holds the grader next to the skill tree: `oracles/`, the rule's
`oracle.py`, and the case's `project/`. It never holds `samples/`,
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
   `project/`. Add a near-miss case when the rule has an exception the agent must respect.
4. Write the prompt as an organic user request that does not name the rule. The
   prompt with its project files, and the case id, must not contain
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
   the `project` it is given.
6. Add `samples/good.md` and `samples/bad.md` to every case, and assert their
   exact failure lists in `rules/<id>/test_oracle.py`, which imports
   `from check import grade`.
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

The offline stand-in matches the prompt, and a case that a variant shares with
its source goes to the rule whose inserted text is mounted.

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
lists an arm rule's arms and each arm's changed files.

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
gets 900 seconds in this mode.

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
discards the agent's workspace. Oracles that run answer code use the pinned
`python:3.12-slim` image with no network, a read-only root, and no
capabilities.

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

## Stopped runs

Every command that takes `--out` appends the traceback of any error to
`<out>/screen-error.log` and prints the log's path on both stdout and stderr.
A caller that filters one stream still sees it. `run` logs a failed arm and
goes on to the next arm, then exits 1 naming each failed arm.

## Rule texts

R6 is labeled "Observe through the caller's interface". It sits right before
**The fix** and narrows that paragraph's mock sentence to "For a mock at a
system boundary, assert the payload it received, not that it was called", so
both edits form one hunk.

## Model-free checks

These need Docker, `uv`, and a skill-ci checkout at `../skill-ci` or
`$SKILL_CI` with its `runner.lock`. `audit` and `run` call the harness through
`uv run <skill-ci>/tools/run_runner.py`. Without a running Docker daemon, the
oracle tests that run answer code skip. The unit tests need neither skill-ci
nor `uv`; only `audit` and `run` do. The `lint` workflow pulls the image and
runs the unit tests on every pull request.

```sh
docker pull python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36
(cd evals/canon && python3 -m unittest)
python3 evals/canon/screen.py plan
python3 evals/canon/screen.py audit --entry poteto-mode
CODEX_BIN=evals/canon/offline/codex python3 evals/canon/screen.py run --agent codex --out "$(mktemp -d)/offline"
CODEX_BIN=evals/canon/offline/codex python3 evals/canon/screen.py run --agent codex --entry poteto-mode --out "$(mktemp -d)/offline"
```

`python3 -m unittest` runs `test_screen.py`, `test_arms.py`, and
`test_oracles.py`, which loads `oracles/test_shared.py` and every
`rules/*/test_oracle.py`. `audit` validates, audits, and prepares both arms of every
case. A positive case's manifest accepts one readiness blocker, "no adversarial
cases", because it holds one case. Any other blocker fails it. The last two
commands run the whole pipeline with a stand-in `codex`. For a positive case it
answers with `good.md` only when the rule text is mounted, and with `bad.md`
otherwise. For a near-miss case it answers with `good.md` in both arms. When
the workspace mounts `skills/pstack`, it exits 3 unless the prompt starts with
`$poteto-mode ` and `.agents/skills` holds the tree. Both runs must print `SEPARATES` for every
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
