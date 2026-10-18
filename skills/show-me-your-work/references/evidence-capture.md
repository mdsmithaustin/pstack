# Retain evidence after checkout cleanup

Choose an absolute store that you will retain after the source checkout disappears. Use the primary checkout's `.audit/<task>/evidence` or another persistent directory. Carry its absolute path in handoffs. The helper cannot infer retention from a directory name.

Run the helper on POSIX with Python 3.10 or later. It uses only the standard library. Every path input must be absolute and contain no `..` components, including file sources and verification manifests. The helper rejects these inputs before path normalization. Capture a command with an explicit cwd and a direct argv vector:

```sh
python3 skills/show-me-your-work/scripts/evidence.py command \
  --store /persistent/task/evidence --id check-01 \
  --cwd /temporary/task-checkout -- \
  python3 -c 'import sys; print("out"); print("err", file=sys.stderr); sys.exit(7)'
```

Capture success means helper exit 0 and one absolute `manifest.json` pointer on stdout. The child's raw return code is 7 in this example. Separate binary stdout and stderr survive a nonzero child exit. A negative raw return code means signal termination on POSIX. Helper failure means a nonzero helper exit and no completed pointer. There is no timeout, retry, or shell evaluation. To impose a deadline, supply your own wrapper and describe its outcome as that wrapper's outcome.

Command launch retains the directory descriptor from the no-follow walk. Its device/inode pair identifies the validated directory, even if someone replaces the cwd entry or an ancestor before launch. A fresh isolated Python process calls `os.fchdir` on that inherited descriptor, closes it, and calls `os.execvp` with the supplied argv. Exec replaces that same process, so its raw return code remains the command outcome. A private close-on-exec status pipe distinguishes setup or exec failure from command exit. The record retains the caller's cwd string. The parent never changes its cwd, and launch never resolves the supplied cwd pathname again.

This mechanism supports POSIX hosts with Python's `fchdir`, descriptor inheritance through `subprocess`, and exec, including macOS and Linux. Missing support or failed setup leaves an occupied incomplete ID with no completed pointer and no requested command launch. There is no pathname fallback or `preexec_fn`. Python documents [descriptor-based cwd changes](https://docs.python.org/3.10/library/os.html#os.fchdir), [exec process replacement and PATH search](https://docs.python.org/3.10/library/os.html#os.execvp), [descriptor inheritance through pass_fds](https://docs.python.org/3.10/library/subprocess.html#subprocess.Popen), and [isolated interpreter mode](https://docs.python.org/3.10/using/cmdline.html#cmdoption-I). Directory binding does not isolate the command from changes to directory contents or the rest of the host.

The child receives only `.stdout-staging` and `.stderr-staging` descriptors. After the direct child exits, the helper freezes both staging byte lengths before copying either bounded prefix into fresh final payload files. Published final bytes stay stable after descendants write to their inherited descriptors. This does not promise an atomic historical point-in-time view of staging bytes that descendants may seek or overwrite during copying. The helper never waits for, signals, or kills descendants. Staging files remain for inspection, including on failed or short copies, which leave the ID incomplete with no completed pointer. Staging names are not valid manifest payload names.

Import an explicitly selected regular file without executing it:

```sh
python3 skills/show-me-your-work/scripts/evidence.py file \
  --store /persistent/task/evidence --id report-01 \
  --source /temporary/task-checkout/report.json
```

Put the printed manifest path in the existing decision log's `evidence` cell. Choose the decision and result yourself. An import records the copied bytes and original path. It establishes no execution outcome or historical atomic version of a changing source file.

Verify the saved artifact before deleting its original checkout:

```sh
python3 skills/show-me-your-work/scripts/evidence.py verify \
  /persistent/task/evidence/check-01/manifest.json
```

Verification exits 0 and prints the capture record as JSON when its structure and saved bytes pass. A nonzero exit means an incomplete, malformed, unsafe, or corrupt capture. Verification reads the saved artifact without consulting original sources. It does not decide test sufficiency or whether a workflow passed.

Each ID has one directory. IDs contain 1 to 80 ASCII letters, digits, dots, underscores, or hyphens, and start with a letter or digit. The helper reserves the directory before reading inputs or starting a child. A completed or incomplete ID stays occupied. Choose a new ID for another attempt. There is no overwrite, repair, deletion, or resume command. Different IDs need no shared lock. Two callers racing for one ID have one winner.

The helper saves capture facts in `record.json`. It hashes that record and all payloads in `manifest.json`, which it publishes last with an atomic no-replace operation. It refuses symlinks in paths, including parent directories, and nonregular source or payload files. Empty files and streams are valid. Retain incomplete directories for inspection. Hashes detect changes relative to the manifest. They do not authenticate the origin of a record or protect against an owner rewriting both the manifest and its files. This is local capture, with no promise of recovery after disk loss.

## Retain identity claims with their limits

Both capture operations accept `--identity /absolute/path/request.json`. Supply only explicitly selected sources. The helper never searches session stores or reads identity from the environment.

```json
{
  "requested": {"harness": "codex", "model": "requested-id", "effort": "high"},
  "resolutionContext": {
    "workModel": null,
    "resolvedArm": {"role": "feature", "arm": 1, "model": "configured-id", "effort": "high", "source": "user flat"}
  },
  "runtimeRecords": [
    {"source": "/temporary/task-checkout/session.jsonl", "line": 12,
     "modelPointer": "/payload/model", "effortPointer": "/payload/effort"}
  ]
}
```

`requested` and `resolutionContext` retain supplied settings and raw resolver data. They do not establish execution identity. Omitting a section preserves null. A supplied context with `workModel: null` stays distinct from no context.

Each runtime selector names an absolute regular file, an optional one-based physical JSONL line, and at least one JSON Pointer. LF separates JSONL records; CR remains JSON whitespace, including in CRLF files. Omit `line` for a JSON document. The helper snapshots each basis file and extracts the selected strings. Invalid pointers, absent lines, and nonstring values fail capture. Missing or null fields remain unknown. A second non-null claim for the same field fails, including matching values. No implicit precedence selects one record.

Saved claims say `runtime-reported` and include the saved basis path, line, and pointer. Verification resolves those pointers against the same saved bytes it hashes. Configured values never fill missing observations. `provider_execution` always remains `unknown`. A runtime report is a declaration, not authenticated proof of which provider served it. Fixture identity records test this storage behavior. A native or live conclusion needs its own saved native or live record.
