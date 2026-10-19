# Native application attempts

`application.py` owns one Codex application attempt, its immutable capture, and fresh replay. A study supplies public project files, assigned skills, a prompt, and a prepared sandbox template. The module accepts no grader or private oracle path.

```python
from pathlib import Path
from application import Request, Runtime, Snapshot, replay, run_application

project = Snapshot.freeze(Path("public/starter"), Path("run/inputs/project"))
skills = Snapshot.freeze(Path("public/skills"), Path("run/inputs/skills"))
runtime = Runtime(
    template="docker.io/library/pstack-port-value-codex:0.162.0",
    model="gpt-6.1-sol",
    effort="high",
    timeout_s=240,
)
result = run_application(
    Request(runtime, project, skills, "Implement the requested application behavior."),
    Path("run/attempts/initial"),
)
if result.capture is not None:
    application = replay(result.capture, Path("run/replays/initial"))
    maintenance = run_application(
        Request(runtime, result.capture, skills, "Apply the maintenance request."),
        Path("run/attempts/maintenance"),
    )
```

Set `skills=None` for native execution without assigned guidance. Maintenance can use any returned capture, including a capture from an attempt with `native_valid=False`. The study decides whether to grade or maintain it.

## Public contract

All four records are frozen dataclasses.

- `Runtime(template, model, effort, timeout_s=240)` identifies the prepared Codex template and requested execution settings.
- `Snapshot(directory, sha256)` identifies an immutable store. `Snapshot.freeze(source, destination)` creates that store from a directory.
- `Request(runtime, project, skills, prompt)` binds the public inputs. `skills` is a snapshot or `None`.
- `Result(state, native_valid, capture, receipt, elapsed_s, usage, native_elapsed_s=None)` records attempt facts. `capture` is a snapshot or `None`. `usage` is the native terminal event's reported dictionary or `None`.

`run_application(request, slot)` claims a new slot and returns a `Result`. An existing slot raises `SpentAttemptError`. A crash leaves the slot spent. Recovery never retries it.

`replay(snapshot, destination)` checks the inventory, content hashes, stored permissions, and relative paths before creating a new destination. It returns that destination. Existing destinations fail. Replaying a full capture preserves file deletions because it reconstructs only the captured inventory. File and directory modes come from the captured inventory.

A snapshot rejects symbolic links, special files, `.git` entries, permissions outside `0777`, more than 10,000 entries, files over 16 MiB, and total file content over 64 MiB. Snapshot stores contain a content-addressed blob directory and a hashed manifest. Their files have mode `0444`, and their directories have mode `0555`. Replay rejects changes to these store modes. Application roots reserve `.agents` and `.codex` for native configuration outside the captured application.

## Isolation and execution

The module creates a small staging Git repository containing `project/` and the assigned `.agents/skills/` directory. Staging removes inherited Git environment overrides, ignores user and system Git configuration, and force-adds all snapshot files, including ignored build outputs and caches. Staging and sandbox setup disable content transformations through the highest-precedence `.git/info/attributes` rules. Setup force-checks out the raw index before inventory validation, preserving original LF and CRLF bytes despite project, nested, or host attributes. It recreates declared directories that Git cannot store, including nested empty directories and empty input roots. It checks cloned paths and content against the validated input inventories, restores their exact declared modes, and verifies both digests before installing personas. The receipt retains the inventories after index checkout and directory reconstruction, before mode restoration. Each attempt creates its own `sbx create --clone --skills off` sandbox from that repository. The candidate cannot see the parent repository, another arm, or private grading files through the cloned workspace. The module adds no Docker socket mount.

Codex runs in `project/`. Its parent directory supplies project skills. When the assigned tree contains the pstack native agent installer, setup registers those project personas through that installer. Delegation remains enabled for every arm. Setup rejects a CLI that lacks the required delegation feature or execution flags.

