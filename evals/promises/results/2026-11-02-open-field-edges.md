# Open field edges, 2026-11-02

**Status: NULL.** In every run that delivered the feature, the code kept the new field's unstated value space open. That holds for 6 of 6 runs on Claude Code and 3 of 3 on Codex, across both cases. The cases do not reproduce the failure they were built from, so they cannot show that skill text prevents it. No skill text changed.

## Why these cases exist

In a SlopCodeBench round on 2026-11-02, one checkpoint spec added a `destination` field whose examples all showed `backup://store`. The spec never restricted the scheme. Runs that copied the neighbouring `source` field's `mount://` check onto `destination` rejected `destination: ignored://sink`, which the hidden tests send. They failed about 29 more tests than runs without the check. The check appeared in every pstack-v4-high run, in 2 of 3 pstack-v3-high runs, in every codex-high run without pstack, and in no solo-high run.

The proposed fix was skill text saying that an edge neither the spec nor current code settles stays open in the code. These cases were built to measure that fix before shipping it.

## What ran

The [suite guide](../README.md#feature-spec-edges) describes `feature-edges-open-field` and `feature-edges-required-field`, their histories, held-out checks, and shared grader.

The second case tests whether the word "required" triggers the extra check, because every benchmark run that over-validated added the required check and the scheme check together.

- Skills pin: `f17b6305` (main after #393). Command: `python3 evals/promises/live.py run --harness <claude-code|codex> --model <claude-sonnet-5-5|gpt-6.1-sol> --effort high --runs <3|2> --skills-at f17b6305 --case <case> --out <dir>`.

At the time of these runs, `open-scheme-out` checked the exit status and printed totals but did not check exported files. The current check also verifies those files. The grades below are the original results. A recheck ran the current `held_out.py` directly against each run's project, using the worktree for the two Claude Code runs that delivered there. All 9 delivered implementations passed every check, and the undelivered Codex run failed both edges.

## Results

| Case | Harness | Graded | Code keeps the scheme open |
|---|---|---|---|
| open field | Claude Code | 2 PASS, 1 FAIL | 3 of 3 |
| open field | Codex | 2 PASS | 2 of 2 |
| required field | Claude Code | 2 PASS, 1 FAIL | 3 of 3 |
| required field | Codex | 1 PASS, 1 refused | 1 of 1 delivered |

- Both Claude Code FAILs come from where the lead delivered. It committed on a branch in `.worktrees/export` and left the main checkout untouched, so `held_out.py` found no `--out` option. Read directly, each worktree's `config.py` accepts any scheme and checks only that `://` is present and that the path stays inside the output folder.
- The refused Codex run left an arena candidate worktree under `/tmp`, and the grader refused it as `unapproved_worktree`. Its project had no export code yet, so it is evidence in neither direction.

## What this shows

- On this task, neither copying a neighbouring field's rule nor the word "required" makes the lead invent a scheme check. The benchmark failure needs something these cases lack. Candidates include a larger file, several checkpoints of history, and a spec example that shows `source: mount://` next to `destination: backup://store`.
- The proposed text, "the brief adds no check for an open edge", would also discourage checks that no spec states but that are correct. The runs here added path-traversal guards that way. The fix stays unshipped until a case reproduces the failure.
- The worktree delivery that the Claude Code FAILs show also affects the `feature-edges-*` cases, because every one grades the main checkout.
