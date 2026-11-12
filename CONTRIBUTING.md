# Contributing to pstack

This page covers the local checks, the git hooks, and how they relate to CI. For what the port changes and how to sync from upstream, see [PORTING.md](./PORTING.md). For the eval suites, see the [evals guide](./evals/README.md).

## Contributor checks

CI uses Python 3.12, Bun 1.4.0, and the runner's preinstalled Node. For the git hooks, create the local virtual environment in the main checkout, install the `skill-ci` command, and install the hooks. The gate selects its interpreter separately, as described below.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r tools/harness-test-requirements.txt
uv tool install git+https://github.com/mdsmithaustin/skill-ci.git
lefthook install
```

Run the local gate tiers from the repository root:

```sh
tools/gate-check.sh lint
tools/gate-check.sh test
```

The `lint` tier checks cross-suite references, the [mode entry byte budget](./skills/pstack-harness/references/skill-retention.md), personal home paths, the generated subagent bundle, the promise ledger and its canonical form, [live promise evidence freshness](./evals/promises/README.md#keep-live-evidence-aligned-with-changes), the shipped models config, the [context byte budgets per route](./tools/check-route-bytes.py), skill line length (`tools/check-line-words.py`), and skill reference spelling (`tools/test_skill_references.py`). The skill reference spelling scope and exceptions are documented in [PORTING.md](./PORTING.md#substitution-map). `skill-ci check` runs the shared skill checks, as described below. The `test` tier runs the tools, promise, setup-pstack, and pstack-harness unit suites. It installs the poteto-mode script and test dependencies and the pr-recap sketch dependencies with their frozen lockfiles, runs both Bun test suites and poteto-mode's typecheck, then installs the statechart test dependencies with their frozen lockfile and runs the statechart script tests with `node --test` through `bun run test`. The statechart tests are TypeScript, so they need Node 22.18 to 22.x, or Node 23.6 or later. Most lint checks also run in the test tier, against the same committed files. The tools unit suite also runs skill reference spelling, skill line length, the route byte budgets, and the repository mode entry byte-budget check, and it runs the subagent bundle check on a copy of the committed sources. The promise unit suite also audits the promise ledger, checks its canonical form, and runs the strict evidence freshness check. The setup-pstack unit suite also lints the shipped models config. Only the cross-suite reference check and the personal home path check run in the lint tier alone. The script runs every check in the selected tier, prints a PASS or FAIL line for each, and exits nonzero if any check fails. Unit suites and Bun tests must report tests, not a zero-test success.

The statechart suite runs its TLC-dependent tests only when `TLA2TOOLS` names `tla2tools.jar`, and skips them otherwise. `JAVA` names the Java binary and defaults to `java` on `PATH`. The `lint.yml` skills job runs the suite on every pull request. It has no TLC, so it skips those tests. The `statechart-tlc.yml` job runs the suite again with TLC, only when a change touches `skills/statechart/`, `tests/skills/statechart/`, or that workflow. It downloads the jar that `TLC_TOOL` in `skills/statechart/scripts/run.ts` pins, checks its sha256, sets `TLA2TOOLS` to the jar and `JAVA` to the runner's Java of the version `JAVA_TOOL` pins, and fails when no test runs or when a test skips for lack of TLC. The render tests install Pele and Mermaid with npm into `~/.cache/statechart`, so they need the network. That job is not a required check, because a path-filtered workflow that does not run would leave a required check pending.

`python3 tools/check-personal-paths.py` scans the names and current contents of every Git-tracked file for concrete account names below `/Users/<account>` or `/home/<account>`. It scans symlink target spelling without following the link, skips contents containing NUL bytes as binary, and decodes other bytes with UTF-8 replacement. Filenames are checked even for binary files. Exact file-scoped content exceptions cover existing synthetic fixtures. An unused exception fails the default working-tree check used by the gate and CI. Index and pushed-tip modes suppress exact known synthetic matches without requiring every fixture to exist in each snapshot. Diagnostics redact account names and identify the file and line without printing source contents. Line 0 identifies a filename finding. Exit 1 means a personal path was found. Exit 2 means file acquisition or exception validation failed, or no tracked text files were inspected. A successful scan exits 0 and reports the number of tracked text files checked. Pre-push exits 0 without scanning when Git supplies no nondeleted local tips. The required CI `skills` job runs this checker explicitly, alongside the shared skill-ci checks.

The script needs neither mise nor the main checkout's `.venv`. It selects `PSTACK_GATE_PYTHON` when set to a Python executable, then `$HOME/.local/share/mise/installs/python/3.14.7/bin/python3.14`, then `uv` on PATH with Python 3.12. This gate runner choice uses the environment's `HOME`. The native evaluators derive their confined runtime paths from the operating system account database, as documented in [the promise suite README](./evals/promises/README.md#run-the-model-free-checks). The native version pin is deliberate because Python 3.12 fails the native fsmonitor control on the reviewed host. The test tier also needs Bun, Node, `rg`, `jq`, `gh`, and `openssl` on `PATH`. `mise run gate-lint` and `mise run gate-test` wrap the same script.

Install `tools/harness-test-requirements.txt` into the interpreter selected for local checks. Without pytest, its preservation cases skip. CI installs these pinned, hashed dependencies before the harness suite, so those cases execute. To use the environment created above, set `PSTACK_GATE_PYTHON="$PWD/.venv/bin/python"` when running the gate. Dependency installation fails on a nonzero exit. Treat a nonzero harness exit or a zero-test summary as failed verification. A Python 3.9 compatibility probe can skip when that separate interpreter is unavailable.

Regenerate the test dependency lock with `uv pip compile --python-version 3.12 --universal --generate-hashes --no-annotate --no-header --output-file tools/harness-test-requirements.txt tools/harness-test-requirements.in`. A nonzero exit means resolution failed. The lock targets Python 3.12 and newer.

`.no-mistakes.yaml` runs the `lint` tier and then `skill-ci check` as the gate's Lint step. It leaves the Test step to the pipeline's targeted checks, because no-mistakes reserves `commands.test` for targeted validation of the change, not a full suite that mirrors CI. Run the `test` tier yourself before a large change. GitHub CI remains authoritative and additionally runs the Docker oracle and maintained canon suites, the npx installation probe, the Linux worktree-audit job, and, for statechart changes, the statechart TLC job. Those checks stay outside the local gate tiers. CI cancels superseded pull-request runs of `lint.yml`, `skill-checks.yml`, and `statechart-tlc.yml`; pushes to main never cancel. The gate fills PR bodies from `.github/pull_request_template.md` through `pr.template`, omits intent from them, keeps a minimal appendix with the risk line and head attestation, and protects `.github/workflows/**` and `.github/rulesets/**` from automatic repairs.

The repository also enables CI repair for green GitHub PRs that are behind main. No-mistakes carries Review approval only when it proves a pure replay.

To reproduce the Docker suites and installation probe manually, use the commands below. Follow the [application and grader instructions](./evals/canon/README.md) for their prerequisites.

```sh
docker pull python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36
(cd evals/verify-commands/oracles && python3 -m unittest -v test_check_plan)
(cd evals/canon && python3 -m unittest -v)
.venv/bin/python tools/probe-subagent-install.py
```

Each command exits nonzero on failure. Each unittest command must report tests, not a zero-test success.

The pre-commit hook runs the cross-suite-reference and personal-path checks with the main checkout's `.venv/bin/python`, from any worktree, and `skill-ci check --fast`, which runs the frontmatter, trigger declaration coverage, content, and staged PII checks. The personal-path pre-commit check uses `--source index` to inspect staged blobs, even when unstaged edits differ. The pre-push hook uses `--source pre-push` with Lefthook stdin forwarding to inspect each nondeleted local tip supplied by Git, and runs the full `skill-ci check`. It scans tip snapshots, not published base history. The default working-tree mode remains the gate and CI interface. For the full skill checks, hook configuration check, and whitespace check:

```sh
skill-ci check
lefthook validate
git diff --check
```

Each command exits nonzero when its check fails.

For guide-promise checks and general live playbook evals, see the [suite guide](evals/promises/README.md).

Behavioral eval manifests and their oracles live at the repository root under `evals/<skill>/`, never inside a skill directory. `npx skills` copies a skill directory verbatim to every consumer and offers no exclude mechanism, so eval material placed there would ship to everyone who installs the skill. `tools/test_eval_artifacts.py` fails if an `evals` or `eval-runs` directory appears under `skills/`. The same reasoning keeps tests out: they live under `tests/`, mirroring their path under `skills/` (`tests/skills/poteto-mode/scripts/`, `tests/skills/pstack-harness/scripts/`, and `tests/skills/setup-pstack/scripts/`), and the same test fails if a tracked file under `skills/` matches a test-file pattern. The Bun and typecheck scripts in `skills/poteto-mode/scripts/package.json` reach into `tests/`. The `.gitignore` rules `**/evals/**/runs/` and `**/eval-runs/` keep raw run transcripts out of git wherever a run writes them.

`.skill-ci.toml` pins the skill-ci release used by GitHub Actions, the git hooks, the no-mistakes Lint step, the mise tasks, and the manual development comparisons. The `skill-ci` command reads that pin and runs that version from any checkout or worktree, and it needs `uv` on your PATH. `skill-ci check` runs the frontmatter and trigger declaration coverage check, the content check with `tools/skill-content-conventions.json`, and the whole-tree PII scan. `evals_dir` points it at the manifests, so for every `evals/**/shared-benchmark.json` it also runs `skill-benchmark validate --strict-leakage` and then `skill-benchmark audit-manifest --fail-on-blockers --strict-judge`, skipping the audit when the manifest has no cases. It runs the harness that the pinned skill-ci release installs, never whatever `skill-benchmark` is on your PATH.

`mise.toml` adds a one-line task for each check and run command, such as `skill-check` for `skill-ci check`. A mise older than 2026.8.9 asks you to run `mise trust` once.

```sh
mise run skill-lint
mise run skill-validate
mise run skill-audit
```

Local runs and CI read the same pin, and each run prints `skill-ci <version> (<commit>)` first, so the two logs show the commit they ran. `skill-ci update` moves the pin to the newest release tag.

The pinned skill-ci runner validates declared `skill_paths`. Both `skill-ci validate` and `skill-ci audit` reject a manifest if an entry does not exist inside the manifest's skill root. `tools/test_eval_artifacts.py` also fails when any manifest under `evals/` names a path that is not a file.

`skill-audit` is stricter than CI on one point. CI skips `audit-manifest` for a manifest with no cases, and the task audits every manifest it finds, so an empty manifest fails locally and passes in CI. Nothing in this repository has one today.

`skill-ci trigger <skill>` and `skill-ci run <skill>` spend model budget on your own logins and never run in CI. Both write to a new directory under `<checkout>.eval-runs/<skill>/`, beside the checkout. Pass `--out` to write under `evals/` instead. skill-ci refuses an output directory inside the skill package.

```sh
skill-ci run skills/unslop --out evals/unslop/runs/$(date +%Y%m%d-%H%M%S)
```

`evals_dir` in `.skill-ci.toml` points every command at `evals/`. Delete it and `check`, `validate`, and `audit` search `skills/`, find no manifest, and still exit 0, so `tools/test_eval_artifacts.py` pins its value.

`tools/skill-trigger-cases.json` checks deterministic trigger declaration coverage. It confirms that every shipped skill has a realistic request, literal description anchors, and the expected invocation policy. `implicit_allowed` is false exactly for the skills whose `agents/openai.yaml` sets `allow_implicit_invocation: false`. It does not measure model-routing accuracy.