The native process uses a new session, isolated `HOME` and `CODEX_HOME`, no user config or execpolicy rules, disabled hooks, disabled apps, disabled host skill discovery, and an empty MCP server table. A disabled server entry still requires a valid transport in Codex 0.162.0, so the module sets `mcp_servers={}` instead of creating a gateway entry with only `enabled=false`. All arms receive the same feature settings. The sandbox's `sandboxd` model provider is an explicit transport setting. It uses the sandbox proxy at `https://chatgpt.com/backend-api/codex`. The module copies no host credential files. It records requested model settings and leaves `observed_model` unknown when native events provide no model identity.

The template must match an exact image ID or full `repository:tag` in the local inventory. The prepared template must already contain Codex, Python, and Git. The module does not install them per attempt. Setup checks the native version and capabilities. The receipt retains the selected local template inventory entry and the CLI version. The sandbox policy must deny an unrelated network destination.

Every transport operation has a timeout. Creation and setup allow 120 seconds each. Other transport operations allow 60 seconds each. The inner native process has the requested deadline, and the outer execution command allows another 15 seconds. Timeout handling kills the native process group. The host command helper terminates and then kills its own process group. Teardown removes the named sandbox and confirms its absence from the sandbox listing.

## Result and receipt facts

`native_valid=True` requires exit code zero, a `turn.completed` event, no native failure event, no malformed native JSON event, a valid capture, unchanged assigned guidance, and confirmed sandbox removal. A complete valid capture can survive a nonzero exit, a missing terminal event, or a timeout. Cleanup failure returns `capture=None` so grading cannot begin while the sandbox may still be live. The receipt retains private capture facts for diagnosis.

The `state` is `completed`, `native_failed`, `timeout`, `setup_failed`, `capture_failed`, `cleanup_failed`, or `interrupted`. Setup failures include inputs found invalid or changed before execution. Capture failures include failed harvest, invalid capture data, or input snapshots or assigned guidance found changed after execution. Post-run integrity failures retain an otherwise valid capture. Cleanup failure overrides native success. A receipt records the detailed error and the native facts when available.

`elapsed_s` measures total time from slot claim through teardown, including infrastructure and setup. `native_elapsed_s` measures only the native subprocess wall-clock duration inside the sandbox, including its termination. Both the result and receipt expose these measurements; native timing stays `None` when no measurement survives, including an outer timeout or interrupt before native status is written. Studies must select and label their reported timing explicitly.

Before sandbox creation, `claim.json` persists the request digest, runtime settings, project and guidance hashes, prompt hash, implementation hash, and deterministic sandbox name. `receipt.json` commits the final facts after teardown. Native stdout and stderr remain in `harvest/`. Usage stays unknown when the native terminal stream reports none. The module performs no grading.

## Verification

Run from the repository root.

```sh
python3 -m unittest discover -s evals/canon -p test_application.py -v
```

A nonzero exit, an `ERROR` or `FAIL` test result, or a summary with zero tests means verification failed. These tests execute a recording native CLI through a recording sandbox transport. A real prepared-template smoke must also run before launching a study.

The optional setup-only integration check uses a real prepared template and calls `config/read`, never a model turn. It checks ignored files, nested empty directories, LF and CRLF files with nested attributes, and mixed project and guidance modes across an actual `sbx --clone`, setup and harvest, and project configuration loading on a path with dots and spaces. The old dotted trust override is a negative control. The app server uses an empty isolated home; the execution command retains `--ignore-user-config`.

```sh
CANON_APPLICATION_TEMPLATE=docker.io/library/pstack-port-value-codex:0.162.0 CANON_APPLICATION_EVIDENCE="$PWD/eval-runs/application-review" python3 -m unittest discover -s evals/canon -p 'test_application*.py' -v
```

A nonzero exit, an `ERROR` or `FAIL`, or a skipped native delivery test means the integration check did not pass. Evidence includes inventories before mode restoration, native configuration responses, harvested snapshots, and the final sandbox listing. Only the check's named sandbox is removed.
